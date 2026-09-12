"""Build, save and load the on-disk vector index.

One JSON file at `docs/designs/.designice/index.json`. Not a database, on
purpose: a design library is a few hundred rows, and a plain file is
inspectable, diffable and trivially portable between machines and agents.

The backend name and its state are written alongside the vectors, because a
query has to be projected into the same space the documents were. Reindexing
with a different backend rewrites everything.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from . import embed, ingest
from .config import index_path, library_dir

INDEX_VERSION = 2


def build(library: Path | None = None, backend_name: str | None = None) -> dict[str, Any]:
    root = library or library_dir()
    designs = ingest.scan(root)
    backend = embed.get_backend(backend_name)

    texts = [d.embed_text for d in designs]
    if texts:
        backend.fit(texts)
        vectors = backend.encode_documents(texts)
    else:
        vectors = []

    rows: list[dict[str, Any]] = []
    for design, vector in zip(designs, vectors):
        row = design.to_dict()
        row["embed_text"] = design.embed_text
        row["vector"] = vector
        rows.append(row)

    return {
        "version": INDEX_VERSION,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "library": str(root),
        "backend": backend.name,
        "backend_state": backend.state(),
        "dim": len(vectors[0]) if vectors else 0,
        "count": len(rows),
        "designs": rows,
    }


def save(index: dict[str, Any], library: Path | None = None) -> Path:
    path = index_path(library)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Compact separators keep the file small; vectors dominate the byte count.
    path.write_text(json.dumps(index, separators=(",", ":")), encoding="utf-8")
    return path


def load(library: Path | None = None) -> dict[str, Any]:
    path = index_path(library)
    if not path.exists():
        raise FileNotFoundError(
            f"no index at {path}. Run `designice index` after adding designs to {library or library_dir()}."
        )
    index = json.loads(path.read_text(encoding="utf-8"))
    if index.get("version") != INDEX_VERSION:
        raise ValueError(f"index at {path} is version {index.get('version')}; rerun `designice index`.")
    return index


def load_or_build(library: Path | None = None, backend_name: str | None = None,
                  refresh: bool = True) -> dict[str, Any]:
    """Load the index, building it if missing and refreshing it if the library changed.

    The staleness check is a folder scan plus a checksum per design - milliseconds
    for a library of hundreds. Paying that on every search means dropping a new
    folder into docs/designs is the whole act of adding a design: no reindex to
    remember, no stale result to be puzzled by. `designice index` still exists to
    force a rebuild or switch embedding backends.
    """
    try:
        index = load(library)
    except (FileNotFoundError, ValueError):
        index = build(library, backend_name)
        save(index, library)
        return index
    if refresh:
        stale, _ = is_stale(library)
        if stale:
            index = build(library, backend_name or index.get("backend"))
            save(index, library)
    return index


def is_stale(library: Path | None = None) -> tuple[bool, str]:
    """Cheap check: did any folder's checksum change, or did folders appear/vanish?"""
    try:
        index = load(library)
    except (FileNotFoundError, ValueError) as exc:
        return True, str(exc)
    on_disk = {d.name: d.checksum for d in ingest.scan(library)}
    indexed = {d["name"]: d.get("checksum", "") for d in index["designs"]}
    added = sorted(set(on_disk) - set(indexed))
    removed = sorted(set(indexed) - set(on_disk))
    changed = sorted(n for n in set(on_disk) & set(indexed) if on_disk[n] != indexed[n])
    if added or removed or changed:
        bits = []
        if added:
            bits.append(f"added: {', '.join(added)}")
        if removed:
            bits.append(f"removed: {', '.join(removed)}")
        if changed:
            bits.append(f"changed: {', '.join(changed)}")
        return True, "; ".join(bits)
    return False, "index is current"


def backend_for(index: dict[str, Any]) -> embed.Backend:
    return embed.backend_from_state(index["backend"], index.get("backend_state", {}))
