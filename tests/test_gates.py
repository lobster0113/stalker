import importlib.util

from referee import gates


def test_full_runs_tests_across_workers_and_keeps_every_check(monkeypatch):
    calls = []
    monkeypatch.setattr(gates, "_run", lambda name, argv: calls.append((name, argv)) or True)
    assert gates.full()
    argv = dict(calls)["tests"]
    assert argv[argv.index("-n") + 1] == "auto"
    assert "-m" not in argv[3:], "full gate must not deselect tests"
    assert [n for n, _ in calls] == ["compile", "tests"] + [n for n, _ in gates.FULL_CHECKS]
    assert ("gate_r", [gates.PY, "-m", "referee.gate_r", "--full"]) in calls
    assert importlib.util.find_spec("xdist"), 'pytest-xdist missing: python -m pip install -e ".[dev]"'


def test_summary_names_the_slowest_step(monkeypatch):
    monkeypatch.setattr(gates, "TIMINGS", {"compile": 0.2, "tests": 410.0, "gate_r": 520.4})
    assert gates.summary("full", True) == "gates full: PASS (compile=0s tests=410s gate_r=520s) slowest=gate_r"
    monkeypatch.setattr(gates, "TIMINGS", {})
    assert gates.summary("quick", False) == "gates quick: FAIL ()"
