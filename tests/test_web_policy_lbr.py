"""#653: web policy file -> c1 LBR policy object."""
import json
import os
import subprocess
import sys

import numpy as np

from referee.e3 import lbr as L
from stalker.e3 import game as G
from stalker.e3 import tp_key as K
from stalker.tools import export_web_policy as X
from stalker.tools import web_policy_lbr as W

N, KSTEPS, DEPTH = 2, 5, "full"


def _state():
    s = G.deal(np.random.default_rng(3), N)
    return s, K.initial_ranges(N)


def _keys(s, ranges):
    public = K.public_key(s, s.to_act, DEPTH)
    steps = K.equity_steps(s, s.to_act, ranges, KSTEPS)
    return [K.key(public, int(v)) for v in np.unique(steps[steps >= 0])]


def _write(tmp_path, table):
    doc = {"schema": "stalker.web.policy", "players": N, "k": KSTEPS, "depth": DEPTH, "q": X.Q,
           "policy": {k: X.quantize(v) for k, v in table.items()}}
    p = tmp_path / "t.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    return p


def test_exported_rows_read_back_same_seat_probs(tmp_path):
    s, ranges = _state()
    n_acts = len(G.legal(s))
    row = X.quantize(np.arange(1, n_acts + 1, dtype=float))
    orig = {k: [x / X.Q for x in row] for k in _keys(s, ranges)}   # exactly representable in 1/255
    path = _write(tmp_path, orig)
    from stalker.tools import web_hit_rate as H
    table, doc = H.load_policy(path)
    wrapped = W.WebPolicy(table, doc["k"])
    a = L.seat_probs(orig, s, s.to_act, ranges, KSTEPS, DEPTH)
    b = L.seat_probs(wrapped, s, s.to_act, ranges, KSTEPS, DEPTH)
    assert np.array_equal(a, b)


def test_missing_key_is_uniform_without_backoff():
    s, ranges = _state()
    n_acts = len(G.legal(s))
    out = L.seat_probs(W.WebPolicy({}, KSTEPS), s, s.to_act, ranges, KSTEPS, DEPTH)
    live = out.sum(axis=1) > 0
    assert live.any() and np.allclose(out[live], 1.0 / n_acts)


def test_same_seed_same_bytes_across_hash_seeds(tmp_path):
    path = _write(tmp_path, {})
    outs = []
    for hs in ("0", "2"):
        r = subprocess.run([sys.executable, "-m", "stalker.tools.web_policy_lbr", "--policy", str(path), "--players",
                            str(N), "--hands", "2", "--seed", "5"], capture_output=True, check=True,
                           env={**os.environ, "PYTHONHASHSEED": hs})
        outs.append(r.stdout)
    assert outs[0] == outs[1] and json.loads(outs[0])["hands"] == 2
