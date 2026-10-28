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


def test_parts_split_the_full_gate_without_dropping_anything(monkeypatch):
    seen = {}
    for part in ("all", "tests", "checks"):
        calls = []
        monkeypatch.setattr(gates, "_run", lambda name, argv, calls=calls: calls.append(name) or True)
        assert gates.full(part)
        seen[part] = calls
    checks = [n for n, _ in gates.FULL_CHECKS]
    assert seen["all"] == ["compile", "tests"] + checks
    assert seen["tests"] == ["compile", "tests"] and seen["checks"] == ["compile"] + checks
    assert set(seen["tests"]) | set(seen["checks"]) == set(seen["all"])


def test_unknown_part_is_rejected():
    import pytest

    with pytest.raises(SystemExit, match="part"):
        gates.full("bogus")


def test_cli_arguments_fail_with_a_short_hint():
    import pytest

    assert gates._parse(["gates", "full", "--part", "tests"]) == ("full", "tests")
    assert gates._parse(["gates"]) == ("quick", "all")
    for argv, msg in ((["gates", "full", "--part"], "needs a value"), (["gates", "full", "--part", "x"], "unknown part"),
                      (["gates", "quick", "--part", "tests"], "full only"), (["gates", "slow"], "unknown mode")):
        with pytest.raises(SystemExit, match=msg):
            gates._parse(argv)
