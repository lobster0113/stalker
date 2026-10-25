"""Gate B reference bot v1: ICMizer-informed short-stack play plus fixed non-solver rules.

Decision layers (first that applies; see referee/GATES.md Gate B):
1. Short-stack zone (preflop, effective stack <= `short_bb`, default 15bb): when the hero is
   first in (everyone before folded) or faces exactly one all-in (or a raise covering the hero)
   with everyone else folded, play the ICMizer-equivalent equilibrium of the whole table
   (`referee.anchors.icm_reference`): push/fold or call/fold with the solved probabilities.
   The spot is rebuilt from hand-start stacks in preflop action order, so seats that already
   folded still count for ICM. Payouts: the config's prize ratios when the whole field sits at
   this table, chip EV otherwise (v1 limit: no cross-table ICM). Stacks are quantised to 0.5bb
   so a solve is shared by every decision of the hand and by later similar hands.
2. Other preflop spots: the fixed chart `data/preflop_chart_v1.json` (open / 3bet / 4bet-jam
   by top-% of hands); a raise that would commit `jam_if_raise_commits_fraction` of the stack
   becomes an all-in.
3. Postflop: Monte Carlo equity against uniformly random hands of the opponents still in,
   compared with pot odds (fixed thresholds below).

`action_probs(obs)` is a pure function of the observation (MC seeds come from a hash of the
cards), so the same input always gives the same probabilities; `act` samples it with the
injected rng. `action_values(obs)` gives the layer-1 EVs (fraction of the prize pool) behind
those probabilities and `None` on the other layers.
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

import numpy as np

from referee.anchors.icm_reference import Evaluation, Spot, SpotError, Strategy, _scale, _Tree, _value_fn, solve
from stalker.agents.base import Action, Agent, Observation
from stalker.core.cards import HAND_CLASSES, card, hand_class
from stalker.core.equity import equity_vs_ranges
from stalker.core.ranges import class_top_pct, uniform_range

CHART_PATH = Path(__file__).resolve().parent / "data" / "preflop_chart_v1.json"
ICM_REFERENCE_VERSION = "icm-ref-v1"
POSTFLOP_VERSION = "post-v1"
SHORT_BB = 15.0
QUANT_BB = 0.5
SPOT_BB = 20  # chips per bb in the normalised solver spot (QUANT_BB = 10 chips)
SOLVE_TOL = 2e-3
SOLVE_MAX_ITER = 400
POST_NSIM = 300
POST_MAX_OPP = 4
POST_VALUE_BET_EQ = 0.65
POST_RAISE_EQ = 0.80
POST_CALL_MARGIN = 0.05  # random-hand equity overstates us against a betting range
POST_BET_FRACTION = 2 / 3
_CLASS_INDEX = {c: i for i, c in enumerate(HAND_CLASSES)}


@lru_cache(maxsize=1)
def load_chart() -> dict:
    return json.loads(CHART_PATH.read_text())


REFERENCE_BOT_VERSION = (f"refbot-v1+{ICM_REFERENCE_VERSION}+{load_chart()['version']}+{POSTFLOP_VERSION}"
                         f"+short{SHORT_BB:g}bb")


def solve_ranges(spot: Spot, value_model: str) -> Strategy:
    """Pure push/call ranges: every seat's best response to the solved equilibrium.

    Fictitious play stops after few iterations with averaged probabilities like 0.9 for AA;
    the best response to that profile is the range ICMizer shows (mixed only on exact ties)."""
    sol = solve(spot, value_model, tol=SOLVE_TOL, max_iter=SOLVE_MAX_ITER)
    tree = _Tree(spot, _value_fn(spot, value_model, 0, SOLVE_TOL, SOLVE_MAX_ITER))
    return tree.evaluate(sol.strategy).best_response(sol.strategy)


@lru_cache(maxsize=8192)
def _solve_spot(stacks: tuple[int, ...], sb: int, ante: int, bb_ante: int,
                payouts: tuple[float, ...] | None) -> tuple[Strategy, Evaluation, float]:
    """The ranges the bot plays, the EVs (per seat and hand) they best-respond to and the value
    scale (prize pool, or total chips for chip EV) that turns EVs into pool fractions."""
    spot = Spot(stacks, sb, SPOT_BB, payouts or (1.0,), ante=ante, bb_ante=bb_ante)
    model = "chipev" if payouts is None else "icm"
    sol = solve(spot, model, tol=SOLVE_TOL, max_iter=SOLVE_MAX_ITER)
    tree = _Tree(spot, _value_fn(spot, model, 0, SOLVE_TOL, SOLVE_MAX_ITER))
    ev = tree.evaluate(sol.strategy)
    return ev.best_response(sol.strategy), ev, _scale(spot, model)


@lru_cache(maxsize=65536)
def _postflop_equity(hole: tuple[str, ...], board: tuple[str, ...], n_opp: int) -> float:
    seed = int.from_bytes(hashlib.sha256(" ".join(hole + ("|",) + board + (str(n_opp),)).encode()).digest()[:8],
                          "little")
    return equity_vs_ranges([card(c) for c in hole], [card(c) for c in board], [uniform_range()] * n_opp,
                            POST_NSIM, np.random.default_rng(seed))


def preflop_order(obs: Observation) -> list[int]:
    """Occupied seats in preflop action order, ending with SB, BB (heads-up: [button/SB, BB])."""
    seats = sorted(obs.stacks)
    if len(seats) == 2:
        sb = obs.button if obs.button in seats else seats[0]
        return [sb, seats[1] if seats[0] == sb else seats[0]]
    after = [s for s in seats if s > obs.button] + [s for s in seats if s <= obs.button]
    return after[2:] + after[:2]


def hand_start_stacks(obs: Observation, order: list[int]) -> tuple[dict[int, int], int, int]:
    """Preflop only: seat -> stack before posting, plus the (classic ante, bb ante) this hand."""
    dead = obs.pot - sum(obs.bets.values())
    if dead <= 0 or obs.ante <= 0:
        ante, bb_ante = 0, 0
    elif dead > obs.ante:
        ante, bb_ante = obs.ante, 0
    else:
        ante, bb_ante = 0, dead
    start = {s: obs.stacks[s] + obs.bets.get(s, 0) + ante for s in order}
    start[order[-1]] += bb_ante
    return start, ante, bb_ante


class ReferenceBot(Agent):
    """`payouts`: the tournament's prize ratios by place (TournamentConfig.payout_ratios())."""

    version = REFERENCE_BOT_VERSION

    def __init__(self, rng: np.random.Generator, payouts: tuple[float, ...] = (1.0,), short_bb: float = SHORT_BB):
        self.rng = rng
        self.payouts = tuple(float(p) for p in payouts)
        self.short_bb = short_bb

    def act(self, observation: Observation) -> Action:
        probs = self.action_probs(observation)
        acts = list(probs)
        if len(acts) == 1:
            return acts[0]
        return acts[int(self.rng.choice(len(acts), p=np.array([probs[a] for a in acts])))]

    def action_probs(self, obs: Observation) -> dict[Action, float]:
        if not obs.board:
            out = self._short_stack(obs)
            if out is None:
                out = self._chart(obs)
        else:
            out = self._postflop(obs)
        return {a: p for a, p in out.items() if p > 0} or {self._check_fold(obs): 1.0}

    def action_values(self, obs: Observation) -> dict[Action, float] | None:
        """EV of each layer-1 action as a fraction of the prize pool (chip share under chip EV),
        against the solved equilibrium of the quantised spot (the EVs `action_probs` best-responds
        to); `None` outside the short-stack layer."""
        ref = None if obs.board else self._reference(obs)
        if ref is None:
            return None
        hero_i, pusher_i, (_, ev, scale), h = ref
        if pusher_i is None:
            push, fold = ev.push_ev[hero_i]
            return {self._jam(obs): float(push[h]) / scale, self._check_fold(obs): float(fold) / scale}
        call, fold, _ = ev.call_ev[hero_i, pusher_i]
        return {Action("call"): float(call[h]) / scale, Action("fold"): float(fold) / scale}

    # ---- helpers ----
    @staticmethod
    def _check_fold(obs: Observation) -> Action:
        return Action("fold") if obs.legal.call_amount > 0 and obs.legal.can_fold else Action("call")

    @staticmethod
    def _raise(obs: Observation, to: float) -> Action:
        la = obs.legal
        if la.min_raise_to is None:
            return Action("call")
        return Action("raise", int(min(max(round(to), la.min_raise_to), la.max_raise_to)))

    def _jam(self, obs: Observation) -> Action:
        la = obs.legal
        return Action("call") if la.min_raise_to is None else Action("raise", la.max_raise_to)

    def _top(self, obs: Observation) -> float:
        return class_top_pct()[hand_class(card(obs.hole_cards[0]), card(obs.hole_cards[1]))]

    # ---- 1. short-stack zone ----
    def _short_stack(self, obs: Observation) -> dict[Action, float] | None:
        ref = self._reference(obs)
        if ref is None:
            return None
        hero_i, pusher_i, (strat, _, _), h = ref
        if pusher_i is None:
            p = float(strat.push[hero_i, h])
            return {self._jam(obs): p, self._check_fold(obs): 1.0 - p}
        p = float(strat.call[hero_i, pusher_i, h])
        return {Action("call"): p, Action("fold"): 1.0 - p}

    def _reference(self, obs: Observation):
        """(hero index, pusher index or None, solved spot, hand class index) when layer 1 applies."""
        order = preflop_order(obs)
        if obs.seat not in order:
            return None
        hist = obs.action_history
        aggressors = [(s, amt) for s, kind, amt in hist if kind == "cbr"]
        if any(kind == "cc" for _, kind, _ in hist) or len(aggressors) > 1:
            return None
        start, ante, bb_ante = hand_start_stacks(obs, order)
        hero_i = order.index(obs.seat)
        bb = obs.bb
        if not aggressors:
            if hero_i == len(order) - 1:
                return None
            behind = max(start[s] for s in order[hero_i + 1:])
            if min(start[obs.seat], behind) > self.short_bb * bb:
                return None
            pusher_i = None
        else:
            pusher, amt = aggressors[0]
            covers = obs.stacks[pusher] == 0 or amt >= obs.stacks[obs.seat] + obs.bets.get(obs.seat, 0)
            if not covers or min(start[obs.seat], start[pusher]) > self.short_bb * bb:
                return None
            pusher_i = order.index(pusher)
        sol = self._solution(obs, order, start, ante, bb_ante)
        if sol is None:
            return None
        return hero_i, pusher_i, sol, _CLASS_INDEX[hand_class(card(obs.hole_cards[0]), card(obs.hole_cards[1]))]

    def _solution(self, obs: Observation, order: list[int], start: dict[int, int], ante: int, bb_ante: int):
        unit = obs.bb * QUANT_BB
        q = SPOT_BB * QUANT_BB
        stacks = tuple(int(max(1, round(start[s] / unit)) * q) for s in order)
        sb = int(round(SPOT_BB * obs.sb / obs.bb))
        n_ante = int(round(SPOT_BB * ante / obs.bb))
        n_bb_ante = int(round(SPOT_BB * bb_ante / obs.bb))
        payouts = None
        if obs.players_remaining == len(order):
            total = sum(self.payouts)
            payouts = tuple(round(p / total, 9) for p in self.payouts[: len(order)]) if total > 0 else None
        try:
            return _solve_spot(stacks, sb, n_ante, n_bb_ante, payouts)
        except SpotError:
            return None  # a post is all-in or the spot is outside the reference; use the chart

    # ---- 2. preflop chart ----
    def _chart(self, obs: Observation) -> dict[Action, float]:
        ch = load_chart()
        la = obs.legal
        order = preflop_order(obs)
        top = self._top(obs)
        raises = [amt for _, kind, amt in obs.action_history if kind == "cbr"]
        limpers = sum(1 for _, kind, _ in obs.action_history if kind == "cc")
        hero_i = order.index(obs.seat) if obs.seat in order else len(order) - 1
        is_bb = hero_i == len(order) - 1
        bb = obs.bb
        own = obs.stacks[obs.seat] + obs.bets.get(obs.seat, 0)

        def raise_to(to: float) -> Action:
            if to >= ch["jam_if_raise_commits_fraction"] * own:
                return self._jam(obs)
            return self._raise(obs, to)

        if not raises:
            if is_bb and la.call_amount == 0:
                if limpers and top <= ch["bb_vs_limp_raise_top_pct"]:
                    return {raise_to(bb * (ch["open_size_bb"] + ch["open_size_per_limper_bb"] * limpers)): 1.0}
                return {Action("call"): 1.0}
            behind = len(order) - 1 - hero_i
            thr = ch["open_top_pct_by_players_behind"].get(str(behind), 0.10)
            if top <= thr:
                return {raise_to(bb * (ch["open_size_bb"] + ch["open_size_per_limper_bb"] * limpers)): 1.0}
            return {self._check_fold(obs): 1.0}
        last = max(raises)
        if len(raises) == 1:
            v = ch["vs_open"]
            if top <= v["threebet_top_pct"]:
                return {raise_to(last * v["threebet_size_x"]): 1.0}
            if top <= (v["bb_call_top_pct"] if is_bb else v["call_top_pct"]):
                return {Action("call"): 1.0}
            return {self._check_fold(obs): 1.0}
        v = ch["vs_3bet"] if len(raises) == 2 else ch["vs_4bet_plus"]
        jam_pct = v.get("fourbet_top_pct", v.get("jam_top_pct"))
        if top <= jam_pct:
            return {self._jam(obs): 1.0}
        if top <= v["call_top_pct"]:
            return {Action("call"): 1.0}
        return {self._check_fold(obs): 1.0}

    # ---- 3. postflop ----
    def _postflop(self, obs: Observation) -> dict[Action, float]:
        la = obs.legal
        n_opp = min(max(len(obs.in_hand) - 1, 1), POST_MAX_OPP)
        eq = _postflop_equity(tuple(obs.hole_cards), tuple(obs.board), n_opp)
        top_bet = max(obs.bets.values(), default=0)
        if la.call_amount > 0:
            if eq >= POST_RAISE_EQ and la.min_raise_to is not None:
                return {self._raise(obs, top_bet + obs.pot + la.call_amount): 1.0}
            odds = la.call_amount / (obs.pot + la.call_amount)
            return {Action("call") if eq >= odds + POST_CALL_MARGIN else Action("fold"): 1.0}
        if eq >= POST_VALUE_BET_EQ and la.min_raise_to is not None:
            return {self._raise(obs, top_bet + POST_BET_FRACTION * obs.pot): 1.0}
        return {Action("call"): 1.0}


def factory(payouts: tuple[float, ...] = (1.0,), short_bb: float = SHORT_BB):
    """An `AgentFactory` (rng -> Agent) for `referee.evaluate.evaluate`."""
    return lambda rng: ReferenceBot(rng, payouts, short_bb)
