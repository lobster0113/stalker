"""Gate R edge cases (SIM-d): rule situations random play rarely reaches, built on purpose.

`python -m referee.gate_r.edge [--cases N]` — exit 1 on any failed check or on a kind with fewer than N cases.

Eight kinds, each a seeded generator plus a classifier; a generated case counts only if the classifier sees the
situation actually happen, so "50 cases" means 50 hands/games that exercised the rule, not 50 attempts.
- Hand kinds (cards fixed through a stacked deck): `short_allin_chain`, `side_pots_split_odd`, `ante_only_allin`,
  `short_blind`, `board_play_split`, `wheel_kicker`. Each hand runs on PokerKit `Hand` and `FastHand` in lockstep
  (item `engines`: same actor, legal actions, cards and `HandResult` at every step) and its public event stream is
  replayed by the independent model in `checks.py` (antes/blinds, order, sizing, flow, settlement, chips).
- Game kinds: `heads_up_transition` (a table drops to two players and keeps playing) and `multi_bust` (two or more
  players bust in one round); whole games go through `run_game` and `check_game`.
Engines are imported only to drive them; every expected value comes from the independent model.
"""
from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from types import SimpleNamespace

import numpy as np

from referee.gate_r.checks import ITEMS, Tally, _check_settlement, _Desync, _HandModel, check_game
from referee.gate_r.evaluator import strength
from referee.gate_r.settlement import build_pots
from referee.gate_r.suite import BOTS
from stalker.core.cards import N_CARDS, card_str
from stalker.tournament.config import BlindLevel, TournamentConfig
from stalker.tournament.director import run_game
from stalker.tournament.fast_hand import FastHand
from stalker.tournament.hand import Hand

EDGE_ITEMS = (*ITEMS, "engines")
MIN_CASES = 50
MAX_ATTEMPTS = 40  # per wanted case; a generator that needs more is too weak to be a test
SEED = 20261027


def tally_for_edge() -> Tally:
    return Tally(counts={k: [0, 0] for k in EDGE_ITEMS})


# ---- cards ----
class StackedDeck:
    """Stands in for the rng both engines draw their deck from: `permutation` returns a fixed deck."""

    def __init__(self, deck: list[int]) -> None:
        self.deck = deck

    def permutation(self, n: int) -> np.ndarray:
        assert n == N_CARDS
        return np.array(self.deck)


def stack_deck(rng: np.random.Generator, n: int, holes: dict[int, tuple[int, int]] | None = None,
               board: list[int] | None = None) -> list[int]:
    """Deck dealing `holes[i]` to player index i (0 = left of the button) and `board`; the rest is random.

    Draw order shared by both engines: draw k is deck[-1 - k]; hole cards round-robin (2n), then burn + 3 flop,
    burn + turn, burn + river.
    """
    holes, board = holes or {}, board or []
    fixed = [c for h in holes.values() for c in h] + list(board)
    if len(set(fixed)) != len(fixed):
        raise ValueError("a card is fixed twice")
    rest = [int(c) for c in rng.permutation(N_CARDS) if int(c) not in fixed]
    take = rest.pop
    hole = [holes.get(i) or (take(), take()) for i in range(n)]
    b = list(board) + [take() for _ in range(5 - len(board))]
    draws = [hole[i][0] for i in range(n)] + [hole[i][1] for i in range(n)]
    draws += [take(), b[0], b[1], b[2], take(), b[3], take(), b[4]]
    return rest + draws[::-1]


def _card(rank: int, suit: int) -> int:
    return rank << 2 | suit


# ---- one hand on three implementations ----
@dataclass(frozen=True)
class HandCase:
    stacks: tuple[int, ...]
    button: int
    sb: int
    bb: int
    ante: int
    ante_mode: str
    deck: tuple[int, ...]
    policy_seed: int
    fold_p: float = 0.15
    raise_p: float = 0.35
    allin_p: float = 0.5  # share of raises that go all-in
    script: tuple[tuple[str, int], ...] = ()  # first actions: ("raise", to) / ("allin", 0) / ("call", 0) / ("fold", 0)


@dataclass
class HandRecord:
    """What happened, for the classifiers. Built from the independent model where it can be."""

    model: _HandModel | None
    shorts: list[tuple[int, bool]] = field(default_factory=list)  # (street, short all-in raise?) per raise
    board: list[str] = field(default_factory=list)
    live: list[int] = field(default_factory=list)
    keys: dict[int, tuple] = field(default_factory=dict)
    awards: tuple = ()
    final: dict[int, int] = field(default_factory=dict)  # engine final stacks by seat
    actions: list = field(default_factory=list)  # (seat, kind, amount) as PokerKit recorded them


def _policy(case: HandCase, rng: np.random.Generator, la, step: int) -> tuple[str, int]:
    if step < len(case.script):
        kind, amount = case.script[step]
        if kind == "allin" and la.max_raise_to is not None:
            return "raise", la.max_raise_to
        if kind == "raise" and la.min_raise_to is not None and la.min_raise_to <= amount <= la.max_raise_to:
            return "raise", amount
        if kind == "call":
            return "call", la.call_amount
        if kind == "fold" and la.can_fold:
            return "fold", 0
    r = rng.random()
    if la.can_fold and la.call_amount > 0 and r < case.fold_p:
        return "fold", 0
    if la.min_raise_to is not None and r > 1 - case.raise_p:
        amount = la.max_raise_to if rng.random() < case.allin_p else la.min_raise_to
        return "raise", amount
    return "call", la.call_amount


def dealt_holes(case: HandCase) -> dict[int, tuple[str, str]]:
    """Hole cards per seat as the stacked deck deals them (see `stack_deck`), without asking an engine."""
    order = [(case.button + k) % len(case.stacks) for k in range(1, len(case.stacks) + 1)]
    seats = [s for s in order if case.stacks[s] > 0]
    n, top = len(seats), len(case.deck) - 1
    return {s: (card_str(case.deck[top - i]), card_str(case.deck[top - n - i])) for i, s in enumerate(seats)}


def _apply(h, kind: str, amount: int) -> None:
    if kind == "fold":
        h.fold()
    elif kind == "call":
        h.check_or_call()
    else:
        h.raise_to(amount)


def run_hand(case: HandCase, tally: Tally, where: str) -> HandRecord:
    kw = dict(stacks=case.stacks, button=case.button, small_blind=case.sb, big_blind=case.bb,
              ante=case.ante, ante_mode=case.ante_mode)
    ref = Hand(rng=StackedDeck(list(case.deck)), **kw)
    fast = FastHand(rng=StackedDeck(list(case.deck)), **kw)
    occupied = [s for s, c in enumerate(case.stacks) if c > 0]
    holes = dealt_holes(case)
    for s in occupied:  # PokerKit has already mucked losers when the hand ends during the postings
        for got in (ref.hole_cards(s), fast.hole_cards(s)):
            tally.check("engines", not got or tuple(got) == holes[s], f"{where}: seat {s} holds {got}, dealt {holes[s]}")
    d = {"button": case.button, "seat_players": {s: s for s in occupied},
         "stacks": {s: case.stacks[s] for s in occupied}, "sb": case.sb, "bb": case.bb, "ante": case.ante}
    cfg = SimpleNamespace(table_size=len(case.stacks), ante_mode=case.ante_mode)
    model: _HandModel | None = _HandModel(cfg, d, tally, where)
    rec = HandRecord(model)
    rng = np.random.default_rng(case.policy_seed)
    folded: set[int] = set()
    first = True
    while True:
        same = ref.is_over == fast.is_over and ref.actor == fast.actor
        if not tally.check("engines", same, f"{where}: after {ref.actions()} actor {ref.actor} vs {fast.actor}"):
            return rec
        if ref.is_over:
            break
        la = ref.legal_actions()
        if not tally.check("engines", la == fast.legal_actions(),
                           f"{where}: after {ref.actions()} {la} vs {fast.legal_actions()}"):
            return rec
        kind, amount = _policy(case, rng, la, len(ref.actions()))
        street = len(ref.board())
        for h in (ref, fast):
            _apply(h, kind, amount)
        if kind == "fold":
            folded.add(la.seat)
        if model is not None:
            if first and kind == "call" and model.actor == la.seat:
                to_call = min(model.max_bet - model.bet[la.seat], model.stack[la.seat])
                tally.check("antes_blinds", amount == to_call, f"{where}: first call {amount}, postings imply {to_call}")
            first = False
            if kind == "raise":
                inc = amount - model.max_bet
                rec.shorts.append((model.street, inc < max(model.bb, model.full_inc)))
            try:
                model.apply({"seat": la.seat, "action": kind, "amount": amount, "street": street,
                             "facing_bet": la.call_amount > 0})
            except _Desync:
                model = rec.model = None
    res, fres = ref.result(), fast.result()
    tally.check("engines", ref.board() == fast.board() and res == fres, f"{where}: results {res} vs {fres}")
    rec.board = ref.board()
    rec.actions = ref.actions()
    rec.live = [s for s in occupied if s not in folded]
    rec.awards = res.awards
    showdown = None
    if len(rec.live) > 1:
        showdown = {"board": tuple(rec.board), "hands": {s: holes[s] for s in rec.live}}
        rec.keys = {s: strength(holes[s], rec.board) for s in rec.live}
    final = rec.final = {s: res.final_stacks[s] for s in occupied}
    tally.check("chip_conservation", sum(final.values()) == sum(d["stacks"].values()),
                f"{where}: {sum(d['stacks'].values())} chips became {sum(final.values())}")
    if model is not None:
        if not model.over:
            tally.check("action_order", False, f"{where}: hand ended but seat {model.actor} was still to act")
        else:
            _check_settlement(model, showdown, final, tally, where)
    return rec


# ---- hand generators: (rng) -> HandCase, and classifiers: (HandCase, HandRecord) -> bool ----
def _table(rng: np.random.Generator, lo: int, hi: int, empty_p: float = 0.15) -> tuple[int, list[bool]]:
    """(button, occupied mask) of a table with `lo`..`hi` seats, at least `lo` of them occupied."""
    while True:
        size = int(rng.integers(lo, hi + 1))
        occ = [rng.random() >= empty_p for _ in range(size)]
        if sum(occ) >= lo:
            button = int(rng.choice([s for s in range(size) if occ[s]]))
            return button, occ


def _order(button: int, occ: list[bool]) -> list[int]:
    n = len(occ)
    return [(button + k) % n for k in range(1, n + 1) if occ[(button + k) % n]]


def _blind_seats(button: int, occ: list[bool]) -> tuple[int, int]:
    order = _order(button, occ)
    return (button, order[0]) if len(order) == 2 else (order[0], order[1])


def _case(rng, stacks, button, sb, bb, ante=0, mode="none", deck=None, **policy) -> HandCase:
    n = sum(s > 0 for s in stacks)
    return HandCase(tuple(int(s) for s in stacks), button, sb, bb, ante, mode,
                    tuple(deck or stack_deck(rng, n)), int(rng.integers(2**32)), **policy)


def gen_short_allin_chain(rng):
    """A deep seat opens to R; the next 2-4 seats are short and shove in turn, each all-in raise smaller than the
    full raise F (stacks laddered by less than F), so betting is not reopened. Half the cases play it on the flop
    after everyone limps."""
    button, occ = _table(rng, 4, 9, empty_p=0.1)
    order = _order(button, occ)
    n = len(order)
    bb = int(rng.integers(2, 21))
    sb = max(1, bb // 2)
    stacks = [int(rng.integers(40 * bb, 120 * bb)) if o else 0 for o in occ]
    m = int(rng.integers(2, min(4, n - 2) + 1))
    if rng.random() < 0.5:  # preflop: action opens left of the BB
        acting = order[2:] + order[:2]
        r = bb * int(rng.integers(2, 5))
        full, put, script = r - bb, 0, [("raise", r)]
    else:  # flop: everyone limps, then the first seat left of the button bets r
        acting = order
        r = bb * int(rng.integers(1, 4))
        full, put = r, bb
        script = [("call", 0)] * n + [("raise", r)]
    level = r
    for k in range(1, m + 1):
        level += int(rng.integers(1, full)) if full > 1 else 1
        stacks[acting[k]] = put + level
    script += [("allin", 0)] * m
    return _case(rng, stacks, button, sb, bb, fold_p=0.2, raise_p=0.3, allin_p=0.5, script=tuple(script))


def is_short_allin_chain(case, rec) -> bool:
    run = best = 0
    street = None
    for st, short in rec.shorts:
        run = run + 1 if short and st == street else (1 if short else 0)
        street = st
        best = max(best, run)
    return best >= 2


def gen_side_pots_split_odd(rng):
    button, occ = _table(rng, 5, 9, empty_p=0.05)
    n = sum(occ)
    bb = int(rng.integers(2, 11))
    mode = str(rng.choice(["none", "classic", "bb_ante"]))
    ante = 0 if mode == "none" else int(rng.integers(1, 4))
    stacks = [int(rng.integers(3 * bb, 40 * bb)) | 1 if o else 0 for o in occ]  # odd stacks make odd pots
    # two players share the same ranks in different suits so a pot they win is split
    i, j = (int(x) for x in rng.choice(n, 2, replace=False))
    r1, r2 = (int(x) for x in rng.choice(np.arange(8, 13), 2, replace=False))
    s = rng.permutation(4)
    holes = {i: (_card(r1, int(s[0])), _card(r2, int(s[1]))), j: (_card(r1, int(s[2])), _card(r2, int(s[3])))}
    deck = stack_deck(rng, n, holes)
    return _case(rng, stacks, button, max(1, bb // 2), bb, ante, mode, deck, fold_p=0.0, raise_p=0.8, allin_p=1.0)


def is_side_pots_split_odd(case, rec) -> bool:
    m = rec.model
    if m is None or len(rec.live) < 2:
        return False
    pots = build_pots(m.paid, m.antes, set(rec.live))
    odd_split = any(len(a.awards) >= 2 and a.amount % len(a.awards) for a in rec.awards)
    return len(pots) >= 4 and odd_split


def gen_ante_only_allin(rng):
    button, occ = _table(rng, 2, 9)
    mode = str(rng.choice(["classic", "bb_ante"]))
    ante = int(rng.integers(2, 11))
    bb = ante * int(rng.integers(1, 4))
    stacks = [int(rng.integers(5 * bb, 40 * bb)) if o else 0 for o in occ]
    order = _order(button, occ)
    targets = [_blind_seats(button, occ)[1]] if mode == "bb_ante" else list(rng.choice(order, int(rng.integers(1, 3))))
    for s in targets:
        stacks[int(s)] = int(rng.integers(1, ante + 1))
    return _case(rng, stacks, button, max(1, bb // 2), bb, ante, mode)


def is_ante_only_allin(case, rec) -> bool:
    m = rec.model
    return m is not None and any(0 < m.antes[s] == case.stacks[s] for s in m.order)


def gen_short_blind(rng):
    button, occ = _table(rng, 2, 9)
    bb = int(rng.integers(4, 41))
    sb = int(rng.integers(2, bb // 2 + 1))
    mode = str(rng.choice(["none", "classic", "bb_ante"]))
    ante = 0 if mode == "none" else int(rng.integers(1, max(2, bb // 4)))
    stacks = [int(rng.integers(5 * bb, 40 * bb)) if o else 0 for o in occ]
    sb_seat, bb_seat = _blind_seats(button, occ)
    seat, blind = (sb_seat, sb) if rng.random() < 0.4 else (bb_seat, bb)
    stacks[seat] = ante + int(rng.integers(1, blind))  # covers the ante, not the blind
    return _case(rng, stacks, button, sb, bb, ante, mode)


def is_short_blind(case, rec) -> bool:
    m = rec.model
    if m is None:
        return False
    for seat, blind in ((m.sb_seat, case.sb), (m.bb_seat, case.bb)):
        posted = case.stacks[seat] - m.antes[seat]
        if 0 < posted < blind:
            return True
    return False


_BOARDS = (  # templates where the board is often everyone's best hand: (ranks, suits); suits avoid flushes
    ((8, 9, 10, 11, 12), (0, 1, 2, 3, 0)),      # T-A broadway
    ((12, 12, 12, 12, 11), (0, 1, 2, 3, 0)),    # four aces, king kicker
    ((11, 11, 11, 10, 10), (0, 1, 2, 0, 1)),    # kings full of queens
)


def gen_board_play_split(rng):
    button, occ = _table(rng, 2, 6)
    n = sum(occ)
    if rng.random() < 0.5:
        ranks, suits = _BOARDS[int(rng.integers(len(_BOARDS)))]
    else:  # a random straight, unsuited
        lo = int(rng.integers(0, 8))
        ranks, suits = tuple(range(lo, lo + 5)), tuple(int(x) for x in rng.permutation([0, 1, 2, 3, 0]))
    board = [_card(r, s) for r, s in zip(ranks, suits)]
    bb = int(rng.integers(2, 11))
    stacks = [int(rng.integers(3 * bb, 30 * bb)) | 1 if o else 0 for o in occ]
    deck = stack_deck(rng, n, board=list(rng.permutation(board).tolist()))
    return _case(rng, stacks, button, max(1, bb // 2), bb, deck=deck, fold_p=0.1, raise_p=0.3)


def is_board_play_split(case, rec) -> bool:
    if len(rec.live) < 2:
        return False
    plays = strength([], rec.board)
    return all(k == plays for k in rec.keys.values()) and any(len(a.awards) >= 2 for a in rec.awards)


def _kicker_decided(keys: list[tuple]) -> bool:
    made = {1: 2, 2: 3, 3: 2, 7: 2}  # category -> key prefix length that is the made hand, rest are kickers
    keys = sorted(keys, reverse=True)
    if len(keys) < 2:
        return False
    a, b = keys[0], keys[1]
    k = made.get(a[0])
    return k is not None and a[:k] == b[:k] and a != b


def gen_wheel_kicker(rng):
    button, occ = _table(rng, 2, 6)
    n = sum(occ)
    bb = int(rng.integers(2, 11))
    stacks = [int(rng.integers(5 * bb, 30 * bb)) if o else 0 for o in occ]
    i, j = (int(x) for x in rng.choice(n, 2, replace=False))
    suits = rng.permutation(4)
    if rng.random() < 0.5:  # wheel: A-2-3 on board, one player holds 4-5, another an ace or a six
        board = [_card(12, int(suits[0])), _card(0, int(suits[1])), _card(1, int(suits[2]))]
        holes = {i: (_card(2, int(suits[0])), _card(3, int(suits[1])))}
        other = 4 if rng.random() < 0.5 else 12
        holes[j] = (_card(other, int(suits[3])), _card(int(rng.integers(5, 12)), int(suits[2])))
    else:  # kicker: both hold the same top card, different side cards, and the board pairs it sometimes
        top = int(rng.integers(8, 13))
        k1, k2 = (int(x) for x in rng.choice([r for r in range(13) if r != top], 2, replace=False))
        holes = {i: (_card(top, int(suits[0])), _card(k1, int(suits[1]))),
                 j: (_card(top, int(suits[2])), _card(k2, int(suits[3])))}
        board = [_card(top, int(suits[1]))] if rng.random() < 0.6 else []
    deck = stack_deck(rng, n, holes, board)
    return _case(rng, stacks, button, max(1, bb // 2), bb, deck=deck, fold_p=0.05, raise_p=0.25)


def is_wheel_kicker(case, rec) -> bool:
    wheel = any(k[0] in (4, 8) and k[1] == 3 for k in rec.keys.values())
    return wheel or _kicker_decided(list(rec.keys.values()))


HAND_KINDS: dict[str, tuple[Callable, Callable]] = {
    "short_allin_chain": (gen_short_allin_chain, is_short_allin_chain),
    "side_pots_split_odd": (gen_side_pots_split_odd, is_side_pots_split_odd),
    "ante_only_allin": (gen_ante_only_allin, is_ante_only_allin),
    "short_blind": (gen_short_blind, is_short_blind),
    "board_play_split": (gen_board_play_split, is_board_play_split),
    "wheel_kicker": (gen_wheel_kicker, is_wheel_kicker),
}


# ---- game kinds ----
def _quick_config(rng: np.random.Generator, players: int, table_size: int, deep: int) -> TournamentConfig:
    """Short structure: blinds start at stack/deep and double every 2-4 hands, so players bust quickly."""
    stack = int(rng.integers(20, 200)) * 10
    bb = max(2, stack // deep)
    mode = str(rng.choice(["none", "classic", "bb_ante"]))
    levels = []
    for k in range(12):
        b = bb * 2**k
        levels.append(BlindLevel(b // 2, b, 0 if mode == "none" else max(1, b // 8), int(rng.integers(2, 5))))
    paid = min(players, 3)
    pays = [0.5, 0.3, 0.2][:paid] if paid == 3 else [0.65, 0.35] if paid == 2 else [1.0]
    return TournamentConfig(name="edge", players=players, table_size=table_size, starting_stack=stack,
                            levels=tuple(levels), payouts=tuple(pays), ante_mode=mode)


def _run_game_case(rng: np.random.Generator, cfg: TournamentConfig):
    bot = BOTS[str(rng.choice(sorted(BOTS)))]
    seed = int(rng.integers(2**32))
    events: list = []
    agents = [bot(np.random.default_rng([seed, i])) for i in range(cfg.players)]
    res = run_game(cfg, agents, np.random.default_rng(seed), observer=events.append)
    return cfg, events, res


def gen_heads_up_transition(rng):
    players = int(rng.integers(3, 5))
    return _run_game_case(rng, _quick_config(rng, players, int(rng.integers(players, 10)), deep=int(rng.integers(5, 30))))


def is_heads_up_transition(game) -> bool:
    """A table played a hand with 3+ players and then, with the same table, a heads-up hand."""
    _, events, _ = game
    seen: dict[int, int] = {}
    for e in events:
        if e.type == "NEW_HAND":
            n = len(e.data["seat_players"])
            if n == 2 and seen.get(e.table_id, 0) >= 3:
                return True
            seen[e.table_id] = n
    return False


def gen_multi_bust(rng):
    players = int(rng.integers(4, 13))
    # table_size >= 3: TournamentConfig.validate rejects table_size=2 with players > 2 (#152), so 2-seat tables never occur here
    table_size = int(rng.integers(max(3, (players + 1) // 2), 10))
    return _run_game_case(rng, _quick_config(rng, players, min(table_size, players), deep=int(rng.integers(3, 12))))


def is_multi_bust(game) -> bool:
    _, events, _ = game
    busts: dict[int, int] = {}
    hand_no = 0
    for e in events:
        if e.type == "NEW_HAND":
            hand_no = e.data["hand_no"]
        elif e.type == "HAND_END":
            busts[hand_no] = busts.get(hand_no, 0) + sum(v == 0 for v in e.data["final_stacks"].values())
    return any(v >= 2 for v in busts.values())


GAME_KINDS: dict[str, tuple[Callable, Callable]] = {
    "heads_up_transition": (gen_heads_up_transition, is_heads_up_transition),
    "multi_bust": (gen_multi_bust, is_multi_bust),
}
KINDS = (*HAND_KINDS, *GAME_KINDS)


def run_kind(kind: str, cases: int = MIN_CASES, seed: int = SEED, tally: Tally | None = None) -> tuple[int, Tally]:
    """Generate until `cases` cases of `kind` pass its classifier (or attempts run out); check every attempt."""
    tally = tally or tally_for_edge()
    rng = np.random.default_rng([seed, KINDS.index(kind)])
    accepted = 0
    for attempt in range(cases * MAX_ATTEMPTS):
        if accepted >= cases:
            break
        where = f"{kind} #{attempt}"
        if kind in HAND_KINDS:
            gen, classify = HAND_KINDS[kind]
            case = gen(rng)
            rec = run_hand(case, tally, where)
            accepted += classify(case, rec)
        else:
            gen, classify = GAME_KINDS[kind]
            game = gen(rng)
            check_game(*game, tally, where)
            accepted += classify(game)
    return accepted, tally


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m referee.gate_r.edge")
    ap.add_argument("--cases", type=int, default=MIN_CASES, help="accepted cases required per kind")
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args(argv)
    tally = tally_for_edge()
    short = []
    for kind in KINDS:
        n, _ = run_kind(kind, args.cases, args.seed, tally)
        print(f"{kind:20s} {n} cases")
        if n < args.cases:
            short.append(kind)
    for item, (passed, total) in tally.counts.items():
        print(f"{item:18s} {passed}/{total}")
    print(f"gate_r_edge: {tally.passed}/{tally.total} ({tally.pass_rate:.4%})")
    ok = True
    if short:
        print(f"too few cases for {short}: the generator rarely produces the situation; strengthen it in "
              "referee/gate_r/edge.py (referee-change)")
        ok = False
    if tally.passed != tally.total:
        print(f"failures (first {len(tally.failures)}):")
        print("\n".join("  " + f for f in tally.failures))
        print("engines disagree or break a rule: fix stalker/tournament; if the rule is wrong, referee/gate_r "
              "via referee-change")
        ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
