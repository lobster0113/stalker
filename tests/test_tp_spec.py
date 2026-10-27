import copy
import json
import re
import warnings
from pathlib import Path

import pytest

from stalker.tp.spec import SpecError, load, validate

ROOT = Path(__file__).resolve().parent.parent
TP_MD = (ROOT / "docs" / "TP.md").read_text(encoding="utf-8")
DEMO = (ROOT / "web" / "demo" / "index.html").read_text(encoding="utf-8")
TIER_NAMES = {"초보": "beginner", "중수": "mid", "고수": "pro"}


def _section(md: str, start: str, end: str) -> str:
    return md[md.index(start):md.index(end)]


def _doc_item_ids() -> set[str]:
    s3 = _section(TP_MD, "## 3. 판단 항목", "## 4.")
    return set(re.findall(r"^\| `([a-z]+\.[a-z]+)` \|", s3, flags=re.M))


def _doc_tiers() -> dict[str, list[str]]:
    s41 = _section(TP_MD, "### 4.1", "### 4.2")
    out, acc = {}, []
    for name, cell in re.findall(r"^\| (초보|중수|고수) \| ([^|]+) \|", s41, flags=re.M):
        acc = acc + re.findall(r"`([a-z]+\.[a-z]+)`", cell)
        out[TIER_NAMES[name]] = list(acc)
    return out


def test_spec_loads_with_stable_hash():
    a, b = load(), load("0.1")
    assert a.version == "0.1" and a.sha256 == b.sha256 and len(a.sha256) == 64


def test_doc_items_equal_spec_items():
    assert _doc_item_ids() == set(load().item_ids)


def test_doc_tier_lists_match_spec():
    spec = load()
    doc = _doc_tiers()
    assert set(doc) == {"beginner", "mid", "pro"}
    for tier, items in doc.items():
        judged = [i for i in spec.tier_items(tier) if i != "act.choice"]
        assert set(judged) == set(items), tier
        assert "act.choice" in spec.tier_items(tier)


def _doc_scale(cell: str):
    """§4.1 '눈금' cell -> spec `steps`: '5단계(0/25/...)' -> list, 'N단계' -> N even steps, '0–100' -> '0-100'."""
    cell = cell.strip()
    if cell in ("0–100", "0-100"):
        return "0-100"
    m = re.fullmatch(r"(\d+)단계(?:\(([\d/]+)\))?", cell)
    assert m, f"unparsed scale cell {cell!r}"
    n = int(m.group(1))
    steps = [int(x) for x in m.group(2).split("/")] if m.group(2) else [round(100 * i / (n - 1)) for i in range(n)]
    assert len(steps) == n
    return steps


def test_doc_scales_and_tolerances_match_spec():
    spec = load().data["tiers"]
    s41 = _section(TP_MD, "### 4.1", "### 4.2")
    rows = re.findall(r"^\| (초보|중수|고수) \| [^|]+ \| ([^|]+) \|", s41, flags=re.M)
    assert len(rows) == 3
    for name, cell in rows:
        assert spec[TIER_NAMES[name]]["steps"] == _doc_scale(cell), name
    tol = re.search(r"초보 ±([\d.]+), 중수 ±([\d.]+), 고수 ±([\d.]+)", TP_MD).groups()
    assert [spec[t]["tolerance"] for t in ("beginner", "mid", "pro")] == [float(x) for x in tol]


def test_doc_grading_exclusions_match_spec():
    spec = load()
    assert spec.item("plan.pot")["eligible_for_grading"] is False
    assert set(spec.graded()) == set(spec.item_ids) - {"plan.pot"}


def test_doc_na_opportunity_counts_match_spec():
    s31 = _section(TP_MD, "### 3.1", "### 3.2")
    doc = {i: int(n) for i, n in re.findall(r"^\| `(opp\.[a-z]+)` \|.*?기회 < (\d+)회", s31, flags=re.M)}
    spec = load()
    assert doc == {i: spec.item(i)["na"]["min_opportunities"] for i in doc}
    assert set(doc) == {"opp.loose", "opp.aggr", "opp.foldy"}


def _edges(text: str) -> list[float]:
    """'≤5·5–10·...·100+ BB' -> [5, 10, ..., 100]: the upper edge of every bounded bucket."""
    out = []
    for part in text.split("·"):
        m = re.match(r"≤?([\d.]+)(?:[–-]([\d.]+))?", part.strip())
        if m and "+" not in part:
            out.append(float(m.group(2) or m.group(1)))
    return out


def test_doc_buckets_match_spec():
    b, sizes = load().data["buckets"], load().data["size_buckets"]
    line = next(x for x in TP_MD.splitlines() if x.startswith("- 둔감해야 할 조건 축"))
    axes = {k.strip(): v for k, v in (re.match(r"(유효 스택|벳 크기|프리플랍 레이즈) (.*)", a.strip()).groups()
                                      for a in line.split(":", 1)[1].split(" / ")[:3])}
    assert _edges(axes["유효 스택"]) == b["effective_stack_bb"]
    assert _edges(axes["벳 크기"]) == b["bet_size_pot_pct"]
    assert _edges(axes["프리플랍 레이즈"]) == b["preflop_raise_bb"]
    assert axes["벳 크기"].endswith("올인") and axes["프리플랍 레이즈"].endswith("올인") and b["all_in_bucket"]
    size_line = next(x for x in TP_MD.splitlines() if x.startswith("- 사이즈 버킷:"))
    pre, post = re.search(r"프리플랍 (.*?), 포스트플랍 (.*?)\.", size_line).groups()
    num = lambda t: [float(x) for x in re.findall(r"([\d.]+)[x%]", t)] + (["all_in"] if t.endswith("올인") else [])
    assert num(pre) == sizes["preflop_x"] and num(post) == sizes["postflop_pot_pct"]


def test_decision_context_fields_are_listed_in_doc():
    s11 = _section(TP_MD, "### 1.1", "### 1.2")
    spec = load().data
    assert spec["decision_context_version"] == "0.1" and "DecisionContext v0.1" in s11
    # Spot-check the facts that most often get confused with judgments.
    for word in ("SPR", "필요 에퀴티", "유효 스택", "합법 액션"):
        assert word in s11
    assert {"spr", "required_equity", "effective_stack_bb", "legal_actions"} <= set(spec["decision_context"])


def _bad(mutate):
    data = copy.deepcopy(load().data)
    mutate(data)
    return data


@pytest.mark.parametrize("mutate,msg", [
    (lambda d: d.pop("tiers"), "missing top-level key 'tiers'"),
    (lambda d: d["items"].append(dict(d["items"][0])), "duplicate item ids"),
    (lambda d: d["items"][0].update(kind="guess"), "kind 'guess'"),
    (lambda d: d["tiers"]["mid"]["items"].remove("opp.range"), "higher tiers must include"),
    (lambda d: d["tiers"]["pro"]["items"].append("opp.bluff"), "unknown items"),
    (lambda d: d["buckets"].update(effective_stack_bb=[10, 5]), "strictly increasing"),
    (lambda d: next(i for i in d["items"] if i["id"] == "plan.pot").update(eligible_for_grading=True),
     "eligible_for_grading to false"),
])
def test_invalid_spec_errors_say_how_to_fix(mutate, msg):
    with pytest.raises(SpecError, match=re.escape(msg)):
        validate(_bad(mutate))


def test_unknown_version_lists_available():
    with pytest.raises(SpecError, match="available: tp_v0_1.json"):
        load("9.9")


def _demo_defs():
    tp_block = DEMO[DEMO.index("const TP = {"):DEMO.index("};", DEMO.index("const TP = {"))]
    items = set(re.findall(r'^\s*"([a-z]+\.[a-z]+)":', tp_block, flags=re.M))
    tiers = {}
    for key, body in re.findall(r"^\s*(beginner|mid|pro): \{(.*?)\},?$", DEMO, flags=re.M):
        tiers[key] = set(re.findall(r'"([a-z]+\.[a-z]+)"', body.split("items:")[1]))
    return items, tiers


def demo_differences() -> list[str]:
    spec = load()
    items, tiers = _demo_defs()
    diffs = []
    if items != set(spec.item_ids):
        diffs.append(f"TP items: demo-only {sorted(items - set(spec.item_ids))}, "
                     f"spec-only {sorted(set(spec.item_ids) - items)}")
    for t in ("beginner", "mid", "pro"):
        want = set(spec.tier_items(t))
        if tiers.get(t) != want:
            got = tiers.get(t, set())
            diffs.append(f"tier {t}: demo-only {sorted(got - want)}, spec-only {sorted(want - got)}")
    return diffs


def test_demo_differences_are_reported():
    # Visible in the default pytest output (warnings summary) until #115 brings the demo to the spec.
    diffs = demo_differences()
    if diffs:
        warnings.warn("demo vs TP spec: " + " | ".join(diffs))


def test_demo_parser_finds_definitions():
    items, tiers = _demo_defs()
    assert "hand.equity" in items and set(tiers) == {"beginner", "mid", "pro"}


@pytest.mark.xfail(strict=True, reason="demo still on TP v0; #115 updates it, then this must pass")
def test_demo_matches_spec():
    diffs = demo_differences()
    print("\n".join(diffs))
    assert not diffs
