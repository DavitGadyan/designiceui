"""Turn a matched design plus the user's prompt into a build brief.

This is the piece that decides whether `createui` produces something specific or
something generic. A retrieved design gives us a *direction*; the brief converts
that direction into decisions an implementing agent can execute without
re-inventing them: tokens, a section order, a motion budget, and image prompts.

The brief never invents a palette when the design has one. Where the design is
silent, defaults are derived from its tags rather than picked at random, so two
runs against the same design agree with each other.
"""

from __future__ import annotations

import json
import re
from typing import Any

from . import colour, taxonomy

# Tag-driven defaults. These encode the "what does this style imply" knowledge
# that would otherwise have to be re-derived on every single build.
STYLE_TOKENS: dict[str, dict[str, Any]] = {
    "minimal":         {"radius": "12px", "shadow": "none", "density": "airy"},
    "swiss-editorial": {"radius": "0px", "shadow": "none", "density": "tight"},
    "brutalist":       {"radius": "0px", "shadow": "none", "density": "tight"},
    "neo-brutalist":   {"radius": "6px", "shadow": "6px 6px 0 currentColor", "density": "chunky"},
    "glassmorphic":    {"radius": "20px", "shadow": "0 8px 32px rgba(0,0,0,.35)", "density": "airy"},
    "luxury":          {"radius": "4px", "shadow": "none", "density": "airy"},
    "playful":         {"radius": "24px", "shadow": "0 6px 0 rgba(0,0,0,.9)", "density": "chunky"},
    "corporate":       {"radius": "16px", "shadow": "0 1px 3px rgba(0,0,0,.08)", "density": "regular"},
    "dark-tech":       {"radius": "10px", "shadow": "none", "density": "tight"},
    "cyberpunk":       {"radius": "0px", "shadow": "none", "density": "tight"},
    "organic":         {"radius": "28px", "shadow": "0 8px 32px rgba(0,0,0,.06)", "density": "airy"},
    "vintage":         {"radius": "8px", "shadow": "none", "density": "regular"},
    "maximalist":      {"radius": "8px", "shadow": "8px 8px 0 currentColor", "density": "chunky"},
    "editorial-photo": {"radius": "2px", "shadow": "none", "density": "airy"},
}

# Motion budget in milliseconds, plus the library that suits the technique.
MOTION_PLAN: dict[str, dict[str, str]] = {
    "scroll-driven":     {"tool": "GSAP ScrollTrigger (scrub)", "note": "tie progress to scroll, never to a timer"},
    "pinned-sections":   {"tool": "GSAP ScrollTrigger (pin)", "note": "budget ~300vh of scroll per pinned scene"},
    "parallax":          {"tool": "CSS transform + rAF, or Lenis", "note": "keep depth factors between 0.8 and 1.2"},
    "3d-webgl":          {"tool": "three.js / react-three-fiber", "note": "apply ACES filmic tone mapping or the model renders dark and muddy"},
    "reveal-on-scroll":  {"tool": "IntersectionObserver + CSS", "note": "fire once at ~20% viewport; never re-animate on scroll up"},
    "marquee":           {"tool": "CSS keyframes on a duplicated track", "note": "20-30s per loop; faster than 15s is unreadable"},
    "magnetic-cursor":   {"tool": "pointermove + lerp", "note": "lerp 0.12-0.18; disable entirely on touch"},
    "hover-tilt":        {"tool": "CSS custom properties + spring", "note": "cap at 6deg; more reads as a gimmick"},
    "gradient-mesh":     {"tool": "blurred radial divs or a shader", "note": "co-prime durations so the loop never visibly repeats"},
    "particle-field":    {"tool": "three.js Points", "note": "cap particle count on mobile; it is the first thing to drop frames"},
    "text-effects":      {"tool": "SplitType + GSAP", "note": "reserve the layout height first to avoid a reflow flash"},
    "morphing":          {"tool": "SVG path interpolation", "note": "keep point counts equal between states"},
    "video-background":  {"tool": "<video> muted autoplay playsinline", "note": "poster frame must match frame one exactly"},
    "static":            {"tool": "none", "note": "motion limited to hover and focus states"},
}

# Techniques that have no meaning on a phone, or fight the platform's own motion.
MOBILE_DROPS = {"marquee", "magnetic-cursor", "hover-tilt", "parallax", "pinned-sections",
                "scroll-driven", "particle-field", "3d-webgl", "video-background"}

MOBILE_CONSTRAINTS = [
    "Tap targets are 44pt minimum; a 32px web button is unusable on a phone.",
    "Hover does not exist. Every hover state becomes a Pressable pressed state.",
    "One column. Multi-column web grids become a vertical stack or a horizontal FlatList.",
    "Respect the safe area; nothing sits under the notch or the home indicator.",
    "Use the platform's own motion (Stack and Tabs transitions) before adding any of your own.",
]

DEFAULT_SECTIONS = ["nav", "hero", "logos", "features", "bento", "stats", "testimonials", "pricing", "faq", "cta", "footer"]
SECTION_ORDER = {name: i for i, name in enumerate(DEFAULT_SECTIONS)}

HEX_RE = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b")


def _pick(values: list[str], table: dict[str, Any], fallback: str) -> str:
    for value in values:
        if value in table:
            return value
    return fallback


def _palette(design: dict[str, Any]) -> list[str]:
    colours = list(design.get("palette") or [])
    if not colours:
        colours = [c.upper() for c in HEX_RE.findall(design.get("description", ""))]
    seen, out = set(), []
    for c in colours:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out[:6]


def _sections(design: dict[str, Any], prompt: str) -> list[str]:
    """Sections the design demonstrates, plus anything the prompt explicitly asks for."""
    wanted = set(design.get("primary", {}).get("section") or design.get("tags", {}).get("section", []))
    wanted |= set(taxonomy.detect_tags(prompt).get("section", []))
    wanted |= {"nav", "hero", "footer"}  # a page without these is not a page
    if len(wanted) < 5:
        wanted |= {"features", "cta"}
    return sorted(wanted, key=lambda s: SECTION_ORDER.get(s, 99))


def _facet(design: dict[str, Any], facet: str, *, strict: bool = False) -> list[str]:
    """Authored tags first, falling back to everything detected.

    `primary` preserves the order the librarian wrote, which is what makes the
    first entry the actual direction rather than an alphabetical accident.

    Pass strict=True for facets where a false positive is actively harmful.
    Industry is the clearest case: a description that closes with "use for
    fintech, legal and music" should help that design get *found* by all three,
    but the brief for a private-bank page must not claim the site is a music
    site. Recall wants the loose set; direction wants the authored one.
    """
    primary = design.get("primary", {}).get(facet) or []
    if strict and primary:
        return list(primary)
    rest = [t for t in design.get("tags", {}).get(facet, []) if t not in primary]
    return list(primary) + rest


OVERRIDE_KEYS = ("primary", "secondary", "ground", "ink", "font_display", "font_body",
                 "style", "sections", "platform", "company")


def _token_source(design: dict[str, Any]) -> str:
    """Where a design's tokens came from - so a brief can say how much to trust them.

    Only meta.json yields fonts or authored (primary) tags; hexes scraped from
    prose give a palette but nothing else; and a bare screenshot folder gives
    nothing at all, in which case everything below is a mode fallback and the
    real tokens have to be read off the image.
    """
    if design.get("fonts"):
        return "meta"
    if design.get("palette"):
        return "description"
    return "fallback"


def _clean_overrides(overrides: dict[str, Any] | None) -> dict[str, Any]:
    ov = {k: v for k, v in (overrides or {}).items() if k in OVERRIDE_KEYS and v not in (None, "", [])}
    if isinstance(ov.get("sections"), str):
        ov["sections"] = [x.strip() for x in ov["sections"].split(",") if x.strip()]
    return ov


def build(design: dict[str, Any], prompt: str, *, project: str = "",
          overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    ov = _clean_overrides(overrides)
    tags = design.get("tags", {})
    styles = _facet(design, "style", strict=True)
    motions = _facet(design, "motion") or ["reveal-on-scroll"]
    palette_tags = _facet(design, "palette", strict=True)

    template_style = _pick(styles, STYLE_TOKENS, "minimal")
    style = ov.get("style") if ov.get("style") in STYLE_TOKENS else template_style
    tokens = dict(STYLE_TOKENS[style])
    colours = _palette(design)
    # An explicit palette tag beats a guess; only fall back to measuring the
    # first colour's luminance when the design never said which mode it is.
    if "dark" in palette_tags:
        template_dark = True
    elif "light" in palette_tags:
        template_dark = False
    else:
        template_dark = bool(colours) and _is_dark(colours[0])

    # Template roles first, then the user's brand laid over them. The template
    # roles are kept in the brief so the "template -> yours" table can show
    # exactly what changed, which is how a user learns what to ask for next time.
    template_roles = colour.roles_from_palette(colours, template_dark)
    roles, notes = colour.apply_overrides(template_roles, ov)
    is_dark = colour.is_dark(roles["ground"])

    template_fonts = list(design.get("fonts") or _fonts_for(template_style))
    fonts = list(template_fonts)
    if ov.get("font_display"):
        fonts[0] = ov["font_display"]
    if ov.get("font_body"):
        if len(fonts) > 1:
            fonts[1] = ov["font_body"]
        else:
            fonts.append(ov["font_body"])
    if len(fonts) < 2:
        fonts.append("Inter")

    density = tokens.pop("density")
    spacing = {"tight": ("112px", "72px"), "regular": ("128px", "80px"),
               "airy": ("160px", "96px"), "chunky": ("120px", "72px")}[density]

    plan = [{"technique": m, **MOTION_PLAN.get(m, {"tool": "CSS", "note": ""})} for m in motions]
    platform = ov.get("platform") if ov.get("platform") in ("web", "mobile") else "web"
    company = str(ov.get("company") or "").strip()

    return {
        "project": project or design.get("slug", "site"),
        "prompt": prompt,
        "platform": platform,
        "company": company,
        "overrides": ov,
        "notes": notes,
        "template_tokens": {
            "source": _token_source(design),
            "roles": template_roles,
            "palette": colours,
            "fonts": template_fonts,
            "style": template_style,
            "mode": "dark" if template_dark else "light",
        },
        "reference_design": {
            "slug": design.get("slug"),
            "title": design.get("title"),
            "path": design.get("path"),
            "use_case": design.get("use_case", ""),
            "reference_url": design.get("reference_url", ""),
            "media": design.get("media", []),
            "score": design.get("score"),
        },
        "direction": {
            "style": style,
            "all_styles": styles,
            "industry": _facet(design, "industry", strict=True)[:3],
            "layout": _facet(design, "layout"),
            "mode": "dark" if is_dark else "light",
        },
        "tokens": {
            "roles": roles,
            "palette": [roles[r] for r in ("ground", "surface", "accent", "ink", "muted")],
            "fonts": fonts,
            "radius": tokens["radius"],
            "shadow": tokens["shadow"],
            "section_padding_desktop": spacing[0],
            "section_padding_mobile": spacing[1],
            "density": density,
            "type_scale": _type_scale(style),
        },
        "sections": list(ov["sections"]) if ov.get("sections") else _sections(design, prompt),
        "motion": plan if platform == "web" else [m for m in plan
                                                   if m["technique"] not in MOBILE_DROPS],
        "image_prompts": image_prompts(design, company or prompt),
        "constraints": constraints(style, is_dark) + (MOBILE_CONSTRAINTS if platform == "mobile" else []),
        "source_description": design.get("description", ""),
    }


def _is_dark(hex_colour: str) -> bool:
    h = hex_colour.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return False
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) < 110


def _fonts_for(style: str) -> list[str]:
    return {
        "swiss-editorial": ["Inter Tight", "Inter"],
        "brutalist": ["Archivo", "Inter"],
        "neo-brutalist": ["Space Grotesk", "Inter"],
        "luxury": ["Instrument Serif", "Inter"],
        "editorial-photo": ["Instrument Serif", "Inter"],
        "organic": ["Fraunces", "Inter"],
        "vintage": ["Fraunces", "Inter"],
        "playful": ["Space Grotesk", "Inter"],
        "cyberpunk": ["Chakra Petch", "IBM Plex Mono"],
        "dark-tech": ["Inter Tight", "JetBrains Mono"],
    }.get(style, ["Inter Tight", "Inter"])


def _type_scale(style: str) -> dict[str, str]:
    if style in {"swiss-editorial", "brutalist", "maximalist", "neo-brutalist"}:
        return {"display": "clamp(3rem, 9vw, 8rem)", "h1": "clamp(2.5rem, 6vw, 5rem)",
                "h2": "clamp(1.75rem, 3.5vw, 3rem)", "body": "17px", "leading_display": "0.92"}
    if style in {"luxury", "editorial-photo", "organic", "vintage"}:
        return {"display": "clamp(2.75rem, 6vw, 5.5rem)", "h1": "clamp(2.25rem, 4.5vw, 4rem)",
                "h2": "clamp(1.6rem, 3vw, 2.5rem)", "body": "18px", "leading_display": "1.05"}
    return {"display": "clamp(2.5rem, 5vw, 4rem)", "h1": "clamp(2rem, 4vw, 3.25rem)",
            "h2": "clamp(1.5rem, 2.5vw, 2.25rem)", "body": "16px", "leading_display": "1.1"}


def constraints(style: str, is_dark: bool) -> list[str]:
    """The anti-slop list. These are the specific failures that make AI sites look AI-made."""
    base = [
        "No purple-to-blue gradient on a white card unless the reference design actually uses one.",
        "No emoji as icons. Use a real icon set or draw inline SVG.",
        "Body text is never below 15px, and never pure #000 on pure #FFF.",
        "Every section must differ from its neighbour in background, rhythm or column count - "
        "eleven identical centred slabs is the single clearest tell of a generated page.",
        "Buttons need real hover, focus-visible and active states, not just a colour change.",
        "Respect prefers-reduced-motion: hold transforms, keep opacity fades.",
        "Images need explicit width/height or aspect-ratio so nothing shifts on load.",
        "Ship real copy, not lorem ipsum, and not three-word headlines that say nothing.",
    ]
    if is_dark:
        base.append("On dark, raise surfaces with a lighter background plus a 1px translucent "
                    "border - a drop shadow is invisible on black and does nothing.")
    if style in {"glassmorphic"}:
        base.append("Cap backdrop-filter surfaces at ~6 on screen; more will drop frames on mid-range hardware.")
    if style in {"swiss-editorial", "brutalist"}:
        base.append("Hold the grid. Nothing floats free of the column structure.")
    if style in {"luxury", "minimal"}:
        base.append("Restraint is the brand. If a decoration can be removed without loss, remove it.")
    return base


def image_prompts(design: dict[str, Any], prompt: str) -> list[dict[str, str]]:
    """Art-directed prompts, one per visual slot, ready for Higgsfield or any image model.

    They inherit the reference design's palette and register so the generated
    imagery belongs to the same world as the layout rather than fighting it.
    """
    style = ", ".join(_facet(design, "style")[:2]) or "minimal"
    palette = ", ".join(_palette(design)[:4]) or "restrained neutral palette"
    industry = ", ".join(_facet(design, "industry", strict=True)[:2]) or "modern product"
    subject = prompt.strip() or design.get("use_case", "")
    shared = f"{style} art direction, palette {palette}, no text, no watermark, no UI chrome"

    return [
        {"slot": "hero",
         "aspect_ratio": "16:9",
         "prompt": f"Wide cinematic hero image for a {industry} website. {subject}. "
                   f"{shared}. Strong single focal point positioned off-centre with generous "
                   f"negative space on the left third for a headline overlay. Shallow depth of "
                   f"field, controlled contrast so white type stays readable over it."},
        {"slot": "feature-texture",
         "aspect_ratio": "1:1",
         "prompt": f"Abstract close-up texture evoking {industry}. {shared}. Macro detail, soft "
                   f"directional light, extremely shallow depth of field, reads as a background "
                   f"at low opacity rather than as a subject."},
        {"slot": "section-support",
         "aspect_ratio": "4:3",
         "prompt": f"Editorial supporting photograph for a {industry} website section. {subject}. "
                   f"{shared}. Documentary framing, natural light, one human gesture or one object "
                   f"in use, nothing staged or stock-like."},
        {"slot": "og-card",
         "aspect_ratio": "16:9",
         "prompt": f"Open Graph share card background for a {industry} brand. {shared}. Simple, "
                   f"high contrast, centre kept visually quiet so a logo and title can be composited on top."},
    ]


def render_markdown(b: dict[str, Any]) -> str:
    """Human- and agent-readable brief. This is what `createui` prints and follows."""
    d, t = b["direction"], b["tokens"]
    ref = b["reference_design"]
    lines = [
        f"# Build brief - {b['project']}",
        "",
        f"**Request:** {b['prompt']}",
        f"**Platform:** {b.get('platform', 'web')}"
        + (f"  |  **Company:** {b['company']}" if b.get("company") else ""),
        f"**Reference design:** {ref['title']} (`{ref['slug']}`)"
        + (f" - score {ref['score']}" if ref.get("score") is not None else ""),
        f"**Reference folder:** `{ref['path']}`",
    ]
    if ref.get("reference_url"):
        lines.append(f"**Origin:** {ref['reference_url']}")
    if ref.get("media"):
        lines.append("**Look at these before writing code:** "
                     + ", ".join(f"`{m['path']}`" for m in ref["media"][:6]))
    lines += [
        "",
        "## Direction",
        f"- Style: **{d['style']}**" + (f" (also {', '.join(s for s in d['all_styles'] if s != d['style'])})"
                                        if len(d["all_styles"]) > 1 else ""),
        f"- Mode: **{d['mode']}**",
        f"- Industry: {', '.join(d['industry']) or 'general'}",
        f"- Layout: {', '.join(d['layout']) or 'standard'}",
    ]
    tt = b.get("template_tokens", {})
    if tt:
        lines += ["", "## Tokens - template -> yours", ""]
        source_note = {
            "meta": "template tokens are authored in meta.json",
            "description": "template tokens were scraped from the description; verify against the images",
            "fallback": "**the template has no authored tokens - these are mode fallbacks.** "
                        "Read the real ground, ink, accent and fonts off the hero screenshot and "
                        "write them to meta.json so the next run starts from the truth.",
        }[tt.get("source", "fallback")]
        lines.append(f"_{source_note}_")
        lines += ["", "| Role | Template | Yours |", "|---|---|---|"]
        for role in ("ground", "surface", "ink", "muted", "accent", "accent2"):
            before, after = tt["roles"].get(role, ""), t["roles"].get(role, "")
            mark = " **<-**" if before != after else ""
            lines.append(f"| {role} | `{before}` | `{after}`{mark} |")
        tf, f = list(tt.get("fonts", [])), list(t["fonts"])
        for i, label in enumerate(("display font", "body font")):
            before = tf[i] if len(tf) > i else "-"
            after = f[i] if len(f) > i else "-"
            lines.append(f"| {label} | {before} | {after}{' **<-**' if before != after else ''} |")
        for n in b.get("notes", []):
            lines.append(f"- ! {n}")
    lines += [
        "",
        "## Tokens",
        f"- Roles: " + "  ".join(f"{k}={v}" for k, v in t["roles"].items()),
        f"- Fonts: {', '.join(t['fonts'])}",
        f"- Radius: {t['radius']}  |  Shadow: {t['shadow']}",
        f"- Section padding: {t['section_padding_desktop']} desktop / {t['section_padding_mobile']} mobile",
        f"- Display type: {t['type_scale']['display']}, leading {t['type_scale']['leading_display']}",
        f"- Body type: {t['type_scale']['body']}",
        "",
        "## Sections, in order",
    ]
    lines += [f"{i}. {s}" for i, s in enumerate(b["sections"], 1)]
    lines += ["", "## Motion"]
    lines += [f"- **{m['technique']}** via {m['tool']} - {m['note']}" for m in b["motion"]]
    lines += ["", "## Non-negotiables"]
    lines += [f"- {c}" for c in b["constraints"]]
    lines += ["", "## Image prompts", ""]
    for p in b["image_prompts"]:
        lines.append(f"**{p['slot']}** ({p['aspect_ratio']})")
        lines.append(f"> {p['prompt']}")
        lines.append("")
    lines += ["## Reference description", "", b["source_description"]]
    return "\n".join(lines)


def to_json(b: dict[str, Any]) -> str:
    return json.dumps(b, indent=2)
