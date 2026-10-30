"""Training Game personas (#429): the node calibration test of web/app/personas.js passes.

CI's `web` job runs only tpgto.test.mjs, so the gates run this one where node is installed."""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_persona_calibration():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not installed; run `node --test web/app/test/personas.test.mjs` where it is")
    r = subprocess.run([node, "--test", str(ROOT / "web" / "app" / "test" / "personas.test.mjs")],
                       capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert r.returncode == 0, r.stdout[-4000:] + r.stderr[-2000:]
