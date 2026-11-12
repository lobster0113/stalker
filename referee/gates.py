"""Quality gates. `python -m referee.gates quick|full [--part tests|checks]`.

G0 (quick): byte-compile + fast tests (parallel like full when pytest-xdist is installed).
G1 (full):  all tests incl. slow/property tests + registered determinism checks.
G2 (full):  registered strength evaluations, when available.
Output policy: one progress line per step on stderr (`[gate] tests ok 312s`) so a long run is
visibly alive, a one-line summary on stdout, and short actionable text on failure.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable

# Extra full-gate checks: (name, argv). Added via referee-change PRs as the product grows.
FULL_CHECKS: list[tuple[str, list[str]]] = [
    ("gate_r", [PY, "-m", "referee.gate_r", "--full"]),
    ("gate_r_edge", [PY, "-m", "referee.gate_r.edge"]),
    ("gate_r_e3", [PY, "-m", "referee.gate_r.e3_suite"]),
    ("gate_l", [PY, "-m", "referee.gate_l"]),
    ("gate_t", [PY, "-m", "referee.gate_t"]),
    ("gate_s", [PY, "-m", "referee.gate_s", "--check"]),
]


# Serial, the full test run alone took 21 of CI's 30 minutes (#167); a few slow tests run 1-5 minutes each,
# so worksteal keeps one long test from leaving the other workers idle.
FULL_TEST_WORKERS = ["-n", "auto", "--dist", "worksteal"]

TIMINGS: dict[str, float] = {}


def summary(mode: str, passed: bool) -> str:
    steps = " ".join(f"{k}={v:.0f}s" for k, v in TIMINGS.items())
    slowest = f" slowest={max(TIMINGS, key=TIMINGS.get)}" if TIMINGS else ""
    return f"gates {mode}: {'PASS' if passed else 'FAIL'} ({steps}){slowest}"


def _run(name: str, argv: list[str]) -> bool:
    print(f"[gate] {name} ...", file=sys.stderr, flush=True)
    t0 = time.monotonic()
    r = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True)
    TIMINGS[name] = time.monotonic() - t0
    print(f"[gate] {name} {'ok' if r.returncode == 0 else 'FAIL'} {TIMINGS[name]:.0f}s", file=sys.stderr, flush=True)
    if r.returncode == 0:
        return True
    tail = (r.stdout + r.stderr).strip().splitlines()[-40:]
    print(f"[FAIL] {name}: {' '.join(argv[1:])}")
    print("\n".join("  " + x for x in tail))
    return False


def _quick_argv(has_xdist: bool) -> list[str]:
    # Serial quick took 500-1700s locally (#800); spreading it like full is the cheap win (#811).
    # Under xdist `-x` still means maxfail=1: the controller stops scheduling after the first failure.
    # Without the plugin `-n` is an unknown flag, so fall back to serial instead of failing the gate.
    argv = [PY, "-m", "pytest", "-q", "-x", "-m", "not slow", "--no-header", "-p", "no:cacheprovider"]
    return argv + FULL_TEST_WORKERS if has_xdist else argv


def quick() -> bool:
    ok = _run("compile", [PY, "-m", "compileall", "-q", "stalker", "referee", "harness"])
    has_xdist = importlib.util.find_spec("xdist") is not None
    if not has_xdist:
        print('[gate] pytest-xdist missing, quick tests run serially: python -m pip install -e ".[dev]"',
              file=sys.stderr, flush=True)
    ok &= _run("tests", _quick_argv(has_xdist))
    return ok


def full(part: str = "all") -> bool:
    """`part` lets CI run the test suite and the registered checks as parallel jobs (#203)."""
    if part not in ("all", "tests", "checks"):
        raise SystemExit(f"unknown part {part!r}; use all, tests or checks")
    ok = _run("compile", [PY, "-m", "compileall", "-q", "stalker", "referee", "harness"])
    if part in ("all", "tests"):
        ok &= _run("tests", [PY, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider", *FULL_TEST_WORKERS])
    if part in ("all", "checks"):
        for name, argv in FULL_CHECKS:
            ok &= _run(name, argv)
    return ok


def _parse(argv: list[str]) -> tuple[str, str]:
    mode = argv[1] if len(argv) > 1 else "quick"
    if mode not in ("quick", "full"):
        raise SystemExit(f"unknown mode {mode!r}; use quick or full")
    part = "all"
    if "--part" in argv:
        i = argv.index("--part")
        if mode != "full":
            raise SystemExit("--part works with full only: python -m referee.gates full --part tests|checks")
        if i + 1 >= len(argv):
            raise SystemExit("--part needs a value; use all, tests or checks")
        part = argv[i + 1]
        if part not in ("all", "tests", "checks"):
            raise SystemExit(f"unknown part {part!r}; use all, tests or checks")
    return mode, part


if __name__ == "__main__":
    mode, part = _parse(sys.argv)
    passed = quick() if mode == "quick" else full(part)
    print(summary(mode if part == "all" else f"{mode}:{part}", passed))
    sys.exit(0 if passed else 1)
