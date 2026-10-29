"""Allow-listed training jobs for the `train` workflow (GitHub Actions CPU runners, #184).

    python -m stalker.train_jobs run e2-mccfr --iters 20000 --seed 3 --out out/
    python -m stalker.train_jobs run e2-tier-beginner --iters 100000 --seed 1 --out out/   (#187)
    python -m stalker.train_jobs summarize e2-mccfr out/ > summary.json

Only names in JOBS can run, so a workflow input can never become an arbitrary command. Each run
writes `<out>/<job>-seed<S>.json` (settings, timings, result numbers, and a small policy digest);
`summarize` merges the per-seed files. Numbers produced here are CI numbers (CLAUDE.md).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from functools import partial
from pathlib import Path

# LBR hands per seat: 400 gave SE ~0.4-0.5 bb/hand, too wide to separate TP tiers (#234); 4000 gives ~0.15.
LBR_HANDS = 4000
# E3 N-seat LBR hands per seat: 150 gave SE ~0.7 bb/hand (docs/research/2026-10-e3-lbr.md); 1000 gives ~0.3.
E3_LBR_HANDS = 1000
# E3 field deals per configuration (each played in all 6 seat rotations): 500 locally gave a 95% CI of
# about +-150 bb/100 (#295); about 0.08 s per deal per configuration, so 9 configs x 1000 is ~12 min.
E3_FIELD_HANDS = 1000
# Iterations per worker between syncs (#318): ~1 min of E3 work at CI speed, so pickling the regrets
# (tens of thousands of keys) stays small next to the work.
E3_SYNC_BATCH = 500
# Noisy-learner hands per (form, level): 4000 gave CI ~±0.1-0.15 bb/hand per seed (#261 note).
NOISE_SIM_HANDS = 4000
SUMMARY_MAX_BYTES = 64 * 1024        # what may be pushed to ops per run
ARTIFACT_MAX_BYTES = 256 * 1024 ** 2  # one seed's output folder (uploaded as an artifact)
# Token shapes that must never reach ops or an artifact: GitHub, RunPod, AWS, PEM keys.
SECRET_PATTERNS = re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}|github_pat_\w{20,}|rpa_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}"
                             r"|-----BEGIN [A-Z ]*PRIVATE KEY-----")


def _e2_mccfr(iters: int, seed: int, out: Path, tier: str = "baseline", name: str = "e2-mccfr") -> dict:
    from referee.e2.lbr import exploitability_lb
    from stalker.e2.abstraction import TIERS
    from stalker.e2.mccfr import MCCFR

    abstraction = TIERS[tier]
    t0 = time.monotonic()
    m = MCCFR(seed, abstraction)
    m.iterate(iters)
    train_s = time.monotonic() - t0
    policy = m.policy()
    (out / f"{name}-seed{seed}.policy.json").write_text(json.dumps(policy), encoding="utf-8")
    t1 = time.monotonic()
    # Same LBR deals for every tier and seed, so tiers differ only in what the policy sees (#187).
    lbr = exploitability_lb(policy, hands=LBR_HANDS, seed=10_000 + seed, abstraction=abstraction)
    return {"iters": iters, "tier": tier, "abstraction": abstraction.to_json(), "train_seconds": round(train_s, 1), "iters_per_s": round(iters / max(train_s, 1e-6), 2),
            "infosets": len(m.regret), "lbr": lbr, "lbr_seconds": round(time.monotonic() - t1, 1),
            "policy_sha256": hashlib.sha256(json.dumps(policy, sort_keys=True).encode()).hexdigest()}


LEAGUE_GENERATIONS = 10
# #299: the league exploiter trains 0.5x the policy and never won (#276), so its lower bound was 0.
# Per seat the long exploiter trains this multiple of the policy's iterations.
EXPLOIT_RATIO = 1.5
EXPLOIT_HANDS = 2000
EXPLOIT_CHECKPOINTS = 3


Q1_HANDS = 1000


def _e2_exploit(iters: int, seed: int, out: Path, tier: str, name: str, field: bool = False) -> dict:
    """#299: train a tier policy, freeze it, then a baseline-abstraction exploiter per seat for
    EXPLOIT_RATIO x iters, recording its gain at evenly spaced checkpoints (is it still rising?).
    `field` (#306): train against a mixed field (`stalker.e2.field`) instead of a copy of itself.
    Also records the persona-field mean (Gate Q1 report) and LBR on the same frozen policy."""
    import numpy as np

    from referee.e2.exploiter import BASELINE, Exploiter, play
    from referee.e2.lbr import exploitability_lb
    from stalker.e2.abstraction import TIERS
    from stalker.e2.field import FieldMCCFR
    from stalker.e2.league import League
    from stalker.e2.mccfr import MCCFR

    t0 = time.monotonic()
    m = FieldMCCFR(seed, TIERS[tier]) if field else MCCFR(seed, TIERS[tier])
    m.iterate(iters)
    train_s = time.monotonic() - t0
    policy = m.policy()
    (out / f"{name}-seed{seed}.policy.json").write_text(json.dumps(policy), encoding="utf-8")
    total = max(EXPLOIT_CHECKPOINTS, int(EXPLOIT_RATIO * iters))
    exs = {seat: Exploiter(policy, TIERS[tier], seat, seed + 17 * seat, BASELINE) for seat in (0, 1)}
    curve, done, ex_s = [], 0, 0.0
    for c in range(1, EXPLOIT_CHECKPOINTS + 1):
        step = total * c // EXPLOIT_CHECKPOINTS - done
        t1 = time.monotonic()
        for ex in exs.values():
            ex.iterate(step)
        ex_s += time.monotonic() - t1
        done += step
        # Same deals at every checkpoint, so the curve moves only with the exploiter's training.
        w0, w1 = (np.array(w) for w in play({s: e.policy("current") for s, e in exs.items()}, policy, TIERS[tier],
                                             EXPLOIT_HANDS, 20_000 + seed))
        se = float(np.hypot(w0.std(ddof=1) / np.sqrt(len(w0)), w1.std(ddof=1) / np.sqrt(len(w1))) / 2)
        curve.append({"exploiter_iters": done, "gain_bb": round(float((w0.mean() + w1.mean()) / 2), 4),
                      "stderr_bb": round(se, 4)})
    q1 = League(tier, seed=seed)._field(policy, TIERS[tier], Q1_HANDS, 30_000 + seed)
    lbr = exploitability_lb(policy, hands=LBR_HANDS, seed=10_000 + seed, abstraction=TIERS[tier])
    return {"iters": iters, "tier": tier, "field_play": field,
            "exploiter": {"tier": "baseline", "ratio": EXPLOIT_RATIO, "strategy": "current"},
            "q1": None if q1 is None else {"field_bb": q1[0], "stderr_bb": q1[1], "worst_persona": q1[2],
                                          "ci95_low_bb": q1[4]},
            "lbr": lbr, "curve": curve, "gain_bb": curve[-1]["gain_bb"], "stderr_bb": curve[-1]["stderr_bb"],
            "policy_iters_per_s": round(iters / max(train_s, 1e-6), 2),
            "exploiter_iters_per_s": round(2 * done / max(ex_s, 1e-6), 2), "wall_seconds": round(time.monotonic() - t0, 1),
            "policy_sha256": hashlib.sha256(json.dumps(policy, sort_keys=True).encode()).hexdigest()}


def _e2_league(tier: str, exploiter_tier: str | None = None, name: str | None = None):
    """League v1 (#202, #226) at a TP tier: `iters` main self-play iterations over LEAGUE_GENERATIONS
    generations, each gated by a fresh exploiter, the snapshot pool and the persona field.
    `exploiter_tier` (#276): the exploiter's own card abstraction; None = the policy's tier."""
    name = name or f"e2-league-{tier}"

    def job(iters: int, seed: int, out: Path) -> dict:
        from dataclasses import asdict

        from stalker.e2.league import League

        per_gen = max(1, iters // LEAGUE_GENERATIONS)
        t0 = time.monotonic()
        lg = League(tier, seed=seed, exploiter_tier=exploiter_tier)
        hist = lg.run(LEAGUE_GENERATIONS, per_gen, exploiter_iters=min(20_000, per_gen), hands=1000)
        if lg.champion is not None:
            (out / f"{name}-seed{seed}.policy.json").write_text(json.dumps(lg.champion), encoding="utf-8")
        champ = [g for g in hist if g.promoted]
        return {"iters": per_gen * LEAGUE_GENERATIONS, "tier": tier, "generations": [asdict(g) for g in hist],
                "exploiter": {"tier": lg.exploiter_tier or tier, "ratio": lg.exploiter_ratio,
                              "strategy": lg.exploiter_strategy},
                "promoted": len(champ), "champion": asdict(champ[-1]) if champ else None,
                "wall_train_seconds": round(time.monotonic() - t0, 1)}
    return job


def _e2_eq(iters: int, seed: int, out: Path, tier: str, name: str) -> dict:
    """#188: the equity-against-range view, measured by LBR through the same dynamic view."""
    from referee.e2.lbr import exploitability_lb
    from stalker.e2.eq_view import EQ_TIERS, EqMCCFR

    t0 = time.monotonic()
    m = EqMCCFR(seed, EQ_TIERS[tier])
    m.iterate(iters)
    train_s = time.monotonic() - t0
    policy = m.policy()
    (out / f"{name}-seed{seed}.policy.json").write_text(json.dumps(policy), encoding="utf-8")
    t1 = time.monotonic()
    lbr = exploitability_lb(policy, hands=LBR_HANDS, seed=10_000 + seed, view=m.view)
    return {"iters": iters, "tier": tier, "view": m.view.to_json(), "train_seconds": round(train_s, 1),
            "iters_per_s": round(iters / max(train_s, 1e-6), 2), "infosets": len(m.regret), "lbr": lbr,
            "lbr_seconds": round(time.monotonic() - t1, 1),
            "policy_sha256": hashlib.sha256(json.dumps(policy, sort_keys=True).encode()).hexdigest()}


def _e3_tp(iters: int, seed: int, out: Path, tier: str, name: str, players: int = 6, resume: Path | None = None,
           workers: int = 1, menu: str = "v1", raise_cap: int | None = 3) -> dict:
    """`resume` (#301): a folder holding this seed's checkpoint from an earlier run; train `iters` more.
    `workers` > 1 trains one chain on that many processes, batch-synchronously (#318).
    `menu`/`raise_cap` (#339): the game rules; LBR and the field are dealt under the same rules."""
    from stalker.e3 import parallel
    from stalker.e3.mccfr import E3MCCFR
    from stalker.e3.tp_key import TIER_DEPTH, TIER_K

    ckpt = f"{name}-seed{seed}.ckpt.json"
    if resume is None:
        m = E3MCCFR(seed, TIER_K[tier], players, TIER_DEPTH[tier], menu, raise_cap)
    elif (resume / ckpt).is_file():
        m = E3MCCFR.from_state(json.loads((resume / ckpt).read_text(encoding="utf-8")))
    else:
        raise SystemExit(f"{resume / ckpt} not found: resume_run must be an earlier {name} run with this seed "
                         "(its train-<seed> artifact holds the checkpoint); leave resume_run empty to start fresh")
    prev = m.iterations
    t0 = time.monotonic()
    parallel.iterate(m, iters, workers, E3_SYNC_BATCH)
    train_s = time.monotonic() - t0
    (out / ckpt).write_text(json.dumps(m.state()), encoding="utf-8")
    avg, cur = m.policy(), m.current_policy()
    (out / f"{name}-seed{seed}.policy.json").write_text(json.dumps({"average": avg, "current": cur}), encoding="utf-8")
    return {"iters": m.iterations, "chunk_iters": iters, "resumed_from": prev, "tier": tier, "depth": m.depth,
            "menu": m.menu, "raise_cap": m.raise_cap,
            "players": players, "workers": workers, "train_seconds": round(train_s, 1),
            "iters_per_s": round(iters / max(train_s, 1e-6), 2), **e3_evaluate(m, seed, avg, cur)}


def e3_evaluate(m, seed: int, avg: dict | None = None, cur: dict | None = None) -> dict:
    """The CI E3 evaluation of a trained model: LBR of both policies, coverage, field (6-max only).
    Shared with the RunPod trainer (`stalker.tools.pod_train`, #333) so pod and CI numbers compare.
    `lbr_seconds` counts LBR and coverage only (before #333 it also counted the field evaluation)."""
    from referee.e3.field import evaluate as field_eval
    from referee.e3.lbr import exploitability_lb
    from stalker.e3 import game as G
    from stalker.e3.mccfr import coverage

    avg = m.policy() if avg is None else avg
    cur = m.current_policy() if cur is None else cur
    t1 = time.monotonic()
    # Same LBR deals for both policies.
    with G.rules(m.menu, m.raise_cap):
        lbr = {k: exploitability_lb(pol, E3_LBR_HANDS, seed=10_000 + seed, k=m.k, n=m.n, depth=m.depth)
               for k, pol in (("average", avg), ("current", cur))}
        # #343: an independent estimate (same seed, but deals drift once the exploiter picks another line) whose
        # exploiter may also use sizes off the menu (the plain LBR undercounts what it can take)
        offmenu = exploitability_lb(cur, E3_LBR_HANDS, seed=10_000 + seed, k=m.k, n=m.n, depth=m.depth,
                                    extra_sizes=True)
        cov = coverage(m)
        t2 = time.monotonic()
        field = field_eval(cur, E3_FIELD_HANDS, seed=20_000 + seed, k=m.k, depth=m.depth) if m.n == 6 else None
    return {"field": field, "field_seconds": round(time.monotonic() - t2, 1), "infosets": len(m.regret),
            "coverage": cov, "lbr": lbr["current"], "lbr_average": lbr["average"], "lbr_offmenu": offmenu,
            "lbr_seconds": round(t2 - t1, 1),
            "policy_sha256": hashlib.sha256(json.dumps(cur, sort_keys=True).encode()).hexdigest()}


def _tp_noise_sim(iters: int, seed: int, out: Path) -> dict:
    """#261: decision loss of a noisy TP learner, form (equity / rank) x level, on the E2 beginner policy."""
    from stalker.tp.noise_sim import table

    t0 = time.monotonic()
    rows = table(iters, NOISE_SIM_HANDS, seed, levels=("exact", "expert", "mid", "beginner"))
    return {"iters": iters, "hands": NOISE_SIM_HANDS, "rows": rows, "wall_sim_seconds": round(time.monotonic() - t0, 1)}


JOBS = {"e2-mccfr": _e2_mccfr,
        "e2-tier-beginner": partial(_e2_mccfr, tier="beginner", name="e2-tier-beginner"),
        "e2-tier-mid": partial(_e2_mccfr, tier="mid", name="e2-tier-mid"),
        "e2-eq-beginner": partial(_e2_eq, tier="beginner", name="e2-eq-beginner"),   # #188
        "e2-eq-mid": partial(_e2_eq, tier="mid", name="e2-eq-mid"),
        "e2-league-beginner": _e2_league("beginner"), "e2-league-mid": _e2_league("mid"),
        # #276: does a finer exploiter find what a same-tier one cannot?
        "e2-league-beginner-xbase": _e2_league("beginner", "baseline", "e2-league-beginner-xbase"),
        "e3-tp-beginner": partial(_e3_tp, tier="beginner", name="e3-tp-beginner"),     # #196/#197, 6-max
        "e3-tp-mid": partial(_e3_tp, tier="mid", name="e3-tp-mid"),
        # #318: one chain on the runner's 4 vCPUs
        "e3-tp-beginner-w4": partial(_e3_tp, tier="beginner", name="e3-tp-beginner-w4", workers=4),
        "e3-tp-mid-w4": partial(_e3_tp, tier="mid", name="e3-tp-mid-w4", workers=4),
        "e3-tp-pro-w4": partial(_e3_tp, tier="pro", name="e3-tp-pro-w4", workers=4),       # #325
        # #324: the target table size (CHARTER), same chains
        "e3-tp-beginner9-w4": partial(_e3_tp, tier="beginner", name="e3-tp-beginner9-w4", players=9, workers=4),
        "e3-tp-mid9-w4": partial(_e3_tp, tier="mid", name="e3-tp-mid9-w4", players=9, workers=4),
        # #339: TP.md section 6 size menu vs e3-tp-mid-w4, with and without the per-street raise cap
        "e3-tp-mid-tp6-w4": partial(_e3_tp, tier="mid", name="e3-tp-mid-tp6-w4", workers=4, menu="tp6"),
        "e3-tp-mid-tp6nc-w4": partial(_e3_tp, tier="mid", name="e3-tp-mid-tp6nc-w4", workers=4, menu="tp6",
                                      raise_cap=None),
        "tp-noise-sim": _tp_noise_sim,                                                  # #261
        "e2-exploit-beginner": partial(_e2_exploit, tier="beginner", name="e2-exploit-beginner"),  # #299
        # #306: the same measurement on a policy trained against a mixed field
        "e2-exploit-field-beginner": partial(_e2_exploit, tier="beginner", name="e2-exploit-field-beginner", field=True)}


RESUMABLE = {"e3-tp-beginner", "e3-tp-mid", "e3-tp-beginner-w4", "e3-tp-mid-w4", "e3-tp-pro-w4",
             "e3-tp-beginner9-w4", "e3-tp-mid9-w4", "e3-tp-mid-tp6-w4", "e3-tp-mid-tp6nc-w4"}   # #301


def run(job: str, iters: int, seed: int, out: Path, resume: Path | None = None) -> Path:
    if job not in JOBS:
        raise SystemExit(f"unknown job {job!r}; allowed: {sorted(JOBS)}")
    if not 1 <= iters <= 10_000_000:
        raise SystemExit("iters must be between 1 and 10^7")
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    if resume is not None and job not in RESUMABLE:
        raise SystemExit(f"{job} cannot resume; resumable jobs: {sorted(RESUMABLE)} (leave resume_run empty)")
    res = JOBS[job](iters, seed, out, **({"resume": resume} if resume is not None else {}))
    path = out / f"{job}-seed{seed}.json"
    path.write_text(json.dumps({"job": job, "seed": seed, "wall_seconds": round(time.monotonic() - t0, 1),
                                **res}, indent=1), encoding="utf-8")
    size = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    if size > ARTIFACT_MAX_BYTES:
        raise SystemExit(f"{out}: {size} bytes > {ARTIFACT_MAX_BYTES}; write a smaller policy (prune or quantize) "
                         "or raise ARTIFACT_MAX_BYTES with a reason in the PR")
    check_clean(path.read_text(encoding="utf-8"), str(path))
    return path


def check_clean(text: str, where: str) -> None:
    """Refuse text that carries a token shape or the value of a secret-looking environment variable."""
    if SECRET_PATTERNS.search(text):
        raise SystemExit(f"{where}: looks like it contains a credential; results must hold numbers only")
    for k, v in os.environ.items():
        if re.search(r"TOKEN|SECRET|KEY|PASSWORD", k) and len(v) >= 8 and v in text:
            raise SystemExit(f"{where}: contains the value of ${k}; results must hold numbers only")


def summary_text(job: str, folder: Path) -> str:
    """The JSON pushed to ops: refuses unknown jobs, zero successful runs, oversize or secret-bearing output."""
    if job not in JOBS:
        raise SystemExit(f"unknown job {job!r}; allowed: {sorted(JOBS)}")
    s = summarize(job, folder)
    if not s["runs"]:
        raise SystemExit(f"no successful {job} runs under {folder}; nothing to push (see the run jobs' logs)")
    text = json.dumps(s, indent=1)
    if len(text.encode("utf-8")) > SUMMARY_MAX_BYTES:
        raise SystemExit(f"summary is {len(text.encode())} bytes > {SUMMARY_MAX_BYTES}; keep per-seed detail in the "
                         "artifacts and only aggregates in the summary")
    check_clean(text, "summary")
    return text


def summarize(job: str, folder: Path) -> dict:
    runs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(folder.rglob(f"{job}-seed*.json"))
            if not p.name.endswith((".policy.json", ".ckpt.json"))]
    # Which code produced these numbers: train.yml can run on a branch ref before merge (#245).
    out = {"job": job, "runs": len(runs), "seeds": [r["seed"] for r in runs],
           "ref": os.environ.get("GITHUB_REF_NAME"), "sha": os.environ.get("GITHUB_SHA"),
           "run_id": os.environ.get("GITHUB_RUN_ID"), "resumed_from_run": os.environ.get("RESUME_RUN") or None}
    if job.startswith(("e2-", "e3-")) and not job.startswith(("e2-league-", "e2-exploit-")) and runs:  # league runs report champions, not LBR
        lb = [r["lbr"]["lbr_bb"] for r in runs]
        out.update({"iters": runs[0]["iters"], "iters_per_s_mean": round(sum(r["iters_per_s"] for r in runs) / len(runs), 2),
                    "lbr_bb_mean": round(sum(lb) / len(lb), 4), "lbr_bb_by_seed": lb,
                    "lbr_stderr_by_seed": [r["lbr"].get("stderr_bb") for r in runs]})
        if all(r.get("lbr_offmenu") for r in runs):    # E3 (#343): exploiter with off-menu sizes, current policy
            out["lbr_offmenu_bb_by_seed"] = [r["lbr_offmenu"]["lbr_bb"] for r in runs]
    if job in RESUMABLE and runs:
        out["resumed_from_iters_by_seed"] = [r.get("resumed_from", 0) for r in runs]
    if job.startswith("e3-") and runs and all(r.get("field") for r in runs):  # #295: max loss vs the opponent set
        out.update({"field_sha256": runs[0]["field"]["sha256"], "field_deals": runs[0]["field"]["deals"],
                    "field_worst_by_seed": [r["field"]["worst"] for r in runs],
                    "field_bb100_by_seed": [{c["name"]: c["bb100"] for c in r["field"]["configs"]} for r in runs]})
    if job.startswith("e2-league-") and runs:
        champs = [r["champion"] or {} for r in runs]  # one entry per seed (null without a champion), aligned with seeds
        out.update({"iters": runs[0]["iters"], "exploiter": runs[0].get("exploiter"),
                    # per seed, the iterations each generation's exploiter actually trained (#247)
                    "exploiter_iters_by_seed": [[g.get("exploiter_iters") for g in r.get("generations", [])] for r in runs],
                    "promoted_by_seed": [r["promoted"] for r in runs],
                    "champion_gain_bb_by_seed": [c.get("gain_bb") for c in champs],
                    "champion_field_bb_by_seed": [c.get("field_bb") for c in champs],
                    "champion_field_ci95_low_bb_by_seed": [c.get("field_ci95_low_bb") for c in champs],
                    "champion_worst_persona_by_seed": [c.get("worst_persona") for c in champs]})
    if job.startswith("e2-exploit-") and runs:
        out.update({"iters": runs[0]["iters"], "exploiter": runs[0]["exploiter"],
                    "lbr_bb_by_seed": [r["lbr"]["lbr_bb"] for r in runs],
                    "q1_field_bb_by_seed": [(r["q1"] or {}).get("field_bb") for r in runs],
                    "gain_bb_by_seed": [r["gain_bb"] for r in runs], "stderr_bb_by_seed": [r["stderr_bb"] for r in runs],
                    "curve_by_seed": [[(c["exploiter_iters"], c["gain_bb"]) for c in r["curve"]] for r in runs],
                    "policy_iters_per_s_mean": round(sum(r["policy_iters_per_s"] for r in runs) / len(runs), 2),
                    "exploiter_iters_per_s_mean": round(sum(r["exploiter_iters_per_s"] for r in runs) / len(runs), 2),
                    "wall_seconds_max": max(r["wall_seconds"] for r in runs)})
    if job == "tp-noise-sim" and runs:
        out.update({"iters": runs[0]["iters"], "hands": runs[0]["hands"], "rows_by_seed": [r["rows"] for r in runs]})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("job")
    r.add_argument("--iters", type=int, required=True)
    r.add_argument("--seed", type=int, default=0)
    r.add_argument("--out", type=Path, required=True)
    r.add_argument("--resume", type=Path, help="folder with this seed's checkpoint from an earlier run (#301)")
    s = sub.add_parser("summarize")
    s.add_argument("job")
    s.add_argument("folder", type=Path)
    a = ap.parse_args(argv)
    if a.cmd == "run":
        print(run(a.job, a.iters, a.seed, a.out, a.resume))
    else:
        print(summary_text(a.job, a.folder))
    return 0


if __name__ == "__main__":
    sys.exit(main())
