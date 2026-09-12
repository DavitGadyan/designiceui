"""Tests for the parts that are easy to break silently.

The theme is regressions that would not raise: a design that stops being found,
a tag that leaks from prose into a build brief, an index that reads back into a
different vector space than it was written in.
"""

import json
import os

import pytest

from designice import brief, embed, ingest, scaffold, search, store, taxonomy


@pytest.fixture
def library(tmp_path):
    """A small library with a deliberate trap: the fintech design's description
    ends by listing unrelated industries, exactly as a real one does."""
    def add(name, description, meta=None):
        folder = tmp_path / name
        folder.mkdir()
        (folder / "description.txt").write_text(description, encoding="utf-8")
        if meta:
            (folder / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
        return folder

    add(
        "Wealthcore",
        "A dark private banking landing page. Champagne gold #C8A96A hairlines on "
        "off-black #0A0A0B. Restrained, expensive, nothing bounces. "
        "Use for private banking, insurance, legal and music labels.",
        {"title": "Wealthcore", "use_case": "Website for a private bank",
         "tags": {"industry": ["fintech"], "style": ["luxury", "minimal"],
                  "page_type": ["landing-page"], "palette": ["dark"]},
         "palette": ["#0A0A0B", "#141416", "#C8A96A", "#E8E6E1"],
         "fonts": ["Instrument Serif", "Inter"]},
    )
    add(
        "Mindora",
        "A soft wellness landing page on warm off-white #FBF7F4 with lilac and sage "
        "blobs drifting behind centred serif type. Everything is slow and round.",
        {"title": "Mindora", "use_case": "Website for a meditation app",
         "tags": {"industry": ["wellness"], "style": ["organic"],
                  "page_type": ["landing-page"], "palette": ["light", "pastel"]},
         "palette": ["#FBF7F4", "#E9DFF7", "#3B3746"]},
    )
    add(
        "Skytrace",
        "A dark B2B SaaS landing page. Near-black ground, one indigo accent, a centred "
        "hero with a tilted product screenshot that straightens as it scrolls into view, "
        "then a bento grid and three pricing tiers.",
        {"title": "Skytrace", "use_case": "Website for a B2B SaaS product",
         "tags": {"industry": ["saas"], "style": ["corporate"],
                  "page_type": ["landing-page"], "palette": ["dark"]},
         "palette": ["#0B0B0C", "#17181B", "#E7E7EA", "#3D5AFE"]},
    )
    add(
        "Glass Features",
        "A reusable frosted glass features section for dark product sites. "
        "backdrop-filter blur over drifting violet and cyan gradients.",
        {"title": "Glass Features", "use_case": "A features section for any product site",
         "tags": {"industry": ["saas"], "style": ["glassmorphic"],
                  "page_type": ["component"], "section": ["features"], "palette": ["dark"]}},
    )
    return tmp_path


@pytest.fixture
def index(library):
    return store.build(library, "lexical")


# --------------------------------------------------------------------- taxonomy

def test_detects_industry_from_paraphrase():
    tags = taxonomy.detect_tags("a website for my neobank")
    assert "fintech" in tags["industry"]


def test_word_boundaries_are_respected():
    # "ai" must not match inside "chair"; a naive substring check gets this wrong.
    assert "ai" not in taxonomy.detect_tags("a shop selling chairs").get("industry", [])


def test_expansion_bridges_vocabulary():
    terms = taxonomy.expansion_terms("website for a bank")
    assert "fintech" in terms and "payments" in terms


# ------------------------------------------------------------------------ ingest

PNG_HEAD = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR"
PNG_IEND = b"\x00\x00\x00\x00IEND\xaeB`\x82"


def fake_png(width=1200, height=3000, complete=True):
    body = PNG_HEAD + width.to_bytes(4, "big") + height.to_bytes(4, "big") + b"\x00" * 20
    return body + (PNG_IEND if complete else b"")


def test_extensionless_image_is_found(library):
    folder = library / "Wealthcore"
    (folder / "image_original").write_bytes(fake_png())
    design = ingest.load_design(folder, library)
    media = [m for m in design.media if m["name"] == "image_original"]
    assert media, "a PNG with no extension must still be picked up"
    assert (media[0]["width"], media[0]["height"]) == (1200, 3000)
    assert media[0]["shape"] == "full-page"


def test_truncated_png_is_not_media(library):
    # A browser that died mid-download leaves a valid header and no IEND. It
    # must not be indexed - it would sort first and become the hero reference.
    folder = library / "Wealthcore"
    (folder / "Unconfirmed 1234.crdownload").write_bytes(fake_png(complete=False))
    (folder / "half.png").write_bytes(fake_png(complete=False))
    design = ingest.load_design(folder, library)
    names = {m["name"] for m in design.media}
    assert "Unconfirmed 1234.crdownload" not in names
    assert "half.png" not in names


def test_slug_survives_awkward_folder_names(tmp_path):
    folder = tmp_path / "Kayenpeppa.com — Design Studio Portfolio 2026"
    folder.mkdir()
    (folder / "description.txt").write_text("A studio portfolio.", encoding="utf-8")
    design = ingest.load_design(folder, tmp_path)
    assert design.slug == "kayenpeppa-com-design-studio-portfolio-2026"


def test_prose_industries_reach_tags_but_not_primary(library):
    design = ingest.load_design(library / "Wealthcore", library)
    # The closing "use for ... legal and music" line should help recall ...
    assert "legal" in design.tags["industry"]
    # ... but must never drive the build brief.
    assert design.primary["industry"] == ["fintech"]


def test_authored_tag_order_is_preserved(library):
    design = ingest.load_design(library / "Wealthcore", library)
    assert design.primary["style"][0] == "luxury"


# ------------------------------------------------------------------------- store

def test_index_roundtrips_into_the_same_space(library, index):
    store.save(index, library)
    reloaded = store.load(library)
    backend = store.backend_for(reloaded)
    # A query encoded from the reloaded state must score identically, or search
    # silently degrades after a restart.
    fresh = search.search("private bank website", index, k=1)[0]
    after = search.search("private bank website", reloaded, k=1, backend=backend)[0]
    assert fresh["slug"] == after["slug"]
    assert fresh["score"] == pytest.approx(after["score"])


def test_staleness_notices_a_new_design(library, index):
    store.save(index, library)
    assert store.is_stale(library)[0] is False
    new = library / "Newcomer"
    new.mkdir()
    (new / "description.txt").write_text("A brutalist portfolio.", encoding="utf-8")
    stale, reason = store.is_stale(library)
    assert stale and "Newcomer" in reason


# ------------------------------------------------------------------------ search

def test_paraphrased_query_finds_the_right_design(index):
    top = search.search("landing page for my neobank startup", index, k=1)[0]
    assert top["slug"] == "wealthcore"


def test_whole_site_query_outranks_a_component(index):
    # Both Skytrace (a dark SaaS page) and Glass Features (a dark SaaS component)
    # describe themselves in near-identical language. Asking for a "website" has
    # to break that tie toward the page.
    hits = search.search("a dark website for my saas product", index, k=4)
    assert hits[0]["slug"] == "skytrace"


def test_component_query_prefers_the_component(index):
    top = search.search("a frosted glass features section", index, k=1)[0]
    assert top["slug"] == "glass-features"


def test_filters_exclude_non_matching_facets(index):
    hits = search.search("landing page", index, k=5, filters={"industry": ["wellness"]})
    assert {h["slug"] for h in hits} == {"mindora"}


def test_component_still_wins_when_it_is_the_only_fit(index):
    # The scope factor is a tiebreaker, not a veto: if nothing else matches the
    # request, the component is genuinely the best answer available.
    top = search.search("frosted glass backdrop-filter card treatment", index, k=1)[0]
    assert top["slug"] == "glass-features"


def test_scores_are_comparable_across_signals(index):
    hits = search.search("private bank", index, k=3)
    assert all(0.0 <= h["score"] <= 1.0 for h in hits)


# ------------------------------------------------------------------------- brief

def test_brief_uses_authored_style_not_alphabetical(index):
    design = search.search("private bank website", index, k=1)[0]
    built = brief.build(design, "a site for my wealth firm")
    assert built["direction"]["style"] == "luxury"


def test_brief_industry_excludes_prose_noise(index):
    design = search.search("private bank website", index, k=1)[0]
    built = brief.build(design, "a site for my wealth firm")
    assert built["direction"]["industry"] == ["fintech"]


def test_light_palette_is_not_reported_as_dark(index):
    design = search.search("meditation app site", index, k=1)[0]
    built = brief.build(design, "calm wellness site")
    assert built["direction"]["mode"] == "light"


def test_brief_always_has_the_structural_sections(index):
    design = search.search("private bank website", index, k=1)[0]
    built = brief.build(design, "a site for my wealth firm")
    for required in ("nav", "hero", "footer"):
        assert required in built["sections"]


def test_image_prompts_carry_the_palette(index):
    design = search.search("private bank website", index, k=1)[0]
    built = brief.build(design, "a site for my wealth firm")
    assert any("#C8A96A" in p["prompt"] for p in built["image_prompts"])


# ---------------------------------------------------------------------- scaffold

def test_scaffold_produces_a_coherent_project(index, tmp_path):
    design = search.search("private bank website", index, k=1)[0]
    built = brief.build(design, "a site for my wealth firm", project="meridian")
    result = scaffold.generate(built, tmp_path / "out")

    out = tmp_path / "out"
    assert (out / "package.json").exists()
    assert '"standalone"' in (out / "next.config.mjs").read_text()

    css = (out / "app" / "globals.css").read_text()
    assert "{{" not in css, "every placeholder must be substituted"
    assert "#0A0A0B" in css

    page = (out / "app" / "page.tsx").read_text()
    for section in built["sections"]:
        component = scaffold._component_name(section)
        assert f"<{component} />" in page
        assert (out / "components" / "sections" / f"{component}.tsx").exists()

    assert (out / "DESIGN.md").exists()
    assert result["colours"]["ground"] == "#0A0A0B"


def test_dark_palette_maps_light_ink(index, tmp_path):
    design = search.search("private bank website", index, k=1)[0]
    built = brief.build(design, "wealth site", project="m")
    result = scaffold.generate(built, tmp_path / "dark")
    # Ink on a near-black ground has to be the light end of the palette.
    assert result["colours"]["ink"] == "#E8E6E1"


def test_scaffold_refuses_to_clobber(index, tmp_path):
    design = search.search("private bank website", index, k=1)[0]
    built = brief.build(design, "wealth site", project="m")
    (tmp_path / "taken").mkdir()
    (tmp_path / "taken" / "keep.txt").write_text("mine")
    with pytest.raises(FileExistsError):
        scaffold.generate(built, tmp_path / "taken")


def test_non_google_font_is_reported_not_imported(index, tmp_path):
    design = search.search("private bank website", index, k=1)[0]
    built = brief.build(design, "wealth site", project="m")
    built["tokens"]["fonts"] = ["Canela", "Inter"]
    result = scaffold.generate(built, tmp_path / "fonts")
    assert any("Canela" in note for note in result["font_notes"])
    layout = (tmp_path / "fonts" / "app" / "layout.tsx").read_text()
    assert "Canela" not in layout, "a licensed face must not become a next/font import"


# ------------------------------------------------------------------------ embed

def test_backend_falls_back_rather_than_failing(monkeypatch):
    monkeypatch.setenv("DESIGNICE_EMBED_BACKEND", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert embed.get_backend().name == "lexical"


def test_explicit_backend_can_refuse(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(embed.EmbedError):
        embed.get_backend("openai", allow_fallback=False)


def test_vectors_are_normalised(index):
    for design in index["designs"]:
        assert embed.cosine(design["vector"], design["vector"]) == pytest.approx(1.0, abs=1e-6)
