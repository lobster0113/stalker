import hashlib
import importlib.util
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("launcher", ROOT / "harness" / "cloud" / "launcher.py")
L = importlib.util.module_from_spec(_spec)
sys.modules["launcher"] = L  # dataclasses resolve annotations through sys.modules
_spec.loader.exec_module(L)

T0 = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)
SPEC = """# comment
name: train-a
image: ghcr.io/x/y:1
command: python -m stalker.rl.train --steps 10  # trailing comment
gpu_type: NVIDIA GeForce RTX 4090
max_minutes: 60
hourly_usd: 0.40
"""


class Clock:
    def __init__(self, t=T0):
        self.t = t

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += timedelta(seconds=s)


class FakeRunPod:
    """Mock of the RunPod REST/GraphQL surface the launcher uses."""

    def __init__(self, cost=0.34, exit_after_polls=None, fail_get=False):
        self.pods, self.calls = {}, []
        self.cost, self.exit_after, self.fail_get, self.polls = cost, exit_after_polls, fail_get, 0

    def __call__(self, method, url, body):
        self.calls.append((method, url, body))
        if url == L.GRAPHQL_URL:
            return {"data": {"myself": {"clientBalance": 99.5}}}
        path = url.removeprefix(L.REST_URL)
        if method == "POST" and path == "/pods":
            pid = f"p{len(self.pods) + 1}"
            self.pods[pid] = {"id": pid, "name": body["name"], "costPerHr": self.cost, "desiredStatus": "RUNNING"}
            return dict(self.pods[pid])
        if method == "GET" and path == "/pods":
            return list(self.pods.values())
        pid = path.split("/")[-1]
        if method == "GET":
            if self.fail_get:
                raise L.LauncherError("network down")
            self.polls += 1
            if self.exit_after is not None and self.polls > self.exit_after:
                self.pods[pid]["desiredStatus"] = "EXITED"
            return self.pods.get(pid)
        if method == "DELETE":
            self.pods.pop(pid, None)
            return {}
        raise AssertionError((method, url))

    def terminated(self):
        return [u.split("/")[-1] for m, u, _ in self.calls if m == "DELETE"]


def _job(**kw):
    return L.parse_spec(SPEC, "jobs/train-a.yaml") if not kw else L.Job(**{**L.parse_spec(SPEC).__dict__, **kw})


def _run(api, ledger, clock, job=None, cap=100.0, **kw):
    return L.run_job(job or _job(), L.RunPod(api), ledger, "42", cap=cap, now=clock, sleep=clock.sleep,
                     poll_s=60, log=lambda *_: None, **kw)


def test_parse_spec_flat_subset_and_worst_case():
    j = _job()
    assert (j.name, j.gpu_type, j.max_minutes, j.hourly_usd) == ("train-a", "NVIDIA GeForce RTX 4090", 60, 0.40)
    assert j.command == "python -m stalker.rl.train --steps 10"
    assert j.worst_case_usd == 0.40
    # a declared estimate never lowers the worst case below max time at the declared rate
    assert L.parse_spec(SPEC + "est_cost_usd: 0.05\n").worst_case_usd == 0.40
    assert L.parse_spec(SPEC + "est_cost_usd: 1.5\n").worst_case_usd == 1.5


@pytest.mark.parametrize("bad, msg", [
    (SPEC.replace("max_minutes: 60\n", ""), "missing required"),
    (SPEC + "cpu_flavor: cpu3c\n", "exactly one"),
    (SPEC + "budget: 999\n", "unknown key"),
    (SPEC + "  nested: 1\n", "flat"),
    (SPEC.replace("max_minutes: 60", "max_minutes: 331"), "360"),
    (SPEC.replace("hourly_usd: 0.40", "hourly_usd: -1.0"), "non-negative"),
    (SPEC + "name: again\n", "duplicate"),
])
def test_parse_spec_rejects_bad_specs(bad, msg):
    with pytest.raises(L.LauncherError, match=msg):
        L.parse_spec(bad)


def test_load_spec_only_from_jobs_dir(tmp_path):
    p = tmp_path / "x.yaml"
    p.write_text(SPEC, encoding="utf-8")
    with pytest.raises(L.LauncherError, match="jobs/"):
        L.load_spec(p)
    cap = json.loads((ROOT / "harness" / "budget.json").read_text(encoding="utf-8"))["monthly_cap_usd"]
    for f in (ROOT / "jobs").glob("*.yaml"):
        # Probes stay under $1; a training run (#333) may take at most a tenth of the monthly cap.
        limit = 0.1 * cap if f.stem.startswith("e3-tp-") else 1.0
        assert L.load_spec(f).worst_case_usd <= limit, f


def test_budget_rejects_over_cap_before_creating_pod(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    L.append_ledger(ledger, {"event": "start", "ts": "2026-11-01T00:00:00Z", "month": "2026-11", "job": "a",
                             "pod_id": "old", "max_minutes": 60, "reserved_usd": 50.0})
    L.append_ledger(ledger, {"event": "end", "ts": "2026-11-01T01:00:00Z", "month": "2026-11", "job": "a",
                             "pod_id": "old", "status": "completed", "actual_usd": 99.8})
    # previous month and open reservations: other months never count, open ones count at worst case
    L.append_ledger(ledger, {"event": "end", "ts": "2026-10-31T00:00:00Z", "month": "2026-10", "job": "a",
                             "pod_id": "oct", "status": "completed", "actual_usd": 80.0})
    api = FakeRunPod()
    with pytest.raises(L.BudgetExceeded, match="cap"):
        _run(api, ledger, Clock())
    assert api.calls == []
    assert len(L.read_ledger(ledger)) == 3
    # exactly at the cap is allowed
    res = _run(api, ledger, Clock(), job=_job(hourly_usd=0.2), dry_run=True, cap=100.0)
    assert res["status"] == "dry_run" and api.calls == []


def test_open_reservation_counts_until_closed(tmp_path):
    ledger = tmp_path / "l.jsonl"
    L.append_ledger(ledger, {"event": "start", "ts": "2026-11-02T00:00:00Z", "month": "2026-11", "job": "a",
                             "pod_id": "crashed", "max_minutes": 600, "reserved_usd": 99.9})
    assert L.month_total(L.read_ledger(ledger), "2026-11") == 99.9
    with pytest.raises(L.BudgetExceeded):
        _run(FakeRunPod(), ledger, Clock(), dry_run=True)


def test_run_completes_terminates_and_records_actual_cost(tmp_path):
    ledger, clock, api = tmp_path / "l.jsonl", Clock(), FakeRunPod(cost=0.34, exit_after_polls=30)
    res = _run(api, ledger, clock)
    assert res["status"] == "completed" and api.terminated() == ["p1"]
    create = next(b for m, u, b in api.calls if m == "POST")
    assert create["name"] == "stalker-train-a-42" and create["gpuTypeIds"] == ["NVIDIA GeForce RTX 4090"]
    start, end = L.read_ledger(ledger)
    assert start["event"] == "start" and start["reserved_usd"] == 0.40
    assert end["status"] == "completed" and end["minutes"] == 30.0
    assert end["actual_usd"] == pytest.approx(0.34 * 0.5)
    assert L.month_total(L.read_ledger(ledger), "2026-11") == pytest.approx(0.17)


def test_run_terminates_at_max_minutes(tmp_path):
    ledger, clock, api = tmp_path / "l.jsonl", Clock(), FakeRunPod(exit_after_polls=None)
    res = _run(api, ledger, clock)
    assert res["status"] == "timeout" and api.terminated() == ["p1"]
    assert clock.t - T0 == timedelta(minutes=60)
    assert L.read_ledger(ledger)[-1]["actual_usd"] <= 0.40


def test_run_terminates_on_error(tmp_path):
    ledger, api = tmp_path / "l.jsonl", FakeRunPod(fail_get=True)
    with pytest.raises(L.LauncherError, match="network"):
        _run(api, ledger, Clock())
    assert api.terminated() == ["p1"]
    assert L.read_ledger(ledger)[-1]["status"] == "error"
    assert L.open_entries(L.read_ledger(ledger)) == {}


def test_run_kills_pod_priced_above_spec(tmp_path):
    ledger, api = tmp_path / "l.jsonl", FakeRunPod(cost=0.89)
    with pytest.raises(L.LauncherError, match="hourly_usd"):
        _run(api, ledger, Clock())
    assert api.terminated() == ["p1"] and not any(m == "GET" for m, _, _ in api.calls)
    assert L.read_ledger(ledger)[-1]["status"] == "rate_exceeded"


def test_reap_kills_overdue_and_unknown_pods_only(tmp_path):
    ledger, api = tmp_path / "l.jsonl", FakeRunPod(cost=0.5)
    for name in ("stalker-a-1", "stalker-b-2", "stalker-c-3", "users-own-pod"):
        api("POST", f"{L.REST_URL}/pods", {"name": name})
    L.append_ledger(ledger, {"event": "start", "ts": "2026-11-03T10:00:00Z", "month": "2026-11", "job": "a",
                             "pod_id": "p1", "max_minutes": 60, "reserved_usd": 0.5})       # overdue
    L.append_ledger(ledger, {"event": "start", "ts": "2026-11-03T11:30:00Z", "month": "2026-11", "job": "b",
                             "pod_id": "p2", "max_minutes": 60, "reserved_usd": 0.5})       # still in window
    L.append_ledger(ledger, {"event": "start", "ts": "2026-11-02T00:00:00Z", "month": "2026-11", "job": "gone",
                             "pod_id": "p9", "max_minutes": 60, "reserved_usd": 0.7})       # pod vanished
    killed = L.reap(L.RunPod(api), ledger, now=Clock(), log=lambda *_: None)
    assert sorted(killed) == ["p1", "p3"]           # p3: stalker pod with no ledger entry
    assert "p4" in api.pods and "p2" in api.pods    # never touch foreign pods or in-window ones
    entries = L.read_ledger(ledger)
    assert set(L.open_entries(entries)) == {"p2"}
    orphan = [e for e in entries if e["pod_id"] == "p3" and e["event"] == "end"][0]
    assert orphan["actual_usd"] == 12.0             # 24h at $0.5/h, conservative
    # force (workflow cleanup step) ignores the deadline for the given pod
    assert L.reap(L.RunPod(api), ledger, pod_name="stalker-b-2", force=True, now=Clock(), log=lambda *_: None) == ["p2"]


@pytest.mark.parametrize("name_line", ["name: smoke-cpu  # tiny", 'name: "smoke-cpu"', "name: 'smoke-cpu' # q"])
def test_cleanup_step_finds_pod_by_parsed_spec_name(tmp_path, name_line, monkeypatch):
    jobs = ROOT / "jobs"
    spec = (jobs / "smoke-cpu.yaml").read_text(encoding="utf-8").replace("name: smoke-cpu", name_line)
    p = jobs / "_test_cleanup.yaml"
    p.write_text(spec, encoding="utf-8")
    try:
        api = FakeRunPod(cost=0.1)
        api("POST", f"{L.REST_URL}/pods", {"name": "stalker-smoke-cpu-77"})
        api("POST", f"{L.REST_URL}/pods", {"name": "stalker-smoke-cpu-770"})   # other run, same prefix
        monkeypatch.setenv("RUNPOD_API_KEY", "k")
        monkeypatch.setattr(L, "http_transport", lambda key: api)
        ledger = tmp_path / "l.jsonl"
        assert L.main(["reap", "--ledger", str(ledger), "--force", "--job", str(p), "--run-id", "77"]) == 0
        assert api.terminated() == ["p1"]
    finally:
        p.unlink()


def test_reap_never_double_bills_ended_pod(tmp_path):
    ledger, clock, api = tmp_path / "l.jsonl", Clock(), FakeRunPod(exit_after_polls=2)
    _run(api, ledger, clock)
    before = L.month_total(L.read_ledger(ledger), "2026-11")
    api.pods["p1"] = {"id": "p1", "name": "stalker-train-a-42", "costPerHr": 0.34}  # list lags the DELETE
    L.reap(L.RunPod(api), ledger, pod_name="stalker-train-a-42", force=True, now=clock, log=lambda *_: None)
    L.reap(L.RunPod(api), ledger, now=clock, log=lambda *_: None)
    assert L.month_total(L.read_ledger(ledger), "2026-11") == before
    assert api.terminated().count("p1") >= 2   # terminate re-sent, no new ledger lines
    assert len(L.read_ledger(ledger)) == 2


def test_reservation_is_synced_before_polling_and_sync_failure_terminates(tmp_path):
    ledger, api = tmp_path / "l.jsonl", FakeRunPod(exit_after_polls=1)
    seen = []

    def sync():
        seen.append([e["event"] for e in L.read_ledger(ledger)])
        assert not any(m == "GET" for m, _, _ in api.calls)   # before the pod is polled

    _run(api, ledger, Clock(), sync=sync)
    assert seen == [["start"]]

    ledger2, api2 = tmp_path / "l2.jsonl", FakeRunPod(exit_after_polls=1)

    def broken():
        raise RuntimeError("push rejected")

    with pytest.raises(L.LauncherError, match="ledger sync failed"):
        _run(api2, ledger2, Clock(), sync=broken)
    assert api2.terminated() == ["p1"]
    assert L.read_ledger(ledger2)[-1]["status"] == "error"


def test_check_reads_balance():
    assert L.RunPod(FakeRunPod()).balance() == 99.5


def test_main_dry_run_and_budget_exit_codes(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("RUNPOD_API_KEY", raising=False)
    ledger = tmp_path / "l.jsonl"
    assert L.main(["run", str(ROOT / "jobs" / "smoke-cpu.yaml"), "--ledger", str(ledger), "--dry-run"]) == 0
    assert "would create pod stalker-smoke-cpu-" in capsys.readouterr().out
    assert not ledger.exists()
    L.append_ledger(ledger, {"event": "end", "ts": "x", "month": datetime.now(timezone.utc).strftime("%Y-%m"),
                             "job": "a", "pod_id": "z", "status": "completed", "actual_usd": 100.0})
    assert L.main(["run", str(ROOT / "jobs" / "smoke-cpu.yaml"), "--ledger", str(ledger), "--dry-run"]) == 2
    assert L.main(["check"]) == 1 and "RUNPOD_API_KEY" in capsys.readouterr().err


def test_budget_cap_is_user_decision():
    # NH-1: user set $100/month. Raising it needs a user decision (reviewer.md), never an agent PR.
    assert json.loads((ROOT / "harness" / "budget.json").read_text(encoding="utf-8")) == {"monthly_cap_usd": 100}
    assert "budget.json" in (ROOT / "harness" / "routines" / "reviewer.md").read_text(encoding="utf-8")


def test_cloud_workflow_guards():
    wf = (ROOT / ".github" / "workflows" / "cloud.yml").read_text(encoding="utf-8")
    on = wf.split("\non:\n", 1)[1].split("\n\n", 1)[0]
    assert "workflow_dispatch:" in on and "schedule:" in on
    assert not any(t in on for t in ("pull_request", "push:", "workflow_run"))
    assert re.findall(r"secrets\.(\w+)", wf) == ["RUNPOD_API_KEY"]
    # #350: runs of different jobs in parallel, same job serial; check/reap/collect share one group
    assert "format('cloud-run-{0}', inputs.job)" in wf and "'cloud-budget'" in wf
    assert "cancel-in-progress: false" in wf
    (minutes,) = re.findall(r"timeout-minutes: (\d+)", wf)
    assert L.MAX_JOB_MINUTES + 15 <= int(minutes) <= 360   # GitHub-hosted runner job limit
    cleanup = wf.split("terminate this run's pods", 1)[1].split("- name:", 1)[0]
    assert "if: always()" in cleanup.split("\n")[1]
    assert '--force --job "$JOB" --run-id "$GITHUB_RUN_ID"' in cleanup and "sed" not in cleanup
    assert "--sync-cmd" in wf and "push_ledger.sh" in wf
    assert "if: always()" in wf.split("- name: push ledger", 1)[1].split("\n")[1]
    assert all("${{ inputs." not in line for line in wf.splitlines() if "launcher.py" in line or "case" in line)


def test_http_transport_sends_a_user_agent(monkeypatch):
    import urllib.request

    seen = {}

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"{}"

    def fake(req, timeout=0):
        seen.update({k.lower(): v for k, v in req.header_items()})
        return Resp()

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    launcher = L
    launcher.http_transport("k")("GET", launcher.REST_URL + "/pods", None)
    assert seen["user-agent"].startswith("stalker-launcher/") and "python-urllib" not in seen["user-agent"].lower()
    assert seen["accept"] == "application/json"


def test_spec_names_use_forward_slashes_on_windows_paths():
    # #225: str() of a Windows path has backslashes, so the jobs/<name>.yaml check refused every spec there.
    from pathlib import PureWindowsPath

    root = PureWindowsPath(r"C:\repo")
    assert L._rel_posix(PureWindowsPath(r"C:\repo\jobs\smoke-cpu.yaml"), root) == "jobs/smoke-cpu.yaml"
    assert L._rel_posix(PureWindowsPath(r"C:\elsewhere\x.yaml"), root) == "C:/elsewhere/x.yaml"


def test_relative_windows_spec_paths_and_nesting(tmp_path, monkeypatch):
    from pathlib import PureWindowsPath

    assert L._rel_posix(PureWindowsPath(r"jobs\x.yaml"), PureWindowsPath(r"C:\repo")) == "jobs/x.yaml"
    monkeypatch.setattr(L, "ROOT", tmp_path)
    (tmp_path / "jobs" / "sub").mkdir(parents=True)
    (tmp_path / "jobs" / "x.yaml").write_text(SPEC, encoding="utf-8")
    (tmp_path / "jobs" / "sub" / "x.yaml").write_text(SPEC, encoding="utf-8")
    assert L.load_spec(tmp_path / "jobs" / "x.yaml").name
    with pytest.raises(L.LauncherError, match="jobs/"):
        L.load_spec(tmp_path / "jobs" / "sub" / "x.yaml")


# ---------- result retrieval (#184, ADR 0014) ----------

TOKEN = "t" * 32


class FakeProxy:
    """RunPod HTTP proxy in front of the pod's result server: status.json appears after `ready_after` polls."""

    def __init__(self, status=b'{"exit": 0}', result=b'{"lbr_bb": 1.25}', ready_after=3, up_after=1, put_code=200,
                 booting_code=0):
        self.status, self.result, self.ready_after, self.urls = status, result, ready_after, []
        self.up_after, self.put_code, self.puts, self.booting_code = up_after, put_code, [], booting_code

    def send(self, url, body):
        """PUT: the proxy answers 502 (0) for `up_after` tries while the pod boots, then the server takes it."""
        assert url.startswith(f"https://p1-{L.RESULT_PORT}.proxy.runpod.net/{TOKEN}/")
        self.puts.append((url.rsplit("/", 1)[1], body))
        if len(self.puts) <= self.up_after:
            return self.booting_code, b""
        if self.put_code != 200:
            return self.put_code, b""
        return 200, json.dumps({"bytes": len(body), "sha256": __import__("hashlib").sha256(body).hexdigest()}).encode()

    def __call__(self, url, max_bytes):
        self.urls.append(url)
        name = url.rsplit("/", 1)[1]
        assert url.startswith(f"https://p1-{L.RESULT_PORT}.proxy.runpod.net/{TOKEN}/")
        if name == "status.json":
            if sum(u.endswith("status.json") for u in self.urls) <= self.ready_after:
                return 0, b""  # proxy 502 while the job is still running
            return 200, self.status[:max_bytes + 1]
        if name == "result.json" and self.result is not None:
            return 200, self.result[:max_bytes + 1]
        return 404, b""


def _result_job(**kw):
    return _job(result_path="/work/out/result.json", **kw)


def _run_result(tmp_path, proxy, api=None, **kw):
    ledger, clock, api = tmp_path / "l.jsonl", Clock(), api or FakeRunPod()
    out = tmp_path / "res" / "result.json"
    res = _run(api, ledger, clock, job=_result_job(), result_out=out, fetch=proxy, send=proxy.send, token=TOKEN, **kw)
    return res, api, L.read_ledger(ledger), out


def test_result_path_spec_validation():
    job = L.parse_spec(SPEC + "result_path: /work/out/result.json\n")
    assert job.result_path == "/work/out/result.json"
    for bad in ("out/result.json", "/work/$(id).json", "/work/a b.json"):
        with pytest.raises(L.LauncherError, match="result_path"):
            L.parse_spec(SPEC + f"result_path: {bad}\n")


def test_result_job_create_body_and_command(tmp_path):
    res, api, entries, out = _run_result(tmp_path, FakeProxy())
    create = next(b for m, u, b in api.calls if m == "POST")
    assert create["ports"] == [f"{L.RESULT_PORT}/http"] and create["env"] == {L.TOKEN_ENV: TOKEN}
    script = create["dockerStartCmd"][2]
    assert TOKEN not in script and "python -m stalker.rl.train --steps 10" in script
    assert script.splitlines()[-1] == "sleep infinity" and L.POD_SERVER.strip() in script
    plain = _run(FakeRunPod(exit_after_polls=1), tmp_path / "l2.jsonl", Clock())
    assert plain["status"] == "completed"  # jobs without result_path behave as before
    body = []
    L.RunPod(lambda m, u, b: body.append(b) or {"id": "x"}).create(_job(), "n")
    assert "ports" not in body[0] and "env" not in body[0] and body[0]["dockerStartCmd"][2] == _job().command


def test_result_is_pulled_saved_and_recorded(tmp_path):
    proxy = FakeProxy()
    res, api, entries, out = _run_result(tmp_path, proxy)
    assert res["status"] == "completed" and api.terminated() == ["p1"]
    assert json.loads(out.read_text(encoding="utf-8")) == {"lbr_bb": 1.25}
    end = entries[-1]
    assert end["result_bytes"] == len(proxy.result) and end["exit"] == 0
    assert end["result_sha256"] == __import__("hashlib").sha256(proxy.result).hexdigest()
    assert TOKEN not in json.dumps(entries)  # the ledger is pushed to a public branch


def test_result_size_limit_fits_a_pod_checkpoint():
    # #346: a pod training result (#333) carries its model; 21 MB passes, the cap still rejects.
    body = b'{"x": "' + b"a" * (21 * 1024 * 1024) + b'"}'
    L.check_result(body)
    assert L.RESULT_MAX_BYTES == 256 * 1024 * 1024
    with pytest.raises(L.LauncherError, match="bytes"):
        L.check_result(body, max_bytes=1024)


def test_result_rejected_when_oversized_non_json_or_secret(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "RESULT_MAX_BYTES", 4096)  # the size path, without a 256 MB body
    cases = {
        "big": b'{"x": "' + b"a" * L.RESULT_MAX_BYTES + b'"}',
        "nonjson": b"\x00\x01 not json",
        "ghtoken": b'{"note": "ghp_' + b"A" * 36 + b'"}',
        "launcher": b'{"echo": "' + TOKEN.encode() + b'"}',
        "apikey": b'{"k": "sekret-runpod-key"}',
    }
    for name, body in cases.items():
        d = tmp_path / name
        d.mkdir()
        res, api, entries, out = _run_result(d, FakeProxy(result=body), forbidden=["sekret-runpod-key"])
        assert res["status"] == "result_rejected", name
        assert not out.exists() and api.terminated() == ["p1"]
        assert "result_sha256" not in entries[-1]


def test_result_job_failed_command_missing_result_and_early_exit(tmp_path):
    for name, proxy, api, status in [
        ("failed", FakeProxy(status=b'{"exit": 3}'), None, "failed"),
        ("missing", FakeProxy(result=None), None, "no_result"),
        ("exited", FakeProxy(ready_after=10**6), FakeRunPod(exit_after_polls=2), "no_result"),
    ]:
        d = tmp_path / name
        d.mkdir()
        res, api, entries, out = _run_result(d, proxy, api=api)
        assert res["status"] == status and entries[-1]["status"] == status, name
        assert not out.exists() and api.terminated() == ["p1"]


def test_result_job_times_out_and_needs_result_out(tmp_path):
    res, api, entries, out = _run_result(tmp_path, FakeProxy(ready_after=10**6))
    assert res["status"] == "timeout" and api.terminated() == ["p1"]
    api2 = FakeRunPod()
    with pytest.raises(L.LauncherError, match="result-out"):
        _run(api2, tmp_path / "l2.jsonl", Clock(), job=_result_job())
    assert api2.calls == []  # refused before any pod exists


def test_http_fetch_sends_no_credentials_and_caps_reads(monkeypatch):
    import urllib.request

    seen = {}

    class Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n=-1):
            seen["n"] = n
            return b"{}"

    def fake_urlopen(req, timeout):
        seen["headers"] = {k.lower() for k in req.headers}
        return Resp()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert L.http_fetch("https://p-8000.proxy.runpod.net/t/status.json", 10) == (200, b"{}")
    assert "authorization" not in seen["headers"] and "user-agent" in seen["headers"] and seen["n"] == 11

    def down(req, timeout):
        raise urllib.error.URLError("refused")

    monkeypatch.setattr(urllib.request, "urlopen", down)
    assert L.http_fetch("https://x/y", 10) == (0, b"")


def _free_port():
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _http(port, path, body=None):
    import urllib.request
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=body,
                                 method="PUT" if body is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except OSError:
        return 0, b""


def _wait(port, path, code=200, tries=150):
    import time
    for _ in range(tries):
        got = _http(port, path)
        if got[0] == code:
            return got
        time.sleep(0.1)
    raise AssertionError(f"{path} never answered {code}")


@pytest.fixture
def pod_server(tmp_path):
    """The pod's result/resume server (launcher.POD_SERVER) as a real process, with a 1000-byte upload cap."""
    import os
    import subprocess
    port, root, rdir = _free_port(), tmp_path / "srv", tmp_path / "rs"
    root.mkdir(), rdir.mkdir()
    proc = subprocess.Popen([sys.executable, "-c", L.POD_SERVER, str(root), str(port), str(rdir), "1000"],
                            env={**os.environ, L.TOKEN_ENV: TOKEN})
    try:
        _wait(port, f"/{TOKEN}/status.json", code=404)
        yield port, root, rdir
    finally:
        proc.kill()
        proc.wait()


def test_pod_server_takes_one_capped_upload_and_serves_only_token_names(pod_server):
    port, root, rdir = pod_server
    (root / "status.json").write_text('{"exit": 0}', encoding="utf-8")
    assert _http(port, f"/{TOKEN}/status.json") == (200, b'{"exit": 0}')
    for path in ("/", f"/{TOKEN}/", "/status.json", f"/{'u' * 32}/status.json", f"/{TOKEN}/../srv/status.json"):
        assert _http(port, path)[0] == 404, path
    assert _http(port, f"/{'u' * 32}/resume", b"x")[0] == 404  # wrong token
    assert _http(port, f"/{TOKEN}/resume", b"x" * 1001)[0] in (413, 0)  # over the cap: refused, nothing kept
    assert not (rdir / "signal").exists() and not (rdir / "resume.bin").exists()
    body = b"\x1f\x8b" + bytes(range(256)) * 3
    code, raw = _http(port, f"/{TOKEN}/resume", body)
    assert code == 200
    assert json.loads(raw) == {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}
    assert (rdir / "resume.bin").read_bytes() == body and (rdir / "signal").read_text(encoding="utf-8") == "ready"
    assert _http(port, f"/{TOKEN}/resume-none", b"")[0] == 409  # one signal only
    assert _http(port, f"/{TOKEN}/resume.bin")[0] == 404  # the upload is not served back


def test_pod_server_none_signal(pod_server):
    port, root, rdir = pod_server
    assert _http(port, f"/{TOKEN}/resume-none", b"")[0] == 200
    assert (rdir / "signal").read_text(encoding="utf-8") == "none" and not (rdir / "resume.bin").exists()


@pytest.mark.skipif(sys.platform == "win32", reason="the pod script is bash on Linux")
@pytest.mark.parametrize("resume", [None, b'{"ok": 2}'], ids=["none", "upload"])
def test_pod_command_waits_for_the_resume_signal_then_serves_the_result(tmp_path, resume):
    """Runs the wrapped script with bash and the real server, as the pod would."""
    import os
    import signal
    import subprocess
    import time

    port, work = _free_port(), tmp_path / "work"
    cmd = (f'mkdir -p {work} && if [ -n "$STALKER_RESUME" ]; then cat "$STALKER_RESUME"; '
           f"else echo '{{\"ok\": 1}}'; fi > {work}/r.json")
    job = _job(command=cmd, result_path=f"{work}/r.json")
    script = L.pod_command(job, serve_dir=str(tmp_path / "srv"), port=port,
                           resume_dir=str(tmp_path / "rs")).replace("sleep infinity", "sleep 30")
    proc = subprocess.Popen(["bash", "-c", script], env={"PATH": "/usr/bin:/bin:" + str(Path(sys.executable).parent),
                                                         L.TOKEN_ENV: TOKEN}, start_new_session=True)
    try:
        time.sleep(0.5)
        assert not work.exists()  # the job waits for the signal
        for _ in range(150):
            if _http(port, f"/{TOKEN}/resume" if resume else f"/{TOKEN}/resume-none", resume or b"")[0] == 200:
                break
            time.sleep(0.1)
        _, body = _wait(port, f"/{TOKEN}/status.json")
        assert json.loads(body) == {"exit": 0}
        assert json.loads(_http(port, f"/{TOKEN}/result.json")[1]) == {"ok": 2 if resume else 1}
        assert _http(port, "/")[0] == 404
    finally:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()


@pytest.mark.skipif(sys.platform == "win32", reason="the pod script is bash on Linux")
def test_pod_command_without_a_signal_skips_the_job(tmp_path):
    import subprocess
    work = tmp_path / "work"
    job = _job(command=f"mkdir -p {work}", result_path=f"{work}/r.json")
    script = L.pod_command(job, serve_dir=str(tmp_path / "srv"), port=_free_port(), resume_dir=str(tmp_path / "rs"),
                           wait_s=2).replace("sleep infinity", "exit 0")
    script = script.replace("python3 - ", "true ", 1)  # no server: nobody can signal
    subprocess.run(["bash", "-c", script], env={"PATH": "/usr/bin:/bin", L.TOKEN_ENV: TOKEN}, timeout=30, check=True)
    assert not work.exists()
    assert json.loads((tmp_path / "srv" / TOKEN / "status.json").read_text(encoding="utf-8")) == {"exit": 97}


def _pod_result(tmp_path, **kw):
    r = {"job": "e3-tp-pro-pod", "tier": "pro", "players": 6, "seed": 1, "iters": 7, "lbr": {"x": 1},
         "model": {"k": 17, "n": 6}, "checkpoint": {"format": "npz", "dtype": "float64", "b64": "QUJD"}} | kw
    f = tmp_path / "resume" / "result.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(r), encoding="utf-8")
    return f


def test_resume_payload_is_trimmed_gzipped_and_capped(tmp_path):
    import gzip
    f = _pod_result(tmp_path)
    got = json.loads(gzip.decompress(L.resume_payload(f, "123")))
    assert got["run_id"] == "123" and got["iters"] == 7 and got["checkpoint"]["b64"] == "QUJD"
    assert "lbr" not in got  # evaluation numbers stay in the artifact
    with pytest.raises(L.LauncherError, match="proxy body limit"):
        L.resume_payload(f, "123", max_bytes=50)
    with pytest.raises(L.LauncherError, match="digits"):
        L.resume_payload(f, "12;rm")
    with pytest.raises(L.LauncherError, match="no checkpoint"):
        L.resume_payload(_pod_result(tmp_path, checkpoint=None), "123")
    with pytest.raises(L.LauncherError, match="downloaded"):
        L.resume_payload(tmp_path / "missing.json", "123")
    assert L.RESUME_MAX_BYTES < 100 * 1024 * 1024  # Cloudflare's request body limit in front of the proxy


def test_resume_is_uploaded_before_the_result_is_polled(tmp_path):
    proxy = FakeProxy(up_after=2)
    res, api, entries, out = _run_result(tmp_path, proxy, resume=b"\x1f\x8bpayload")
    assert res["status"] == "completed" and json.loads(out.read_text(encoding="utf-8")) == {"lbr_bb": 1.25}
    assert proxy.puts == [("resume", b"\x1f\x8bpayload")] * 3  # retried while the proxy said 502
    assert sum(u.endswith("status.json") for u in proxy.urls) == proxy.ready_after + 1
    assert TOKEN not in json.dumps(entries) and entries[-1]["status"] == "completed"


@pytest.mark.parametrize("booting_code", [404, 502])
def test_signal_retries_while_the_proxy_routes_the_new_pod(tmp_path, booting_code):
    # #361: the RunPod proxy answered 404 right after creation (run 40886839070) and the launcher gave up
    proxy = FakeProxy(up_after=2, booting_code=booting_code)
    res, api, entries, out = _run_result(tmp_path, proxy)
    assert res["status"] == "completed" and proxy.puts == [("resume-none", b"")] * 3


def test_no_resume_signals_none(tmp_path):
    proxy = FakeProxy(up_after=0)
    res, *_ = _run_result(tmp_path, proxy)
    assert res["status"] == "completed" and proxy.puts == [("resume-none", b"")]


class _Garbled(FakeProxy):
    def send(self, url, body):
        self.puts.append((url.rsplit("/", 1)[1], body))
        return 200, b'{"bytes": 1, "sha256": "0"}'


@pytest.mark.parametrize("proxy,msg", [(lambda: FakeProxy(up_after=0, put_code=413), "cap"),
                                       (lambda: FakeProxy(up_after=0, put_code=403), "refused"),
                                       (lambda: _Garbled(), "received")], ids=["oversized", "refused", "garbled"])
def test_resume_refused_or_garbled_terminates(tmp_path, proxy, msg):
    p = proxy()
    with pytest.raises(L.LauncherError, match=msg):
        _run_result(tmp_path, p, resume=b"xy")
    entries = L.read_ledger(tmp_path / "l.jsonl")
    assert entries[-1]["status"] == "resume_failed" and entries[-1]["event"] == "end"
    assert not any(u.endswith("status.json") for u in p.urls)  # the job never got its file: no result taken


def test_resume_lost_reply_then_409_carries_on(tmp_path):
    # only this launcher knows the token, so a 409 means an earlier try of ours landed
    res, *_ = _run_result(tmp_path, FakeProxy(up_after=0, put_code=409), resume=b"x")
    assert res["status"] == "completed"


def test_resume_needs_a_result_job_and_is_checked_in_dry_run(tmp_path, capsys):
    with pytest.raises(L.LauncherError, match="result_path"):
        _run(FakeRunPod(), tmp_path / "l.jsonl", Clock(), resume=b"x")
    f = _pod_result(tmp_path)
    ledger = tmp_path / "l2.jsonl"
    spec = ROOT / "jobs" / "e3-tp-pro-pod32.yaml"
    assert L.main(["run", str(spec), "--ledger", str(ledger), "--dry-run", "--resume-file", str(f),
                   "--resume-run", "55"]) == 0
    assert "resume upload" in capsys.readouterr().out
    assert L.main(["run", str(spec), "--ledger", str(ledger), "--dry-run", "--resume-file", str(f)]) == 1
    assert "together" in capsys.readouterr().err


def test_cloud_workflow_resume_run_input():
    wf = (ROOT / ".github" / "workflows" / "cloud.yml").read_text(encoding="utf-8")
    assert "resume_run:" in wf and "RESUME_RUN: ${{ inputs.resume_run }}" in wf
    check = wf.split("- name: check resume_run", 1)[1].split("- name:", 1)[0]
    assert '"$RESUME_RUN" =~ ^[0-9]+$' in check and "${{" not in check
    fetch = wf.split("- name: fetch resume result", 1)[1].split("- name:", 1)[0]
    assert "env.RESUME_RUN != ''" in fetch and "actions/download-artifact@v4" in fetch
    assert "run-id: ${{ env.RESUME_RUN }}" in fetch and "github-token: ${{ github.token }}" in fetch
    assert "resume/" in fetch
    # validated before the download uses it, downloaded before the launcher runs
    assert wf.index("- name: check resume_run") < wf.index("- name: fetch resume result") < wf.index("- name: launcher")
    assert '--resume-file "$RUNNER_TEMP/resume/result.json" --resume-run "$RESUME_RUN"' in wf


def test_cloud_workflow_uploads_result():
    wf = (ROOT / ".github" / "workflows" / "cloud.yml").read_text(encoding="utf-8")
    assert '--result-out "$RUNNER_TEMP/cloud-result/result.json"' in wf
    up = wf.split("- name: upload result", 1)[1].split("- name:", 1)[0]
    assert "if: always()" in up and "actions/upload-artifact@v4" in up and "cloud-result/" in up


def test_publish_copies_checked_result_to_ops(tmp_path, capsys):
    src, ops = tmp_path / "result.json", tmp_path / "ops"
    src.write_text('{"iters_per_s": 400}', encoding="utf-8")
    dst = L.publish(src, "40778103365", ops, log=lambda _m: None)
    assert dst == ops / "cloud" / "results" / "40778103365.json" and dst.read_bytes() == src.read_bytes()
    with pytest.raises(L.LauncherError, match="digits"):
        L.publish(src, "../x", ops)
    src.write_text('{"k": "ghp_' + "a" * 36 + '"}', encoding="utf-8")
    with pytest.raises(L.LauncherError, match="secret"):
        L.publish(src, "2", ops)
    assert not (ops / "cloud" / "results" / "2.json").exists()
    src.write_text(json.dumps({"x": "a" * L.OPS_RESULT_MAX_BYTES}), encoding="utf-8")
    assert L.publish(src, "3", ops, log=lambda _m: None) is None and not (ops / "cloud" / "results" / "3.json").exists()
    src.write_text("{}", encoding="utf-8")
    assert L.main(["publish", str(src), "--run-id", "4", "--ops", str(ops)]) == 0
    assert L.main(["publish", str(src), "--run-id", "x4", "--ops", str(ops)]) == 1 and "digits" in capsys.readouterr().err


def test_push_ledger_commits_published_results(tmp_path):
    import subprocess

    def git(*a, cwd):
        subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True)

    remote, wt = tmp_path / "remote.git", tmp_path / "ops"
    git("init", "-q", "--bare", "-b", "ops", str(remote), cwd=tmp_path)
    git("clone", "-q", str(remote), str(wt), cwd=tmp_path)
    git("checkout", "-q", "-b", "ops", cwd=wt)
    (wt / "cloud" / "results").mkdir(parents=True)
    (wt / "cloud" / "results" / "9.json").write_text("{}", encoding="utf-8")
    subprocess.run(["bash", str(ROOT / "harness" / "cloud" / "push_ledger.sh"), str(wt), "cloud: collect 9"],
                   check=True, capture_output=True)
    files = subprocess.run(["git", "ls-tree", "-r", "--name-only", "ops"], cwd=remote, check=True,
                           capture_output=True, text=True, encoding="utf-8").stdout.split()
    assert files == ["cloud/results/9.json"]


def test_cloud_workflow_collect_mode_and_result_to_ops():
    wf = (ROOT / ".github" / "workflows" / "cloud.yml").read_text(encoding="utf-8")
    assert "collect)" in wf and "actions: read" in wf and "COLLECT_RUN: ${{ inputs.collect_run }}" in wf
    fetch = wf.split("- name: fetch earlier result", 1)[1].split("- name:", 1)[0]
    assert "if: env.MODE == 'collect'" in fetch and "actions/download-artifact@v4" in fetch
    assert "run-id: ${{ inputs.collect_run }}" in fetch and "cloud-result/" in fetch
    # publish runs after upload and before the ledger push, which commits cloud/results too
    i_up, i_pub, i_push = (wf.index(s) for s in ("- name: upload result", "- name: result to ops", "- name: push ledger"))
    assert i_up < i_pub < i_push
    pub = wf[i_pub:i_push]
    assert "if: always()" in pub and "launcher.py publish" in pub and "${{ inputs." not in pub


def test_parallel_reservation_over_cap_terminates_after_sync(tmp_path):
    # #350: another run's reservation arrives with our sync; together they pass the cap -> stop ours
    ledger, api = tmp_path / "l.jsonl", FakeRunPod(exit_after_polls=5)

    def sync():  # what a pull brings in: a parallel run reserved $0.80 of the $1.00 cap
        L.append_ledger(ledger, {"event": "start", "ts": "2026-11-01T00:00:00Z", "month": "2026-11", "job": "other",
                                 "pod_id": "q9", "pod_name": "stalker-other-7", "run_id": "7", "max_minutes": 60,
                                 "reserved_usd": 0.8})

    with pytest.raises(L.BudgetExceeded, match="parallel run"):
        _run(api, ledger, Clock(), cap=1.0, sync=sync)
    assert api.terminated() == ["p1"] and not any(m == "GET" for m, _, _ in api.calls)
    end = L.read_ledger(ledger)[-1]
    assert end["status"] == "over_cap" and end["pod_id"] == "p1"


def test_push_ledger_union_merges_parallel_appends(tmp_path):
    import shutil
    import subprocess
    if shutil.which("git") is None or shutil.which("bash") is None:
        pytest.skip("needs git and bash")
    sh = str(ROOT / "harness" / "cloud" / "push_ledger.sh")

    def git(cwd, *a):
        return subprocess.run(["git", "-C", str(cwd), *a], check=True, capture_output=True, text=True,
                              encoding="utf-8")

    NL = b"\n"
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "ops", str(remote))
    seed = tmp_path / "seed"
    git(tmp_path, "clone", "-q", str(remote), str(seed))
    (seed / "budget").mkdir()
    (seed / "budget" / "ledger.jsonl").write_bytes(b'{"n": 0}' + NL)
    git(seed, "add", "budget/ledger.jsonl")
    git(seed, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "seed")
    git(seed, "push", "-q", "origin", "HEAD:ops")
    a, b = tmp_path / "a", tmp_path / "b"
    for d in (a, b):
        git(tmp_path, "clone", "-q", "-b", "ops", str(remote), str(d))
    for d, n in ((a, 1), (b, 2)):
        with open(d / "budget" / "ledger.jsonl", "ab") as f:
            f.write(b'{"n": %d}' % n + NL)
    for d in (a, b):  # b pushes second: its rebase meets a's line at the same end of file
        subprocess.run(["bash", sh, str(d), "test"], check=True, capture_output=True)
    check = tmp_path / "check"
    git(tmp_path, "clone", "-q", "-b", "ops", str(remote), str(check))
    lines = (check / "budget" / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    assert sorted(lines) == ['{"n": 0}', '{"n": 1}', '{"n": 2}']
