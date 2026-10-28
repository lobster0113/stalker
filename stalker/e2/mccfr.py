"""External-sampling MCCFR for E2 (unconstrained baseline, ADR 0012).

Self-play: each iteration deals one hand, and for each player in turn walks the tree sampling the
opponent's actions from the current strategy while exploring all of the traverser's actions
(Lanctot et al. 2009). Infoset = (player, street, card bucket, public history). Regret matching+
with linear averaging. Deterministic for a seed; a checkpoint (regrets, averages, iteration count
and RNG state) resumes exactly, so N iterations + save + load + M iterations equals N+M in one go.

    python -m stalker.e2.mccfr --iters 2000 --seed 1 --out runs/e2.json --log runs/e2.jsonl --every 100
    python -m stalker.e2.mccfr --resume runs/e2.ckpt.json --iters 2000 --checkpoint runs/e2.ckpt.json
"""
from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

from stalker.e2 import game as G
from stalker.e2.abstraction import BASELINE, TIERS, Abstraction


def infoset(s: G.State, abstraction: Abstraction = BASELINE) -> str:
    p = s.to_act
    return f"{p}|{s.street}|{abstraction.bucket(s.hole[p], s.board)}|{''.join(h if len(h) == 1 else h[1:] for h in s.history)}"


class MCCFR:
    def __init__(self, seed: int = 0, abstraction: Abstraction = BASELINE):
        self.seed = seed
        self.abstraction = abstraction
        self.rng = np.random.default_rng(seed)
        self.regret: dict[str, np.ndarray] = {}
        self.avg: dict[str, np.ndarray] = defaultdict(lambda: None)
        self.iterations = 0

    def _sigma(self, key: str, n: int) -> np.ndarray:
        r = self.regret.get(key)
        if r is None:
            return np.full(n, 1.0 / n)
        pos = np.maximum(r, 0)
        s = pos.sum()
        return pos / s if s > 0 else np.full(n, 1.0 / n)

    def _walk(self, s: G.State, trav: int) -> float:
        if s.done:
            v = G.payoff(s) / G.BB
            return v if trav == 0 else -v
        acts = G.legal(s)
        key = infoset(s, self.abstraction)
        sigma = self._sigma(key, len(acts))
        if s.to_act == trav:
            vals = np.array([self._walk(G.apply(s, a), trav) for a in acts])
            v = float(sigma @ vals)
            r = self.regret.setdefault(key, np.zeros(len(acts)))
            np.maximum(r + (vals - v), 0, out=r)
            return v
        a = self.rng.choice(len(acts), p=sigma)
        avg = self.avg[key]
        self.avg[key] = (avg if avg is not None else 0) + self.iterations * sigma
        return self._walk(G.apply(s, acts[a]), trav)

    def iterate(self, n: int = 1, log=None, every: int = 1) -> None:
        """Run n iterations; with `log` (a text file), write a JSONL row every `every` iterations."""
        t0 = time.monotonic()
        for i in range(n):
            if log is not None and i and i % every == 0:
                self._log_row(log, t0)
            self.iterations += 1
            s = G.deal(self.rng)
            for trav in (0, 1):
                self._walk(s, trav)
        if log is not None:
            self._log_row(log, t0)

    def _log_row(self, log, t0: float) -> None:
        log.write(json.dumps({"iteration": self.iterations, "seed": self.seed, "infosets": len(self.regret),
                              "seconds": round(time.monotonic() - t0, 3)}) + "\n")
        log.flush()

    def save(self, path: Path) -> None:
        """Checkpoint: everything needed to continue exactly where this run stopped."""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps({
            "seed": self.seed, "iterations": self.iterations, "rng": self.rng.bit_generator.state,
            "abstraction": self.abstraction.to_json(),
            "regret": {k: v.tolist() for k, v in self.regret.items()},
            "avg": {k: v.tolist() for k, v in self.avg.items() if v is not None}}), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "MCCFR":
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        m = cls(d["seed"], Abstraction.from_json(d.get("abstraction")))
        m.iterations = d["iterations"]
        m.rng.bit_generator.state = d["rng"]
        m.regret = {k: np.array(v) for k, v in d["regret"].items()}
        for k, v in d["avg"].items():
            m.avg[k] = np.array(v)
        return m

    def policy(self) -> dict[str, list[float]]:
        out = {}
        for k, v in self.avg.items():
            if v is not None and v.sum() > 0:
                out[k] = (v / v.sum()).tolist()
        return out


def main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="E2 external-sampling MCCFR (local reference numbers)")
    ap.add_argument("--iters", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--tier", choices=sorted(TIERS), default="baseline", help="TP card resolution (#187)")
    ap.add_argument("--out", type=Path, help="average policy JSON")
    ap.add_argument("--log", type=Path, help="JSONL progress rows (iteration, seed, infosets, seconds)")
    ap.add_argument("--every", type=int, default=100, help="log every K iterations")
    ap.add_argument("--checkpoint", type=Path, help="write a resumable checkpoint at the end")
    ap.add_argument("--resume", type=Path, help="continue from a checkpoint (its seed and tier win)")
    a = ap.parse_args(argv)
    t0 = time.monotonic()
    m = MCCFR.load(a.resume) if a.resume else MCCFR(a.seed, TIERS[a.tier])
    if a.log:
        a.log.parent.mkdir(parents=True, exist_ok=True)
        with a.log.open("a", encoding="utf-8") as log:
            m.iterate(a.iters, log, a.every)
    else:
        m.iterate(a.iters)
    dt = time.monotonic() - t0
    pol = m.policy()
    print(json.dumps({"iters": m.iterations, "seed": m.seed, "abstraction": m.abstraction.name, "seconds": round(dt, 2),
                      "iters_per_s": round(a.iters / dt, 1), "infosets": len(m.regret)}))
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps({"seed": m.seed, "iters": m.iterations, "abstraction": m.abstraction.to_json(),
                                     "policy": pol}), encoding="utf-8")
    if a.checkpoint:
        m.save(a.checkpoint)
    return 0


if __name__ == "__main__":
    sys.exit(main())
