"""A mixn c1 pod result -> one web policy file per seat count, in CI (#588, ADR 0021 follow-up 2).

`cloud.yml mode=export` runs this: agent sandboxes cannot download the run's `cloud-result-<run>` artifact
(proxy 403), so the runner splits it and leaves the files as the `web-policy-<run>` artifact plus a summary in
`ops:cloud/exports/<run>.json` the agents can read.

    python -m stalker.tools.export_web_players check-artifact artifacts.json --run 41812635702
    python -m stalker.tools.export_web_players export --pod-result result.json --run 41812635702 --tier mid \\
        --index-base web/app/policy/index.json --out-dir out/ --summary-out ops/cloud/exports/41812635702.json

`export` loads the table once and writes `<tier>-<n>.json` for every seat count (2-6 by default, each through
`export_web_policy.policy_doc` with `--players n`) and `index.json`: `--index-base` with those files upserted.
A file over the page budget (`export_web_policy.MAX_BYTES`) is still written and marked
`within_page_budget: false`; `keys_by_min_visits` in the summary says how many keys each `--min-visits` keeps,
so the PR that ships the files can pick a threshold without another download.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from stalker.tools import export_web_policy as X

SCHEMA = "stalker.web.policy-export"
SCHEMA_VERSION = 1
PLAYERS = (2, 3, 4, 5, 6)
VISIT_STEPS = (1, 2, 5, 10, 20, 50, 100)


def artifact_name(run: str) -> str:
    return f"cloud-result-{run}"


def check_artifact(listing: dict, run: str) -> dict:
    """The run's result artifact from a `GET /actions/runs/<run>/artifacts` listing; refuses a missing or
    expired one with the line the job log shows first."""
    name = artifact_name(run)
    for art in listing.get("artifacts") or []:
        if art.get("name") == name and not art.get("expired"):
            return art
    raise SystemExit(f"artifact {name} not found/expired: 다시 학습하거나 다른 run을 지정 "
                     "(cloud.yml artifacts are kept 30 days; pass export_run=<a newer cloud.yml run id>)")


def _keys_by_min_visits(keys, visits: dict) -> dict:
    return {str(v): sum(1 for k in keys if visits.get(k, 0) >= v) for v in VISIT_STEPS}


def export_all_players(st: dict, summary: dict, run: str, out_dir: Path, tier: str = "",
                       index_base: dict | None = None, players=PLAYERS, strategy: str = "current",
                       min_visits: int = 0, sha: str = "", max_bytes: int = X.MAX_BYTES) -> dict:
    """Write `<tier>-<n>.json` per seat count and `index.json` into out_dir; return the export summary."""
    if not st.get("player_mix"):
        raise SystemExit(f"run {run}: this table has no player_mix ({st.get('n')}-handed only); "
                         "export it whole with `python -m stalker.tools.export_web_policy --pod-result` instead")
    m = X.load_model(st)
    visits = dict(m.visits)
    full = m.policy() if strategy == "average" else m.current_policy()
    out_dir.mkdir(parents=True, exist_ok=True)
    idx = index_base
    files, tiers = [], set()
    for n in players:
        doc = X.policy_doc(m, st, summary, run, sha, strategy, False, X.split_players(st, n), min_visits, full)
        tiers.add(doc["tier"])
        if tier and doc["tier"] != tier:
            raise SystemExit(f"run {run} is tier {doc['tier']!r}, not {tier!r}: pass tier={doc['tier']} "
                             "or pick a run of that tier")
        body = json.dumps(doc, separators=(",", ":")).encode()
        name = f"{doc['tier']}-{n}.json"
        (out_dir / name).write_bytes(body)
        idx = X.upsert_index(idx, X.index_entry(doc, name, len(body)))
        files.append({"file": name, "players": doc["players"], "keys": doc["keys"], "keys_dropped": doc["keys_dropped"],
                      "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
                      "within_page_budget": len(body) <= max_bytes,
                      "keys_by_min_visits": _keys_by_min_visits(X.keep_players(full, n), visits),
                      "lbr_bb": doc["lbr_bb"], "lbr_stderr_bb": doc["lbr_stderr_bb"], "field_worst": doc["field_worst"]})
        print(f"{name}: {doc['keys']} keys, {len(body)} bytes")
    X.write_index(out_dir / "index.json", idx)
    ib = (out_dir / "index.json").read_bytes()
    return {"schema": SCHEMA, "schema_version": SCHEMA_VERSION, "export_run": str(run), "artifact": f"web-policy-{run}",
            "job": summary.get("job", ""), "tier": min(tiers) if tiers else tier,
            "iterations": st.get("iterations"), "strategy": strategy, "min_visits": min_visits,
            "player_mix": [int(x) for x in st["player_mix"]], "max_bytes": max_bytes, "files": files,
            "index": {"file": "index.json", "bytes": len(ib), "sha256": hashlib.sha256(ib).hexdigest()}}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check-artifact", help="refuse a missing or expired cloud-result-<run> artifact")
    c.add_argument("listing", type=Path, help="GET /repos/<repo>/actions/runs/<run>/artifacts output")
    c.add_argument("--run", required=True)
    e = sub.add_parser("export", help="split a mixn c1 pod result into per-seat-count web policy files")
    e.add_argument("--pod-result", type=Path, required=True)
    e.add_argument("--run", required=True, help="the cloud.yml run id the result came from")
    e.add_argument("--tier", default="", help="refuse a result of another tier")
    e.add_argument("--players", default=",".join(map(str, PLAYERS)), help="comma-separated seat counts")
    e.add_argument("--strategy", choices=("current", "average"), default="current")
    e.add_argument("--min-visits", type=int, default=0)
    e.add_argument("--index-base", type=Path, help="the model list to upsert into (web/app/policy/index.json)")
    e.add_argument("--out-dir", type=Path, required=True)
    e.add_argument("--summary-out", type=Path, required=True)
    a = ap.parse_args(argv)
    if a.cmd == "check-artifact":
        try:
            listing = json.loads(a.listing.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            listing = {}
        check_artifact(listing, a.run)
        return 0
    if not a.pod_result.exists():
        raise SystemExit(f"artifact {artifact_name(a.run)} not found/expired: 다시 학습하거나 다른 run을 지정 "
                         f"({a.pod_result} is missing)")
    st, summary = X.load_pod_result(a.pod_result)
    base = json.loads(a.index_base.read_text(encoding="utf-8")) if a.index_base else None
    players = tuple(int(p) for p in a.players.split(",") if p.strip())
    out = export_all_players(st, summary, a.run, a.out_dir, a.tier, base, players, a.strategy, a.min_visits)
    a.summary_out.parent.mkdir(parents=True, exist_ok=True)
    a.summary_out.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{a.summary_out}: {len(out['files'])} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
