"""CI guard: fail a PR that touches protected/harness paths without the matching label.

Usage: python -m referee.guard --base <sha> --labels "a,b,c"
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_rules(path: Path = ROOT / "referee" / "PROTECTED_PATHS") -> dict[str, list[str]]:
    rules: dict[str, list[str]] = {}
    label = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            label = line[1:-1]
            rules[label] = []
        elif label:
            rules[label].append(line)
    return rules


def violations(changed: list[str], labels: set[str], rules: dict[str, list[str]]) -> list[str]:
    out = []
    for f in changed:
        for label, prefixes in rules.items():
            if any(f == p or f.startswith(p) for p in prefixes) and label not in labels:
                out.append(f"{f}: requires label '{label}'")
    return out


def changed_files(base: str) -> list[str]:
    r = subprocess.run(["git", "diff", "--name-only", f"{base}...HEAD"], cwd=ROOT,
                       capture_output=True, text=True, check=True)
    return [x for x in r.stdout.splitlines() if x]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--labels", default="")
    a = ap.parse_args()
    labels = {x.strip() for x in a.labels.split(",") if x.strip()}
    v = violations(changed_files(a.base), labels, load_rules())
    if v:
        print("referee-guard FAILED. Protected paths changed without permission label:")
        print("\n".join("  " + x for x in v))
        print("Fix: revert these files, or work from an issue that carries the label "
              "(only Planner/Auditor may grant it; see harness/PROTOCOL.md §2).")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
