"""#841: the stage runner turns a failing stage into a retrievable stage-failure JSON."""
import json
import sys

from stalker.tools import run_stages

PY = sys.executable


def _run(tmp_path, *stages):
    out = tmp_path / "out.json"
    args = ["--out", str(out)]
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
    assert doc["schema"] == "stalker.cloud.stage-failure" and doc["schema_version"] == 1
    assert doc["stage"] == "two" and doc["exit"] == 3 and doc["stages_done"] == ["one"]
    assert "max_rss_kb" in doc and "elapsed_s" in doc
    assert not marker.exists()


def test_stderr_tail_is_last_200_lines_and_small(tmp_path):
    cmd = f"{PY} -c \"import sys; [print('x'*900+str(i), file=sys.stderr) for i in range(1000)]; sys.exit(1)\""
    code, out = _run(tmp_path, f"big={cmd}")
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert code == 0 and len(doc["stderr_tail"]) == 200
    assert doc["stderr_tail"][-1].endswith("999") is False  # truncated to 500 chars per line
    assert all(len(line) <= 500 for line in doc["stderr_tail"])
    assert out.stat().st_size < 1_000_000
