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

`--min-visits-by-players "2:10,3:5"` overrides `--min-visits` per seat count (each file's summary entry says the
value it used). `--policies-out DIR` additionally copies the files within the page budget and an `index.json`
listing only them (entries already in `--index-base` stay as they are); `cloud.yml` points it at `ops/cloud/policies/<run>/`, the one place agents can read them from (#596).

`--hit-rate-hands N` (default 300, 0 = off) plays N seeded hands per seat count with the table before any `min_visits`
filter and puts `hit_rate` (`stalker.tools.web_hit_rate.measure`: by street, `call|` or not, and `by_min_visits`
0/1/2/5/10) into each file's summary entry, so CI tells a low hit rate from the filter apart from missing training coverage (#617).
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path

from stalker.tools import export_web_policy as X
from stalker.tools import web_hit_rate as H

SCHEMA = "stalker.web.policy-export"
SCHEMA_VERSION = 2   # 2: files[].hit_rate (#617); a v1 summary is the same without it
HIT_RATE_HANDS = 300   # CLI default: seeded hands per seat count; 0 turns the measurement off
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


def parse_min_visits_by_players(spec: str, mix) -> dict:
    """`"2:10,3:5"` -> {2: 10, 3: 5}; a malformed, repeated or out-of-mix entry fails with the fix."""
    out: dict[int, int] = {}
    for part in (p.strip() for p in (spec or "").split(",") if p.strip()):
        n, sep, v = part.partition(":")
        if not (sep and n.strip().isdigit() and v.strip().isdigit()):
            raise SystemExit(f"--min-visits-by-players: '{part}' is not <players>:<count>; write e.g. \"2:10,3:5\"")
        n, v = int(n), int(v)
        if mix is not None and n not in mix:
            raise SystemExit(f"--min-visits-by-players: {n} players is not in this run's player_mix {sorted(mix)}; "
                             "drop that entry")
        if n in out:
            raise SystemExit(f"--min-visits-by-players: {n} players appears twice; keep one entry")
        out[n] = v
    return out


def export_all_players(st: dict, summary: dict, run: str, out_dir: Path, tier: str = "",
                       index_base: dict | None = None, players=PLAYERS, strategy: str = "current",
                       min_visits: int = 0, sha: str = "", max_bytes: int = X.MAX_BYTES,
                       min_visits_by_players: dict | None = None, hit_rate_hands: int = 0) -> dict:
    """Write `<tier>-<n>.json` per seat count and `index.json` into out_dir; return the export summary.
    `hit_rate_hands` > 0 adds `hit_rate` to each file's entry: how often the page would find the actor's key in
    the table before the `min_visits` filter, per `min_visits` candidate (#617; seed 611+n, so same input, same JSON)."""
    if not st.get("player_mix"):
        raise SystemExit(f"run {run}: this table has no player_mix ({st.get('n')}-handed only); "
                         "export it whole with `python -m stalker.tools.export_web_policy --pod-result` instead")
    m = X.load_model(st)
    visits = dict(m.visits)
    full = m.policy() if strategy == "average" else m.current_policy()
    out_dir.mkdir(parents=True, exist_ok=True)
    idx = copy.deepcopy(index_base)   # upsert_index edits in place; policies_for_ops needs the untouched base
    files, tiers = [], set()
    by_n = min_visits_by_players or {}
    for n in players:
        mv = by_n.get(n, min_visits)
        doc = X.policy_doc(m, st, summary, run, sha, strategy, False, X.split_players(st, n), mv, full)
        tiers.add(doc["tier"])
        if tier and doc["tier"] != tier:
            raise SystemExit(f"run {run} is tier {doc['tier']!r}, not {tier!r}: pass tier={doc['tier']} "
                             "or pick a run of that tier")
        body = json.dumps(doc, separators=(",", ":")).encode()
        name = f"{doc['tier']}-{n}.json"
        (out_dir / name).write_bytes(body)
        idx = X.upsert_index(idx, X.index_entry(doc, name, len(body)))
        files.append({"file": name, "players": doc["players"], "min_visits": mv, "keys": doc["keys"], "keys_dropped": doc["keys_dropped"],
                      "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
                      "within_page_budget": len(body) <= max_bytes,
                      "keys_by_min_visits": _keys_by_min_visits(X.keep_players(full, n), visits),
                      "lbr_bb": doc["lbr_bb"], "lbr_stderr_bb": doc["lbr_stderr_bb"], "field_worst": doc["field_worst"]})
        if hit_rate_hands > 0:
            files[-1]["hit_rate"] = H.measure(X.keep_players(full, n), n, doc["k"], doc["depth"],
                                              hit_rate_hands, 611 + n, visits)
        print(f"{name}: {doc['keys']} keys, {len(body)} bytes")
    X.write_index(out_dir / "index.json", idx)
    ib = (out_dir / "index.json").read_bytes()
    return {"schema": SCHEMA, "schema_version": SCHEMA_VERSION, "export_run": str(run), "artifact": f"web-policy-{run}",
            "job": summary.get("job", ""), "tier": min(tiers) if tiers else tier,
            "iterations": st.get("iterations"), "strategy": strategy, "min_visits": min_visits,
            "min_visits_by_players": {str(n): v for n, v in sorted(by_n.items())},
            "player_mix": [int(x) for x in st["player_mix"]], "max_bytes": max_bytes, "files": files,
            "index": {"file": "index.json", "bytes": len(ib), "sha256": hashlib.sha256(ib).hexdigest()}}


def policies_for_ops(summary: dict, out_dir: Path, index_base: dict | None = None) -> dict[str, bytes]:
    """{file name: bytes} for `ops:cloud/policies/<run>/`: the files within the page budget and an `index.json`
    that lists only them (over-budget files stay in the summary). Empty when none fits (#596)."""
    kept = {f["file"]: f for f in summary["files"] if f["within_page_budget"]}
    if not kept:
        return {}
    idx = copy.deepcopy(index_base)
    for name in kept:
        body = (out_dir / name).read_bytes()
        doc = json.loads(body)
        idx = X.upsert_index(idx, X.index_entry(doc, name, len(body)))
    files = {name: (out_dir / name).read_bytes() for name in kept}
    files["index.json"] = (json.dumps(idx, indent=1, ensure_ascii=False) + "\n").encode()
    return files


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
    e.add_argument("--min-visits-by-players", default="", metavar="2:10,3:5",
                   help="per-seat-count --min-visits; other counts use --min-visits")
    e.add_argument("--hit-rate-hands", type=int, default=HIT_RATE_HANDS,
                   help="seeded hands per seat count for the table hit-rate in the summary (0 = off)")
    e.add_argument("--policies-out", type=Path,
                   help="also copy the files within the page budget (+ an index of them) here (ops:cloud/policies/<run>/)")
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
    by_n = parse_min_visits_by_players(a.min_visits_by_players, st.get("player_mix"))
    out = export_all_players(st, summary, a.run, a.out_dir, a.tier, base, players, a.strategy, a.min_visits,
                             min_visits_by_players=by_n, hit_rate_hands=a.hit_rate_hands)
    if a.policies_out:
        kept = policies_for_ops(out, a.out_dir, base)
        for name, body in kept.items():
            a.policies_out.mkdir(parents=True, exist_ok=True)
            (a.policies_out / name).write_bytes(body)
        print(f"{a.policies_out}: {len(kept) - 1 if kept else 0} files within the page budget")
    a.summary_out.parent.mkdir(parents=True, exist_ok=True)
    a.summary_out.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{a.summary_out}: {len(out['files'])} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
