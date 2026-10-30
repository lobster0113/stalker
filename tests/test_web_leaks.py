"""Known-leak warnings (#441): the export tool keeps every probe cell and the leak details, and the page's
own leakVerdict/leakHTML pass the node test against synthetic cells and the shipped leaks files."""
import json
import subprocess
from pathlib import Path

import pytest

from stalker.tools import policy_leaks as PL

ROOT = Path(__file__).resolve().parent.parent


def _probe_cell(spot, seat, group, leak, best="r", gain=3.0):
    acts = {"c": {"row": 0.6, "vs_row_bb": -1.0, "vs_row_se": 0.4, "vs_row_ci": [-1.8, -0.2]},
            best: {"row": 0.4, "vs_row_bb": gain, "vs_row_se": 0.5, "vs_row_ci": [gain - 1, gain + 1]}}
    return {"spot": spot, "seat": seat, "group": group, "deals": 300, "reach": 0.5, "actions": acts,
            "open_minus_limp": {"r": {"bb": 4.0, "ci": [2.0, 6.0]}}, "best": best, "leak": leak, "leak_low_bb": 1.2}


PROBE = {"probe": "e3_preflop_v1", "deals_per_cell": 300, "seed": 0, "threshold_bb": 0.5, "alpha": 0.05,
         "z_corrected": 3.69, "players": 6, "menu": "v1", "k": 11, "depth": "full",
         "cells": [_probe_cell("first_in", "HJ", "AA", True), _probe_cell("first_in", "HJ", "KK", False),
                   {"spot": "vs_open", "seat": "BB", "group": "QQ", "deals": 0, "reach": 0.0, "actions": {},
                    "best": None, "leak": False}]}


def test_build_keeps_cells_and_leak_details():
    out = PL.build(PROBE, "mid", "mid-6.json", {"run_id": "1", "sha": "abc"}, "local; CI test covers mid HJ/CO AA")
    assert out["schema"] == PL.SCHEMA and out["tier"] == "mid" and out["policy_run_id"] == "1"
    assert out["evidence"].startswith("local")
    assert [(c["seat"], c["group"], c["measured"], c["leak"]) for c in out["cells"]] == \
        [(1, "AA", True, True), (1, "KK", True, False), (5, "QQ", False, False)]
    (lk,) = out["leaks"]
    assert lk["pos"] == "HJ" and lk["best"] == "r" and lk["gain_bb"] == 3.0 and lk["open_minus_limp"]["r"]["bb"] == 4.0
    assert out["settings"]["deals_per_cell"] == 300 and out["settings"]["groups"] == ["AA", "KK", "QQ"]


def test_confirmation_rechecks_only_promising_cells_and_wins_when_it_flags():
    weak = _probe_cell("first_in", "CO", "KK", False, gain=0.3)
    promising = _probe_cell("vs_open", "BTN", "AA", False, best="a", gain=2.0)
    screen = dict(PROBE, cells=PROBE["cells"] + [weak, promising])
    assert [(c["seat"], c["group"]) for c in PL.candidates(screen)] == [("HJ", "KK"), ("BTN", "AA")]
    again = dict(_probe_cell("vs_open", "BTN", "AA", True, best="a", gain=2.5), deals=1000)
    conf = {"probe": "e3_preflop_v1", "deals_per_cell": 1000, "seed": 7, "z_corrected": 2.8, "cells": [again]}
    out = PL.build(screen, "mid", "mid-6.json", confirmed=conf)
    by = {(lk["pos"], lk["group"]): lk for lk in out["leaks"]}
    assert by[("HJ", "AA")]["stage"] == "screen" and by[("BTN", "AA")]["stage"] == "confirm"
    assert by[("BTN", "AA")]["deals"] == 1000 and by[("BTN", "AA")]["gain_bb"] == 2.5
    assert out["settings"]["confirm"]["cells"] == 1


def test_build_refuses_other_files():
    with pytest.raises(ValueError, match="preflop_probe"):
        PL.build({"probe": "lbr"}, "mid", "mid-6.json")
    with pytest.raises(ValueError, match="6-max"):
        PL.build(dict(PROBE, players=9), "mid", "mid-6.json")


def test_cli_writes_the_file(tmp_path):
    p = tmp_path / "probe.json"
    p.write_text(json.dumps(PROBE), encoding="utf-8")
    out = tmp_path / "mid-6.leaks.json"
    assert PL.main(["--probe", str(p), "--tier", "mid", "--policy", str(tmp_path / "none.json"), "--out", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["leaks"][0]["group"] == "AA"


def test_node_leak_warnings_pass(node):
    r = subprocess.run([node, "--test", str(ROOT / "web" / "app" / "test" / "leaks.test.mjs")],
                       capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert r.returncode == 0, r.stdout[-4000:] + r.stderr[-2000:]
