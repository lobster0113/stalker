"""JSON tables on disk, plain or gzipped (#560): a 6x10^4-iteration E3 table was over the artifact limit as text."""
from __future__ import annotations

import gzip
import json
from pathlib import Path


def write_json_gz(path: Path, obj) -> None:
    """Write `obj` to `path` (give it the `.json.gz` name). mtime=0 so equal tables give equal bytes."""
    with open(path, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, compresslevel=6) as gz:
        gz.write(json.dumps(obj).encode("utf-8"))


def read_json(path: Path):
    """Read a `.json` or `.json.gz` file."""
    if path.name.endswith(".gz"):
        with gzip.open(path, "rb") as f:
            return json.loads(f.read().decode("utf-8"))
    return json.loads(path.read_text(encoding="utf-8"))


def find_table(folder: Path, stem: str, recursive: bool = False) -> Path | None:
    """`<stem>.json.gz` if present, else the older plain `<stem>.json`, else None."""
    hits = lambda name: sorted(folder.rglob(name)) if recursive else ([folder / name] if (folder / name).is_file() else [])
    for name in (f"{stem}.json.gz", f"{stem}.json"):
        found = hits(name)
        if found:
            return found[0]
    return None
