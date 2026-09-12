"""Paths and environment resolution.

Everything is resolved lazily so that importing designice never touches the
filesystem or the network - the MCP server imports this at startup and must
not fail just because a key is missing.
"""

from __future__ import annotations

import os
from pathlib import Path

# Image/video extensions we treat as design references. Video and GIF matter
# because a lot of the best motion work only reads as motion.
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".avif", ".gif"}
VIDEO_EXTS = {".mp4", ".webm", ".mov"}
MEDIA_EXTS = IMAGE_EXTS | VIDEO_EXTS

INDEX_DIRNAME = ".designice"
INDEX_FILENAME = "index.json"


def repo_root() -> Path:
    """Walk up from this file to the project root (the dir holding pyproject.toml)."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return Path.cwd()


def library_dir() -> Path:
    """Where design folders live. Override with DESIGNICE_LIBRARY."""
    override = os.environ.get("DESIGNICE_LIBRARY")
    if override:
        return Path(override).expanduser().resolve()
    return repo_root() / "docs" / "designs"


def output_dir() -> Path:
    """Where generated projects go: one folder per project under <repo>/output.

    A fixed convention means neither a person nor an agent has to decide (or be
    asked) where a build lands, and every generated site is findable in one
    place. Override with DESIGNICE_OUTPUT.
    """
    override = os.environ.get("DESIGNICE_OUTPUT")
    if override:
        return Path(override).expanduser().resolve()
    return repo_root() / "output"


def index_path(library: Path | None = None) -> Path:
    lib = library or library_dir()
    return lib / INDEX_DIRNAME / INDEX_FILENAME


def env(*names: str) -> str | None:
    """First non-empty value among the given env var names."""
    for name in names:
        val = os.environ.get(name)
        if val and val.strip():
            return val.strip()
    return None


def higgsfield_credentials() -> tuple[str, str] | None:
    key_id = env("HF_API_KEY_ID", "HIGGSFIELD_API_KEY_ID")
    secret = env("HF_API_KEY_SECRET", "HIGGSFIELD_API_KEY_SECRET")
    if key_id and secret:
        return key_id, secret
    return None
