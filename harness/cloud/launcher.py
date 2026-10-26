"""Budget-guarded cloud launcher: the only path by which agents spend money (ADR 0004 §5, #20).

Runs only inside `.github/workflows/cloud.yml`; the RunPod key lives in the `RUNPOD_API_KEY`
secret and agents never see it. Agents submit a job spec `jobs/<name>.yaml` by PR and
dispatch the workflow.

Usage:
  python harness/cloud/launcher.py check                       # balance query, costs nothing
  python harness/cloud/launcher.py run jobs/x.yaml --ledger L [--dry-run] [--run-id ID] [--sync-cmd CMD]
  python harness/cloud/launcher.py reap --ledger L [--job jobs/x.yaml --run-id ID --force]

Budget rule: a job runs only if month_total + worst_case(job) <= monthly cap
(`harness/budget.json`). month_total counts finished jobs at their actual cost and open
ones (no end entry yet) at their reserved worst case, so a crashed run still counts.
Pods are always terminated: on completion, on deadline, on error (finally), by the
workflow's `if: always()` reap step, and by the daily orphan reap.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent.parent
BUDGET_FILE = ROOT / "harness" / "budget.json"
POD_PREFIX = "stalker-"
REAP_GRACE_MIN = 10
# GitHub-hosted runners stop any job at 360 min; keep the launcher's own deadline, terminate
# and ledger push well inside that, or the runner limit kills the job before its finally runs.
MAX_JOB_MINUTES = 330
REST_URL = "https://rest.runpod.io/v1"
GRAPHQL_URL = "https://api.runpod.io/graphql"


class LauncherError(Exception):
    pass


class BudgetExceeded(LauncherError):
    pass


# ---------- job spec ----------

SPEC_FIELDS = {"name", "image", "command", "gpu_type", "gpu_count", "cpu_flavor", "vcpu",
               "max_minutes", "hourly_usd", "est_cost_usd", "disk_gb", "cloud"}
REQUIRED = {"name", "image", "command", "max_minutes", "hourly_usd"}


@dataclass(frozen=True)
class Job:
    name: str
    image: str
    command: str
    max_minutes: int
    hourly_usd: float
    est_cost_usd: float = 0.0
    gpu_type: str | None = None
    gpu_count: int = 1
    cpu_flavor: str | None = None
    vcpu: int = 2
    disk_gb: int = 20
    cloud: str = "COMMUNITY"

    @property
    def worst_case_usd(self) -> float:
        # never trust a declared estimate below what max time at the declared rate costs
        return round(max(self.est_cost_usd, self.hourly_usd * self.max_minutes / 60), 4)


def _scalar(raw: str):
    v = raw.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    if re.fullmatch(r"-?\d+", v):
        return int(v)
    if re.fullmatch(r"-?\d+\.\d*", v):
        return float(v)
    return v


def parse_spec(text: str, source: str = "job") -> Job:
    """Flat `key: value` YAML subset (no nesting, lists or multi-line), so no YAML dependency."""
    data: dict = {}
    for n, line in enumerate(text.splitlines(), 1):
        s = line.split(" #", 1)[0].rstrip() if not line.lstrip().startswith("#") else ""
        if not s.strip():
            continue
        m = re.fullmatch(r"([a-z_]+):\s*(.*)", s)
        if not m or line[0].isspace():
            raise LauncherError(f"{source}:{n}: expected flat 'key: value' (no nesting) — got {line!r}")
        key, val = m.groups()
        if key not in SPEC_FIELDS:
            raise LauncherError(f"{source}:{n}: unknown key {key!r}; allowed: {', '.join(sorted(SPEC_FIELDS))}")
        if key in data:
            raise LauncherError(f"{source}:{n}: duplicate key {key!r}")
        data[key] = _scalar(val)
    missing = REQUIRED - data.keys()
    if missing:
        raise LauncherError(f"{source}: missing required keys: {', '.join(sorted(missing))}")
    if bool(data.get("gpu_type")) == bool(data.get("cpu_flavor")):
        raise LauncherError(f"{source}: set exactly one of gpu_type or cpu_flavor")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,40}", str(data["name"])):
        raise LauncherError(f"{source}: name must be lowercase [a-z0-9-], ≤41 chars")
    for k in ("max_minutes", "gpu_count", "vcpu", "disk_gb"):
        if k in data and (not isinstance(data[k], int) or data[k] <= 0):
            raise LauncherError(f"{source}: {k} must be a positive integer")
    for k in ("hourly_usd", "est_cost_usd"):
        if k in data and (not isinstance(data[k], (int, float)) or data[k] < 0):
            raise LauncherError(f"{source}: {k} must be a non-negative number")
    if data["max_minutes"] > MAX_JOB_MINUTES:
        raise LauncherError(f"{source}: max_minutes > {MAX_JOB_MINUTES} (GitHub runner job limit 360); "
                            "split the job into resumable chunks")
    if data.get("cloud", "COMMUNITY") not in ("COMMUNITY", "SECURE"):
        raise LauncherError(f"{source}: cloud must be COMMUNITY or SECURE")
    data["hourly_usd"] = float(data["hourly_usd"])
    data["est_cost_usd"] = float(data.get("est_cost_usd", 0.0))
    return Job(**data)


def load_spec(path: Path) -> Job:
    rel = path.resolve().relative_to(ROOT) if path.resolve().is_relative_to(ROOT) else path
    if not re.fullmatch(r"jobs/[^/]+\.yaml", str(rel)):
        raise LauncherError(f"{path}: job specs must be jobs/<name>.yaml in this repo")
    return parse_spec(path.read_text(), str(rel))


# ---------- budget ledger ----------

def load_cap(path: Path = BUDGET_FILE) -> float:
    cap = json.loads(path.read_text())["monthly_cap_usd"]
    if not isinstance(cap, (int, float)) or cap < 0:
        raise LauncherError(f"{path}: monthly_cap_usd must be a non-negative number")
    return float(cap)


def read_ledger(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def append_ledger(path: Path, entry: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def open_entries(entries: list[dict]) -> dict[str, dict]:
    """start entries without a matching end, keyed by pod_id."""
    starts = {e["pod_id"]: e for e in entries if e["event"] == "start"}
    for e in entries:
        if e["event"] == "end":
            starts.pop(e["pod_id"], None)
    return starts


def month_total(entries: list[dict], month: str) -> float:
    total = 0.0
    for e in entries:
        if e["month"] != month:
            continue
        if e["event"] == "end":
            total += e["actual_usd"]
    for e in open_entries(entries).values():
        if e["month"] == month:
            total += e["reserved_usd"]
    return round(total, 4)


def check_budget(job: Job, entries: list[dict], cap: float, month: str) -> float:
    spent = month_total(entries, month)
    if spent + job.worst_case_usd > cap:
        raise BudgetExceeded(
            f"budget: {month} spent/reserved ${spent:.2f} + job worst case ${job.worst_case_usd:.2f} "
            f"> cap ${cap:.2f} (harness/budget.json). Shrink max_minutes/hourly_usd or wait for next month.")
    return spent


# ---------- RunPod API ----------

Transport = Callable[[str, str, dict | None], dict | list | None]


def http_transport(api_key: str) -> Transport:
    def call(method: str, url: str, body: dict | None):
        req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise LauncherError(f"RunPod {method} {url}: HTTP {e.code} {e.read()[:300]!r}") from e
        return json.loads(raw) if raw.strip() else {}
    return call


class RunPod:
    def __init__(self, transport: Transport):
        self.t = transport

    def balance(self) -> float:
        r = self.t("POST", GRAPHQL_URL, {"query": "query { myself { clientBalance } }"})
        try:
            return float(r["data"]["myself"]["clientBalance"])
        except (TypeError, KeyError) as e:
            raise LauncherError(f"RunPod balance query: unexpected response {str(r)[:300]}") from e

    def create(self, job: Job, pod_name: str) -> dict:
        body = {"name": pod_name, "imageName": job.image, "cloudType": job.cloud,
                "containerDiskInGb": job.disk_gb, "dockerStartCmd": ["bash", "-lc", job.command]}
        if job.gpu_type:
            body |= {"computeType": "GPU", "gpuTypeIds": [job.gpu_type], "gpuCount": job.gpu_count}
        else:
            body |= {"computeType": "CPU", "cpuFlavorIds": [job.cpu_flavor], "vcpuCount": job.vcpu}
        pod = self.t("POST", f"{REST_URL}/pods", body)
        if not pod or "id" not in pod:
            raise LauncherError(f"RunPod create: no pod id in response {str(pod)[:300]}")
        return pod

    def get(self, pod_id: str) -> dict | None:
        return self.t("GET", f"{REST_URL}/pods/{pod_id}", None)

    def list(self) -> list[dict]:
        r = self.t("GET", f"{REST_URL}/pods", None) or []
        return r.get("pods", []) if isinstance(r, dict) else r

    def terminate(self, pod_id: str) -> None:
        self.t("DELETE", f"{REST_URL}/pods/{pod_id}", None)


def _cost_per_hr(pod: dict | None) -> float | None:
    v = (pod or {}).get("costPerHr")
    return float(v) if v is not None else None


# ---------- run / reap ----------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def pod_name_for(job: Job, run_id: str) -> str:
    return f"{POD_PREFIX}{job.name}-{run_id}"


def run_job(job: Job, api: RunPod | None, ledger: Path, run_id: str, *, cap: float | None = None,
            dry_run: bool = False, sync: Callable[[], None] = lambda: None, now: Callable[[], datetime] = _now,
            sleep: Callable[[float], None] = time.sleep, poll_s: float = 30.0, log=print) -> dict:
    cap = load_cap() if cap is None else cap
    start = now()
    month = start.strftime("%Y-%m")
    spent = check_budget(job, read_ledger(ledger), cap, month)
    pod_name = pod_name_for(job, run_id)
    log(f"budget ok: {month} ${spent:.2f} + worst case ${job.worst_case_usd:.2f} <= cap ${cap:.2f}")
    if dry_run:
        log(f"dry run: would create pod {pod_name} ({job.gpu_type or job.cpu_flavor}, max {job.max_minutes} min)")
        return {"status": "dry_run", "pod_name": pod_name, "worst_case_usd": job.worst_case_usd}
    assert api is not None
    pod = api.create(job, pod_name)
    pod_id = pod["id"]
    rate = _cost_per_hr(pod) or job.hourly_usd
    # reserve before anything can fail, so a crash still counts the worst case against the cap
    append_ledger(ledger, {"event": "start", "ts": _iso(start), "month": month, "job": job.name, "pod_id": pod_id,
                           "pod_name": pod_name, "run_id": run_id, "max_minutes": job.max_minutes,
                           "reserved_usd": job.worst_case_usd})
    status = "error"
    try:
        # publish the reservation before the pod can run long: if the runner dies later, the next
        # budget check still sees it. A failed publish terminates the pod (finally) and fails the run.
        try:
            sync()
        except Exception as e:
            raise LauncherError(f"ledger sync failed after creating {pod_id}: {e}; terminated") from e
        if rate > job.hourly_usd:
            status = "rate_exceeded"
            raise LauncherError(f"pod {pod_id} costs ${rate}/h > job hourly_usd ${job.hourly_usd}; terminated")
        deadline = start + timedelta(minutes=job.max_minutes)
        while True:
            info = api.get(pod_id)
            if info is None or info.get("desiredStatus") in ("EXITED", "TERMINATED"):
                status = "completed"
                break
            rate = _cost_per_hr(info) or rate
            if now() >= deadline:
                status = "timeout"
                log(f"max_minutes {job.max_minutes} reached; terminating {pod_id}")
                break
            sleep(poll_s)
    finally:
        try:
            api.terminate(pod_id)
        finally:
            end = now()
            hours = max((end - start).total_seconds(), 0) / 3600
            actual = round(min(rate * hours, job.worst_case_usd) if status != "rate_exceeded" else rate * hours, 4)
            append_ledger(ledger, {"event": "end", "ts": _iso(end), "month": month, "job": job.name, "pod_id": pod_id,
                                   "status": status, "minutes": round(hours * 60, 2), "cost_per_hr": rate,
                                   "actual_usd": actual})
            log(f"pod {pod_id} {status}: {hours * 60:.1f} min, ${actual:.4f}")
    return {"status": status, "pod_id": pod_id, "actual_usd": actual}


def reap(api: RunPod, ledger: Path, *, name_prefix: str = POD_PREFIX, pod_name: str | None = None,
         force: bool = False, now: Callable[[], datetime] = _now, log=print) -> list[str]:
    """Terminate our pods past their deadline (or unknown to the ledger) and close stale ledger entries.

    pod_name + force: the workflow's cleanup step — terminate exactly this run's pod regardless
    of deadline."""
    t = now()
    entries = read_ledger(ledger)
    opened = open_entries(entries)
    ended = {e["pod_id"] for e in entries if e["event"] == "end"}
    killed = []
    live = {}
    for pod in api.list():
        name = str(pod.get("name", ""))
        if not name.startswith(POD_PREFIX) or not name.startswith(name_prefix):
            continue  # never touch pods this launcher did not create
        if pod_name is not None and name != pod_name:
            continue
        if pod["id"] in ended:
            # already billed (the list can lag a DELETE): re-send terminate, never charge twice
            api.terminate(pod["id"])
            continue
        live[pod["id"]] = pod
        e = opened.get(pod["id"])
        if e and not force and t < _ts(e["ts"]) + timedelta(minutes=e["max_minutes"] + REAP_GRACE_MIN):
            continue
        api.terminate(pod["id"])
        killed.append(pod["id"])
        log(f"reaped {pod['id']} ({pod.get('name')})")
    for pod_id, e in opened.items():
        if pod_id in live and pod_id not in killed:
            continue
        if pod_name is not None and e.get("pod_name") != pod_name:
            continue  # scoped cleanup: other runs' entries are the daily reap's job
        # unknown runtime: charge the reservation, the conservative figure
        append_ledger(ledger, {"event": "end", "ts": _iso(t), "month": e["month"], "job": e["job"], "pod_id": pod_id,
                               "status": "reaped", "actual_usd": e["reserved_usd"]})
    for pod_id in killed:
        if pod_id not in opened:
            pod = live[pod_id]
            # a pod with no start entry (runner died before the ledger write): charge 24h, one reap period
            cost = round((_cost_per_hr(pod) or 0.0) * 24, 4)
            month = t.strftime("%Y-%m")
            append_ledger(ledger, {"event": "start", "ts": _iso(t), "month": month, "job": "unknown", "pod_id": pod_id,
                                   "pod_name": pod.get("name"), "run_id": "orphan", "max_minutes": 0,
                                   "reserved_usd": cost})
            append_ledger(ledger, {"event": "end", "ts": _iso(t), "month": month, "job": "unknown", "pod_id": pod_id,
                                   "status": "orphan", "actual_usd": cost})
    return killed


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    r = sub.add_parser("run")
    r.add_argument("spec", type=Path)
    r.add_argument("--ledger", type=Path, required=True)
    r.add_argument("--run-id", default=os.environ.get("GITHUB_RUN_ID", "local"))
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--sync-cmd", help="command run after the start entry is written; nonzero → terminate, fail")
    g = sub.add_parser("reap")
    g.add_argument("--ledger", type=Path, required=True)
    g.add_argument("--job", type=Path, help="with --run-id: reap only this run's pod (name from the parsed spec)")
    g.add_argument("--run-id")
    g.add_argument("--force", action="store_true")
    a = p.parse_args(argv)

    def api() -> RunPod:
        key = os.environ.get("RUNPOD_API_KEY")
        if not key:
            raise LauncherError("RUNPOD_API_KEY not set — the launcher runs only in .github/workflows/cloud.yml")
        return RunPod(http_transport(key))

    try:
        if a.cmd == "check":
            print(f"RunPod key ok; balance ${api().balance():.2f}; cap ${load_cap():.2f}/month")
        elif a.cmd == "run":
            job = load_spec(a.spec)
            sync = (lambda: subprocess.run(a.sync_cmd, shell=True, check=True)) if a.sync_cmd else (lambda: None)
            res = run_job(job, None if a.dry_run else api(), a.ledger, a.run_id, dry_run=a.dry_run, sync=sync)
            if res["status"] not in ("completed", "dry_run"):
                print(f"job {job.name}: {res['status']}", file=sys.stderr)
                return 1
        else:
            if bool(a.job) != bool(a.run_id):
                raise LauncherError("reap: pass --job and --run-id together (or neither for the daily reap)")
            name = pod_name_for(load_spec(a.job), a.run_id) if a.job else None
            reap(api(), a.ledger, pod_name=name, force=a.force)
    except BudgetExceeded as e:
        print(e, file=sys.stderr)
        return 2
    except LauncherError as e:
        print(e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
