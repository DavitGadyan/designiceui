---
description: Match a product to an existing UI template and rebuild it as Next.js or React Native with your brand
argument-hint: <company> <what it is> [website with Next.js React | mobile app React Native] [colours] [fonts]
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Skill, Agent
---

Invoke the `properui` skill and build: **$ARGUMENTS**

In short:

1. Parse the request: platform ("website with Next.js React" → web, "mobile app React
   Native" → mobile; neither → ask), company, primary/secondary colours, fonts.
2. `designice search "<request>" --require-media -k 5` - pick the template, tell the
   user which and why in one line.
3. `designice show <slug> --json`, then **Read every image in `media[]`.** Note the
   template's own tokens and its section order.
4. If the brief says the template has no authored tokens, write `meta.json` from what
   you saw and `designice index`.
5. `designice scaffold "<request>" --require-media --platform <web|mobile> --company
   ... --primary ... --secondary ... --font-display ... --font-body ... --sections
   <the order you read off the screenshots>` - it lands in `output/<company-slug>/`.
6. Fill `LAYOUT.md` from the screenshots, then implement each block: same components,
   same order, same proportions - only tokens change, and they always change.
7. Verify: build / typecheck, mobile width or Expo export, keyboard focus, reduced
   motion.
8. **Critique - the last stage.** Spawn the `design-critic` subagent (Agent tool,
   `subagent_type: "design-critic"`) with the project path, the platform, the template
   slug and the dev URL. It compares the finished build with the template screenshots
   for fine-grained UI/UX drift - structure, proportion, anatomy, states, responsive -
   and ignores colours and fonts, which changed on purpose. Apply every **Must fix**,
   apply the **Should fix** items unless one contradicts the brief, rebuild, and run
   the critic once more if you changed anything. Two rounds at most.
9. Report the template used, the token changes from DESIGN.md's "template → yours"
   table, and the critic's final verdict with anything you left unfixed and why.

Projects always go in `output/<project>/`. Do not ask where to put it; only pass
`--out` if the user named a path.
