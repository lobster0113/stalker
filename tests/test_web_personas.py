"""Training Game personas (#429): the node calibration test of web/app/personas.js passes.

CI runs it twice: in the `web` job directly and here through the gates (#436)."""
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_persona_calibration(node):
    r = subprocess.run([node, "--test", str(ROOT / "web" / "app" / "test" / "personas.test.mjs")],
                       capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert r.returncode == 0, r.stdout[-4000:] + r.stderr[-2000:]
