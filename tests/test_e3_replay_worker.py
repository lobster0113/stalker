"""#721 (#418): a checkpoint loaded in another process gives the same outputs, bit for bit.

The worker is a fresh interpreter (`python -c`), so nothing is shared but the checkpoint file: it must
rebuild the fixed spots' average-strategy rows and, after N more iterations, the regret table that the
saving process computes itself. Without numba the train path is the numpy one in both processes; the
numba-off child is checked only when numba is installed (otherwise it is the same run twice).
"""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from stalker.e3.mccfr import E3MCCFR

ROOT = Path(__file__).resolve().parents[1]
SEED, PLAYERS, TRAIN, MORE, SPOTS = 721, 3, 40, 20, 24

# The child prints the fixed spots' row hash, then the regret hash after MORE iterations.
CHILD = """
import hashlib, json, sys
import numpy as np
from stalker.e3.mccfr import E3MCCFR
st = json.load(open(sys.argv[1], encoding="utf-8"))
spots = json.load(open(sys.argv[2], encoding="utf-8"))
m = E3MCCFR.from_state(st)
pol = m.policy()
h = hashlib.sha256()
for k in spots:
    h.update(k.encode("utf-8") + b"\\0" + np.asarray(pol[k], dtype="<f8").tobytes())
print(h.hexdigest())
m.iterate(int(sys.argv[3]))
print(m.regret_hash())
"""


def _spot_hash(m, spots):
    pol = m.policy()
    h = hashlib.sha256()
    for k in spots:
        h.update(k.encode("utf-8") + b"\0" + np.asarray(pol[k], dtype="<f8").tobytes())
    return h.hexdigest()


def _child(ckpt, spots_file, env_extra):
    env = {**os.environ, **env_extra, "PYTHONPATH": str(ROOT) + os.pathsep + os.environ.get("PYTHONPATH", "")}
    r = subprocess.run([sys.executable, "-c", CHILD, str(ckpt), str(spots_file), str(MORE)],
                       capture_output=True, text=True, encoding="utf-8", env=env, cwd=ROOT, timeout=120)
    assert r.returncode == 0, f"replay worker failed:\n{r.stderr[-2000:]}"
    return r.stdout.split()


def _settings():
    out = {"default": {}}
    try:
        import numba  # noqa: F401
        out["numba-off"] = {"NUMBA_DISABLE_JIT": "1"}
    except ImportError:
        pass
    return out


@pytest.mark.parametrize("name", list(_settings()))
def test_checkpoint_replays_bit_identical_in_another_process(tmp_path, name):
    m = E3MCCFR(SEED, 5, PLAYERS, "basic")
    m.iterate(TRAIN)
    ckpt = tmp_path / "ckpt.json"
    ckpt.write_text(json.dumps(m.state()), encoding="utf-8")
    keys = sorted(m.policy())
    assert len(keys) >= SPOTS, f"only {len(keys)} infosets after {TRAIN} iterations; raise TRAIN"
    # The fixed spot set: infosets of the seeded deals, picked by a fixed seed (sorted, so order is stable).
    spots = sorted(np.random.default_rng(SEED).choice(keys, SPOTS, replace=False).tolist())
    spots_file = tmp_path / "spots.json"
    spots_file.write_text(json.dumps(spots), encoding="utf-8")

    rows, regrets = _child(ckpt, spots_file, _settings()[name])

    here = E3MCCFR.from_state(json.loads(ckpt.read_text(encoding="utf-8")))
    assert rows == _spot_hash(here, spots) == _spot_hash(m, spots)
    m.iterate(MORE)
    assert regrets == m.regret_hash()
