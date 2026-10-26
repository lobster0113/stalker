"""EnvSpec and env_id: one exact identifier per training/judging environment (plan §2.6).

`env_id` = first 16 hex chars of sha256 over the canonical JSON (sorted keys, no spaces), so field
order never matters and any field change gives a new id. `register` stores the JSON under
`stalker/env/registry/<env_id>.json` so an id can always be traced back to its full spec.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

REGISTRY_DIR = Path(__file__).resolve().parent / "registry"
KINDS = ("cash", "sng", "mtt", "hu_pushfold")
RULES_VERSION = "nlhe-1"
RNG_SCHEMA_VERSION = 1


class EnvSpecError(ValueError):
    pass


def _is_int(x) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


@dataclass(frozen=True)
class EnvSpec:
    kind: str
    rules_version: str
    table_size: int
    field_size: int
    initial_stacks: tuple[int, ...]           # chips, per entrant (or per seat for cash)
    blind_schedule: tuple[tuple[int, int, int], ...]  # (sb, bb, length) per level
    ante_schedule: tuple[int, ...]            # ante per level, aligned with blind_schedule
    payout_vector: tuple[float, ...]          # per place, 1st first; empty for cash
    payout_mode: str                          # "ratio" | "amount" | "none"
    reentry_rule: str                         # "none" in v1
    rake: int                                 # chips; cash v1 = 0
    time_model: str                           # "hands" | "minutes"
    rng_schema_version: int
    ante_mode: str = "none"  # TournamentConfig ante modes, or "dead" (posted from outside the stacks)

    def __post_init__(self) -> None:
        def fail(msg: str) -> None:
            raise EnvSpecError(f"EnvSpec: {msg}")
        if self.kind not in KINDS:
            fail(f"kind {self.kind!r}; use one of {KINDS}")
        for name in ("table_size", "field_size", "rake", "rng_schema_version"):
            if not _is_int(getattr(self, name)):
                fail(f"{name} must be an integer (chips and counts are integers)")
        if not 2 <= self.table_size <= 9 or self.field_size < 2:
            fail("table_size must be 2..9 and field_size >= 2")
        if not self.initial_stacks or any(not _is_int(s) or s <= 0 for s in self.initial_stacks):
            fail("initial_stacks must be positive integers; give one stack per entrant")
        if not self.blind_schedule:
            fail("blind_schedule is empty; give at least one (sb, bb, length) level")
        for lv in self.blind_schedule:
            if len(lv) != 3 or not all(_is_int(x) for x in lv) or not 0 < lv[0] <= lv[1] or lv[2] <= 0:
                fail(f"blind level {lv}: need integers 0 < sb <= bb and length > 0")
        if len(self.ante_schedule) != len(self.blind_schedule) or any(not _is_int(a) or a < 0
                                                                       for a in self.ante_schedule):
            fail("ante_schedule needs one non-negative integer ante (chips) per blind level")
        if self.rake < 0:
            fail("rake must be >= 0")

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, text: str) -> "EnvSpec":
        d = json.loads(text)
        try:
            d["initial_stacks"] = tuple(d["initial_stacks"])
            d["blind_schedule"] = tuple(tuple(x) for x in d["blind_schedule"])
            d["ante_schedule"] = tuple(d["ante_schedule"])
            d["payout_vector"] = tuple(d["payout_vector"])
            return cls(**d)
        except (KeyError, TypeError) as e:
            raise EnvSpecError(f"EnvSpec JSON: {e}; it must hold every EnvSpec field") from None

    @property
    def env_id(self) -> str:
        return hashlib.sha256(self.to_json().encode("utf-8")).hexdigest()[:16]


def register(spec: EnvSpec, directory: Path = REGISTRY_DIR) -> str:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{spec.env_id}.json"
    if not path.exists():
        path.write_text(spec.to_json() + "\n", encoding="utf-8")
    return spec.env_id


def lookup(env_id: str, directory: Path = REGISTRY_DIR) -> EnvSpec:
    path = directory / f"{env_id}.json"
    if not path.exists():
        raise EnvSpecError(f"env_id {env_id} is not registered under {directory}; call register(spec) when "
                           "the environment is created")
    spec = EnvSpec.from_json(path.read_text(encoding="utf-8"))
    if spec.env_id != env_id:
        raise EnvSpecError(f"{path.name} holds a spec whose id is {spec.env_id}; the registry file was edited")
    return spec


def from_tournament(cfg) -> EnvSpec:
    """EnvSpec of a `stalker.tournament.config.TournamentConfig` (presets included)."""
    kind = "sng" if cfg.players <= cfg.table_size else "mtt"
    return EnvSpec(
        kind=kind, rules_version=RULES_VERSION, table_size=cfg.table_size, field_size=cfg.players,
        initial_stacks=(cfg.starting_stack,) * cfg.players,
        blind_schedule=tuple((lv.sb, lv.bb, lv.length) for lv in cfg.levels),
        ante_schedule=tuple(lv.ante for lv in cfg.levels), payout_vector=tuple(float(x) for x in cfg.payouts),
        payout_mode=cfg.payout_mode, reentry_rule="none", rake=0, time_model=cfg.length_unit,
        rng_schema_version=RNG_SCHEMA_VERSION, ante_mode=cfg.ante_mode)


def pushfold(stack_bb: float, ante_bb: float, bb: int = 100) -> EnvSpec:
    """E1 heads-up push/fold (`referee.anchors.pushfold`): chips in units of bb/100.

    The anchor's ante is dead money that comes from neither stack (the BB loses it with the pot),
    unlike a `bb_ante` posted from the stack, so its ante mode is "dead".
    """
    stack = int(round(stack_bb * bb))
    ante = int(round(ante_bb * bb))
    return EnvSpec(
        kind="hu_pushfold", rules_version=RULES_VERSION, table_size=2, field_size=2, initial_stacks=(stack, stack),
        blind_schedule=((bb // 2, bb, 1),), ante_schedule=(ante,), payout_vector=(), payout_mode="none",
        reentry_rule="none", rake=0, time_model="hands", rng_schema_version=RNG_SCHEMA_VERSION,
        ante_mode="dead" if ante else "none")


def register_known() -> list[str]:
    """Register every tournament preset and every point of the push/fold anchor grid."""
    from referee.anchors import pushfold as anchor
    from stalker.tournament.config import load_preset, preset_names

    ids = [register(from_tournament(load_preset(n))) for n in preset_names()]
    ids += [register(pushfold(s, a)) for s in anchor.STACKS for a in anchor.ANTES]
    return ids


if __name__ == "__main__":
    for i in register_known():
        print(i)
