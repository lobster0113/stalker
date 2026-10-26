"""Gate A judgement against the ICM reference (referee/GATES.md Gate A).

Per spot the baseline is the reference's own Nash solution for hero. A diff is
(candidate EV - baseline EV) / prize pool for hero, against ① the Nash opponents of that spot
and ② every profile of the pre-registered non-Nash pool. Spots are the clusters: within one
format (players x bubble) the CI resamples whole spots, so ② pool profiles of one spot stay
together. A format passes when ① is non-inferior (CI lo > -delta_ni) and ② superior
(CI lo > 0 and >= delta_min). The baseline is the reference, never real ICMizer output, and
results say so.
"""
from __future__ import annotations

import hashlib
import importlib
import json
from functools import lru_cache
from pathlib import Path

import numpy as np

from referee.anchors.icm_reference import Solution, Spot, evaluate_spot, solve, top_percent_strategy
from referee.gate_a.spots import load_spots, spot_set_hash
from referee.stats import noninferiority, superiority

SCHEMA_VERSION = 1
PASS, FAIL, PARTIAL = "pass", "fail", "해당 형식 한정 통과"
BASELINE = "reference"
SPEC_V1 = Path(__file__).with_name("spec_v1.json")
SPEC_KEYS = ("name", "spot_set_version", "spot_set_sha256", "baseline", "value_model", "fgs_depth", "baseline_tol",
             "baseline_max_iter",
             "delta_ni", "delta_min", "level", "n_boot", "seed", "pool")
FORMATS = ((6, True), (6, False), (9, True), (9, False))


def format_name(players: int, bubble: bool) -> str:
    return f"{players}max-{'bubble' if bubble else 'nonbubble'}"


def load_spec(path: str | Path = SPEC_V1) -> tuple[dict, str]:
    raw = Path(path).read_bytes()
    spec = json.loads(raw)
    missing = [k for k in SPEC_KEYS if k not in spec]
    if missing:
        raise ValueError(f"spec {path} lacks {missing}; add them (see referee/gate_a/spec_v1.json).")
    if spec["baseline"] != BASELINE:
        raise ValueError(f"spec baseline {spec['baseline']!r}: only {BASELINE!r} (ICM reference) is implemented.")
    if not spec["pool"] or any(set(p) != {"name", "push", "call"} for p in spec["pool"]):
        raise ValueError("spec pool must be a non-empty list of {name, push, call} top-percent profiles.")
    return spec, hashlib.sha256(raw).hexdigest()


@lru_cache(maxsize=None)
def nash(spot: Spot, value_model: str, fgs_depth: int, tol: float, max_iter: int) -> Solution:
    """Cached reference solution; shared by the baseline and the `reference` candidate."""
    sol = solve(spot, value_model, fgs_depth, tol, max_iter)
    if not sol.converged:
        raise RuntimeError(f"reference did not reach tol {tol} on {spot} in {max_iter} iterations; raise "
                           "baseline_max_iter in the spec (an unconverged baseline biases every diff).")
    return sol


def nash_policy(config: dict):
    """config = {value_model, fgs_depth, tol, max_iter}, the candidate config `run_gate_a` passes."""
    key = (config["value_model"], config["fgs_depth"], config["tol"], config["max_iter"])

    def policy(spot, seat, pusher):
        st = nash(spot, *key).strategy
        return st.push[seat] if pusher is None else st.call[seat, pusher]
    return policy


def resolve_candidate(ref: str):
    mod, _, attr = ref.partition(":")
    if not attr:
        raise ValueError(f"candidate '{ref}': use module:factory, where factory(config) returns a PolicyFn.")
    return getattr(importlib.import_module(mod), attr)


def _ci(dec) -> dict:
    c = dec.ci
    return {"passed": bool(dec.passed), "threshold": dec.threshold, "rule": dec.rule, "mean": c.mean,
            "lo": c.lo, "hi": c.hi, "level": c.level, "n_clusters": c.n_clusters, "n_obs": c.n_obs}


def overall_verdict(verdicts: list[str]) -> str:
    """GATES.md: a candidate passing only some formats is "해당 형식 한정 통과", never a plain pass."""
    n = sum(v == PASS for v in verdicts)
    return PASS if verdicts and n == len(verdicts) else PARTIAL if n else FAIL


def run_gate_a(spec: dict, spec_sha256: str, candidate_ref: str, spots_path: str | Path) -> dict:
    version, sha = spot_set_hash(spots_path)
    if (version, sha) != (spec["spot_set_version"], spec["spot_set_sha256"]):
        raise ValueError(f"spot set {spots_path} is {version} sha256 {sha[:12]} but the spec pins "
                         f"{spec['spot_set_version']} {spec['spot_set_sha256'][:12]}; use the pinned set "
                         "or register a new spec.")
    vm, d = spec["value_model"], spec["fgs_depth"]
    config = {"value_model": vm, "fgs_depth": d, "tol": spec["baseline_tol"], "max_iter": spec["baseline_max_iter"]}
    cand = resolve_candidate(candidate_ref)(config)
    base = nash_policy(config)

    def diff(spot, opp, hero):
        a = evaluate_spot(cand, spot, opp, hero, vm, d)["ev"]
        b = evaluate_spot(base, spot, opp, hero, vm, d)["ev"]
        return (a - b) / spot.prize_pool

    rows = []
    for sid, spot, meta in load_spots(spots_path):
        hero = meta["hero"]
        pool = {p["name"]: diff(spot, top_percent_strategy(spot.n, p["push"], p["call"]), hero)
                for p in spec["pool"]}
        rows.append({"id": sid, "format": format_name(meta["players"], meta["bubble"]),
                     "nash": diff(spot, nash(spot, vm, d, config["tol"], config["max_iter"]), hero), "pool": pool})

    formats = {}
    for k, (players, bubble) in enumerate(FORMATS):
        name = format_name(players, bubble)
        fr = [r for r in rows if r["format"] == name]
        if not fr:
            continue
        ni = noninferiority([r["nash"] for r in fr], [r["id"] for r in fr], delta_ni=spec["delta_ni"],
                            level=spec["level"], n_boot=spec["n_boot"], rng=np.random.default_rng([spec["seed"], k, 0]))
        pd = [(r["id"], v) for r in fr for _, v in sorted(r["pool"].items())]
        sup = superiority([v for _, v in pd], [i for i, _ in pd], delta_min=spec["delta_min"],
                          level=spec["level"], n_boot=spec["n_boot"], rng=np.random.default_rng([spec["seed"], k, 1]))
        formats[name] = {"verdict": PASS if ni.passed and sup.passed else FAIL, "spots": len(fr),
                         "nash_noninferiority": _ci(ni), "pool_superiority": _ci(sup)}
    passed = [f for f, v in formats.items() if v["verdict"] == PASS]
    overall = overall_verdict([v["verdict"] for v in formats.values()])
    return {"schema_version": SCHEMA_VERSION, "baseline": BASELINE, "candidate": candidate_ref,
            "spec_sha256": spec_sha256, "spec": spec, "spot_set": {"version": version, "sha256": sha},
            "verdict": overall, "passed_formats": passed, "formats": formats, "spots": rows}


def to_json(result: dict) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def to_markdown(result: dict) -> str:
    s = result["spec"]
    verdict = result["verdict"]
    if verdict == PARTIAL:
        verdict += f" ({', '.join(result['passed_formats'])})"
    lines = [f"# Gate A (참조기 기준): {verdict}", "",
             f"candidate `{result['candidate']}` vs ICM reference (not ICMizer), spot set "
             f"{result['spot_set']['version']} `{result['spot_set']['sha256'][:12]}`, spec sha256 "
             f"`{result['spec_sha256'][:12]}`, value {s['value_model']} fgs {s['fgs_depth']} tol {s['baseline_tol']}, "
             f"delta_ni {s['delta_ni']}, delta_min {s['delta_min']} (prize-pool fraction per spot)", "",
             "| format | verdict | ① vs Nash mean | ① CI | ② vs pool mean | ② CI |", "|---|---|---|---|---|---|"]
    for name, f in result["formats"].items():
        a, b = f["nash_noninferiority"], f["pool_superiority"]
        lines.append(f"| {name} | {f['verdict']} | {a['mean']:+.5f} | [{a['lo']:+.5f}, {a['hi']:+.5f}] | "
                     f"{b['mean']:+.5f} | [{b['lo']:+.5f}, {b['hi']:+.5f}] |")
    lines += ["", "① passes when CI lo > -delta_ni; ② when CI lo > 0 and >= delta_min. "
              "A format passes only with both; real-ICMizer agreement is not measured yet (#18)."]
    return "\n".join(lines) + "\n"

