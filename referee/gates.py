"""Quality gates. `python -m referee.gates quick|full`.

G0 (quick): byte-compile + fast tests.
G1 (full):  all tests incl. slow/property tests + registered determinism checks.
G2 (full):  registered strength evaluations, when available.
Output policy: silent on success, short actionable text on failure.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable

# Extra full-gate checks: (name, argv). Added via referee-change PRs as the product grows.
FULL_CHECKS: list[tuple[str, list[str]]] = [
    ("gate_r", [PY, "-m", "referee.gate_r", "--full"]),
    ("gate_l", [PY, "-m", "referee.gate_l"]),
]


def _run(name: str, argv: list[str]) -> bool:
    r = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True)
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
    ok &= _run("tests", [PY, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider"])
    for name, argv in FULL_CHECKS:
        ok &= _run(name, argv)
    return ok


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "quick"
    passed = {"quick": quick, "full": full}[mode]()
    print(f"gates {mode}: {'PASS' if passed else 'FAIL'}")
    sys.exit(0 if passed else 1)
