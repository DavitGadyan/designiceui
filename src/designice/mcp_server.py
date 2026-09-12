"""MCP server exposing the design library to any agent that speaks MCP.

Hand-rolled JSON-RPC over stdio rather than the MCP SDK, for one reason: this
must run with nothing installed. `designice mcp` works on a bare Python 3.10+,
which means registering it is one command and never a dependency problem.

Register it with:

    claude mcp add designice --scope user -- python3 -m designice mcp

The protocol surface is small and stable: initialize, tools/list, tools/call,
ping, and the initialized notification.

All stdout is protocol. Anything diagnostic goes to stderr, because a stray
print corrupts the stream and the client just sees the server die.
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from typing import Any, Callable

from . import brief as brief_mod
from . import embed, higgsfield, ingest, scaffold, search, store, taxonomy
from .config import library_dir, output_dir

SERVER_NAME = "designice"
SERVER_VERSION = "0.1.0"
SUPPORTED_PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")
DEFAULT_PROTOCOL = "2025-06-18"


def _log(message: str) -> None:
    print(f"[designice-mcp] {message}", file=sys.stderr, flush=True)


# --------------------------------------------------------------------------- helpers

def _index(args: dict[str, Any]) -> dict[str, Any]:
    lib = Path(args["library"]).expanduser() if args.get("library") else None
    return store.load_or_build(lib)


def _resolve(index: dict[str, Any], ref: str) -> dict[str, Any] | None:
    needle = (ref or "").strip().lower()
    if not needle:
        return None
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


def _select(index: dict[str, Any], args: dict[str, Any]) -> tuple[dict[str, Any], str]:
    prompt = (args.get("prompt") or "").strip()
    if args.get("design"):
        design = _resolve(index, args["design"])
        if not design:
            raise ValueError(f"no design matching {args['design']!r}; call design_list to see what exists")
        return design, prompt or design.get("use_case", "")
    if not prompt:
        raise ValueError("provide `prompt` to match against, or `design` to pick one directly")
    hits = search.search(prompt, index, k=1, filters=_filters(args),
                         require_media=bool(args.get("require_media")))
    if not hits:
        raise ValueError("no design matched; loosen filters, drop require_media, or add designs")
    return hits[0], prompt


def _overrides(args: dict[str, Any]) -> dict[str, Any]:
    """Brand overrides arrive as a nested object; pass through only known keys."""
    raw = args.get("overrides") or {}
    return {k: v for k, v in raw.items() if k in brief_mod.OVERRIDE_KEYS}


def _filters(args: dict[str, Any]) -> dict[str, list[str]]:
    raw = args.get("filters") or {}
    if isinstance(raw, str):
        return search.parse_filters([raw])
    return {facet: ([tags] if isinstance(tags, str) else list(tags))
            for facet, tags in raw.items() if tags}


def _slim(design: dict[str, Any]) -> dict[str, Any]:
    """Everything an agent needs about a design, minus the vector."""
    return {k: v for k, v in design.items() if k not in ("vector", "embed_text")}


# --------------------------------------------------------------------------- tools

def tool_design_search(args: dict[str, Any]) -> dict[str, Any]:
    index = _index(args)
    hits = search.search(args["prompt"], index, k=int(args.get("k", 5)), filters=_filters(args),
                         require_media=bool(args.get("require_media")))
    return {
        "query": args["prompt"],
        "backend": index["backend"],
        "library": index["library"],
        "results": [
            {**_slim(h), "why": search.why(h)} for h in hits
        ],
    }


def tool_design_get(args: dict[str, Any]) -> dict[str, Any]:
    index = _index(args)
    design = _resolve(index, args["design"])
    if not design:
        raise ValueError(f"no design matching {args['design']!r}")
    return _slim(design)


def tool_design_list(args: dict[str, Any]) -> dict[str, Any]:
    index = _index(args)
    filters = _filters(args)
    rows = [d for d in index["designs"] if search._passes(d, filters)]
    return {
        "library": index["library"],
        "count": len(rows),
        "designs": [
            {"slug": r["slug"], "title": r["title"], "use_case": r.get("use_case", ""),
             "primary": r.get("primary", {}), "media": len(r.get("media", []))}
            for r in rows
        ],
    }


def tool_design_tags(args: dict[str, Any]) -> dict[str, Any]:
    return {"facets": taxonomy.facets(),
            "usage": "filter with {\"industry\": [\"fintech\"], \"motion\": [\"3d-webgl\"]}; "
                     "a design must match at least one tag in every facet named"}


def tool_design_brief(args: dict[str, Any]) -> dict[str, Any]:
    index = _index(args)
    design, prompt = _select(index, args)
    built = brief_mod.build(design, prompt, project=args.get("project", ""), overrides=_overrides(args))
    return {"brief": built, "markdown": brief_mod.render_markdown(built)}


def _scaffold(args: dict[str, Any], platform: str) -> dict[str, Any]:
    index = _index(args)
    design, prompt = _select(index, args)
    overrides_in = args.get("overrides") or {}
    if args.get("out_dir"):
        out = Path(args["out_dir"]).expanduser().resolve()
        project = args.get("project") or out.name
    else:
        # Same convention as the CLI: every generated project lands in
        # output/<project>, so an agent never has to ask where to put it.
        project = args.get("project") or overrides_in.get("company") or design.get("slug", "site")
        out = output_dir() / ingest.slugify(project)
    overrides = {**_overrides(args), "platform": platform}
    built = brief_mod.build(design, prompt, project=project, overrides=overrides)
    generator = scaffold.generate_expo if platform == "mobile" else scaffold.generate
    result = generator(built, out, force=bool(args.get("force")))
    result["brief_markdown"] = brief_mod.render_markdown(built)
    result["template_token_source"] = built["template_tokens"]["source"]
    result["notes"] = built.get("notes", [])
    return result


def tool_scaffold_nextjs(args: dict[str, Any]) -> dict[str, Any]:
    return _scaffold(args, "web")


def tool_scaffold_expo(args: dict[str, Any]) -> dict[str, Any]:
    return _scaffold(args, "mobile")


def tool_higgsfield_generate(args: dict[str, Any]) -> dict[str, Any]:
    out = Path(args["out_dir"]).expanduser().resolve()
    if args.get("prompts"):
        prompts = [{"slot": p.get("slot", f"image-{i + 1}"), "prompt": p["prompt"],
                    "aspect_ratio": p.get("aspect_ratio", "16:9")}
                   for i, p in enumerate(args["prompts"])]
    else:
        index = _index(args)
        design, prompt = _select(index, args)
        prompts = brief_mod.build(design, prompt)["image_prompts"]
        if args.get("slots"):
            wanted = set(args["slots"])
            prompts = [p for p in prompts if p["slot"] in wanted]
    results = higgsfield.generate_set(prompts, out,
                                      model=args.get("model", higgsfield.DEFAULT_MODEL),
                                      dry_run=bool(args.get("dry_run")))
    return {"out_dir": str(out), "configured": higgsfield.available(), "results": results}


def tool_library_index(args: dict[str, Any]) -> dict[str, Any]:
    lib = Path(args["library"]).expanduser() if args.get("library") else None
    index = store.build(lib, args.get("backend"))
    path = store.save(index, lib)
    return {"index": str(path), "backend": index["backend"], "dim": index["dim"],
            "count": index["count"], "library": index["library"]}


def tool_library_status(args: dict[str, Any]) -> dict[str, Any]:
    lib = Path(args["library"]).expanduser() if args.get("library") else None
    stale, reason = store.is_stale(lib)
    return {"library": str(lib or library_dir()),
            "designs_on_disk": len(ingest.scan(lib)),
            "stale": stale, "reason": reason,
            "embed_backend": embed.resolve_backend_name(),
            "higgsfield_configured": higgsfield.available()}


_LIBRARY_PROP = {"library": {"type": "string",
                             "description": "design library folder; defaults to docs/designs"}}
_OVERRIDES_PROP = {
    "overrides": {
        "type": "object",
        "description": "the new company's brand, laid over the matched design's tokens. "
                       "primary -> accent (CTAs, links); secondary -> accent2 (tags, secondary "
                       "buttons); ground/ink only when the user names a background or text colour; "
                       "font_display / font_body; style (a style tag); sections (list, replaces the "
                       "derived plan); company (name used in copy and image prompts)",
        "properties": {
            "primary": {"type": "string"}, "secondary": {"type": "string"},
            "ground": {"type": "string"}, "ink": {"type": "string"},
            "font_display": {"type": "string"}, "font_body": {"type": "string"},
            "style": {"type": "string"},
            "sections": {"type": "array", "items": {"type": "string"}},
            "company": {"type": "string"},
        },
    },
}
_REQUIRE_MEDIA_PROP = {
    "require_media": {"type": "boolean",
                      "description": "only match designs that have screenshots - set this whenever "
                                     "the design will be reproduced as a template"},
}
_MATCH_PROPS = {
    "prompt": {"type": "string", "description": "what the user wants to build, in their own words"},
    "design": {"type": "string", "description": "slug or title of a specific design, instead of searching"},
    "filters": {"type": "object", "description": "facet -> tags, e.g. {\"industry\": [\"fintech\"]}"},
    **_REQUIRE_MEDIA_PROP,
    **_LIBRARY_PROP,
}

TOOLS: list[dict[str, Any]] = [
    {
        "name": "design_search",
        "description": "Find the design references closest to a natural-language prompt. Returns "
                       "ranked designs with tags, folder paths, reference imagery and a short "
                       "explanation of why each matched. Use this first for any 'build me a site "
                       "that looks like...' request.",
        "inputSchema": {"type": "object", "required": ["prompt"], "properties": {
            "prompt": {"type": "string"},
            "k": {"type": "integer", "description": "how many to return (default 5)"},
            "filters": {"type": "object"}, **_REQUIRE_MEDIA_PROP, **_LIBRARY_PROP}},
        "handler": tool_design_search,
    },
    {
        "name": "design_get",
        "description": "Fetch one design in full by slug or title: its complete description, all "
                       "tags, palette, fonts and the paths of its reference images.",
        "inputSchema": {"type": "object", "required": ["design"], "properties": {
            "design": {"type": "string"}, **_LIBRARY_PROP}},
        "handler": tool_design_get,
    },
    {
        "name": "design_list",
        "description": "List every design in the library, optionally filtered by facet tags. Use to "
                       "browse what is available before searching.",
        "inputSchema": {"type": "object", "properties": {"filters": {"type": "object"}, **_LIBRARY_PROP}},
        "handler": tool_design_list,
    },
    {
        "name": "design_tags",
        "description": "The controlled tag vocabulary: every facet (industry, page_type, section, "
                       "style, motion, palette, layout) and its allowed tags. Read this before "
                       "constructing filters.",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": tool_design_tags,
    },
    {
        "name": "design_brief",
        "description": "Turn a prompt plus its matched design into a concrete build brief: design "
                       "tokens (palette, fonts, radius, spacing, type scale), an ordered section "
                       "plan, a motion plan naming the technique and library for each effect, "
                       "art-directed image prompts, and the anti-generic constraints to hold to. "
                       "Read the brief before writing any code.",
        "inputSchema": {"type": "object", "properties": {
            **_MATCH_PROPS, **_OVERRIDES_PROP, "project": {"type": "string"}}},
        "handler": tool_design_brief,
    },
    {
        "name": "scaffold_nextjs",
        "description": "Generate a runnable standalone Next.js 15 project (App Router, TypeScript, "
                       "Tailwind v4, output:'standalone') wired to the matched design's tokens, with "
                       "one component per planned section, DESIGN.md, and the reference imagery "
                       "copied in. Produces a correct shell for you to implement into - it does not "
                       "write the finished sections.",
        "inputSchema": {"type": "object", "properties": {
            **_MATCH_PROPS, **_OVERRIDES_PROP,
            "out_dir": {"type": "string", "description": "where to create the project; "
                        "defaults to output/<project> in the repo - leave unset unless the user names a path"},
            "project": {"type": "string"},
            "force": {"type": "boolean", "description": "overwrite a non-empty directory"}}},
        "handler": tool_scaffold_nextjs,
    },
    {
        "name": "scaffold_expo",
        "description": "Generate a runnable Expo (React Native) app - Expo Router, TypeScript, tabs - "
                       "wired to the matched design's tokens with the brand overrides applied, one "
                       "block component per planned section, DESIGN.md, LAYOUT.md and the reference "
                       "screenshots copied in. The library holds desktop references only, so the "
                       "phone layout is derived from them; the skill carries the translation rules. "
                       "Runs with `npx expo start`.",
        "inputSchema": {"type": "object", "properties": {
            **_MATCH_PROPS, **_OVERRIDES_PROP,
            "out_dir": {"type": "string", "description": "where to create the project; "
                        "defaults to output/<project> in the repo - leave unset unless the user names a path"},
            "project": {"type": "string"},
            "force": {"type": "boolean", "description": "overwrite a non-empty directory"}}},
        "handler": tool_scaffold_expo,
    },
    {
        "name": "higgsfield_generate",
        "description": "Generate site imagery with Higgsfield, art-directed to match the design's "
                       "palette and register, and download it into a folder. Without HF_API_KEY_ID "
                       "and HF_API_KEY_SECRET it returns the prompts instead of failing, so they can "
                       "be used in any other image tool.",
        "inputSchema": {"type": "object", "required": ["out_dir"], "properties": {
            **_MATCH_PROPS,
            "out_dir": {"type": "string"},
            "slots": {"type": "array", "items": {"type": "string"},
                      "description": "subset of hero, feature-texture, section-support, og-card"},
            "prompts": {"type": "array", "description": "explicit prompts instead of brief-derived ones",
                        "items": {"type": "object", "required": ["prompt"], "properties": {
                            "slot": {"type": "string"}, "prompt": {"type": "string"},
                            "aspect_ratio": {"type": "string"}}}},
            "model": {"type": "string", "description": "soul (default), soul-hd, flux-kontext"},
            "dry_run": {"type": "boolean"}}},
        "handler": tool_higgsfield_generate,
    },
    {
        "name": "library_index",
        "description": "Rebuild the vector index after designs are added, edited or removed.",
        "inputSchema": {"type": "object", "properties": {
            "backend": {"type": "string", "description": "voyage | openai | local | lexical"},
            **_LIBRARY_PROP}},
        "handler": tool_library_index,
    },
    {
        "name": "library_status",
        "description": "Where the library is, how many designs it holds, whether the index is stale, "
                       "which embedding backend is active and whether Higgsfield is configured.",
        "inputSchema": {"type": "object", "properties": {**_LIBRARY_PROP}},
        "handler": tool_library_status,
    },
]

HANDLERS: dict[str, Callable[[dict[str, Any]], Any]] = {t["name"]: t["handler"] for t in TOOLS}
TOOL_SCHEMAS = [{k: v for k, v in t.items() if k != "handler"} for t in TOOLS]


# --------------------------------------------------------------------------- protocol

def _result(request_id: Any, payload: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": payload}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def handle(message: dict[str, Any]) -> dict[str, Any] | None:
    """Return a response, or None for notifications (which must not be answered)."""
    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params") or {}

    if method == "initialize":
        requested = params.get("protocolVersion")
        protocol = requested if requested in SUPPORTED_PROTOCOLS else DEFAULT_PROTOCOL
        return _result(request_id, {
            "protocolVersion": protocol,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            "instructions": (
                "A library of website design references, searchable by meaning. Typical flow: "
                "design_search to find a direction, design_brief to turn it into concrete tokens "
                "and a section plan, scaffold_nextjs to create the project, then implement the "
                "sections against DESIGN.md. Look at the reference images before writing code."
            ),
        })

    if method in ("notifications/initialized", "initialized", "notifications/cancelled"):
        return None

    if method == "ping":
        return _result(request_id, {})

    if method == "tools/list":
        return _result(request_id, {"tools": TOOL_SCHEMAS})

    if method == "tools/call":
        name = params.get("name")
        handler = HANDLERS.get(name)
        if not handler:
            return _error(request_id, -32602, f"unknown tool: {name}")
        try:
            payload = handler(params.get("arguments") or {})
            text = json.dumps(payload, indent=2, ensure_ascii=False, default=str)
            return _result(request_id, {"content": [{"type": "text", "text": text}]})
        except Exception as exc:  # a tool failing must not take the server down
            _log(f"tool {name} failed: {exc}\n{traceback.format_exc()}")
            return _result(request_id, {
                "content": [{"type": "text", "text": f"{type(exc).__name__}: {exc}"}],
                "isError": True,
            })

    if request_id is None:
        return None
    return _error(request_id, -32601, f"method not found: {method}")


def serve(stdin=None, stdout=None) -> None:
    """Read newline-delimited JSON-RPC from stdin, write responses to stdout."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    _log(f"serving {len(TOOLS)} tools from {library_dir()}")
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            _log(f"bad JSON: {exc}")
            stdout.write(json.dumps(_error(None, -32700, "parse error")) + "\n")
            stdout.flush()
            continue

        # A client may batch requests in a JSON array.
        batch = message if isinstance(message, list) else [message]
        responses = [r for r in (handle(m) for m in batch) if r is not None]
        for response in responses:
            stdout.write(json.dumps(response, default=str) + "\n")
        if responses:
            stdout.flush()


if __name__ == "__main__":
    serve()
