import json

import numpy as np
import pytest

from referee.e3 import field as F
from stalker.e3 import game as G
from stalker.e3 import personas


def test_config_set_loads_with_hash_and_covers_the_registered_kinds():
    spec, sha = F.load()
    assert len(sha) == 64 and spec["players"] == 6
    names = {c["name"] for c in spec["configs"]}
    assert {"self5", "uniform5", "mixed_styles"} <= names and len(names) == len(spec["configs"])


def test_bad_config_files_are_rejected(tmp_path):
    spec, _ = F.load()
    short = tmp_path / "short.json"
    short.write_text(json.dumps({**spec, "configs": [{"name": "x", "opponents": ["tag"] * 4}]}), encoding="utf-8")
    with pytest.raises(F.FieldError, match="need 5"):
        F.load(short)
    unknown = tmp_path / "unknown.json"
    unknown.write_text(json.dumps({**spec, "configs": [{"name": "x", "opponents": ["shark"] * 5}]}), encoding="utf-8")
    with pytest.raises(F.FieldError, match="unknown opponents"):
        F.load(unknown)


def test_personas_return_distributions_over_the_e3_menu():
    rng = np.random.default_rng(3)
    field = personas.field()
    for _ in range(30):
        s = G.deal(rng, 6)
        while not s.done:
            p = field[s.to_act % len(field)](s)
            assert len(p) == len(G.legal(s)) and abs(p.sum() - 1) < 1e-12 and (p >= 0).all()
            s = G.apply(s, G.legal(s)[int(rng.choice(len(p), p=p))])


def test_a_table_of_one_policy_sums_to_zero_on_every_deal():
    # Duplicate symmetry: same policy everywhere -> the same hand in every rotation -> net zero.
    tag = personas.Persona("tag")
    for d in range(5):
        assert F.play_deal(tag, [tag] * 5, d).sum() == pytest.approx(0.0, abs=1e-9)
    assert F.evaluate(F.uniform, 4, configs=["self5"])["configs"][0]["bb100"] == 0.0


def test_tp_policy_self_table_is_zero_and_beliefs_do_not_break_play():
    pol = {}  # an empty TP table plays uniformly but still tracks its public ranges
    r = F.evaluate(pol, 3, configs=["self5", "tag5"])
    by = {c["name"]: c["bb100"] for c in r["configs"]}
    assert by["self5"] == 0.0 and r["worst"]["name"] == "tag5"


def test_worst_ignores_the_all_self_configuration(monkeypatch):
    # A policy that beats every non-self table: self5 is 0.0 but must not be reported as the worst.
    def fake(target, opps, deal_seed, k=5, depth="basic"):
        return np.zeros(6) if all(o is target for o in opps) else np.full(6, 0.5)

    monkeypatch.setattr(F, "play_deal", fake)
    r = F.evaluate(F.uniform, 3, configs=["self5", "tag5", "nit5"])
    by = {c["name"]: c["bb100"] for c in r["configs"]}
    assert by["self5"] == 0.0 and by["tag5"] > 0
    assert r["worst"]["name"] in ("tag5", "nit5") and r["worst"]["bb100"] > 0
    only_self = F.evaluate(F.uniform, 3, configs=["self5"])
    assert only_self["worst"]["name"] == "self5"


def test_results_are_seeded():
    a = F.evaluate(F.uniform, 3, seed=5, configs=["lag5"])
    assert a == F.evaluate(F.uniform, 3, seed=5, configs=["lag5"])


@pytest.mark.slow
def test_uniform_play_loses_to_tight_and_aggressive_fields():
    r = F.evaluate(F.uniform, 150, seed=1, configs=["tag5", "nit5", "lag5"])
    for c in r["configs"]:
        assert c["ci95"][1] < 0, c
    assert r["worst"]["bb100"] == min(c["bb100"] for c in r["configs"])


def test_v2_adds_registered_champions_and_v1_still_loads():
    spec, sha = F.load()
    assert spec["version"] == 2 and F.load(F.CONFIGS_V1)[0]["version"] == 1 and sha != F.load(F.CONFIGS_V1)[1]
    champs = {o for c in spec["configs"] for o in c["opponents"] if o.startswith(F.CHAMPION)}
    assert len(champs) >= 2 and champs <= {F.CHAMPION + n for n in F.champion_names(spec)}
    c = F.champion("beginner-40783153094")
    assert (c.k, c.depth, c.menu, c.raise_cap, c.variant) == (5, "basic", "v1", G.RAISE_CAP, "")
    assert len(c.sha256) == 64 and c.policy


def test_unregistered_champion_and_tampered_file_are_rejected(tmp_path):
    spec, _ = F.load()
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({**spec, "configs": [{"name": "x", "opponents": ["champion:nobody"] * 5}]}),
                   encoding="utf-8")
    with pytest.raises(F.FieldError, match="unknown opponents"):
        F.load(bad)
    reg = json.loads((F.HERE / F.REGISTRY).read_text(encoding="utf-8"))
    entry = dict(reg["champions"][0], file=str(F.HERE / "champions" / reg["champions"][0]["file"]), sha256="0" * 64)
    fake = tmp_path / "reg.json"
    fake.write_text(json.dumps({"champions": [entry]}), encoding="utf-8")
    with pytest.raises(F.FieldError, match="sha256"):
        F.champion(entry["name"], str(fake))


def test_a_champion_reads_its_own_beliefs_like_the_same_policy_as_target():
    # The target is the champion's own table read the same way: every rotation plays the same hand -> zero.
    c = F.champion("beginner-40783153094")
    for d in range(3):
        assert F.play_deal(c.policy, [c] * 5, d, k=c.k, depth=c.depth).sum() == pytest.approx(0.0, abs=1e-9)


def test_a_champion_keeps_its_key_variant_under_the_targets():
    c = F.champion("beginner-40783153094")
    s = G.deal(np.random.default_rng(4), 6)
    ranges = F.K.initial_ranges(6)
    base = c.probs(s, s.to_act, ranges)
    with F.K.using_variant("s2"):
        assert np.array_equal(c.probs(s, s.to_act, ranges), base)


def test_rows_report_pairing_and_seat_mix_and_champion_hashes():
    r = F.evaluate(F.uniform, 2, configs=["mixed_styles", "champions_mixed"])
    by = {c["name"]: c for c in r["configs"]}
    mixed = by["champions_mixed"]
    assert mixed["hands"] == 12 and mixed["deals"] == 2 and mixed["ci95_low"] == mixed["ci95"][0]
    assert mixed["opponents"][0].startswith(F.CHAMPION) and sum(mixed["seat_mix"].values()) == 5
    assert by["mixed_styles"]["seat_mix"] == {"tag": 1, "lag": 1, "nit": 1, "calling_station": 1, "maniac": 1}
    assert set(r["champions"]) == {o[len(F.CHAMPION):] for o in mixed["opponents"]} and "duplicate" in r["pairing"]


def test_champion_configs_are_skipped_on_rules_they_were_not_trained_on():
    with G.rules("real", None):
        r = F.evaluate(F.uniform, 2, configs=["tag5", "champion_mid5"])
    assert [c["name"] for c in r["configs"]] == ["tag5"] and r["champions"] == {}
    assert r["skipped"][0]["name"] == "champion_mid5" and "menu v1" in r["skipped"][0]["reason"]
    with G.rules("real", None), pytest.raises(F.FieldError, match="skipped"):
        F.evaluate(F.uniform, 2, configs=["champion_mid5"])


# #534: short-handed tables (field_v3) and per-player-count evaluation of player-mix models.
V3_SHA = "0a4639e07a747ea8e0cefcfc8822fdfc6e60ef4c6772b471a42d935c4d33ce1b"
STYLES = {"tag", "lag", "nit", "calling_station", "maniac"}


def _fingerprint(r: dict) -> str:
    import hashlib

    return hashlib.sha256(json.dumps(r, sort_keys=True).encode()).hexdigest()


def test_v3_has_pinned_short_handed_tables_with_single_style_and_mixed_configs():
    for n in (2, 3, 4, 5):
        spec, sha = F.load_players(n)
        assert sha == V3_SHA and spec["version"] == 3 and spec["players"] == n
        cfgs = spec["configs"]
        assert all(len(c["opponents"]) == n - 1 for c in cfgs)
        single = {c["opponents"][0] for c in cfgs if len(set(c["opponents"])) == 1}
        assert STYLES <= single and {"uniform", "self"} <= single
        if n >= 3:   # heads-up has one opponent, so no mixed table there
            assert sum(len(set(c["opponents"])) > 1 for c in cfgs) >= 2
    spec6, sha6 = F.load_players(6)
    assert (spec6, sha6) == F.load() and spec6["version"] == 2


def test_wrong_player_count_for_a_file_is_rejected():
    with pytest.raises(F.FieldError, match="no table for players=7"):
        F.load(F.CONFIGS_V3, 7)
    with pytest.raises(F.FieldError, match="not 4"):
        F.load(F.CONFIGS, 4)
    spec, _ = F.load_players(3)
    with pytest.raises(F.FieldError, match="not 6"):
        F.evaluate(F.uniform, 2, spec=spec, players=6)


def test_six_max_results_are_bit_identical_to_before_534():
    # Fingerprints taken on main (479eb96) before the players option: field_v2 sha, every row, worst.
    assert _fingerprint(F.evaluate(F.uniform, 3, seed=7)) == \
        "0f049fcdd8ceda622f277f0a8fae0e866b0f1a27a47516112db2c27a3d436c3f"
    r = F.evaluate({}, 2, seed=11, configs=["mixed_regs", "champions_mixed", "self5"])
    assert _fingerprint(r) == "99e5069af06bcd48df5c7886c10af56c63613152206d35bed3b463d9f5a1cd4d"
    assert F.evaluate(F.uniform, 3, seed=7, players=6) == F.evaluate(F.uniform, 3, seed=7)


@pytest.mark.parametrize("n", [2, 4])
def test_short_handed_deal_sums_to_zero_over_seat_rotations(n):
    tag = personas.Persona("tag")
    out = F.play_deal(tag, [tag] * (n - 1), 3)
    assert out.shape == (n,) and out.sum() == pytest.approx(0.0, abs=1e-9) and np.abs(out).sum() > 0
    pol = {}
    assert F.play_deal(pol, [pol] * (n - 1), 5).sum() == pytest.approx(0.0, abs=1e-9)
    r = F.evaluate(F.uniform, 2, players=n, configs=[f"self{n - 1}", f"tag{n - 1}"])
    by = {c["name"]: c for c in r["configs"]}
    assert by[f"self{n - 1}"]["bb100"] == 0.0 and by[f"tag{n - 1}"]["hands"] == 2 * n
    assert r["sha256"] == V3_SHA and r["worst"]["name"] == f"tag{n - 1}"


def test_six_handed_champions_are_skipped_at_other_table_sizes():
    r = F.evaluate(F.uniform, 2, players=2, configs=["tag1", "champion_mid1"])
    assert [c["name"] for c in r["configs"]] == ["tag1"] and r["champions"] == {}
    assert r["skipped"][0]["name"] == "champion_mid1" and "at 6 seats" in r["skipped"][0]["reason"]
    assert F.champion("mid-40851654734").players == 6
    with pytest.raises(F.FieldError, match="skipped"):
        F.evaluate(F.uniform, 2, players=4, configs=["champion_mid3"])


# --- AIVAT behaviour corrections (#593) ---

import zlib  # noqa: E402

_AIVAT_SPEC = {"version": "t", "players": 3, "configs": [{"name": "uni", "opponents": ["tag", "uniform"]}]}


def _noise_value(s, seat):
    # a deterministic but meaningless value of the state: unbiasedness must not depend on v
    return (zlib.crc32(f"{seat}|{s.history}|{s.street}".encode()) / 2**32 - 0.5) * 20


def _corr(value, opponents, deals=240, seed=7):
    rows = [F.play_deal({}, opponents, seed * 1_000_003 + d, value=value) for d in range(deals)]
    raw = np.array([r[0] for r in rows]).mean(axis=1)
    cor = np.array([r[1] for r in rows]).mean(axis=1)
    return raw, cor


def test_value_none_keeps_the_return_and_the_play():
    plain = F.play_deal({}, [F.uniform, F.uniform], 11)
    raw, corr = F.play_deal({}, [F.uniform, F.uniform], 11, value=F.committed_value)
    assert isinstance(plain, np.ndarray) and plain.tolist() == raw.tolist() and corr.shape == plain.shape


@pytest.mark.slow
def test_corrections_have_mean_zero_for_the_default_and_a_nonsense_value():
    # 2-handed needs an opponent with a different strategy: {} vs uniform is symmetric, so every mean is exactly 0
    tables = (
        [personas.Persona("tag")],  # 2-handed
        [personas.Persona("tag"), F.uniform],  # 3-handed
    )
    for opponents in tables:
        for value in (F.committed_value, _noise_value):
            raw, cor = _corr(value, opponents)
            assert raw.std(ddof=1) > 0 and cor.std(ddof=1) > 0
            assert abs(cor.mean()) < 2 * cor.std(ddof=1) / len(cor) ** 0.5


def test_unknown_strategies_are_not_corrected():
    tag = personas.Persona("tag")
    _, corr = F.play_deal(tag, [tag, tag], 5, value=F.committed_value)
    assert (corr == 0).all()
    custom = lambda s: np.full(len(G.legal(s)), 1.0 / len(G.legal(s)))  # noqa: E731
    _, corr = F.play_deal(custom, [custom, custom], 5, value=F.committed_value)
    assert (corr == 0).all()
    _, corr = F.play_deal(F.uniform, [F.uniform, F.uniform], 5, value=F.committed_value)
    assert (corr != 0).any()


def test_evaluate_aivat_is_record_only():
    base = F.evaluate({}, 6, spec=_AIVAT_SPEC)
    with_aivat = F.evaluate({}, 6, spec=_AIVAT_SPEC, aivat=True)
    stripped = {**with_aivat, "configs": [{k: v for k, v in c.items() if k != "aivat"} for c in with_aivat["configs"]]}
    assert stripped == base and "aivat" not in base["configs"][0]
    a = with_aivat["configs"][0]["aivat"]
    assert set(a) == {"bb100", "se", "variance_ratio"} and a["se"] > 0 and a["variance_ratio"] > 0


# --- AIVAT chance-node (board reveal) corrections (#597) ---

def _board_value(s, seat):
    # board-dependent and deterministic: rank sum of the board plus a hole/board hash noise
    ranks = sum(c % 13 for c in s.board)
    noise = zlib.crc32(f"{seat}|{s.hole[seat]}|{s.board}".encode()) / 2**32 - 0.5
    return ranks * 0.3 + noise * 4


def test_chance_off_matches_the_593_corrections_and_default_value_has_zero_chance_term():
    opps = [personas.Persona("tag"), F.uniform]
    n0, c0 = F.play_deal({}, opps, 9, value=F.committed_value, chance=False)
    n1, c1 = F.play_deal({}, opps, 9, value=F.committed_value)
    assert n0.tolist() == n1.tolist() and c0.tolist() == c1.tolist()  # committed_value ignores the board
    n2, c2 = F.play_deal({}, opps, 9, value=_board_value, chance=False)
    n3, c3 = F.play_deal({}, opps, 9, value=_board_value)
    assert n2.tolist() == n3.tolist() and c2.tolist() != c3.tolist()


def test_chance_terms_are_unbiased_and_keep_the_action_stream():
    for opps in ([personas.Persona("tag")], [personas.Persona("tag"), F.uniform]):
        rows = [F.play_deal({}, opps, 7_000_003 + d, value=_board_value) for d in range(200)]
        rows_off = [F.play_deal({}, opps, 7_000_003 + d, value=_board_value, chance=False) for d in range(200)]
        raw = np.array([r[0] for r in rows]).mean(axis=1)
        assert raw.tolist() == np.array([r[0] for r in rows_off]).mean(axis=1).tolist()
        chance = np.array([r[1] for r in rows]).mean(axis=1) - np.array([r[1] for r in rows_off]).mean(axis=1)
        se = chance.std(ddof=1) / len(chance) ** 0.5
        assert chance.std(ddof=1) > 0 and abs(chance.mean()) < 2 * se
        cor = np.array([r[1] for r in rows]).mean(axis=1)
        diff = raw - cor
        assert abs(diff.mean() - raw.mean()) < 2 * cor.std(ddof=1) / len(cor) ** 0.5


def test_allin_runout_is_one_chance_event():
    # a runout that opens several streets at once must be counted once (same stream index)
    seen = []
    orig = F._chance_term

    def spy(s, nxt, seat, value, rng, m):
        seen.append(len(nxt.board) - len(s.board))
        return orig(s, nxt, seat, value, rng, m)

    F._chance_term = spy
    try:
        for d in range(40):
            F.play_deal(F.uniform, [F.uniform, F.uniform], d, value=_board_value)
    finally:
        F._chance_term = orig
    assert seen and set(seen) <= {1, 2, 3, 4, 5}


def test_main_aivat_flag_adds_the_record_only_key(tmp_path, capsys, monkeypatch):
    pol = tmp_path / "p.json"
    pol.write_text("{}", encoding="utf-8")
    spec = {**_AIVAT_SPEC}
    monkeypatch.setattr(F, "load_players", lambda n: (spec, None))
    assert F.main([str(pol), "--hands", "4", "--players", "3"]) == 0
    plain = json.loads(capsys.readouterr().out)
    assert F.main([str(pol), "--hands", "4", "--players", "3", "--aivat"]) == 0
    withv = json.loads(capsys.readouterr().out)
    assert "aivat" not in plain["configs"][0] and "aivat" in withv["configs"][0]
    withv["configs"][0].pop("aivat")
    assert withv == plain


# --- board-dependent equity value (#634) ---

def test_equity_value_is_deterministic_and_never_reads_opponent_hole_cards():
    rng = np.random.default_rng(3)
    s = G.deal(np.random.default_rng([5, 0]), 3)
    while not s.done and len(s.board) < 3:
        s = G.apply(s, "c")  # everyone calls or checks to the flop
    assert len(s.board) == 3 and not s.folded[0]
    v = F.equity_value(s, 0)
    assert v == F.equity_value(s, 0)
    used = set(s.hole[0]) | set(s.board)
    others = [c for c in range(52) if c not in used]
    for _ in range(5):
        pick = rng.choice(others, size=4, replace=False).tolist()
        swapped = s._replace(hole=(s.hole[0], tuple(pick[:2]), tuple(pick[2:])))
        assert F.equity_value(swapped, 0) == v


def test_equity_value_folded_and_last_seat_and_live_cases():
    s = G.deal(np.random.default_rng([8, 0]), 3)
    pot = sum(s.total)
    folded = s._replace(folded=(True, False, False))
    assert F.equity_value(folded, 0) == F.committed_value(folded, 0) == -s.total[0] / G.BB
    alone = s._replace(folded=(False, True, True))
    assert F.equity_value(alone, 0) == (pot - s.total[0]) / G.BB
    eq = float(F._uniform_equity(())[F.combo_index(s.hole[0])])
    assert 0 < eq < 1 and F.equity_value(s, 0) == pytest.approx((eq ** 2 * pot - s.total[0]) / G.BB)


@pytest.mark.slow
def test_equity_value_gives_nonzero_chance_terms():
    opps = [personas.Persona("tag")]
    nonzero = 0
    for d in range(50):
        _, c_on = F.play_deal({}, opps, 3_000_017 + d, value=F.equity_value)
        _, c_off = F.play_deal({}, opps, 3_000_017 + d, value=F.equity_value, chance=False)
        nonzero += bool(np.any(c_on != c_off))
    assert nonzero >= 1


@pytest.mark.slow
def test_equity_value_corrections_are_unbiased_two_and_three_handed():
    for opps in ([personas.Persona("tag")], [personas.Persona("tag"), F.uniform]):
        raw, cor = _corr(F.equity_value, opps, deals=200, seed=11)
        assert raw.std(ddof=1) > 0 and cor.std(ddof=1) > 0
        adj = raw - cor
        assert abs(adj.mean() - raw.mean()) < 2 * cor.std(ddof=1) / len(cor) ** 0.5


def test_main_aivat_equity_picks_the_equity_value_and_bare_flag_keeps_committed(tmp_path, capsys, monkeypatch):
    pol = tmp_path / "p.json"
    pol.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(F, "load_players", lambda n: (_AIVAT_SPEC, None))
    seen = []
    orig = F.evaluate

    def spy(*a, **kw):
        seen.append(kw["aivat"])
        return orig(*a, **kw)

    monkeypatch.setattr(F, "evaluate", spy)
    assert F.main([str(pol), "--hands", "4", "--players", "3"]) == 0
    plain = json.loads(capsys.readouterr().out)
    assert F.main([str(pol), "--hands", "4", "--players", "3", "--aivat"]) == 0
    bare = json.loads(capsys.readouterr().out)
    assert F.main([str(pol), "--hands", "4", "--players", "3", "--aivat", "equity"]) == 0
    eq = json.loads(capsys.readouterr().out)
    assert seen == [False, F.committed_value, F.equity_value]
    assert bare == orig({}, 4, spec=_AIVAT_SPEC, k=5, depth="basic", players=3, aivat=True) | {"sha256": None}
    assert {k: v for k, v in eq.items() if k != "configs"} == {k: v for k, v in plain.items() if k != "configs"}
    eq["configs"][0].pop("aivat")
    assert eq == plain
