"""Gate R cash suite (SIM-b2/SIM-c): every cash preset played by `FastHand`, PokerKit `Hand` and the referee model.

Each session runs twice from the same seeds, once per engine. Three-way agreement means:
- `engine_agreement`: both engines emit the same session stream and the same per-hand events. The only field
  left out is `pot` on a hand's closing action: PokerKit reports it after the award (0), FastHand before it.
  It is a display value, not chips; the stacks and deltas that follow are compared in full.
- each engine's stream passes the independent hand model (`check_cash_hands`) and the five session checks
  (`check_cash_session`), so neither engine can agree with the other on a wrong answer the model would catch.
"""
from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from referee.gate_r.cash import CASH_HAND_ITEMS, CASH_ITEMS, CashRules, check_cash_hands, check_cash_session, tally_for_cash
from referee.gate_r.checks import Tally
from referee.gate_r.suite import BOTS
from stalker.cash.presets import PRESETS, preset
from stalker.cash.session import run_cash_session

ITEMS = ("engine_agreement",) + CASH_ITEMS + CASH_HAND_ITEMS
ENGINES = ("fast", "pokerkit")
FULL_SESSIONS, FULL_HANDS = 12, 1000  # 9 presets x 12 x 1000 = 108k hands per engine
QUICK_SESSIONS, QUICK_HANDS = 2, 100


def _variant(seed: int) -> tuple[str, bool]:
    """Bot and auto top-up for session `seed`: seeds 0-1 cover both bots and both top-up modes, every four seeds all combinations."""
    return sorted(BOTS)[seed % 2], (seed + seed // 2) % 2 == 1


def _play(name: str, seed: int, hands: int, engine: str):
    bot, topup = _variant(seed)
    cfg = preset(name, hands=hands, auto_topup=topup)
    ss = np.random.SeedSequence([sum(map(ord, name)), seed]).spawn(cfg.seats + 1)
    agents = [BOTS[bot](np.random.default_rng(s)) for s in ss[1:]]
    events: list = []
    res = run_cash_session(cfg, agents, np.random.default_rng(ss[0]), observer=events.append, engine=engine)
    return cfg, res, events


def _comparable(res, events) -> tuple:
    out = []
    for i, e in enumerate(events):
        data = dict(e.data)
        if e.type == "ACTION" and events[i + 1].type in ("SHOWDOWN", "HAND_END"):
            data.pop("pot")
        out.append((e.type, e.hand_id, data))
    return tuple(res.events), tuple(out), res.final, res.rebuys, res.topups


def check_session(name: str, seed: int, hands: int) -> Tally:
    tally = tally_for_cash(ITEMS)
    runs = {eng: _play(name, seed, hands, eng) for eng in ENGINES}
    bot, topup = _variant(seed)
    where = f"{name} {bot}{' topup' if topup else ''} seed {seed}"
    cfg = runs["fast"][0]
    lo, hi = cfg.buy_range
    rules = CashRules(seats=cfg.seats, sb=cfg.sb, bb=cfg.bb, min_buyin=lo, max_buyin=hi, hands=cfg.hands)
    seen = {eng: _comparable(res, ev) for eng, (_, res, ev) in runs.items()}
    a, b = (seen[e] for e in ENGINES)
    diff = next((f"{x} != {y}" for x, y in zip(a[1], b[1]) if x != y), "session stream or totals differ")
    tally.check("engine_agreement", a == b, f"{where}: fast vs pokerkit: {diff}"[:400])
    for eng, (_, res, ev) in runs.items():
        check_cash_session(rules, list(res.events), tally, f"{where} [{eng}]")
        check_cash_hands(rules, ev, tally, f"{where} [{eng}]")
    return tally


def _job(args) -> Tally:
    return check_session(*args)


def run_cash_suite(sessions: int = QUICK_SESSIONS, hands: int = QUICK_HANDS, presets=None,
                   workers: int | None = None) -> tuple[Tally, int]:
    """(tally, hands per engine) over `sessions` seeded sessions of `hands` hands for each preset."""
    jobs = [(name, seed, hands) for name in (presets or sorted(PRESETS)) for seed in range(sessions)]
    workers = workers or min(len(jobs), os.cpu_count() or 1)
    tally = tally_for_cash(ITEMS)
    if workers <= 1:
        parts = list(map(_job, jobs))
    else:
        with ProcessPoolExecutor(workers) as pool:
            parts = list(pool.map(_job, jobs))
    for part in parts:
        tally.merge(part)
    return tally, len(jobs) * hands
