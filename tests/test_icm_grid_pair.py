import json

import pytest

from stalker.tools import icm_grid
from stalker.tools.icm_grid_pair import SCHEMA, bundle, main


def _grid(tmp_path, name, agents):
    out = tmp_path / f"{name}.json"
    icm_grid.main(["--presets", "9max_sng_503020", "--remaining", "2", "--profiles", "even", "--games", "3",
                   "--seed", "1", "--agents", agents, "--lambda-grid", "--out", str(out)])
    return out


def test_pair_embeds_each_original_output_unchanged(tmp_path):
    r, t = _grid(tmp_path, "r", "random"), _grid(tmp_path, "t", "persona:tag")
    out = tmp_path / "pair.json"
    assert main(["--out", str(out), f"random={r}", f"tag={t}"]) == 0
    d = json.loads(out.read_text(encoding="utf-8"))
    assert (d["schema"], d["schema_version"]) == (SCHEMA, 1)
    assert set(d["agents"]) == {"random", "tag"}
    assert d["agents"]["random"] == json.loads(r.read_text(encoding="utf-8"))
    assert d["agents"]["tag"]["selected_lambda"] in d["agents"]["tag"]["lambda_grid"]


def test_grid_without_lambda_grid_is_rejected(tmp_path):
    plain = tmp_path / "p.json"
    icm_grid.main(["--presets", "9max_sng_503020", "--remaining", "2", "--profiles", "even", "--games", "2",
                   "--out", str(plain)])
    with pytest.raises(ValueError, match="--lambda-grid"):
        bundle({"random": plain})
