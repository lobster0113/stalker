"""Hero tell report (#430): the node tests of web/app/tells.js pass, and the demo wires the log and panel."""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DEMO = (ROOT / "web" / "demo" / "index.html").read_text(encoding="utf-8")


def test_node_tells_pass():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not installed; run `node --test web/app/test/tells.test.mjs` where it is")
    r = subprocess.run([node, "--test", str(ROOT / "web" / "app" / "test" / "tells.test.mjs")],
                       capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert r.returncode == 0, r.stdout[-4000:] + r.stderr[-2000:]


def test_demo_wires_the_tell_log_and_panel():
    # The hooks are read-only and must stay where they are: hero decisions are logged in applyAction,
    # showdowns in showdown(), and the panel lives in the learning section.
    for needle, fix in [
        ("tellHook(s, a, L);", "call tellHook(s, a, L) at the top of applyAction"),
        ("tellPend(keys);", "call tellPend(keys) in finishHero before resolving the action"),
        ("tellShowdown(contenders);", "call tellShowdown(contenders) in showdown()"),
        ('id="tell-box"', "keep the 텔 리포트 box in the learning section"),
        ('import(APP_BASE + "tells.js")', "load app/tells.js from APP_BASE"),
    ]:
        assert needle in DEMO, f"web/demo/index.html: {fix} (#430)"
