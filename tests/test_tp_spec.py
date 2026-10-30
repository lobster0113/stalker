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
    a, b = load(), load("0.3")
    assert a.version == "0.3" and a.sha256 == b.sha256 and len(a.sha256) == 64


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
    assert _size_lines() == {k: v for k, v in sizes.items() if isinstance(v, list)}


SIZE_LINES = {"프리플랍 오픈": "preflop_open_bb", "프리플랍 3벳": "preflop_3bet_x", "프리플랍 4벳": "preflop_4bet_x",
              "프리플랍 5벳 이상": "preflop_5bet_plus", "포스트플랍 벳": "postflop_bet_pot_pct",
              "포스트플랍 레이즈": "postflop_raise_x"}


def _size_lines() -> dict[str, list]:
    """TP.md section 6 size bucket sub-items, e.g. "  - 포스트플랍 벳: 20·33·…·300% 팟·올인." -> spec lists."""
    out = {}
    for line in TP_MD.splitlines():
        m = re.match(r"  - (.+?)(?:\(.*?\))?: (.*)", line)
        if m and m.group(1).strip() in SIZE_LINES:
            vals = m.group(2).split("올인")[0]   # the numbers come before the all-in; notes after it
            nums = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)", vals)]
            out[SIZE_LINES[m.group(1).strip()]] = nums + (["all_in"] if "올인" in m.group(2) else [])
    return out


def test_size_buckets_are_the_training_menu():
    # TP.md section 6 = spec = the E3 "real" menu (#382): one change has to touch all three.
    from stalker.e3 import game as G
    sizes = load().data["size_buckets"]
    num = lambda xs: [x for x in xs if x != "all_in"]
    assert num(sizes["preflop_open_bb"]) == [x for _, x in G.REAL_OPEN]
    assert num(sizes["preflop_3bet_x"]) == [x for _, x in G.REAL_PREFLOP_RAISE[2]]
    assert num(sizes["preflop_4bet_x"]) == [x for _, x in G.REAL_PREFLOP_RAISE[3]]
    assert num(sizes["postflop_bet_pot_pct"]) == [round(100 * x) for _, x in G.REAL_BET]
    assert num(sizes["postflop_raise_x"]) == [x for _, x in G.REAL_RAISE]
    assert sizes["preflop_iso_per_limper_bb"] * G.BB == G.ISO_PER_LIMPER
    assert all(v[-1] == "all_in" for v in sizes.values() if isinstance(v, list))
    assert sizes["translation"]["rule"] == "pseudo_harmonic"


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
    (lambda d: next(i for i in d["items"] if i["id"] == "hand.equity")["question_forms"]["beginner"]
     .update(form="slider"), "form 'slider'"),
    (lambda d: next(i for i in d["items"] if i["id"] == "hand.equity")["question_forms"]
     .update(expert={"form": "rank", "question": "q"}), "question_forms tier 'expert'"),
    (lambda d: next(i for i in d["items"] if i["id"] == "hand.equity")["question_forms"]["beginner"]
     .pop("answer"), "lacks 'answer'; a rank form must define its graded answer"),
    (lambda d: next(i for i in d["items"] if i["id"] == "hand.equity")["question_forms"]["beginner"]
     .update(bands=[0.4, 0.2, 0.6, 0.8]), "strictly increasing shares"),
    (lambda d: next(i for i in d["items"] if i["id"] == "hand.equity")["question_forms"]["beginner"]
     .update(bands=[0.25, 0.5, 0.75]), "5 chips for 3 bands"),
])
def test_invalid_spec_errors_say_how_to_fix(mutate, msg):
    with pytest.raises(SpecError, match=re.escape(msg)):
        validate(_bad(mutate))


def test_beginner_equity_is_asked_as_rank_in_doc_spec_and_demo():
    # ADR 0011 #263: beginners answer hand.equity as "top X% of my range"; the call comparison
    # (hand.eq_call) stays a win probability, and mid/pro keep form A.
    qf = load().item("hand.equity")["question_forms"]
    assert set(qf) == {"beginner"} and qf["beginner"]["form"] == "rank"
    assert qf["beginner"]["exception"] == "hand.eq_call"
    row = next(x for x in _section(TP_MD, "### 3.1", "### 3.2").splitlines() if x.startswith("| `hand.equity`"))
    assert qf["beginner"]["question"] in row and "`hand.eq_call`" in row
    assert qf["beginner"]["question"] in DEMO


def test_beginner_rank_answer_and_scale_are_in_the_contract():
    # The rank form grades share_better, not the equity value, so its definition and scale live in the
    # spec and TP.md, and the demo grades the same chips against my range (not all hands).
    qf = load().item("hand.equity")["question_forms"]["beginner"]
    assert qf["answer"].startswith("share_better") and "내 레인지" in qf["answer"]
    assert qf["bands"] == [0.2, 0.4, 0.6, 0.8] and len(qf["chips"]) == 5
    row = next(x for x in _section(TP_MD, "### 3.1", "### 3.2").splitlines() if x.startswith("| `hand.equity`"))
    assert "share_better" in row
    sec = _section(TP_MD, "### 4.1", "### 4.2")
    assert "0.2·0.4·0.6·0.8" in sec and all(c in sec for c in qf["chips"])
    b_chips = re.search(r'B: \{[^}]*chips: \[([^\]]*)\]', DEMO).group(1)
    assert [c.strip().strip('"') for c in b_chips.split(",")] == qf["chips"]
    assert 'eqabTruth("B", g, heroRangePct(CUR.hero))' in DEMO


def test_unknown_version_lists_available():
    with pytest.raises(SpecError, match="available: tp_v0_3.json"):
        load("9.9")


def _demo_defs():
    tp_block = DEMO[DEMO.index("const TP = {"):DEMO.index("};", DEMO.index("const TP = {"))]
    items = set(re.findall(r'^\s*"([a-z]+\.[a-z]+)":', tp_block, flags=re.M))
    tiers = {}
    for key, body in re.findall(r"^\s*(beginner|mid|pro): \{(.*?)\},?$", DEMO, flags=re.M):
        tiers[key] = set(re.findall(r'"([a-z]+\.[a-z]+)"', body.split("items:")[1]))
    return items, tiers


def _demo_quick_mode():
    m = re.search(r"^const MODES = (\{.*\});$", DEMO, flags=re.M)
    return json.loads(m.group(1))["quick"] if m else None


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
    quick = _demo_quick_mode()
    want = {k: spec.data["modes"]["quick"][k] for k in ("max_judgments", "rule")}
    if quick != want:
        diffs.append(f"modes.quick: demo {quick} != spec {want} (copy the spec's max_judgments/rule into MODES)")
    return diffs


def test_demo_differences_are_reported():
    # Visible in the default pytest output (warnings summary) until #115 brings the demo to the spec.
    diffs = demo_differences()
    if diffs:
        warnings.warn("demo vs TP spec: " + " | ".join(diffs))


def test_demo_parser_finds_definitions():
    items, tiers = _demo_defs()
    assert "hand.equity" in items and set(tiers) == {"beginner", "mid", "pro"}


def test_demo_quick_rule_is_read_from_spec_field():
    # Quick must pick its questions through MODES (the spec field), not a list hard-coded in the flow.
    assert _demo_quick_mode() is not None, "web/demo/index.html: no single-line `const MODES = {...};` JSON"
    assert "MODES.quick.rule[" in DEMO and "MODES.quick.max_judgments" in DEMO


def test_demo_matches_spec():
    diffs = demo_differences()
    print("\n".join(diffs))
    assert not diffs


def test_demo_size_shortcuts_are_the_spec_sizes():
    # The training screen's size shortcuts (#386) are TP.md section 6's real-play sizes.
    m = re.search(r"^const REAL_SIZES = (\{.*?\});$", DEMO, flags=re.M | re.S)
    assert m, "web/demo/index.html: no `const REAL_SIZES = {...};`"
    demo = json.loads(re.sub(r"(\w+):", r'"\1":', m.group(1)))
    sizes = load().data["size_buckets"]
    num = lambda xs: [x for x in xs if x != "all_in"]
    assert demo == {"open": num(sizes["preflop_open_bb"]), "three": num(sizes["preflop_3bet_x"]),
                    "four": num(sizes["preflop_4bet_x"]), "raise": num(sizes["postflop_raise_x"]),
                    "bet": num(sizes["postflop_bet_pot_pct"])}
