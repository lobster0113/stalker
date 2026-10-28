"""Regenerate stalker/tournament/presets/*.json (``python -m stalker.tools.build_presets``)."""
from __future__ import annotations

from pathlib import Path

from stalker.tournament import config as c

OUT = Path(__file__).resolve().parents[1] / "tournament" / "presets"

# (sb, bb) ladder shared by all presets; ante filled per ante_mode.
LADDER = [(25, 50), (50, 100), (75, 150), (100, 200), (150, 300), (200, 400), (300, 600),
          (400, 800), (500, 1000), (700, 1400), (1000, 2000), (1500, 3000), (2000, 4000)]


def levels(ante_mode: str, length: int) -> tuple[c.BlindLevel, ...]:
    out = []
    for i, (sb, bb) in enumerate(LADDER):
        if ante_mode == "none" or i < 3:
            ante = 0
        else:
            ante = bb if ante_mode == "bb_ante" else bb // 8
        out.append(c.BlindLevel(sb, bb, ante, length))
    return tuple(out)


def build() -> dict[str, c.TournamentConfig]:
    def cfg(name, players, table, stack, pay, ante="none", length=10, buy_in=100, short="all_in"):
        return c.TournamentConfig(name=name, players=players, table_size=table, starting_stack=stack,
                                  levels=levels(ante, length), payouts=pay, ante_mode=ante, buy_in=buy_in,
                                  short_stack_rule=short)
    return {
        "6max_sng_wta": cfg("6max SNG winner-take-all", 6, 6, 1500, c.winner_take_all()),
        "6max_sng_topheavy": cfg("6max SNG top-heavy (65/35)", 6, 6, 1500, (0.65, 0.35)),
        "9max_sng_503020": cfg("9max SNG 50/30/20", 9, 9, 1500, (0.5, 0.3, 0.2)),
        "9max_sng_flat": cfg("9max SNG flat top-3", 9, 9, 1500, c.flat(3)),
        "9max_sng_skip": cfg("9max SNG 50/30/20, short stacks skip blinds", 9, 9, 1500, (0.5, 0.3, 0.2),
                             ante="classic", short="skip"),
        "mtt54": cfg("54-player MTT", 54, 9, 5000, c.mtt_payouts(54, 15), ante="classic", length=20),
        "mtt180_bbante": cfg("180-player MTT BB-ante 15% paid", 180, 9, 10000, c.mtt_payouts(180, 15),
                             ante="bb_ante", length=20),
    }


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for key, conf in build().items():
        (OUT / f"{key}.json").write_text(conf.to_json() + "\n", encoding="utf-8")
