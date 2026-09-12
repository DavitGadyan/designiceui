# output/

Every project the skills generate lands here, one folder per project:

```
output/
  acme-ledger/        <- /design Acme Ledger ... website with Next.js React
  nova-health/        <- /design Nova Health ... mobile app React Native
  meridian/           <- /createui ... --project meridian
```

The folder name is the project name (`--project`), else the company named in the
prompt, else the matched design's slug - slugified. Pass `--out` to put a project
somewhere else; nothing here is special beyond being the default.

Generated projects are **not committed** to this repo (see `.gitignore`) - they are
reproducible from the library plus the prompt, and each one is a complete Next.js or
Expo app that belongs in its own repository once you start working on it. Their build
artefacts (`node_modules/`, `.next/`, `.expo/`, `dist/`) are ignored inside each folder
either way.

To keep a project in git, either move it out and `git init` there, or remove the
`output/*` line from `.gitignore`.
