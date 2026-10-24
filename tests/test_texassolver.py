import json
import stat

import pytest

from stalker.core.cards import card
from stalker.oracle import texassolver as ts
from stalker.oracle.texassolver import SolveSettings, Spot, StreetSizes, TexasSolverError
from stalker.tools import bench_texassolver

RIVER = Spot("Ks Td 7h 3c 2s", pot=100, effective_stack=100,
             range_oop="KK,TT,77,AQs,QJ,98s", range_ip="KK, AK, KQ, TT, JJ, 99, 65s",
             sizes={("oop", "river"): StreetSizes(bet=(50,)),
                    ("ip", "river"): StreetSizes(bet=(50,), allin=True)})


def combo(text):
    a, b = card(text[:2]), card(text[2:])
    return (max(a, b), min(a, b))


def dump(player=1):
    return {
        "node_type": "action_node", "player": player, "actions": ["CHECK", "BET 50.000000"],
        "strategy": {"actions": ["CHECK", "BET 50.000000"],
                     "strategy": {"KhKd": [0.25, 0.75], "9s8s": [1.0, 0.0]}},
        "childrens": {
            "BET 50.000000": {
                "node_type": "action_node", "player": 0, "actions": ["FOLD", "CALL", "RAISE 200.000000"],
                "strategy": {"actions": ["FOLD", "CALL", "RAISE 200.000000"],
                             "strategy": {"KcKh": [0.0, 0.2, 0.8]}},
            },
        },
    }


def test_build_input_orders_commands_and_strips_range_spaces():
    text = ts.build_input(RIVER, SolveSettings(accuracy=0.3, max_iteration=50, threads=2))
    lines = text.splitlines()
    assert lines[:5] == ["set_pot 100", "set_effective_stack 100", "set_board Ks,Td,7h,3c,2s",
                         "set_range_oop KK,TT,77,AQs,QJ,98s", "set_range_ip KK,AK,KQ,TT,JJ,99,65s"]
    assert "set_bet_sizes ip,river,bet,50" in lines and "set_bet_sizes ip,river,allin" in lines
    assert "set_bet_sizes oop,river,allin" not in lines
    assert lines.index("build_tree") < lines.index("start_solve") < lines.index("dump_result result.json")
    assert "set_accuracy 0.3" in lines and "set_thread_num 2" in lines
    # The console rejects commands with more than one space-separated argument.
    assert all(len(line.split(" ")) <= 2 for line in lines)


@pytest.mark.parametrize("bad", [
    dict(board="Ks Td"), dict(board="Ks Ks 7h"), dict(pot=0),
    dict(sizes={("btn", "river"): StreetSizes(bet=(50,))}), dict(sizes={("ip", "preflop"): StreetSizes()}),
])
def test_build_input_rejects_bad_spots(bad):
    fields = {**RIVER.__dict__, **bad}
    with pytest.raises(ValueError):
        ts.build_input(Spot(**fields), SolveSettings())


def test_street_from_board_size():
    assert RIVER.street() == "river"
    assert Spot("Qs Jh 2h", 10, 95, "AA", "KK").street() == "flop"


def test_parse_root_maps_combos_and_players():
    root = ts.parse_root(dump())
    assert root.player == "oop" and root.actions == ("CHECK", "BET 50.000000")
    assert root.probs[combo("KhKd")] == (0.25, 0.75)
    assert root.action_index("BET") == [1]
    child = ts.parse_root(dump(), ("BET 50.000000",))
    assert child.player == "ip" and child.probs[combo("KcKh")] == (0.0, 0.2, 0.8)


def test_parse_root_errors_name_the_problem():
    with pytest.raises(TexasSolverError, match="not in"):
        ts.parse_root(dump(), ("RAISE 1",))
    bad = dump()
    bad["strategy"]["strategy"]["KhKd"] = [1.0]
    with pytest.raises(TexasSolverError, match="1 probs for 2 actions"):
        ts.parse_root(bad)
    with pytest.raises(TexasSolverError, match="root player"):
        ts.parse_root(dump(player=7))
    with pytest.raises(TexasSolverError, match="action node"):
        ts.parse_root({"node_type": "chance_node"})


def test_parse_log_takes_last_line():
    text = '{"iteration":10,"exploitibility":2.5,"time_ms":5}\n{"iteration":20,"exploitibility":0.4,"time_ms":9}\n'
    assert ts.parse_log(text) == (0.4, 21)
    assert ts.parse_log("") == (None, None)


def test_missing_binary_is_reported(tmp_path):
    assert ts.find_binary(tmp_path) is None
    with pytest.raises(TexasSolverError, match="install_texassolver"):
        ts.solve(RIVER, home=tmp_path)


def fake_install(tmp_path, script):
    (tmp_path / "resources").mkdir()
    exe = tmp_path / "console_solver"
    exe.write_text("#!/bin/sh\n" + script)
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    (tmp_path / "VERSION").write_text("deadbeef\n")
    return tmp_path


def test_solve_plumbing_with_fake_binary(tmp_path):
    home = fake_install(tmp_path, f"""
grep -q '^set_board Ks,Td,7h,3c,2s$' "$2" || exit 3
echo '{{"iteration":30,"exploitibility":0.2,"time_ms":1}}' > tmp_log.txt
echo '{json.dumps(dump())}' > result.json
""")
    r = ts.solve(RIVER, SolveSettings(threads=1), home=home)
    assert r.root.probs[combo("9s8s")] == (1.0, 0.0)
    assert (r.exploitability, r.iterations, r.solver_version) == (0.2, 31, "deadbeef")
    assert r.wall_s >= 0 and r.peak_rss_mb > 0


def test_solve_failure_shows_output_tail(tmp_path):
    home = fake_install(tmp_path, "echo 'board error'; exit 1\n")
    with pytest.raises(TexasSolverError, match="(?s)exit 1.*board error"):
        ts.solve(RIVER, home=home)


def test_solve_timeout(tmp_path):
    home = fake_install(tmp_path, "exec sleep 5\n")
    with pytest.raises(TexasSolverError, match="timeout"):
        ts.solve(RIVER, home=home, timeout=0.2)


def test_bench_without_binary_exits_2(tmp_path, monkeypatch):
    monkeypatch.setenv("STALKER_TEXASSOLVER_HOME", str(tmp_path))
    assert bench_texassolver.main(["--streets", "river"]) == 2
    assert bench_texassolver.make_spot("turn").street() == "turn"


@pytest.mark.slow
@pytest.mark.skipif(ts.find_binary() is None, reason="console_solver not installed (scripts/install_texassolver.sh)")
def test_river_spot_sanity():
    r = ts.solve(RIVER, SolveSettings(accuracy=0.5, max_iteration=200), timeout=600)
    root = r.root
    assert root.player == "oop" and len(root.probs) > 0
    for p in root.probs.values():
        assert sum(p) == pytest.approx(1.0, abs=1e-4)
    # KK is the nut hand on Ks Td 7h 3c 2s (no straight or flush possible): IP never folds it to a bet.
    (bet,) = [a for a in root.actions if a.startswith("BET")]
    facing = ts.parse_root(r.dump, (bet,))
    assert facing.player == "ip"
    fold = facing.action_index("FOLD")[0]
    nut = [p for c, p in facing.probs.items() if c in {combo("KhKd"), combo("KhKc"), combo("KdKc")}]
    assert len(nut) == 3 and max(p[fold] for p in nut) < 0.01
    assert r.exploitability is not None and r.peak_rss_mb > 0
