"""Budget-guarded cloud launcher: the only path by which agents spend money (ADR 0004 §5, #20).

Runs only inside `.github/workflows/cloud.yml`; the RunPod key lives in the `RUNPOD_API_KEY`
secret and agents never see it. Agents submit a job spec `jobs/<name>.yaml` by PR and
dispatch the workflow.

Usage:
  python harness/cloud/launcher.py check                       # balance query, costs nothing
  python harness/cloud/launcher.py run jobs/x.yaml --ledger L [--dry-run] [--run-id ID] [--sync-cmd CMD]
                                       [--result-out PATH] [--resume-file R.json --resume-run ID]
  python harness/cloud/launcher.py reap --ledger L [--job jobs/x.yaml --run-id ID --force]
  python harness/cloud/launcher.py publish result.json --run-id ID --ops OPS_WORKTREE

Budget rule: a job runs only if month_total + worst_case(job) <= monthly cap
(`harness/budget.json`). month_total counts finished jobs at their actual cost and open
ones (no end entry yet) at their reserved worst case, so a crashed run still counts.
Pods are always terminated: on completion, on deadline, on error (finally), by the
workflow's `if: always()` reap step, and by the daily orphan reap.

Results (#184, ADR 0014): a job with `result_path` gets a per-run random token in its env and,
after its command, serves only `/<token>/status.json` and `/<token>/result.json` over the RunPod
HTTP proxy. The launcher pulls them (no RunPod key sent), checks size, JSON and secret patterns,
writes `--result-out`, then terminates the pod. The pod needs no GitHub credential.
Resume (#354): the same server takes one upload at `/<token>/resume` (PUT, at most RESUME_MAX_BYTES),
or `/<token>/resume-none`. The wrapped job waits for either (RESUME_WAIT_S) before it starts and sees
the uploaded file in `$STALKER_RESUME` (empty for none). With `--resume-file` the launcher sends an
earlier run's result there, trimmed to what a resume needs and gzipped; without it, `resume-none`.
`publish` copies a checked result to `ops:cloud/results/<run id>.json`: agent sandboxes cannot
download artifacts (their blob storage host is outside the egress allow-list, #264), but read ops.
Over 1 MB it writes `<run id>.summary.json` with long strings (model blobs) left out (#358).
Capacity and hosts (#401, ADR 0019 §6): `cpu_flavors` are tried in order, a RunPod "no instances" refusal moves
to the next one and, when all are full, waits CAPACITY_RETRY_MINUTES and tries again (each refusal a $0
`create_failed` ledger line, exit 3 when they run out, plus an `outcome: failed` line in `--journal`). With `median_iters_per_s` the result server also answers
`/<token>/progress.json` (the first progress line's it/s only) and a pod below SLOW_HOST_FRACTION of the median
is replaced once. Waits and replacements happen only if the pod still ends inside MAX_JOB_MINUTES.
"""
from __future__ import annotations

import argparse
import gzip
import json
import hashlib
import os
import re
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePath
from typing import Callable, Sequence

ROOT = Path(__file__).resolve().parent.parent.parent
BUDGET_FILE = ROOT / "harness" / "budget.json"
POD_PREFIX = "stalker-"
REAP_GRACE_MIN = 10
# GitHub-hosted runners stop any job at 360 min; keep the launcher's own deadline, terminate
# and ledger push well inside that, or the runner limit kills the job before its finally runs.
MAX_JOB_MINUTES = 330
REST_URL = "https://rest.runpod.io/v1"
# RunPod sits behind Cloudflare, which rejects urllib's default "Python-urllib" agent with 403/1010.
USER_AGENT = "stalker-launcher/1 (+https://github.com/lobster0113/stalker)"
GRAPHQL_URL = "https://api.runpod.io/graphql"
RESULT_PORT = 8000
RESULT_DIR = "/stalker-result"
TOKEN_ENV = "STALKER_RESULT_TOKEN"
# artifacts of a public repo are readable by anyone signed in; keep them small and checked
# A pod training run returns its model in the result (#333): a pro checkpoint is tens of MB (#346).
RESULT_MAX_BYTES = 256 * 1024 * 1024
SECRET_PATTERNS = [re.compile(p) for p in (
    rb"gh[pousr]_[A-Za-z0-9]{30,}", rb"github_pat_[A-Za-z0-9_]{30,}", rb"rpa_[A-Za-z0-9]{20,}",
    rb"AKIA[0-9A-Z]{16}", rb"-----BEGIN [A-Z ]*PRIVATE KEY-----", rb"xox[abpr]-[A-Za-z0-9-]{10,}")]
# ops is a git branch every routine fetches; bigger results stay artifact-only
OPS_RESULT_MAX_BYTES = 1024 * 1024
OPS_RESULT_DIR = PurePath("cloud", "results")
SUMMARY_BLOB_CHARS = 4096  # strings longer than this (model blobs) are left out of an oversized result's ops summary
RESUME_DIR = "/stalker-resume"
RESUME_ENV = "STALKER_RESUME"
# The upload goes through RunPod's proxy, which is behind Cloudflare: its request bodies stop at 100 MB.
RESUME_MAX_BYTES = 95 * 1024 * 1024
RESUME_WAIT_S = 1200
# what pod_train --resume-result reads; the evaluation numbers stay in the artifact
RESUME_FIELDS = ("job", "tier", "players", "seed", "iters", "model", "checkpoint", "sha")


class LauncherError(Exception):
    pass


class BudgetExceeded(LauncherError):
    pass


class CapacityError(LauncherError):
    """RunPod has no instance of the requested flavor right now; no pod was made, so it cost nothing."""


class CapacityExhausted(LauncherError):
    pass


def journal_failure(journal_dir: Path, job: str, run_id: str, message: str, now: datetime) -> None:
    """One `outcome: failed` line in `ops:journal/YYYY-MM.jsonl` for a run that never got a pod.

    The launcher has no GitHub credential to comment on an issue; the journal is what the routines
    and the auditor already read, so a capacity give-up shows up there with its run id (#401)."""
    journal_dir.mkdir(parents=True, exist_ok=True)
    ts = _iso(now)
    line = {"ts": ts, "role": "cloud", "outcome": "failed", "issue": None, "pr": None,
            "notes": f"cloud run {run_id} job {job}: {message}"[:500], "friction": "",
            "run_id": run_id, "job": job}
    with open(journal_dir / f"{ts[:7]}.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")


# ---------- job spec ----------

SPEC_FIELDS = {"name", "image", "command", "gpu_type", "gpu_count", "cpu_flavor", "vcpu",
               "max_minutes", "hourly_usd", "est_cost_usd", "disk_gb", "cloud", "result_path",
               "cpu_flavors", "flavor_hourly_usd", "median_iters_per_s"}
REQUIRED = {"name", "image", "command", "max_minutes", "hourly_usd"}
# one-line `[a, b]` lists (#401); everything else stays a scalar
LIST_FIELDS = {"cpu_flavors", "flavor_hourly_usd", "median_iters_per_s"}
# ADR 0019 §6: pod chains keep 32 parallel MCCFR workers, so a fallback flavor must not change the vCPU count
FLAVOR_LIST_VCPU = 32
# a host below this fraction of the job's measured median it/s gets one reissue (cpu3c 7713/9754 ran ~0.45×, #373)
SLOW_HOST_FRACTION = 0.6
# RunPod HTTP 500 "no longer any instances available" costs nothing; wait and try the flavor list again
CAPACITY_RETRY_MINUTES = (15, 30, 60)
CAPACITY_RE = re.compile(rb"no longer any instances available|no instances available", re.IGNORECASE)


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
    result_path: str | None = None
    cpu_flavors: tuple[str, ...] = ()
    flavor_hourly_usd: tuple[float, ...] = ()
    median_iters_per_s: tuple[float, ...] = ()

    @property
    def flavors(self) -> list[tuple[str | None, float, float]]:
        """(flavor, hourly cap, median it/s or 0) in try order; a GPU job is one (None, hourly_usd, 0) entry."""
        names = list(self.cpu_flavors) or [self.cpu_flavor]
        caps = list(self.flavor_hourly_usd) or [self.hourly_usd] * len(names)
        medians = list(self.median_iters_per_s) or [0.0] * len(names)
        return list(zip(names, caps, medians))

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
        if key in LIST_FIELDS:
            v = val.strip()
            if not (v.startswith("[") and v.endswith("]")) or not v[1:-1].strip():
                raise LauncherError(f"{source}:{n}: {key} must be a one-line list like [cpu5c, cpu3c] — got {val!r}")
            data[key] = tuple(_scalar(x) for x in v[1:-1].split(","))
            continue
        data[key] = _scalar(val)
    missing = REQUIRED - data.keys()
    if missing:
        raise LauncherError(f"{source}: missing required keys: {', '.join(sorted(missing))}")
    if sum(bool(data.get(k)) for k in ("gpu_type", "cpu_flavor", "cpu_flavors")) != 1:
        raise LauncherError(f"{source}: set exactly one of gpu_type, cpu_flavor or cpu_flavors")
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
    # spliced into the pod's shell script unquoted, so only plain absolute paths
    if "result_path" in data and not re.fullmatch(r"/[A-Za-z0-9._/-]+", str(data["result_path"])):
        raise LauncherError(f"{source}: result_path must be an absolute path of [A-Za-z0-9._/-]")
    data["hourly_usd"] = float(data["hourly_usd"])
    data["est_cost_usd"] = float(data.get("est_cost_usd", 0.0))
    _check_flavor_lists(data, source)
    return Job(**data)


def _check_flavor_lists(data: dict, source: str) -> None:
    names = data.get("cpu_flavors") or ((data["cpu_flavor"],) if data.get("cpu_flavor") else ())
    if data.get("cpu_flavors"):
        if not all(isinstance(f, str) and re.fullmatch(r"[a-z0-9]+", f) for f in names) or len(set(names)) != len(names):
            raise LauncherError(f"{source}: cpu_flavors must be distinct RunPod CPU flavor ids like [cpu5c, cpu3c]")
        if data.get("vcpu") != FLAVOR_LIST_VCPU:
            raise LauncherError(f"{source}: cpu_flavors needs vcpu: {FLAVOR_LIST_VCPU} (same workers and checkpoints "
                                "on every flavor, ADR 0019 §6)")
    for key in ("flavor_hourly_usd", "median_iters_per_s"):
        vals = data.get(key)
        if vals is None:
            continue
        if not names:
            raise LauncherError(f"{source}: {key} is for CPU jobs (cpu_flavor or cpu_flavors)")
        if len(vals) != len(names) or not all(isinstance(v, (int, float)) and v >= 0 for v in vals):
            raise LauncherError(f"{source}: {key} needs one non-negative number per flavor ({len(names)})")
        data[key] = tuple(float(v) for v in vals)
    if any(c > data["hourly_usd"] for c in data.get("flavor_hourly_usd", ())):
        # hourly_usd stays the budget's worst-case rate, so no flavor may be allowed to cost more
        raise LauncherError(f"{source}: every flavor_hourly_usd must be <= hourly_usd {data['hourly_usd']}")
    if any(data.get("median_iters_per_s", ())) and not data.get("result_path"):
        raise LauncherError(f"{source}: median_iters_per_s needs result_path (it/s comes through the result server)")



def _rel_posix(path: PurePath, root: PurePath) -> str:
    """Repo-relative name with forward slashes on every OS (Windows paths use backslashes, #225)."""
    return path.relative_to(root).as_posix() if path.is_relative_to(root) else path.as_posix()


def load_spec(path: Path) -> Job:
    rel = _rel_posix(path.resolve(), ROOT)
    if not re.fullmatch(r"jobs/[^/]+\.yaml", rel):
        raise LauncherError(f"{path}: job specs must be jobs/<name>.yaml in this repo")
    return parse_spec(path.read_text(encoding="utf-8"), rel)


# ---------- budget ledger ----------

def load_cap(path: Path = BUDGET_FILE) -> float:
    cap = json.loads(path.read_text(encoding="utf-8"))["monthly_cap_usd"]
    if not isinstance(cap, (int, float)) or cap < 0:
        raise LauncherError(f"{path}: monthly_cap_usd must be a non-negative number")
    return float(cap)


def read_ledger(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def append_ledger(path: Path, entry: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
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
                                     headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
                                              "Accept": "application/json", "User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            full = e.read()
            body = full[:300]
            if e.code == 500 and CAPACITY_RE.search(full):
                raise CapacityError(f"RunPod {method} {url}: HTTP 500 {body!r}") from e
            hint = (" — Cloudflare rejected the client signature; check USER_AGENT in harness/cloud/launcher.py"
                    if e.code == 403 and b"1010" in body else "")
            raise LauncherError(f"RunPod {method} {url}: HTTP {e.code} {body!r}{hint}") from e
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

    def create(self, job: Job, pod_name: str, token: str | None = None, flavor: str | None = None) -> dict:
        body = {"name": pod_name, "imageName": job.image, "cloudType": job.cloud,
                "containerDiskInGb": job.disk_gb, "dockerStartCmd": ["bash", "-lc", pod_command(job)]}
        if job.result_path:
            # the token goes in env, never in the command, so it stays out of logs that echo the spec
            body |= {"ports": [f"{RESULT_PORT}/http"], "env": {TOKEN_ENV: token}}
        if job.gpu_type:
            body |= {"computeType": "GPU", "gpuTypeIds": [job.gpu_type], "gpuCount": job.gpu_count}
        else:
            body |= {"computeType": "CPU", "cpuFlavorIds": [flavor or job.flavors[0][0]], "vcpuCount": job.vcpu}
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


# The pod's result server (stdlib only, the image may have nothing else). GET serves status.json and
# result.json from the token directory; PUT/POST takes one resume upload (size-capped, written whole
# then renamed) or a "none", and then refuses more, so the job sees exactly one signal.
POD_SERVER = r"""
import hashlib, http.server, json, os, shutil, sys, threading
root, port, rdir, cap = sys.argv[1], int(sys.argv[2]), sys.argv[3], int(sys.argv[4])
pre = "/" + os.environ["STALKER_RESULT_TOKEN"] + "/"
lock = threading.Lock()  # a retried upload waits for the one still running
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass
    def reply(self, code, body=b""):
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def name(self):
        return self.path[len(pre):] if self.path.startswith(pre) else ""
    def do_GET(self):
        if self.name() == "progress.json":
            return self.progress()
        if self.name() not in ("status.json", "result.json"):
            return self.reply(404)
        try:
            f = open(os.path.join(root, self.name()), "rb")
        except OSError:
            return self.reply(404)
        with f:
            self.send_response(200)
            self.send_header("Content-Length", str(os.fstat(f.fileno()).st_size))
            self.end_headers()
            shutil.copyfileobj(f, self.wfile)
    def progress(self):
        # only the first progress line's number leaves the pod, never the log text
        try:
            with open(os.path.join(rdir, "job.log"), "rb") as f:
                lines = f.read(1 << 20).splitlines()
        except OSError:
            lines = []
        for b in lines:
            try:
                v = json.loads(b).get("iters_per_s")
            except (ValueError, AttributeError):
                continue
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return self.reply(200, json.dumps({"iters_per_s": float(v)}).encode())
        self.reply(404)
    def do_PUT(self):
        kind = {"resume": "ready", "resume-none": "none"}.get(self.name())
        if kind is None:
            return self.reply(404)
        with lock:
            self.take(kind)
    def take(self, kind):
        if os.path.exists(os.path.join(rdir, "signal")):
            return self.reply(409)
        try:
            n = int(self.headers.get("Content-Length", ""))
        except ValueError:
            return self.reply(411)
        if not 0 <= n <= cap or (kind == "ready" and n == 0):
            self.close_connection = True
            return self.reply(413)
        h, left = hashlib.sha256(), n
        part = os.path.join(rdir, "resume.part")
        with open(part, "wb") as f:
            while left:
                b = self.rfile.read(min(left, 1 << 20))
                if not b:
                    return self.reply(400)
                f.write(b)
                h.update(b)
                left -= len(b)
        if kind == "ready":
            os.replace(part, os.path.join(rdir, "resume.bin"))
        with open(os.path.join(rdir, "signal.tmp"), "w") as f:
            f.write(kind)
        os.replace(os.path.join(rdir, "signal.tmp"), os.path.join(rdir, "signal"))
        self.reply(200, json.dumps({"bytes": n, "sha256": h.hexdigest()}).encode())
    do_POST = do_PUT
http.server.ThreadingHTTPServer(("", port), H).serve_forever()
"""


def pod_command(job: Job, serve_dir: str = RESULT_DIR, port: int = RESULT_PORT, resume_dir: str = RESUME_DIR,
                wait_s: int = RESUME_WAIT_S) -> str:
    """The job's command, wrapped to take a resume upload and publish its result over HTTP when
    `result_path` is set.

    Only `/<token>/...` names answer, so the token is the only way in. The job starts once the launcher
    has sent a resume file or "none"; no signal in `wait_s` exits 97 without running it. status.json
    is written last (atomically), so once it is visible the result copy is complete. The pod then
    idles until the launcher terminates it."""
    if not job.result_path:
        return job.command
    d = f'{serve_dir}/"${TOKEN_ENV}"'
    sig = f"{resume_dir}/signal"
    return "\n".join([
        f"mkdir -p {d} {resume_dir}",
        f"python3 - {d} {port} {resume_dir} {RESUME_MAX_BYTES} >/dev/null 2>&1 <<'STALKER_SERVER' &",
        POD_SERVER.strip("\n"),
        "STALKER_SERVER",
        f"w=0; while [ ! -f {sig} ] && [ $w -lt {wait_s} ]; do sleep 2; w=$((w+2)); done",
        f'sig=$(cat {sig} 2>/dev/null); {RESUME_ENV}=""; [ "$sig" = ready ] && {RESUME_ENV}={resume_dir}/resume.bin',
        f"export {RESUME_ENV}",
        'if [ "$sig" = ready ] || [ "$sig" = none ]; then',
        # stderr also goes to job.log, where the server finds the first progress line (#401)
        "(", job.command, f") 2> >(tee -a {resume_dir}/job.log >&2)",
        "rc=$?",
        f'else echo "no resume signal from the launcher in {wait_s} s" >&2; rc=97; fi',
        f"cp {job.result_path} {d}/result.json 2>/dev/null",
        f'printf \'{{"exit": %d}}\' "$rc" > {d}/.status.tmp && mv {d}/.status.tmp {d}/status.json',
        "sleep infinity",
    ])


def proxy_url(pod_id: str, token: str, name: str, port: int = RESULT_PORT) -> str:
    return f"https://{pod_id}-{port}.proxy.runpod.net/{token}/{name}"


Fetch = Callable[[str, int], tuple[int, bytes]]


def http_fetch(url: str, max_bytes: int) -> tuple[int, bytes]:
    """GET without credentials; reads at most max_bytes + 1 so an oversized body is detectable.
    Unreachable (pod still booting, proxy 502) is status 0, i.e. "not yet"."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read(max_bytes + 1)
    except urllib.error.HTTPError as e:
        return e.code, b""
    except (urllib.error.URLError, OSError):
        return 0, b""


Send = Callable[[str, bytes], tuple[int, bytes]]


def http_send(url: str, body: bytes) -> tuple[int, bytes]:
    """PUT without credentials (the pod's resume upload). Unreachable is status 0, i.e. "try again"."""
    req = urllib.request.Request(url, data=body, method="PUT",
                                 headers={"User-Agent": USER_AGENT, "Content-Type": "application/octet-stream"})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            return r.status, r.read(4096)
    except urllib.error.HTTPError as e:
        return e.code, b""
    except (urllib.error.URLError, OSError):
        return 0, b""


def resume_payload(path: Path, run_id: str, max_bytes: int = RESUME_MAX_BYTES) -> bytes:
    """An earlier pod result, trimmed to RESUME_FIELDS plus its run id, gzipped, for the next pod."""
    if not re.fullmatch(r"[0-9]+", run_id):
        raise LauncherError(f"--resume-run must be digits (the cloud.yml run id of the result), got {run_id!r}")
    try:
        body = path.read_bytes()
    except OSError as e:
        raise LauncherError(f"resume file {path}: {e.strerror}; was artifact cloud-result-{run_id} downloaded?") from e
    check_result(body)
    r = json.loads(body)
    if not isinstance(r, dict) or not r.get("checkpoint") or not isinstance(r.get("model"), dict):
        note = r.get("checkpoint_note", "missing") if isinstance(r, dict) else "not an object"
        raise LauncherError(f"run {run_id}'s result has no checkpoint ({note}); it cannot be resumed — "
                            "dispatch without resume_run")
    trimmed = {k: r[k] for k in RESUME_FIELDS if k in r} | {"run_id": run_id}
    # the npz inside is compressed already; gzip takes back most of base64's 4/3
    blob = gzip.compress(json.dumps(trimmed).encode(), compresslevel=6, mtime=0)
    if len(blob) > max_bytes:
        raise LauncherError(f"resume upload {len(blob)} bytes > {max_bytes} (RunPod proxy body limit); "
                            "the checkpoint is too big to hand over — see harness/experiments/026-pod-resume.md")
    return blob


def check_result(body: bytes, forbidden: Sequence[str] = (), max_bytes: int | None = None) -> None:
    max_bytes = RESULT_MAX_BYTES if max_bytes is None else max_bytes
    if len(body) > max_bytes:
        raise LauncherError(f"result over {max_bytes} bytes; write a summary JSON and keep checkpoints small")
    try:
        json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as e:
        raise LauncherError(f"result is not UTF-8 JSON ({e.__class__.__name__}); result_path must be a JSON file") from e
    hits = [p.pattern.decode() for p in SECRET_PATTERNS if p.search(body)]
    hits += ["<launcher secret>" for v in forbidden if v and v.encode() in body]
    if hits:
        raise LauncherError(f"result rejected: looks like it contains a secret ({', '.join(hits)}); not saved")


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
            sleep: Callable[[float], None] = time.sleep, poll_s: float = 30.0, log=print,
            result_out: Path | None = None, fetch: Fetch = http_fetch, token: str | None = None,
            forbidden: Sequence[str] = (), resume: bytes | None = None, send: Send = http_send) -> dict:
    """Create the job's pod (flavor list, capacity retries), run it, and at most once replace a slow host (#401).

    Every wait and every replacement must still leave the whole pod run inside MAX_JOB_MINUTES of this
    launcher's start, or the runner's 360-min limit would kill the job before its finally (terminate, ledger)."""
    cap = load_cap() if cap is None else cap
    launch = now()
    month = launch.strftime("%Y-%m")
    spent = check_budget(job, read_ledger(ledger), cap, month)
    pod_name = pod_name_for(job, run_id)
    log(f"budget ok: {month} ${spent:.2f} + worst case ${job.worst_case_usd:.2f} <= cap ${cap:.2f}")
    if resume is not None and not job.result_path:
        raise LauncherError(f"{job.name}: resume needs a job with result_path (the upload goes to its result server)")
    if dry_run:
        if resume is not None:
            log(f"dry run: resume upload {len(resume)} bytes ok")
        what = job.gpu_type or ", ".join(f for f, _, _ in job.flavors)
        log(f"dry run: would create pod {pod_name} ({what}, max {job.max_minutes} min)")
        return {"status": "dry_run", "pod_name": pod_name, "worst_case_usd": job.worst_case_usd}
    assert api is not None
    if job.result_path and result_out is None:
        raise LauncherError(f"{job.name}: result_path is set but no --result-out; the result would be lost")
    token = token or secrets.token_hex(16)

    def fits(extra_min: float = 0.0) -> bool:
        return (now() - launch).total_seconds() / 60 + extra_min + job.max_minutes <= MAX_JOB_MINUTES

    replaced: list[str] = []
    while True:
        pod, (flavor, rate_cap, median) = _create(job, api, pod_name, token, ledger, run_id, month, fits, now, sleep, log)
        res = _run_pod(job, api, pod, flavor, rate_cap, median if not replaced else 0.0, fits, ledger, run_id, month,
                       cap, sync=sync, now=now, sleep=sleep, poll_s=poll_s, log=log, result_out=result_out,
                       fetch=fetch, token=token, forbidden=forbidden, resume=resume, send=send)
        if res["status"] != "slow_host":
            return res | ({"replaced_pods": replaced} if replaced else {})
        replaced.append(res["pod_id"])
        # the slow pod's actual cost is in the ledger now; the replacement must still fit the cap
        check_budget(job, read_ledger(ledger), cap, month)


def _create(job: Job, api: RunPod, pod_name: str, token: str, ledger: Path, run_id: str, month: str,
            fits: Callable[[float], bool], now: Callable[[], datetime], sleep: Callable[[float], None],
            log) -> tuple[dict, tuple]:
    """Try the flavors in order; when all are out of capacity, wait CAPACITY_RETRY_MINUTES and go again.

    Each refused create is a zero-cost `create_failed` ledger line with the run id, so the record shows
    every try even though no pod (and no start/end pair) exists for it."""
    waits = list(CAPACITY_RETRY_MINUTES)
    attempt = 0
    while True:
        for entry in job.flavors:
            attempt += 1
            try:
                return api.create(job, pod_name, token, entry[0]), entry
            except CapacityError as e:
                append_ledger(ledger, {"event": "create_failed", "ts": _iso(now()), "month": month,
                                       "job": job.name, "run_id": run_id, "flavor": entry[0], "attempt": attempt,
                                       "error": "capacity", "actual_usd": 0.0})
                log(f"no capacity for {entry[0] or job.gpu_type} (try {attempt}): {e}")
        if not waits:
            raise CapacityExhausted(f"run {run_id}: no capacity for {', '.join(str(f) for f, _, _ in job.flavors)} after "
                                    f"{attempt} tries over {'+'.join(map(str, CAPACITY_RETRY_MINUTES))} min of waits "
                                    "($0); dispatch again later — the tries are create_failed lines in the ledger")
        wait = waits.pop(0)
        if not fits(wait):
            raise CapacityExhausted(f"run {run_id}: no capacity, and a {wait} min wait + max_minutes {job.max_minutes} "
                                    f"would pass the launcher's {MAX_JOB_MINUTES} min ($0); dispatch again later "
                                    "(a shorter max_minutes leaves room for capacity waits)")
        log(f"all flavors out of capacity; waiting {wait} min")
        sleep(wait * 60)


def _run_pod(job: Job, api: RunPod, pod: dict, flavor: str | None, rate_cap: float, median: float,
             fits: Callable[[float], bool], ledger: Path, run_id: str, month: str, cap: float, *,
             sync, now, sleep, poll_s, log, result_out, fetch, token, forbidden, resume, send) -> dict:
    start = now()
    pod_id = pod["id"]
    pod_name = pod.get("name") or pod_name_for(job, run_id)
    rate = _cost_per_hr(pod) or rate_cap
    # reserve before anything can fail, so a crash still counts the worst case against the cap
    append_ledger(ledger, {"event": "start", "ts": _iso(start), "month": month, "job": job.name, "pod_id": pod_id,
                           "pod_name": pod_name, "run_id": run_id, "max_minutes": job.max_minutes,
                           "reserved_usd": job.worst_case_usd, **({"flavor": flavor} if flavor else {})})
    status = "error"
    result: dict = {}
    try:
        # publish the reservation before the pod can run long: if the runner dies later, the next
        # budget check still sees it. A failed publish terminates the pod (finally) and fails the run.
        try:
            sync()
        except Exception as e:
            raise LauncherError(f"ledger sync failed after creating {pod_id}: {e}; terminated") from e
        # Runs of different jobs go in parallel (#350): two may pass check_budget before either's
        # reservation is on ops. The sync pulled every reservation pushed before ours, and a later one
        # sees ours, so at least one of two racing runs sees both here and stops its pod.
        total = month_total(read_ledger(ledger), month)
        if total > cap:
            status = "over_cap"
            raise BudgetExceeded(f"budget: {month} reserved ${total:.2f} > cap ${cap:.2f} after a parallel run "
                                 f"reserved too; {pod_id} terminated. Dispatch it again when a run finishes.")
        if rate > rate_cap:
            status = "rate_exceeded"
            raise LauncherError(f"pod {pod_id} costs ${rate}/h > hourly_usd ${rate_cap} for {flavor or job.gpu_type}; "
                                "terminated")
        deadline = start + timedelta(minutes=job.max_minutes)
        signalled = not job.result_path
        speed_checked = not median
        while True:
            info = api.get(pod_id)
            if info is None or info.get("desiredStatus") in ("EXITED", "TERMINATED"):
                # a result job idles after publishing, so exiting on its own means it never did
                status = "no_result" if job.result_path else "completed"
                break
            rate = _cost_per_hr(info) or rate
            if not signalled:
                status = "resume_failed"  # what the ledger says if the pod refuses the handover
                signalled = _signal(pod_id, token, resume, send, log)
                status = "error"
            elif job.result_path:
                if not speed_checked:
                    its = _first_its(fetch(proxy_url(pod_id, token, "progress.json"), 1024))
                    if its is not None:
                        speed_checked = True
                        if its < SLOW_HOST_FRACTION * median:
                            if fits(0.0):
                                status = "slow_host"
                                result = {"iters_per_s": its}
                                log(f"slow host: {its} it/s < {SLOW_HOST_FRACTION} x median {median}; replacing "
                                    f"{pod_id} once")
                                break
                            log(f"slow host: {its} it/s < {SLOW_HOST_FRACTION} x median {median}, but a new pod "
                                f"would not finish inside {MAX_JOB_MINUTES} min; keeping it")
                code, raw = fetch(proxy_url(pod_id, token, "status.json"), 1024)
                if code == 200:
                    status, result = _collect(job, pod_id, token, raw, result_out, fetch, [token, *forbidden], log)
                    break
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
                                   "actual_usd": actual, **result})
            log(f"pod {pod_id} {status}: {hours * 60:.1f} min, ${actual:.4f}")
    return {"status": status, "pod_id": pod_id, "actual_usd": actual, **result}


def _first_its(reply: tuple[int, bytes]) -> float | None:
    code, raw = reply
    if code != 200:
        return None
    try:
        v = json.loads(raw)["iters_per_s"]
    except (ValueError, KeyError, TypeError):
        return None
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _signal(pod_id: str, token: str, resume: bytes | None, send: Send, log) -> bool:
    """Hand the pod its resume file (or "none"); False while the proxy is not up yet."""
    name, body = ("resume", resume) if resume is not None else ("resume-none", b"")
    code, raw = send(proxy_url(pod_id, token, name), body)
    if code in (0, 404) or code >= 500:
        # pod booting: the proxy answers 404 before the port is routed (run 40886839070, #361) and 502
        # until the server listens; our server's own 404 is only for paths this launcher never sends.
        # Bounded: without a signal the pod exits 97 after RESUME_WAIT_S and the loop ends on EXITED.
        return False
    if code == 409:
        # a signal is already there; only this launcher knows the token, so an earlier try of ours landed
        log(f"{name}: pod already signalled (an earlier upload's reply was lost)")
        return True
    if code != 200:
        raise LauncherError(f"{name} refused by the pod (HTTP {code}); {pod_id} terminated"
                            + (f" — over the pod's {RESUME_MAX_BYTES}-byte cap" if code == 413 else ""))
    want = {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}
    try:
        got = json.loads(raw)
    except ValueError:
        got = None
    if got != want:
        raise LauncherError(f"{name}: pod received {got}, sent {want}; {pod_id} terminated")
    log(f"{name}: sent {len(body)} bytes" if resume is not None else "resume: none")
    return True


def _collect(job: Job, pod_id: str, token: str, raw_status: bytes, out: Path, fetch: Fetch,
             forbidden: list[str], log) -> tuple[str, dict]:
    try:
        rc = int(json.loads(raw_status)["exit"])
    except (ValueError, KeyError, TypeError):
        return "result_rejected", {}
    if rc != 0:
        log(f"job command exited {rc}; result not collected")
        return "failed", {"exit": rc}
    code, body = fetch(proxy_url(pod_id, token, "result.json"), RESULT_MAX_BYTES)
    if code != 200:
        log(f"job exited 0 but {job.result_path} was not written (HTTP {code})")
        return "no_result", {"exit": 0}
    try:
        check_result(body, forbidden)
    except LauncherError as e:
        log(str(e))
        return "result_rejected", {"exit": 0}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(body)
    meta = {"exit": 0, "result_bytes": len(body), "result_sha256": hashlib.sha256(body).hexdigest()}
    log(f"result saved: {out} ({len(body)} bytes, sha256 {meta['result_sha256'][:12]})")
    return "completed", meta


def _strip_blobs(obj):
    """Copy of a JSON value with long strings replaced by {omitted_chars, sha256}."""
    if isinstance(obj, str) and len(obj) > SUMMARY_BLOB_CHARS:
        return {"omitted_chars": len(obj), "sha256": hashlib.sha256(obj.encode("utf-8")).hexdigest()}
    if isinstance(obj, dict):
        return {k: _strip_blobs(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_strip_blobs(v) for v in obj]
    return obj


def publish(src: Path, run_id: str, ops: Path, log=print) -> Path | None:
    """Copy a checked result JSON to <ops>/cloud/results/<run_id>.json.

    Over the ops limit: publish <run_id>.summary.json instead (long strings, i.e. model blobs, left out;
    agent sandboxes cannot download the artifact). None when nothing was published."""
    if not re.fullmatch(r"[0-9]+", run_id):
        raise LauncherError(f"run id must be digits (a cloud.yml run id), got {run_id!r}")
    body = src.read_bytes()
    check_result(body)  # again: a collected artifact did not pass through this process's _collect
    name = f"{run_id}.json"
    if len(body) > OPS_RESULT_MAX_BYTES:
        summary = _strip_blobs(json.loads(body.decode("utf-8")))
        if isinstance(summary, dict):
            summary["_summary_of"] = {"result_bytes": len(body), "result_sha256": hashlib.sha256(body).hexdigest()}
        body = json.dumps(summary, ensure_ascii=False, indent=1).encode("utf-8")
        check_result(body)
        if len(body) > OPS_RESULT_MAX_BYTES:
            log(f"result and its summary are over {OPS_RESULT_MAX_BYTES} bytes for ops; it stays in the run's artifact only")
            return None
        name = f"{run_id}.summary.json"
    dst = ops / OPS_RESULT_DIR / name
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(body)
    log(f"result published: ops:{OPS_RESULT_DIR.as_posix()}/{name} ({len(body)} bytes)")
    return dst


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
    r.add_argument("--result-out", type=Path, help="where to write the job's result_path JSON (required if set)")
    r.add_argument("--resume-file", type=Path, help="an earlier run's result JSON to continue from (#354)")
    r.add_argument("--resume-run", help="the cloud.yml run id that produced --resume-file")
    r.add_argument("--journal", type=Path, help="ops journal dir: a capacity give-up (exit 3) appends a failed line")
    g = sub.add_parser("reap")
    g.add_argument("--ledger", type=Path, required=True)
    g.add_argument("--job", type=Path, help="with --run-id: reap only this run's pod (name from the parsed spec)")
    g.add_argument("--run-id")
    g.add_argument("--force", action="store_true")
    u = sub.add_parser("publish")
    u.add_argument("result", type=Path)
    u.add_argument("--run-id", required=True)
    u.add_argument("--ops", type=Path, required=True, help="ops worktree")
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
            if bool(a.resume_file) != bool(a.resume_run):
                raise LauncherError("run: pass --resume-file and --resume-run together")
            resume = resume_payload(a.resume_file, a.resume_run) if a.resume_file else None
            sync = (lambda: subprocess.run(a.sync_cmd, shell=True, check=True)) if a.sync_cmd else (lambda: None)
            res = run_job(job, None if a.dry_run else api(), a.ledger, a.run_id, dry_run=a.dry_run, sync=sync,
                          result_out=a.result_out, forbidden=[os.environ.get("RUNPOD_API_KEY", "")], resume=resume)
            if res["status"] not in ("completed", "dry_run"):
                print(f"job {job.name}: {res['status']}", file=sys.stderr)
                return 1
        elif a.cmd == "publish":
            publish(a.result, a.run_id, a.ops)
        else:
            if bool(a.job) != bool(a.run_id):
                raise LauncherError("reap: pass --job and --run-id together (or neither for the daily reap)")
            name = pod_name_for(load_spec(a.job), a.run_id) if a.job else None
            reap(api(), a.ledger, pod_name=name, force=a.force)
    except BudgetExceeded as e:
        print(e, file=sys.stderr)
        return 2
    except CapacityExhausted as e:
        print(e, file=sys.stderr)
        if a.cmd == "run" and a.journal:
            journal_failure(a.journal, job.name, a.run_id, str(e), datetime.now(timezone.utc))
        return 3
    except LauncherError as e:
        print(e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
