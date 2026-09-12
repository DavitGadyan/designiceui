"""Read the design library off disk.

The library is deliberately a folder of folders, because that is the format a
person will actually maintain:

    docs/designs/
      aurora-fintech/
        hero.png
        pricing.webp
        description.txt      <- plain English, no schema to learn
        meta.json            <- optional; only when you want to override

Everything else - tags, palette hints, the text that gets embedded - is derived.
Hand-written `meta.json` values always win over derived ones, because a person
correcting the machine should not have to fight it twice.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from . import taxonomy
from .config import IMAGE_EXTS, MEDIA_EXTS, VIDEO_EXTS, INDEX_DIRNAME, library_dir

DESCRIPTION_NAMES = ("description.txt", "description.md", "readme.md", "notes.txt")
META_NAMES = ("meta.json", "design.json", "meta.yaml", "meta.yml")
HEX_RE = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b")


def slugify(value: str) -> str:
    """Folder names are for humans; slugs are how the CLI and MCP address a design.

    Real folders are called things like "Kayenpeppa.com - Design Studio Portfolio
    2026", so every lookup path needs a stable, typeable identifier alongside the
    display name.
    """
    value = value.lower().replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return re.sub(r"-{2,}", "-", value).strip("-") or "design"


@dataclass
class Design:
    name: str
    slug: str
    title: str
    path: str
    description: str
    tags: dict[str, list[str]] = field(default_factory=dict)
    primary: dict[str, list[str]] = field(default_factory=dict)
    tag_list: list[str] = field(default_factory=list)
    media: list[dict[str, str]] = field(default_factory=list)
    palette: list[str] = field(default_factory=list)
    fonts: list[str] = field(default_factory=list)
    use_case: str = ""
    source: str = ""
    reference_url: str = ""
    checksum: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def embed_text(self) -> str:
        """What actually goes to the encoder.

        Title and use-case lead because they are the highest-signal lines, then
        the description, then the tag names spelled out as words. Tags are
        included as text rather than only as filters so that a query mentioning
        "brutalist" still scores against a design whose prose never says it but
        whose tags do.
        """
        parts = [self.title]
        if self.use_case:
            parts.append(self.use_case)
        parts.append(self.description)
        readable = [tag.replace("-", " ") for tag in self.tag_list_readable()]
        if readable:
            parts.append("Tags: " + ", ".join(readable))
        return "\n".join(p for p in parts if p).strip()

    def tag_list_readable(self) -> list[str]:
        return [t.split(":", 1)[1] for t in self.tag_list]


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def _load_meta(folder: Path) -> dict[str, Any]:
    """Optional per-design overrides. JSON always; YAML only if PyYAML is around."""
    for name in META_NAMES:
        candidate = folder / name
        if not candidate.exists():
            continue
        raw = _read_text(candidate)
        if not raw:
            continue
        if candidate.suffix == ".json":
            try:
                return json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{candidate} is not valid JSON: {exc}") from exc
        try:
            import yaml  # type: ignore
        except ImportError:
            raise ValueError(
                f"{candidate} needs PyYAML to parse. Use meta.json instead, or pip install pyyaml."
            )
        return yaml.safe_load(raw) or {}
    return {}


def _find_description(folder: Path) -> str:
    """Preferred filename first, then any .txt, so people can name it anything."""
    lowered = {p.name.lower(): p for p in folder.iterdir() if p.is_file()}
    for name in DESCRIPTION_NAMES:
        if name in lowered:
            return _read_text(lowered[name])
    txts = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in {".txt", ".md"})
    return "\n\n".join(filter(None, (_read_text(p) for p in txts)))


# Magic bytes, because screenshots dragged out of a browser or a design tool
# very often arrive with no extension at all ("image_original"). Filtering on
# suffix alone silently drops exactly the files a user just added.
_SIGNATURES: list[tuple[bytes, str, str]] = [
    (b"\x89PNG\r\n\x1a\n", "png", "image"),
    (b"\xff\xd8\xff", "jpg", "image"),
    (b"GIF87a", "gif", "image"),
    (b"GIF89a", "gif", "image"),
]


# A browser that dies mid-download leaves a file with a valid PNG header and no
# ending. It sniffs as an image, sorts first, and ends up as the first thing an
# agent is told to look at. Refuse partial-download suffixes outright, and check
# that a PNG actually ends.
_PARTIAL_SUFFIXES = {".crdownload", ".part", ".partial", ".download", ".tmp"}
_PNG_IEND = b"IEND\xaeB`\x82"


def _png_is_complete(path: Path) -> bool:
    try:
        with path.open("rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            if size < 16:
                return False
            fh.seek(size - 8)
            return fh.read(8) == _PNG_IEND
    except OSError:
        return False


def _sniff(path: Path) -> tuple[str, str] | None:
    """Return (format, kind) for a media file, or None if it isn't one."""
    suffix = path.suffix.lower()
    if suffix in _PARTIAL_SUFFIXES:
        return None
    if suffix in MEDIA_EXTS:
        if suffix == ".png" and not _png_is_complete(path):
            return None
        return suffix.lstrip("."), ("video" if suffix in VIDEO_EXTS else "image")
    try:
        with path.open("rb") as fh:
            head = fh.read(32)
    except OSError:
        return None
    for magic, fmt, kind in _SIGNATURES:
        if head.startswith(magic):
            if fmt == "png" and not _png_is_complete(path):
                return None
            return fmt, kind
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp", "image"
    if head[4:8] == b"ftyp":  # ISO base media: mp4, mov, avif, heic
        brand = head[8:12]
        if brand in (b"avif", b"avis"):
            return "avif", "image"
        return "mp4", "video"
    return None


def _dimensions(path: Path, fmt: str) -> tuple[int, int] | None:
    """Width/height without pulling in Pillow.

    Worth the few lines: a 3226x3266 capture is a whole scrolled page, while a
    1600x900 one is a single viewport. An agent looking at the reference needs
    to know which it is before it starts copying layout from it.
    """
    try:
        with path.open("rb") as fh:
            head = fh.read(64)
            if fmt == "png" and head[12:16] == b"IHDR":
                return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")
            if fmt == "gif":
                return int.from_bytes(head[6:8], "little"), int.from_bytes(head[8:10], "little")
            if fmt == "webp" and head[12:16] == b"VP8X":
                w = int.from_bytes(head[24:27], "little") + 1
                h = int.from_bytes(head[27:30], "little") + 1
                return w, h
            if fmt in ("jpg", "jpeg"):
                fh.seek(2)
                while True:
                    marker = fh.read(2)
                    if len(marker) < 2 or marker[0] != 0xFF:
                        return None
                    if 0xC0 <= marker[1] <= 0xCF and marker[1] not in (0xC4, 0xC8, 0xCC):
                        fh.read(3)
                        h = int.from_bytes(fh.read(2), "big")
                        w = int.from_bytes(fh.read(2), "big")
                        return w, h
                    size = int.from_bytes(fh.read(2), "big")
                    if size < 2:
                        return None
                    fh.seek(size - 2, 1)
    except (OSError, ValueError):
        return None
    return None


def _collect_media(folder: Path, root: Path) -> list[dict[str, Any]]:
    """Media sorted so a file that looks like a hero shows up first."""
    items: list[tuple[int, str, dict[str, Any]]] = []
    for p in sorted(folder.rglob("*")):
        if not p.is_file() or INDEX_DIRNAME in p.parts or p.name.startswith("."):
            continue
        sniffed = _sniff(p)
        if not sniffed:
            continue
        fmt, kind = sniffed
        stem = p.stem.lower()
        if any(k in stem for k in ("hero", "01", "1-", "cover", "main", "full")):
            rank = 0
        elif kind == "video":
            rank = 2
        else:
            rank = 1
        entry: dict[str, Any] = {
            "path": str(p.relative_to(root)), "kind": kind, "name": p.name, "format": fmt,
        }
        size = _dimensions(p, fmt)
        if size:
            entry["width"], entry["height"] = size
            ratio = size[0] / size[1] if size[1] else 0
            # A capture much taller than it is wide is a full scrolled page, not
            # a viewport - that changes how an agent should read it.
            entry["shape"] = ("full-page" if ratio < 1.2 else
                              "viewport" if ratio < 2.2 else "wide-banner")
        items.append((rank, p.name, entry))
    items.sort(key=lambda t: (t[0], t[1]))
    return [item for _, _, item in items]


def _is_dark_hex(hexstr: str) -> bool:
    h = hexstr.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return False
    try:
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return False
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) < 110


def _titleize(slug: str) -> str:
    words = re.split(r"[-_\s\u2013\u2014]+", slug)
    return " ".join(w.capitalize() if w.islower() else w for w in words if w)


def _manual_tags(manual: Any) -> dict[str, list[str]]:
    """Hand-authored tags with their order preserved.

    Order carries intent: a design tagged style ["luxury", "minimal"] is
    primarily luxurious. Sorting that away is how a brief ends up calling a
    private-bank page "glassmorphic" because g sorts before l.
    """
    out: dict[str, list[str]] = {}
    if isinstance(manual, dict):
        for facet, tags in manual.items():
            values = [tags] if isinstance(tags, str) else list(tags or [])
            out[facet] = [t for t in values if t]
    elif isinstance(manual, list):
        for tag in manual:
            for facet, known in taxonomy.FACETS.items():
                if tag in known:
                    out.setdefault(facet, []).append(tag)
                    break
    return {f: v for f, v in out.items() if v}


def _merge_tags(derived: dict[str, list[str]], manual: Any) -> dict[str, list[str]]:
    """Union derived and manual tags, keeping only tags in the controlled vocabulary.

    A manual tag outside the vocabulary is kept under an `extra` facet rather
    than dropped - losing someone's hand-written label silently is worse than
    carrying an uncontrolled one.
    """
    merged = {facet: list(tags) for facet, tags in derived.items()}
    if isinstance(manual, dict):
        for facet, tags in manual.items():
            values = [tags] if isinstance(tags, str) else list(tags or [])
            known = taxonomy.FACETS.get(facet, {})
            for tag in values:
                bucket = facet if tag in known else ("extra" if facet not in taxonomy.FACETS else facet)
                merged.setdefault(bucket, [])
                if tag not in merged[bucket]:
                    merged[bucket].append(tag)
    elif isinstance(manual, list):  # flat ["fintech", "dark"] - place by lookup
        for tag in manual:
            placed = False
            for facet, known in taxonomy.FACETS.items():
                if tag in known:
                    merged.setdefault(facet, [])
                    if tag not in merged[facet]:
                        merged[facet].append(tag)
                    placed = True
                    break
            if not placed:
                merged.setdefault("extra", [])
                if tag not in merged["extra"]:
                    merged["extra"].append(tag)
    manual_map = _manual_tags(manual)
    out: dict[str, list[str]] = {}
    for facet, tags in merged.items():
        resolved = taxonomy.resolve_exclusives(facet, tags, manual_map.get(facet, ()))
        if resolved:
            out[facet] = sorted(set(resolved))
    return out


def load_design(folder: Path, root: Path | None = None) -> Design | None:
    """Turn one folder into a Design. Returns None for folders with nothing usable."""
    root = root or folder.parent
    description = _find_description(folder)
    media = _collect_media(folder, root)
    if not description and not media:
        return None

    meta = _load_meta(folder)
    name = folder.name
    title = str(meta.get("title") or _titleize(name))
    use_case = str(meta.get("use_case") or meta.get("useCase") or "")

    # Tag from every scrap of text we have, including the folder name and file
    # names - "dark-brutalist-hero.png" is a real signal people rely on.
    taggable = "\n".join([title, use_case, description, name.replace("-", " "),
                          " ".join(m["name"] for m in media)])
    tags = _merge_tags(taxonomy.detect_tags(taggable), meta.get("tags"))

    # `primary` is the subset we trust enough to drive a build brief. A design
    # description that ends "use for fintech, legal and music" is genuinely
    # useful for recall, but it must not convince the brief that a private-bank
    # page is a music site. So primary comes only from authored tags plus the
    # title and one-line use case - never from the body prose.
    headline = "\n".join([title, use_case, name.replace("-", " ")])
    primary = _manual_tags(meta.get("tags"))
    for facet, detected in taxonomy.detect_tags(headline).items():
        bucket = primary.setdefault(facet, [])
        bucket.extend(t for t in detected if t not in bucket)

    # Authored palette leads: meta lists colours in role order (ground, surface,
    # accent, text), which the brief relies on. Hexes scraped from the prose
    # follow as extras.
    #
    # Validate loudly. A palette written as [{"role": ..., "value": ...}] used to
    # stringify into nonsense, fail the hex check downstream, and silently drop
    # the whole build back to generic defaults - the worst kind of failure,
    # because everything still "works".
    authored = meta.get("palette", [])
    if not isinstance(authored, list) or not all(isinstance(c, str) and HEX_RE.fullmatch(c.strip()) for c in authored):
        raise ValueError(
            f"{folder.name}/meta.json: \"palette\" must be a list of hex strings in role order, "
            f"e.g. [\"#0A0A0B\", \"#141416\", \"#C8A96A\", \"#E8E6E1\"], got {authored!r}"
        )
    authored_fonts = meta.get("fonts", [])
    if not isinstance(authored_fonts, list) or not all(isinstance(f, str) for f in authored_fonts):
        raise ValueError(f"{folder.name}/meta.json: \"fonts\" must be a list of font names, got {authored_fonts!r}")
    palette = list(dict.fromkeys(
        [c.strip().upper() for c in authored] + [c.upper() for c in HEX_RE.findall(description)]
    ))
    fonts = [f.strip() for f in authored_fonts if f.strip()]

    if "dark" in tags.get("palette", []) and "light" in tags.get("palette", []) \
            and not _manual_tags(meta.get("tags")).get("palette"):
        # No authored answer, so let the palette itself decide: the first colour
        # is the ground, and its luminance is not a matter of opinion.
        drop = "light" if (palette and _is_dark_hex(palette[0])) else "dark"
        tags["palette"] = [t for t in tags["palette"] if t != drop]

    design = Design(
        name=name,
        slug=slugify(name),
        title=title,
        path=str(folder.relative_to(root)) if folder != root else ".",
        description=description,
        tags=tags,
        primary={f: v for f, v in primary.items() if v},
        tag_list=taxonomy.flatten_tags(tags),
        media=media,
        palette=palette,
        fonts=fonts,
        use_case=use_case,
        source=str(meta.get("source") or ""),
        reference_url=str(meta.get("reference_url") or meta.get("url") or ""),
    )
    design.checksum = hashlib.sha256(
        json.dumps(
            {"d": description, "m": [m["path"] for m in media], "meta": meta},
            sort_keys=True, default=str,
        ).encode()
    ).hexdigest()[:16]
    return design


def scan(library: Path | None = None) -> list[Design]:
    """Every design folder in the library, sorted by name."""
    root = library or library_dir()
    if not root.exists():
        return []
    designs: list[Design] = []
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        if folder.name.startswith(".") or folder.name == INDEX_DIRNAME:
            continue
        design = load_design(folder, root)
        if design:
            designs.append(design)
    return designs
