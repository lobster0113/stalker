"""A trained E3 policy (c1 key) seated in the tournament director (#900, ADR 0027 decision 6 F3).

The agent mirrors each hand of its table in the E3 engine (`stalker.e3.game`) and acts from the policy row of its
real c1 key, `tp_key.key(public_key(variant="c1"), step)`, exactly as training reads it:

- Seats map to E3 preflop order (0 = first to act after the big blind ... n-2 = SB, n-1 = BB); chips are scaled to
  E3 units (BB = 100 chips) at the level's big blind, rounded to whole chips.
- The environment slot `t<stage><ante>` comes from `e3_stage` (ADR 0027 decision 2, K = paid places, r = survivors):
  `e` r >= K + 2, `b` r = K + 1, `m` r <= K, `f` in the money at a multi-table field's final table. This is not
  `tournament_stage`, whose "bubble_near" spans more than r = K + 1. The ante bit is the deal's BB ante (#878).
- Every public action of the hand (own and others') is replayed on the mirror state; bet and raise sizes off the
  E3 menu are read with `translate.sample` (the referee and web reading) from the agent's own seeded Generator.
  Every seat's public range is Bayes-updated with the policy row of its key (uniform where the table has none),
  as `stalker.tools.web_hit_rate` and training do. The chosen E3 label goes back as a real chip amount (scaled,
  clamped to the legal range).

Backoff: when the table has no row for the key (`no_key`) or the row length differs from the legal action count
(`arity_mismatch`, #961), or the hand cannot be put on the E3 menu (classic antes, blinds
not SB = BB / 2, a stack under 2 BB, blinds not just after the button, more than 9 seats, a replay out of step with
the real hand), the decision goes to the fallback rule bot (`persona:tag` by default), which sees every event so
its own state stays right. `decisions`, `policy_hits`, `backoffs` and `backoff_reasons` count what happened; `by_street`
({street: {decisions, policy_hits}}, 0 preflop .. 3 river) splits decisions and hits by street.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from stalker.agents.base import Action, Agent, Event, Observation
from stalker.agents.persona import PersonaAgent, persona_params
from stalker.core.cards import card
from stalker.e2.eq_view import N
from stalker.e3 import game as G
from stalker.e3 import tp_key as K
from stalker.e3 import translate as T

FALLBACK = "tag"   # the rule bot a miss goes to (ADR 0027 decision 4 field)
_STREET = {0: 0, 3: 1, 4: 2, 5: 3}   # board cards -> street (0 preflop .. 3 river), for `by_street`
MAX_SEATS = 9      # E3 deals 2..9 players


def e3_stage(remaining: int, paid_places: int, players: int | None = None, table_size: int | None = None) -> str:
    """c1 `t<stage>` of a tournament with `remaining` survivors (ADR 0027 decision 2). `players`/`table_size`
    (the field and the table size) only tell a multi-table field's final table (`f`); without them it is a SNG."""
    if remaining < 1 or paid_places < 1:
        raise ValueError(f"bad arguments: remaining={remaining} paid_places={paid_places}")
    if remaining >= paid_places + 2:
        return "e"
    if remaining == paid_places + 1:
        return "b"
    mtt = players is not None and table_size is not None and players > table_size
    return "f" if mtt and remaining <= table_size else "m"


@dataclass(frozen=True)
class PolicyTable:
    """Key -> probability row (the order of `game.legal`), and the rules the table was trained on."""

    policy: dict
    k: int
    depth: str
    menu: str
    raise_cap: int | None
    source: str = ""

    @classmethod
    def from_model(cls, m, strategy: str = "current", source: str = "") -> PolicyTable:
        if m.key_variant != "c1":
            raise ValueError(f"key variant {m.key_variant!r}: the tournament agent reads c1 tables only")
        policy = m.policy() if strategy == "average" else m.current_policy()
        return cls(policy, m.k, m.depth, m.menu, m.raise_cap, source)


def load_table(path: Path, strategy: str = "current") -> PolicyTable:
    """A pod training result (`stalker.tools.pod_train`), a checkpoint (`.ckpt.json[.gz]`) or a web policy file
    (`web/app/policy/<tier>-<n>.json`). A folder must hold exactly one of them."""
    path = Path(path)
    if path.is_dir():
        found = sorted(p for p in path.iterdir() if p.is_file() and p.name.endswith((".json", ".json.gz")))
        if len(found) != 1:
            raise ValueError(f"{path}: need exactly one result/checkpoint/policy .json[.gz] in the folder, "
                             f"found {len(found)}; pass the file itself")
        path = found[0]
    if not path.is_file():
        raise FileNotFoundError(f"{path}: no such policy file or folder")
    from stalker.jsonio import read_json

    doc = read_json(path)
    if "policy" in doc and "q" in doc:   # web policy file
        if doc.get("key_variant", "c1") != "c1":
            raise ValueError(f"{path}: key variant {doc.get('key_variant')!r}; the tournament agent reads c1 tables only")
        q = doc["q"]
        return PolicyTable({k: [x / q for x in row] for k, row in doc["policy"].items()}, doc["k"], doc["depth"],
                           doc.get("menu") or "v1", doc.get("raise_cap", G.RAISE_CAP), str(path))
    from stalker.e3.mccfr import E3MCCFR

    if "checkpoint" in doc:
        from stalker.tools.export_web_policy import load_pod_result

        st, _ = load_pod_result(path)
    else:
        st = doc
    return PolicyTable.from_model(E3MCCFR.from_state(st), strategy, str(path))


class BackoffError(Exception):
    """This hand cannot be mirrored on the E3 menu; the message is the backoff reason."""


class E3PolicyAgent(Agent):
    def __init__(self, table: PolicyTable, rng: np.random.Generator, fallback: Agent | None = None,
                 players: int | None = None, table_size: int | None = None) -> None:
        self.table, self.rng = table, rng
        self.fallback = fallback if fallback is not None else PersonaAgent(
            persona_params(FALLBACK), np.random.default_rng(int(rng.integers(2**63))))
        self.players, self.table_size = players, table_size
        self.decisions = self.policy_hits = self.backoffs = 0
        self.backoff_reasons: dict[str, int] = {}
        self.by_street: dict[str, dict[str, int]] = {}
        self._new_hand: dict | None = None
        self._mirror: dict | None = None

    # ---- events ----
    def on_game_start(self, game_id: str) -> None:
        self.fallback.on_game_start(game_id)

    def on_game_end(self, game_id: str) -> None:
        self.fallback.on_game_end(game_id)

    def observe(self, event: Event) -> None:
        self.fallback.observe(event)
        if event.type == "NEW_HAND":
            self._new_hand = {"game": event.game_id, "hand": event.hand_id, **event.data}
            self._mirror = None

    # ---- acting ----
    def act(self, obs: Observation) -> Action:
        self.decisions += 1
        cell = self.by_street.setdefault(str(_STREET.get(len(obs.board), 0)), {"decisions": 0, "policy_hits": 0})
        cell["decisions"] += 1
        try:
            action = self._policy_act(obs)
        except BackoffError as e:
            reason = str(e)
        else:
            self.policy_hits += 1
            cell["policy_hits"] += 1
            return action
        self.backoffs += 1
        self.backoff_reasons[reason] = self.backoff_reasons.get(reason, 0) + 1
        return self.fallback.act(obs)

    def counts(self) -> dict:
        return {"decisions": self.decisions, "policy_hits": self.policy_hits, "backoffs": self.backoffs,
                "backoff_reasons": dict(sorted(self.backoff_reasons.items())),
                "by_street": {k: dict(v) for k, v in sorted(self.by_street.items())}}

    def decision_key(self, obs: Observation) -> str:
        """The actor's real c1 key for this decision; raises `BackoffError` when the hand is off the E3 menu."""
        mir = self._sync(obs)
        s = mir["s"]
        p = mir["seat_map"][obs.seat]
        if s.done or s.to_act != p:
            raise BackoffError("out_of_sync")
        with K.using_env(mir["stage"], s.ante > 0):
            steps = K.equity_steps(s, p, mir["ranges"], self.table.k, "c1", self.table.depth)
            public = K.public_key(s, p, self.table.depth, "c1")
        return K.key(public, K.my_step(steps, s, p))

    def _policy_act(self, obs: Observation) -> Action:
        key = self.decision_key(obs)
        mir = self._mirror
        s = mir["s"]
        acts = G.legal(s)
        row = self.table.policy.get(key)
        if row is None:
            raise BackoffError("no_key")
        if len(row) != len(acts):
            raise BackoffError("arity_mismatch")
        pr = np.asarray(row, dtype=float)
        label = acts[int(self.rng.choice(len(acts), p=pr / pr.sum()))]
        mir["mine"] = (len(obs.action_history), label)
        return self._real_action(s, label, obs, mir["bb"])

    @staticmethod
    def _real_action(s: G.State, label: str, obs: Observation, bb: int) -> Action:
        la = obs.legal
        if label == "f":
            return Action("fold") if la.can_fold and la.call_amount > 0 else Action("call")
        if label in ("c", "k") or la.min_raise_to is None:
            return Action("call")
        if label == "a":
            return Action("raise", la.max_raise_to)
        to = round(G._amount_to(s, label) * bb / G.BB)
        return Action("raise", min(max(to, la.min_raise_to), la.max_raise_to))

    # ---- the E3 mirror of this hand ----
    def _sync(self, obs: Observation) -> dict:
        key = (obs.game_id, obs.hand_id)
        if self._mirror is None or self._mirror["key"] != key:
            self._mirror = {"key": key, "broken": None}
            try:
                self._mirror.update(self._build(obs))
            except BackoffError as e:
                self._mirror["broken"] = str(e)
        mir = self._mirror
        if mir["broken"]:
            raise BackoffError(mir["broken"])
        try:
            for i in range(mir["done"], len(obs.action_history)):
                self._replay(mir, i, obs.action_history[i], obs.board)
                mir["done"] = i + 1
        except BackoffError as e:
            mir["broken"] = str(e)
            raise
        return mir

    def _build(self, obs: Observation) -> dict:
        nh = self._new_hand
        if nh is None or (nh["game"], nh["hand"]) != (obs.game_id, obs.hand_id):
            raise BackoffError("no_new_hand")
        if obs.ante and obs.ante_mode != "bb_ante":
            raise BackoffError("ante_mode")
        sb, bb = nh["sb"], nh["bb"]
        if 2 * sb != bb:
            raise BackoffError("blinds")
        occupied = sorted(nh["stacks"])
        n = len(occupied)
        if n > MAX_SEATS:
            raise BackoffError("seats")
        sb_seat, bb_seat = nh["blind_seats"]
        j = occupied.index(bb_seat)
        order = occupied[j + 1:] + occupied[:j + 1]   # clockwise from the seat after the BB, the BB last
        if n == 2:
            ok = order == [nh["button"], bb_seat] and sb_seat == nh["button"]
        else:
            ok = order[-2] == sb_seat and order[-3] == nh["button"]
        if not ok:
            raise BackoffError("blind_seats")
        stacks = tuple(round(nh["stacks"][seat] * G.BB / bb) for seat in order)
        ante = round(nh["ante"] * G.BB / bb) if obs.ante else 0
        if min(stacks[:-1]) < 2 * G.BB or stacks[-1] < (1 if ante else 2 * G.BB):
            raise BackoffError("short_stack")
        p = order.index(obs.seat)
        mine = tuple(card(c) for c in obs.hole_cards)
        rest = [c for c in range(52) if c not in mine]
        holes = [mine if i == p else (rest.pop(), rest.pop()) for i in range(n)]
        s = G.deal(np.random.default_rng(0), n, self.table.menu, self.table.raise_cap, stacks, ante)
        s = s._replace(hole=tuple(holes), deck=tuple(rest))
        stage = e3_stage(obs.players_remaining, obs.paid_places, self.players, self.table_size)
        return {"s": s, "ranges": K.initial_ranges(n), "seat_map": {seat: i for i, seat in enumerate(order)},
                "bb": bb, "stage": stage, "done": 0, "mine": None}

    def _replay(self, mir: dict, i: int, entry: tuple[int, str, int], board: tuple[str, ...]) -> None:
        s = mir["s"]
        seat, kind, amount = entry
        p = mir["seat_map"].get(seat)
        if s.done or p is None or s.to_act != p:
            raise BackoffError("out_of_sync")
        acts = G.legal(s)
        to = None
        if mir["mine"] is not None and mir["mine"][0] == i:
            label = mir["mine"][1]
        elif kind == "f":
            label = "f"
        elif kind == "cc":
            label = "k" if "k" in acts else "c"
        else:
            to = round(amount * G.BB / mir["bb"])
            room = s.stack[p] + s.bet[p]
            if to >= room and "a" in acts:
                label, to = "a", None
            else:
                try:
                    to = min(max(to, min(max(s.bet) + s.last_raise, room)), room)
                    label = T.sample(s, to, self.rng)
                except ValueError:
                    raise BackoffError("off_menu") from None
                if label in acts and G._amount_to(s, label) == to:
                    to = None
        if label not in acts:
            raise BackoffError("off_menu")
        with K.using_env(mir["stage"], s.ante > 0):
            steps = K.equity_steps(s, p, mir["ranges"], self.table.k, "c1", self.table.depth)
            public = K.public_key(s, p, self.table.depth, "c1")
        col = np.zeros(N)
        a = acts.index(label)
        uniform = 1.0 / len(acts)
        for v in np.unique(steps[steps >= 0]):
            row = self.table.policy.get(K.key(public, int(v)))
            col[steps == v] = row[a] if row is not None and len(row) == len(acts) else uniform
        mir["ranges"] = K.update_range(mir["ranges"], p, col)
        try:
            ns = G.apply(s, label) if to is None else G.apply_to(s, to, label)
        except ValueError:
            raise BackoffError("off_menu") from None
        if ns.board:
            real = tuple(card(c) for c in board)
            if len(real) < len(ns.board):
                if not ns.done:
                    raise BackoffError("out_of_sync")
            else:
                ns = ns._replace(board=real[:len(ns.board)])
        mir["s"] = ns
