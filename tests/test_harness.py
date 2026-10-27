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


def test_bash_guard_checks_each_command_separately():
    g = _load(ROOT / "harness" / "hooks" / "guard_bash.py")
    for cmd in ["git push -u origin x && gh pr view 1 --jq '\"a\" + .b'",
                "git push origin x; gh issue comment 1 --body \"고수 + SB\"",
                "git push origin x\necho a +b", "git push origin x | tee log +c"]:
        assert g.check(cmd) is None, cmd
    for cmd in ["git push origin +claude/1-x", "git push --force origin y", "cd a && git push --force origin y",
                "echo hi; git push -f origin y", "git status || git push origin +y", "true\ngit push origin main"]:
        assert g.check(cmd), cmd


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


def test_ci_web_job_runs_gate_u_with_timeout_and_screenshots():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    web = ci.split("\n  web:\n", 1)[1].split("\n\n", 1)[0]
    minutes = int(re.search(r"timeout-minutes: (\d+)", web).group(1))
    assert minutes <= 15
    assert "npm test" in web and "playwright install" in web
    assert "name: web-screenshots" in web and "if: always()" in web
    script = (ROOT / "web" / "e2e" / "gate-u.mjs").read_text()
    assert "scrollWidth" in script and "critical" in script
    assert all(f"{w}" in script for w in ("390", "820", "1440"))


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
    (cap,) = re.findall(r"bench_texassolver .*--timeout (\d+)", wf)
    assert int(cap) < 60 * 60
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


def _should_run():
    return _load(ROOT / "harness" / "should_run.py")


NOW = __import__("datetime").datetime(2026, 10, 26, 12, 0, tzinfo=__import__("datetime").timezone.utc)


def _lock_at(hours_ago):
    from datetime import timedelta
    return {"role": "builder", "run_id": "other", "started": (NOW - timedelta(hours=hours_ago)).isoformat()}


def _decide(lock, prev_hours_ago=2.0, role="builder"):
    from datetime import timedelta
    sr = _should_run()
    return sr.decide(role, False, now=NOW, read_lock=lambda r: lock,
                     last_run=lambda r: NOW - timedelta(hours=prev_hours_ago))


def test_should_run_skips_while_same_role_lock_is_fresh():
    ok, why = _decide(_lock_at(0.5))
    assert not ok and why.startswith("running")
    # Unthrottled roles (reviewer) are serialized by the lock too.
    ok, why = _decide(_lock_at(0.5), role="reviewer")
    assert not ok and why.startswith("running")


def test_should_run_ignores_expired_lock():
    ok, why = _decide(_lock_at(3.5))
    assert ok, why


def test_should_run_without_lock_falls_back_to_throttle():
    assert _decide(None, prev_hours_ago=2.0)[0]
    ok, why = _decide(None, prev_hours_ago=0.2)
    assert not ok and "<" in why


def _decide_planner(ready, prev_hours_ago, merged_hours_ago=None):
    from datetime import timedelta
    sr = _should_run()
    calls = []

    def count():
        calls.append(1)
        return ready

    merged = None if merged_hours_ago is None else NOW - timedelta(hours=merged_hours_ago)
    ok, why = sr.decide("planner", False, now=NOW, read_lock=lambda r: None,
                        last_run=lambda r: NOW - timedelta(hours=prev_hours_ago), ready_count=count,
                        main_updated_at=lambda: merged)
    return ok, why, calls


def test_planner_runs_right_after_a_merge():
    ok, why, _ = _decide_planner(ready=5, prev_hours_ago=0.5, merged_hours_ago=0.2)
    assert ok and why.startswith("main updated"), why
    # A merge older than the last run does not trigger it again.
    ok, why, _ = _decide_planner(ready=5, prev_hours_ago=0.5, merged_hours_ago=1)
    assert not ok and "<" in why


def test_merge_trigger_still_respects_the_lock():
    from datetime import timedelta
    sr = _should_run()
    ok, why = sr.decide("planner", False, now=NOW, read_lock=lambda r: _lock_at(0.5),
                        last_run=lambda r: NOW - timedelta(hours=1),
                        main_updated_at=lambda: NOW - timedelta(minutes=5))
    assert not ok and why.startswith("running")


def test_planner_runs_early_when_ready_queue_is_low():
    ok, why, _ = _decide_planner(ready=1, prev_hours_ago=3)
    assert ok and why.startswith("queue low"), why
    ok, why, _ = _decide_planner(ready=0, prev_hours_ago=3)
    assert ok and why.startswith("queue low"), why
    # Still respects the 2h spacing so an empty queue cannot make the planner run hourly.
    ok, why, _ = _decide_planner(ready=0, prev_hours_ago=1)
    assert not ok and "<" in why


def test_planner_keeps_interval_when_ready_queue_is_full():
    ok, why, _ = _decide_planner(ready=5, prev_hours_ago=3)
    assert not ok and "<" in why
    # Past the regular interval it runs without asking GitHub.
    ok, why, calls = _decide_planner(ready=5, prev_hours_ago=11)
    assert ok and not why.startswith("queue low") and not calls


def test_planner_falls_back_to_interval_when_ready_lookup_fails():
    ok, why, calls = _decide_planner(ready=None, prev_hours_ago=3)
    assert not ok and "<" in why and calls


def test_queue_floor_applies_to_planner_only():
    from datetime import timedelta
    sr = _should_run()
    ok, _ = sr.decide("researcher", False, now=NOW, read_lock=lambda r: None,
                      last_run=lambda r: NOW - timedelta(hours=3), ready_count=lambda: 0,
                      main_updated_at=lambda: NOW)
    assert not ok


def test_should_run_lock_race_lets_only_one_run():
    sr = _should_run()
    locks = {}

    def decide(role, sweep):
        return sr.decide(role, sweep, now=NOW, read_lock=locks.get, last_run=lambda r: None)

    def lost_race(path, content, msg):
        locks["builder"] = _lock_at(0)  # another run pushed its lock first
        return False

    ok, why = sr.acquire("builder", False, decide_fn=decide, commit=lost_race, fetch=lambda: None)
    assert not ok and why.startswith("running")

    locks.clear()
    written = []
    ok, _ = sr.acquire("builder", False, decide_fn=decide, fetch=lambda: None,
                       commit=lambda p, c, m: written.append((p, c)) or True)
    assert ok and written[0][0] == "locks/builder.json"
    assert {"run_id", "started"} <= set(__import__("json").loads(written[0][1]))


def test_every_workflow_is_valid_yaml_with_triggers_and_jobs():
    import yaml

    bad = []
    for wf in sorted((ROOT / ".github" / "workflows").glob("*.y*ml")):
        try:
            doc = yaml.safe_load(wf.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            bad.append(f"{wf.name}: YAML parse error ({e.problem}, line {e.problem_mark.line + 1}) - quote scalars containing ': '")
            continue
        # PyYAML reads the bare key `on` as boolean True (YAML 1.1)
        if not isinstance(doc, dict) or not ({"on", True} & doc.keys()):
            bad.append(f"{wf.name}: missing top-level `on:` trigger")
        elif not isinstance(doc.get("jobs"), dict) or not doc["jobs"]:
            bad.append(f"{wf.name}: missing or empty `jobs:`")
    assert not bad, "\n".join(bad)


def test_two_reviewers_split_prs_by_parity():
    import json
    sched = json.loads((ROOT / "harness" / "schedule.json").read_text())
    assert sched["reviewer-b"]["instructions"] == sched["reviewer"]["instructions"] == "reviewer"
    assert {k: v for k, v in sched["reviewer-b"].items()} == {k: v for k, v in sched["reviewer"].items()}
    text = (ROOT / "harness" / "routines" / "reviewer.md").read_text(encoding="utf-8")
    assert "홀수" in text and "짝수" in text and "reviewer-b" in text


def test_reviewer_locks_are_separate_per_role():
    sr = _should_run()
    seen = []
    sr.decide("reviewer-b", True, now=NOW, read_lock=lambda r: seen.append(r) or None, last_run=lambda r: None)
    sr.decide("reviewer", True, now=NOW, read_lock=lambda r: seen.append(r) or None, last_run=lambda r: None)
    assert seen == ["reviewer-b", "reviewer"]  # each role reads ops:locks/<role>.json
    # A held reviewer lock does not block reviewer-b.
    held = {"role": "reviewer", "run_id": "x", "started": NOW.isoformat()}
    ok, _ = sr.decide("reviewer-b", True, now=NOW, read_lock=lambda r: held if r == "reviewer" else None,
                      last_run=lambda r: None)
    assert ok
