"""Quality gates. `python -m referee.gates quick|full`.

G0 (quick): byte-compile + fast tests.
G1 (full):  all tests incl. slow/property tests + registered determinism checks.
G2 (full):  registered strength evaluations, when available.
Output policy: one progress line per step on stderr (`[gate] tests ok 312s`) so a long run is
visibly alive, a one-line summary on stdout, and short actionable text on failure.
"""
from __future__ import annotations

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
    ("gate_l", [PY, "-m", "referee.gate_l"]),
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


def quick() -> bool:
    ok = _run("compile", [PY, "-m", "compileall", "-q", "stalker", "referee", "harness"])
    ok &= _run("tests", [PY, "-m", "pytest", "-q", "-x", "-m", "not slow", "--no-header", "-p", "no:cacheprovider"])
    return ok


def full() -> bool:
    ok = _run("compile", [PY, "-m", "compileall", "-q", "stalker", "referee", "harness"])
    ok &= _run("tests", [PY, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider", *FULL_TEST_WORKERS])
    for name, argv in FULL_CHECKS:
        ok &= _run(name, argv)
    return ok


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "quick"
    passed = {"quick": quick, "full": full}[mode]()
    print(summary(mode, passed))
    sys.exit(0 if passed else 1)
