---
description: Build a website by matching a design reference from the library
argument-hint: <what you want to build>  [--design <slug>]  [--out <dir>]
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Skill
---

Invoke the `createui` skill and build: **$ARGUMENTS**

Follow the skill's pipeline. In short:

1. `designice status` - confirm the library is indexed.
2. `designice search "<the request>" -k 5` - pick a reference, and tell the user which
   one you picked and why in one line before building.
3. `designice brief "<the request>" --project <name>` - read it fully.
4. `designice scaffold "<the request>" --project <name>` - it lands in `output/<name>/`.
5. Look at the images in `design-reference/`, read
   `.claude/skills/createui/references/implementation.md`, then implement each component
   in `components/sections/` top to bottom.
6. `npm run build` and check the mobile, keyboard and reduced-motion passes.

Projects always go in `output/<project>/`. Do not ask where to put it; only pass
`--out` if the user named a path.
