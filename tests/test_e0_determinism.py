"""E0 CFR+ must not depend on the runner's CPU (#481): Leduc's exploitability flipped between two
values across CI runners because a node's value `sigma @ vals` went to BLAS (the #447 pattern).
It must not depend on the Python version either (#488): 3.12 made built-in `sum()` of floats
compensated, so CI (3.12) and local 3.11 runs disagreed until every sum went through `math.fsum`."""
import json
import math
import os
import subprocess
import sys

import pytest

from stalker.tools import e3_determinism as D

PROBE = """
import hashlib, json, math, os
import numpy as np
from referee.anchors.toy import leduc
from stalker.toy.cfr import CFRPlus
s = CFRPlus(leduc.game())
if os.environ.get("E0_STRIDED"):
    # Non-contiguous views take numpy's strided loops instead of the contiguous SIMD ones.
    for d in (s.regret, s.avg):
        for k, a in d.items():
            d[k] = np.zeros(2 * len(a))[::2]
s.iterate(300)
h = hashlib.sha256()
for k, v in sorted(s.average_strategy().items()):
    h.update(k.encode()); h.update(np.asarray(v, dtype="<f8").tobytes())
print(json.dumps({"avg_sha256": h.hexdigest()}))
"""


def _probe(env: dict[str, str]) -> str:
    out = subprocess.run([sys.executable, "-c", PROBE], env={**os.environ, **env}, capture_output=True,
                         encoding="utf-8", timeout=300, check=True)
    return json.loads(out.stdout.strip().splitlines()[-1])["avg_sha256"]


@pytest.mark.slow
def test_leduc_cfr_plus_average_strategy_is_identical_under_emulated_runners():
    # Each setting is a fresh process with another OpenBLAS kernel/thread count or numpy SIMD level.
    settings = {**D.settings(numba_off=False), "strided-views": {"E0_STRIDED": "1"}}
    results = {name: _probe(env) for name, env in settings.items()}
    assert len(set(results.values())) == 1, f"average strategy differs by runner setting: {results}"


def _reference_cfr_plus(root, iterations: int) -> dict[str, list[float]]:
    """CFR+ in lists and `math.fsum` only, mirroring `stalker.toy.cfr.CFRPlus` operation by operation."""
    from referee.anchors.toy.game import CHANCE, TERMINAL, infosets

    info = infosets(root)
    regret = {k: [0.0] * len(a) for k, (_, a) in info.items()}
    avg = {k: [0.0] * len(a) for k, (_, a) in info.items()}

    def current(r):
        s = math.fsum(r)
        return [x / s for x in r] if s > 0 else [1.0 / len(r)] * len(r)

    for t in range(1, iterations + 1):
        for player in (0, 1):
            sigma = {k: current(r) for k, r in regret.items()}
            delta = {k: [0.0] * len(a) for k, (_, a) in info.items()}

            def walk(n, rs, ro):
                if n.kind == TERMINAL:
                    return n.utility if player == 0 else -n.utility
                if n.kind == CHANCE:
                    return math.fsum(p * walk(c, rs, ro * p) for p, c in zip(n.probs, n.children))
                sg = sigma[n.infoset]
                if n.player == player:
                    vals = [walk(c, rs * sg[i], ro) for i, c in enumerate(n.children)]
                    v = math.fsum(a * b for a, b in zip(sg, vals))
                    d = delta[n.infoset]
                    for i, x in enumerate(vals):
                        d[i] += ro * (x - v)
                    w = t * rs
                    av = avg[n.infoset]
                    for i, x in enumerate(sg):
                        av[i] += w * x
                    return v
                return math.fsum(sg[i] * walk(c, rs, ro * sg[i]) for i, c in enumerate(n.children))

            walk(root, 1.0, 1.0)
            for k, d in delta.items():
                if info[k][0] == player:
                    regret[k] = [max(r + x, 0.0) for r, x in zip(regret[k], d)]
    out = {}
    for k, s in avg.items():
        tot = math.fsum(s)
        out[k] = [x / tot for x in s] if tot > 0 else [1.0 / len(s)] * len(s)
    return out


@pytest.mark.slow
def test_leduc_cfr_plus_matches_a_pure_python_fsum_reference_bit_for_bit():
    from referee.anchors.toy import exploitability, leduc
    from stalker.toy.cfr import CFRPlus

    game = leduc.game()
    solver = CFRPlus(game)
    solver.iterate(300)
    got = solver.average_strategy()
    want = _reference_cfr_plus(game, 300)
    assert got == want, "CFRPlus drifted from the fsum reference: keep every float sum in math.fsum (#488)"
    assert float(exploitability(game, got)).hex() == float(exploitability(game, want)).hex()


def _reference_exploitability(root, strategy) -> float:
    """Exact best response in lists and `math.fsum` only, mirroring `referee.anchors.toy.game` (#497)."""
    from referee.anchors.toy.game import CHANCE, PLAYER, TERMINAL

    def probs(n):
        if n.kind == CHANCE:
            return list(n.probs)
        p = strategy.get(n.infoset)
        return [1.0 / len(n.actions)] * len(n.actions) if p is None else [float(x) for x in p]

    def br(br_player):
        sign = 1.0 if br_player == 0 else -1.0
        weight, members, stack = {}, {}, [(root, 1.0)]
        while stack:
            n, w = stack.pop()
            weight[id(n)] = w
            if n.kind == TERMINAL:
                continue
            if n.kind == PLAYER and n.player == br_player:
                members.setdefault(n.infoset, []).append(n)
                stack.extend((c, w) for c in n.children)
            else:
                stack.extend((c, w * p) for c, p in zip(n.children, probs(n)))
        choice, memo = {}, {}

        def v(n):
            if id(n) in memo:
                return memo[id(n)]
            if n.kind == TERMINAL:
                r = sign * n.utility
            elif n.kind == PLAYER and n.player == br_player:
                r = v(n.children[choice[n.infoset]])
            else:
                r = math.fsum(p * v(c) for p, c in zip(probs(n), n.children) if p > 0)
            memo[id(n)] = r
            return r

        for info in sorted(members, key=lambda i: -members[i][0].depth):
            nodes = members[info]
            scores = [math.fsum(weight[id(h)] * v(h.children[a]) for h in nodes) for a in range(len(nodes[0].actions))]
            choice[info] = scores.index(max(scores))
        return v(root)

    return (br(0) + br(1)) / 2


@pytest.mark.slow
@pytest.mark.parametrize("name", ["kuhn", "leduc"])
def test_exploitability_matches_a_pure_python_fsum_reference_bit_for_bit(name):
    from referee.anchors.toy import exploitability, kuhn, leduc
    from stalker.toy.cfr import CFRPlus

    game = {"kuhn": kuhn, "leduc": leduc}[name].game()
    solver = CFRPlus(game)
    solver.iterate(300)
    for label, strat in {"uniform": {}, "cfr+300": solver.average_strategy()}.items():
        got = float(exploitability(game, strat)).hex()
        want = _reference_exploitability(game, strat).hex()
        assert got == want, f"{name}/{label}: referee exploitability drifted from the fsum reference (#497)"


def _reference_cfr_br(root, key, iterations: int) -> dict[str, list[float]]:
    """CFR-BR in lists and `math.fsum` only, mirroring `stalker.toy.cfr_br.solve` operation by operation (#498)."""
    from referee.anchors.toy.game import CHANCE, PLAYER, TERMINAL, infosets

    info = infosets(root)

    def best_response(strategy, br_player):
        sign = 1.0 if br_player == 0 else -1.0

        def probs(n):
            if n.kind == CHANCE:
                return list(n.probs)
            p = strategy.get(n.infoset)
            return [1.0 / len(n.actions)] * len(n.actions) if p is None else [float(x) for x in p]

        weight, members, stack = {}, {}, [(root, 1.0)]
        while stack:
            n, w = stack.pop()
            weight[id(n)] = w
            if n.kind == TERMINAL:
                continue
            if n.kind == PLAYER and n.player == br_player:
                members.setdefault(n.infoset, []).append(n)
                stack.extend((c, w) for c in n.children)
            else:
                stack.extend((c, w * p) for c, p in zip(n.children, probs(n)))
        choice, memo = {}, {}

        def v(n):
            if id(n) in memo:
                return memo[id(n)]
            if n.kind == TERMINAL:
                r = sign * n.utility
            elif n.kind == PLAYER and n.player == br_player:
                r = v(n.children[choice[n.infoset]])
            else:
                r = math.fsum(p * v(c) for p, c in zip(probs(n), n.children) if p > 0)
            memo[id(n)] = r
            return r

        for i in sorted(members, key=lambda i: -members[i][0].depth):
            nodes = members[i]
            scores = [math.fsum(weight[id(h)] * v(h.children[a]) for h in nodes) for a in range(len(nodes[0].actions))]
            choice[i] = scores.index(max(scores))
        return choice

    out: dict[str, list[float]] = {}
    for player in (0, 1):
        own = [i for i, (p, _) in info.items() if p == player]
        sizes = {key(i): len(info[i][1]) for i in own}
        regret = {k: [0.0] * n for k, n in sizes.items()}
        avg = {k: [0.0] * n for k, n in sizes.items()}
        for t in range(1, iterations + 1):
            sigma = {}
            for k, r in regret.items():
                s = math.fsum(r)
                sigma[k] = [x / s for x in r] if s > 0 else [1.0 / len(r)] * len(r)
            br = best_response({i: list(sigma[key(i)]) for i in own}, 1 - player)
            delta = {k: [0.0] * len(s) for k, s in sigma.items()}

            def walk(n, rs, ro):
                if n.kind == TERMINAL:
                    return n.utility if player == 0 else -n.utility
                if n.kind == CHANCE:
                    return math.fsum(q * walk(c, rs, ro * q) for q, c in zip(n.probs, n.children))
                if n.player != player:
                    return walk(n.children[br[n.infoset]], rs, ro)
                k = key(n.infoset)
                sg = sigma[k]
                vals = [walk(c, rs * sg[i], ro) for i, c in enumerate(n.children)]
                v = math.fsum(a * b for a, b in zip(sg, vals))
                d = delta[k]
                for i, x in enumerate(vals):
                    d[i] += ro * (x - v)
                w = t * rs
                av = avg[k]
                for i, x in enumerate(sg):
                    av[i] += w * x
                return v

            walk(root, 1.0, 1.0)
            for k, d in delta.items():
                regret[k] = [max(r + x, 0.0) for r, x in zip(regret[k], d)]
        for i in own:
            s = avg[key(i)]
            tot = math.fsum(s)
            out[i] = [x / tot for x in s] if tot > 0 else [1.0 / len(s)] * len(s)
    return out


@pytest.mark.slow
@pytest.mark.parametrize("name,level,iterations", [("kuhn", (2,), 300), ("kuhn", (3,), 300), ("leduc", (2, 1), 30)])
def test_cfr_br_matches_a_pure_python_fsum_reference_bit_for_bit(name, level, iterations):
    from referee.anchors.toy import kuhn, leduc
    from stalker.toy import bottleneck as bn
    from stalker.toy import cfr_br

    game = {"kuhn": kuhn, "leduc": leduc}[name].game()
    key = (bn.kuhn_key if name == "kuhn" else bn.leduc_key)(*level)
    got = cfr_br.solve(game, key, iterations)
    want = _reference_cfr_br(game, key, iterations)
    assert got == want, f"{name}{level}: CFR-BR drifted from the fsum reference: keep every float sum in math.fsum (#498)"
