"""Decision record schema v1 (see docs/RECORDS.md).

Records are the output of game generation and the input of typing and RL training, so every field is
plain JSON-able and every record carries `schema_version`. Classes are frozen dataclasses; `to_dict`
and `from_dict` round-trip them, and `from_dict` rejects missing, unknown, or mistyped fields.
"""
from __future__ import annotations

import dataclasses
import math
import re
import types
import typing
from dataclasses import dataclass, field
from typing import Any

SCHEMA_VERSION = 1
MAX_SEATS = 9
PROB_TOL = 1e-6
STREETS = ("preflop", "flop", "turn", "river")
BOARD_SIZE = {"preflop": 0, "flop": 3, "turn": 4, "river": 5}
ANTE_TYPES = ("none", "classic", "bb_ante")
ACTION_KINDS = ("fold", "call", "raise")  # `call` also means check, as in stalker.agents.base
POLICIES = ("ai0", "ai1")
_CARD = re.compile(r"[2-9TJQKA][cdhs]")


class RecordError(ValueError):
    """Raised for a malformed or invalid record; message names the field and how to fix it."""


@dataclass(frozen=True)
class RecordIds:
    """Kept separate on purpose: episode = one RL rollout, game = one tournament run (the memory
    boundary), tournament = the config/series, hand_id unique within a game, decision_id unique
    within a game, player_id = seat-independent index of the player in the game."""

    episode_id: str
    game_id: str
    tournament_id: str
    hand_id: int
    decision_id: int
    player_id: int
    policy_version: str


@dataclass(frozen=True)
class StackSummary:
    """Distribution of all remaining players' stacks in the tournament, in chips."""

    n: int
    total: int
    min: int
    max: int
    mean: float
    median: float

    @classmethod
    def of(cls, stacks: typing.Sequence[int]) -> "StackSummary":
        s = sorted(stacks)
        n = len(s)
        if n == 0:
            raise RecordError("StackSummary.of: no stacks given; pass every remaining player's stack.")
        mid = n // 2
        median = float(s[mid]) if n % 2 else (s[mid - 1] + s[mid]) / 2
        return cls(n=n, total=sum(s), min=s[0], max=s[-1], mean=sum(s) / n, median=median)


@dataclass(frozen=True)
class TournamentContext:
    table_size: int
    sb: int
    bb: int
    ante_type: str
    ante: int
    level: int  # 0-based blind level index
    remaining: int  # players left in the tournament
    paid_places: int
    payout_vector: tuple[float, ...]  # currency per finishing place, 1st first
    next_level: tuple[int, int, int] | None  # (sb, bb, ante), None at the final level
    stacks: StackSummary


@dataclass(frozen=True)
class SeatInfo:
    seat: int
    player_id: int
    stack: int  # chips behind
    bet: int  # chips committed this street
    in_hand: bool


@dataclass(frozen=True)
class ActionOption:
    """One entry of the decision's action space. `amount` is the raise-to total (0 unless raise)."""

    kind: str
    amount: int = 0


@dataclass(frozen=True)
class PublicAction:
    seat: int
    kind: str  # 'f' | 'cc' | 'cbr', as in Hand.actions()
    amount: int


@dataclass(frozen=True)
class TableObservation:
    """What the acting player sees: own hole cards and public information only."""

    seats: tuple[SeatInfo, ...]
    hero_seat: int
    button: int
    position: str  # e.g. BTN, SB, BB, UTG, HJ, CO
    pot: int
    hole_cards: tuple[str, ...]
    board: tuple[str, ...]
    street: str
    current_hand_actions: tuple[PublicAction, ...]
    action_space: tuple[ActionOption, ...]
    legal_action_mask: tuple[bool, ...]  # aligned with action_space


@dataclass(frozen=True)
class MemorySnapshot:
    """In-game memory summary for the memory-on policy. Scalars only: raw logs do not belong here."""

    hands_observed: int
    features: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class PolicySource:
    agent: str  # e.g. "random", "ppo-lstm"
    checkpoint: str | None = None
    meta: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class DecisionRecord:
    ids: RecordIds
    tournament_context: TournamentContext
    table_observation: TableObservation
    session_memory_snapshot: MemorySnapshot | None
    probs_ai0: tuple[float, ...]  # memory off; aligned with action_space
    probs_ai1: tuple[float, ...] | None  # memory on; None until a memory model exists
    acting_policy: str  # which of the two produced chosen_action
    chosen_action: int  # index into action_space
    action_logprob: float  # log of the acting policy's probability of chosen_action
    action_values: tuple[float, ...] | None  # optional per-action value estimates
    policy_source: PolicySource
    schema_version: int = SCHEMA_VERSION


@dataclass(frozen=True)
class PlayerHandOutcome:
    player_id: int
    seat: int
    start_stack: int
    final_stack: int
    delta: int


@dataclass(frozen=True)
class HandRecord:
    """Per-hand outcome. Chip deltas are shaping data only; the reward lives in GameRecord."""

    episode_id: str
    game_id: str
    tournament_id: str
    hand_id: int
    table_id: int
    players: tuple[PlayerHandOutcome, ...]
    busted: tuple[int, ...]  # player_ids eliminated in this hand
    terminal_flag: bool  # True when this hand ended the game
    schema_version: int = SCHEMA_VERSION


@dataclass(frozen=True)
class GameRecord:
    episode_id: str
    game_id: str
    tournament_id: str
    buy_in: float
    ranks: tuple[int, ...]  # by player_id, 1 = winner
    prizes: tuple[float, ...]  # by player_id
    rewards: tuple[float, ...]  # by player_id: prize - buy_in
    hands: int
    terminal_flag: bool = True
    schema_version: int = SCHEMA_VERSION

    @classmethod
    def from_result(cls, result: Any, buy_in: float, episode_id: str) -> "GameRecord":
        """Build from a `stalker.tournament.director.GameResult`."""
        return cls(episode_id=episode_id, game_id=result.game_id, tournament_id=result.tournament_id,
                   buy_in=float(buy_in), ranks=tuple(result.ranks), prizes=tuple(float(p) for p in result.prizes),
                   rewards=tuple(float(p) - float(buy_in) for p in result.prizes), hands=result.hands)


Record = DecisionRecord | HandRecord | GameRecord
RECORD_TYPES: dict[str, type] = {"decision": DecisionRecord, "hand": HandRecord, "game": GameRecord}


# ---------------------------------------------------------------- (de)serialisation

def to_dict(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj):
        return {f.name: to_dict(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, (tuple, list)):
        return [to_dict(x) for x in obj]
    if isinstance(obj, dict):
        return {k: to_dict(v) for k, v in obj.items()}
    return obj


def from_dict(cls: type, data: Any, path: str | None = None) -> Any:
    """Build `cls` from JSON data, checking field presence and types recursively."""
    return _convert(cls, data, path or cls.__name__)


def _convert(tp: Any, v: Any, path: str) -> Any:
    origin = typing.get_origin(tp)
    if origin in (types.UnionType, typing.Union):
        args = typing.get_args(tp)
        if v is None:
            if type(None) in args:
                return None
            raise RecordError(f"{path}: is null but required; provide a value.")
        (inner,) = [a for a in args if a is not type(None)]
        return _convert(inner, v, path)
    if dataclasses.is_dataclass(tp):
        if not isinstance(v, dict):
            raise RecordError(f"{path}: expected an object, got {type(v).__name__}.")
        hints = typing.get_type_hints(tp)
        fields = {f.name: f for f in dataclasses.fields(tp)}
        unknown = sorted(set(v) - set(fields))
        if unknown:
            raise RecordError(f"{path}: unknown field(s) {unknown}; remove them or bump schema_version.")
        kwargs = {}
        for name, f in fields.items():
            if name not in v:
                if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING:
                    raise RecordError(f"{path}.{name}: required field is missing.")
                continue
            kwargs[name] = _convert(hints[name], v[name], f"{path}.{name}")
        return tp(**kwargs)
    if origin is tuple:
        if not isinstance(v, (list, tuple)):
            raise RecordError(f"{path}: expected a list, got {type(v).__name__}.")
        args = typing.get_args(tp)
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_convert(args[0], x, f"{path}[{i}]") for i, x in enumerate(v))
        if len(v) != len(args):
            raise RecordError(f"{path}: expected {len(args)} items, got {len(v)}.")
        return tuple(_convert(a, x, f"{path}[{i}]") for i, (a, x) in enumerate(zip(args, v)))
    if origin is dict:
        if not isinstance(v, dict):
            raise RecordError(f"{path}: expected an object, got {type(v).__name__}.")
        _, vt = typing.get_args(tp)
        return {str(k): _convert(vt, x, f"{path}.{k}") for k, x in v.items()}
    if tp is Any:
        return v
    if tp is bool:
        if not isinstance(v, bool):
            raise RecordError(f"{path}: expected a bool, got {v!r}.")
        return v
    if tp is int:
        if isinstance(v, bool) or not isinstance(v, int):
            raise RecordError(f"{path}: expected an integer, got {v!r} (chips and ids are integers).")
        return v
    if tp is float:
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise RecordError(f"{path}: expected a number, got {v!r}.")
        return float(v)
    if tp is str:
        if not isinstance(v, str):
            raise RecordError(f"{path}: expected a string, got {v!r}.")
        return v
    raise TypeError(f"{path}: unsupported annotation {tp!r}")


# ---------------------------------------------------------------- validation

def validate(record: Record, hole_cards: dict[int, typing.Sequence[str]] | None = None) -> list[str]:
    """Return every rule violation (empty = valid). For decisions, `hole_cards` (seat -> true hole
    cards of every player at the table) enables an exact leak check against the real deal."""
    if isinstance(record, DecisionRecord):
        return _validate_decision(record, hole_cards)
    if isinstance(record, HandRecord):
        return _validate_hand(record)
    if isinstance(record, GameRecord):
        return _validate_game(record)
    return [f"unknown record type {type(record).__name__}"]


def ensure_valid(record: Record, hole_cards: dict[int, typing.Sequence[str]] | None = None) -> None:
    errors = validate(record, hole_cards)
    if errors:
        raise RecordError("invalid record: " + "; ".join(errors))


def _validate_decision(r: DecisionRecord, hole_cards: dict[int, typing.Sequence[str]] | None) -> list[str]:
    e: list[str] = []
    if r.schema_version != SCHEMA_VERSION:
        e.append(f"schema_version={r.schema_version}: expected {SCHEMA_VERSION}")
    tc, ob = r.tournament_context, r.table_observation
    if tc.ante_type not in ANTE_TYPES:
        e.append(f"tournament_context.ante_type={tc.ante_type!r}: must be one of {ANTE_TYPES}")
    if not 2 <= tc.table_size <= MAX_SEATS:
        e.append(f"tournament_context.table_size={tc.table_size}: must be 2..{MAX_SEATS}")
    if len(tc.payout_vector) != tc.paid_places:
        e.append(f"payout_vector has {len(tc.payout_vector)} entries but paid_places={tc.paid_places}")
    if not 1 <= len(ob.seats) <= min(tc.table_size, MAX_SEATS):
        e.append(f"table_observation.seats has {len(ob.seats)} entries: must be 1..{min(tc.table_size, MAX_SEATS)}")
    seat_nums = [s.seat for s in ob.seats]
    if len(set(seat_nums)) != len(seat_nums):
        e.append("table_observation.seats: duplicate seat numbers")
    hero = [s for s in ob.seats if s.seat == ob.hero_seat]
    if not hero:
        e.append(f"hero_seat={ob.hero_seat} is not in table_observation.seats")
    elif hero[0].player_id != r.ids.player_id:
        e.append(f"hero seat holds player {hero[0].player_id} but ids.player_id={r.ids.player_id}")
    if any(s.stack < 0 or s.bet < 0 for s in ob.seats) or ob.pot < 0:
        e.append("stacks, bets and pot must be >= 0")
    if ob.street not in STREETS:
        e.append(f"street={ob.street!r}: must be one of {STREETS}")
    elif len(ob.board) != BOARD_SIZE[ob.street]:
        e.append(f"board has {len(ob.board)} cards but street={ob.street} needs {BOARD_SIZE[ob.street]}")
    if len(ob.hole_cards) != 2:
        e.append(f"hole_cards has {len(ob.hole_cards)} cards: NLHE needs exactly 2")
    for c in (*ob.hole_cards, *ob.board):
        if not _CARD.fullmatch(c):
            e.append(f"card {c!r} is not like 'As'")
    if len(set(ob.hole_cards) | set(ob.board)) != len(ob.hole_cards) + len(ob.board):
        e.append("a card appears twice among hole_cards and board")
    e += _leak_errors(r, hole_cards)

    n = len(ob.action_space)
    if n == 0:
        e.append("action_space is empty")
    for a in ob.action_space:
        if a.kind not in ACTION_KINDS:
            e.append(f"action kind {a.kind!r}: must be one of {ACTION_KINDS}")
    if len(ob.legal_action_mask) != n:
        e.append(f"legal_action_mask has {len(ob.legal_action_mask)} entries, action_space has {n}")
    for name in ("probs_ai0", "probs_ai1", "action_values"):
        v = getattr(r, name)
        if v is not None and len(v) != n:
            e.append(f"{name} has {len(v)} entries, action_space has {n}")
    for name in ("probs_ai0", "probs_ai1"):
        p = getattr(r, name)
        if p is None:
            continue
        if any(not math.isfinite(x) or x < 0 for x in p):
            e.append(f"{name}: probabilities must be finite and >= 0")
        elif abs(sum(p) - 1.0) > PROB_TOL:
            e.append(f"{name} sums to {sum(p):.9f}: must be 1 within {PROB_TOL}")
    if r.acting_policy not in POLICIES:
        e.append(f"acting_policy={r.acting_policy!r}: must be one of {POLICIES}")
    elif r.acting_policy == "ai1" and r.probs_ai1 is None:
        e.append("acting_policy='ai1' but probs_ai1 is null")
    if not 0 <= r.chosen_action < n:
        e.append(f"chosen_action={r.chosen_action}: must index action_space (0..{n - 1})")
    elif len(ob.legal_action_mask) == n:
        if not ob.legal_action_mask[r.chosen_action]:
            e.append(f"chosen_action={r.chosen_action} ({ob.action_space[r.chosen_action]}) is not legal")
        acting = r.probs_ai1 if r.acting_policy == "ai1" else r.probs_ai0
        if acting is not None and len(acting) == n and r.acting_policy in POLICIES:
            p = acting[r.chosen_action]
            if p <= 0:
                e.append(f"chosen_action has probability {p} under {r.acting_policy}")
            elif abs(math.log(p) - r.action_logprob) > PROB_TOL:
                e.append(f"action_logprob={r.action_logprob} but log({r.acting_policy}[chosen])={math.log(p)}")
    m = r.session_memory_snapshot
    if m is not None and any(not math.isfinite(x) for x in m.features.values()):
        e.append("session_memory_snapshot.features must be finite numbers")
    return e


def _cards_in(obj: Any) -> list[str]:
    if isinstance(obj, str):
        return [obj] if _CARD.fullmatch(obj) else []
    if isinstance(obj, dict):
        return [c for k, v in obj.items() for c in (*_cards_in(k), *_cards_in(v))]
    if isinstance(obj, (list, tuple)):
        return [c for x in obj for c in _cards_in(x)]
    return []


def _leak_errors(r: DecisionRecord, hole_cards: dict[int, typing.Sequence[str]] | None) -> list[str]:
    ob = r.table_observation
    visible = set(ob.hole_cards) | set(ob.board)
    obs = to_dict(ob)
    obs.pop("hole_cards")
    obs.pop("board")
    stray = [c for c in _cards_in([obs, to_dict(r.session_memory_snapshot)]) if c not in visible]
    e = [f"observation contains card(s) {sorted(set(stray))} outside own hole cards and board"] if stray else []
    if hole_cards is not None:
        others = {c for seat, cs in hole_cards.items() if seat != ob.hero_seat for c in cs}
        leaked = sorted(others & set(_cards_in([to_dict(ob), to_dict(r.session_memory_snapshot)])))
        if leaked:
            e.append(f"observation contains other players' hole cards {leaked}")
        own = tuple(hole_cards.get(ob.hero_seat, ()))
        if own and set(own) != set(ob.hole_cards):
            e.append(f"hole_cards {list(ob.hole_cards)} differ from the dealt cards {list(own)}")
    return e


def _validate_hand(r: HandRecord) -> list[str]:
    e: list[str] = []
    if r.schema_version != SCHEMA_VERSION:
        e.append(f"schema_version={r.schema_version}: expected {SCHEMA_VERSION}")
    if not r.players:
        e.append("players is empty")
    for p in r.players:
        if p.final_stack - p.start_stack != p.delta:
            e.append(f"player {p.player_id}: delta {p.delta} != final_stack - start_stack")
        if p.final_stack < 0 or p.start_stack <= 0:
            e.append(f"player {p.player_id}: start_stack must be > 0 and final_stack >= 0")
    if sum(p.delta for p in r.players) != 0:
        e.append(f"chip deltas sum to {sum(p.delta for p in r.players)}: chips must be conserved")
    zero = {p.player_id for p in r.players if p.final_stack == 0}
    if set(r.busted) != zero:
        e.append(f"busted={sorted(r.busted)} but players with 0 chips are {sorted(zero)}")
    return e


def _validate_game(r: GameRecord) -> list[str]:
    e: list[str] = []
    if r.schema_version != SCHEMA_VERSION:
        e.append(f"schema_version={r.schema_version}: expected {SCHEMA_VERSION}")
    n = len(r.ranks)
    if not (len(r.prizes) == len(r.rewards) == n):
        e.append("ranks, prizes and rewards must have one entry per player")
    elif sorted(r.ranks) != list(range(1, n + 1)):
        e.append(f"ranks must be a permutation of 1..{n}")
    for i, (prize, reward) in enumerate(zip(r.prizes, r.rewards)):
        if abs(reward - (prize - r.buy_in)) > 1e-9:
            e.append(f"player {i}: reward {reward} != prize {prize} - buy_in {r.buy_in}")
    if not r.terminal_flag:
        e.append("GameRecord.terminal_flag must be True")
    return e

