"""Trained E3 policy -> the web service's policy file (#336): `python -m stalker.tools.export_web_policy`.

The service plays and grades from the regret-matching (current) strategy, the one the CI and pod
runs evaluate (`stalker.train_jobs.e3_evaluate`: LBR and field are measured on it). Probabilities are
quantized to 1/255 with the largest remainder, so each row still sums to exactly 255, and every
action the policy plays (p > 0) keeps at least 1: a zero would empty that action's combos in the page's
Bayes range update (`updateRanges`) when a person takes it. Values are integers 0..255; divide by `q`.
Keys the traverser updated fewer than `--min-visits` times can be dropped to fit the page budget: they are
close to the uniform start, and the page plays uniform for a missing key. Keys stay strings: the page
builds the same keys (`web/app/tpgto.js`, #335). The file names its training run so the page can
label every answer with the model it came from (iterations, LBR, run).

    python -m stalker.tools.export_web_policy --ckpt e3-tp-mid-w4-seed1.ckpt.json --summary e3-tp-mid-w4-seed1.json \
        --run 40793583489 --out web/app/policy/mid-6.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

SCHEMA = "stalker.web.policy"
SCHEMA_VERSION = 1
Q = 255
MAX_BYTES = 3 * 1024 * 1024  # one tier's file (#336): the page loads it before the first hand


def quantize(p) -> list[int]:
    """Probabilities -> integers summing to Q (largest remainder; ties to the earlier action)."""
    p = np.asarray(p, dtype=float)
    p = np.full(len(p), 1.0 / len(p)) if not np.isfinite(p).all() or p.sum() <= 0 else p / p.sum()
    raw = p * Q
    q = np.floor(raw).astype(int)
    for i in sorted(range(len(p)), key=lambda i: (-(raw[i] - q[i]), i))[: Q - int(q.sum())]:
        q[i] += 1
    for i in np.flatnonzero((p > 0) & (q == 0)):  # keep played actions playable, take from the largest
        q[i] += 1
        q[int(np.argmax(q))] -= 1
    return q.tolist()


def export(policy: dict[str, list[float]], meta: dict, visits: dict[str, int] | None = None,
           min_visits: int = 0) -> dict:
    kept = {k: v for k, v in policy.items() if visits is None or visits.get(k, 0) >= min_visits}
    return {"schema": SCHEMA, "schema_version": SCHEMA_VERSION, **meta, "q": Q, "min_visits": min_visits,
            "keys": len(kept), "keys_dropped": len(policy) - len(kept),
            "policy": {k: quantize(v) for k, v in sorted(kept.items())}}


def meta_from(model: dict, summary: dict | None, run: str, sha: str) -> dict:
    s = summary or {}
    field = s.get("field") or {}
    worst = field.get("worst") if isinstance(field, dict) else None
    tier = {5: "beginner", 11: "mid", 17: "pro"}.get(model["k"], s.get("tier"))
    lbr = s.get("lbr")
    lbr, se = (lbr.get("lbr_bb"), lbr.get("stderr_bb")) if isinstance(lbr, dict) else (lbr, None)
    return {"tier": s.get("tier", tier), "players": model["n"], "k": model["k"], "depth": model["depth"],
            "iterations": model["iterations"], "run_id": str(run), "sha": sha or s.get("sha", ""),
            "lbr_bb": lbr, "lbr_stderr_bb": se, "field_worst": worst, "job": s.get("job", "")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ckpt", type=Path, required=True, help="a CI-layout .ckpt.json (or `pod_train --unpack` output)")
    ap.add_argument("--summary", type=Path, help="the seed's summary JSON (<job>-seed<s>.json): LBR, field, job")
    ap.add_argument("--run", default="", help="the training run id the checkpoint came from")
    ap.add_argument("--sha", default="")
    ap.add_argument("--min-visits", type=int, default=0, help="drop keys updated fewer times than this")
    ap.add_argument("--max-bytes", type=int, default=MAX_BYTES)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    from stalker.e3.mccfr import E3MCCFR

    st = json.loads(a.ckpt.read_text(encoding="utf-8"))
    m = E3MCCFR.from_state(st)
    summary = json.loads(a.summary.read_text(encoding="utf-8")) if a.summary else None
    doc = export(m.current_policy(), meta_from(st, summary, a.run, a.sha), dict(m.visits), a.min_visits)
    body = json.dumps(doc, separators=(",", ":")).encode()
    if len(body) > a.max_bytes:
        raise SystemExit(f"{a.out}: {len(body)} bytes > {a.max_bytes}; drop rarely updated keys with --min-visits "
                         "(e.g. 10) or pass --max-bytes with a reason")
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_bytes(body)
    print(f"{a.out}: {doc['keys']} keys, {len(body)} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
