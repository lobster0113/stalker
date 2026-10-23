"""Decide whether a routine run should do work. Prints RUN or SKIP (+ reason).

Usage: python harness/should_run.py <role> [--sweep]
Throttling lives in harness/schedule.json so the meta-harness can tune cadence via PRs
without touching the registered cloud triggers.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _git(*args: str) -> str:
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""


def last_run(role: str) -> datetime | None:
    """Latest journal timestamp for role (ignoring 'skipped'/'paused'), from origin/ops."""
    _git("fetch", "-q", "origin", "ops")
    now = datetime.now(timezone.utc)
    months = {now.strftime("%Y-%m"), (now.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")}
    latest = None
    for m in months:
        for line in _git("show", f"origin/ops:journal/{m}.jsonl").splitlines():
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get("role") != role or e.get("outcome") in ("skipped", "paused"):
                continue
            ts = datetime.fromisoformat(e["ts"].replace("Z", "+00:00"))
            if latest is None or ts > latest:
                latest = ts
    return latest


def decide(role: str, sweep: bool) -> tuple[bool, str]:
    if role != "auditor" and (ROOT / "harness" / "PAUSE").exists():
        return False, "harness/PAUSE present"
    cfg = json.loads((ROOT / "harness" / "schedule.json").read_text()).get(role)
    if cfg is None:
        return False, f"unknown role {role!r}"
    if not cfg.get("enabled", True):
        return False, "disabled in schedule.json"
    hours = cfg.get("sweep_min_interval_hours" if sweep else "min_interval_hours", 0)
    if hours <= 0:
        return True, "no throttle"
    prev = last_run(role)
    if prev is None:
        return True, "no previous run"
    elapsed = datetime.now(timezone.utc) - prev
    # 10-minute grace so hourly triggers that start a little early still run.
    if elapsed + timedelta(minutes=10) < timedelta(hours=hours):
        return False, f"last run {elapsed} ago < {hours}h"
    return True, f"last run {elapsed} ago"


if __name__ == "__main__":
    ok, why = decide(sys.argv[1], "--sweep" in sys.argv[2:])
    print(("RUN" if ok else "SKIP") + f" ({why})")
