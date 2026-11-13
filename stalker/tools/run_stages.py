"""Run shell stages in order; on a failing stage write a stage-failure JSON and still exit 0 (#841).

The cloud launcher only retrieves the result file when the job command exits 0, so a failing stage's
exit code, elapsed time and stderr tail would otherwise be lost with the pod.
"""
import argparse
import collections
import json
import resource
import subprocess
import sys
import time

SCHEMA = "stalker.cloud.stage-failure"
TAIL_LINES = 200
LINE_CHARS = 500


def run_stage(command: str, tail: collections.deque) -> int:
    proc = subprocess.Popen(command, shell=True, stderr=subprocess.PIPE, encoding="utf-8", errors="replace")
    for line in proc.stderr:
        sys.stderr.write(line)
        sys.stderr.flush()
        tail.append(line.rstrip("\n")[:LINE_CHARS])
    return proc.wait()


def run(stages: list[tuple[str, str]], out: str) -> int:
    done: list[str] = []
    t0 = time.monotonic()
    for name, command in stages:
        tail: collections.deque = collections.deque(maxlen=TAIL_LINES)
        code = run_stage(command, tail)
        if code != 0:
            doc = {
                "schema": SCHEMA, "schema_version": 1, "stage": name, "exit": code,
                "elapsed_s": round(time.monotonic() - t0, 1), "stages_done": done,
                "stderr_tail": list(tail),
                "max_rss_kb": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
            }
            with open(out, "w", encoding="utf-8") as f:
                json.dump(doc, f)
            print(f"[run_stages] stage {name} failed (exit {code}); wrote {out}", file=sys.stderr)
            return 0
        done.append(name)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True, help="stage-failure JSON path (same as the job's result_path)")
    ap.add_argument("--stage", action="append", required=True, metavar="NAME=CMD")
    args = ap.parse_args(argv)
    stages = []
    for s in args.stage:
        name, sep, cmd = s.partition("=")
        if not sep or not name or not cmd:
            ap.error(f"--stage needs NAME=COMMAND, got {s!r}")
        stages.append((name, cmd))
    return run(stages, args.out)


if __name__ == "__main__":
    sys.exit(main())
