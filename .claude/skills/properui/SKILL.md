---
name: properui
description: >
  Build a React web app (Next.js) or React Native mobile app (Expo) by matching the
  request to the closest real product UI in docs/designs and reproducing that UI's
  components and layout as a template - always re-skinned with the new company's
  fonts and primary/secondary colours. Use this skill whenever someone says "/design",
  "make a website like X but for my company", "build me a mobile app for ...", "React
  Native app for our ...", "Next.js site for ...", "use our brand colours", "match this
  to one of our existing UIs", "re-skin", "same layout different brand", or describes a
  product and names colours or fonts they want. Use it even when the request does not
  say "template" - if there is a comparable product in the library, reproducing it
  beats designing from nothing. For art-direction-led builds with no screenshot
  template, use `createui` instead.
---

# properui

`createui` matches a *direction* and designs from it. This skill matches a *template*
and re-skins it. The library holds real product UIs - screenshots plus a description of
what the product does. The request is matched to the closest one, that UI's components
and layout are reproduced as faithfully as the screenshots allow, and the fonts and
colours are **always** swapped for the new company's. Only tokens change.

The images are the template. The description is for finding it. Never build from the
description alone when screenshots exist.

## What the prompt must tell you

- **Platform** - "website with Next.js React" → web; "mobile app React Native" → mobile.
  If the prompt names neither, ask. The two outputs are different enough that guessing
  wrong wastes the whole run.
- **Company / product** - what to write copy about.
- **Colours** - "primary #1E3A8A, secondary #F59E0B", "teal and amber", "our brand blue".
  Hex codes pass straight through. Named colours: pick a specific hex and say which.
- **Fonts** - "Space Grotesk headings", "use Inter".

Parse these yourself and pass them as explicit CLI flags. The CLI never guesses from
prose; you do the reading, it does the applying. If the prompt gives no colours, the
template's own are kept - and the brief flags every one of them as "yours = template's",
which you must surface to the user, because a re-skin that still carries the template's
brand colour is not finished.

## Tooling: MCP tools or the CLI

Every operation exists twice, identically:

| CLI | MCP tool |
|---|---|
| `designice status` | `library_status` |
| `designice search "..." --require-media` | `design_search` with `require_media: true` |
| `designice show <slug> --json` | `design_get` |
| `designice brief ... --primary ...` | `design_brief` with `overrides: {primary: ...}` |
| `designice scaffold ... --platform web` | `scaffold_nextjs` |
| `designice scaffold ... --platform mobile` | `scaffold_expo` |
| `designice index` | `library_index` |
| `designice snapshot <url> --out verify/critique` | CLI only - it drives a browser; used by the critic |

**Either works. If `designice` is on PATH use the CLI; if not but the `designice` MCP
server is connected, use the tools; inside the designiceui repo,
`PYTHONPATH=src python3 -m designice ...` always works.** If none of those is true, the
skill was installed without its engine (e.g. via `npx skills add`) - tell the user to run
`npx designiceui`, which installs the CLI, the design library and the MCP server, and stop
there rather than improvising a build without the library. The examples below use CLI syntax because
it is shorter to read; map each one to its MCP tool with the table. Arguments are the
same words: `--primary` is `overrides.primary`, `--sections a,b` is `overrides.sections:
["a","b"]`, `--out` is `out_dir` (leave it unset - projects land in `output/<project>/`).

## Pipeline

```
status → search --require-media → show → LOOK → (fix meta.json) → scaffold → LAYOUT.md → implement → verify → critique
```

### 1. Library ready?

```bash
designice status
```

Stale index → `designice index`. Zero designs with imagery → say so; this skill cannot
work without screenshots.

### 2. Match

```bash
designice search "<the prompt>" --require-media -k 5
```

`--require-media` is not optional here - it keeps the text-only art briefs out. Pick by
judgement from the top few, not by rank alone: a fintech dashboard and a fintech
marketing page can both score high and they are different templates. **Tell the user
which design you picked and why, in one line, before building.** Switching now is free;
switching after the build exists is not.

Top score under ~0.35, or a match that is clearly a different kind of product → say the
library has no good template for this and offer `createui` instead.

### 3. Look at the template

```bash
designice show <slug> --json
```

Then **open every path in `media[]` with the Read tool.** This is the step that makes
the result a reproduction rather than an invention. `shape` tells you what you are
looking at: `full-page` is a whole scrolled page (read top to bottom for section order),
`viewport` is one screen (read for composition), `wide-banner` is a hero or detail.
Mosaics of several pages are common - treat each tile as its own screen.

While looking, read the template's own tokens off the hero: ground, surface, ink,
accent, whether the nav is a bar or a sidebar, the corner radius, the card treatment,
the display and body faces (serif/sans, weight). You will write these into LAYOUT.md.

### 4. Fix the library while you are here

Most captures have no `meta.json`, so the brief starts from mode fallbacks and says so:
_"the template has no authored tokens"_. When you see that, write what you just read
off the image back:

```bash
designice annotate <slug>      # drafts meta.json from the description
```

then edit `meta.json`: `palette` in role order (ground, surface, accent, ink, muted),
`fonts` (display, body), correct `tags` with the primary style and industry first, a
real `use_case`. `designice index`. Thirty seconds now, and every future match against
this template starts from the truth instead of a guess.

### 5. Scaffold

Web:
```bash
designice scaffold "<prompt>" --require-media --platform web --company "<name>" \
  --primary "#..." --secondary "#..." --font-display "<face>" --font-body "<face>" \
  --sections nav,hero,logos,features,pricing,faq,cta,footer
```

Mobile:
```bash
designice scaffold "<prompt>" --require-media --platform mobile --company "<name>" \
  --primary "#..." --secondary "#..." --font-display "<face>" --font-body "<face>" \
  --sections hero,features,pricing,faq,cta
```

**The project lands in `output/<company-slug>/` automatically** - one folder per
project, in the repo. Do not ask the user where to put it; the convention is the answer.
Only pass `--out` if they named a path themselves. If `output/<slug>/` already exists,
add `--force` only when the user asked to regenerate; otherwise pick a distinct
`--project` name so nothing is silently overwritten.

`--sections` is the ordered block list **you read off the screenshots in step 3**. Do not
let the scaffold derive it from the description - descriptions of these captures are
business prose and the derived list is noise. Add `--design <slug>` to force the
template you chose.

You get: tokens wired (`app/globals.css` + `lib/tokens.ts`, or `lib/theme.ts`), a
`DESIGN.md` with a **"Tokens - template → yours"** table showing exactly what changed,
one component per section with its guidance, the screenshots copied into
`design-reference/`, and a `LAYOUT.md` pre-filled with one block per screenshot.

### 6. Fill LAYOUT.md

Before writing a component. One row per region, top to bottom, per screen: what the
component is, what it contains (counts, media, copy shape), how it is laid out, what
states it has. Fill the template-tokens table from what you read in step 3. For mobile,
fill the derivation table using `references/mobile-derivation.md`.

This is the contract. A component with no row in LAYOUT.md is an invention, and
inventions are how a re-skin drifts back into a generic page.

### 7. Implement

Each block from its row. The rule that matters: **same component shapes, same order,
same proportions - only tokens differ.** A three-card feature row stays a three-card
feature row. A split hero with a product mockup on the right stays split with a mockup
on the right. Use `var(--color-accent)` / `theme.colors.accent`, never a hex. Write
real copy for the new company; the body copy in mosaics is unreadable anyway.

Things that must always change even when the prompt says nothing about them: the
template's brand colour on CTAs, its logo, its product name in copy, its photography
subject. Things that must not change without being asked: layout, component types,
section order, spacing rhythm, type hierarchy.

Web: `npm run dev` early. Mobile: `npx expo start` early. Build blind and the spacing is
wrong in eight places at once.

### 8. Verify

Web: `npm run build` clean; 375px wide, nothing overflows; keyboard focus visible;
reduced motion holds. Mobile: `npx tsc --noEmit` clean; `npx expo export` succeeds;
44pt tap targets; safe areas respected.

Then put the result next to the reference. Same section order? Same component
shapes? Different colours and fonts? That three-line check is the builder's own
definition of done - and the reason the next stage exists is that the builder is the
worst-placed person to run it honestly.

### 9. Critique - the last stage

Hand the finished build to the `design-critic` subagent (`.claude/agents/
design-critic.md`). Spawn it with the Agent tool, `subagent_type: "design-critic"`,
and tell it: the project path, the platform, the template slug, and the URL the dev
server is on (or that it should start one). It reads every reference screenshot,
captures the build with `designice snapshot` (desktop and mobile, per-region images
plus a `manifest.json` of heights, paddings, column counts, heading sizes and element
counts), and returns `verify/CRITIQUE.md`: a region-fidelity table, then findings as
**Must fix / Should fix / Polish**, each citing a reference image, a build capture, a
number, and the concrete change.

What it judges is the fine grain that a section list does not catch: split ratios,
card anatomy, item counts, hero height, section rhythm, eyebrows and sub-headlines,
accordion default state, sticky nav, hover and focus states, placeholder boxes where
the reference had imagery, mobile stacking order, the template's brand name leaking
into copy. What it never judges is colours and fonts - those changed on purpose and
are listed under *Excluded by design* so you know they were seen, not missed.

Act on it: apply every Must fix; apply each Should fix unless it contradicts the
user's brief (say which and why); leave Polish for the report unless it is a one-line
change. Rebuild. If you changed anything, run the critic once more for a confirmation
pass - two rounds at most, then stop and report what remains. The critic is
read-only; do not ask it to edit.

### 10. Report

The path (`output/<slug>/`), which template, what was re-skinned (list the token
changes from DESIGN.md's table), what was derived (mobile), the critic's final
verdict with any findings you left unfixed and why, and anything you deliberately
kept from the template that the user may want to change.

## Mobile from a desktop reference

The library has no native mobile screenshots - every capture is a desktop page. A
React Native request therefore *derives* a phone layout from a desktop template. That
is a translation with rules, not an improvisation; read
`references/mobile-derivation.md` before filling the derivation table. The short
version: the nav becomes tabs, the footer becomes the More tab, every multi-column
region becomes a stack or a horizontal list, every hover becomes a press, and marquees,
parallax and cursor effects are dropped.

## Reference

- `references/mobile-derivation.md` - web region → phone treatment table, with the
  reasoning. Read before any mobile build.
- `../../agents/design-critic.md` - the post-build critic: what it compares, what it
  ignores, and the report format the builder acts on.
- `../createui/references/implementation.md` - section recipes and the anti-generic
  tells. The craft advice applies here too; only the "design it" framing does not.
- `../createui/references/library.md` - the library format and how matching works.
