"""The `designice` command line.

Every subcommand can emit JSON (`--json`), because the primary consumer is an
agent, not a person. The human-readable output is the courtesy, not the
contract.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import brief as brief_mod
from . import embed, higgsfield, ingest, scaffold, search, store, taxonomy
from .config import library_dir, output_dir


def _library(args: argparse.Namespace) -> Path | None:
    return Path(args.library).expanduser().resolve() if getattr(args, "library", None) else None


def _emit(payload: Any, as_json: bool, text: str = "") -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False) if as_json else text)


def _resolve(index: dict, ref: str) -> dict | None:
    """Find a design by slug, folder name or title - people type all three."""
    needle = ref.strip().lower()
    for design in index["designs"]:
        if needle in (design.get("slug", "").lower(), design.get("name", "").lower()):
            return design
    for design in index["designs"]:
        if needle == design.get("title", "").lower():
            return design
    for design in index["designs"]:
        if needle in design.get("title", "").lower() or needle in design.get("slug", "").lower():
            return design
    return None


def _pick(index: dict, args: argparse.Namespace) -> tuple[dict, str]:
    """Either an explicit design, or the top search hit for the prompt."""
    prompt = " ".join(getattr(args, "query", []) or [])
    if getattr(args, "design", None):
        design = _resolve(index, args.design)
        if not design:
            raise SystemExit(f"no design matching {args.design!r}. Try `designice list`.")
        return design, prompt or design.get("use_case", "")
    if not prompt:
        raise SystemExit("give a prompt to match against, or --design <slug>")
    hits = search.search(prompt, index, k=1, filters=search.parse_filters(getattr(args, "filter", None)),
                         require_media=bool(getattr(args, "require_media", False)))
    if not hits:
        raise SystemExit("nothing in the library matched. Add designs, or loosen --filter"
                         + (" / drop --require-media" if getattr(args, "require_media", False) else "") + ".")
    return hits[0], prompt


def _overrides(args: argparse.Namespace) -> dict:
    """Collect the brand-override flags into the dict brief.build() expects.

    The CLI takes explicit values only. Turning "make it teal with a warm accent"
    into hexes is the skill's job - a model reads prose far better than a regex
    does, and the flags keep the contract inspectable.
    """
    keys = ("primary", "secondary", "ground", "ink", "font_display", "font_body",
            "style", "sections", "platform", "company")
    return {k: getattr(args, k, None) for k in keys if getattr(args, k, None)}


# --------------------------------------------------------------------------- commands

def cmd_index(args: argparse.Namespace) -> int:
    lib = _library(args)
    index = store.build(lib, args.backend)
    path = store.save(index, lib)
    requested = embed.resolve_backend_name(args.backend)
    payload = {"index": str(path), "backend": index["backend"], "dim": index["dim"],
               "count": index["count"], "library": index["library"]}
    note = ""
    if requested != index["backend"]:
        note = (f"\n  note: {requested} was requested but unavailable, so the zero-dependency "
                f"lexical backend was used. Set the relevant API key to upgrade.")
    _emit(payload, args.json,
          f"Indexed {index['count']} designs from {index['library']}\n"
          f"  backend: {index['backend']} ({index['dim']} dims)\n  written: {path}{note}")
    return 0


def _duplicate_descriptions(designs: list[ingest.Design]) -> list[list[str]]:
    """Groups of designs sharing a byte-identical description.

    This happens when someone copies a folder as a starting point and forgets
    to rewrite the text. The copies then match every query the original does,
    and the brief for one describes the other.
    """
    import hashlib
    groups: dict[str, list[str]] = {}
    for d in designs:
        text = d.description.strip()
        if text:
            groups.setdefault(hashlib.sha256(text.encode()).hexdigest(), []).append(d.slug)
    return [sorted(v) for v in groups.values() if len(v) > 1]


def cmd_status(args: argparse.Namespace) -> int:
    lib = _library(args)
    stale, reason = store.is_stale(lib)
    designs = ingest.scan(lib)
    duplicates = _duplicate_descriptions(designs)
    payload = {"library": str(lib or library_dir()), "designs_on_disk": len(designs),
               "with_media": sum(1 for d in designs if d.media),
               "stale": stale, "reason": reason,
               "duplicate_descriptions": duplicates,
               "embed_backend_available": embed.resolve_backend_name(),
               "higgsfield": higgsfield.available()}
    text = (f"Library:   {payload['library']}\n"
            f"Designs:   {payload['designs_on_disk']} ({payload['with_media']} with imagery)\n"
            f"Index:     {'STALE - run `designice index`' if stale else 'current'} ({reason})\n"
            f"Embedding: {payload['embed_backend_available']}\n"
            f"Higgsfield: {'configured' if payload['higgsfield'] else 'no credentials (prompt-only mode)'}")
    for group in duplicates:
        text += f"\n  ! identical descriptions: {', '.join(group)} - one of them describes the wrong design"
    _emit(payload, args.json, text)
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    index = store.load_or_build(_library(args))
    hits = search.search(" ".join(args.query), index, k=args.k,
                         filters=search.parse_filters(args.filter),
                         require_media=args.require_media)
    if args.json:
        _emit(hits, True)
        return 0
    if not hits:
        print("no matches")
        return 0
    for i, hit in enumerate(hits, 1):
        print(f"{i}. {search.why(hit)}")
        if hit.get("use_case"):
            print(f"     {hit['use_case']}")
        print(f"     folder: {hit['path']}  media: {len(hit.get('media', []))}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    index = store.load_or_build(_library(args))
    filters = search.parse_filters(args.filter)
    rows = [d for d in index["designs"] if search._passes(d, filters)]
    if args.json:
        _emit([{k: v for k, v in r.items() if k != "vector"} for r in rows], True)
        return 0
    for row in rows:
        primary = row.get("primary", {})
        summary = " / ".join(", ".join(primary.get(f, [])[:2])
                             for f in ("industry", "style") if primary.get(f))
        print(f"{row['slug']:<44} {summary}")
    print(f"\n{len(rows)} design(s) in {index['library']}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    index = store.load_or_build(_library(args))
    design = _resolve(index, args.design)
    if not design:
        raise SystemExit(f"no design matching {args.design!r}")
    payload = {k: v for k, v in design.items() if k != "vector"}
    if args.json:
        _emit(payload, True)
        return 0
    print(f"{design['title']}  ({design['slug']})")
    if design.get("use_case"):
        print(f"  {design['use_case']}")
    print(f"  folder: {design['path']}")
    for facet, tags in sorted(design.get("tags", {}).items()):
        print(f"  {facet:<10} {', '.join(tags)}")
    if design.get("media"):
        print("  media:")
        for m in design["media"]:
            size = f" {m['width']}x{m['height']} ({m.get('shape')})" if m.get("width") else ""
            print(f"    - {m['path']}{size}")
    print()
    print(design.get("description", ""))
    return 0


def cmd_tags(args: argparse.Namespace) -> int:
    payload = taxonomy.facets()
    if args.json:
        _emit(payload, True)
        return 0
    for facet, tags in payload.items():
        print(f"\n{facet} ({len(tags)})")
        print("  " + ", ".join(tags))
    return 0


def cmd_brief(args: argparse.Namespace) -> int:
    index = store.load_or_build(_library(args))
    design, prompt = _pick(index, args)
    built = brief_mod.build(design, prompt, project=args.project or "", overrides=_overrides(args))
    _emit(built, args.json, brief_mod.render_markdown(built))
    return 0


def _project_and_out(args: argparse.Namespace, design: dict) -> tuple[str, Path]:
    """Resolve the project name and where it lands.

    `--project` names it; failing that, the output folder name; failing that,
    the matched design's slug. The location is output/<project> unless `--out`
    says otherwise - so a plain `designice scaffold "..."` always produces a
    findable folder and never needs a follow-up question.
    """
    if args.out:
        out = Path(args.out).expanduser().resolve()
        project = args.project or out.name
    else:
        project = args.project or (args.company if getattr(args, "company", None) else None) \
                  or design.get("slug", "site")
        out = output_dir() / ingest.slugify(project)
    return project, out


def cmd_scaffold(args: argparse.Namespace) -> int:
    index = store.load_or_build(_library(args))
    design, prompt = _pick(index, args)
    project, out = _project_and_out(args, design)
    built = brief_mod.build(design, prompt, project=project, overrides=_overrides(args))
    if built["platform"] == "mobile":
        result = scaffold.generate_expo(built, out, force=args.force)
    else:
        result = scaffold.generate(built, out, force=args.force)
    if args.json:
        _emit(result, True)
        return 0
    print(f"Scaffolded {project} ({built['platform']}) from '{design['title']}' into {result['out_dir']}")
    if built["template_tokens"]["source"] == "fallback":
        print("  ! template has no authored tokens - read them off the hero screenshot and write meta.json")
    for note in built.get("notes", []):
        print(f"  ! {note}")
    print(f"  {len(result['files'])} files, {len(result['sections'])} sections: "
          f"{', '.join(result['sections'])}")
    print(f"  colours: {result['colours']}")
    if result["reference_media"]:
        print(f"  reference imagery copied: {', '.join(result['reference_media'])}")
    for note in result["font_notes"]:
        print(f"  ! {note}")
    print("\nNext:")
    for step in result["next_steps"]:
        print(f"  {step}")
    return 0


def cmd_images(args: argparse.Namespace) -> int:
    index = store.load_or_build(_library(args))
    design, prompt = _pick(index, args)
    project, project_dir = _project_and_out(args, design)
    built = brief_mod.build(design, prompt, project=project, overrides=_overrides(args))
    prompts = built["image_prompts"]
    if args.slot:
        prompts = [p for p in prompts if p["slot"] in args.slot]
    # Images default to the project's public/ folder so a scaffolded site can
    # reference them straight away; --out still wins when given.
    out = Path(args.out).expanduser().resolve() if args.out else project_dir / "public"
    results = higgsfield.generate_set(prompts, out, model=args.model, dry_run=args.dry_run)
    if args.json:
        _emit(results, True)
        return 0
    for r in results:
        print(f"[{r['status']}] {r['slot']} ({r['aspect_ratio']})")
        if r.get("files"):
            print("   saved: " + ", ".join(r["files"]))
        if r.get("error"):
            print(f"   error: {r['error']}")
        if r["status"] == "prompt-only":
            print(f"   {r['prompt']}")
    return 0


def cmd_new(args: argparse.Namespace) -> int:
    lib = _library(args) or library_dir()
    folder = lib / args.name
    folder.mkdir(parents=True, exist_ok=True)
    desc = folder / "description.txt"
    if not desc.exists():
        desc.write_text(
            f"# {args.name}\n\n"
            "Describe this design the way you would to a colleague who cannot see it.\n"
            "What is it for, what does it look like, how does it move, what makes it work.\n"
            "Name real colours as hex, real fonts, real spacing. Specifics are what make\n"
            "this design findable and reproducible.\n", encoding="utf-8")
    print(f"Created {folder}\n  add images to the folder, write {desc.name}, then run `designice index`")
    return 0


def cmd_annotate(args: argparse.Namespace) -> int:
    """Write a starter meta.json from what the description already implies.

    Auto-detected tags drive recall well but should not drive a build brief -
    that is what authored tags are for. This gives a person the detected set as
    a starting point to correct, which is far less work than writing it blank.
    """
    lib = _library(args) or library_dir()
    folder = lib / args.design
    if not folder.is_dir():
        index = store.load_or_build(_library(args))
        design = _resolve(index, args.design)
        if not design:
            raise SystemExit(f"no design folder matching {args.design!r}")
        folder = lib / design["path"]

    loaded = ingest.load_design(folder, lib)
    if not loaded:
        raise SystemExit(f"{folder} has no description or media yet")

    target = folder / "meta.json"
    if target.exists() and not args.force:
        raise SystemExit(f"{target} already exists (pass --force to overwrite)")

    payload = {
        "title": loaded.title,
        "use_case": loaded.use_case or "Website for ...",
        "tags": {facet: tags for facet, tags in loaded.tags.items() if facet != "extra"},
        "palette": loaded.palette,
        "fonts": loaded.fonts,
        "source": loaded.source,
        "reference_url": loaded.reference_url,
    }
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {target}\n"
          "Edit it: put the *primary* style and industry first in each list, drop wrong tags,\n"
          "and fill in use_case. Authored order is what the build brief follows.")
    return 0


def cmd_snapshot(args: argparse.Namespace) -> int:
    import json as _json
    import pathlib as _pathlib

    from . import snapshot

    try:
        manifest = snapshot.capture(
            args.url, args.out, desktop=args.desktop, mobile=args.mobile, only=args.only,
            sections=not args.no_sections, settle_ms=args.settle, timeout_ms=args.timeout,
        )
    except snapshot.SnapshotUnavailable as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(_json.dumps(manifest, indent=2))
        return 0
    for screen in manifest["screens"]:
        flag = "  ! horizontal overflow" if screen.get("overflow_x") else ""
        print(f"{screen['viewport']:<8} {screen['width']}x{screen['height']}  page {screen['page_height']}px"
              f"  {len(screen['sections'])} regions{flag}")
        for sec in screen["sections"]:
            print(f"  {sec['slug']:<20} {sec['height']:>5}px  cols {sec['columns']}  {sec['file'] or '-'}")
    if manifest["errors"]:
        print(f"{len(manifest['errors'])} console/page errors - see manifest.json")
    print(f"wrote {_pathlib.Path(args.out) / 'manifest.json'}")
    return 0


def cmd_mcp(args: argparse.Namespace) -> int:
    from .mcp_server import serve
    serve()
    return 0


def snapshot_defaults() -> tuple[str, str]:
    from . import snapshot
    return snapshot.DEFAULT_DESKTOP, snapshot.DEFAULT_MOBILE


# --------------------------------------------------------------------------- parser

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="designice",
        description="Vector-matched design library that turns a prompt into a standalone Next.js site.",
    )
    parser.add_argument("--library", help="design library folder (default: docs/designs)")
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name: str, func, help_text: str) -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--json", action="store_true", help="emit JSON")
        p.set_defaults(func=func)
        return p

    p = add("index", cmd_index, "scan the library and build the vector index")
    p.add_argument("--backend", help="voyage | openai | local | lexical (default: auto)")

    add("status", cmd_status, "show library, index freshness and backend availability")

    def add_override_flags(p: argparse.ArgumentParser) -> None:
        g = p.add_argument_group("brand overrides (applied on top of the matched design)")
        g.add_argument("--primary", help="brand colour for CTAs, links, focus (#hex)")
        g.add_argument("--secondary", help="second brand colour for tags, secondary buttons (#hex)")
        g.add_argument("--ground", help="page background (#hex) - only if you mean to change the mode")
        g.add_argument("--ink", help="body text colour (#hex)")
        g.add_argument("--font-display", dest="font_display", help="headline font")
        g.add_argument("--font-body", dest="font_body", help="body font")
        g.add_argument("--style", help="override the visual register (see `designice tags`)")
        g.add_argument("--sections", help="comma-separated section list, replaces the derived one")
        g.add_argument("--platform", choices=["web", "mobile"], help="web = Next.js, mobile = Expo")
        g.add_argument("--company", help="the company or product the site is for")

    p = add("search", cmd_search, "find the closest designs to a prompt")
    p.add_argument("query", nargs="+")
    p.add_argument("-k", type=int, default=5)
    p.add_argument("--filter", action="append", help="facet=tag[,tag] (repeatable)")
    p.add_argument("--require-media", dest="require_media", action="store_true",
                   help="only designs with screenshots (for template reproduction)")

    p = add("list", cmd_list, "list designs in the library")
    p.add_argument("--filter", action="append")

    p = add("show", cmd_show, "print one design in full")
    p.add_argument("design")

    add("tags", cmd_tags, "print the tag vocabulary")

    p = add("brief", cmd_brief, "build a design brief from a prompt")
    p.add_argument("query", nargs="*")
    p.add_argument("--design", help="use this design instead of searching")
    p.add_argument("--project", help="project name")
    p.add_argument("--filter", action="append")
    p.add_argument("--require-media", dest="require_media", action="store_true")
    add_override_flags(p)

    p = add("scaffold", cmd_scaffold, "generate a Next.js (web) or Expo (mobile) project")
    p.add_argument("query", nargs="*")
    p.add_argument("--out", help="output directory (default: output/<project>)")
    p.add_argument("--design", help="use this design instead of searching")
    p.add_argument("--project", help="project name (default: output folder name)")
    p.add_argument("--filter", action="append")
    p.add_argument("--require-media", dest="require_media", action="store_true")
    p.add_argument("--force", action="store_true", help="overwrite a non-empty output dir")
    add_override_flags(p)

    p = add("images", cmd_images, "generate reference imagery with Higgsfield")
    p.add_argument("query", nargs="*")
    p.add_argument("--out", help="output directory (default: output/<project>/public)")
    p.add_argument("--design")
    p.add_argument("--project")
    p.add_argument("--company")
    p.add_argument("--filter", action="append")
    p.add_argument("--slot", action="append", help="only these slots (hero, feature-texture, ...)")
    p.add_argument("--model", default=higgsfield.DEFAULT_MODEL)
    p.add_argument("--dry-run", action="store_true", help="print prompts without calling the API")

    p = add("new", cmd_new, "create an empty design folder with a description stub")
    p.add_argument("name")

    p = add("annotate", cmd_annotate, "write a starter meta.json for a design")
    p.add_argument("design")
    p.add_argument("--force", action="store_true")

    p = add("snapshot", cmd_snapshot, "screenshot a running build for the critique stage (needs playwright)")
    p.add_argument("url", help="where the build is running, e.g. http://localhost:3000")
    p.add_argument("--out", default="verify/critique", help="folder for the images + manifest.json")
    p.add_argument("--desktop", default=snapshot_defaults()[0], help="desktop viewport (default 1440x900)")
    p.add_argument("--mobile", default=snapshot_defaults()[1], help="mobile viewport (default 390x844)")
    p.add_argument("--only", choices=["desktop", "mobile"], help="capture one viewport only")
    p.add_argument("--no-sections", dest="no_sections", action="store_true",
                   help="skip the per-region screenshots")
    p.add_argument("--settle", type=int, default=600, help="ms to wait after load before capturing")
    p.add_argument("--timeout", type=int, default=30000, help="navigation timeout in ms")

    add("mcp", cmd_mcp, "run the MCP server on stdio")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, ValueError, FileExistsError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
