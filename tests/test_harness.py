import importlib.util
from pathlib import Path

from referee.guard import load_rules, violations

ROOT = Path(__file__).resolve().parent.parent


def _load(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_guard_rules_parse():
    rules = load_rules()
    assert "referee/" in rules["referee-change"]
    assert "CLAUDE.md" in rules["harness-change"]


def test_guard_flags_unlabeled_protected_change():
    rules = load_rules()
    changed = ["stalker/core/cards.py", "referee/gates.py", "harness/routines/builder.md"]
    v = violations(changed, set(), rules)
    assert len(v) == 2
    assert violations(changed, {"referee-change", "harness-change"}, rules) == []
    assert violations(["stalker/x.py"], set(), rules) == []


def test_bash_guard_blocks_policy_violations():
    g = _load(ROOT / "harness" / "hooks" / "guard_bash.py")
    for cmd in ["git push --force origin claude/1-x", "git push origin main", "git push -u origin HEAD:main",
                "gh secret set X", "gh repo delete foo", "git filter-branch", "gh api -X DELETE repos/a/b"]:
        assert g.check(cmd), cmd
    for cmd in ["git push -u origin claude/12-fix-main", "git push origin ops", "gh pr merge 3 --squash --delete-branch",
                "git commit -m 'main: tidy'", "gh api repos/a/b/pulls"]:
        assert g.check(cmd) is None, cmd


def test_schedule_covers_all_routines():
    import json
    sched = json.loads((ROOT / "harness" / "schedule.json").read_text())
    roles = {p.stem for p in (ROOT / "harness" / "routines").glob("*.md")}
    assert roles == set(sched)
