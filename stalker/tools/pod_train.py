"""E3 TP training on a many-core RunPod CPU pod (#333): `python -m stalker.tools.pod_train --out r.json`.

One chain, `--workers` processes (batch-synchronous, `stalker.e3.parallel`), trained until
`--minutes` of wall time, then evaluated exactly as the CI `e3-tp-*` jobs are
(`stalker.train_jobs.e3_evaluate`: LBR, coverage, field), so pod and CI numbers compare. The launcher
fetches one JSON of at most 256 MB (#346), so the result carries the summary plus the model as a compressed
`.npz` (base64): keys, regrets, average-strategy sums and visit counts, float32 if float64 does not
fit. `--unpack` turns it back into the CI layout (`<job>-seed<s>.ckpt.json`, `.policy.json`), so a
pod run can be evaluated, compared and resumed (`resume_run` in CI, or `--resume` here) like a CI one.
A float32 checkpoint continues the chain but not bit for bit.

Pod chains (#354): `cloud.yml resume_run=<id>` hands run <id>'s result to the next pod (launcher upload,
gzipped), which passes it as `--resume-result`; the job, tier, players and board.nut grid must match.
The checkpoint is kept under RESUME_BUDGET (the proxy's upload limit) when float32 fits, so a chain
can continue; above that the result still carries it, but only for `--unpack`.

`--ranges average` (#405) trains with TP-feature ranges from the average-strategy snapshot; the npz then also
carries the snapshot rows, and a chain resumes only a result trained with the same ranges.

`--key-variant` / `--stacks` (#400): the key variant (`stalker.e3.tp_key`, e.g. the combined cash key "c1") and the
table stacks ("sampled" 20-250BB). The job name carries the variant (`e3-tp-mid-c1-pod`), and a chain resumes only a
result of the same variant, key version and stacks.

`--player-mix 2,3,4,5,6` (#486, ADR 0019 D): each hand is dealt to a player count drawn from the list; `--players`
is then the evaluation table. The job name carries `-mixn` (`e3-tp-mid-c1-mixn-pod`), and a chain resumes only a
result of the same mix.

Tournament training (#899, ADR 0027): `--payoff icm --preset <name> --stage <e|b|m|f> --level-index <i> --lam <x>
--stacks bubble:<even|random|skewed>` deal every hand at the preset's survivors (`--players`) and reward the prize-equity
change; `--ante` defaults to the preset level's BB ante. The result and its `model` block then carry `train_env`
(`tournament_env`) and a chain resumes only a result of the same one. Without these arguments nothing changes.

`--max-iters N` (#547): stop once the chain (resume included) has N iterations, the last sync batch cut to land on
N; `--minutes` stays the ceiling. The result's `stopped_by` says which limit ended training ("max_iters" or
"minutes"), so runs of different pod speeds compare at the same iteration count. Without it training is as before.

Warm start (#918, ADR 0027 decision 4 arm B): `--prior-result PATH` (a pod result, plain or gzipped, or a CI
`.ckpt.json`) of a cash run of the same tier, key variant and rules seeds the average-strategy sums of a fresh
run: each prior key's `tc0` slot becomes the training env's `t<stage><ante>` and its normalized average strategy
goes in `min(visits, PRIOR_W_CAP)` times. Regrets start at 0 (copying regrets across rewards is refused by the ADR).
Keys of player counts the run never deals are left out; `call|` keys have no env slot and keep their name. Reading
the prior is inside the `--minutes` clock ("same compute"). The result's top-level `prior` names the source (run id,
file sha256) and the cap; it is not in `train_env`, so a chain of the run resumes by its environment as before.
"""
from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import io
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from stalker.jsonio import read_json
from stalker.tools.pod_bench import machine, max_child_rss_mb, max_rss_mb

RESULT_BUDGET = 250 * 1024 * 1024  # under the launcher's 256 MB result cap (#346), with room for the summary
# = harness/cloud/launcher.py RESUME_MAX_BYTES (tested): the gzipped upload is about the npz size
RESUME_BUDGET = 95 * 1024 * 1024
GZIP_MAGIC = bytes((0x1F, 0x8B))
PROGRESS_SECONDS = 300
PRIOR_W_CAP = 1000   # ADR 0027 decision 4: w = min(the key's prior visits, 1000), an assumption the A/B checks


def tournament_env(preset: str, players: int, stage: str = "c", level_index: int = 0, lam: float = 0.0,
                   stacks: str = "uniform", payoff: str = "icm", ante: int | None = None) -> tuple[dict, dict]:
    """(`E3MCCFR` keyword arguments, `train_env` record) of a tournament training run (#899, ADR 0027 decisions 1 and 5).

    Payouts are the preset's `payout_ratios()`; `ante` (E3 chips, BB = 100) defaults to the preset level's BB ante,
    0 if the level has none. `train_env.env_id` is `from_tournament(preset).env_id`; stage, level, lam and stacks are
    training settings, not part of the id."""
    from stalker.e3 import game as G
    from stalker.env.spec import from_tournament
    from stalker.tournament.config import load_preset

    try:
        cfg = load_preset(preset)
    except (OSError, ValueError, KeyError) as e:
        raise SystemExit(f"--preset {preset!r}: {e}; pass a name from stalker/tournament/presets") from None
    if not 0 <= level_index < len(cfg.levels):
        raise SystemExit(f"--level-index {level_index}: preset {preset} has levels 0..{len(cfg.levels) - 1}")
    lv = cfg.levels[level_index]
    if ante is None:
        if lv.ante and cfg.ante_mode != "bb_ante":
            raise SystemExit(f"preset {preset} level {level_index} has a {cfg.ante_mode} ante, which E3 does not deal; "
                             "pass --ante in chips (e.g. 0) to choose")
        ante = int(round(lv.ante * G.BB / lv.bb))
    bubble = stacks.startswith("bubble:")
    kw = {"payoff": payoff, "payouts": preset if payoff == "icm" else None, "lam": lam, "ante": ante, "stage": stage,
          **({"stack_preset": preset, "stack_remaining": players, "stack_level": level_index} if bubble else {})}
    train_env = {"env_id": from_tournament(cfg).env_id, "stage": stage, "level_index": level_index, "lam": lam,
                 "stacks": stacks}
    return kw, train_env


def job_name(tier: str, players: int, key_variant: str = "", player_mix: tuple[int, ...] = ()) -> str:
    return (f"e3-tp-{tier}{'' if players == 6 else players}{'-' + key_variant if key_variant else ''}"
            f"{'-mixn' if player_mix else ''}-pod")


def load_resume_result(path: Path, tier: str, players: int, menu: str = "v1",
                       raise_cap: int | None | str = "default", ranges: str = "current",
                       avg_rule: str = "legacy", key_variant: str = "", stacks: str = "uniform",
                       player_mix: tuple[int, ...] = (), train_env: dict | None = None) -> tuple[dict, str | None]:
    """`E3MCCFR.state()` from an earlier pod result (plain or gzipped JSON), plus the run it came from.

    Refuses a result of another job: its keys would mean other things in this table."""
    from stalker.e3 import game as G
    from stalker.e3 import tp_key as K

    raise_cap = G.RAISE_CAP if raise_cap == "default" else raise_cap
    raw = path.read_bytes()
    r = json.loads(gzip.decompress(raw) if raw[:2] == GZIP_MAGIC else raw)
    if not r.get("checkpoint"):
        raise SystemExit(f"{path}: no checkpoint to resume ({r.get('checkpoint_note', 'missing')}); "
                         "dispatch without resume_run")
    model = r.get("model") or {}
    want = {"job": job_name(tier, players, key_variant, player_mix), "tier": tier, "players": players}
    bad = [f"{k} {r.get(k)!r} != {v!r}" for k, v in want.items() if r.get(k) != v]
    bad += [f"model.{k} {model.get(k)!r} != {v!r}" for k, v in
            {"k": K.TIER_K[tier], "n": players, "depth": K.TIER_DEPTH[tier]}.items() if model.get(k) != v]
    # the game rules (#339): a result from before them was v1 with cap 3, as E3MCCFR.from_state reads it
    rules = {"menu": (model.get("menu", "v1"), menu), "raise_cap": (model.get("raise_cap", G.RAISE_CAP), raise_cap),
             "ranges": (model.get("ranges", "current"), ranges),
             "avg_rule": (model.get("avg_rule", "legacy"), avg_rule),    # #426: a result before it was legacy
             # #400: a result before these was plain keys on 100BB tables
             "key_variant": (model.get("key_variant", ""), key_variant), "stacks": (model.get("stacks", "uniform"), stacks),
             "key_version": (model.get("key_version"), K.KEY_VERSIONS.get(key_variant)),
             # #486: a result before it dealt every hand to `players`
             "player_mix": (list(model.get("player_mix", [])), list(player_mix)),
             # #899: a result before it, or of cash training, has none
             "train_env": (r.get("train_env"), train_env)}
    bad += [f"{k} {got!r} != {want!r}" for k, (got, want) in rules.items() if got != want]
    if K.TIER_DEPTH[tier] == "pro" and model.get("nut_k", K.K_PRO) != K.NUT_K:
        bad.append(f"nut_k {model.get('nut_k', K.K_PRO)} != {K.NUT_K} (#332)")
    if bad:
        raise SystemExit(f"{path}: cannot resume this result here ({'; '.join(bad)}); pass a run of the same "
                         "job as resume_run, or start fresh without it")
    st = unpack_state(base64.b64decode(r["checkpoint"]["b64"]), model)
    return st, (str(r["run_id"]) if r.get("run_id") is not None else None)


def read_prior(path: Path) -> tuple[dict, dict]:
    """(`E3MCCFR.state()` data, source record) of a warm-start prior: a pod result or a CI checkpoint (#918)."""
    raw = path.read_bytes()
    try:
        r = json.loads(gzip.decompress(raw) if raw[:2] == GZIP_MAGIC else raw)
    except (ValueError, OSError) as e:
        raise SystemExit(f"--prior-result {path}: not JSON ({e}); pass a pod result or a .ckpt.json") from None
    src = {"run_id": str(r["run_id"]) if r.get("run_id") is not None else None,
           "sha256": hashlib.sha256(raw).hexdigest(), "w_cap": PRIOR_W_CAP}
    if "avg" in r and "visits" in r:   # a CI-layout checkpoint (or `--unpack` output)
        return r, src
    if not r.get("checkpoint"):
        raise SystemExit(f"--prior-result {path}: no model in it ({r.get('checkpoint_note', 'no checkpoint')}); "
                         "pass a pod result with a checkpoint, or its `--unpack`ed .ckpt.json")
    return unpack_state(base64.b64decode(r["checkpoint"]["b64"]), r.get("model") or {}), src


def apply_prior(m, st: dict, cap: int = PRIOR_W_CAP) -> int:
    """Seed fresh model `m`'s average-strategy sums from prior state `st` (#918); returns the keys seeded.

    Refuses a prior whose keys mean other things in `m`'s table: another tier, key variant or version, action
    menu, a prior that is not cash (`tc0`), or one that never dealt a player count `m` deals."""
    from stalker.e3 import game as G
    from stalker.e3 import tp_key as K
    from stalker.e3.mccfr import key_players

    if m.iterations or m.regret or any(v is not None for v in m.avg.values()):
        raise SystemExit("--prior-result seeds a fresh run only; drop --resume/--resume-result or the prior")
    have = {"k": st.get("k"), "depth": st.get("depth"), "key_variant": st.get("key_variant", ""),
            "key_version": st.get("key_version"), "menu": st.get("menu", "v1"),
            "raise_cap": st.get("raise_cap", G.RAISE_CAP)}
    want = {"k": m.k, "depth": m.depth, "key_variant": m.key_variant, "key_version": K.KEY_VERSIONS.get(m.key_variant),
            "menu": m.menu, "raise_cap": m.raise_cap}
    bad = [f"{k} {have[k]!r} != {v!r}" for k, v in want.items() if have[k] != v]
    if m.key_variant != "c1":
        bad.append(f"key_variant {m.key_variant!r}: only c1 keys carry the t<stage><ante> slot")
    if (st.get("stage", "c"), st.get("ante", 0)) != ("c", 0) or st.get("train_env"):
        bad.append(f"prior env stage {st.get('stage', 'c')!r} ante {st.get('ante', 0)!r}: the prior must be a cash "
                   "(tc0) run")
    dealt = set(st.get("player_mix") or [st.get("n")])
    need = set(m.player_mix or (m.n,))
    if not need <= dealt:
        bad.append(f"prior dealt {sorted(dealt)} players, this run deals {sorted(need)}")
    if bad:
        raise SystemExit(f"--prior-result: cannot seed this run ({'; '.join(bad)}); pass a cash c1 policy of the "
                         "same tier, menu and key version (e.g. the c1 mixn run of the tier)")
    slot = f"t{m.stage}{int(m.ante > 0)}"
    visits, seeded = st.get("visits", {}), 0
    for key, row in st.get("avg", {}).items():
        row = np.asarray(row, dtype=float)
        w = min(int(visits.get(key, 0)), cap)
        n = key_players(key)
        if w <= 0 or not row.sum() > 0 or (n is not None and n not in need):
            continue
        new = "|".join(slot if f == "tc0" else f for f in key.split("|"))
        m.avg[new] = row / row.sum() * w
        seeded += 1
    return seeded


def pack(m, dtype=np.float64) -> bytes:
    """The model's tables as a compressed npz (rng and counters travel in the JSON summary)."""
    keys = sorted(m.regret.keys() | {k for k, v in m.avg.items() if v is not None})
    zero = np.zeros(0)
    reg = [m.regret.get(k, zero) for k in keys]
    avg = [m.avg[k] if m.avg.get(k) is not None else zero for k in keys]
    extra = {}
    if m.ranges == "average":  # the snapshot rows (#405); its keys are a subset of the average's
        snap = [m.snap.get(k, zero) for k in keys]
        extra = {"snap_len": np.array([len(r) for r in snap], dtype=np.int16),
                 "snap": np.concatenate(snap + [zero]).astype(dtype)}
    buf = io.BytesIO()
    np.savez_compressed(buf, keys=np.array("\n".join(keys).encode()),
                        reg_len=np.array([len(r) for r in reg], dtype=np.int16),
                        avg_len=np.array([len(a) for a in avg], dtype=np.int16),
                        reg=np.concatenate(reg + [zero]).astype(dtype), avg=np.concatenate(avg + [zero]).astype(dtype),
                        visits=np.array([m.visits.get(k, 0) for k in keys], dtype=np.int64), **extra)
    return buf.getvalue()


def unpack_state(blob: bytes, meta: dict) -> dict:
    """`E3MCCFR.state()` data from `pack` output plus the summary's `model` block."""
    z = np.load(io.BytesIO(blob))
    raw = bytes(z["keys"])
    keys = raw.decode().split("\n") if raw else []
    regret, avg, visits = {}, {}, {}
    ri = ai = 0
    # z[name] decompresses the whole array on every access, so read each once (#355).
    reg, av = z["reg"].astype(float).tolist(), z["avg"].astype(float).tolist()
    # Python ints for the offsets: NumPy 2 keeps int + int16 as int16, which wraps past 32767 (#355).
    for k, rl, al, v in zip(keys, z["reg_len"].tolist(), z["avg_len"].tolist(), z["visits"].tolist()):
        if rl:
            regret[k] = reg[ri:ri + rl]
        if al:
            avg[k] = av[ai:ai + al]
        if v:
            visits[k] = int(v)
        ri, ai = ri + rl, ai + al
    version = 3 if meta.get("avg_rule") == "own" else 1   # a result before #426 has no avg_rule: legacy
    if meta.get("key_variant"):   # E3MCCFR.state versions (#398, #399)
        version = 5 if meta.get("stacks", "uniform") != "uniform" else 4
    if meta.get("player_mix"):   # #486; with the per-size counts (#535) version 7
        version = 7 if "mix_counts" in meta else 6
    if "train_env" in meta:   # #899: E3MCCFR.state versions 9-11 (payoff, ante/stage, bubble stacks)
        # same rule as E3MCCFR.state(): a chip run with no ante/stage/bubble stacks keeps its earlier version
        env = (meta.get("ante", 0), meta.get("stage", "c"))
        if meta.get("payoff", "chip") != "chip":
            version = 9
        if meta.get("stack_preset") or env != (0, "c"):
            version = 11 if meta.get("stack_preset") else 10
    if meta.get("ranges", "current") != "average":
        return {"version": version, "avg_rule": "legacy", **meta, "regret": regret, "avg": avg, "visits": visits}
    snap, si, sv = {}, 0, z["snap"].astype(float).tolist()
    for k, sl in zip(keys, z["snap_len"].tolist()):
        if sl:
            snap[k] = sv[si:si + sl]
        si += sl
    return {"version": version if "train_env" in meta else max(version, 2), "avg_rule": "legacy", **meta, "regret": regret, "avg": avg, "visits": visits,
            "snap": snap}


def train(tier: str, players: int, workers: int, minutes: float, seed: int, batch: int,
          resume: dict | None = None, menu: str = "v1", raise_cap: int | None | str = "default",
          ranges: str = "current", avg_rule: str = "legacy", key_variant: str = "", stacks: str = "uniform",
          player_mix: tuple[int, ...] = (), max_iters: int | None = None, env: dict | None = None,
          prior: Path | None = None, log=lambda s: print(s, file=sys.stderr, flush=True)):
    from stalker.e3 import game as G
    from stalker.e3 import parallel
    from stalker.e3.mccfr import E3MCCFR
    from stalker.e3.tp_key import TIER_DEPTH, TIER_K

    env = env or {}   # tournament training (#899); empty = the call every earlier run made
    if resume:
        asked = {k: env[k] for k in ("payoff", "ante", "stage") if k in env}
        sample = (env.get("stack_preset", ""), env.get("stack_remaining", 0), env.get("stack_level", 0))
        m = E3MCCFR.from_state(resume, avg_rule, player_mix, **({**asked, "stack_sample": sample} if env else {}))
    else:
        m = E3MCCFR(seed, TIER_K[tier], players, TIER_DEPTH[tier], menu,
                    G.RAISE_CAP if raise_cap == "default" else raise_cap, ranges, avg_rule=avg_rule,
                    key_variant=key_variant, stacks=stacks, player_mix=player_mix, **env)
    start_iters, timing, prior_rec = m.iterations, {}, None
    t0 = time.monotonic()
    deadline, next_log = t0 + minutes * 60, t0 + PROGRESS_SECONDS
    if prior is not None:   # on the clock: ADR 0027 "same compute" for both arms
        st, prior_rec = read_prior(prior)
        prior_rec["keys"] = apply_prior(m, st)
        prior_rec["read_seconds"] = round(time.monotonic() - t0, 2)
    with ProcessPoolExecutor(workers) if workers > 1 else _NoPool() as p:
        while time.monotonic() < deadline and (max_iters is None or m.iterations < max_iters):
            step = workers * batch if max_iters is None else min(workers * batch, max_iters - m.iterations)
            parallel.iterate(m, step, workers, batch, pool=p if workers > 1 else None, timing=timing)
            if time.monotonic() >= next_log:
                dt = time.monotonic() - t0
                log(json.dumps({"iters": m.iterations, "keys": len(m.regret), "minutes": round(dt / 60, 1),
                                "iters_per_s": round((m.iterations - start_iters) / dt, 1)}))
                next_log += PROGRESS_SECONDS
    train_s = time.monotonic() - t0
    done = m.iterations - start_iters
    total = max(timing.get("total", 0.0), 1e-9)
    stopped = "max_iters" if max_iters is not None and m.iterations >= max_iters else "minutes"
    return m, {**({"prior": prior_rec} if prior_rec else {}), "chunk_iters": done, "max_iters": max_iters, "stopped_by": stopped, "resumed_from": start_iters, "train_seconds": round(train_s, 1),
               "iters_per_s": round(done / max(train_s, 1e-6), 2),
               "sync_frac": round(max(0.0, total - timing.get("compute", 0.0)) / total, 3)}


class _NoPool:
    def __enter__(self):
        return None

    def __exit__(self, *exc):
        return False


def run(tier: str, players: int, workers: int, minutes: float, seed: int, batch: int, resume: dict | None = None,
        budget: int = RESULT_BUDGET, resume_budget: int = RESUME_BUDGET, resumed_from_run: str | None = None,
        menu: str = "v1", raise_cap: int | None | str = "default", ranges: str = "current",
        avg_rule: str = "legacy", key_variant: str = "", stacks: str = "uniform",
        player_mix: tuple[int, ...] = (), max_iters: int | None = None, env: dict | None = None,
        train_env: dict | None = None, lbr_hands: int | None = None, prior: Path | None = None) -> dict:
    from stalker.e3 import tp_key as K
    from stalker.train_jobs import e3_evaluate

    m, stats = train(tier, players, workers, minutes, seed, batch, resume, menu, raise_cap, ranges, avg_rule,
                     key_variant, stacks, player_mix, max_iters, env, prior)
    res = {"job": job_name(tier, players, m.key_variant, m.player_mix), "tier": tier, "players": players, "seed": seed, "workers": workers,
           "batch": batch, "iters": m.iterations, "resumed_from_run": resumed_from_run, **stats}
    res.update(e3_evaluate(m, seed, **({} if lbr_hands is None else {"lbr_hands": lbr_hands})))   # under the model's t<stage><ante> key slot, so LBR reads the rows trained
    res["model"] = {"k": m.k, "n": m.n, "depth": m.depth, "iterations": m.iterations, "nodes": m.nodes,
                    "menu": m.menu, "raise_cap": m.raise_cap, "avg_rule": m.avg_rule, "rng": m.rng.bit_generator.state,
                    **m._grid()}
    if m.key_variant or m.stacks != "uniform":   # absent for plain keys, so those results stay as before #400
        res["model"].update(key_variant=m.key_variant, stacks=m.stacks)
        if m.key_variant in K.KEY_VERSIONS:
            res["model"]["key_version"] = K.KEY_VERSIONS[m.key_variant]
    if m.player_mix:   # absent for n-handed deals, so those results stay as before #486
        res["model"].update(player_mix=list(m.player_mix), **m._count_state())   # #535: counts resume with the table
    if train_env:   # absent for cash training, so those results stay as before #899
        res["train_env"] = dict(train_env)
        res["model"].update(train_env=dict(train_env), ante=m.ante, stage=m.stage, player_mix=list(m.player_mix),
                            key_variant=m.key_variant, stacks=m.stacks)
        if m.payoff != "chip":   # from_state refuses payouts/lam on a chip run
            res["model"].update(payoff=m.payoff, payouts=list(m.payouts), lam=m.lam)
        if m.bubble_stacks():
            res["model"].update(stack_preset=m.stack_preset, stack_remaining=m.stack_remaining,
                                stack_level=m.stack_level)
    if m.ranges == "average":  # absent for current ranges, so those results stay as before #405
        res["model"].update(ranges=m.ranges, range_every=m.range_every, snap_at=m.snap_at)
    res.update(_checkpoint(m, budget, resume_budget))
    res.update(max_rss_mb=max_rss_mb(), max_child_rss_mb=max_child_rss_mb(), machine=machine(),
               regret_sha256=m.regret_hash())   # #447: bit-level drift check against a CI run of the same state
    return res


def _checkpoint(m, budget: int, resume_budget: int) -> dict:
    """float64 if the next pod can take it, else float32; past the resume limit, whatever fits the result."""
    blobs: dict = {}

    def blob(dtype):
        if dtype not in blobs:
            blobs[dtype] = pack(m, dtype)
        return blobs[dtype]

    fits = {"resume": lambda b: len(b) + 1024 * 1024 < resume_budget,
            "result": lambda b: len(b) * 4 // 3 + 64 * 1024 < budget}
    for limit in ("resume", "result"):
        for dtype in (np.float64, np.float32):
            b = blob(dtype)
            if fits["result"](b) and fits[limit](b):
                out = {"checkpoint": {"format": "npz", "dtype": np.dtype(dtype).name,
                                      "b64": base64.b64encode(b).decode()}}
                if limit == "result":
                    out["checkpoint_note"] = (f"npz {len(b)} bytes is over the {resume_budget}-byte pod upload "
                                              "limit: unpack it, but a pod chain cannot resume from it")
                return out
    return {"checkpoint": None, "checkpoint_note": f"model npz over {budget} bytes even as float32; summary only"}


def unpack(result: Path, out: Path) -> list[Path]:
    """Write a pod result's model in the CI artifact layout; returns the files written."""
    from stalker.e3.mccfr import E3MCCFR

    r = json.loads(result.read_text(encoding="utf-8"))
    if not r.get("checkpoint"):
        raise SystemExit(f"{result}: no checkpoint in this result ({r.get('checkpoint_note', 'missing')})")
    st = unpack_state(base64.b64decode(r["checkpoint"]["b64"]), r["model"])
    m = E3MCCFR.from_state(st)
    out.mkdir(parents=True, exist_ok=True)
    stem = f"{r['job']}-seed{r['seed']}"
    ck, pol = out / f"{stem}.ckpt.json", out / f"{stem}.policy.json"
    ck.write_text(json.dumps(st), encoding="utf-8")
    pol.write_text(json.dumps({"average": m.policy(), "current": m.current_policy()}), encoding="utf-8")
    return [ck, pol]


def parse_stacks(text: str) -> str:
    from stalker.e3.mccfr import BUBBLE_PREFIX, STACK_PROFILES, STACKS

    if text in STACKS or (text.startswith(BUBBLE_PREFIX) and text[len(BUBBLE_PREFIX):] in STACK_PROFILES):
        return text
    raise argparse.ArgumentTypeError(f"{text!r}: use {'|'.join(STACKS)} or {BUBBLE_PREFIX}<{'|'.join(STACK_PROFILES)}>")


def tournament_args(a) -> tuple[dict, dict | None]:
    """(`E3MCCFR` kwargs, `train_env`) of the CLI's tournament arguments; ({}, None) when none was given (#899)."""
    from stalker.e3 import tp_key as K

    given = (a.payoff != "chip" or a.preset or a.stage != "c" or a.level_index or a.lam or a.ante is not None
             or a.stacks.startswith("bubble:"))
    if not given:
        return {}, None
    if a.stage not in K.STAGES:
        raise SystemExit(f"--stage {a.stage!r}: use one of {'|'.join(K.STAGES)}")
    if not a.preset:
        raise SystemExit("tournament arguments need --preset <name> (payouts, ante and stacks come from it)")
    if a.stacks == "sampled":
        raise SystemExit("--stacks sampled is cash training; use uniform or bubble:<profile> with --preset")
    if a.payoff != "icm" and a.lam:
        raise SystemExit("--lam only goes with --payoff icm")
    return tournament_env(a.preset, a.players, a.stage, a.level_index, a.lam, a.stacks, a.payoff, a.ante)


def build_parser() -> argparse.ArgumentParser:
    from stalker.e3.mccfr import parse_mix

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tier", default="pro", choices=("beginner", "mid", "pro"))
    ap.add_argument("--players", type=int, default=6)
    ap.add_argument("--workers", type=int, default=32)
    ap.add_argument("--minutes", type=float, default=60, help="training wall time; evaluation comes after")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--batch", type=int, default=500, help="iterations per worker between syncs")
    ap.add_argument("--resume", type=Path, help="a CI-layout .ckpt.json[.gz] to continue")
    ap.add_argument("--menu", default="v1", choices=("v1", "tp6", "real"),
                    help="E3 action menu: v1, tp6 (#339) or real (#382)")
    ap.add_argument("--no-raise-cap", action="store_true", help="no raise cap (#339); default cap 3")
    ap.add_argument("--ranges", default="current", choices=("current", "average"),
                    help="strategy that moves the TP-feature ranges (#405)")
    ap.add_argument("--avg-rule", default="legacy", choices=("legacy", "own"),
                    help="average-strategy accumulation (#426): legacy (every run before it) or own reach")
    ap.add_argument("--key-variant", default="", help="E3 key variant (stalker.e3.tp_key.VARIANTS), e.g. c1 (#400)")
    ap.add_argument("--stacks", default="uniform", type=parse_stacks,
                    help="table stacks: uniform 100BB, sampled 20-250BB (#399) or bubble:<even|random|skewed> "
                    "(survivors of --preset at --level-index, #898)")
    ap.add_argument("--payoff", default="chip", choices=("chip", "icm"), help="icm: prize-equity reward (#883)")
    ap.add_argument("--preset", help="tournament preset (stalker/tournament/presets): payouts, ante, stacks (#899)")
    ap.add_argument("--stage", default="c", help="c1 key tournament stage e|b|m|f (#886); c = cash")
    ap.add_argument("--level-index", type=int, default=0, help="blind level of the --preset table (#899)")
    ap.add_argument("--lbr-hands", type=int, help="LBR deals of the evaluation (default: train_jobs.E3_LBR_HANDS); #901 uses 600")
    ap.add_argument("--lam", type=float, default=0.0, help="payoff icm: bubble correction (ADR 0026), 0 = pure ICM")
    ap.add_argument("--ante", type=int, help="BB ante in E3 chips (BB=100); default: the --preset level's BB ante")
    ap.add_argument("--player-mix", type=parse_mix, default=(),
                    help="per-hand player counts, e.g. 2,3,4,5,6 (#486); --players is then the evaluation table")
    ap.add_argument("--max-iters", type=int, help="stop once the chain (resume included) reaches this many "
                    "iterations (#547); --minutes stays the ceiling")
    ap.add_argument("--resume-result", type=Path, help="an earlier pod result (JSON, may be gzipped) to continue")
    ap.add_argument("--prior-result", type=Path, help="warm start (#918): a cash c1 pod result or .ckpt.json whose "
                    "average strategy seeds this fresh run's averages (tc0 -> t<stage><ante>), regrets 0")
    ap.add_argument("--sha-file", type=Path, help="file holding the source commit (the pod reads it from the tarball)")
    ap.add_argument("--unpack", type=Path, help="instead of training: write this pod result's model to --out (a folder)")
    ap.add_argument("--out", type=Path, required=True)
    return ap


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    if a.unpack:
        for f in unpack(a.unpack, a.out):
            print(f)
        return 0
    if a.workers < 1 or a.minutes <= 0 or a.batch < 1:
        raise SystemExit("--workers and --batch must be >= 1 and --minutes > 0")
    if a.max_iters is not None and a.max_iters < 1:
        raise SystemExit("--max-iters must be >= 1 (leave it out for a time-limited run)")
    if a.resume and a.resume_result:
        raise SystemExit("pass --resume or --resume-result, not both")
    if a.prior_result and (a.resume or a.resume_result):
        raise SystemExit("--prior-result seeds a fresh run; a resumed chain already carries its prior - drop one")
    resume, from_run = (read_json(a.resume) if a.resume else None), None
    cap = None if a.no_raise_cap else "default"
    env, train_env = tournament_args(a)
    if a.resume and (resume.get("train_env") if isinstance(resume, dict) else None) != train_env:
        raise SystemExit(f"{a.resume}: cannot resume (train_env {resume.get('train_env')!r} != {train_env!r}); "
                         "pass a checkpoint of the same tournament environment, or start fresh")
    if a.resume_result:
        resume, from_run = load_resume_result(a.resume_result, a.tier, a.players, a.menu, cap, a.ranges, a.avg_rule,
                                              a.key_variant, a.stacks, a.player_mix, train_env)
    res = run(a.tier, a.players, a.workers, a.minutes, a.seed, a.batch, resume, resumed_from_run=from_run,
              menu=a.menu, raise_cap=cap, ranges=a.ranges, avg_rule=a.avg_rule, key_variant=a.key_variant,
              stacks=a.stacks, player_mix=a.player_mix, max_iters=a.max_iters, env=env, train_env=train_env, lbr_hands=a.lbr_hands,
              prior=a.prior_result)
    res["sha"] = a.sha_file.read_text(encoding="utf-8").strip() if a.sha_file and a.sha_file.exists() else ""
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(res), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
