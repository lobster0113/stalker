import json
import re
import time
from collections import Counter

import pytest

from referee.anchors import icm_reference as ir
from referee.gate_a import SPOT_SET_VERSION, SPOTS_V1, SpotSetError, load_spots, spot_set_hash

# Retired metric (ADR 0008): kept for the record, run only in the full gate (#104).
pytestmark = pytest.mark.slow


def _write(tmp_path, spots):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"spots": spots}), encoding="utf-8")
    return p


def _first():
    return json.loads(SPOTS_V1.read_text(encoding="utf-8"))["spots"][0]


def test_v1_set_covers_all_axes():
    spots = load_spots()
    assert len(spots) == 16
    axes = Counter((m["players"], m["bubble"], m["kind"]) for _, _, m in spots)
    assert len(axes) == 8 and set(axes.values()) == {2}
    assert all(s.n == m["players"] for _, s, m in spots)


def test_hash_is_stable_and_versioned():
    v, h = spot_set_hash()
    assert v == SPOT_SET_VERSION and len(h) == 64
    assert spot_set_hash() == (v, h)


@pytest.mark.parametrize("mutate,msg", [
    (lambda s: s.pop("hero"), "missing"),
    (lambda s: s.update(hero=5), "hero"),          # BB cannot push first-in
    (lambda s: s.update(kind="call", hero=0), "hero"),
    (lambda s: s.update(kind="raise"), "kind"),
    (lambda s: s.update(players=7), "players"),
    (lambda s: s.update(stacks=[10, 20]), "spot"),  # post-blind stack too small is rejected by Spot
    (lambda s: s.update(ante=5, bb_ante=5), "spot"),
    (lambda s: s.update(players=9), "stacks"),      # players must equal len(stacks)
    (lambda s: s.update(pusher=1), "pusher"),       # push spots have no pusher
])
def test_invalid_spot_rejected(tmp_path, mutate, msg):
    s = _first()
    mutate(s)
    with pytest.raises(SpotSetError, match=msg):
        load_spots(_write(tmp_path, [s]))


def test_duplicate_id_rejected(tmp_path):
    s = _first()
    with pytest.raises(SpotSetError, match="duplicate"):
        load_spots(_write(tmp_path, [s, dict(s)]))


def test_all_spots_solve_within_budget():
    t0 = time.time()
    for sid, spot, _ in load_spots():
        assert ir.solve(spot).converged, sid
    assert time.time() - t0 < 60


def _eff_bb(spot, m):
    """Effective stack in bb: push = min(hero, largest stack behind); call = min(hero, pusher)."""
    h, st = m["hero"], spot.stacks
    other = max(st[h + 1:]) if m["kind"] == "push" else st[m["pusher"]]
    return min(st[h], other) / spot.bb


def test_v1_effective_stacks_in_range():
    for sid, spot, m in load_spots():
        assert 7 <= _eff_bb(spot, m) <= 20, f"{sid}: effective stack outside 7..20bb"


def test_v1_ids_match_data():
    pos = {6: ["utg", "hj", "co", "btn", "sb", "bb"], 9: ["utg", "utg1", "utg2", "lj", "hj", "co", "btn", "sb", "bb"]}
    for sid, spot, m in load_spots():
        bb = int(re.search(r"-(\d+)bb", sid).group(1))
        names = pos[m["players"]]
        assert f"-{names[m['hero']]}-" in sid or sid.split("-")[2] == names[m["hero"]], sid
        if m["kind"] == "push":
            assert spot.stacks[m["hero"]] == bb * spot.bb, sid
        else:
            assert sid.split("-vs-")[1].startswith(names[m["pusher"]] + "-"), sid
            assert spot.stacks[m["pusher"]] == bb * spot.bb, sid


def test_call_spot_requires_valid_pusher(tmp_path):
    s = next(r for r in json.loads(SPOTS_V1.read_text(encoding="utf-8"))["spots"] if r["kind"] == "call")
    for bad in (None, s["hero"], -1):
        s["pusher"] = bad
        with pytest.raises(SpotSetError, match="pusher"):
            load_spots(_write(tmp_path, [s]))
