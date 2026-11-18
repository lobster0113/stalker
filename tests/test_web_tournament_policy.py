"""#969 (ADR 0029 H4): the first real tournament policy in web/app/policy and what reads the folder.

The file and index are copied byte for byte from ops e4c10b40 `cloud/policies/43735226442/` (cloud.yml run 44196749263,
`mode=export export_kind=tournament tier=mid export_min_visits=10`); the summary is `ops:cloud/exports/43735226442.json`.
"""
import hashlib
import json
import re
from pathlib import Path

from stalker.env.spec import from_tournament
from stalker.tools import export_web_policy as X
from stalker.tools import web_policy_lbr_job as J
from stalker.tournament.config import load_preset

ROOT = Path(__file__).resolve().parents[1]
POL = ROOT / "web/app/policy"
FILE = "t-1261657cabcdc1ad-b0.json"
FILE_SHA = "197050c28cceb92769f267aad3e23374778fdcc2d48061bf42766ce4c732b782"   # summary files[0].sha256
# train_env of run 43735226442 (ops:cloud/results/43735226442.summary.json via the export) and the run's own record.
TRAIN_ENV = {"env_id": "1261657cabcdc1ad", "stage": "b", "lam": 0.0, "stacks": "bubble:skewed", "level_index": 0}
# json.dumps(tiers, sort_keys=True) before #969: the cash entries must not move by a byte (ADR 0029 decision 1).
TIERS_SHA = "06f69512730bd69b8f9355bfa39614a689443b64282dd27e7d43dfd1b7025777"


def _index():
    return json.loads((POL / "index.json").read_text(encoding="utf-8"))


def test_shipped_tournament_policy_is_the_export_bytes_within_the_budgets():
    body = (POL / FILE).read_bytes()
    assert hashlib.sha256(body).hexdigest() == FILE_SHA, f"{FILE} differs from ops cloud/policies/43735226442; re-copy it"
    assert len(body) <= X.MAX_BYTES, f"{FILE} is {len(body)} bytes > {X.MAX_BYTES}: raise export_min_visits"
    total = sum((POL / f).stat().st_size for f in (p.name for p in POL.glob("t-*.json")))
    assert total <= X.TOURNAMENT_MAX_BYTES, f"tournament policies total {total} > {X.TOURNAMENT_MAX_BYTES} (ADR 0029 decision 3)"
    listed = {e["file"] for *_, e in X.tournament_entries(_index())}
    assert listed == {p.name for p in POL.glob("t-*.json")}, "every t-*.json needs an index entry and vice versa"


def test_index_entry_matches_the_file_and_the_runs_train_env():
    idx = _index()
    assert idx["schema_version"] == 2
    e = idx["tournament"]["1261657cabcdc1ad"]["b"]["ante"]["0"]
    doc = json.loads((POL / FILE).read_bytes())
    assert e["file"] == FILE and e["bytes"] == (POL / FILE).stat().st_size
    assert {k: e[k] for k in TRAIN_ENV} == TRAIN_ENV == {k: doc[k] for k in TRAIN_ENV}
    assert e["ante"] == doc["ante"] == 0 and e["payoff"] == doc["payoff"] == "icm"
    assert e["players"] == doc["players"] == 4 and e["trained_on"] == doc["trained_on"]
    assert e["run_id"] == doc["run_id"] == "43735226442" and e["tier"] == "mid" and e["key_variant"] == "c1"
    assert e["keys"] == len(doc["policy"]) and e["min_visits"] == 10
    # the env_id is the preset's, so the page (and records) can find it from the preset name
    assert from_tournament(load_preset("9max_sng_503020")).env_id == e["env_id"]


# #995: the in-the-money stage (m) of the same preset, trained 3- and 2-handed (ADR 0027 stage 2), exported by
# cloud.yml `mode=export export_kind=tournament tier=mid export_min_visits=10`: run -> (export run, file, sha256 of the
# ops `cloud/policies/<run>/t-1261657cabcdc1ad-m0.json`, copied byte for byte under the per-count name).
STAGE2 = {
    3: ("44121220524", "44273145277", "t-1261657cabcdc1ad-m0-n3.json", "03aa66ee27761d501f15b94341d7c77b534d829ae5e6ed45aa12a59f6b1e3d4e"),
    2: ("44139238381", "44273417103", "t-1261657cabcdc1ad-m0-n2.json", "603c5bdea104343141abeb4f3211f37656d32d86f48b060a27e565512c0487c8"),
}
STAGE2_ENV = {"env_id": "1261657cabcdc1ad", "stage": "m", "lam": 0.0, "stacks": "bubble:skewed", "level_index": 0}
# The bubble slot as #969 shipped it (json.dumps(slot, sort_keys=True)): adding stage m must not move it by a byte.
B0_SHA = "f2e58253aedc96570f78c97056e8fd516515e577cc9d42ce81ec8e5214d502f0"


def test_stage2_policies_are_the_export_bytes_and_match_their_runs_train_env():
    slot = _index()["tournament"]["1261657cabcdc1ad"]["m"]["ante"]
    assert list(slot) == ["0"] and sorted(slot["0"]["by_players"]) == ["2", "3"]
    for n, (run, _export, name, sha) in STAGE2.items():
        body = (POL / name).read_bytes()
        assert hashlib.sha256(body).hexdigest() == sha, f"{name} differs from ops cloud/policies/{run}; re-copy it"
        assert len(body) <= X.MAX_BYTES, f"{name} is {len(body)} bytes > {X.MAX_BYTES}: raise export_min_visits"
        e, doc = slot["0"]["by_players"][str(n)], json.loads(body)
        assert e["file"] == name and e["bytes"] == len(body)
        assert {k: e[k] for k in STAGE2_ENV} == STAGE2_ENV == {k: doc[k] for k in STAGE2_ENV}
        assert e["players"] == doc["players"] == n and e["trained_on"] == doc["trained_on"] == {"game": "tournament", "env_id": STAGE2_ENV["env_id"], "stage": "m", "players": n}
        assert e["ante"] == doc["ante"] == 0 and e["payoff"] == doc["payoff"] == "icm"
        assert e["run_id"] == doc["run_id"] == run and e["tier"] == "mid" and e["key_variant"] == "c1" and e["min_visits"] == 10
        assert e["keys"] == len(doc["policy"])


def test_bubble_entry_is_unchanged_by_stage2():
    b = _index()["tournament"]["1261657cabcdc1ad"]["b"]
    assert hashlib.sha256(json.dumps(b, sort_keys=True).encode()).hexdigest() == B0_SHA


def test_cash_tiers_are_unchanged_by_the_tournament_entry():
    tiers = _index()["tiers"]
    assert hashlib.sha256(json.dumps(tiers, sort_keys=True).encode()).hexdigest() == TIERS_SHA


def test_page_env_ids_are_the_python_presets():
    # #969: the index is keyed by EnvSpec.env_id; the page had preset names there and could never find a policy.
    html = (ROOT / "web/demo/index.html").read_text(encoding="utf-8")
    ids = json.loads(re.search(r"const TOUR_ENV_ID = (\{[^}]*\});", html).group(1))
    presets = json.loads(re.search(r"const TOUR_PRESET = (\{[^}]*\});", html).group(1).replace("mtt:", '"mtt":'))
    assert set(presets.values()) == set(ids)
    for name, env_id in ids.items():
        assert from_tournament(load_preset(name)).env_id == env_id, f"TOUR_ENV_ID[{name!r}] must be {from_tournament(load_preset(name)).env_id}"


def test_web_lbr_readers_skip_the_tournament_file():
    # e3_web_lbr / web_policy_lbr_job measure the served cash pages mid-<n>.json only; a t-*.json in the folder is not one
    # of them (no tournament LBR here, ADR 0029 H4 out of scope).
    from referee import metrics

    runs = J.page_runs(POL)
    assert sorted(runs) == list(J.PLAYERS)
    assert all(runs[n] == json.loads((POL / f"mid-{n}.json").read_bytes())["run_id"] for n in J.PLAYERS)
    assert set(J.legacy_players(POL)) <= set(J.PLAYERS)   # loads the mid pages only
    assert "43735226442" not in runs.values()
    assert {metrics._page_run(ROOT, str(n)) for n in J.PLAYERS} == set(runs.values())
