import json

from stalker.tools import it_ratio as R


def test_common_cpu_ratio():
    a = {"iters_per_s_mean": 3.0, "iters_per_s_by_seed": [2.0, 4.0, 3.0], "cpu_model_by_seed": ["x", "y", "x"]}
    b = {"iters_per_s_mean": 6.0, "iters_per_s_by_seed": [6.0, 6.0], "cpu_model_by_seed": ["x", "z"]}
    r = R.compare(a, b)
    assert r["overall"]["ratio"] == 0.5
    assert r["common_cpu"] and r["by_cpu"] == {"x": {"a": 2.5, "b": 6.0, "ratio": 0.417}}


def test_no_common_cpu_and_old_format(tmp_path, capsys):
    a = {"iters_per_s_mean": 3.0, "iters_per_s_by_seed": [3.0], "cpu_model_by_seed": ["x"]}
    b = {"iters_per_s_mean": 6.0}
    assert R.compare(a, b)["common_cpu"] is False
    pa, pb = tmp_path / "a.json", tmp_path / "b.json"
    pa.write_text(json.dumps(a)); pb.write_text(json.dumps(b))
    assert R.main([str(pa), str(pb)]) == 0
    assert "no common CPU" in capsys.readouterr().out
    R.main([str(pa), str(pb), "--json"])
    assert json.loads(capsys.readouterr().out)["overall"]["ratio"] == 0.5
