"""Gate B judgement (referee/GATES.md Gate B and 표본 정책).

The spec is pre-registered: its sha256 goes into the result. A preset whose `blocks` is below
`required_tournaments(pilot_sigma, delta_min, alpha, power)` is "판정 불가(표본 부족)" whatever the CI
says; otherwise it passes when the 95% CI lower bound is > 0 (GATES.md), else fails. delta_min only sizes the
sample: n gives power 0.9 when the true effect is delta_min.
"""
from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path

import numpy as np

from referee.agents.reference_bot import REFERENCE_BOT_VERSION, factory
from referee.evaluate import evaluate
from referee.stats import required_tournaments
from stalker.tournament.config import load_preset

SCHEMA_VERSION = 1
PASS, FAIL, INSUFFICIENT = "pass", "fail", "판정 불가(표본 부족)"
SPEC_KEYS = ("name", "reference_version", "presets", "blocks", "rotations", "seed", "delta_min",
             "pilot_sigma", "alpha", "power")


def load_spec(path: str | Path) -> tuple[dict, str]:
    raw = Path(path).read_bytes()
    spec = json.loads(raw)
    missing = [k for k in SPEC_KEYS if k not in spec]
    if missing:
        raise ValueError(f"spec {path} lacks {missing}; add them (see referee/gate_b/spec_v1.json).")
    if spec["reference_version"] != REFERENCE_BOT_VERSION:
        raise ValueError(f"spec pins reference {spec['reference_version']} but code is {REFERENCE_BOT_VERSION}; "
                         "update the spec (a new reference version needs a new spec, old results stay).")
    return spec, hashlib.sha256(raw).hexdigest()


def resolve_candidate(ref: str):
    mod, _, attr = ref.partition(":")
    if not attr:
        raise ValueError(f"candidate '{ref}': use module:factory, where factory(config) returns rng -> Agent.")
    return getattr(importlib.import_module(mod), attr)


def _verdict(blocks: int, required: int, lo: float) -> str:
    if blocks < required:
        return INSUFFICIENT
    return PASS if lo > 0 else FAIL


def run_gate_b(spec: dict, spec_sha256: str, candidate_ref: str) -> dict:
    make = resolve_candidate(candidate_ref)
    required = required_tournaments(spec["pilot_sigma"], spec["delta_min"], alpha=spec["alpha"], power=spec["power"])
    presets = {}
    for name in spec["presets"]:
        cfg = load_preset(name)
        res = evaluate(cfg, make(cfg), factory(cfg.payout_ratios()), blocks=spec["blocks"], seed=spec["seed"],
                       rotations=spec["rotations"], candidate_name=candidate_ref,
                       baseline_name="reference_bot", reference_version=REFERENCE_BOT_VERSION)
        verdict = _verdict(spec["blocks"], required, res.ci.lo)
        presets[name] = {"verdict": verdict, "ci": {"mean": res.ci.mean, "lo": res.ci.lo, "hi": res.ci.hi,
                                                    "level": res.ci.level, "n_clusters": res.ci.n_clusters},
                         "games": res.games, "illegal_actions": res.illegal_actions}
    verdicts = [p["verdict"] for p in presets.values()]
    overall = PASS if all(v == PASS for v in verdicts) else FAIL if FAIL in verdicts else INSUFFICIENT
    return {"schema_version": SCHEMA_VERSION, "spec_sha256": spec_sha256, "spec": spec, "candidate": candidate_ref,
            "required_blocks": required, "verdict": overall, "presets": presets}


def run_pilot(spec: dict, spec_sha256: str, candidate_ref: str) -> dict:
    """Small fixed Gate B run that measures the duplicate variance reduction (GATES.md 표본 정책).

    Flat metric keys (CI appends them to metrics history). Per preset: the run_gate_b verdict and CI, `sd_dup`
    = SD of the duplicate block diffs, `sd_indep` = SD of clusters built from the same games without the seat swap
    pairing (block b's shifted-mask games with block b+1's complement games, so the swapped games share no deck). `required_tournaments` sizes
    the sample from the largest measured `sd_dup`; it is a record, not a change to the spec's pilot_sigma.
    """
    make = resolve_candidate(candidate_ref)
    required = required_tournaments(spec["pilot_sigma"], spec["delta_min"], alpha=spec["alpha"], power=spec["power"])
    out: dict = {"gate_b_pilot_spec_sha256": spec_sha256}
    sds = []
    for name in spec["presets"]:
        cfg = load_preset(name)
        res = evaluate(cfg, make(cfg), factory(cfg.payout_ratios()), blocks=spec["blocks"], seed=spec["seed"],
                       rotations=spec["rotations"], candidate_name=candidate_ref,
                       baseline_name="reference_bot", reference_version=REFERENCE_BOT_VERSION)
        g = np.asarray(res.block_game_diffs)
        unpaired = np.concatenate([g[:, 0::2], np.roll(g[:, 1::2], -1, axis=0)], axis=1).mean(axis=1)
        sd_dup = float(np.std(res.block_diffs, ddof=1))
        sds.append(sd_dup)
        key = f"gate_b_pilot_{name}"
        out.update({f"{key}_roi_diff": round(res.ci.mean, 6), f"{key}_ci_lower": round(res.ci.lo, 6),
                    f"{key}_ci_upper": round(res.ci.hi, 6),
                    f"{key}_verdict": _verdict(spec["blocks"], required, res.ci.lo),
                    f"{key}_sd_dup": round(sd_dup, 6), f"{key}_sd_indep": round(float(np.std(unpaired, ddof=1)), 6)})
    sigma = max(sds)
    # A zero SD (e.g. a deterministic candidate mirrored by duplicate) needs no more than the minimum sample.
    out["gate_b_pilot_required_tournaments"] = (
        required_tournaments(sigma, spec["delta_min"], alpha=spec["alpha"], power=spec["power"]) if sigma > 0 else 2)
    return out


def to_json(result: dict) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def to_markdown(result: dict) -> str:
    lines = [f"# Gate B: {result['verdict']}", "",
             f"candidate `{result['candidate']}` vs reference {result['spec']['reference_version']}, "
             f"spec sha256 `{result['spec_sha256'][:12]}`, blocks {result['spec']['blocks']} "
             f"(required {result['required_blocks']}), delta_min {result['spec']['delta_min']}", "",
             "| preset | verdict | ROI diff mean | 95% CI |", "|---|---|---|---|"]
    for name, p in result["presets"].items():
        c = p["ci"]
        lines.append(f"| {name} | {p['verdict']} | {c['mean']:+.4f} | [{c['lo']:+.4f}, {c['hi']:+.4f}] |")
    lines += ["", "Gate B is superiority over the reference bot only; report together with Gate A."]
    return "\n".join(lines) + "\n"
