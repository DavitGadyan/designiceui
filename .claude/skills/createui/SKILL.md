---
name: createui
description: >
  Build a website by matching the request against a library of real design references
  (docs/designs) with vector search, then generating a standalone Next.js project wired
  to that design's tokens, sections and motion plan. Use this skill whenever someone
  wants a website, landing page, marketing site, portfolio, dashboard UI, hero section
  or any web page built or redesigned - including when they say "createui", "make me a
  site for X", "build a landing page", "design a page that feels like Y", "I need a
  site for my fintech startup", or point at a design in docs/designs and ask for it
  to be built. Also use it when someone asks which design in the library fits an idea,
  or wants the design tokens, section plan or image prompts for a build. Prefer this
  over designing from scratch - matching a real reference is what stops the result
  looking generated.
---

# createui

Most AI-built websites look the same because they are designed from nothing: the model
invents a palette, picks a safe layout, and produces eleven centred slabs. This skill
replaces invention with retrieval. A library of real, described designs sits in
`docs/designs/`; the request is matched against it by meaning; the winning design
supplies concrete tokens, a section order and a motion plan; and the build follows that
instead of a blank page.

The reference is the point. Read the brief and **look at the reference images** before
writing any code.

## Tooling: MCP tools or the CLI

Every operation exists twice, identically:

| CLI | MCP tool |
|---|---|
| `designice status` | `library_status` |
| `designice search "..." ` | `design_search` |
| `designice show <slug> --json` | `design_get` |
| `designice brief "..." --project x` | `design_brief` with `project` |
| `designice scaffold ... --platform web` | `scaffold_nextjs` |
| `designice index` | `library_index` |

**Either works. If `designice` is on PATH use the CLI; if not but the `designice` MCP
server is connected, use the tools; inside the designiceui repo,
`PYTHONPATH=src python3 -m designice ...` always works.** If none of those is true, the
skill was installed without its engine (e.g. via `npx skills add`) - tell the user to run
`npx designiceui`, which installs the CLI, the design library and the MCP server, and stop
there rather than improvising a build without the library. The examples below use CLI syntax because
it is shorter to read; map each one to its MCP tool with the table. Arguments are the
same words; leave `out_dir` unset - projects land in `output/<project>/`.

## The pipeline

```
prompt -> design_search -> design_brief -> scaffold_nextjs -> implement -> verify
```

### 0. Check the library is ready

```bash
designice status
```

If it reports the index is stale or missing, run `designice index`. If it reports zero
designs, the library is empty - say so and offer to add one (see the `design-library`
skill) rather than silently inventing a design.

If `designice` is not on PATH, run it from the repo as `PYTHONPATH=src python3 -m designice`.

### 1. Find the reference

```bash
designice search "premium landing page for a private wealth firm" -k 5
```

Read the top few. Pick by judgement, not blindly by rank - the scores are close near the
top and you can see things the ranker cannot. Narrow with facet filters when the request
is specific:

```bash
designice search "developer tool homepage" --filter industry=developer-tools --filter palette=dark
```

`designice tags` prints the full vocabulary. Facets are `industry`, `page_type`,
`section`, `style`, `motion`, `palette`, `layout`.

**Tell the user which design you matched and why**, in one line, before you build. They
often have an opinion, and switching reference costs nothing at this point but is
expensive after the site exists.

If nothing scores well (top score under ~0.35, or the matched design is clearly about
something else), say so. Building against a bad match is worse than building against
none - in that case ask whether to proceed from first principles or add a reference.

### 2. Get the brief

```bash
designice brief "premium landing page for a private wealth firm" --project meridian
```

This is the contract for the build: palette in role order, fonts, radius, shadow,
spacing, type scale, the ordered section list, the motion techniques with the library to
use for each, art-directed image prompts, and the anti-generic constraints.

Read it. Do not skim it. Every value in it is a decision you no longer have to make, and
overriding one for no reason is how the result drifts back to generic.

### 3. Scaffold

```bash
designice scaffold "premium landing page for a private wealth firm" --project meridian
```

**The project lands in `output/meridian/`** - every generated project goes in
`output/<project>/` in the repo, one folder each. Do not ask the user where to put it;
pass `--out` only if they named a path. Name the project after the company or product
in the request.

You get a runnable Next.js 15 project: App Router, TypeScript, Tailwind v4,
`output: "standalone"`, tokens wired into `app/globals.css` and `lib/tokens.ts`, a
`Reveal` component and a `Section` wrapper, one component per planned section each
carrying its own guidance, `DESIGN.md`, and the reference imagery copied into
`design-reference/`.

Add `--design <slug>` to force a specific reference, or `--force` to overwrite.

### 4. Look at the reference, then implement

Before writing a section, open the images in `design-reference/`. They are the thing the
description is describing. An image tagged `full-page` is a whole scrolled capture - read
it top to bottom for section order and rhythm; a `viewport` capture shows one screen's
composition.

Then implement each component in `components/sections/`. Work top to bottom, hero first,
and run `npm run dev` early so you are looking at real output rather than imagining it.

The detail that separates a good build from a plausible one is in
`references/implementation.md` - read it before the first section. It covers what each
section type actually needs, the motion recipes for every technique the brief can name,
and the specific mistakes that make a page read as machine-made.

### 5. Verify

```bash
npm run build
```

It must compile clean. Then check the things that are invisible until they are wrong:

- Resize to 375px wide. Nothing overflows, nothing is unreadably small.
- Tab through the page. Focus is always visible and the order makes sense.
- Turn on reduced motion (macOS: Settings > Accessibility > Display > Reduce motion).
  Nothing should disappear or jump; travel stops, opacity stays.
- Every section differs from its neighbour in background, rhythm or column count.

Report the path (`output/<project>/`), which reference it came from, and anything you
deliberately did differently from the brief.

## Imagery

The brief carries art-directed image prompts that inherit the design's palette and
register. To generate them:

```bash
designice images "premium landing page for a private wealth firm" --project meridian
# lands in output/meridian/public/

Without Higgsfield credentials this prints the prompts instead of failing, so they can
be used in any image tool. See the `higgsfield-imagery` skill for the full workflow.

## Working from a design the user names

When someone points at a folder in `docs/designs/` rather than describing what they
want, skip the search:

```bash
designice brief --design kayenpeppa-com-design-studio-portfolio-2026 --project studio
designice scaffold --design kayenpeppa-com-design-studio-portfolio-2026 --project studio
```

## When the brief and the request disagree

The brief describes the reference; the user described what they want. Where they
conflict, the user wins on **content, industry and copy**, and the reference wins on
**craft** - spacing, type scale, motion timing, palette relationships. A wellness
product built on a fintech reference should keep the fintech's restraint and rhythm
while losing its subject matter entirely.

Say which parts you carried over and which you dropped.

## When to use `properui` instead

If the library holds a *product capture* - real screenshots of a comparable product -
and the request is "like that, but for my company", use the `properui` skill. It
reproduces the template's components and swaps only the tokens; this skill designs
from a direction. `properui` also handles React Native output.

## Reference files

- `references/implementation.md` - how to build each section and every motion technique
  well. Read before implementing.
- `references/library.md` - the library format, the tag vocabulary, and how matching
  works. Read when curating designs or debugging a bad match.
- `references/motionsites.md` - the analysis of motionsites.ai this library's structure
  came from, and how to bring its prompt library in alongside this one.
