"""Gate T: the action goes through the TP bottleneck (referee/GATES.md Gate T). `python -m referee.gate_t`.

T1 (bottleneck compliance): with the TP vector and DecisionContext held fixed, randomizing every
other part of the observation must leave the action distribution exactly unchanged. Agents under
test expose `action_distribution(po, tp=None)` and `tp(po)` (see `stalker.tp.bottleneck`).
"""
from __future__ import annotations

import dataclasses
import sys
from collections.abc import Callable

import numpy as np

from stalker.env.contract import PublicObservation, decision_context
from stalker.observe.builder import ObservationBuilder
from stalker.tournament.config import load_preset
from stalker.tp.bottleneck import default_agent
from stalker.tp.spec import load

T1_PERTURBATIONS = 100
T1_DECISIONS = 8


def _perturb(po: PublicObservation, rng: np.random.Generator) -> PublicObservation:
    """Change what the DecisionContext does not carry: opponent identities and stats, memory, ids."""
    seats = []
    for k, s in enumerate(po.seats):
        if s.used and k != 0:
            n = int(rng.integers(1, 200))
            stats = {"pre": {"opportunities": n, "f": int(rng.integers(0, n)), "c": 0, "r": 0},
                     "vpip_hands": int(rng.integers(0, n)), "pfr_hands": int(rng.integers(0, n)),
                     "showdowns": int(rng.integers(0, 10))}
            s = dataclasses.replace(s, player_id=int(rng.integers(0, 10_000)), hands_seen=n, stats=stats)
        seats.append(s)
    recent = tuple((int(rng.integers(0, 50)), int(rng.integers(0, 9)), int(rng.integers(0, 4)), "cbr",
                    int(rng.integers(0, 500))) for _ in range(int(rng.integers(0, 12))))
    return dataclasses.replace(po, seats=tuple(seats), recent_actions=recent, game_id=f"g{rng.integers(1e9)}",
                               hand_id=int(rng.integers(1, 10_000)), showdowns=())


def _observations(preset: str = "6max_sng_wta", n: int = T1_DECISIONS) -> list[PublicObservation]:
    from referee.gate_l import record_game

    cfg = load_preset(preset)
    builder = ObservationBuilder(cfg)
    obs = [o for o, _ in record_game(cfg, 91, "t1").decisions]
    pre = [o for o in obs if not o.board][: n // 2]
    post = [o for o in obs if o.board][: n - len(pre)]
    return [builder.build(o) for o in pre + post]


def check_t1(agent, perturbations: int = T1_PERTURBATIONS, seed: int = 0) -> tuple[int, int, list[str]]:
    """Returns (passed, total, failures). One check per base observation."""
    rng = np.random.default_rng(seed)
    passed, failures = 0, []
    pos = _observations()
    for po in pos:
        tp, dc = agent.tp(po), decision_context(po)
        base = agent.action_distribution(po, tp)
        bad = 0
        for _ in range(perturbations):
            v = _perturb(po, rng)
            if decision_context(v) != dc:
                raise AssertionError("T1 perturbation changed the DecisionContext; fix _perturb")
            if agent.action_distribution(v, tp) != base:
                bad += 1
        if bad == 0:
            passed += 1
        else:
            failures.append(f"T1: hand {po.hand_id}: {bad}/{perturbations} perturbations outside TP+DecisionContext "
                            "changed the action distribution. The action head may read only the TP vector and the "
                            "DecisionContext (stalker/tp/bottleneck.py).")
    return passed, len(pos), failures


# Agents under test. Register a TP policy here (referee-change) so every CI run checks the bottleneck.
REGISTRY: dict[str, Callable[[], object]] = {"linear_bottleneck_v0": default_agent}


def main() -> int:
    spec = load()
    print(f"tp_spec {spec.version} sha256 {spec.sha256}")
    ok = True
    for name, make in REGISTRY.items():
        p, t, fails = check_t1(make())
        print(f"T1 [{name}] {p}/{t}")
        for f in fails:
            print("  " + f)
        ok &= p == t
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
