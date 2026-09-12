"""Generate a standalone Next.js project from a build brief.

What this produces is a *correct shell*, not a finished website: the token
system is fully wired, the app builds and runs, and every planned section
exists as a real component carrying its slice of the brief as a comment. The
implementing agent then fills the sections in.

That split is deliberate. Tokens, config, fonts, reduced-motion handling and
the standalone output setting are mechanical and get them wrong-once-wrong-
everywhere, so a script should own them. Layout and copy are judgement, so a
model should own those - working against a brief rather than a blank page.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from . import colour

TEMPLATES_ROOT = Path(__file__).parent / "templates"
TEMPLATES = TEMPLATES_ROOT / "nextjs"
EXPO_TEMPLATES = TEMPLATES_ROOT / "expo"

# next/font/google exposes these directly. Anything outside the list is a
# licensed or self-hosted face, and we emit a stack plus a note rather than
# generating an import that will fail the build.
GOOGLE_FONTS = {
    "Inter", "Inter Tight", "Space Grotesk", "Fraunces", "Instrument Serif", "Instrument Sans",
    "Archivo", "Chakra Petch", "JetBrains Mono", "IBM Plex Mono", "IBM Plex Sans", "Manrope",
    "DM Sans", "DM Serif Display", "Playfair Display", "Libre Baskerville", "Sora", "Outfit",
    "Plus Jakarta Sans", "Figtree", "Geist", "Geist Mono", "Roboto Mono", "Source Serif 4",
    "Newsreader", "Lora", "Bricolage Grotesque", "Syne", "Unbounded", "Cormorant Garamond",
    "Work Sans", "Public Sans", "Spline Sans", "Space Mono", "Anton", "Bebas Neue",
    "Poppins", "Nunito", "Nunito Sans", "Rubik", "Raleway", "Montserrat", "Lato", "Open Sans",
    "Roboto", "Karla", "Merriweather", "EB Garamond", "Crimson Pro", "Josefin Sans", "Quicksand",
    "Urbanist", "Kanit", "Barlow", "Oswald", "Archivo Black", "Fredoka", "Red Hat Display",
    "Red Hat Text", "Albert Sans", "Onest", "Be Vietnam Pro", "Hanken Grotesk", "Schibsted Grotesk",
    "Familjen Grotesk", "Epilogue", "Jost", "Prompt", "Lexend", "Atkinson Hyperlegible",
    "Fira Code", "Fira Sans", "Source Code Pro", "Source Sans 3", "Noto Sans", "Noto Serif",
    "Libre Franklin", "Cabinet Grotesk" if False else "Chivo", "Gloock", "Bodoni Moda", "Italiana",
    "Cormorant", "Marcellus", "Cinzel", "Zilla Slab", "Roboto Slab", "Bitter", "Domine",
}

# next/font/google needs an explicit `weight` for fonts that are not variable
# fonts, and refuses to build without one. Variable fonts (Inter, Work Sans,
# Space Grotesk...) load their whole axis when weight is omitted, which is what
# we want. So: single-weight faces get ["400"], static multi-weight faces get
# ["400", "700"] (the pair every static family ships), variable faces get nothing.
# Guessing "static" for an uncertain font costs a couple of intermediate weights;
# guessing "variable" for a static one breaks the build - so when in doubt, it
# goes in this set.
STATIC_FONTS = {
    "Instrument Serif", "Anton", "Bebas Neue", "DM Serif Display", "Space Mono", "Archivo Black",
    "Marcellus", "Italiana", "Gloock",
    "Poppins", "Lato", "Kanit", "Barlow", "Chakra Petch", "IBM Plex Mono", "IBM Plex Sans",
    "Prompt", "Be Vietnam Pro", "Atkinson Hyperlegible", "Fira Sans", "Libre Baskerville",
    "Zilla Slab",
}
SINGLE_WEIGHT_WEB = {"Instrument Serif", "Anton", "Bebas Neue", "DM Serif Display", "Archivo Black",
                     "Marcellus", "Italiana", "Gloock"}

SERIF_HINTS = ("serif", "canela", "ogg", "editorial", "alpina", "fraunces", "playfair",
               "newsreader", "lora", "baskerville", "cormorant", "garamond", "instrument serif")
MONO_HINTS = ("mono", "berkeley", "jetbrains", "plex mono", "code")

SECTION_TITLES = {
    "nav": "Navigation", "hero": "Hero", "logos": "Trusted by", "features": "Features",
    "bento": "Bento grid", "stats": "By the numbers", "testimonials": "Testimonials",
    "pricing": "Pricing", "faq": "Frequently asked", "cta": "Call to action",
    "footer": "Footer", "gallery": "Gallery", "timeline": "How it works", "team": "Team",
    "contact": "Contact", "marquee": "Marquee", "comparison": "Comparison",
    "integrations": "Integrations",
}

# What each section is actually for. Generic scaffolds skip this and that is
# exactly why generated sections read as filler.
SECTION_GUIDANCE = {
    "nav": ["Sticky, but only after the hero leaves - a bar pinned from pixel one steals the opening.",
            "Keep it to five links maximum plus one action."],
    "hero": ["One idea, one sentence, one primary action. Everything else is a distraction.",
             "The headline should name what the product does, not how it feels."],
    "logos": ["Greyscale at rest, full colour on hover. Six to eight marks, evenly optically sized."],
    "features": ["Lead each item with the outcome, not the mechanism.",
                 "Vary the column count from the section above so the page has rhythm."],
    "bento": ["Asymmetric by design: one wide cell, several small. Equal cells are just a grid.",
              "One cell should hold something live - a chart, a small looping UI."],
    "stats": ["Four numbers maximum. Count them up once on reveal, never on every scroll pass."],
    "testimonials": ["Real names, roles and companies. An unattributed quote reads as invented."],
    "pricing": ["Three tiers, middle one emphasised. Annual toggle animates the price, not the layout."],
    "faq": ["Answer the objection, not the softball. Accordion, one open at a time."],
    "cta": ["Restate the single action from the hero. Do not introduce a new one here."],
    "footer": ["Oversized wordmark, grouped links, and the legal line. This is where the brand signs off."],
    "gallery": ["Consistent aspect ratios, explicit dimensions, lazy-loaded below the fold."],
    "timeline": ["Three to five steps. Number them; the count is the reassurance."],
    "team": ["Consistent crops and lighting across every portrait, or the grid falls apart."],
    "contact": ["Fewest possible fields. Inline validation, a real success state, no dead submit."],
    "marquee": ["20-30 seconds per loop. Anything faster is unreadable and reads as nervous."],
    "comparison": ["Be honest about the columns you lose - a table you always win reads as marketing."],
    "integrations": ["A hairline grid of marks. Alignment is the whole effect."],
}


def _slugify(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return value or "site"


def _component_name(section: str) -> str:
    return "".join(part.capitalize() for part in re.split(r"[^a-zA-Z0-9]+", section) if part) or "Block"


def _stack(font: str, css_var: str | None = None) -> str:
    """Build a font stack, putting the next/font variable first when there is one.

    next/font generates a hashed family name and exposes it through a CSS
    variable. Naming the font literally instead means the loaded face is never
    actually used - the browser looks for a locally installed "Fraunces", does
    not find one, and silently falls back to Georgia. The variable has to lead.
    """
    lowered = font.lower()
    if any(h in lowered for h in MONO_HINTS):
        fallbacks = 'ui-monospace, SFMono-Regular, Menlo, monospace'
    elif any(h in lowered for h in SERIF_HINTS):
        fallbacks = 'ui-serif, Georgia, "Times New Roman", serif'
    else:
        fallbacks = 'ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif'
    head = f"var({css_var}), " if css_var else ""
    return f'{head}"{font}", {fallbacks}'


def _font_plan(fonts: list[str]) -> dict[str, Any]:
    """Wire Google fonts through next/font; leave licensed faces as a stack + note."""
    display = fonts[0] if fonts else "Inter Tight"
    body = fonts[1] if len(fonts) > 1 else "Inter"

    imports: list[str] = []
    variables: list[str] = []
    notes: list[str] = []
    loaded: dict[str, str] = {}

    for role, font in (("display", display), ("body", body)):
        if font in GOOGLE_FONTS:
            loaded[role] = f"--font-{role}-loaded"
            module = font.replace(" ", "_").replace("-", "_")
            imports.append(
                f'import {{ {module} as {role.capitalize()}Font }} from "next/font/google";'
            )
            if font in SINGLE_WEIGHT_WEB:
                weight = 'weight: ["400"], '
            elif font in STATIC_FONTS:
                weight = 'weight: ["400", "700"], '
            else:
                weight = ""
            variables.append(
                f'const {role}Font = {role.capitalize()}Font({{ subsets: ["latin"], {weight}'
                f'variable: "--font-{role}-loaded", display: "swap" }});'
            )
        else:
            notes.append(
                f"{font} is not on Google Fonts. Self-host it in app/fonts/ and swap "
                f"--font-{role} in globals.css; until then the stack falls back to a system face."
            )

    font_imports = "\n".join(imports + ([""] if imports else []) + variables)
    class_attr = ""
    if variables:
        parts = " ".join(f"${{{role}Font.variable}}" for role in ("display", "body")
                         if f"const {role}Font" in font_imports)
        class_attr = f' className={{`{parts}`}}'

    return {
        "imports": font_imports,
        "class_attr": class_attr,
        "display_stack": _stack(display, loaded.get("display")),
        "body_stack": _stack(body, loaded.get("body")),
        "notes": notes,
    }


def _colours(palette: list[str], is_dark: bool) -> dict[str, str]:
    """Kept for callers and tests; the logic now lives in colour.roles_from_palette."""
    return colour.roles_from_palette(palette, is_dark)


def _roles(brief: dict[str, Any], is_dark: bool) -> dict[str, str]:
    """Prefer the brief's resolved roles (overrides applied); derive otherwise."""
    tokens = brief["tokens"]
    roles = tokens.get("roles")
    if roles:
        return dict(roles)
    derived = _colours(tokens["palette"], is_dark)
    derived.setdefault("accent2", colour.mix(derived["accent"], derived["ink"], 0.35))
    return derived


def _layout_inventory(brief: dict[str, Any], values: dict[str, str], copied: list[str]) -> str:
    """Pre-fill LAYOUT.md with one block per reference screenshot.

    The agent still has to look and write, but it should never have to work
    out *which* files to look at or what shape each one is - that part is known.
    """
    template = (TEMPLATES_ROOT / "LAYOUT.md.tmpl").read_text(encoding="utf-8")
    media = brief.get("reference_design", {}).get("media", [])
    blocks = ["## Screens", ""]
    if not media:
        blocks.append("_No reference imagery - this design was matched on text alone. "
                      "Build from DESIGN.md instead._")
    for i, item in enumerate(media[:8], 1):
        rel = copied[i - 1] if i - 1 < len(copied) else item["path"]
        size = f"{item['width']}x{item['height']}" if item.get("width") else "size unknown"
        shape = item.get("shape", "")
        hint = {
            "full-page": "a whole scrolled page - read it top to bottom for section order and rhythm",
            "viewport": "one screen - read it for composition and how much air the headline gets",
            "wide-banner": "a hero or a section detail - read it for type scale",
        }.get(shape, "")
        blocks += [
            f"### Screen {i} - `{rel}` ({size}{', ' + shape if shape else ''})",
            f"_{hint}_" if hint else "",
            "",
            "| # | Region (top -> bottom) | Component type | Contents (copy, counts, media) | Layout (cols, alignment) | States / motion |",
            "|---|---|---|---|---|---|",
            "| 1 | | | | | |",
            "| 2 | | | | | |",
            "| 3 | | | | | |",
            "",
        ]
    mobile = ""
    if brief.get("platform") == "mobile":
        mobile = "\n".join([
            "## Mobile derivation",
            "",
            "The reference is a desktop page. Record how each web region becomes a phone",
            "treatment - see the properui skill's `references/mobile-derivation.md`.",
            "",
            "| Web region | Mobile treatment | Tab |",
            "|---|---|---|",
            "| nav | | |",
            "| hero | | home |",
            "| footer | | settings |",
        ])
    return _render(template, {**values, "SCREEN_BLOCKS": "\n".join(blocks).strip(),
                              "MOBILE_BLOCK": mobile,
                              "COMPANY": brief.get("company") or values.get("TITLE", ""),
                              "MODE": values["COLOR_SCHEME"],
                              "FONT_DISPLAY": brief["tokens"]["fonts"][0],
                              "FONT_BODY": brief["tokens"]["fonts"][1] if len(brief["tokens"]["fonts"]) > 1 else "-"})


def _render(template: str, values: dict[str, str]) -> str:
    for key, value in values.items():
        template = template.replace("{{" + key + "}}", value)
    return template


def generate(brief: dict[str, Any], out_dir: Path, *, force: bool = False) -> dict[str, Any]:
    out_dir = Path(out_dir)
    if out_dir.exists() and any(out_dir.iterdir()) and not force:
        raise FileExistsError(f"{out_dir} already exists and is not empty (pass force=True to overwrite)")
    out_dir.mkdir(parents=True, exist_ok=True)

    tokens = brief["tokens"]
    direction = brief["direction"]
    ref = brief["reference_design"]
    is_dark = direction["mode"] == "dark"
    slug = _slugify(brief.get("project") or ref.get("slug") or "site")

    colours = _roles(brief, is_dark)
    fonts = _font_plan(tokens["fonts"])
    scale = tokens["type_scale"]

    values = {
        "SLUG": slug,
        "TITLE": brief.get("project") or ref.get("title", "New site"),
        "DESCRIPTION": (brief.get("prompt") or ref.get("use_case", ""))[:180],
        "REFERENCE_TITLE": ref.get("title", ""),
        "COLOR_GROUND": colours["ground"],
        "COLOR_SURFACE": colours["surface"],
        "COLOR_INK": colours["ink"],
        "COLOR_MUTED": colours["muted"],
        "COLOR_ACCENT": colours["accent"],
        "COLOR_ACCENT2": colours.get("accent2", colour.mix(colours["accent"], colours["ink"], 0.35)),
        "COLOR_SCHEME": "dark" if is_dark else "light",
        "PALETTE_JSON": json.dumps(tokens["palette"]),
        "FONT_IMPORTS": fonts["imports"],
        "FONT_CLASS_ATTR": fonts["class_attr"],
        "FONT_DISPLAY_STACK": fonts["display_stack"],
        "FONT_BODY_STACK": fonts["body_stack"],
        "RADIUS": tokens["radius"],
        "SHADOW": tokens["shadow"],
        "PAD_DESKTOP": tokens["section_padding_desktop"],
        "PAD_MOBILE": tokens["section_padding_mobile"],
        "DISPLAY_SIZE": scale["display"],
        "H1_SIZE": scale["h1"],
        "H2_SIZE": scale["h2"],
        "BODY_SIZE": scale["body"],
        "LEADING_DISPLAY": scale["leading_display"],
    }

    written: list[str] = []

    def write(rel: str, content: str) -> None:
        path = out_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written.append(rel)

    # Static config copied as-is.
    for name in ("next.config.mjs", "postcss.config.mjs", "tsconfig.json"):
        write(name, (TEMPLATES / name).read_text(encoding="utf-8"))
    write(".gitignore", (TEMPLATES / "gitignore.tmpl").read_text(encoding="utf-8"))

    # Templated files.
    for src, dest in (
        ("package.json.tmpl", "package.json"),
        ("app/globals.css.tmpl", "app/globals.css"),
        ("app/layout.tsx.tmpl", "app/layout.tsx"),
        ("lib/tokens.ts.tmpl", "lib/tokens.ts"),
    ):
        write(dest, _render((TEMPLATES / src).read_text(encoding="utf-8"), values))

    for name in ("Reveal.tsx", "Section.tsx"):
        write(f"components/{name}", (TEMPLATES / "components" / name).read_text(encoding="utf-8"))

    # One component per planned section, each carrying its own guidance.
    section_tmpl = (TEMPLATES / "components" / "SectionTemplate.tsx.tmpl").read_text(encoding="utf-8")
    imports, tags = [], []
    for i, section in enumerate(brief["sections"]):
        component = _component_name(section)
        guidance = SECTION_GUIDANCE.get(section, ["Implement against the brief in DESIGN.md."])
        write(
            f"components/sections/{component}.tsx",
            _render(section_tmpl, {
                **values,
                "COMPONENT": component,
                "SECTION_ID": section,
                "SECTION_TITLE": SECTION_TITLES.get(section, section.title()),
                "SECTION_TONE": "surface" if i % 2 else "ground",
                "SECTION_GUIDANCE": "\n".join(f" * - {line}" for line in guidance),
            }),
        )
        imports.append(f'import {{ {component} }} from "@/components/sections/{component}";')
        tags.append(f"      <{component} />")

    write("app/page.tsx", _render((TEMPLATES / "app" / "page.tsx.tmpl").read_text(encoding="utf-8"),
                                  {**values, "SECTION_IMPORTS": "\n".join(imports),
                                   "SECTION_TAGS": "\n".join(tags)}))

    # The brief travels with the project, in both readable and machine form.
    from . import brief as brief_module
    write("DESIGN.md", brief_module.render_markdown(brief))
    write("designice.json", json.dumps(brief, indent=2))
    write("README.md", _readme(values, brief, fonts["notes"]))
    write("public/.gitkeep", "")

    # Copy the reference imagery in so it is visible next to the code an agent
    # is about to write. Looking at the reference is the single highest-value
    # thing it can do, and it will not go hunting for a path.
    copied = _copy_reference_media(brief, out_dir)
    written.extend(copied)
    write("LAYOUT.md", _layout_inventory(brief, values, copied))

    return {
        "out_dir": str(out_dir),
        "platform": "web",
        "files": written,
        "sections": brief["sections"],
        "colours": colours,
        "font_notes": fonts["notes"],
        "reference_media": copied,
        "next_steps": [
            f"cd {out_dir} && npm install",
            "npm run dev",
            "Look at design-reference/, fill LAYOUT.md, then implement components/sections/",
            "npm run build  # emits .next/standalone/server.js",
        ],
    }


def _copy_reference_media(brief: dict[str, Any], out_dir: Path) -> list[str]:
    from .config import library_dir

    media = brief.get("reference_design", {}).get("media", [])
    if not media:
        return []
    dest_dir = out_dir / "design-reference"
    dest_dir.mkdir(parents=True, exist_ok=True)
    library = library_dir()
    copied: list[str] = []
    for item in media[:8]:
        src = library / item["path"]
        if not src.exists():
            continue
        # Files often arrive without an extension; give them one so editors and
        # browsers will actually preview them.
        suffix = src.suffix or f".{item.get('format', 'png')}"
        dest = dest_dir / (src.stem + suffix)
        try:
            shutil.copy2(src, dest)
            copied.append(str(dest.relative_to(out_dir)))
        except OSError:
            continue
    return copied


# ------------------------------------------------------------------ Expo target

# Google fonts that ship a single weight only. Asking @expo-google-fonts for a
# _700Bold that does not exist is a Metro resolution error on first start.
SINGLE_WEIGHT = {"Instrument Serif", "Anton", "Bebas Neue", "DM Serif Display", "Space Mono"}


def _expo_font_plan(fonts: list[str]) -> dict[str, Any]:
    """Wire Google fonts through @expo-google-fonts; anything else uses the system face.

    Returns the package.json fragment, the import lines, the useFonts map, and
    the family names theme.ts should reference - which are the export names
    (e.g. "SpaceGrotesk_700Bold"), because that is what expo-font registers.
    """
    display = fonts[0] if fonts else "Inter"
    body = fonts[1] if len(fonts) > 1 else "Inter"

    deps: list[str] = []
    imports: list[str] = []
    font_map: list[str] = []
    families: dict[str, str] = {}
    notes: list[str] = []

    for role, font in (("display", display), ("body", body)):
        if font in GOOGLE_FONTS:
            kebab = re.sub(r"[^a-z0-9]+", "-", font.lower()).strip("-")
            pascal = "".join(part.capitalize() for part in re.split(r"[^A-Za-z0-9]+", font) if part)
            regular = f"{pascal}_400Regular"
            bold = regular if font in SINGLE_WEIGHT else f"{pascal}_700Bold"
            pkg = f"@expo-google-fonts/{kebab}"
            if f'"{pkg}"' not in "".join(deps):
                deps.append(f',\n    "{pkg}": ">=0.3.0"')
            names = [regular] + ([bold] if bold != regular else [])
            imports.append(f'import {{ {", ".join(names)} }} from "{pkg}";')
            for name in names:
                line = f"    {name},"
                if line not in font_map:
                    font_map.append(line)
            families[f"{role}"] = regular
            families[f"{role}_bold"] = bold
            if font in SINGLE_WEIGHT:
                notes.append(f"{font} ships one weight; bold text will use the same face")
        else:
            families[f"{role}"] = "System"
            families[f"{role}_bold"] = "System"
            notes.append(f"{font} is not on Google Fonts. Add its .ttf files under assets/fonts/, "
                         f"register them in app/_layout.tsx, and set theme.fonts.{role}.")

    # Dedupe imports from the same package into one line.
    merged: dict[str, list[str]] = {}
    for line in imports:
        m = re.match(r'import \{ (.+) \} from "(.+)";', line)
        if m:
            merged.setdefault(m.group(2), [])
            for name in m.group(1).split(", "):
                if name not in merged[m.group(2)]:
                    merged[m.group(2)].append(name)
    import_lines = [f'import {{ {", ".join(v)} }} from "{k}";' for k, v in merged.items()]

    return {
        "deps": "".join(deps),
        "imports": "\n".join(import_lines),
        "font_map": "\n".join(font_map) if font_map else "    // no Google fonts to load",
        "families": families,
        "notes": notes,
    }


def generate_expo(brief: dict[str, Any], out_dir: Path, *, force: bool = False) -> dict[str, Any]:
    """Emit an Expo Router app wired to the brief's tokens.

    Same philosophy as the web scaffold: everything mechanical (tokens, fonts,
    safe areas, tab shell, one block per section) is written by the script so
    it is right everywhere at once; the layout inside each block is the
    agent's, working from LAYOUT.md and the reference screenshots.
    """
    out_dir = Path(out_dir)
    if out_dir.exists() and any(out_dir.iterdir()) and not force:
        raise FileExistsError(f"{out_dir} already exists and is not empty (pass force=True to overwrite)")
    out_dir.mkdir(parents=True, exist_ok=True)

    tokens = brief["tokens"]
    ref = brief["reference_design"]
    roles = _roles(brief, brief["direction"]["mode"] == "dark")
    is_dark = colour.is_dark(roles["ground"])
    slug = _slugify(brief.get("project") or ref.get("slug") or "app")
    fonts = _expo_font_plan(tokens["fonts"])
    radius_pt = int(re.sub(r"[^0-9]", "", tokens.get("radius", "12px")) or 12)

    values = {
        "SLUG": slug,
        "TITLE": brief.get("company") or brief.get("project") or ref.get("title", "App"),
        "REFERENCE_TITLE": ref.get("title", ""),
        "COLOR_GROUND": roles["ground"],
        "COLOR_SURFACE": roles["surface"],
        "COLOR_INK": roles["ink"],
        "COLOR_MUTED": roles["muted"],
        "COLOR_ACCENT": roles["accent"],
        "COLOR_ACCENT2": roles.get("accent2", colour.mix(roles["accent"], roles["ink"], 0.35)),
        "COLOR_SCHEME": "dark" if is_dark else "light",
        "HAIRLINE": "rgba(255,255,255,0.10)" if is_dark else "rgba(0,0,0,0.08)",
        "RADIUS_PT": str(radius_pt),
        "FONT_DEPS": fonts["deps"],
        "FONT_IMPORTS": fonts["imports"],
        "FONT_MAP": fonts["font_map"],
        "FONT_DISPLAY_FAMILY": fonts["families"]["display"],
        "FONT_DISPLAY_BOLD_FAMILY": fonts["families"]["display_bold"],
        "FONT_BODY_FAMILY": fonts["families"]["body"],
        "FONT_BODY_BOLD_FAMILY": fonts["families"]["body_bold"],
    }

    written: list[str] = []

    def write(rel: str, content: str) -> None:
        path = out_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written.append(rel)

    write("tsconfig.json", (EXPO_TEMPLATES / "tsconfig.json").read_text(encoding="utf-8"))
    write(".gitignore", (EXPO_TEMPLATES / "gitignore.tmpl").read_text(encoding="utf-8"))
    for src, dest in (
        ("package.json.tmpl", "package.json"),
        ("app.json.tmpl", "app.json"),
        ("lib/theme.ts.tmpl", "lib/theme.ts"),
        ("app/_layout.tsx.tmpl", "app/_layout.tsx"),
        ("app/(tabs)/_layout.tsx.tmpl", "app/(tabs)/_layout.tsx"),
        ("app/(tabs)/settings.tsx.tmpl", "app/(tabs)/settings.tsx"),
    ):
        write(dest, _render((EXPO_TEMPLATES / src).read_text(encoding="utf-8"), values))
    for name in ("Screen.tsx", "Section.tsx"):
        write(f"components/{name}", (EXPO_TEMPLATES / "components" / name).read_text(encoding="utf-8"))

    # One block per section. Nav and footer are handled by the tab shell, so
    # they do not become blocks - a phone has no nav bar to build and its
    # footer is the "More" tab.
    block_tmpl = (EXPO_TEMPLATES / "components" / "BlockTemplate.tsx.tmpl").read_text(encoding="utf-8")
    blocks = [s for s in brief["sections"] if s not in ("nav", "footer")]
    imports, tags = [], []
    for i, section in enumerate(blocks):
        component = _component_name(section)
        guidance = SECTION_GUIDANCE.get(section, ["Implement against LAYOUT.md."])
        write(
            f"components/blocks/{component}.tsx",
            _render(block_tmpl, {
                **values,
                "COMPONENT": component,
                "SECTION_TITLE": SECTION_TITLES.get(section, section.title()),
                "SECTION_TONE": "surface" if i % 2 else "ground",
                "SECTION_GUIDANCE": "\n".join(f" * - {line}" for line in guidance),
            }),
        )
        imports.append(f'import {{ {component} }} from "@/components/blocks/{component}";')
        tags.append(f"      <{component} />")
    write("app/(tabs)/index.tsx",
          _render((EXPO_TEMPLATES / "app" / "(tabs)" / "index.tsx.tmpl").read_text(encoding="utf-8"),
                  {**values, "BLOCK_IMPORTS": "\n".join(imports), "BLOCK_TAGS": "\n".join(tags)}))

    from . import brief as brief_module
    write("DESIGN.md", brief_module.render_markdown(brief))
    write("designice.json", json.dumps(brief, indent=2))
    copied = _copy_reference_media(brief, out_dir)
    written.extend(copied)
    write("LAYOUT.md", _layout_inventory(brief, values, copied))
    write("README.md", _expo_readme(values, brief, fonts["notes"]))

    return {
        "out_dir": str(out_dir),
        "platform": "mobile",
        "files": written,
        "sections": blocks,
        "colours": roles,
        "font_notes": fonts["notes"],
        "reference_media": copied,
        "next_steps": [
            f"cd {out_dir} && npm install && npx expo install --fix",
            "npx expo start   # then open in Expo Go (SDK 57) or a simulator",
            "Look at design-reference/, fill LAYOUT.md including the Mobile derivation table,",
            "then implement components/blocks/",
        ],
    }


def _expo_readme(values: dict[str, str], brief: dict[str, Any], font_notes: list[str]) -> str:
    ref = brief["reference_design"]
    lines = [
        f"# {values['TITLE']}",
        "",
        f"Expo (React Native) app generated by `designice scaffold --platform mobile` from the",
        f"reference design **{ref['title']}** - a desktop web reference, translated for a phone.",
        "",
        "```bash",
        "npm install",
        "npx expo install --fix   # aligns every native package to the installed SDK",
        "npx expo start           # scan the QR with Expo Go, or press i / a for a simulator",
        "```",
        "",
        "## What is here",
        "",
        "- `LAYOUT.md` - the inventory of the reference screens and how each region becomes a",
        "  phone treatment. Fill it before writing a block.",
        "- `lib/theme.ts` - every token. Nothing else may hold a colour or a font name.",
        "- `app/(tabs)/` - Expo Router tab shell: Home composes the blocks, More holds the footer.",
        "- `components/blocks/` - one component per reference section, each with its guidance.",
        "- `design-reference/` - the screenshots this direction came from.",
        "",
        "## Shipping",
        "",
        "`npx expo export` produces a static bundle; `eas build` produces installable binaries.",
        "Neither is needed to iterate - Expo Go runs the project straight from `expo start`.",
    ]
    if font_notes:
        lines += ["", "## Fonts needing attention", ""] + [f"- {n}" for n in font_notes]
    return "\n".join(lines) + "\n"


def _readme(values: dict[str, str], brief: dict[str, Any], font_notes: list[str]) -> str:
    ref = brief["reference_design"]
    lines = [
        f"# {values['TITLE']}",
        "",
        f"Generated by `designice scaffold` from the reference design **{ref['title']}**.",
        "",
        "```bash",
        "npm install",
        "npm run dev          # http://localhost:3000",
        "npm run build        # standalone server at .next/standalone/server.js",
        "node .next/standalone/server.js",
        "```",
        "",
        "## What is here",
        "",
        "- `DESIGN.md` - the brief. Read it before changing anything visual.",
        "- `app/globals.css` - every design token. Change values here, not in components.",
        "- `lib/tokens.ts` - the same tokens for canvas, WebGL and chart code.",
        "- `components/sections/` - one component per planned section, each carrying its brief.",
        "- `design-reference/` - the reference imagery this direction came from.",
        "",
        "## Deploying the standalone output",
        "",
        "`next build` traces every file the app needs into `.next/standalone`. Copy that",
        "directory, plus `.next/static` and `public/`, onto any Node 18+ host and run",
        "`node server.js`. No `node_modules` needed at runtime.",
    ]
    if font_notes:
        lines += ["", "## Fonts needing attention", ""] + [f"- {n}" for n in font_notes]
    return "\n".join(lines) + "\n"
