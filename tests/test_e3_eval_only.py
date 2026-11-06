"""#589: evaluation-only E3 jobs re-measure a finished run's checkpoint with more LBR hands."""
import json

import pytest

from stalker import train_jobs as T
from stalker.e3.mccfr import E3MCCFR
from stalker.jsonio import write_json_gz

EVAL = {"e3-tp-mid-ownavg-w4-eval": "e3-tp-mid-ownavg-w4",
        "e3-tp-mid-ownavg-cap2-w4-eval": "e3-tp-mid-ownavg-cap2-w4",
        "e3-tp-mid-ownavg-cap8-w4-eval": "e3-tp-mid-ownavg-cap8-w4"}


def test_eval_jobs_are_registered_and_match_their_source_job():
    assert T.E3_LBR_HANDS == 1000       # existing jobs keep their LBR size
    for job, src in EVAL.items():
        kw, base = T.JOBS[job].keywords, T.JOBS[src].keywords
        assert job in T.RESUMABLE and kw["eval_of"] == src and kw["lbr_hands"] == 4000
        same = {k: v for k, v in kw.items() if k not in ("name", "eval_of", "lbr_hands")}
        assert same == {k: v for k, v in base.items() if k != "name"}


def test_eval_without_resume_is_refused(tmp_path):
    with pytest.raises(SystemExit, match="resume_run"):
        T.JOBS["e3-tp-mid-ownavg-w4-eval"](1, 1, tmp_path)


def test_eval_reads_the_source_checkpoint_trains_nothing_and_writes_no_table(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    m = E3MCCFR(3, 3, 3, avg_rule="own")
    m.iterate(4)
    write_json_gz(src / "e3-tp-mid-ownavg-w4-seed3.ckpt.json.gz", m.state())
    h0, it0 = m.regret_hash(), m.iterations
    out = tmp_path / "out"
    out.mkdir()
    res = T._e3_tp(7, 3, out, tier="mid", name="e3-tp-mid-ownavg-w4-eval", players=3, resume=src,
                   avg_rule="own", eval_of="e3-tp-mid-ownavg-w4", lbr_hands=12)
    assert res["chunk_iters"] == 0 and res["iters"] == it0 and res["resumed_from"] == it0
    assert res["regret_sha256"] == h0 and res["lbr_hands"] == 12
    assert not list(out.iterdir())
    json.dumps(res)
