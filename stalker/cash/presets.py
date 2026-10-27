"""Cash presets (plan §2.4, SIM-b): heads-up, 6-max and 9-max at 40/100/200 BB, blinds 1/2.

Buy-in is fixed at the preset depth (min = max = depth), so every re-buy and auto top-up restores that depth.
"""
from __future__ import annotations

from dataclasses import replace

from stalker.cash.session import CashConfig

SB, BB = 1, 2
DEFAULT_HANDS = 1000
TABLES = {"hu": 2, "6max": 6, "9max": 9}
DEPTHS_BB = (40, 100, 200)

PRESETS: dict[str, CashConfig] = {
    f"cash_{table}_{depth}bb": CashConfig(f"cash_{table}_{depth}bb", seats, SB, BB, depth * BB, DEFAULT_HANDS)
    for table, seats in TABLES.items() for depth in DEPTHS_BB
}


def preset(name: str, **overrides) -> CashConfig:
    """A preset by name, optionally with fields replaced (e.g. hands=, auto_topup=)."""
    if name not in PRESETS:
        raise KeyError(f"unknown cash preset {name!r}; choose from {sorted(PRESETS)}")
    return replace(PRESETS[name], **overrides)
