"""#336: trained E3 policy -> web policy file."""
import json

import numpy as np
import pytest

from stalker.e3.mccfr import E3MCCFR
from stalker.tools import export_web_policy as X


@pytest.mark.parametrize("p", [[1, 0, 0], [0.5, 0.5], [1 / 3] * 3, [0.001, 0.999], [0.2, 0.3, 0.1, 0.4], [0, 0],
                               [0.0025, 0.3324, 0.3324, 0.3327]])
def test_quantize_sums_to_q_within_one_step(p):
    q = X.quantize(p)
    assert sum(q) == X.Q and all(v >= 0 for v in q)
    ref = np.full(len(p), 1 / len(p)) if sum(p) == 0 else np.asarray(p) / sum(p)
    assert np.abs(np.asarray(q) / X.Q - ref).max() <= 1 / X.Q


def test_export_round_trip_keeps_every_key_and_names_the_run(tmp_path):
    m = E3MCCFR(1, 5, 3, "basic")
    m.iterate(5)
    ck = tmp_path / "c.ckpt.json"
    ck.write_text(json.dumps(m.state()), encoding="utf-8")
    sm = tmp_path / "s.json"
    sm.write_text(json.dumps({"job": "e3-tp-beginner", "tier": "beginner", "lbr": {"lbr_bb": 0.8, "stderr_bb": 0.2},
                              "field": {"worst": {"name": "nit5", "bb100": -30.0}}}), encoding="utf-8")
    out = tmp_path / "p.json"
    assert X.main(["--ckpt", str(ck), "--summary", str(sm), "--run", "123", "--out", str(out)]) == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["schema"] == X.SCHEMA and doc["run_id"] == "123" and doc["iterations"] == 5
    assert doc["tier"] == "beginner" and doc["players"] == 3 and doc["lbr_bb"] == 0.8 and doc["lbr_stderr_bb"] == 0.2
    assert doc["field_worst"]["name"] == "nit5"
    cur = m.current_policy()
    assert set(doc["policy"]) == set(cur) and doc["keys"] == len(cur)
    for k, v in cur.items():
        assert np.abs(np.asarray(doc["policy"][k]) / X.Q - np.asarray(v)).max() <= 1 / X.Q


def test_played_actions_never_quantize_to_zero():
    # #340 review: largest remainder alone gives [0, 85, 85, 85] here
    q = X.quantize([0.0025, 0.3324, 0.3324, 0.3327])
    assert q[0] >= 1 and sum(q) == X.Q
    assert X.quantize([1e-9, 1 - 1e-9]) == [1, 254] and X.quantize([0, 1]) == [0, 255]


def test_size_cap_and_pruning(tmp_path):
    m = E3MCCFR(1, 5, 3, "basic")
    m.iterate(20)
    ck = tmp_path / "c.ckpt.json"
    ck.write_text(json.dumps(m.state()), encoding="utf-8")
    out = tmp_path / "p.json"
    with pytest.raises(SystemExit, match="--min-visits"):
        X.main(["--ckpt", str(ck), "--out", str(out), "--max-bytes", "100"])
    X.main(["--ckpt", str(ck), "--out", str(out), "--min-visits", "3"])
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["keys_dropped"] > 0 and doc["min_visits"] == 3
    assert all(m.visits[k] >= 3 for k in doc["policy"])


@pytest.mark.slow
def test_average_strategy_and_pod_result_input(tmp_path):
    # #355: export the average strategy, straight from a pod training result
    from stalker.tools import pod_train as P

    r = P.run("beginner", 3, 1, minutes=0.001, seed=1, batch=2)
    res = tmp_path / "pod.json"
    res.write_text(json.dumps(r), encoding="utf-8")
    out = tmp_path / "p.json"
    assert X.main(["--pod-result", str(res), "--strategy", "average", "--run", "9", "--out", str(out)]) == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["strategy"] == "average" and doc["lbr_bb"] == r["lbr_average"]["lbr_bb"]
    assert doc["iterations"] == r["iters"] and doc["field_worst"] is None
    m = E3MCCFR.from_state(P.unpack_state(__import__("base64").b64decode(r["checkpoint"]["b64"]), r["model"]))
    assert set(doc["policy"]) <= set(m.policy()) and doc["keys"] == len(m.policy())
    with pytest.raises(SystemExit, match="drop --summary"):
        X.main(["--pod-result", str(res), "--summary", str(res), "--out", str(out)])


def test_pro_tables_name_their_board_nut_grid():
    # tpgto.js checkNutK skips a missing nut_k, so the export must write it for pro (#332)
    from stalker.e3 import tp_key as K

    assert X.meta_from({"k": 17, "n": 6, "depth": "pro", "iterations": 1, "nut_k": K.NUT_K}, None, "1", "")["nut_k"] == K.NUT_K
    assert X.meta_from({"k": 17, "n": 6, "depth": "pro", "iterations": 1}, None, "1", "")["nut_k"] == K.K_PRO
    assert "nut_k" not in X.meta_from({"k": 11, "n": 6, "depth": "full", "iterations": 1}, None, "1", "")


def test_policy_names_its_size_menu():
    # tpgto.js menuOf reads these (#386); a checkpoint without them is v1 with cap 3.
    old = X.meta_from({"k": 11, "n": 6, "depth": "full", "iterations": 1}, None, "1", "")
    assert (old["menu"], old["raise_cap"]) == ("v1", 3)
    real = X.meta_from({"k": 11, "n": 6, "depth": "full", "iterations": 1, "menu": "real", "raise_cap": None}, None, "1", "")
    assert (real["menu"], real["raise_cap"]) == ("real", None)


def test_placeholder_flag_is_written_and_read_and_defaults_false(tmp_path):
    # #397: the web shows 임시 AI only for entries that say so; a file without the field is not a placeholder.
    m = E3MCCFR(1, 5, 3, "basic")
    m.iterate(3)
    ck = tmp_path / "c.ckpt.json"
    ck.write_text(json.dumps(m.state()), encoding="utf-8")
    on, off = tmp_path / "on.json", tmp_path / "off.json"
    assert X.main(["--ckpt", str(ck), "--run", "1", "--placeholder", "--out", str(on)]) == 0
    assert X.main(["--ckpt", str(ck), "--run", "1", "--out", str(off)]) == 0
    d_on, d_off = (json.loads(p.read_text(encoding="utf-8")) for p in (on, off))
    assert X.placeholder_of(d_on) is True and d_on["trained_on"] == {"game": "cash", "players": 3, "stack_bb": 100, "menu": "v1"}
    assert X.placeholder_of(d_off) is False and "trained_on" not in d_off
    assert X.placeholder_of({}) is False and X.placeholder_of({"placeholder": "yes"}) is False


def test_shipped_index_marks_every_tier_placeholder_with_its_rules():
    from pathlib import Path

    idx = json.loads((Path(__file__).resolve().parents[1] / "web/app/policy/index.json").read_text(encoding="utf-8"))
    for tier, e in idx["tiers"].items():
        assert X.placeholder_of(e), f"{tier}: v1 6-max 100BB policy must stay marked 임시 until a real-rules one replaces it"
        assert {"game", "players", "stack_bb", "menu"} <= set(e["trained_on"])


def _ckpt(tmp_path, n, name="c"):
    m = E3MCCFR(1, 5, n, "basic")
    m.iterate(3)
    ck = tmp_path / f"{name}.ckpt.json"
    ck.write_text(json.dumps(m.state()), encoding="utf-8")
    return ck


def test_index_upsert_leaves_the_policy_file_and_6max_entry_unchanged(tmp_path):
    # #541: --index only adds the model-list entry; the 6-max policy bytes are the same with or without it,
    # a 6-max upsert keeps the shipped entry shape, and a 4-handed upsert goes to by_players only.
    from pathlib import Path

    shipped = Path(__file__).resolve().parents[1] / "web/app/policy/index.json"
    idx = tmp_path / "index.json"
    idx.write_bytes(shipped.read_bytes())
    ck6 = _ckpt(tmp_path, 6, "six")
    plain, indexed = tmp_path / "plain.json", tmp_path / "beginner-6.json"
    assert X.main(["--ckpt", str(ck6), "--run", "7", "--out", str(plain)]) == 0
    assert X.main(["--ckpt", str(ck6), "--run", "7", "--out", str(indexed), "--index", str(idx)]) == 0
    assert plain.read_bytes() == indexed.read_bytes()
    six = json.loads(idx.read_text(encoding="utf-8"))["tiers"]["beginner"]
    old = json.loads(shipped.read_text(encoding="utf-8"))["tiers"]["beginner"]
    assert six["file"] == "beginner-6.json" and six["bytes"] == len(plain.read_bytes()) and six["run_id"] == "7"
    assert [k for k in six if k in old] == [k for k in old if k in six] and "by_players" not in six

    before = idx.read_text(encoding="utf-8")
    out4 = tmp_path / "beginner-4.json"
    assert X.main(["--ckpt", str(_ckpt(tmp_path, 4, "four")), "--run", "fixture", "--out", str(out4), "--index", str(idx)]) == 0
    after = json.loads(idx.read_text(encoding="utf-8"))
    b = after["tiers"]["beginner"]
    assert {k: v for k, v in b.items() if k != "by_players"} == json.loads(before)["tiers"]["beginner"]
    assert after["tiers"]["mid"] == json.loads(before)["tiers"]["mid"] and after["tiers"]["pro"] == json.loads(before)["tiers"]["pro"]
    e4 = b["by_players"]["4"]
    assert e4["file"] == "beginner-4.json" and e4["players"] == 4 and e4["run_id"] == "fixture" and "policy" not in e4
    # a later 6-max re-export keeps the by_players map, and a 2-handed one sorts in front of 4
    X.main(["--ckpt", str(_ckpt(tmp_path, 2, "two")), "--run", "fixture", "--out", str(tmp_path / "beginner-2.json"), "--index", str(idx)])
    X.main(["--ckpt", str(ck6), "--run", "8", "--out", str(indexed), "--index", str(idx)])
    b = json.loads(idx.read_text(encoding="utf-8"))["tiers"]["beginner"]
    assert list(b["by_players"]) == ["2", "4"] and b["run_id"] == "8"


def test_index_upsert_refuses_another_schema_and_starts_a_new_list(tmp_path):
    with pytest.raises(SystemExit, match="index.json"):
        X.upsert_index({"schema": "stalker.web.policy"}, {"tier": "mid", "players": 6})
    idx = X.upsert_index(None, {"tier": "mid", "players": 3, "file": "mid-3.json"})
    assert idx["schema"] == X.INDEX_SCHEMA and idx["tiers"] == {"mid": {"by_players": {"3": {"tier": "mid", "players": 3, "file": "mid-3.json"}}}}


def test_export_reads_gz_and_plain_checkpoints_alike(tmp_path):
    from stalker.jsonio import write_json_gz

    m = E3MCCFR(1, 5, 3, "basic")
    m.iterate(5)
    plain, gz = tmp_path / "c.ckpt.json", tmp_path / "c.ckpt.json.gz"
    plain.write_text(json.dumps(m.state()), encoding="utf-8")
    write_json_gz(gz, m.state())
    for ck, out in ((plain, tmp_path / "a.json"), (gz, tmp_path / "b.json")):
        assert X.main(["--ckpt", str(ck), "--run", "1", "--out", str(out)]) == 0
    assert (tmp_path / "a.json").read_bytes() == (tmp_path / "b.json").read_bytes()


MIX = (2, 4, 6)


@pytest.fixture(scope="module")
def mixn(tmp_path_factory):
    """#585: a small seeded 2/4/6 c1 player-mix checkpoint and the full table it holds."""
    m = E3MCCFR(1, 5, 6, "basic", key_variant="c1", player_mix=MIX)
    m.iterate(3)   # seed 1: each of 2, 4 and 6 owns keys, and call| keys are shared
    d = tmp_path_factory.mktemp("mixn")
    ck = d / "mixn.ckpt.json"
    ck.write_text(json.dumps(m.state()), encoding="utf-8")
    return ck, m


def test_players_split_a_c1_mix_into_complete_files_sharing_call_keys(tmp_path, mixn):
    from stalker.e3.mccfr import key_players

    ck, m = mixn
    cur = m.current_policy()
    idx = tmp_path / "index.json"
    docs = {}
    for n in MIX:
        out = tmp_path / f"beginner-{n}.json"
        assert X.main(["--ckpt", str(ck), "--run", "5", "--players", str(n), "--min-visits", "0",
                       "--out", str(out), "--index", str(idx)]) == 0
        docs[n] = json.loads(out.read_text(encoding="utf-8"))
    shared = {k for k in cur if key_players(k) is None}
    assert shared and all(k.startswith("call|") for k in shared)
    for n, doc in docs.items():
        own = {k for k in cur if key_players(k) == n}
        assert own and set(doc["policy"]) == own | shared and doc["keys"] == len(own) + len(shared) and doc["players"] == n
    # every count's own keys land in exactly one file; the shared call| keys in all of them (#610)
    assert sum(d["keys"] for d in docs.values()) == len(cur) + (len(MIX) - 1) * len(shared)
    assert len(shared) == m.shared_keys()
    tiers = json.loads(idx.read_text(encoding="utf-8"))["tiers"]["beginner"]
    assert tiers["file"] == "beginner-6.json" and tiers["players"] == 6
    assert {k: v["file"] for k, v in tiers["by_players"].items()} == {"2": "beginner-2.json", "4": "beginner-4.json"}


def test_players_meta_reads_that_counts_lbr_and_leaves_it_empty_when_missing(tmp_path, mixn):
    ck, _ = mixn
    sm = tmp_path / "s.json"
    sm.write_text(json.dumps({"job": "e3-tp-beginner-c1-mixn", "tier": "beginner", "lbr": {"lbr_bb": 9.0, "stderr_bb": 1.0},
                              "by_players": {"4": {"lbr": {"lbr_bb": 0.4, "stderr_bb": 0.1}, "lbr_average": {"lbr_bb": 0.3, "stderr_bb": 0.05},
                                                   "field": {"worst": {"name": "nit5", "bb100": -3.0}}}}}), encoding="utf-8")
    out = tmp_path / "p.json"

    def run(*extra):
        assert X.main(["--ckpt", str(ck), "--summary", str(sm), "--run", "77", "--out", str(out), *extra]) == 0
        return json.loads(out.read_text(encoding="utf-8"))

    d = run("--players", "4")
    assert (d["run_id"], d["iterations"], d["players"]) == ("77", 3, 4)
    assert (d["lbr_bb"], d["lbr_stderr_bb"], d["field_worst"]["name"]) == (0.4, 0.1, "nit5")
    d = run("--players", "4", "--strategy", "average")
    assert (d["lbr_bb"], d["lbr_stderr_bb"], d["field_worst"]) == (0.3, 0.05, None)
    d = run("--players", "2", "--placeholder")   # no "2" row: empty numbers, still the run
    assert (d["lbr_bb"], d["lbr_stderr_bb"], d["field_worst"], d["run_id"]) == (None, None, None, "77")
    assert d["trained_on"]["players"] == 2
    assert X.main(["--ckpt", str(ck), "--run", "1", "--players", "2", "--out", str(out)]) == 0   # no summary at all
    assert json.loads(out.read_text(encoding="utf-8"))["lbr_bb"] is None


def test_players_refuses_what_it_cannot_split(tmp_path, mixn):
    ck, _ = mixn
    out = tmp_path / "p.json"
    with pytest.raises(SystemExit, match=r"not in this table's player_mix \[2, 4, 6\]"):
        X.main(["--ckpt", str(ck), "--players", "3", "--out", str(out)])
    six = _ckpt(tmp_path, 6, "six")
    with pytest.raises(SystemExit, match="drop --players or pass --players 6"):
        X.main(["--ckpt", str(six), "--players", "4", "--out", str(out)])
    plain, same = tmp_path / "plain.json", tmp_path / "same.json"
    assert X.main(["--ckpt", str(six), "--run", "1", "--out", str(plain)]) == 0
    assert X.main(["--ckpt", str(six), "--run", "1", "--players", "6", "--out", str(same)]) == 0
    assert plain.read_bytes() == same.read_bytes()
    st = json.loads(ck.read_text(encoding="utf-8"))
    st["key_variant"] = "b1"
    with pytest.raises(SystemExit, match="only a c1 player-mix table splits"):
        X.split_players(st, 4)
    assert X.main(["--ckpt", str(ck), "--run", "1", "--out", str(out)]) == 0   # no --players: the whole table, as before
    assert json.loads(out.read_text(encoding="utf-8"))["players"] == 6


@pytest.mark.parametrize("depth", ["basic", "full", "pro"])
def test_key_players_reads_the_c1_public_key_player_field(depth):
    # #585: the split relies on key_players matching tp_key's c1 key at every depth and seat count
    from stalker.e3 import game as G
    from stalker.e3 import tp_key as K
    from stalker.e3.mccfr import key_players

    rng = np.random.default_rng(585)
    seen = set()
    for n in (2, 3, 4, 5, 6):
        for _ in range(3):
            s = G.deal(rng, n)
            while not s.done:
                seat = s.to_act
                pub = K.public_key(s, seat, depth, "c1")
                want = None if pub.startswith("call|") else n
                assert key_players(K.key(pub, 3)) == want, pub
                seen.add(want)
                legal = G.legal(s)
                s = G.apply(s, legal[int(rng.integers(len(legal)))])
    assert set(range(2, 7)) <= seen


def test_key_variant_is_written_for_c1_tables_and_left_out_for_legacy_ones(tmp_path, mixn):
    # #604: the page picks c1 keys from this field; a legacy table must not grow it.
    ck, _ = mixn
    out, idx = tmp_path / "c1.json", tmp_path / "index.json"
    assert X.main(["--ckpt", str(ck), "--run", "9", "--players", "4", "--out", str(out), "--index", str(idx)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["key_variant"] == "c1"
    assert json.loads(idx.read_text(encoding="utf-8"))["tiers"]["beginner"]["by_players"]["4"]["key_variant"] == "c1"
    six = _ckpt(tmp_path, 6, "legacy")
    assert X.main(["--ckpt", str(six), "--run", "9", "--out", str(out)]) == 0
    assert "key_variant" not in json.loads(out.read_text(encoding="utf-8"))
    assert "key_variant" not in X.meta_from({"k": 11, "n": 6, "depth": "full", "iterations": 1}, None, "1", "")


def test_shipped_short_handed_mid_policies_are_the_c1_export_bytes():
    # #615: mid-2..5 are copied byte for byte from ops 5b5f2875 (docs/research/2026-11-c1-web-export.md
    # 「실측: call| 포함 재-export」); the index routes them to c1 keys and leaves the 6-max (legacy key) entry alone.
    # #610: the earlier copy (ops fd521c42) had no shared `call|` keys, so call-or-fold spots played uniform.
    import hashlib
    from pathlib import Path

    pol = Path(__file__).resolve().parents[1] / "web/app/policy"
    # #640: mid-2 is the min_visits=5 re-export, copied from ops 81aa9424 (#631); the old mv=10 file was a4287c01….
    want = {2: "66613749fa23f3fefe7243aeb34648eb964c0476e8fba7491701d5c52a3a3579",
            3: "c78a325925b73ea47c15381c5c355917f38aa99b92826d470b718d81d48578ea",
            4: "2bc99320fc231ed9f365d4869fccbf14c6fa2c2b2169f137031293a341c7e29c",
            # #753: mid-4 is the 120k export (run 42591543123) copied from ops 18409fb6, swapped in on #741's
            # 4-seed flop/turn uniform-rate remeasure (intervals overlap, preflop exact higher); the 40k file was 3f248f0c….
            # #739: mid-5 is the 120k export (run 42591543123) copied from ops 18409fb6, swapped in on #733's
            # flop/turn uniform-rate comparison; the 40k file was 0b785199….
            5: "7484bcd181ec7c2d2fd46534c774671265a6c59fb947a918afc2db137de8e18c"}
    run_ids = {2: "41813684540", 3: "41813684540", 4: "42591543123", 5: "42591543123"}
    mid = json.loads((pol / "index.json").read_text(encoding="utf-8"))["tiers"]["mid"]
    for n, sha in want.items():
        body = (pol / f"mid-{n}.json").read_bytes()
        assert hashlib.sha256(body).hexdigest() == sha, f"mid-{n}.json differs from its ops source; re-copy it"
        policy = json.loads(body)["policy"]
        assert any(k.startswith("call|") for k in policy), f"mid-{n}.json has no call| keys; re-export after #610"
        e = mid["by_players"][str(n)]
        assert (e["file"], e["players"], e["run_id"], e["key_variant"], e["bytes"]) == (
            f"mid-{n}.json", n, run_ids[n], "c1", len(body))
        assert len(body) <= 3_145_728, f"mid-{n}.json exceeds the page budget"
    assert mid["by_players"]["2"]["min_visits"] == 5
    assert (mid["run_id"], mid["file"]) == ("40919207457", "mid-6.json") and "key_variant" not in mid


def test_keep_players_keeps_the_shared_call_keys_in_every_seat_count():
    # #610: `call|` keys name no seat count (mixn shares them), so each per-count file must carry them;
    # dropping them left mid-3.json with none and the page played every call-or-fold spot uniform.
    pol = {"call|0|1|2|fc": [0.3, 0.7], "BTN|n3|x|1": [0.5, 0.5], "BTN|n4|x|1": [0.2, 0.8],
           "b|n3|y|2": [1.0, 0.0], "p|SB|n4|z|3": [0.1, 0.9]}
    assert set(X.keep_players(pol, 3)) == {"call|0|1|2|fc", "BTN|n3|x|1", "b|n3|y|2"}
    assert set(X.keep_players(pol, 4)) == {"call|0|1|2|fc", "BTN|n4|x|1", "p|SB|n4|z|3"}
    assert set(X.keep_players(pol, 5)) == {"call|0|1|2|fc"}
