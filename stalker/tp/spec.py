"""Load and validate the TP machine-readable spec (`stalker/tp/spec/tp_v<version>.json`).

    from stalker.tp.spec import load
    spec = load()            # latest version
    spec.item("hand.equity")["kind"]

The JSON must match docs/TP.md (tests compare them); `sha256` (of the canonical JSON) lets records
name the exact spec.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

SPEC_DIR = Path(__file__).resolve().parent / "spec"
LATEST = "0.2"
KINDS = {"judgment", "computed", "decision", "reflection"}
MODULES = {"common", "postflop", "plan", "decision"}
GRADING_CONDITIONS = {
    "always", "ci_width_le_30", "tier_metric", "assumption_shown", "tier_pro_only",
    "tier_mid_or_above", "single_table_exact_icm", "definition_open", "q_values_available",
}
TIER_ORDER = ("beginner", "mid", "pro")
# Per-tier question forms (ADR 0011 #263): "rank" asks the item as "top X% of my range" on screen;
# the graded answer is the form's own `answer` (a different quantity from the item value), so the
# contract must carry its definition and scale; the item value itself (records, Gate T2) is unchanged.
QUESTION_FORMS = {"rank"}
RANK_FORM_KEYS = ("answer", "bands", "chips", "chip_rule", "grading")
REQUIRED = ("tp_version", "decision_context_version", "decision_context", "items", "tiers", "modes",
            "grading", "buckets", "sensitivity_exceptions", "size_buckets")


class SpecError(ValueError):
    pass


@dataclass(frozen=True)
class Spec:
    data: dict
    sha256: str
    path: Path

    @property
    def version(self) -> str:
        return self.data["tp_version"]

    @property
    def item_ids(self) -> list[str]:
        return [i["id"] for i in self.data["items"]]

    def item(self, item_id: str) -> dict:
        for i in self.data["items"]:
            if i["id"] == item_id:
                return i
        raise KeyError(f"no TP item {item_id!r} in spec {self.version}; known: {', '.join(self.item_ids)}")

    def tier_items(self, tier: str) -> list[str]:
        return list(self.data["tiers"][tier]["items"])

    def graded(self) -> list[str]:
        return [i["id"] for i in self.data["items"] if i["eligible_for_grading"]]


def _fail(path: Path, msg: str) -> None:
    raise SpecError(f"{path.name}: {msg}")


def validate(data: dict, path: Path = Path("tp_spec.json")) -> None:
    for k in REQUIRED:
        if k not in data:
            _fail(path, f"missing top-level key {k!r}; add it (see docs/TP.md)")
    ids = [i.get("id") for i in data["items"]]
    if len(ids) != len(set(ids)):
        dup = sorted({i for i in ids if ids.count(i) > 1})
        _fail(path, f"duplicate item ids {dup}; each TP item id must appear once")
    for it in data["items"]:
        where = f"item {it.get('id')!r}"
        for k in ("module", "kind", "question", "scale", "applies", "eligible_for_grading", "grading_condition"):
            if k not in it:
                _fail(path, f"{where} lacks {k!r}")
        if it["kind"] not in KINDS:
            _fail(path, f"{where} kind {it['kind']!r}; use one of {sorted(KINDS)}")
        if it["module"] not in MODULES:
            _fail(path, f"{where} module {it['module']!r}; use one of {sorted(MODULES)}")
        if it["grading_condition"] not in GRADING_CONDITIONS:
            _fail(path, f"{where} grading_condition {it['grading_condition']!r}; add it to GRADING_CONDITIONS "
                        "in stalker/tp/spec.py together with its meaning, or use a known one")
        if it["kind"] == "reflection" and it["eligible_for_grading"]:
            _fail(path, f"{where} is a reflection question; set eligible_for_grading to false")
        for tier, qf in it.get("question_forms", {}).items():
            if tier not in TIER_ORDER:
                _fail(path, f"{where} question_forms tier {tier!r}; use one of {list(TIER_ORDER)}")
            if qf.get("form") not in QUESTION_FORMS:
                _fail(path, f"{where} question_forms[{tier!r}] form {qf.get('form')!r}; use one of "
                            f"{sorted(QUESTION_FORMS)} or add the form to QUESTION_FORMS with its meaning")
            if not qf.get("question"):
                _fail(path, f"{where} question_forms[{tier!r}] lacks 'question'; give the on-screen wording")
            if qf["form"] == "rank":
                for k in RANK_FORM_KEYS:
                    if not qf.get(k):
                        _fail(path, f"{where} question_forms[{tier!r}] lacks {k!r}; a rank form must define "
                                    f"its graded answer and scale ({', '.join(RANK_FORM_KEYS)}, see docs/TP.md §4.1)")
                b = qf["bands"]
                if not (all(0 < x < 1 for x in b) and all(x < y for x, y in zip(b, b[1:]))):
                    _fail(path, f"{where} question_forms[{tier!r}] bands {b}; use strictly increasing shares in (0, 1)")
                if len(qf["chips"]) != len(b) + 1:
                    _fail(path, f"{where} question_forms[{tier!r}] has {len(qf['chips'])} chips for {len(b)} bands; "
                                "give one chip per band interval (len(bands) + 1)")
    known = set(ids)
    prev: set[str] = set()
    for t in TIER_ORDER:
        tier = data["tiers"].get(t)
        if tier is None:
            _fail(path, f"tier {t!r} missing; tiers must be {list(TIER_ORDER)}")
        items = set(tier["items"])
        if items - known:
            _fail(path, f"tier {t!r} lists unknown items {sorted(items - known)}")
        if not prev <= items:
            _fail(path, f"tier {t!r} drops {sorted(prev - items)}; higher tiers must include lower tiers' items")
        prev = items
    for name, edges in data["buckets"].items():
        if isinstance(edges, list) and edges and all(isinstance(e, (int, float)) for e in edges):
            if edges != sorted(set(edges)):
                _fail(path, f"bucket {name!r} edges must be strictly increasing, got {edges}")


def load(version: str = LATEST) -> Spec:
    path = SPEC_DIR / f"tp_v{version.replace('.', '_')}.json"
    if not path.exists():
        raise SpecError(f"no TP spec for version {version!r} at {path}; available: "
                        + ", ".join(sorted(p.name for p in SPEC_DIR.glob("tp_v*.json"))))
    raw = path.read_bytes()
    try:
        data = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as e:
        raise SpecError(f"{path.name}: invalid JSON at line {e.lineno}: {e.msg}") from None
    validate(data, path)
    if data["tp_version"] != version:
        _fail(path, f"tp_version {data['tp_version']!r} does not match file name version {version!r}")
    # Hash the canonical form so line endings or formatting do not change the identity.
    canon = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return Spec(data=data, sha256=hashlib.sha256(canon).hexdigest(), path=path)
