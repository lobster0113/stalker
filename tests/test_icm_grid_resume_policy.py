"""#916: the lambda-selection job reads the F5 policy as the pod sees it: a `resume_run` upload, trimmed to the
launcher's RESUME_FIELDS, gzipped, at `$STALKER_RESUME` = `.../resume.bin` (no `.gz` in the name)."""
import json
import sys
from pathlib import Path

import pytest

from stalker.jsonio import read_json
from tests.test_pod_train_tournament import CLI, PRESET, small_eval  # noqa: F401  (fixture)

ROOT = Path(__file__).parents[1]


def _launcher():
    sys.path.insert(0, str(ROOT / "harness/cloud"))
    import launcher
    return launcher


def test_read_json_tells_gzip_by_its_bytes_not_its_name(tmp_path):
    import gzip

    (tmp_path / "resume.bin").write_bytes(gzip.compress(b'{"a": 1}', mtime=0))
    (tmp_path / "plain.json.gz").write_text('{"b": 2}', encoding="utf-8")   # misnamed plain file
    assert read_json(tmp_path / "resume.bin") == {"a": 1}
    assert read_json(tmp_path / "plain.json.gz") == {"b": 2}


@pytest.mark.slow
def test_icm_grid_plays_a_trimmed_resume_upload_of_a_tournament_pod_result(tmp_path, small_eval):  # noqa: F811
    from stalker.tools import pod_train as P
    from stalker.tools.icm_grid import run_grid

    out = tmp_path / "r.json"
    assert P.main([*CLI, "--out", str(out)]) == 0
    L = _launcher()
    blob = L.resume_payload(out, "43735226442")
    trimmed = read_json_bytes(blob)
    assert set(trimmed) == set(L.RESUME_FIELDS) | {"run_id"}   # the evaluation numbers are dropped; train_env (#923) stays
    resume = tmp_path / "stalker-resume" / "resume.bin"
    resume.parent.mkdir()
    resume.write_bytes(blob)
    grid = run_grid([PRESET], [4], ["even"], games=2, seed=10001, agents=f"policy:{resume}",
                    lambda_grid=[0.0, 0.1])
    (cell,) = grid["cells"]
    pol = cell["policy"]
    assert pol["policy_hits"] > 0 and pol["policy_hits"] + pol["backoffs"] == pol["decisions"]


@pytest.mark.slow
def test_trimmed_tournament_result_resumes_only_under_its_own_train_env(tmp_path, small_eval):  # noqa: F811
    # #923: RESUME_FIELDS dropped train_env, so load_resume_result saw None != {...} and refused every tournament chain
    from stalker.tools import pod_train as P

    out = tmp_path / "r.json"
    assert P.main([*CLI, "--out", str(out)]) == 0
    f = tmp_path / "resume.bin"
    f.write_bytes(_launcher().resume_payload(out, "1"))
    r = json.loads(out.read_text(encoding="utf-8"))
    kw = dict(menu="real", raise_cap=None, ranges="average", avg_rule="own", key_variant="c1",
              stacks="bubble:skewed")
    _, env = P.tournament_env(PRESET, 4, "b", 0, 0.0, "bubble:skewed")
    assert env == r["train_env"]
    _, run_id = P.load_resume_result(f, "mid", 4, train_env=env, **kw)
    assert run_id == "1"
    _, other = P.tournament_env(PRESET, 4, "b", 0, 0.0, "bubble:even")
    with pytest.raises(SystemExit, match="train_env"):
        P.load_resume_result(f, "mid", 4, train_env=other, **kw)


def read_json_bytes(blob):
    import gzip

    return json.loads(gzip.decompress(blob))
