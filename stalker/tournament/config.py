"""Tournament configuration schema, payout generators, and presets.

Conventions (kept explicit because downstream engine code depends on them):
- Chips are integers. Payout *amounts* are integer chips-of-currency too.
- ``hand_no`` is 1-based: hand 1 is the first hand of level 0.
- Past the final level the final level keeps applying.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from importlib import resources
from pathlib import Path

SCHEMA_VERSION = 1
ANTE_MODES = ("none", "classic", "bb_ante")
LENGTH_UNITS = ("hands", "minutes")
SHORT_STACK_RULES = ("all_in", "skip")
PAYOUT_MODES = ("ratio", "amount")
_EPS = 1e-9


class ConfigError(ValueError):
    """Raised for an invalid tournament configuration; message says how to fix it."""


@dataclass(frozen=True)
class BlindLevel:
    sb: int
    bb: int
    ante: int
    length: int  # in TournamentConfig.length_unit


@dataclass(frozen=True)
class TournamentConfig:
    name: str
    players: int
    table_size: int
    starting_stack: int
    levels: tuple[BlindLevel, ...]
    payouts: tuple[float, ...]
    payout_mode: str = "ratio"
    ante_mode: str = "none"
    length_unit: str = "hands"
    # all_in: a player who cannot cover a blind/ante posts the remainder and is all-in.
    # skip: a player who cannot cover the big blind is skipped for the blind that orbit.
    short_stack_rule: str = "all_in"
    buy_in: int = 0
    schema_version: int = field(default=SCHEMA_VERSION)

    def __post_init__(self) -> None:
        object.__setattr__(self, "levels", tuple(self.levels))
        object.__setattr__(self, "payouts", tuple(self.payouts))
        self.validate()

    # ---- validation ----
    def validate(self) -> None:
        _require_int("players", self.players)
        _require_int("table_size", self.table_size)
        _require_int("starting_stack", self.starting_stack)
        _require_int("buy_in", self.buy_in)
        if self.players < 2:
            raise ConfigError(f"players={self.players}: need at least 2 players.")
        if not 2 <= self.table_size <= 10:
            raise ConfigError(f"table_size={self.table_size}: must be between 2 and 10.")
        if self.starting_stack <= 0:
            raise ConfigError(f"starting_stack={self.starting_stack}: must be a positive integer.")
        if self.buy_in < 0:
            raise ConfigError(f"buy_in={self.buy_in}: must be >= 0.")
        for attr, allowed in (("ante_mode", ANTE_MODES), ("length_unit", LENGTH_UNITS),
                              ("short_stack_rule", SHORT_STACK_RULES), ("payout_mode", PAYOUT_MODES)):
            if getattr(self, attr) not in allowed:
                raise ConfigError(f"{attr}={getattr(self, attr)!r}: must be one of {allowed}.")
        self._validate_levels()
        self._validate_payouts()

    def _validate_levels(self) -> None:
        if not self.levels:
            raise ConfigError("levels is empty: define at least one blind level.")
        prev = None
        for i, lv in enumerate(self.levels):
            for attr in ("sb", "bb", "ante", "length"):
                _require_int(f"levels[{i}].{attr}", getattr(lv, attr))
            if lv.sb <= 0 or lv.bb <= 0 or lv.length <= 0:
                raise ConfigError(f"levels[{i}]: sb, bb and length must be positive.")
            if lv.sb > lv.bb:
                raise ConfigError(f"levels[{i}]: sb={lv.sb} exceeds bb={lv.bb}.")
            if lv.ante < 0:
                raise ConfigError(f"levels[{i}]: ante must be >= 0.")
            if self.ante_mode == "none" and lv.ante != 0:
                raise ConfigError(f"levels[{i}]: ante={lv.ante} but ante_mode='none'; "
                                  "set ante to 0 or choose 'classic'/'bb_ante'.")
            if prev is not None and (lv.bb < prev.bb or lv.sb < prev.sb or lv.ante < prev.ante
                                     or (lv.bb, lv.sb, lv.ante) == (prev.bb, prev.sb, prev.ante)):
                raise ConfigError(f"levels[{i}]: blinds must increase monotonically "
                                  f"(strictly in at least one of sb/bb/ante, never decrease); "
                                  f"got {lv} after {prev}.")
            prev = lv

    def _validate_payouts(self) -> None:
        if not self.payouts:
            raise ConfigError("payouts is empty: pay at least first place.")
        if len(self.payouts) > self.players:
            raise ConfigError(f"{len(self.payouts)} paid places exceed players={self.players}.")
        if any(p < 0 for p in self.payouts):
            raise ConfigError("payouts must be non-negative.")
        if any(a < b - _EPS for a, b in zip(self.payouts, self.payouts[1:])):
            raise ConfigError("payouts must be non-increasing by finishing place.")
        if self.payout_mode == "ratio":
            total = sum(self.payouts)
            if abs(total - 1.0) > _EPS:
                raise ConfigError(f"ratio payouts sum to {total:.12g}, must be 1; "
                                  "use payout_mode='amount' or normalise.")
        else:
            for i, p in enumerate(self.payouts):
                if float(p) != int(p):
                    raise ConfigError(f"payouts[{i}]={p}: amounts must be integers.")

    # ---- derived ----
    @property
    def prize_pool(self) -> int:
        """Total prize money: buy_in * players for ratio mode, the sum of amounts otherwise."""
        if self.payout_mode == "amount":
            return int(sum(self.payouts))
        return self.buy_in * self.players

    def payout_amounts(self) -> tuple[float, ...]:
        if self.payout_mode == "amount":
            return self.payouts
        return tuple(r * self.prize_pool for r in self.payouts)

    def payout_ratios(self) -> tuple[float, ...]:
        if self.payout_mode == "ratio":
            return self.payouts
        total = sum(self.payouts)
        return tuple(p / total for p in self.payouts)

    # ---- level lookup ----
    def level_index_at(self, t: int) -> int:
        """Level index at time ``t`` (hand_no for 'hands', elapsed minutes from 0 for 'minutes')."""
        if t < 0:
            raise ValueError(f"t={t}: must be >= 0.")
        start = 0
        for i, lv in enumerate(self.levels):
            start += lv.length
            if t < start:
                return i
        return len(self.levels) - 1

    def _t_from_hand(self, hand_no: int) -> int:
        if self.length_unit != "hands":
            raise ValueError("length_unit is 'minutes': use level_index_at(elapsed_minutes).")
        if hand_no < 1:
            raise ValueError(f"hand_no={hand_no}: hands are numbered from 1.")
        return hand_no - 1

    def level_at(self, hand_no: int) -> BlindLevel:
        return self.levels[self.level_index_at(self._t_from_hand(hand_no))]

    def next_level(self, hand_no: int) -> BlindLevel | None:
        """Next level after the one in force at ``hand_no``; None at the final level."""
        i = self.level_index_at(self._t_from_hand(hand_no))
        return self.levels[i + 1] if i + 1 < len(self.levels) else None

    def hands_left_in_level(self, hand_no: int) -> int | None:
        """Hands remaining in the current level including ``hand_no``; None at the final level."""
        t = self._t_from_hand(hand_no)
        i = self.level_index_at(t)
        if i == len(self.levels) - 1:
            return None
        return sum(lv.length for lv in self.levels[: i + 1]) - t

    # ---- serialization ----
    def to_dict(self) -> dict:
        d = asdict(self)
        d["levels"] = [asdict(lv) for lv in self.levels]
        d["payouts"] = list(self.payouts)
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, d: dict) -> "TournamentConfig":
        d = dict(d)
        version = d.pop("schema_version", SCHEMA_VERSION)
        if version != SCHEMA_VERSION:
            raise ConfigError(f"schema_version={version}: only {SCHEMA_VERSION} is supported; migrate the file.")
        try:
            d["levels"] = tuple(BlindLevel(**lv) for lv in d["levels"])
            d["payouts"] = tuple(d["payouts"])
            return cls(**d)
        except (KeyError, TypeError) as e:
            raise ConfigError(f"malformed config: {e!r}") from e

    @classmethod
    def from_json(cls, text: str) -> "TournamentConfig":
        return cls.from_dict(json.loads(text))


def _require_int(name: str, v: object) -> None:
    if isinstance(v, bool) or not isinstance(v, int):
        raise ConfigError(f"{name}={v!r}: chips and counts must be integers.")


# ---- payout generators (ratios summing to 1) ----
def _normalise(weights: list[float]) -> tuple[float, ...]:
    total = sum(weights)
    return tuple(w / total for w in weights)


def winner_take_all() -> tuple[float, ...]:
    return (1.0,)


def flat(paid: int) -> tuple[float, ...]:
    if paid < 1:
        raise ConfigError(f"paid={paid}: must be >= 1.")
    return _normalise([1.0] * paid)


def top_heavy(paid: int, ratio: float = 2.0) -> tuple[float, ...]:
    """Geometric payouts: each place pays ``1/ratio`` of the place above."""
    if paid < 1:
        raise ConfigError(f"paid={paid}: must be >= 1.")
    if ratio < 1:
        raise ConfigError(f"ratio={ratio}: must be >= 1.")
    return _normalise([ratio ** -i for i in range(paid)])


def mtt_payouts(players: int, paid_pct: float, alpha: float = 0.8) -> tuple[float, ...]:
    """MTT-style curve: pay ``paid_pct``% of the field (at least 1), place k weighted k**-alpha."""
    if not 0 < paid_pct <= 100:
        raise ConfigError(f"paid_pct={paid_pct}: must be in (0, 100].")
    paid = min(players, max(1, round(players * paid_pct / 100)))
    return _normalise([(k + 1) ** -alpha for k in range(paid)])


# ---- presets ----
def preset_names() -> list[str]:
    root = resources.files("stalker.tournament") / "presets"
    return sorted(p.name[:-5] for p in root.iterdir() if p.name.endswith(".json"))


def load_preset(name: str) -> TournamentConfig:
    path = resources.files("stalker.tournament") / "presets" / f"{name}.json"
    if not path.is_file():
        raise ConfigError(f"unknown preset {name!r}; available: {preset_names()}.")
    return TournamentConfig.from_json(path.read_text(encoding="utf-8"))


def load_config(path: str | Path) -> TournamentConfig:
    return TournamentConfig.from_json(Path(path).read_text(encoding="utf-8"))
