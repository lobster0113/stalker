import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "research" / "2026-11-north-star-coverage.md"


def _metrics_key_patterns() -> list[re.Pattern]:
    """Every string literal in referee/metrics.py; f-string holes match anything."""
    pats = []
    for node in ast.walk(ast.parse((ROOT / "referee" / "metrics.py").read_text(encoding="utf-8"))):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            pats.append(re.compile(re.escape(node.value)))
        elif isinstance(node, ast.JoinedStr):
            parts = [re.escape(v.value) if isinstance(v, ast.Constant) else ".+" for v in node.values]
            pats.append(re.compile("".join(parts)))
    return pats


def _documented_keys() -> set[str]:
    keys = set()
    for line in DOC.read_text(encoding="utf-8").split("## 2.")[0].splitlines():
        cells = line.split("|")
        if line.startswith("|") and len(cells) >= 5 and "없음" not in cells[2]:
            keys.update(re.findall(r"`([a-z0-9_<>]+)`", cells[2]))
    return keys


def test_documented_history_keys_exist_in_metrics():
    # The doc table must not name keys the snapshot never writes (#892).
    keys = _documented_keys()
    assert len(keys) >= 10, "table parse found too few keys: keep the 'history 키' column as the 2nd cell"
    pats = _metrics_key_patterns()
    missing = sorted(k for k in keys
                     if not any(p.fullmatch(re.sub("<tier>", "beginner", k)) for p in pats))
    assert not missing, f"keys not produced by referee/metrics.py: {missing}: fix the table or the key name"
