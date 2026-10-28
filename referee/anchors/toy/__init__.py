"""E0 toy poker games with exact best response (Gate Q4 anchor).

`kuhn.game()` and `leduc.game()` build full game trees; `exploitability(root, strategy)` is exact
(no sampling), so a policy's distance from equilibrium can be stated as a number here (and in E1
push/fold) and nowhere else.
"""
from .game import Node, best_response_value, exploitability, expected_value, infosets

__all__ = ["Node", "best_response_value", "exploitability", "expected_value", "infosets"]
