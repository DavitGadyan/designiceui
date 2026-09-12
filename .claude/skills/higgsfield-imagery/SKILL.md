---
name: higgsfield-imagery
description: >
  Generate website imagery with the Higgsfield API - hero shots, background textures,
  editorial section photography and OG cards - art-directed to match a design's palette
  and visual register. Use this skill when someone asks for images, photography, hero
  visuals, background art, textures or an OG image for a site being built, mentions
  Higgsfield, or has a scaffolded project whose image slots are still empty. Also use it
  when someone wants the image prompts themselves to paste into another tool. Works
  without API credentials by returning the art-directed prompts instead of failing.
---

# higgsfield-imagery

Generated imagery fails in a predictable way: it is technically fine and belongs to a
different website. A stock-looking photograph with the wrong colour temperature next to a
carefully tuned palette undoes the palette.

The fix is to derive the prompts from the design rather than from the subject alone.
Every prompt carries the reference design's palette and style register, so what comes
back belongs to the same world as the layout.

## Credentials

```bash
export HF_API_KEY_ID="..."
export HF_API_KEY_SECRET="..."
```

Create them at <https://cloud.higgsfield.ai/>. Server-side only - never commit them.

Without keys everything still works; the prompts come back with status `prompt-only` so
they can be pasted into any image tool. Check with `designice status`.

## Generating

From a prompt, matching a design automatically:

```bash
designice images "premium landing page for a private wealth firm" --project meridian
# lands in output/meridian/public/ - next to the scaffolded site
```

From a specific design, for a project already scaffolded:

```bash
designice images --design wealthcore-ledger --project meridian
```

Just the prompts, no API call:

```bash
designice images --design wealthcore-ledger --out ./tmp --dry-run
```

One slot at a time:

```bash
designice images --design wealthcore-ledger --out ./public --slot hero --slot og-card
```

## The slots

Every brief produces four, sized for where they land:

| Slot | Ratio | What it is for |
|---|---|---|
| `hero` | 16:9 | The main visual. Composed with negative space in the left third so a headline can sit over it. |
| `feature-texture` | 1:1 | Abstract macro texture for section backgrounds at low opacity. |
| `section-support` | 4:3 | Editorial photograph for a mid-page section. Documentary, not staged. |
| `og-card` | 16:9 | Share card background, centre kept quiet for a logo and title. |

## Models

- `soul` (default) - photographic, the right choice for hero and editorial work.
- `soul-hd` - same, higher resolution. Slower and costs more; use for a hero that will be
  displayed large.
- `flux-kontext` - better at graphic and illustrative work than photography.

```bash
designice images --design celestix-orbital --out ./public --model soul-hd
```

## Writing your own prompts

The generated ones are a strong default, but when you need something specific, keep the
structure that makes them work:

1. **Subject and context** - "Wide cinematic hero image for a fintech website"
2. **Art direction** - the design's style tags, verbatim
3. **Palette** - the actual hex codes from the brief
4. **Composition** - where the negative space goes, because that is what makes it usable
   as a hero rather than just a nice picture
5. **Exclusions** - "no text, no watermark, no UI chrome". Generated text is always wrong
   and always has to be removed.

Pass them directly through the MCP tool's `prompts` argument, or via `--slot` filtering
plus a hand-edited brief.

## After generating

- Images land in `--out` as `<slot>.png`. Put them in `public/` and reference with
  `next/image` so they are optimised and lazy-loaded.
- Always set explicit `width`/`height` or `aspect-ratio` - a hero that shifts on load
  undoes the impression it was generated to create.
- Check contrast if type sits over the image. If white text is not clearly readable, add
  a scrim (a 30-40% dark overlay) rather than regenerating.
- Higgsfield keeps outputs for at least seven days. `designice images` downloads
  immediately, so anything you want to keep is already local.

## Failure modes

- **`nsfw` status** - the safety filter fired, often on nothing obvious. Rephrase and
  retry; do not retry identically.
- **401** - credentials wrong or not exported into this shell.
- **Wrong mood entirely** - the palette is in the prompt but the model went its own way.
  Add one concrete lighting instruction ("overcast north light", "single hard rim light
  from the left"). Lighting moves the result more than any adjective.
- **Text in the image** - it will be wrong. Regenerate with the exclusion strengthened,
  or crop it out.

## In a build

The natural point is after scaffolding and before implementing the hero, so the real
image is present while the composition is being built:

```bash
designice scaffold "..." --out ./meridian --project meridian
designice images "..." --out ./meridian/public
# then implement the hero against the actual image
```
