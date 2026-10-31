"""RL best response (RL-BR) for E3 (#413, Gate Q3): an attacker trained against a frozen policy.

LBR (`referee.e3.lbr`) looks one action ahead and the preflop probe (`referee.e3.preflop_probe`)
deviates at one decision. This attacker learns a whole-hand deviation from played hands: Monte Carlo
control over a table. One seat is the attacker; every other seat follows the frozen policy, read with
the policy's own keys and public ranges (`seat_probs`). The public ranges move by the policy's own row
for whatever the attacker does, so the table reads the attacker as the policy would.

The attacker's key is the basic public key of its seat plus its own equity step (`ATTACKER_K` steps)
against those ranges: its own cards and the public line only (Gate L). Per key it keeps the mean
return of each action label and of "pol" (following the policy's row there). It plays the best mean
among entries with at least `min_visits` returns, and "pol" when none qualifies, so it starts as the
policy and only deviates where its returns say so. Training explores (epsilon-greedy, seats rotate);
evaluation is greedy on held-out duplicate deals (every deal once per attacker seat, the same action
stream in every rotation), so the in-sample optimism of picking the best noisy mean does not reach the
reported number. Self-play over a deal's rotations sums to zero, so the attacker's mean is its gain.

Seeds: `rlbr_seeds.json` (sha256 pinned below) lists dev seeds and a disjoint audit list. Dev runs may
only use dev seeds; the final-audit attacker uses an audit seed and is never a dev attacker. Each result
records the seed, its role, the code sha256, the git sha (when available), the policy sha256 and the
trained table's sha256.

The result is a found exploitation gain - a lower bound, never a certificate (GATES.md Q3). Local runs
are reference values only (CLAUDE.md).

    python -m referee.e3.rlbr web/app/policy/mid-6.json --seeds 1 2 --train-hands 20000 --eval-deals 1000
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

from referee.e3.lbr import seat_probs
from referee.e3.preflop_probe import load
from referee.stats import bootstrap_ci
from stalker.e2.eq_view import combo_index
from stalker.e3 import game as G
from stalker.e3 import tp_key as K

HERE = Path(__file__).resolve().parent
SEEDS = HERE / "rlbr_seeds.json"
SEEDS_SHA256 = "0a60ddbd36225507e5cdc2682fb11cea88a12524a017a509c0332eb1f9c5c310"
ATTACKER = "rlbr-mc-v1"
ATTACKER_K = 8
POL = "pol"                  # the table entry for "follow the policy's row here"
WORDING = "found exploitation (a lower bound)"


class SeedError(ValueError):
    pass


def seed_registry(path: Path = SEEDS, pinned: str | None = SEEDS_SHA256) -> dict:
    """The dev and audit seed lists, checked against the pinned sha256 and for overlap."""
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if pinned is not None and sha != pinned:
        raise SeedError(f"{path.name}: sha256 {sha[:12]} != pinned {pinned[:12]}; the audit split is fixed. "
                        "Add a new registry file and pin it instead of editing this one")
    reg = json.loads(raw)
    overlap = set(reg["dev"]) & set(reg["audit"])
    if overlap:
        raise SeedError(f"{path.name}: seeds {sorted(overlap)} are both dev and audit; keep the lists disjoint")
    return reg


def check_seed(seed: int, audit: bool, reg: dict | None = None) -> str:
    """The seed's role, or SeedError when a dev run asks for an audit seed (or the reverse)."""
    reg = reg or seed_registry()
    if audit:
        if seed not in reg["audit"]:
            raise SeedError(f"seed {seed} is not an audit seed; the audit attacker uses one of {reg['audit']}")
        return "audit"
    if seed not in reg["dev"]:
        raise SeedError(f"seed {seed} is not a dev seed ({reg['dev']}); audit seeds need --audit, "
                        "and new dev seeds go into a new registry file")
    return "dev"


class Attacker:
    """The table: key -> {entry: [returns, sum]}. Entries are action labels and POL."""

    def __init__(self, min_visits: int = 10) -> None:
        self.q: dict[str, dict[str, list[float]]] = {}
        self.min_visits = min_visits

    def _means(self, keys: tuple[str, ...], acts: list[str]) -> dict[str, float]:
        """Per entry, the mean return at the finest key where it has `min_visits` returns."""
        out: dict[str, float] = {}
        for key in keys:
            for e, (n, total) in self.q.get(key, {}).items():
                if e not in out and n >= self.min_visits and (e == POL or e in acts):
                    out[e] = total / n
        return out

    def best(self, keys: tuple[str, ...], acts: list[str]) -> str:
        """The best measured entry (keys finest first); nothing measured -> the policy. Ties keep the policy."""
        means = self._means(keys, acts)
        return max(means, key=lambda e: (means[e], e == POL)) if means else POL

    def update(self, visits: list[tuple[tuple[str, ...], str]], ret: float) -> None:
        for keys, entry in visits:
            for key in keys:
                v = self.q.setdefault(key, {}).setdefault(entry, [0, 0.0])
                v[0] += 1
                v[1] += ret

    def deviations(self) -> int:
        """Table keys where the greedy attacker leaves the policy (every label seen there taken as legal)."""
        return sum(self.best((k,), list(row)) != POL for k, row in self.q.items())

    def sha256(self) -> str:
        blob = json.dumps(self.q, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(blob).hexdigest()


def attacker_keys(s: G.State, seat: int, ranges) -> tuple[str, str]:
    """(fine, coarse): the basic public key with the attacker's equity step out of ATTACKER_K, then the
    same line with only weak/strong halves, which fills up sooner and stands in until the fine key has data."""
    step = K.my_step(K.equity_steps(s, seat, ranges, ATTACKER_K), s, seat)
    public = K.public_key(s, seat, "basic")
    return K.key(public, step), K.key(public, step * 2 // ATTACKER_K) + "~"


def play_hand(t: dict, att: Attacker, s: G.State, seat: int, rng: np.random.Generator,
              eps: float = 0.0) -> tuple[float, list]:
    """The attacker's net (bb) in one hand from `s` and the (keys, entry) pairs it chose."""
    pol, k, depth = t["policy"], t["k"], t["depth"]
    ranges = K.initial_ranges(s.n)
    visits = []
    while not s.done:
        q, acts = s.to_act, G.legal(s)
        pr = seat_probs(pol, s, q, ranges, k, depth)
        row = pr[combo_index(s.hole[q])]
        if q == seat:
            keys = attacker_keys(s, seat, ranges)
            if eps and rng.random() < eps:
                entry = POL if rng.random() < 1 / (len(acts) + 1) else acts[int(rng.integers(len(acts)))]
            else:
                entry = att.best(keys, acts)
            visits.append((keys, entry))
            i = int(rng.choice(len(acts), p=row / row.sum())) if entry == POL else acts.index(entry)
        else:
            i = int(rng.choice(len(acts), p=row / row.sum()))
        nxt = K.update_range(ranges, q, pr[:, i])
        # an action the policy never takes with any combo empties that range, and every equity against
        # it is undefined; the policy cannot explain it, so its belief about the seat stays where it was
        ranges = nxt if nxt[q].sum() > 0 else ranges
        s = G.apply(s, acts[i])
    return float(G.payoff(s)[seat]) / G.BB, visits


def _deal(t: dict, seed) -> G.State:
    return G.deal(np.random.default_rng(seed), t["players"], t["menu"], t["raise_cap"])


def train(t: dict, hands: int, seed: int, eps: float = 0.2, min_visits: int = 10) -> Attacker:
    """Epsilon-greedy MC control; the attacker's seat rotates hand by hand."""
    att = Attacker(min_visits)
    rng = np.random.default_rng([seed, 1])
    for h in range(hands):
        ret, visits = play_hand(t, att, _deal(t, [seed, 0, h]), h % t["players"], rng, eps)
        att.update(visits, ret)
    return att


def evaluate(t: dict, att: Attacker, deals: int, seed: int) -> dict:
    """Greedy attacker on held-out duplicate deals: bb/hand, 95% CI over deals (rotations cluster)."""
    if deals < 2:
        raise ValueError("deals must be >= 2 (the CI resamples deals)")
    n = t["players"]
    res = np.empty((deals, n))
    for d in range(deals):
        for seat in range(n):
            res[d, seat] = play_hand(t, att, _deal(t, [seed, 2, d]), seat, np.random.default_rng([seed, 3, d]))[0]
    ci = bootstrap_ci(res.ravel(), np.repeat(np.arange(deals), n), rng=np.random.default_rng(seed))
    return {"gain_bb_per_hand": round(ci.mean, 4), "ci95": [round(ci.lo, 4), round(ci.hi, 4)],
            "ci95_low": round(ci.lo, 4), "deals": deals, "hands": deals * n,
            "by_seat_bb": [round(float(x), 4) for x in res.mean(axis=0)]}


def _git_sha() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=HERE, capture_output=True, text=True,
                              check=True).stdout.strip() or None
    except (OSError, subprocess.CalledProcessError):
        return None


def run(t: dict, seed: int, train_hands: int, eval_deals: int, audit: bool = False, eps: float = 0.2,
        min_visits: int = 10, reg: dict | None = None) -> dict:
    """Train one attacker (seed checked against the registry), evaluate it, record its versions."""
    role = check_seed(seed, audit, reg)
    code, git = hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), _git_sha()    # before the long part
    att = train(t, train_hands, seed, eps, min_visits)
    out = {"attacker": ATTACKER, "role": role, "seed": seed, "code_sha256": code, "git_sha": git,
           "policy_sha256": t.get("sha256"), "train_hands": train_hands, "eps": eps, "min_visits": min_visits,
           "attacker_k": ATTACKER_K, "keys": len(att.q), "deviating_keys": att.deviations(),
           "table_sha256": att.sha256(), "wording": WORDING}
    out.update(evaluate(t, att, eval_deals, seed))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="E3 RL best response against a frozen web policy (Gate Q3, lower bound)")
    ap.add_argument("policy", type=Path, help="web policy file (stalker.web.policy)")
    ap.add_argument("--seeds", type=int, nargs="+", required=True)
    ap.add_argument("--audit", action="store_true", help="final audit: seeds must come from the audit list")
    ap.add_argument("--train-hands", type=int, default=20000)
    ap.add_argument("--eval-deals", type=int, default=1000)
    ap.add_argument("--eps", type=float, default=0.2)
    ap.add_argument("--min-visits", type=int, default=10)
    a = ap.parse_args(argv)
    t = load(a.policy)
    t["sha256"] = hashlib.sha256(a.policy.read_bytes()).hexdigest()
    try:
        reg = seed_registry()
        for sd in a.seeds:
            check_seed(sd, a.audit, reg)
    except SeedError as e:
        print(f"rlbr: {e}", file=sys.stderr)
        return 2
    res = [run(t, sd, a.train_hands, a.eval_deals, a.audit, a.eps, a.min_visits, reg) for sd in a.seeds]
    print(json.dumps({"policy": str(a.policy), "runs": res}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
