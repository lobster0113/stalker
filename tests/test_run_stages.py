"""#841: the stage runner turns a failing stage into a retrievable stage-failure JSON (#853: deadline)."""
import json
import sys
import time

import pytest

from stalker.tools import run_stages

PY = sys.executable


def _run(tmp_path, *stages, deadline=None):
    out = tmp_path / "out.json"
    args = ["--out", str(out)] + ([] if deadline is None else ["--deadline-s", str(deadline)])
    for s in stages:
        args += ["--stage", s]
    return run_stages.main(args), out


def test_all_stages_ok_leaves_out_untouched(tmp_path):
    code, out = _run(tmp_path, "a=true", "b=true")
    assert code == 0 and not out.exists()


def test_failing_stage_is_reported_and_later_stages_skipped(tmp_path):
    marker = tmp_path / "third"
    code, out = _run(tmp_path, "one=true", "two=exit 3", f"three=touch {marker}")
    assert code == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["schema"] == "stalker.cloud.stage-failure" and doc["schema_version"] == 2
    assert doc["stage"] == "two" and doc["exit"] == 3 and doc["stages_done"] == ["one"]
    assert "max_rss_kb" in doc and "elapsed_s" in doc
    assert set(doc["stage_elapsed_s"]) == {"one", "two"} and doc["deadline_s"] is None
    assert not marker.exists()


def test_stderr_tail_is_last_200_lines_and_small(tmp_path):
    cmd = f"{PY} -c \"import sys; [print('x'*900+str(i), file=sys.stderr) for i in range(1000)]; sys.exit(1)\""
    code, out = _run(tmp_path, f"big={cmd}")
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert code == 0 and len(doc["stderr_tail"]) == 200
    assert doc["stderr_tail"][-1].endswith("999") is False  # truncated to 500 chars per line
    assert all(len(line) <= 500 for line in doc["stderr_tail"])
    assert out.stat().st_size < 1_000_000


def test_success_logs_each_stage_time(tmp_path, capsys):
    code, out = _run(tmp_path, "a=true", "b=true")
    err = capsys.readouterr().err
    assert code == 0 and not out.exists()
    assert "[run_stages] stage a done in" in err and "[run_stages] stage b done in" in err


def _alive(pid):
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as f:
            state = f.read().rsplit(")", 1)[1].split()[0]
    except FileNotFoundError:
        return False
    return state != "Z"


def test_deadline_stops_running_stage_and_its_grandchildren(tmp_path):
    marker, pidfile = tmp_path / "after", tmp_path / "pid"
    t0 = time.monotonic()
    code, out = _run(tmp_path, "quick=true", f"slow=sh -c 'sleep 30 & echo $! > {pidfile}; wait'",
                     f"after=touch {marker}", deadline=2)
    assert time.monotonic() - t0 < 5
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert code == 0 and doc["exit"] == "timeout" and doc["stage"] == "slow" and doc["deadline_s"] == 2
    assert doc["stages_done"] == ["quick"] and set(doc["stage_elapsed_s"]) == {"quick", "slow"}
    assert not marker.exists()
    assert not _alive(int(pidfile.read_text(encoding="utf-8")))


def test_rejects_non_positive_deadline(tmp_path):
    with pytest.raises(SystemExit):
        _run(tmp_path, "a=true", deadline=0)
