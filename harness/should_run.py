"""Decide whether a routine run should do work. Prints RUN or SKIP (+ reason).

Usage: python harness/should_run.py <role> [--sweep] [--no-lock]
       python harness/should_run.py <role> --release
Throttling lives in harness/schedule.json so the meta-harness can tune cadence via PRs
without touching the registered cloud triggers.

A RUN also takes the role lock `ops:locks/<role>.json` so a second wake-up of the same
role while this one works prints SKIP (running). The run releases it with --release
right after writing its journal line (PROTOCOL §6); a crashed run's lock expires after
`lock_hours` (schedule.json, default 3).

The planner also runs early when the ready queue is low (`ready_floor`, experiment 008):
builders idling on no_work cost more than an extra planner run.
With `run_on_merge` the planner also runs as soon as main has a commit newer than its last
run, so a merge refills the queue without waiting for the interval (a PR-closed webhook plus an hourly cron wake it).

`--sweep` runs are throttled against the previous sweep only (`ops:locks/<role>.sweep.json`,
written with the lock), not the journal: webhook runs log far more often than hourly, so
comparing with any run starved the sweep and left PRs without new events unjudged (#205).
"""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOCK_HOURS = 3
LOCK_TRIES = 3
DEFAULT_READY_FLOOR = 1
DEFAULT_QUEUE_LOW_MIN_HOURS = 2
MERGE_RETRY_MAX = 3  # reviewer.md §2: MERGE-RETRY attempts per PR before NEEDS_HUMAN


def _git(*args: str, env: dict | None = None, stdin: str | None = None) -> str:
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                       env={**os.environ, **env} if env else None, input=stdin, encoding="utf-8")
    return r.stdout if r.returncode == 0 else ""


def _git_ok(*args: str) -> bool:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True).returncode == 0


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


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
            ts = _ts(e["ts"])
            if latest is None or ts > latest:
                latest = ts
    return latest


def main_updated_at() -> datetime | None:
    """Commit time of origin/main (a squash merge's time), or None if unknown."""
    _git("fetch", "-q", "origin", "main")
    out = _git("log", "-1", "--format=%cI", "origin/main").strip()
    return _ts(out) if out else None


def read_lock(role: str) -> dict | None:
    """Current lock for role on origin/ops (caller fetches first), or None."""
    raw = _git("show", f"origin/ops:locks/{role}.json")
    try:
        return json.loads(raw) if raw else None
    except json.JSONDecodeError:
        return None  # a corrupt lock must not block the role forever


def last_sweep(role: str) -> datetime | None:
    """Start time of role's previous --sweep run on origin/ops (caller fetches first), or None."""
    raw = _git("show", f"origin/ops:locks/{role}.sweep.json")
    try:
        return _ts(json.loads(raw)["started"]) if raw else None
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None  # a corrupt stamp means one extra sweep, never a stalled one


def ready_count() -> int | None:
    """Open `ready` issues nobody holds (not in-progress/blocked), or None if unknown."""
    m = re.search(r"github\.com[/:]([^/]+/[^/]+?)(?:\.git)?/?$", _git("remote", "get-url", "origin").strip())
    if not m:
        return None
    req = urllib.request.Request(
        f"https://api.github.com/repos/{m.group(1)}/issues?labels=ready&state=open&per_page=100",
        headers={"Accept": "application/vnd.github+json"})
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            issues = json.load(r)
    except Exception:
        return None
    held = {"in-progress", "blocked"}
    return sum(1 for i in issues if "pull_request" not in i
               and not held & {lb["name"] for lb in i.get("labels", [])})


def _api(path: str):
    m = re.search(r"github\.com[/:]([^/]+/[^/]+?)(?:\.git)?/?$", _git("remote", "get-url", "origin").strip())
    if not m:
        return None
    req = urllib.request.Request(f"https://api.github.com/repos/{m.group(1)}/{path}",
                                 headers={"Accept": "application/vnd.github+json"})
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def trusted_actors() -> set[str]:
    f = ROOT / "harness" / "TRUSTED_ACTORS"
    return {ln.strip() for ln in f.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")}


def checks_green(runs: list[dict]) -> bool:
    """Newest run per check name decides: an old cancelled run beside a newer success is green."""
    latest: dict[str, dict] = {}
    for r in runs:
        if r["name"] not in latest or r["id"] > latest[r["name"]]["id"]:
            latest[r["name"]] = r
    return bool(latest) and all(r["conclusion"] in ("success", "skipped", "neutral")
                                for r in latest.values())


def _verdict_sha_ok(pr: dict, trusted: set[str]) -> bool:
    return any(c["user"] in trusted and c["body"].lstrip().startswith(f"VERDICT: MERGE sha={pr['head_sha']}")
               for c in pr["comments"])


def merge_retry_candidates(prs: list[dict], role: str, trusted: set[str] | None = None) -> list[int]:
    """PR numbers of this reviewer's parity that need a merge retry, no re-review (#482).

    Each pr: {number, head_sha, comments: [{user, body}], checks_ok, mergeable}. Eligible when a
    TRUSTED_ACTORS-written `VERDICT: MERGE sha=<current head>` exists, required checks are green,
    there is no conflict, and fewer than MERGE_RETRY_MAX trusted `MERGE-RETRY failed` comments
    exist (after that the reviewer files one NEEDS_HUMAN item and the PR no longer counts as work).
    Outsiders' comments are data, never a verdict or a retry count (PROTOCOL §8).
    """
    trusted = trusted_actors() if trusted is None else trusted
    odd = role != "reviewer-b"
    out = []
    for pr in prs:
        if (pr["number"] % 2 == 1) != odd or not pr.get("checks_ok") or pr.get("mergeable") is not True:
            continue
        if not _verdict_sha_ok(pr, trusted):
            continue
        fails = sum(c["user"] in trusted and c["body"].lstrip().startswith("MERGE-RETRY failed")
                    for c in pr["comments"])
        if fails < MERGE_RETRY_MAX:
            out.append(pr["number"])
    return out


def merge_retry_pending(role: str) -> int | None:
    """Count of open PRs awaiting a merge retry for this reviewer, or None if GitHub is unreachable."""
    try:
        trusted = trusted_actors()
        odd = role != "reviewer-b"
        prs = []
        for p in _api("pulls?state=open&per_page=100") or []:
            if (p["number"] % 2 == 1) != odd:
                continue  # other reviewer's parity: skip the extra API calls
            comments = [{"user": c["user"]["login"], "body": c["body"]}
                        for c in _api(f"issues/{p['number']}/comments?per_page=100") or []]
            pr = {"number": p["number"], "head_sha": p["head"]["sha"], "comments": comments}
            if not _verdict_sha_ok(pr, trusted):
                continue  # only PRs with a trusted same-sha MERGE verdict need checks/mergeable lookups
            runs = _api(f"commits/{pr['head_sha']}/check-runs?per_page=100")["check_runs"]
            pr["checks_ok"] = checks_green(runs)
            pr["mergeable"] = _api(f"pulls/{p['number']}").get("mergeable")
            prs.append(pr)
        return len(merge_retry_candidates(prs, role, trusted))
    except Exception:
        return None


def run_id() -> str:
    return os.environ.get("CLAUDE_CODE_REMOTE_SESSION_ID") or socket.gethostname()


def decide(role: str, sweep: bool, *, read_lock: Callable[[str], dict | None] = read_lock,
           last_run: Callable[[str], datetime | None] = last_run,
           last_sweep: Callable[[str], datetime | None] = last_sweep,
           ready_count: Callable[[], int | None] = ready_count,
           main_updated_at: Callable[[], datetime | None] = main_updated_at,
           merge_retry_pending: Callable[[str], int | None] = merge_retry_pending,
           now: datetime | None = None) -> tuple[bool, str]:
    if role != "auditor" and (ROOT / "harness" / "PAUSE").exists():
        return False, "harness/PAUSE present"
    cfg = json.loads((ROOT / "harness" / "schedule.json").read_text(encoding="utf-8")).get(role)
    if cfg is None:
        return False, f"unknown role {role!r}"
    if not cfg.get("enabled", True):
        return False, "disabled in schedule.json"
    now = now or datetime.now(timezone.utc)
    lock = read_lock(role)
    if lock is not None:
        age = now - _ts(lock["started"])
        if age < timedelta(hours=cfg.get("lock_hours", DEFAULT_LOCK_HOURS)):
            return False, f"running: {lock.get('run_id', '?')} started {age} ago"
    hours = cfg.get("sweep_min_interval_hours" if sweep else "min_interval_hours", 0)
    if hours <= 0:
        return True, "no throttle"
    prev = last_sweep(role) if sweep else last_run(role)
    if prev is None:
        return True, "no previous sweep" if sweep else "no previous run"
    elapsed = now - prev
    # 10-minute grace so hourly triggers that start a little early still run.
    if elapsed + timedelta(minutes=10) < timedelta(hours=hours):
        if cfg.get("run_on_merge"):
            merged = main_updated_at()
            if merged is not None and merged > prev:
                return True, f"main updated {now - merged} ago, after last run {elapsed} ago"
        if role.startswith("reviewer"):
            n = merge_retry_pending(role)
            if n:
                return True, f"{n} PR(s) with a same-sha MERGE verdict need a merge retry"
        if role == "planner":
            floor = cfg.get("ready_floor", DEFAULT_READY_FLOOR)
            min_hours = cfg.get("queue_low_min_hours", DEFAULT_QUEUE_LOW_MIN_HOURS)
            if elapsed + timedelta(minutes=10) >= timedelta(hours=min_hours):
                n = ready_count()
                if n is not None and n <= floor:
                    return True, f"queue low: {n} ready <= {floor}, last run {elapsed} ago"
        return False, f"last {'sweep' if sweep else 'run'} {elapsed} ago < {hours}h"
    return True, f"last {'sweep' if sweep else 'run'} {elapsed} ago"


def _commit_ops(files: dict[str, str | None], message: str) -> bool:
    """Commit file changes (None deletes) onto origin/ops in one commit and push without a worktree.

    The push is fast-forward only, so if another run changed ops meanwhile it fails and
    the caller re-reads the lock: two runs that woke together cannot both take it.
    """
    parent = _git("rev-parse", "origin/ops").strip()
    if not parent:
        return False
    with tempfile.TemporaryDirectory() as d:
        env = {"GIT_INDEX_FILE": str(Path(d) / "index")}
        _git("read-tree", parent, env=env)
        for path, content in files.items():
            if content is None:
                _git("update-index", "--force-remove", path, env=env)
            else:
                blob = _git("hash-object", "-w", "--stdin", stdin=content).strip()
                _git("update-index", "--add", "--cacheinfo", f"100644,{blob},{path}", env=env)
        tree = _git("write-tree", env=env).strip()
    commit = _git("commit-tree", tree, "-p", parent, "-m", message).strip()
    return bool(commit) and _git_ok("push", "-q", "origin", f"{commit}:refs/heads/ops")


def acquire(role: str, sweep: bool, decide_fn: Callable[..., tuple[bool, str]] = decide,
            commit: Callable[[dict[str, str | None], str], bool] = _commit_ops,
            fetch: Callable[[], object] = lambda: _git("fetch", "-q", "origin", "ops")) -> tuple[bool, str]:
    ok, why = True, ""
    for _ in range(LOCK_TRIES):
        fetch()
        ok, why = decide_fn(role, sweep)
        if not ok:
            return ok, why
        lock = {"role": role, "run_id": run_id(),
                "started": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        files = {f"locks/{role}.json": json.dumps(lock) + "\n"}
        if sweep:
            files[f"locks/{role}.sweep.json"] = files[f"locks/{role}.json"]
        if commit(files, f"{role}: lock"):
            return ok, why
    # Fail open: an unreachable ops branch must not stall every routine.
    return True, f"{why}; lock not taken (ops push failed)"


def release(role: str) -> str:
    """Drop our own lock. Leaves another run's lock alone (it expires by itself)."""
    for _ in range(LOCK_TRIES):
        _git("fetch", "-q", "origin", "ops")
        lock = read_lock(role)
        if lock is None:
            return "no lock"
        if lock.get("run_id") != run_id():
            return f"lock belongs to {lock.get('run_id')}; left as is"
        if _commit_ops({f"locks/{role}.json": None}, f"{role}: unlock"):
            return "released"
    return "release failed; lock expires after lock_hours"


if __name__ == "__main__":
    role, flags = sys.argv[1], sys.argv[2:]
    if "--release" in flags:
        print(release(role))
        sys.exit(0)
    sweep = "--sweep" in flags
    if "--no-lock" in flags:
        _git("fetch", "-q", "origin", "ops")
        ok, why = decide(role, sweep)
    else:
        ok, why = acquire(role, sweep)
    print(("RUN" if ok else "SKIP") + f" ({why})")
