---
description: Add a design to the reference library and index it
argument-hint: <folder name or path>  |  <url>
allowed-tools: Bash, Read, Write, Edit, Glob
---

Invoke the `design-library` skill and add: **$ARGUMENTS**

If given a folder that already has images, look at them and write `description.txt`
yourself - what it is for, real hex codes and fonts, how it moves, and the one detail
that carries the design plus the trap in reproducing it.

If given a URL, capture screenshots first (Playwright MCP if available, otherwise ask
the user for them), then describe what you see and set `reference_url` in `meta.json`.

Then:

```bash
designice annotate "<folder>"    # writes meta.json from the description
# correct it: primary style and industry first, drop wrong tags, order palette by role
designice index
designice search "<the query this design should serve>"
```

Confirm it comes back in the top results. If it does not, the description is too vague -
fix the text, not the tags.
