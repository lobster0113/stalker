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


def test_quick_runs_fast_tests_across_workers_and_stops_at_first_failure(monkeypatch):
    calls = []
    monkeypatch.setattr(gates, "_run", lambda name, argv: calls.append((name, argv)) or True)
    assert gates.quick()
    argv = dict(calls)["tests"]
    assert argv[argv.index("-m", 3) + 1] == "not slow"
    assert "-x" in argv
    assert argv[-len(gates.FULL_TEST_WORKERS):] == gates.FULL_TEST_WORKERS


def test_quick_falls_back_to_serial_without_xdist():
    serial = gates._quick_argv(has_xdist=False)
    assert "-n" not in serial and "--dist" not in serial
    assert serial[serial.index("-m", 3) + 1] == "not slow" and "-x" in serial
    assert gates._quick_argv(has_xdist=True) == serial + gates.FULL_TEST_WORKERS


def test_quick_uses_serial_argv_when_xdist_is_not_importable(monkeypatch):
    calls = []
    monkeypatch.setattr(gates, "_run", lambda name, argv: calls.append((name, argv)) or True)
    real = importlib.util.find_spec
    monkeypatch.setattr(gates.importlib.util, "find_spec", lambda n, *a: None if n == "xdist" else real(n, *a))
    assert gates.quick()
    assert dict(calls)["tests"] == gates._quick_argv(has_xdist=False)


def test_xdist_maxfail_stops_after_first_failure(tmp_path):
    # Evidence for keeping `-x` under xdist (#811): after the first failure the controller stops scheduling, so the
    # third test never runs (tests already running on other workers still finish). xdist exits 2 (interrupted), not 1.
    import subprocess

    import pytest

    if not importlib.util.find_spec("xdist"):
        pytest.skip("pytest-xdist not installed")
    (tmp_path / "test_x.py").write_text(
        "import time\n"
        "def test_a():\n    assert False\n"
        "def test_b():\n    time.sleep(1)\n    assert False\n"
        "def test_c():\n    time.sleep(1)\n    assert False\n", encoding="utf-8")
    r = subprocess.run([gates.PY, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", "-n", "2", "--dist", "worksteal",
                        str(tmp_path)], capture_output=True, text=True, encoding="utf-8", cwd=tmp_path)
    assert r.returncode != 0
    assert "stopping after 1 failures" in r.stdout and "3 failed" not in r.stdout, r.stdout
