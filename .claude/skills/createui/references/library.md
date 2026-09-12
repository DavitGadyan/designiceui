# The design library and how matching works

## Folder format

```
docs/designs/
  <anything you want to call it>/
    hero.png              any images or video; extensions optional
    pricing.webp
    description.txt       plain English - the important part
    meta.json             optional, but it is what makes briefs accurate
```

The folder name is the display name. A stable slug is derived from it, so
`Kayenpeppa.com — Design Studio Portfolio 2026` is addressable as
`kayenpeppa-com-design-studio-portfolio-2026`. Spaces, dots and em dashes are fine.

Images are found by magic bytes as well as extension, because screenshots dragged out of
a browser frequently arrive as `image_original` with no suffix.

### description.txt

This is what gets embedded, so it is what determines whether the design is ever found.
Write it as if to a colleague who cannot see it. Specifics are everything:

- What is it for. One line: "Website for a private bank."
- What it looks like. Real hex codes, real font names, real spacing values.
- How it moves. Name the technique, not just "animated".
- Why it works, and the trap to avoid.

A description that says "modern clean design with nice animations" matches every query
equally, which means it matches none of them usefully.

### meta.json

Optional, and worth writing for anything you will build from more than once. Auto-tagging
drives recall well but should not drive a build brief - a description that closes with
"use for fintech, legal and music" should help the design be *found* by all three without
convincing the brief that a bank site is a music site. Authored tags are the ones the
brief trusts.

```json
{
  "title": "Wealthcore",
  "use_case": "Website for a private banking or wealth management product",
  "tags": {
    "industry": ["fintech"],
    "page_type": ["landing-page"],
    "style": ["luxury", "minimal"],
    "motion": ["reveal-on-scroll", "hover-tilt"],
    "palette": ["dark"],
    "layout": ["split-screen", "bento-grid"],
    "section": ["hero", "logos", "features", "stats", "pricing", "cta", "footer"]
  },
  "palette": ["#0A0A0B", "#141416", "#C8A96A", "#E8E6E1", "#8A8A93"],
  "fonts": ["Canela", "Inter"],
  "reference_url": "https://..."
}
```

**Order matters.** The first style is the primary style; the first industry is the
primary industry. The brief follows authored order, so `["luxury", "minimal"]` and
`["minimal", "luxury"]` produce different sites.

**Palette order matters too**: ground, surface, then accents and text. The scaffold maps
them onto semantic roles in that order, then sanity-checks ink against the ground's
luminance.

Generate a starting point from what the description already implies, then correct it:

```bash
designice annotate <slug>
```

## The tag vocabulary

Seven facets. `designice tags` prints them all.

| Facet | What it answers |
|---|---|
| `industry` | Which field is this for - fintech, ai, wellness, agency, ... |
| `page_type` | What shape - landing-page, dashboard, docs, component, ... |
| `section` | Which blocks it demonstrates - hero, pricing, bento, footer, ... |
| `style` | The visual register - luxury, brutalist, glassmorphic, ... |
| `motion` | How it moves - scroll-driven, 3d-webgl, marquee, ... |
| `palette` | dark, light, pastel, neon, earth-tone, ... |
| `layout` | bento-grid, split-screen, asymmetric, magazine, ... |

Filters require a match in **every facet named**, and **any tag within** a facet:

```bash
designice search "developer homepage" --filter industry=developer-tools --filter palette=dark
```

## How matching works

Three signals, each min-max normalised across candidates before fusion so the weights
mean the same thing regardless of embedding backend:

- **dense (0.60)** - cosine against the stored embedding. Handles meaning: "a site for my
  neobank" finding a design described as "private banking".
- **lexical (0.25)** - BM25 over the description. Handles the exact words an encoder
  blurs away: a brand name, "terracotta", "Three.js".
- **tags (0.15)** - how much of the query's implied tag set the design covers. Handles
  "which field is this for" directly.

Then a **scope factor**: a query asking for a whole site is penalised against designs
tagged as a single component, and vice versa. A features section and a marketing site can
describe themselves in near-identical language, so scope needs its own answer.

Both sides are expanded through a synonym map before embedding, which is why "website for
a bank" lands near designs tagged `fintech` even when neither text shares a word.

## Embedding backends

Resolution order, unless `DESIGNICE_EMBED_BACKEND` forces one:

1. `voyage` if `VOYAGE_API_KEY` is set
2. `openai` if `OPENAI_API_KEY` is set
3. `lexical` - pure stdlib TF-IDF, no key, no network, no install

The lexical floor exists so the library always answers. It is genuinely decent for a few
hundred designs, but the API backends understand paraphrase far better - set a key if
matching feels literal-minded.

Switching backends requires a reindex: `designice index --backend voyage`.

## Keeping the index fresh

`designice status` reports staleness by checksumming each folder. Anything that changes
a description, adds an image or edits `meta.json` makes the index stale. Rebuild with
`designice index`. The index is a single JSON file at `docs/designs/.designice/index.json`
and is gitignored - it is derived data, rebuild it rather than committing it.
