"""Tests for the template re-skin path: colour overrides, media-required matching,
the Expo scaffold, and the library-hygiene checks that keep templates honest."""

import json
import re

import pytest

from designice import brief, colour, ingest, scaffold, search, store
from designice.cli import _duplicate_descriptions

PNG_HEAD = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR"
PNG_IEND = b"\x00\x00\x00\x00IEND\xaeB`\x82"


def fake_png(width=1440, height=900):
    return PNG_HEAD + width.to_bytes(4, "big") + height.to_bytes(4, "big") + b"\x00" * 20 + PNG_IEND


@pytest.fixture
def library(tmp_path):
    def add(name, description, meta=None, images=0):
        folder = tmp_path / name
        folder.mkdir()
        (folder / "description.txt").write_text(description, encoding="utf-8")
        if meta:
            (folder / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
        for i in range(images):
            (folder / f"image_original{i or ''}.png").write_bytes(fake_png())
        return folder

    # A real capture: screenshots, business prose, no meta.json - the common case.
    add("MoolaX — Time Tracking & Invoicing SaaS",
        "MoolaX is a SaaS time-tracking and invoicing platform built for boutique creative "
        "agencies and freelancers. React frontend, Stripe and Plaid integrations.", images=3)
    # An authored template with a palette in role order.
    add("Wealthcore",
        "A dark private banking landing page with champagne gold hairlines on off-black.",
        {"title": "Wealthcore", "use_case": "Website for a private bank",
         "tags": {"industry": ["fintech"], "style": ["luxury"], "page_type": ["landing-page"],
                  "palette": ["dark"]},
         "palette": ["#0A0A0B", "#141416", "#C8A96A", "#E8E6E1", "#8A8A93"],
         "fonts": ["Instrument Serif", "Inter"]}, images=1)
    # A text-only art brief that must never be picked as a template.
    add("Invoice Brief",
        "An art-direction brief for an invoicing and time tracking product for freelancers. "
        "Warm neutrals, generous type, calm.",
        {"title": "Invoice Brief", "use_case": "Website for an invoicing product",
         "tags": {"industry": ["fintech", "saas"], "page_type": ["landing-page"]}})
    return tmp_path


@pytest.fixture
def index(library):
    return store.build(library, "lexical")


def _template(index, slug):
    return next(d for d in index["designs"] if d["slug"] == slug)


# ------------------------------------------------------------------ colour

def test_primary_and_secondary_map_to_accents_leaving_neutrals():
    roles = colour.roles_from_palette(["#0A0A0B", "#141416", "#C8A96A", "#E8E6E1", "#8A8A93"], True)
    out, notes = colour.apply_overrides(roles, {"primary": "#0F766E", "secondary": "#F59E0B"})
    assert out["accent"] == "#0F766E"
    assert out["accent2"] == "#F59E0B"
    for role in ("ground", "surface", "ink", "muted"):
        assert out[role] == roles[role], f"{role} must not move when only brand colours change"
    assert not [n for n in notes if "ink" in n]


def test_ground_override_rederives_surface_and_flips_mode():
    roles = colour.roles_from_palette(["#0A0A0B", "#141416", "#C8A96A", "#E8E6E1"], True)
    out, _ = colour.apply_overrides(roles, {"ground": "#FFFFFF"})
    assert colour.mode_of(out) == "light"
    assert out["surface"] != roles["surface"]
    assert colour.contrast(out["ink"], out["ground"]) >= colour.MIN_INK_CONTRAST


def test_illegible_ink_is_corrected_and_noted():
    roles = colour.roles_from_palette(["#FFFFFF", "#F5F5F7", "#3D5AFE", "#111113"], False)
    out, notes = colour.apply_overrides(roles, {"ink": "#EEEEEE"})
    assert out["ink"] != "#EEEEEE"
    assert any("swapped" in n for n in notes)


def test_low_contrast_brand_colour_is_noted_not_changed():
    roles = colour.roles_from_palette(["#FFFFFF", "#F5F5F7", "#3D5AFE", "#111113"], False)
    out, notes = colour.apply_overrides(roles, {"primary": "#F5E6A3"})  # pale yellow on white
    assert out["accent"] == "#F5E6A3", "a brand colour is never recoloured"
    assert any("accent" in n and "fills" in n for n in notes)


def test_non_hex_override_is_ignored_with_a_note():
    roles = colour.roles_from_palette(["#FFFFFF", "#F5F5F7", "#3D5AFE", "#111113"], False)
    out, notes = colour.apply_overrides(roles, {"primary": "teal"})
    assert out["accent"] == roles["accent"]
    assert any("not a hex" in n for n in notes)


# ------------------------------------------------------------------- brief

def test_brief_marks_fallback_tokens_for_a_bare_capture(index):
    design = _template(index, "moolax-time-tracking-and-invoicing-saas")
    built = brief.build(design, "invoicing for freelancers")
    assert built["template_tokens"]["source"] == "fallback"
    assert "no authored tokens" in brief.render_markdown(built)


def test_brief_marks_meta_tokens_for_an_authored_design(index):
    built = brief.build(_template(index, "wealthcore"), "private bank")
    assert built["template_tokens"]["source"] == "meta"
    assert built["template_tokens"]["roles"]["accent"] == "#C8A96A"


def test_overrides_flow_into_tokens_and_the_markdown_table(index):
    built = brief.build(_template(index, "wealthcore"), "a bank", overrides={
        "primary": "#0F766E", "secondary": "#F59E0B", "font_display": "Space Grotesk",
        "company": "Acme"})
    assert built["tokens"]["roles"]["accent"] == "#0F766E"
    assert built["tokens"]["fonts"][0] == "Space Grotesk"
    assert built["tokens"]["fonts"][1] == "Inter", "body font untouched when not overridden"
    md = brief.render_markdown(built)
    assert "| accent | `#C8A96A` | `#0F766E` **<-** |" in md
    assert "| body font | Inter | Inter |" in md


def test_sections_override_replaces_the_derived_plan(index):
    built = brief.build(_template(index, "wealthcore"), "a bank",
                        overrides={"sections": "nav,hero,pricing,footer"})
    assert built["sections"] == ["nav", "hero", "pricing", "footer"]


def test_mobile_platform_drops_web_only_motion(index):
    design = dict(_template(index, "wealthcore"))
    design["tags"] = {**design["tags"], "motion": ["marquee", "reveal-on-scroll", "magnetic-cursor"]}
    built = brief.build(design, "a bank", overrides={"platform": "mobile"})
    techniques = {m["technique"] for m in built["motion"]}
    assert "marquee" not in techniques and "magnetic-cursor" not in techniques
    assert any("44pt" in c for c in built["constraints"])


# ------------------------------------------------------------------ search

def test_require_media_excludes_text_only_designs(index):
    loose = search.search("invoicing product for freelancers", index, k=3)
    strict = search.search("invoicing product for freelancers", index, k=3, require_media=True)
    assert "invoice-brief" in {h["slug"] for h in loose}
    assert "invoice-brief" not in {h["slug"] for h in strict}
    assert strict[0]["slug"] == "moolax-time-tracking-and-invoicing-saas"


# ------------------------------------------------------------------- expo

@pytest.fixture
def mobile_brief(index):
    return brief.build(_template(index, "wealthcore"), "a bank app", project="acme", overrides={
        "platform": "mobile", "company": "Acme", "primary": "#0F766E",
        "font_display": "Space Grotesk", "font_body": "Inter",
        "sections": "nav,hero,features,pricing,footer"})


def test_expo_scaffold_is_complete_and_substituted(mobile_brief, tmp_path):
    result = scaffold.generate_expo(mobile_brief, tmp_path / "app")
    out = tmp_path / "app"
    for rel in ("package.json", "app.json", "app/_layout.tsx", "app/(tabs)/_layout.tsx",
                "app/(tabs)/index.tsx", "app/(tabs)/settings.tsx", "lib/theme.ts",
                "components/Screen.tsx", "components/Section.tsx", "LAYOUT.md", "DESIGN.md"):
        assert (out / rel).exists(), rel
    for path in out.rglob("*"):
        if path.suffix in {".ts", ".tsx", ".json", ".md"} and "design-reference" not in path.parts:
            assert not re.search(r"\{\{[A-Z_]+\}\}", path.read_text()), f"placeholder left in {path.name}"
    # nav and footer are the tab shell, not blocks
    assert result["sections"] == ["hero", "features", "pricing"]
    assert {p.name for p in (out / "components" / "blocks").iterdir()} == {"Hero.tsx", "Features.tsx", "Pricing.tsx"}
    assert "#0F766E" in (out / "lib" / "theme.ts").read_text()
    assert '"main": "expo-router/entry"' in (out / "package.json").read_text()


def test_expo_google_fonts_are_wired_by_export_name(mobile_brief, tmp_path):
    scaffold.generate_expo(mobile_brief, tmp_path / "app")
    layout = (tmp_path / "app" / "app" / "_layout.tsx").read_text()
    theme = (tmp_path / "app" / "lib" / "theme.ts").read_text()
    pkg = json.loads((tmp_path / "app" / "package.json").read_text())
    assert 'from "@expo-google-fonts/space-grotesk"' in layout
    assert "SpaceGrotesk_700Bold" in layout
    assert 'displayBold: "SpaceGrotesk_700Bold"' in theme
    assert "@expo-google-fonts/space-grotesk" in pkg["dependencies"]
    assert "@expo-google-fonts/inter" in pkg["dependencies"]


def test_single_weight_font_gets_no_bold_import(mobile_brief, tmp_path):
    mobile_brief["tokens"]["fonts"] = ["Instrument Serif", "Inter"]
    result = scaffold.generate_expo(mobile_brief, tmp_path / "app")
    layout = (tmp_path / "app" / "app" / "_layout.tsx").read_text()
    assert "InstrumentSerif_400Regular" in layout
    assert "InstrumentSerif_700Bold" not in layout, "a 700 import that does not exist breaks Metro"
    assert any("one weight" in n for n in result["font_notes"])


def test_non_google_font_becomes_system_with_a_note(mobile_brief, tmp_path):
    mobile_brief["tokens"]["fonts"] = ["Canela", "Inter"]
    result = scaffold.generate_expo(mobile_brief, tmp_path / "app")
    theme = (tmp_path / "app" / "lib" / "theme.ts").read_text()
    assert 'display: "System"' in theme
    assert any("Canela" in n for n in result["font_notes"])
    assert "Canela" not in (tmp_path / "app" / "app" / "_layout.tsx").read_text()


def test_layout_inventory_lists_each_screenshot(mobile_brief, tmp_path, library, monkeypatch):
    monkeypatch.setenv("DESIGNICE_LIBRARY", str(library))
    scaffold.generate_expo(mobile_brief, tmp_path / "app")
    layout_md = (tmp_path / "app" / "LAYOUT.md").read_text()
    assert "### Screen 1" in layout_md
    assert "## Mobile derivation" in layout_md
    assert "Acme" in layout_md


def test_web_scaffold_gains_accent2_and_layout(index, tmp_path, library, monkeypatch):
    monkeypatch.setenv("DESIGNICE_LIBRARY", str(library))
    built = brief.build(_template(index, "wealthcore"), "a bank", project="acme",
                        overrides={"secondary": "#F59E0B"})
    scaffold.generate(built, tmp_path / "web")
    css = (tmp_path / "web" / "app" / "globals.css").read_text()
    assert "--color-accent2: #F59E0B" in css
    assert (tmp_path / "web" / "LAYOUT.md").exists()
    assert "## Mobile derivation" not in (tmp_path / "web" / "LAYOUT.md").read_text()


# ---------------------------------------------------------------- hygiene

def test_status_flags_identical_descriptions(library):
    (library / "Copycat").mkdir()
    (library / "Copycat" / "description.txt").write_text(
        (library / "Wealthcore" / "description.txt").read_text(), encoding="utf-8")
    groups = _duplicate_descriptions(ingest.scan(library))
    assert ["copycat", "wealthcore"] in groups


def test_muted_is_never_a_brand_colour():
    # NowUtalk's palette: a mid-luminance magenta used to win the "muted" role on
    # luminance alone, which would leak the template's brand into body text.
    roles = colour.roles_from_palette(
        ["#FFFFFF", "#F7F7FA", "#7B3FE4", "#111111", "#5B5B66", "#E040A0"], False)
    assert roles["muted"] == "#5B5B66"
    assert roles["ink"] == "#111111"
    assert {roles["accent"], roles["accent2"]} == {"#7B3FE4", "#E040A0"}
    assert colour.chroma(roles["muted"]) < colour.NEUTRAL_CHROMA


def test_new_design_is_searchable_without_reindexing(library):
    store.save(store.build(library, "lexical"), library)
    folder = library / "Brutal Portfolio"
    folder.mkdir()
    (folder / "description.txt").write_text(
        "A raw brutalist portfolio: black type on white, hairlines, no images.", encoding="utf-8")
    # No `designice index` in between - load_or_build must notice the new folder.
    index = store.load_or_build(library)
    assert "brutal-portfolio" in {d["slug"] for d in index["designs"]}
    assert search.search("brutalist portfolio", index, k=1)[0]["slug"] == "brutal-portfolio"


def test_static_google_fonts_get_an_explicit_weight(index, tmp_path, library, monkeypatch):
    # next/font/google fails the build for a non-variable font with no `weight`.
    # Instrument Serif ships a single weight; Inter is variable and must stay bare.
    monkeypatch.setenv("DESIGNICE_LIBRARY", str(library))
    built = brief.build(_template(index, "wealthcore"), "a bank", project="w")
    built["tokens"]["fonts"] = ["Instrument Serif", "Inter"]
    scaffold.generate(built, tmp_path / "w")
    layout = (tmp_path / "w" / "app" / "layout.tsx").read_text()
    assert 'DisplayFont({ subsets: ["latin"], weight: ["400"], ' in layout
    assert 'BodyFont({ subsets: ["latin"], variable:' in layout
