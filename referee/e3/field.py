"""E3 duplicate field evaluation (6-max; 2-5 players from #534): "max loss vs opponent set" (#295, referee/GATES.md Gate Q, ADR 0015).

One target policy sits with five opponents from a pre-registered configuration (`field_v2.json`,
recorded with its sha256; `field_v1.json` is kept for older results). Short-handed tables (2-5
players, #534) come from `field_v3.json`, one configuration set per player count, played the same way. Duplicate: every deal is
played once per seat rotation - the target takes each seat's cards in turn and the opponents fill
the other seats in their listed order, starting after the target - with the same action random stream in every rotation. When every seat plays the
same policy the hand is identical in all rotations, so the target collects each seat's payoff once
and the deal sums to zero exactly (the symmetry check). The CI resamples whole deals
(`referee.stats.bootstrap_ci`; a deal is the cluster of its rotations).

Opponent kinds: a persona name (`stalker.e3.personas`), "uniform" (uniform over the legal actions),
"self" (the target policy), "champion:<name>" (an archived served policy, `champions/champions_v1.json`,
pinned by sha256, #413). A TP-key policy (the target dict, as trained by `stalker.e3.mccfr`, or a
champion) is read the way it was trained: its public ranges are its own beliefs - every seat
Bayes-updated with that policy's strategy, whatever that seat really plays - as `referee.e3.lbr`
reads it, and a champion keeps its own k, depth and key variant. Each TP policy at the table tracks
its own ranges. Persona and uniform players need no beliefs. A champion only plays the rules it was
trained on (menu, raise cap): a configuration with a champion whose rules differ from the deal's is
reported as skipped, not played with keys it never saw.

Reported per configuration: the target's bb/100, its 95% CI and CI lower bound, deals and hands
(deals x seat rotations), the opponents in seat order after the target (the pairing) and the seat
mix (seats per opponent kind); then the worst configuration (lowest mean) with its point estimate
and CI lower bound. This is a measured loss against this
opponent set, not an exploitability bound (no Q4 here).
"""
from __future__ import annotations

import gzip
import hashlib
import json
from collections import Counter
from collections.abc import Callable
from functools import cache, lru_cache
from pathlib import Path

import numpy as np

from referee.e3.lbr import seat_probs
from referee.stats import adjust_with_corrections, bootstrap_ci
from stalker.e2.eq_view import N as EQ_N
from stalker.e2.eq_view import combo_index, equity_vs
from stalker.e3 import game as G
from stalker.e3 import tp_key as K

HERE = Path(__file__).resolve().parent
CONFIGS_V1 = HERE / "field_v1.json"
CONFIGS = HERE / "field_v2.json"
CONFIGS_V3 = HERE / "field_v3.json"      # 2-5 players (#534); 6 players stay on CONFIGS
SPECIAL = ("uniform", "self")
CHAMPION = "champion:"
REGISTRY = "champions/champions_v1.json"     # relative to this directory, as field_v2.json names it
PAIRING = ("duplicate: every deal once per target seat; the opponents fill the seats after the target "
           "in the listed order, with the same action random stream in every rotation")


class FieldError(ValueError):
    pass


def champion_names(spec: dict) -> set[str]:
    reg = spec.get("champions")
    if not reg:
        return set()
    return {c["name"] for c in json.loads((HERE / reg).read_text(encoding="utf-8"))["champions"]}


def load(path: Path = CONFIGS, players: int | None = None) -> tuple[dict, str]:
    """A configuration set and the sha256 of its file. A per-player-count file (`tables`, v3) needs
    `players` and yields that table's set in the single-table shape (`players`, `configs`)."""
    from stalker.agents.persona import PRESETS

    raw = path.read_bytes()
    spec = json.loads(raw)
    if "tables" in spec:
        if str(players) not in spec["tables"]:
            raise FieldError(f"{path.name}: no table for players={players}; it has {sorted(spec['tables'], key=int)}")
        spec = {k: v for k, v in spec.items() if k != "tables"} | {"players": players, **spec["tables"][str(players)]}
    elif players is not None and players != spec["players"]:
        raise FieldError(f"{path.name} is for {spec['players']} players, not {players}; use load_players({players})")
    if not spec.get("configs"):
        raise FieldError(f"{path.name}: no configs; list opponent configurations under 'configs'")
    known = set(PRESETS) | set(SPECIAL) | {CHAMPION + n for n in champion_names(spec)}
    for c in spec["configs"]:
        if len(c["opponents"]) != spec["players"] - 1:
            raise FieldError(f"{path.name}: config {c['name']!r} has {len(c['opponents'])} opponents; "
                             f"need {spec['players'] - 1}")
        bad = [o for o in c["opponents"] if o not in known]
        if bad:
            raise FieldError(f"{path.name}: config {c['name']!r} names unknown opponents {bad}; use {sorted(known)}")
    return spec, hashlib.sha256(raw).hexdigest()


def load_players(n: int) -> tuple[dict, str]:
    """The registered configuration set for an n-player table: 6 keeps field_v2 (results unchanged), 2-5 field_v3."""
    return load(CONFIGS, 6) if n == 6 else load(CONFIGS_V3, n)


class Champion:
    """An archived TP-key policy at the table: it reads its own keys (k, depth, key variant), so its
    rows are the ones it was trained and served with whatever the target's variant is."""

    def __init__(self, name: str, policy: dict, k: int, depth: str, menu: str, raise_cap, variant: str, sha256: str,
                 players: int = 6):
        self.name, self.policy, self.k, self.depth = name, policy, k, depth
        self.menu, self.raise_cap, self.variant, self.sha256 = menu, raise_cap, variant, sha256
        self.players = players

    def probs(self, s: G.State, seat: int, ranges) -> np.ndarray:
        with K.using_variant(self.variant):
            return seat_probs(self.policy, s, seat, ranges, self.k, self.depth)


@cache
def champion(name: str, registry: str = REGISTRY) -> Champion:
    """A registered champion, its file checked against the pinned sha256 (uncompressed JSON)."""
    reg = HERE / registry
    entry = next((c for c in json.loads(reg.read_text(encoding="utf-8"))["champions"] if c["name"] == name), None)
    if entry is None:
        raise FieldError(f"{reg.name}: no champion {name!r}; register it there first")
    raw = gzip.decompress((reg.parent / entry["file"]).read_bytes())
    sha = hashlib.sha256(raw).hexdigest()
    if sha != entry["sha256"]:
        raise FieldError(f"champion {name}: sha256 {sha[:12]} != registered {entry['sha256'][:12]}; "
                         "restore the file from its 'source' (git show) instead of editing the registry")
    d = json.loads(raw)
    if d.get("schema") != "stalker.web.policy":
        raise FieldError(f"champion {name}: not a web policy export (schema stalker.web.policy)")
    q = d["q"]
    return Champion(name, {k: [x / q for x in v] for k, v in d["policy"].items()}, d["k"], d["depth"],
                    d.get("menu", "v1"), d.get("raise_cap", G.RAISE_CAP), d.get("key_variant", ""), sha,
                    d.get("players", 6))


def uniform(s: G.State) -> np.ndarray:
    m = len(G.legal(s))
    return np.full(m, 1.0 / m)


def _actor(kind: str, target, registry: str | None = None):
    if kind == "self":
        return target
    if kind == "uniform":
        return uniform
    if kind.startswith(CHAMPION):
        return champion(kind[len(CHAMPION):], registry or REGISTRY)
    from stalker.e3.personas import Persona

    return Persona(kind)


def _mismatch(c: Champion, s: G.State) -> str | None:
    if (c.menu, c.raise_cap, c.players) != (s.menu, s.raise_cap, s.n):
        return (f"champion {c.name} plays menu {c.menu} cap {c.raise_cap} at {c.players} seats; "
                f"these deals use menu {s.menu} cap {s.raise_cap} at {s.n}")
    return None


def committed_value(s: G.State, seat: int) -> float:
    """A cheap value estimate (bb) of state `s` for `seat`: its share of the pot among the players
    still in the hand (the pot split evenly) minus the chips it has put in. A folded seat is worth
    minus its investment. It need not be right: the AIVAT corrections stay unbiased for any value
    function, a better one only shrinks the variance (#593)."""
    pot = sum(s.total)
    if s.folded[seat]:
        return -s.total[seat] / G.BB
    live = sum(1 for f in s.folded if not f)
    return (pot / live - s.total[seat]) / G.BB


@lru_cache(maxsize=4096)  # ~10 KB per board; chance terms draw fresh boards, so it must stay bounded
def _uniform_equity(board: tuple[int, ...]) -> np.ndarray:
    # read-only: one array per board, shared by every call on that board
    eq = equity_vs(board, np.ones(EQ_N))
    eq.flags.writeable = False
    return eq


def equity_value(s: G.State, seat: int) -> float:
    """A board-dependent value estimate (bb) of `s` for `seat`: `eq**L * pot - total[seat]`, where `eq` is
    the seat's own hole cards' equity against a uniform range on the current board (`stalker.e2.eq_view.
    equity_vs`, preflop from the class table) and `L` the live opponents. `eq**L` is an approximation
    (it treats the opponents as independent uniform ranges and ignores who is still betting); the
    AIVAT corrections stay unbiased for any value, so it only has to track the outcome better than
    `committed_value` to shrink the variance. Only the seat's own cards and the board are read: no
    opponent hole cards. A folded seat is worth minus its investment; the last seat left wins the pot."""
    pot = sum(s.total)
    if s.folded[seat]:
        return -s.total[seat] / G.BB
    live = sum(1 for f in s.folded if not f) - 1
    if live == 0:
        return (pot - s.total[seat]) / G.BB
    eq = float(_uniform_equity(tuple(s.board))[combo_index(s.hole[seat])])
    return (eq ** live * pot - s.total[seat]) / G.BB


AIVAT_VALUES = {"committed": committed_value, "equity": equity_value}


def _chance_term(s: G.State, nxt: G.State, seat: int, value, rng, m: int) -> float:
    """`v(h.board) - mean_m v(h.board_m)` for a board reveal `s -> nxt`: `m` alternative boards of the
    same size are drawn from the cards left in `s.deck` (the actual board is one more draw from it), so
    the term has mean zero for any `value`. A reveal that opens several streets at once (all-in
    runout) is one chance event."""
    cnt = len(nxt.board) - len(s.board)
    alts = []
    for _ in range(m):
        idx = sorted(rng.choice(len(s.deck), size=cnt, replace=False).tolist())
        keep = tuple(c for i, c in enumerate(s.deck) if i not in set(idx))
        alts.append(nxt._replace(board=s.board + tuple(s.deck[i] for i in idx), deck=keep))
    v = value(nxt, seat)
    return -float(np.mean([value(x, seat) - v for x in alts]))  # diff first: exactly 0 for a board-blind value


def play_deal(target, opponents: list, deal_seed: int, k: int = 5, depth: str = "basic",
              value: Callable[[G.State, int], float] | None = None, chance: bool = True, chance_m: int = 8):
    """The target's net (bb) in each seat rotation of one deal. `target`: a TP-key policy dict or a
    callable state -> probabilities over the legal actions; `opponents`: one actor per other seat
    (a `Champion` is a TP-key policy with its own beliefs).

    With `value(state, target_seat)` (bb, the target's view) it returns `(net, corrections)`: per
    rotation, the sum over decisions by actors whose strategy is known (a TP-key policy, a champion,
    or `uniform`) of `v(h.a) - sum_a' p(a') v(h.a')`. Each term has mean zero, so `net - corrections`
    is unbiased with less variance. Personas and other callables are not corrected. The action
    random stream is the same with or without `value`.

    `chance` (default on) also adds a board-reveal term per chance event (`_chance_term`, `chance_m`
    alternative boards from the separate stream `[deal_seed, 2, event]`). The default `committed_value`
    does not depend on the board, so that term is exactly 0 there: board-dependent value functions
    (e.g. equity) are needed for it to reduce variance. `chance=False` gives the #593 corrections."""
    n = len(opponents) + 1
    # every TP-key policy at the table, once each, with how it reads a seat: (policy, read)
    readers = [(target, lambda s, p, r: seat_probs(target, s, p, r, k, depth))] if isinstance(target, dict) else []
    for o in dict.fromkeys(o for o in opponents if isinstance(o, Champion)):
        readers.append((o, o.probs))
    out = np.empty(n)
    corr = np.zeros(n)
    for seat in range(n):
        s = G.deal(np.random.default_rng([deal_seed, 0]), n)
        rng = np.random.default_rng([deal_seed, 1])      # the same action stream in every rotation
        actors = {seat: target}
        for j, opp in enumerate(opponents):
            actors[(seat + 1 + j) % n] = opp
        ranges = [K.initial_ranges(n) for _ in readers]
        events = 0
        while not s.done:
            p, acts = s.to_act, G.legal(s)
            tables = [read(s, p, r) for (_, read), r in zip(readers, ranges)]
            who = actors[p]
            mine = next((t for (pol, _), t in zip(readers, tables) if pol is who), None)
            row = mine[combo_index(s.hole[p])] if mine is not None else who(s)
            a = int(rng.choice(len(acts), p=row / row.sum()))
            ranges = [K.update_range(r, p, t[:, a]) for r, t in zip(ranges, tables)]
            nxt = G.apply(s, acts[a])
            if value is not None and (mine is not None or who is uniform):
                vals = np.array([value(nxt if i == a else G.apply(s, x), seat) for i, x in enumerate(acts)])
                corr[seat] += vals[a] - float(vals @ (row / row.sum()))
            if value is not None and chance and len(nxt.board) > len(s.board):
                corr[seat] += _chance_term(s, nxt, seat, value, np.random.default_rng([deal_seed, 2, events]), chance_m)
                events += 1
            s = nxt
        out[seat] = float(G.payoff(s)[seat]) / G.BB
    return out if value is None else (out, corr)


def evaluate(target, hands: int, seed: int = 0, spec: dict | None = None, k: int = 5, depth: str = "basic",
             configs: list[str] | None = None, players: int | None = None,
             aivat: bool | Callable[[G.State, int], float] = False) -> dict:
    """The target's bb/100 per configuration (95% CI over deals) and the worst configuration
    (all-self configurations are reported in `configs` but excluded from `worst`, #374; champion
    configurations the deal's rules do not fit are listed in `skipped`). `players` picks the
    registered set for that table size (`load_players`, default 6). `aivat` (True: `committed_value`, or a
    value callable) adds per configuration `aivat: {bb100, se, variance_ratio}` from `referee.stats.
    adjust_with_corrections` over per-deal means; it is record-only and never enters `worst` (#593)."""
    sha = None
    if spec is None:
        spec, sha = load_players(6 if players is None else players)
    elif players is not None and players != spec["players"]:
        raise FieldError(f"spec is for {spec['players']} players, not {players}")
    if hands < 2:
        raise ValueError("hands must be >= 2 (the CI resamples deals)")
    rules = G.deal(np.random.default_rng(0), spec["players"])
    rows, matched, skipped, used = [], [], [], {}
    for c in spec["configs"]:
        if configs and c["name"] not in configs:
            continue
        opps = [_actor(o, target, spec.get("champions")) for o in c["opponents"]]
        champs = list(dict.fromkeys(o for o in opps if isinstance(o, Champion)))
        why = next((m for m in (_mismatch(ch, rules) for ch in champs) if m), None)
        if why:
            skipped.append({"name": c["name"], "reason": why})
            continue
        used.update((ch.name, ch.sha256) for ch in champs)
        matched.append(c)
        corr = None
        if aivat:
            val = committed_value if aivat is True else aivat
            pairs = [play_deal(target, opps, seed * 1_000_003 + h, k, depth, val) for h in range(hands)]
            res, corr = np.array([p[0] for p in pairs]), np.array([p[1] for p in pairs])
        else:
            res = np.array([play_deal(target, opps, seed * 1_000_003 + h, k, depth) for h in range(hands)])
        ci = bootstrap_ci(res.ravel() * 100, np.repeat(np.arange(hands), res.shape[1]), rng=np.random.default_rng(seed))
        rows.append({"name": c["name"], "bb100": round(ci.mean, 2), "ci95": [round(ci.lo, 2), round(ci.hi, 2)],
                     "ci95_low": round(ci.lo, 2), "deals": hands, "hands": hands * res.shape[1],
                     "opponents": list(c["opponents"]), "seat_mix": dict(Counter(c["opponents"])),
                     "by_seat_bb100": [round(float(x), 1) for x in res.mean(axis=0) * 100]})
        if corr is not None:
            adj = adjust_with_corrections(res.mean(axis=1) * 100, corr.mean(axis=1) * 100)
            rows[-1]["aivat"] = {"bb100": round(adj.mean, 2), "se": round(adj.se, 2),
                                 "variance_ratio": round(adj.var_ratio, 3)}
    if not rows:
        raise FieldError(f"no config matched {configs}" + (f" (skipped: {skipped})" if skipped else ""))
    # self-play is exactly 0 by symmetry (a sanity row); counting it would hide the real worst opponent set
    rivals = [r for r, c in zip(rows, matched) if any(o != "self" for o in c["opponents"])] or rows
    worst = min(rivals, key=lambda r: r["bb100"])
    return {"version": spec["version"], "sha256": sha, "seed": seed, "deals": hands, "pairing": PAIRING,
            "champions": used, "configs": rows, "skipped": skipped,
            "worst": {"name": worst["name"], "bb100": worst["bb100"], "ci95_low": worst["ci95"][0]}}


def main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="E3 field evaluation of a TP-key policy (bb/100, worst configuration)")
    ap.add_argument("policy", type=Path, help="policy JSON: a dict of TP keys, or {'average': ..., 'current': ...}")
    ap.add_argument("--which", default="current", choices=["current", "average"])
    ap.add_argument("--tier", default="beginner", choices=sorted(K.TIER_K))
    ap.add_argument("--hands", type=int, default=200)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--configs", nargs="*")
    ap.add_argument("--players", type=int, default=6, help="table size: 6 uses field_v2, 2-5 field_v3 (#534)")
    ap.add_argument("--aivat", nargs="?", const="committed", choices=sorted(AIVAT_VALUES),
                    help="also record the AIVAT-adjusted bb/100 per config (record-only); the value function: "
                         "committed (default when the flag has no argument) or equity (board-dependent, #634)")
    a = ap.parse_args(argv)
    pol = json.loads(a.policy.read_text(encoding="utf-8"))
    if isinstance(pol.get(a.which), dict):
        pol = pol[a.which]
    res = evaluate(pol, a.hands, a.seed, k=K.TIER_K[a.tier], depth=K.TIER_DEPTH[a.tier], configs=a.configs,
                   players=a.players, aivat=AIVAT_VALUES[a.aivat] if a.aivat else False)
    print(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
