"""E0 CFR+ must not depend on the runner's CPU (#481): Leduc's exploitability flipped between two
values across CI runners because a node's value `sigma @ vals` went to BLAS (the #447 pattern)."""
import json
import os
import subprocess
import sys

import pytest

from stalker.tools import e3_determinism as D

PROBE = """
import hashlib, json, math
import numpy as np
from referee.anchors.toy import leduc
from stalker.toy.cfr import CFRPlus
s = CFRPlus(leduc.game())
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
    results = {name: _probe(env) for name, env in D.settings(numba_off=False).items()}
    assert len(set(results.values())) == 1, f"average strategy differs by runner setting: {results}"
