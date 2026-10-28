"""Leduc hold'em: deck J,J,Q,Q,K,K; ante 1; a private card each, one public card after round 1.

Bets are 2 in round 1 and 4 in round 2, at most two raises (bet + raise) per round, player 0
opens both rounds. A private card pairing the public card wins; otherwise the higher private card
wins; equal ranks split. Infoset keys: `<private>[<public>]:<round1>[/<round2>]` over
{k=check, b=bet, r=raise, c=call, f=fold}. Equilibrium value for player 0 is about -0.0856
(Southey et al. 2005), which CFR reproduces in the tests.
"""
from __future__ import annotations

from .game import CHANCE, PLAYER, TERMINAL, Node, finalize

RANKS = "JQK"
DECK = (0, 0, 1, 1, 2, 2)
BET = (2, 4)
GAME_VALUE_APPROX = -0.0856


def _actions(h: str) -> tuple[str, ...]:
    if h in ("", "k"):
        return ("k", "b")
    raises = sum(a in "br" for a in h)
    return ("c", "f", "r") if raises < 2 else ("c", "f")


def _round_over(h: str) -> bool:
    return h == "kk" or (len(h) >= 2 and h[-1] in "cf")


def _contrib(h: str, bet: int, start: int) -> list[int]:
    """Chips each player has in after round history h (both started the round at `start`)."""
    put = [start, start]
    for i, a in enumerate(h):
        p = i % 2
        if a in "br":
            put[p] = put[1 - p] + bet
        elif a == "c":
            put[p] = put[1 - p]
    return put


def _showdown(priv: tuple[int, int], pub: int) -> int:
    """+1 if player 0 wins, -1 if player 1 wins, 0 split."""
    s = [(priv[p] == pub, priv[p]) for p in (0, 1)]
    return (s[0] > s[1]) - (s[0] < s[1])


def _node(priv: tuple[int, int], pub: int | None, r1: str, r2: str | None) -> Node:
    rnd = 0 if r2 is None else 1
    h = r1 if rnd == 0 else r2
    start = 1 if rnd == 0 else _contrib(r1, BET[0], 1)[0]
    if _round_over(h):
        put = _contrib(h, BET[rnd], start)
        if h[-1] == "f":
            folder = (len(h) - 1) % 2
            return Node(TERMINAL, utility=-put[0] if folder == 0 else put[1])
        if rnd == 0:
            return _deal_public(priv, r1)
        return Node(TERMINAL, utility=_showdown(priv, pub) * put[0])
    p = len(h) % 2
    acts = _actions(h)
    seen = RANKS[priv[p]] + ("" if pub is None else RANKS[pub])
    key = f"{seen}:{r1}" + ("" if r2 is None else f"/{r2}")
    kids = [_node(priv, pub, r1 + a, None) if rnd == 0 else _node(priv, pub, r1, r2 + a) for a in acts]
    return Node(PLAYER, player=p, infoset=key, actions=acts, children=kids)


def _deal_public(priv: tuple[int, int], r1: str) -> Node:
    rest = list(DECK)
    rest.remove(priv[0])
    rest.remove(priv[1])
    cards = sorted(set(rest))
    return Node(CHANCE, children=[_node(priv, c, r1, "") for c in cards],
                probs=tuple(rest.count(c) / len(rest) for c in cards))


def game() -> Node:
    kids, probs = [], []
    for a in range(3):
        for b in range(3):
            n_b = DECK.count(b) - (a == b)
            if n_b > 0:
                probs.append(DECK.count(a) / 6 * n_b / 5)
                kids.append(_node((a, b), None, "", None))
    return finalize(Node(CHANCE, children=kids, probs=tuple(probs)))
