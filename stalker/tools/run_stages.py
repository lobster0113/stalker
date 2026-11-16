"""Run shell stages in order; on a failing stage write a stage-failure JSON and still exit 0 (#841).

The cloud launcher only retrieves the result file when the job command exits 0, so a failing stage's
exit code, elapsed time and stderr tail would otherwise be lost with the pod. `--deadline-s` (#853)
stops the running stage before the pod's own limit cuts everything, so a timeout is still retrievable.
"""
import argparse
import collections
import json
import os
import pathlib
import resource
import signal
import subprocess
import sys
import threading
import time

SCHEMA = "stalker.cloud.stage-failure"
SCHEMA_VERSION = 2
TAIL_LINES = 200
LINE_CHARS = 500
TERM_GRACE_S = 10.0


def _killpg(pgid: int, sig: int) -> None:
    try:
        os.killpg(pgid, sig)
    except ProcessLookupError:
        pass


def _stop_group(proc: subprocess.Popen) -> None:
    # The stage runs in its own session, so its pgid is its pid; killing the group also reaches
    # grandchildren such as multiprocessing Pool workers that would otherwise keep stderr open.
    _killpg(proc.pid, signal.SIGTERM)
    try:
        proc.wait(timeout=TERM_GRACE_S)
    except subprocess.TimeoutExpired:
        pass
    _killpg(proc.pid, signal.SIGKILL)


def run_stage(command: str, tail: collections.deque, remaining_s: float | None = None) -> tuple[int, bool]:
    """Return (exit code, timed_out)."""
    proc = subprocess.Popen(command, shell=True, stderr=subprocess.PIPE, encoding="utf-8", errors="replace",
                            start_new_session=True)
    done = threading.Event()
    timed_out = threading.Event()

    def watchdog():
        if not done.wait(remaining_s):
            timed_out.set()
            _stop_group(proc)

    guard = threading.Thread(target=watchdog, daemon=True) if remaining_s is not None else None
    if guard:
        guard.start()
    for line in proc.stderr:
        sys.stderr.write(line)
        sys.stderr.flush()
        tail.append(line.rstrip("\n")[:LINE_CHARS])
    code = proc.wait()
    done.set()
    if guard:
        guard.join()
    return code, timed_out.is_set()


def run(stages: list[tuple[str, str]], out: str, deadline_s: float | None = None) -> int:
    # The pod's result dir may not exist yet; without it a failing stage's report itself would crash (#864).
    pathlib.Path(out).parent.mkdir(parents=True, exist_ok=True)
    done: list[str] = []
    stage_elapsed: dict[str, float] = {}
    t0 = time.monotonic()
    for name, command in stages:
        tail: collections.deque = collections.deque(maxlen=TAIL_LINES)
        remaining = None if deadline_s is None else max(0.0, deadline_s - (time.monotonic() - t0))
        ts = time.monotonic()
        if remaining == 0.0:
            code, timed_out = None, True
        else:
            code, timed_out = run_stage(command, tail, remaining)
        stage_elapsed[name] = round(time.monotonic() - ts, 1)
        if timed_out or code != 0:
            exit_ = "timeout" if timed_out else code
            doc = {
                "schema": SCHEMA, "schema_version": SCHEMA_VERSION, "stage": name, "exit": exit_,
                "elapsed_s": round(time.monotonic() - t0, 1), "stages_done": done,
                "stage_elapsed_s": stage_elapsed, "deadline_s": deadline_s,
                "stderr_tail": list(tail),
                "max_rss_kb": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
            }
            with open(out, "w", encoding="utf-8") as f:
                json.dump(doc, f)
            why = f"hit deadline {deadline_s}s" if timed_out else f"failed (exit {code})"
            print(f"[run_stages] stage {name} {why}; wrote {out}", file=sys.stderr)
            return 0
        print(f"[run_stages] stage {name} done in {stage_elapsed[name]}s", file=sys.stderr)
        done.append(name)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True, help="stage-failure JSON path (same as the job's result_path)")
    ap.add_argument("--stage", action="append", required=True, metavar="NAME=CMD")
    ap.add_argument("--deadline-s", type=float, default=None,
                    help="total seconds from start; past it the running stage's process group is killed "
                         "and exit 'timeout' is reported (suggested: max_minutes*60 - 900)")
    args = ap.parse_args(argv)
    if args.deadline_s is not None and args.deadline_s <= 0:
        ap.error("--deadline-s must be > 0")
    stages = []
    for s in args.stage:
        name, sep, cmd = s.partition("=")
        if not sep or not name or not cmd:
            ap.error(f"--stage needs NAME=COMMAND, got {s!r}")
        stages.append((name, cmd))
    return run(stages, args.out, args.deadline_s)


if __name__ == "__main__":
    sys.exit(main())
