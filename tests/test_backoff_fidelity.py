import json

import pytest

from stalker.tools import backoff_fidelity as F

# Three keys sharing one L1 key (they differ only in the stack depths), one more that shares only their L2 key.
A = "BTN|n3|1|1|0|2|0|0|tc0|s4:4|u10|hn|go|ka|e5|o1v1k0"
B = "BTN|n3|1|1|0|2|0|0|tc0|s7:7|u10|hn|go|ka|e5|o1v1k0"
C = "BTN|n3|1|1|0|2|0|0|tc0|s5:5|u10|hn|go|ka|e5|o1v1k0"
L2ONLY = "BTN|n3|1|1|0|2|0|4|tc0|s5:5|u01|ha|gm|ka|e5|o-v-k2"
E6 = "BTN|n3|1|1|0|2|0|0|tc0|s4:4|u10|hn|go|ka|e6|o1v1k0"   # alone at every level; its e5 neighbour is the four above
TABLE = {A: [1.0, 0.0], B: [0.0, 1.0], C: [0.5, 0.5], L2ONLY: [0.9, 0.1]}
TOP = 10


def _cell(out, level, street="1"):
    return out["by_street"][street][level]


def test_leave_one_out_mean_excludes_the_keys_own_row():
    sums = F.sum_tables(TABLE)
    row, level = F.loo_row(sums, A, TABLE[A])
    assert level == "L1" and row.tolist() == [0.25, 0.75]   # mean of B, C; with A mixed in it would be [0.5, 0.5]
    assert F.tv(TABLE[A], row) == pytest.approx(0.75)
    out = F.measure(TABLE, TOP)
    l1 = _cell(out, "L1")   # A 0.75 (uniform 0.5), B 0.75 (0.5), C 0 (0): mean of A, B is C itself
    assert l1["n"] == 3 and l1["tv_mean"] == pytest.approx(0.5)
    assert l1["uniform_tv_mean"] == pytest.approx(1 / 3) and l1["better_than_uniform"] == 0.0


def test_a_key_alone_at_a_level_falls_through_to_the_next():
    sums = F.sum_tables(TABLE)
    row, level = F.loo_row(sums, L2ONLY, TABLE[L2ONLY])   # its L1 key holds only itself
    assert level == "L2" and row.tolist() == pytest.approx([0.5, 0.5])   # A, B, C
    l2 = _cell(F.measure(TABLE, TOP), "L2")
    assert l2["n"] == 1 and l2["tv_mean"] == pytest.approx(0.4)
    assert l2["uniform_tv_mean"] == pytest.approx(0.4) and l2["better_than_uniform"] == 0.0   # equal is not better


def test_l4_neighbor_on_and_off():
    table = {**TABLE, E6: [0.0, 1.0]}
    off = F.measure(table, TOP)
    assert _cell(off, "uniform")["n"] == 1 and "L4" not in off["levels"] and "l4_neighbor" not in off
    on = F.measure(table, TOP, l4_neighbor=True)
    l4 = _cell(on, "L4")   # e5 L3 mean of A, B, C, L2ONLY = [0.6, 0.4]
    assert l4["n"] == 1 and l4["tv_mean"] == pytest.approx(0.6) and l4["better_than_uniform"] == 0.0
    assert "uniform" not in on["by_street"]["1"] and on["l4_neighbor"] is True
    assert _cell(on, "L1") == _cell(off, "L1")   # the levels before L4 are unchanged


def test_call_keys_are_counted_apart():
    table = {**TABLE, "call|1|1|1|fc|e0": [1.0, 0.0], "call|1|2|1|fc|e0": [0.75, 0.25]}   # share the L2 key
    out = F.measure(table, TOP)
    c = out["call_keys"]["by_street"]["1"]["L2"]
    assert c["n"] == 2 and c["tv_mean"] == pytest.approx(0.25) and c["better_than_uniform"] == 0.5   # [.75,.25] ties uniform
    assert sum(cell["n"] for cell in out["by_street"]["1"].values()) == len(TABLE)


def _write(tmp_path, policy, name="t-3.json", **head):
    p = tmp_path / name
    doc = {"q": 4, "players": 3, "k": TOP + 1, "depth": "full", "key_variant": "c1", **head,
           "policy": {k: [round(x * 4) for x in r] for k, r in policy.items()}}
    p.write_text(json.dumps(doc), encoding="utf-8")
    return p


def test_main_output_is_byte_identical_and_independent_of_key_order(tmp_path, capsys):
    table = {**TABLE, E6: [0.0, 1.0]}
    outs = []
    for i, pol in enumerate((table, dict(reversed(list(table.items()))))):
        assert F.main([str(_write(tmp_path, pol, f"t{i}.json")), "--l4-neighbor"]) == 0
        outs.append(capsys.readouterr().out.replace(f"t{i}.json", "t.json"))
    assert outs[0] == outs[1]
    assert json.loads(outs[0])["schema_version"] == 2
    for combine in ("mean", "mode"):   # same input -> same bytes, for both combines
        runs = []
        for _ in range(2):
            assert F.main([str(_write(tmp_path, table)), "--l4-neighbor", "--combine", combine]) == 0
            runs.append(capsys.readouterr().out)
        assert runs[0] == runs[1] and json.loads(runs[0])["combine"] == combine


def test_main_rejects_a_legacy_table(tmp_path):
    p = _write(tmp_path, {"0|0|1|1|0|2|0|fcra|e0": [1.0, 0.0]}, key_variant="")
    with pytest.raises(SystemExit, match="c1"):
        F.main([str(p)])


# Two near-pure rows per argmax (actions 0 and 2) in one L1 cell; the mean of the others mixes both sides.
P = "BTN|n3|1|1|0|2|0|0|tc0|s4:4|u10|hn|go|ka|e2|o1v1k0"
Q = "BTN|n3|1|1|0|2|0|0|tc0|s7:7|u10|hn|go|ka|e2|o1v1k0"
R = "BTN|n3|1|1|0|2|0|0|tc0|s5:5|u10|hn|go|ka|e2|o1v1k0"
S = "BTN|n3|1|1|0|2|0|0|tc0|s6:6|u10|hn|go|ka|e2|o1v1k0"
T = "BTN|n3|1|1|0|2|0|0|tc0|s3:3|u10|hn|go|ka|e2|o1v1k0"
PURE = {P: [0.9, 0.1, 0.0], Q: [0.8, 0.2, 0.0], R: [0.0, 0.1, 0.9], S: [0.1, 0.0, 0.9]}


def test_mode_row_takes_the_most_common_argmax_and_scores_agreement():
    row, level = F.loo_mode_row(F.mode_tables(PURE), P, PURE[P])   # left: Q (argmax 0) and R, S (argmax 2): 2 wins
    assert level == "L1" and row.tolist() == pytest.approx([0.05, 0.05, 0.9])
    out = F.measure(PURE, TOP, combine="mode")   # every key leaves its own side one row short, so all disagree
    l1 = _cell(out, "L1")
    assert out["combine"] == "mode" and l1["n"] == 4 and l1["argmax_agree"] == 0.0 and l1["tv_mean"] == pytest.approx(0.9)
    assert l1["uniform_argmax_agree"] == pytest.approx(1 / 3)


def test_mode_recovers_the_real_row_where_the_mean_is_near_uniform():
    three = {**PURE, T: [1.0, 0.0, 0.0]}
    mean, _ = F.loo_row(F.sum_tables(three), P, three[P])
    assert mean.tolist() == pytest.approx([0.475, 0.075, 0.45])   # TV 0.45 against uniform's 0.567
    mode, _ = F.loo_mode_row(F.mode_tables(three), P, three[P])   # Q, T (argmax 0) beat R, S 2:2 on the tie rule
    assert mode.tolist() == pytest.approx(three[P])   # mean of Q and T is P itself
    l1 = _cell(F.measure(three, TOP, combine="mode"), "L1")
    # P, Q, T: a 2:2 tie -> action 0 -> agree; R, S: 3:1 for action 0 -> disagree.
    assert l1["argmax_agree"] == pytest.approx(3 / 5) and l1["better_than_uniform"] == pytest.approx(3 / 5)


def test_argmax_ties_go_to_the_smallest_index():
    assert F.mode_row([[0.5, 0.5, 0.0], [0.0, 0.0, 1.0]]).tolist() == [0.5, 0.5, 0.0]   # in-row tie -> 0; 1:1 -> 0
    assert F.mode_row([[0.0, 1.0], [0.0, 1.0], [1.0, 0.0]]).tolist() == [0.0, 1.0]
    assert F.mode_row([]) is None


def test_mode_l4_combines_the_neighbours_mode_rows():
    lone = "BTN|n3|1|1|0|2|0|0|tc0|s4:4|u10|hn|go|ka|e3|o1v1k0"   # e2 cell = PURE (mode action 0 on the tie rule)
    e4 = "BTN|n3|1|1|0|2|0|0|tc0|s4:4|u10|hn|go|ka|e4|o1v1k0"
    table = {**PURE, lone: [0.0, 1.0, 0.0], e4: [0.0, 0.0, 1.0]}
    out = F.measure(table, TOP, l4_neighbor=True, combine="mode")
    l4 = _cell(out, "L4")   # e2 mode row [.85,.15,0] (argmax 0), e4 [0,0,1] (argmax 2): 1:1 -> action 0
    assert l4["n"] == 2   # lone and e4 (whose e3 neighbour is lone) both reach L4
    row = F._neighbor(F.mode_tables(table), lone, 3, TOP, "mode")
    assert row.tolist() == pytest.approx([0.85, 0.15, 0.0])


def test_mean_combine_keeps_the_schema_1_values():
    # Frozen schema 1 output of the table above (main before #660); the new fields are additions only.
    table = {**TABLE, E6: [0.0, 1.0]}
    out = F.measure(table, TOP, l4_neighbor=True)
    old = {k: v for k, v in _cell(out, "L1").items() if k not in ("argmax_agree", "uniform_argmax_agree")}
    assert old == {"n": 3, "tv_mean": 0.5, "tv_p90": 0.75, "uniform_tv_mean": 0.333333, "better_than_uniform": 0.0}
    assert {k: v for k, v in _cell(out, "L4").items() if "argmax" not in k} == {
        "n": 1, "tv_mean": 0.6, "tv_p90": 0.6, "uniform_tv_mean": 0.5, "better_than_uniform": 0.0}
    with pytest.raises(ValueError, match="combine"):
        F.measure(table, TOP, combine="median")
