from pathlib import Path

from stalker.tools import compute_plan as cp

ADR = Path(__file__).resolve().parent.parent / "docs" / "decisions" / "0017-compute-plan-tp-gto.md"


def test_totals_are_the_sums_of_the_rows():
    rows, s = cp.rows(), cp.summary()
    assert len(rows) == 6
    assert abs(s["seed_hours"] - sum(r["seed_hours"] for r in rows)) < 0.15
    assert abs(s["runpod_usd"] - sum(r["runpod_usd"] for r in rows)) < 0.01
    assert s["longest_chain_days"] == max(r["chain_days"] for r in rows)


def test_rows_follow_the_formulas():
    for r in cp.rows():
        assert abs(r["seed_hours"] - r["iters"] / r["it_s"] / 3600 * cp.SEEDS) < 0.1 + 0.01 * r["seed_hours"]
        assert r["pieces"] * r["it_s"] * cp.PIECE_MINUTES * 60 >= r["iters"]
        # A piece must fit the train.yml job.
        assert cp.PIECE_MINUTES < cp.JOB_MINUTES


def test_adr_tables_match_the_module():
    text = ADR.read_text(encoding="utf-8")
    for r in cp.rows():
        it_s = f"{r['it_s']:.2f}".rstrip("0").rstrip(".") if r["it_s"] % 1 else f"{r['it_s']:.1f}"
        cells = f"| {r['iters']:,} | {it_s} | {r['pieces']} | {r['chain_days']:.1f} | {r['seed_hours']:.1f} | {r['runpod_usd']:.2f} |"
        assert cells in text, f"ADR 0017 table row out of date: {cells} (rerun python -m stalker.tools.compute_plan)"
    s = cp.summary()
    assert f"**{s['seed_hours']:.1f}** | **{s['runpod_usd']:.2f}** |" in text
    assert f"{s['free_ci_days_if_perfectly_parallel']:g}일" in text
    assert f"{s['runpod_seed_hours_per_month_at_cap']:,}" in text
