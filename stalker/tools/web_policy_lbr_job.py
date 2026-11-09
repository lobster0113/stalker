"""Cloud job: c1 LBR of the filtered web policy files at ADR 0020's hands and seeds (#661, follow-up 1 of #653).

    python -m stalker.tools.web_policy_lbr_job --policy-run 41813684540 --out /result/web-policy-lbr.json [--workers 32]
    python -m stalker.tools.web_policy_lbr_job --from-pages web/app/policy --out /result/web-policy-lbr.json   # what the service serves (#695)

`--from-pages <dir>` measures the page files `<dir>/mid-<n>.json` of a main checkout (or tarball dir) and records each file's own
`run_id` as that player count's `policy_run` in the cells of `backoff`, so `e3_web_lbr` compares `fresh` per player count.

Reads `cloud/policies/<policy_run>/mid-{2..6}.json` from the `ops` branch tarball (only those members are kept), measures each
file with `web_policy_lbr.measure` with the page's backoff off and on, at the hand counts and minimum seed counts of
`referee/e3/lbr_thresholds_v1.json` (read-only), evaluation seed `10000+seed` as in `train_jobs`. The result has no timings, so
the same inputs give the same bytes. The pass is record-only (the page keeps the policy either way; a person reads it).
The result deliberately has no `by_players` key: the launcher would take that as a training summary and overwrite a verdict.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import tarfile
import urllib.request
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

SCHEMA = "stalker.web.policy-lbr"
SCHEMA_VERSION = 1
PLAYERS = (2, 3, 4, 5, 6)
OPS_TARBALL = "https://codeload.github.com/lobster0113/stalker/tar.gz/refs/heads/ops"


def page_runs(pages: Path) -> dict[int, str]:
    """`run_id` of each page file `mid-<n>.json` (as a string); a missing or run-less file is an error, not a guess."""
    out = {}
    for n in PLAYERS:
        f = Path(pages) / f"mid-{n}.json"
        try:
            run_id = json.loads(f.read_text(encoding="utf-8")).get("run_id")
        except (OSError, ValueError, AttributeError):
            run_id = None
        if run_id is None:
            raise SystemExit(f"{f} has no readable run_id: pass the directory of the pages main serves (web/app/policy)")
        out[n] = str(run_id)
    return out


def plan(policy_run: str, table: dict | None = None, backoffs=(False, True), seeds: int | None = None,
         runs: dict[int, str] | None = None) -> list[dict]:
    """One task per (players, seed, backoff): hands from ADR 0020, seeds 1..max(min_seeds of the current strategy, `seeds`)."""
    if table is None:
        from referee.e3.thresholds import load_thresholds
        table = load_thresholds()
    tasks = []
    for n in PLAYERS:
        spec = table["players"][str(n)]
        for seed in range(1, max(spec["min_seeds"]["lbr"], seeds or 1) + 1):
            for backoff in backoffs:
                tasks.append({"players": n, "seed": seed, "eval_seed": 10_000 + seed, "hands": spec["hands"],
                              "backoff": backoff, "file": f"mid-{n}.json", "policy_run": runs[n] if runs else policy_run})
    return tasks


def fetch(policy_run: str, dest: Path, tarball: bytes | None = None) -> None:
    prefix = f"cloud/policies/{policy_run}/"
    raw = tarball if tarball is not None else urllib.request.urlopen(OPS_TARBALL).read()
    dest.mkdir(parents=True, exist_ok=True)
    found = 0
    with tarfile.open(None, "r:gz", fileobj=io.BytesIO(raw)) as t:
        for m in t.getmembers():
            rel = m.name.split("/", 1)[-1]
            if m.isfile() and rel.startswith(prefix) and rel.count("/") == prefix.count("/"):
                (dest / rel[len(prefix):]).write_bytes(t.extractfile(m).read())
                found += 1
    if not found:
        raise SystemExit(f"ops has no {prefix}: pass an existing policy_run (ls cloud/policies on the ops branch)")


def _one(args):
    from stalker.tools.web_policy_lbr import measure
    task, d = args
    r = measure(Path(d) / task["file"], task["players"], task["hands"], task["eval_seed"], task["backoff"])
    return {**task, **{k: r[k] for k in ("lbr_bb", "lbr_stderr_bb", "policy_sha256")}}


def summarize(rows: list[dict], table: dict | None = None, per_players_run: bool = False) -> dict:
    if table is None:
        from referee.e3.thresholds import load_thresholds
        table = load_thresholds()
    out = {}
    for backoff in (False, True):
        cells = {}
        for n in PLAYERS:
            r = [x for x in rows if x["players"] == n and x["backoff"] is backoff]
            if not r:
                continue
            spec = table["players"][str(n)]
            mean = sum(x["lbr_bb"] for x in r) / len(r)
            se = (sum(x["lbr_stderr_bb"] ** 2 for x in r) ** 0.5) / len(r)
            enough = len(r) >= spec["min_seeds"]["lbr"]
            cells[str(n)] = {"lbr_bb": round(mean, 4), "lbr_stderr_bb": round(se, 4), "hands": spec["hands"],
                             "seeds": sorted(x["seed"] for x in r), "limit": spec["lbr_max"],
                             "policy_sha256": r[0]["policy_sha256"],
                             "pass": (mean <= spec["lbr_max"]) if enough else None}
            if per_players_run:
                cells[str(n)]["policy_run"] = r[0]["policy_run"]
        out["on" if backoff else "off"] = cells
    return out


def run(policy_run: str | None, out: Path, workers: int = 1, seeds: int | None = None, src: Path | None = None,
        pages: Path | None = None) -> dict:
    import tempfile
    runs = page_runs(pages) if pages else None
    if runs:
        src = Path(pages)
        distinct = set(runs.values())
        policy_run = distinct.pop() if len(distinct) == 1 else "mixed"
    tasks = plan(policy_run, seeds=seeds, runs=runs)
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(src) if src else Path(tmp)
        if not src:
            fetch(policy_run, d)
        jobs = [(t, str(d)) for t in tasks]
        if workers > 1:
            with ProcessPoolExecutor(workers) as ex:
                rows = list(ex.map(_one, jobs))
        else:
            rows = [_one(j) for j in jobs]
    rows.sort(key=lambda x: (x["backoff"], x["players"], x["seed"]))
    res = {"schema": SCHEMA, "schema_version": SCHEMA_VERSION, "policy_run": policy_run,
           "thresholds": "referee/e3/lbr_thresholds_v1.json", "rows": rows, "backoff": summarize(rows, per_players_run=bool(runs))}
    res["sha256"] = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(res, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--policy-run", default=None, help="ops:cloud/policies/<run> directory name")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--seeds", type=int, default=None, help="seeds per cell (default: ADR 0020 minimum for the current strategy)")
    ap.add_argument("--src", type=Path, default=None, help="local dir with mid-N.json instead of the ops tarball")
    ap.add_argument("--from-pages", type=Path, default=None, help="dir with the served mid-N.json pages (web/app/policy); per-player policy_run")
    a = ap.parse_args(argv)
    if bool(a.policy_run) == bool(a.from_pages):
        ap.error("give exactly one of --policy-run and --from-pages")
    run(a.policy_run, a.out, a.workers, a.seeds, a.src, a.from_pages)
    return 0


if __name__ == "__main__":
    sys.exit(main())
