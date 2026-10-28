"""Kuhn poker: 3 cards (J<Q<K), ante 1, one bet of 1, player 0 acts first.

Infoset keys are `<card>:<history>` with history over {k=check, b=bet, c=call, f=fold}.
Equilibrium value for player 0 is -1/18 (Kuhn 1950).
"""
from __future__ import annotations

from itertools import permutations

from .game import CHANCE, PLAYER, TERMINAL, Node, finalize

CARDS = "JQK"
GAME_VALUE = -1.0 / 18.0


def _node(cards: tuple[int, int], h: str) -> Node:
    if h in ("kk", "bc", "kbc"):
        each = 1 if h == "kk" else 2
        return Node(TERMINAL, utility=each if cards[0] > cards[1] else -each)
    if h == "bf":
        return Node(TERMINAL, utility=1.0)
    if h == "kbf":
        return Node(TERMINAL, utility=-1.0)
    player = len(h) % 2
    actions = ("c", "f") if h.endswith("b") else ("k", "b")
    return Node(PLAYER, player=player, infoset=f"{CARDS[cards[player]]}:{h}", actions=actions,
                children=[_node(cards, h + a) for a in actions])


def game() -> Node:
    deals = list(permutations(range(3), 2))
    return finalize(Node(CHANCE, children=[_node(d, "") for d in deals], probs=(1 / len(deals),) * len(deals)))


def nash(alpha: float = 0.0) -> dict:
    """The known equilibrium family (alpha in [0, 1/3]): player 0 bets J with alpha, K with 3*alpha."""
    return {
        "J:": [1 - alpha, alpha], "Q:": [1.0, 0.0], "K:": [1 - 3 * alpha, 3 * alpha],
        "J:kb": [0.0, 1.0], "Q:kb": [alpha + 1 / 3, 2 / 3 - alpha], "K:kb": [1.0, 0.0],
        "J:k": [2 / 3, 1 / 3], "Q:k": [1.0, 0.0], "K:k": [0.0, 1.0],
        "J:b": [0.0, 1.0], "Q:b": [1 / 3, 2 / 3], "K:b": [1.0, 0.0],
    }
