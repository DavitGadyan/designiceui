# motionsites.ai - the analysis this library is modelled on

Reference: <https://motionsites.ai/>

## What it is

A curated library of premium design prompts for AI website builders - hero sections,
full landing pages, animated backgrounds and reusable blocks. Its positioning is worth
quoting because it is the same problem this repo addresses: *"Keep the web free of AI
slop. Connect your AI agents to 500+ Premium Website Design Prompts."*

The product is not a generator. It is a **retrieval layer in front of a generator** - the
insight being that the model was never the bottleneck; the absence of a specific,
art-directed starting point was.

## How it is put together

**Catalogue.** Every entry is a named design (Celestix, Wealthcore, Cyber Ronin, Heritage
Grove) with a preview image and one category label. Naming each design rather than
numbering it is not decoration - it gives people and agents a handle to refer back to.

**Imagery.** Previews are generated with Higgsfield and served through `images.higgs.ai`
with width and quality parameters. Animated entries are WebP or GIF, because a still
frame cannot show motion and motion is what they are selling.

**Taxonomy.** Two axes, which is exactly the split this library uses:
- *Industry / use case*: SaaS, Agency, AI, Portfolio, Technology, Travel, Wellness,
  Fintech, Creative, Ecommerce, Fashion, Space, Healthcare, Developer, Social,
  Environmental, Food.
- *Section type*: Hero, Features, Footer, Pricing, CTA, Testimonial, Marquee, Sign In,
  404, Component, Info, Carousel.

**Distribution via MCP.** Their newest surface is an MCP server, registered with a single
command and authorised in the browser:

```
claude mcp add motionsites --scope user --transport http \
  https://xgdzyqfalbibzelpdpvr.supabase.co/functions/v1/mcp
```

Free accounts open three prompts; paid plans unlock the full library. Shipping the
library as MCP rather than as copy-paste is the significant move - it puts the reference
inside the agent's tool loop instead of relying on a human to fetch it.

**Academy.** Lessons teaching the workflow. The 3D one is worth reading in full; its
practical notes ended up in `implementation.md`, in particular that AI-generated
Three.js scenes render dark and muddy without tone mapping, and that GLB textures should
be exported at 1K-2K for the web.

## What this repo took from it

| Their move | Here |
|---|---|
| Named designs with previews | `docs/designs/<name>/` with images + `description.txt` |
| Two-axis taxonomy | Seven facets, `industry` and `section` among them |
| Prompt as the unit of value | `description.txt` plus a derived build brief |
| MCP distribution | `designice mcp`, nine tools, stdlib-only so install is one command |
| Higgsfield imagery | `designice images`, same API, key-optional |
| Category browsing | `designice list --filter`, `designice tags` |

## Where this repo differs deliberately

**Retrieval instead of browsing.** MotionSites is a catalogue a human picks from.
Here the prompt is matched by meaning, so `createui` can go from a sentence to a chosen
reference without a human in the loop - while still reporting which design it picked and
why, so the human can override.

**Briefs, not prompts.** A prompt is text handed to a model. A brief is resolved
decisions: palette in role order, type scale, section order, a motion plan naming the
library for each technique, and the anti-generic constraints. It is more constrained on
purpose, because the failure mode being designed against is drift back to generic.

**A build target, not just a description.** `designice scaffold` emits a runnable
standalone Next.js project with the tokens already wired. The reference stops being
advice and becomes the configuration.

**Local and private.** The library is folders in a repo. It works offline, it diffs in
git, and nothing is sent anywhere unless an API embedding backend or Higgsfield is
explicitly configured.

## Using both together

They compose well - MotionSites is a catalogue of hundreds of art-directed prompts, this
is a pipeline that turns a reference into a project. Register their MCP alongside
`designice`, then:

1. `design_search` here first, since the local library holds your own work and anything
   you have curated.
2. If nothing local fits, pull a prompt from the MotionSites MCP.
3. Save what you used into `docs/designs/<name>/` with a `description.txt` capturing the
   direction in your own words, plus `reference_url`. Run `designice index`.
4. It is now matchable locally, and the next similar request finds it without a round
   trip.

Their imagery is theirs - record `reference_url` rather than copying preview files into
this repo. The seeded designs here follow that rule: the descriptions are original
analysis, and no MotionSites imagery is redistributed.
