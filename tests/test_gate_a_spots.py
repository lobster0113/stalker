import json
import time
from collections import Counter

import pytest

from referee.anchors import icm_reference as ir
from referee.gate_a import SPOT_SET_VERSION, SPOTS_V1, SpotSetError, load_spots, spot_set_hash


def _write(tmp_path, spots):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"spots": spots}))
    return p


def _first():
    return json.loads(SPOTS_V1.read_text())["spots"][0]


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
