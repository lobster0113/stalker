"""#439: TP.md section 6 states the high_translation_error rule with the same constants as the code."""
import re
from pathlib import Path

from stalker.e3 import game as G
from stalker.e3 import translate as T

TP = (Path(__file__).resolve().parents[1] / "docs" / "TP.md").read_text(encoding="utf-8")
FIX = "TP.md section 6 and stalker/e3/translate.py disagree: change both in one referee-change PR (#439)"


def _rule():
    i = TP.index("**번역 오차 큼(#417")
    return TP[i:TP.index("\n  - ", i + 1)]


def test_tp_md_constants_match_code():
    rule = _rule()
    assert f"`ALLIN_MERGE` = {G.ALLIN_MERGE}" in rule and f"**{round(G.ALLIN_MERGE * 100)}%**" in rule, FIX
    assert f"**{T.F_BAND[0]} < f < {T.F_BAND[1]}**" in rule, FIX
    assert f"`GAP_HIGH` = {T.GAP_HIGH}" in rule and f"**{T.GAP_HIGH:g}배**" in rule, FIX
    assert f"**{T.TV_HIGH}**(`TV_HIGH`)" in rule, FIX


def test_tp_md_states_approximate_grading_and_the_sweep_tool():
    rule = _rule()
    assert "근사로 채점" in rule and "근사(번역)" in rule, FIX
    assert re.search(r"python -m stalker\.tools\.translation_map", rule), FIX
