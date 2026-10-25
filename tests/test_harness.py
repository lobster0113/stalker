import importlib.util
import re
import subprocess
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
    assert roles == {cfg["instructions"] for cfg in sched.values()}


def _run_pytest(tmp_path, body, require_torch):
    import os
    import shutil
    import subprocess
    import sys

    shutil.copy(ROOT / "tests" / "conftest.py", tmp_path / "conftest.py")
    (tmp_path / "test_case.py").write_text(body)
    env = {k: v for k, v in os.environ.items() if k != "STALKER_REQUIRE_TORCH"}
    if require_torch:
        env["STALKER_REQUIRE_TORCH"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(tmp_path)],
        cwd=tmp_path, env=env, capture_output=True, text=True,
    )


NO_TESTS_COLLECTED = 5  # a module-level skip leaves nothing to run
FAILED = (1, 2)  # test failure, or collection error
MISSING_TORCH = 'import pytest\npytest.importorskip("torch_missing_for_test")\n\ndef test_x():\n    pass\n'


def test_require_torch_turns_torch_skip_into_failure(tmp_path):
    r = _run_pytest(tmp_path, MISSING_TORCH, require_torch=False)
    assert r.returncode == NO_TESTS_COLLECTED and "1 skipped" in r.stdout
    r = _run_pytest(tmp_path, MISSING_TORCH, require_torch=True)
    assert r.returncode in FAILED
    assert "STALKER_REQUIRE_TORCH" in r.stdout


def test_require_torch_catches_in_test_skip_and_keeps_other_skips(tmp_path):
    in_test = 'import pytest\n\ndef test_x():\n    pytest.skip("torch not available")\n'
    assert _run_pytest(tmp_path, in_test, require_torch=True).returncode in FAILED
    other = 'import pytest\n\ndef test_x():\n    pytest.skip("solver binary missing")\n'
    r = _run_pytest(tmp_path, other, require_torch=True)
    assert r.returncode == 0 and "1 skipped" in r.stdout


def test_ci_rl_job_runs_torch_tests_without_skips():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    jobs = {}
    name = None
    for line in ci.splitlines():
        if line.startswith("  ") and not line.startswith("   ") and line.strip().endswith(":"):
            name = line.strip()[:-1]
            jobs[name] = []
        elif name:
            jobs[name].append(line)
    assert {"gates", "guard", "rl", "record-metrics"} <= set(jobs)
    rl = "\n".join(jobs["rl"])
    assert "download.pytorch.org/whl/cpu" in rl
    assert '".[dev,rl]"' in rl
    assert 'STALKER_REQUIRE_TORCH: "1"' in rl
    assert "tests/test_rl_" in rl
    assert "timeout-minutes: 20" in rl
    assert "cache: pip" in rl
    gates = "\n".join(jobs["gates"])
    assert "python -m referee.gates full" in gates and "rl]" not in gates


def test_texassolver_job_is_manual_capped_and_secretless():
    wf = (ROOT / ".github" / "workflows" / "texassolver.yml").read_text()
    on = wf.split("\non:\n", 1)[1].split("\n\n", 1)[0]
    assert "workflow_dispatch:" in on
    assert not any(t in on for t in ("pull_request", "push:", "schedule:", "workflow_run"))
    minutes = [int(line.split(":")[1]) for line in wf.splitlines() if line.strip().startswith("timeout-minutes:")]
    assert minutes and all(m <= 60 for m in minutes)
    assert "secrets." not in wf
    assert "actions/cache@" in wf and "key: texassolver-${{ runner.os }}-${{ steps.commit.outputs.sha }}" in wf
    order = ["install_texassolver.sh", "pytest -m slow", "tests/test_texassolver.py",
             "stalker.tools.bench_texassolver", "actions/upload-artifact@"]
    pos = [wf.index(s) for s in order]
    assert pos == sorted(pos)
    assert '"runner":' in wf and "if: always()" in wf
    # inputs reach the shell only via env; `${{ inputs.* }}` inside `run:` would allow injection
    assert all("${{ inputs." not in line for line in wf.splitlines() if "run:" in line or "python -m" in line)


def test_texassolver_job_cache_key_tracks_install_commit():
    script = (ROOT / "scripts" / "install_texassolver.sh").read_text()
    (commit,) = re.findall(r'^COMMIT="([0-9a-f]{40})"', script, re.M)
    wf = (ROOT / ".github" / "workflows" / "texassolver.yml").read_text()
    sed = re.search(r"sha=\$\(sed -n '([^']+)' scripts/install_texassolver.sh\)", wf).group(1)
    out = subprocess.run(["sed", "-n", sed, str(ROOT / "scripts" / "install_texassolver.sh")],
                         capture_output=True, text=True, check=True).stdout.strip()
    assert out == commit
