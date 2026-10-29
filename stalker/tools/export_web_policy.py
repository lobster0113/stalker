"""Trained E3 policy -> the web service's policy file (#336): `python -m stalker.tools.export_web_policy`.

The service plays and grades from the regret-matching (current) strategy, the one the CI and pod
runs evaluate (`stalker.train_jobs.e3_evaluate`: LBR and field are measured on it). Probabilities are
quantized to 1/255 with the largest remainder, so each row still sums to exactly 255 and an action
the policy plays keeps at least 1/255 if it had at least half of that. Keys stay strings: the page
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
MAX_BYTES = 8 * 1024 * 1024  # one tier's file; the page loads it once per table


def quantize(p) -> list[int]:
    """Probabilities -> integers summing to Q (largest remainder; ties to the earlier action)."""
    p = np.asarray(p, dtype=float)
    p = np.full(len(p), 1.0 / len(p)) if not np.isfinite(p).all() or p.sum() <= 0 else p / p.sum()
    raw = p * Q
    q = np.floor(raw).astype(int)
    for i in sorted(range(len(p)), key=lambda i: (-(raw[i] - q[i]), i))[: Q - int(q.sum())]:
        q[i] += 1
    return q.tolist()


def export(policy: dict[str, list[float]], meta: dict) -> dict:
    return {"schema": SCHEMA, "schema_version": SCHEMA_VERSION, **meta, "q": Q,
            "keys": len(policy), "policy": {k: quantize(v) for k, v in sorted(policy.items())}}


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
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    from stalker.e3.mccfr import E3MCCFR

    st = json.loads(a.ckpt.read_text(encoding="utf-8"))
    m = E3MCCFR.from_state(st)
    summary = json.loads(a.summary.read_text(encoding="utf-8")) if a.summary else None
    doc = export(m.current_policy(), meta_from(st, summary, a.run, a.sha))
    body = json.dumps(doc, separators=(",", ":")).encode()
    if len(body) > MAX_BYTES:
        raise SystemExit(f"{a.out}: {len(body)} bytes > {MAX_BYTES}; export fewer keys (prune rarely visited ones) "
                         "or raise MAX_BYTES with a reason in the PR")
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_bytes(body)
    print(f"{a.out}: {doc['keys']} keys, {len(body)} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
