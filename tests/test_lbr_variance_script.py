"""scripts/lbr_variance.py (#770): same seed gives the same bytes, and its plain column is the referee's LBR."""
import importlib.util
import json
import pathlib

from referee.e3.lbr import lbr
from stalker.e3 import game as G
from stalker.e3 import tp_key as K
from stalker.tools import web_hit_rate as H
from stalker.tools.web_policy_lbr import WebPolicy

ROOT = pathlib.Path(__file__).parents[1]
_spec = importlib.util.spec_from_file_location("lbr_variance", ROOT / "scripts/lbr_variance.py")
lv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lv)
POLICY = ROOT / "web/app/policy/mid-2.json"


def test_deterministic_and_plain_column_is_the_referee_lbr():
    a = lv.run(POLICY, 2, hands=3, seeds=1, samples=4)
    b = lv.run(POLICY, 2, hands=3, seeds=1, samples=4)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    table, doc = H.load_policy(POLICY)
    rules = H.rules_of(doc)
    with G.rules(rules["menu"], rules["raise_cap"]), K.using_variant(H.variant_of(table, doc)):
        ref = [lbr(WebPolicy(table, doc["k"]), q, 3, 10_001 + 101 * q, doc["k"], 2, doc["depth"]).mean_bb for q in (0, 1)]
    assert a["seeds"][0]["plain_bb"] == round((ref[0] + ref[1]) / 2, 4)
    assert abs(a["mean"]["diff"] - (a["mean"]["plain"] - a["mean"]["corrected"])) < 2e-4


def test_corrected_column_is_the_referee_aivat_column():
    """#781: the script runs the referee's loop, so its corrected column is `exploitability_lb`'s `aivat_lbr_bb`."""
    from referee.e3.lbr import exploitability_lb
    a = lv.run(POLICY, 2, hands=3, seeds=1, samples=4)
    table, doc = H.load_policy(POLICY)
    rules = H.rules_of(doc)
    with G.rules(rules["menu"], rules["raise_cap"]), K.using_variant(H.variant_of(table, doc)):
        ref = exploitability_lb(WebPolicy(table, doc["k"]), 3, seed=10_001, k=doc["k"], n=2, depth=doc["depth"],
                                aivat_samples=4)
    assert a["seeds"][0]["corrected_bb"] == ref["aivat_lbr_bb"]
    assert a["seeds"][0]["plain_bb"] == ref["lbr_bb"]
