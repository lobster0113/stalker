"""JSON Lines storage for records, plus a run manifest for reproducibility.

A run directory holds `manifest.json` (config, seed, git sha, policy_version) and `records.jsonl`,
one record per line: {"type": "decision"|"hand"|"game", "record": {...}}. Records are validated on
write and on read so a bad record never silently enters training or typing data.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from stalker.records.schema import (
    RECORD_TYPES,
    SCHEMA_VERSION,
    Record,
    RecordError,
    ensure_valid,
    from_dict,
    to_dict,
)

MANIFEST = "manifest.json"
RECORDS = "records.jsonl"


@dataclass(frozen=True)
class RunManifest:
    run_id: str
    created_at: str  # ISO 8601 UTC
    config: dict[str, Any]  # TournamentConfig.to_dict()
    seed: int
    git_sha: str
    policy_version: str
    meta: dict[str, str] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION

    @classmethod
    def create(cls, run_id: str, config: Any, seed: int, policy_version: str,
               meta: dict[str, str] | None = None) -> "RunManifest":
        cfg = config.to_dict() if hasattr(config, "to_dict") else dict(config)
        return cls(run_id=run_id, created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   config=cfg, seed=seed, git_sha=current_git_sha(), policy_version=policy_version,
                   meta=dict(meta or {}))


def current_git_sha() -> str:
    """HEAD of the checkout this code runs from, suffixed '-dirty' if it has local changes."""
    root = Path(__file__).resolve().parent
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True,
                             check=True, encoding="utf-8").stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=root,
                               capture_output=True, text=True, check=True, encoding="utf-8").stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return sha + ("-dirty" if dirty else "")


def write_manifest(run_dir: str | Path, manifest: RunManifest) -> Path:
    path = Path(run_dir) / MANIFEST
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(to_dict(manifest), indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                    encoding="utf-8")
    return path


def _loads(text: str, where: str) -> Any:
    # json.loads accepts NaN/Infinity by default; they would slip into training data as nan/inf
    def reject(token: str) -> Any:
        raise RecordError(f"{where}: non-finite number {token} is not allowed; write finite values only.")
    try:
        return json.loads(text, parse_constant=reject)
    except json.JSONDecodeError as exc:
        raise RecordError(f"{where}: not valid JSON ({exc.msg}).") from None


def read_manifest(run_dir: str | Path) -> RunManifest:
    data = _loads((Path(run_dir) / MANIFEST).read_text(encoding="utf-8"), MANIFEST)
    _check_version(data, MANIFEST)
    return from_dict(RunManifest, data, "manifest")


def _type_name(record: Record) -> str:
    for name, cls in RECORD_TYPES.items():
        if type(record) is cls:
            return name
    raise RecordError(f"cannot store {type(record).__name__}: expected one of {sorted(RECORD_TYPES)} records.")


def _check_version(data: Any, where: str) -> None:
    version = data.get("schema_version") if isinstance(data, dict) else None
    if version != SCHEMA_VERSION:
        raise RecordError(f"{where}: schema_version={version}; only {SCHEMA_VERSION} is supported, migrate the file.")


class RecordWriter:
    """Append records to `<run_dir>/records.jsonl`. Use as a context manager."""

    def __init__(self, run_dir: str | Path) -> None:
        self.path = Path(run_dir) / RECORDS
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._f = self.path.open("a", encoding="utf-8")

    def write(self, record: Record, hole_cards: dict[int, Any] | None = None) -> None:
        ensure_valid(record, hole_cards)
        line = json.dumps({"type": _type_name(record), "record": to_dict(record)},
                          ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        self._f.write(line + "\n")

    def close(self) -> None:
        self._f.close()

    def __enter__(self) -> "RecordWriter":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def iter_records(run_dir: str | Path, validate: bool = True) -> Iterator[Record]:
    path = Path(run_dir) / RECORDS
    with path.open(encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            if not line.strip():
                continue
            where = f"{path.name}:{lineno}"
            obj = _loads(line, where)
            if not isinstance(obj, dict) or obj.get("type") not in RECORD_TYPES or "record" not in obj:
                raise RecordError(f"{where}: expected {{\"type\": one of {sorted(RECORD_TYPES)}, \"record\": {{...}}}}.")
            _check_version(obj["record"], where)
            record = from_dict(RECORD_TYPES[obj["type"]], obj["record"], where)
            if validate:
                try:
                    ensure_valid(record)
                except RecordError as exc:
                    raise RecordError(f"{where}: {exc}") from None
            yield record


def load_records(run_dir: str | Path, validate: bool = True) -> list[Record]:
    return list(iter_records(run_dir, validate))
