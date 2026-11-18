"""Bundle per-agent `icm_grid --lambda-grid` outputs into one result file (#873).

A cloud job has one `result_path`; the lambda-grid baseline needs one run per agent. Each agent's
original output is embedded unchanged under `agents[<name>]`, so `selected_lambda` can be recomputed
from it later.

Usage: python -m stalker.tools.icm_grid_pair --out pair.json random=random.json tag=tag.json
"""
import argparse
import json
from pathlib import Path

SCHEMA = "stalker.icm.lambda-grid-pair"
SCHEMA_VERSION = 1


def bundle(named_paths: dict[str, Path]) -> dict:
    agents = {}
    for name, path in named_paths.items():
        grid = json.loads(Path(path).read_text(encoding="utf-8"))
        if "selected_lambda" not in grid:
            raise ValueError(f"{path}: no selected_lambda; run icm_grid with --lambda-grid.")
        agents[name] = grid
    return {"schema": SCHEMA, "schema_version": SCHEMA_VERSION, "agents": agents}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("inputs", nargs="+", help="NAME=path of an icm_grid --lambda-grid JSON")
    a = ap.parse_args(argv)
    named = {}
    for item in a.inputs:
        name, sep, path = item.partition("=")
        if not sep or not name or not path:
            ap.error(f"{item!r}: use NAME=path, e.g. random=random.json.")
        named[name] = Path(path)
    try:
        pair = bundle(named)
    except (ValueError, OSError) as e:
        ap.exit(2, f"icm_grid_pair: {e}\n")
    a.out.write_text(json.dumps(pair, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
                     encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
