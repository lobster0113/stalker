"""TexasSolver console wrapper: heads-up postflop spot -> root-node mixed strategy per combo.

Install the binary with `scripts/install_texassolver.sh` (pinned commit, AGPL, personal research use —
ADR 0002 decision 3). The wrapper writes a command file, runs `console_solver` in a scratch directory,
and parses the `dump_result` JSON. Card strings are converted to STALKER ints (`stalker.core.cards`),
so a root strategy is keyed by `(hi, lo)` combo tuples like `COMBOS`.

Solver conventions this module relies on (checked against the pinned source, `src/tools/CommandLineTool.cpp`):
- `set_pot P` splits P evenly as both players' commitment; `set_effective_stack S` is the stack behind.
- Bet sizes are percent of pot; `set_accuracy` is the target exploitability in percent of pot.
- In the dump, `player` 1 is OOP and 0 is IP; the root is OOP's first decision on the given street.
- The solver appends `{"iteration","exploitibility","time_ms"}` lines (sic) to `tmp_log.txt` in its cwd.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from stalker.core.cards import card, card_str

PLAYERS = ("oop", "ip")
STREETS = ("flop", "turn", "river")
DEFAULT_HOME = Path.home() / ".cache" / "stalker" / "texassolver"
LOG_NAME = "tmp_log.txt"
OUTPUT_NAME = "result.json"


class TexasSolverError(RuntimeError):
    pass


@dataclass(frozen=True)
class StreetSizes:
    """Bet options for one player on one street, in percent of pot. `donk` is OOP-only (leading into the
    previous street's aggressor); `allin` adds a shove option at every decision."""
    bet: tuple[float, ...] = ()
    raise_: tuple[float, ...] = ()
    donk: tuple[float, ...] = ()
    allin: bool = False


@dataclass(frozen=True)
class Spot:
    """Ranges use TexasSolver syntax (`AA,KQs:0.5,...`). Board is 3–5 cards, e.g. `"Qs Jh 2h"`."""
    board: str
    pot: int
    effective_stack: int
    range_oop: str
    range_ip: str
    sizes: dict[tuple[str, str], StreetSizes] = field(default_factory=dict)
    allin_threshold: float = 0.67

    def board_cards(self) -> list[int]:
        text = self.board.replace(",", "").replace(" ", "")
        cs = [card(text[i:i + 2]) for i in range(0, len(text), 2)]
        if not 3 <= len(cs) <= 5 or len(set(cs)) != len(cs):
            raise ValueError(f"board {self.board!r}: need 3-5 distinct cards like 'Qs Jh 2h'")
        return cs

    def street(self) -> str:
        return STREETS[len(self.board_cards()) - 3]


@dataclass(frozen=True)
class SolveSettings:
    accuracy: float = 0.5  # target exploitability, % of pot
    max_iteration: int = 200
    threads: int = 0  # 0 = os.cpu_count()
    use_isomorphism: bool = True
    print_interval: int = 10


@dataclass(frozen=True)
class RootStrategy:
    player: str  # "oop" | "ip"
    actions: tuple[str, ...]  # e.g. ("CHECK", "BET 10.000000")
    probs: dict[tuple[int, int], tuple[float, ...]]  # combo (hi, lo) -> prob per action

    def action_index(self, prefix: str) -> list[int]:
        return [i for i, a in enumerate(self.actions) if a.split()[0] == prefix]


@dataclass(frozen=True)
class SolveResult:
    root: RootStrategy
    dump: dict  # raw `dump_result` JSON (current street only), for `parse_root(dump, path)`
    exploitability: float | None  # % of pot at the last logged iteration
    iterations: int | None
    wall_s: float
    peak_rss_mb: float  # solver process peak RSS (Linux ru_maxrss is KiB)
    solver_version: str | None


def build_input(spot: Spot, settings: SolveSettings, output: str = OUTPUT_NAME) -> str:
    board = ",".join(card_str(c) for c in spot.board_cards())
    for key in spot.sizes:
        if key[0] not in PLAYERS or key[1] not in STREETS:
            raise ValueError(f"sizes key {key!r}: use (player, street) with player in {PLAYERS}, street in {STREETS}")
    if spot.pot <= 0 or spot.effective_stack <= 0:
        raise ValueError("pot and effective_stack must be positive chip counts")
    threads = settings.threads or os.cpu_count() or 1
    lines = [
        f"set_pot {spot.pot}",
        f"set_effective_stack {spot.effective_stack}",
        f"set_board {board}",
        f"set_range_oop {_no_space(spot.range_oop)}",
        f"set_range_ip {_no_space(spot.range_ip)}",
    ]
    for (player, street), s in sorted(spot.sizes.items()):
        for kind, sizes in (("bet", s.bet), ("raise", s.raise_), ("donk", s.donk)):
            if sizes:
                lines.append(f"set_bet_sizes {player},{street},{kind},{','.join(_num(x) for x in sizes)}")
        if s.allin:
            lines.append(f"set_bet_sizes {player},{street},allin")
    lines += [
        f"set_allin_threshold {_num(spot.allin_threshold)}",
        "build_tree",
        f"set_thread_num {threads}",
        f"set_accuracy {_num(settings.accuracy)}",
        f"set_max_iteration {settings.max_iteration}",
        f"set_print_interval {settings.print_interval}",
        f"set_use_isomorphism {int(settings.use_isomorphism)}",
        "start_solve",
        "set_dump_rounds 1",
        f"dump_result {output}",
    ]
    return "\n".join(lines) + "\n"


def parse_root(dump: dict, path: tuple[str, ...] = ()) -> RootStrategy:
    """Action node of a `dump_result` JSON reached by `path` (action strings from the root, same street
    only — the dump stops at chance nodes). Strategies of colliding combos are already dropped by the
    solver; combos are re-keyed as STALKER `(hi, lo)` tuples."""
    for step in path:
        children = dump.get("childrens", {})
        if step not in children:
            raise TexasSolverError(f"path step {step!r} not in {sorted(children)}")
        dump = children[step]
    if dump.get("node_type") != "action_node" or "strategy" not in dump:
        raise TexasSolverError("dump root is not an action node with a strategy — was the tree built?")
    actions = tuple(dump["strategy"]["actions"])
    probs: dict[tuple[int, int], tuple[float, ...]] = {}
    for hand, p in dump["strategy"]["strategy"].items():
        if len(p) != len(actions):
            raise TexasSolverError(f"combo {hand}: {len(p)} probs for {len(actions)} actions")
        a, b = card(hand[:2]), card(hand[2:4])
        probs[(max(a, b), min(a, b))] = tuple(float(x) for x in p)
    player = {1: "oop", 0: "ip"}.get(dump.get("player"))
    if player is None:
        raise TexasSolverError(f"unknown root player {dump.get('player')!r}")
    return RootStrategy(player, actions, probs)


def parse_log(text: str) -> tuple[float | None, int | None]:
    last = None
    for line in text.splitlines():
        line = line.strip()
        if line:
            last = json.loads(line)
    if last is None:
        return None, None
    return float(last["exploitibility"]), int(last["iteration"]) + 1


def find_binary(home: str | os.PathLike | None = None) -> Path | None:
    root = Path(home or os.environ.get("STALKER_TEXASSOLVER_HOME") or DEFAULT_HOME)
    exe = root / "console_solver"
    return exe if exe.is_file() and os.access(exe, os.X_OK) and (root / "resources").is_dir() else None


def solve(spot: Spot, settings: SolveSettings = SolveSettings(), home: str | os.PathLike | None = None,
          timeout: float | None = None) -> SolveResult:
    exe = find_binary(home)
    if exe is None:
        raise TexasSolverError("console_solver not found — run scripts/install_texassolver.sh "
                               "or set STALKER_TEXASSOLVER_HOME")
    root = exe.parent
    version = (root / "VERSION").read_text().strip() if (root / "VERSION").is_file() else None
    with tempfile.TemporaryDirectory(prefix="texassolver-") as work:
        inp = Path(work) / "input.txt"
        inp.write_text(build_input(spot, settings))
        start = time.perf_counter()
        code, rss_mb, output = _run([str(exe), "-i", str(inp), "-r", str(root / "resources"), "-m", "holdem"],
                                    work, timeout)
        wall = time.perf_counter() - start
        out = Path(work) / OUTPUT_NAME
        if code != 0 or not out.is_file():
            tail = "\n".join(output.splitlines()[-10:])
            raise TexasSolverError(f"console_solver exit {code}, no {OUTPUT_NAME}:\n{tail}")
        raw = json.loads(out.read_text())
        rootstrat = parse_root(raw)
        log = Path(work) / LOG_NAME
        expl, iters = parse_log(log.read_text()) if log.is_file() else (None, None)
    return SolveResult(rootstrat, raw, expl, iters, wall, rss_mb, version)


def _run(cmd: list[str], cwd: str, timeout: float | None) -> tuple[int, float, str]:
    """Run to completion; returns (exit code, this child's peak RSS in MB, combined output). `os.wait4`
    gives per-child rusage, which `subprocess.run` does not expose."""
    log = Path(cwd) / "console.out"
    with open(log, "w") as fh:
        proc = subprocess.Popen(cmd, cwd=cwd, stdout=fh, stderr=subprocess.STDOUT)
        timer = threading.Timer(timeout, proc.kill) if timeout else None
        if timer:
            timer.start()
        try:
            _, status, usage = os.wait4(proc.pid, 0)
        finally:
            if timer:
                timer.cancel()
        proc.returncode = os.waitstatus_to_exitcode(status)
    if timer and proc.returncode < 0:
        raise TexasSolverError(f"console_solver killed after {timeout}s timeout")
    return proc.returncode, usage.ru_maxrss / 1024, log.read_text(errors="replace")


def _no_space(text: str) -> str:
    # The console splits each command on spaces and rejects more than one argument.
    return "".join(text.split())


def _num(x: float) -> str:
    return f"{x:g}"
