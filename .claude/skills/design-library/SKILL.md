---
name: design-library
description: >
  Curate the design reference library in docs/designs - add a new design from screenshots
  or a URL, write the description that makes it findable, tag it, generate meta.json, and
  rebuild the vector index. Use this skill whenever someone drops images into a folder
  under docs/designs, says "add this design", "I saved a screenshot of a site I like",
  "tag this design", "reindex the library", "why didn't my design show up in search", or
  wants to capture a site's look for later reuse. Also use it when a createui match came
  back wrong and the library needs correcting, or when someone asks what designs are
  available. The quality of every generated site depends on this library, so treat
  writing a description as the real work, not the paperwork.
---

# design-library

The library is the whole system. `createui` can only be as good as what it retrieves, so
a vague description is not a small problem - it is a design that will never be found, or
worse, one that gets found for the wrong request.

## Adding a design

### 1. Make the folder

```bash
designice new "Aurora Fintech"      # or just create the folder yourself
```

Folder name is the display name. Spaces, dots and em dashes are fine; a stable slug is
derived from it. Drop the images in - PNG, JPG, WebP, GIF, MP4, and files with no
extension at all, which is how browser screenshots usually arrive.

### 2. Write description.txt

This is the work. It gets embedded, and it is what determines whether the design is ever
retrieved. Write it as if to a colleague who cannot see the screenshot.

Look at the images first. Then cover, roughly in this order:

- **What it is for.** One line. "Website for a private bank." This becomes the use case.
- **What it looks like.** Real hex codes. Real font names. Real spacing values. "Deep
  navy #05070F with a single electric blue #4C7DFF used only for the horizon glow and
  the primary button" is findable and buildable; "modern dark theme" is neither.
- **How it moves.** Name the technique - "pinned sections, scrubbed to scroll" rather
  than "smooth animations".
- **Why it works, and the trap.** The one detail that carries the design, and the
  mistake someone would make reproducing it. This is the highest-value sentence in the
  file and almost nobody writes it.

Length: 200-400 words is the sweet spot. Under 100 and there is not enough to embed;
over 600 and the signal dilutes.

A useful test: could someone rebuild the design from your description without the image?
If not, it is too vague to retrieve reliably either.

### 3. Tag it

```bash
designice annotate "Aurora Fintech"
```

This writes `meta.json` pre-filled with everything the description already implies. Then
**correct it**, because auto-detection is deliberately loose:

- Put the **primary** style and industry **first** in each list. Order is meaning - the
  build brief follows it, so `["luxury", "minimal"]` and `["minimal", "luxury"]` produce
  different sites.
- Delete wrong tags. A description that closes with "use for fintech, legal and music"
  will have picked up all three; that is good for search recall and wrong for a brief.
- Order `palette` by role: ground, surface, then accents and text. The scaffold maps them
  onto semantic roles in that order.
- Fill in `use_case` as a real sentence starting "Website for ...".
- Add `reference_url` if it came from somewhere. Record the URL rather than copying
  someone else's imagery into the repo.

`designice tags` prints the full vocabulary. Facets are `industry`, `page_type`,
`section`, `style`, `motion`, `palette`, `layout`.

### 4. Confirm it is found

```bash
designice search "site for a wealth manager"    # confirm it comes back
```

No reindex needed - the index refreshes itself when the library changes. (`designice
index` still exists to force a rebuild or switch embedding backends.) Always search for
it afterwards. A design that does not surface for the query it was
added to serve has a description problem, and the fix is in the text, not the tags.

## Capturing a design from a live URL

When someone gives a URL rather than screenshots:

1. Take screenshots - full page and the hero at viewport size. Use the Playwright MCP if
   it is available, or ask the user for captures.
2. Save them into the folder.
3. Write `description.txt` from what you see, following the section above. Describe the
   design, do not copy the site's marketing copy.
4. Set `reference_url` in `meta.json` so provenance is recorded.

Describing someone's public design for your own reference library is ordinary practice.
Copying their assets into your repo is not - link instead.

## Fixing a bad match

When `createui` retrieves the wrong design:

```bash
designice search "<the query that went wrong>" -k 5 --json
```

The `signals` field on each hit shows why. Read it before changing anything:

- **High `lexical`, low `dense`** - matched on a shared word rather than meaning. Usually
  a stray sentence in the description; often the "use for X, Y, Z" closing line.
- **High `tag_overlap`, nothing else** - tags are carrying a design the prose does not
  support. Either the description is too thin, or the tags are aspirational.
- **Everything low, and it still won** - the library has no good answer for that query.
  That is a gap to fill, not a bug to fix.
- **A component beat a full page** (or vice versa) - check `page_type`. Scope is handled
  by a separate factor and it needs the tag to be right.

Fix the description first, tags second. Tags nudge; the description decides.

## Health checks

```bash
designice status                  # library path, count, index freshness, backends
designice list                    # everything, with primary industry and style
designice list --filter industry=fintech
designice show <slug>             # full record including media dimensions
```

Signs the library needs attention:

- Two designs that always return together for different queries - their descriptions are
  not distinct enough.
- A design that never appears in any search - too vague, or duplicated by a stronger one.
- Everything scoring under 0.4 for real requests - the library is too small. Twelve
  designs is a working minimum; the useful range starts around thirty.

## Backends

Matching runs on `voyage` or `openai` when a key is set, and falls back to a
zero-dependency lexical backend otherwise. The fallback is decent but literal-minded; if
matching feels like keyword search, set `OPENAI_API_KEY` or `VOYAGE_API_KEY` and run
`designice index --backend openai`. Switching backend requires a reindex.

See `createui/references/library.md` for the format reference and how scoring works.
