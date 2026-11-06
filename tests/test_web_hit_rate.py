"""#611: web policy table hit-rate tool."""
import json

from stalker.tools import web_hit_rate as H

K, DEPTH, N3 = 11, "full", 3


class Spy(dict):
    """Records the keys looked up; the first lookup is the first actor's real key."""
    def __init__(self, *a):
        super().__init__(*a)
        self.asked = []

    def get(self, k, d=None):
        self.asked.append(k)
        return super().get(k, d)


def _first_key():
    spy = Spy()
    H.measure(spy, N3, K, DEPTH, 1, 5)
    return spy.asked[0]


def _totals(r):
    return sum(c["decisions"] for c in r["by_street"].values()), sum(c["hits"] for c in r["by_street"].values())


def test_empty_policy_never_hits_and_same_seed_same_output():
    a = H.measure({}, N3, K, DEPTH, 3, 5)
    assert a == H.measure({}, N3, K, DEPTH, 3, 5)
    n, hits = _totals(a)
    assert n > 0 and hits == 0
    assert sum(c["decisions"] for c in a["by_kind"].values()) == n


def test_one_key_hits_on_its_street_only_and_min_visits_filters():
    key = _first_key()
    # the row length must match the legal actions: try widths until the key hits
    for width in (2, 3, 4, 5, 6, 7, 8):
        pol = {key: [1.0 / width] * width}
        r = H.measure(pol, N3, K, DEPTH, 1, 5, visits={key: 3})
        if r["by_street"]["0"]["hits"]:
            break
    assert r["by_street"]["0"]["hits"] >= 1
    assert all(r["by_street"][s]["hits"] == 0 for s in "123")
    mv = r["by_min_visits"]
    assert mv["2"]["by_street"]["0"]["hits"] >= 1 and mv["5"]["by_street"]["0"]["hits"] == 0
    assert mv["0"]["by_street"]["0"]["decisions"] == r["by_street"]["0"]["decisions"]


def test_load_policy_divides_by_q(tmp_path):
    p = tmp_path / "t.json"
    p.write_text(json.dumps({"q": 255, "policy": {"k": [255, 0]}}), encoding="utf-8")
    assert H.load_policy(p)[0] == {"k": [1.0, 0.0]}
