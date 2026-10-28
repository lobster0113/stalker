"""Public hand-history replay (SIM-f, #148): recorded PHH hands re-dealt and re-played on our engines.

Each hand's recorded hole cards and board are injected as the deck (`Hand`/`FastHand` draw from
`rng.permutation(52)`, popping from the end), the recorded actions are applied, and the engine's
final stacks must equal the record's `finishing_stacks` chip for chip. Hands whose rules differ from
ours are excluded with a reason code instead of being compared.

Sample build (needs a checkout of https://github.com/uoftcprg/phh-dataset, MIT):
    python -m referee.gate_r.phh build <phh-dataset>/data/pluribus tests/data/phh/pluribus.jsonl.gz --step 5
"""
from __future__ import annotations

import argparse
import gzip
import json
import tomllib
from collections import Counter
from pathlib import Path

import numpy as np

from stalker.core.cards import N_CARDS, card
from stalker.tournament.fast_hand import FastHand
from stalker.tournament.hand import Hand

SAMPLE = Path(__file__).resolve().parents[2] / "tests" / "data" / "phh" / "pluribus.jsonl.gz"


class _FixedDeck:
    """Stands in for the Generator: `permutation` returns a deck whose last cards are drawn first."""

    def __init__(self, deck: list[int]) -> None:
        self._deck = deck

    def permutation(self, n: int) -> np.ndarray:
        assert n == N_CARDS
        return np.array(self._deck)


def exclusion(rec: dict) -> str | None:
    """Reason code if the hand was not played under our rules (no ante, SB/BB only, no run-it-twice)."""
    if rec.get("variant") != "NT":
        return "variant"
    if any(rec.get("antes", [])):
        return "ante"
    blinds = rec["blinds_or_straddles"]
    if len(blinds) < 2 or any(blinds[2:]) or not 0 < blinds[0] <= blinds[1]:
        return "straddle_or_blinds"
    if rec.get("min_bet") != blinds[1]:
        return "min_bet"
    if len(set(rec["starting_stacks"])) and min(rec["starting_stacks"]) <= 0:
        return "empty_seat"
    if any(x != int(x) for x in rec["finishing_stacks"]):
        return "fractional_chips"  # the record split an odd chip; ours are integers (odd chip to the first winner)
    if len(rec["players"]) < 2:
        return "players"
    for a in rec["actions"]:
        if a.split()[0] == "d" and a.split()[1] == "dh" and "?" in a:
            return "hidden_cards"
    return None


def _deck(rec: dict) -> list[int]:
    n = len(rec["players"])
    holes: list[list[int]] = [[] for _ in range(n)]
    streets: list[list[int]] = []
    for a in rec["actions"]:
        t = a.split()
        if t[0] != "d":
            continue
        if t[1] == "dh":
            p = int(t[2][1:]) - 1
            holes[p] = [card(t[3][i:i + 2]) for i in range(0, len(t[3]), 2)]
        else:
            streets.append([card(t[2][i:i + 2]) for i in range(0, len(t[2]), 2)])
    known = {c for h in holes for c in h} | {c for s in streets for c in s}
    fillers = [c for c in range(N_CARDS) if c not in known]
    order = [holes[i][r] for r in range(2) for i in range(n)]
    for k, s in enumerate(streets):
        order.append(fillers[k])  # burn card
        order.extend(s)
    rest = fillers[len(streets):]
    return rest + order[::-1]  # popped from the end: order[0] is drawn first


def replay(rec: dict, engine=Hand) -> tuple[int, ...]:
    """Final stacks (PHH player order) after replaying the record on `engine` (`Hand` or `FastHand`)."""
    n = len(rec["players"])
    sb, bb = rec["blinds_or_straddles"][:2]
    # PHH p1 is the small blind and pn the button, so the engine's seats are the PHH players in order.
    hand = engine(rec["starting_stacks"], n - 1, sb, bb, _FixedDeck(_deck(rec)))
    for a in rec["actions"]:
        t = a.split()
        if t[0] == "d" or t[1] in ("sm", "sh"):
            continue
        seat = int(t[0][1:]) - 1
        if hand.is_over or hand.actor != seat:
            raise AssertionError(f"hand {rec.get('hand')}: record says p{seat + 1} acts ({a!r}), engine says {hand.actor}")
        if t[1] == "f":
            hand.fold()
        elif t[1] == "cc":
            hand.check_or_call()
        elif t[1] == "cbr":
            hand.raise_to(int(t[2]))
        else:
            raise ValueError(f"unknown PHH action {a!r}")
    if not hand.is_over:
        raise AssertionError(f"hand {rec.get('hand')}: record ended but the engine still expects an action")
    return tuple(hand.result().final_stacks)


def load_sample(path: Path = SAMPLE) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def run(recs: list[dict], engine=Hand) -> dict:
    """Replay every non-excluded record; returns counts and the list of mismatching hand ids."""
    excluded: Counter = Counter()
    mismatches: list[str] = []
    compared = 0
    for r in recs:
        why = exclusion(r)
        if why:
            excluded[why] += 1
            continue
        compared += 1
        try:
            final = replay(r, engine)
        except AssertionError as e:
            mismatches.append(str(e))
            continue
        if list(final) != list(r["finishing_stacks"]):
            mismatches.append(f"hand {r.get('id')}: engine {list(final)} != record {r['finishing_stacks']}")
    return {"total": len(recs), "compared": compared, "excluded": dict(excluded), "mismatches": mismatches}


def build(src: Path, out: Path, step: int) -> int:
    """Every `step`-th hand of a PHH directory tree (sorted paths) as gzipped JSON lines."""
    files = sorted(src.glob("*/*.phh"), key=lambda p: (p.parent.name, int(p.stem)))[::step]
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for p in files:
        rec = tomllib.loads(p.read_text(encoding="utf-8"))
        rec["id"] = f"{p.parent.name}/{p.name}"
        lines.append(json.dumps(rec, sort_keys=True) + "\n")
    with open(out, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as f:  # mtime=0: reproducible bytes
        f.write("".join(lines).encode("utf-8"))
    return len(files)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("src", type=Path)
    b.add_argument("out", type=Path)
    b.add_argument("--step", type=int, default=5)
    sub.add_parser("check")
    args = ap.parse_args(argv)
    if args.cmd == "build":
        print(f"wrote {build(args.src, args.out, args.step)} hands to {args.out}")
        return 0
    recs = load_sample()
    bad = 0
    for engine in (Hand, FastHand):
        res = run(recs, engine)
        print(f"{engine.__name__}: compared {res['compared']}/{res['total']} excluded {res['excluded']} mismatches {len(res['mismatches'])}")
        bad += len(res["mismatches"])
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
