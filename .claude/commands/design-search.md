---
description: Search the design library and explain the matches
argument-hint: <what you are looking for>  [--filter facet=tag]
allowed-tools: Bash, Read
---

Search the design reference library for: **$ARGUMENTS**

```bash
designice search "$ARGUMENTS" -k 5 --json
```

Report the top matches with, for each: the title, what it is for, its primary style and
industry, and one line on why it matched. Use the `signals` field to be specific -
whether it won on meaning (`dense`), exact words (`lexical`) or tags (`tag_overlap`).

If the top score is under about 0.35, say the library has no good answer for this rather
than presenting a weak match as a good one, and offer to add a design that would fill
the gap.
