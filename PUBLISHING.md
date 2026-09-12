# Publishing and running the skills

Four skills live in `.claude/skills/`: `createui`, `properui` (the `/design` command),
`design-library`, `higgsfield-imagery`. They all drive one Python package, `designice`,
which has **no required dependencies** - Python 3.10+ is the whole install.

Four ways to run them, from the one to give other people down to the manual pieces.

---

## 0. Install the skills (recommended)

```bash
npx designiceui            # after `npm publish`
npx github:DavitGadyan/designiceui   # works as soon as the repo is pushed, no npm needed
```

`bin/designiceui.js` is a one-file bootstrapper: it clones the repo into `~/.designiceui`
(`DESIGNICEUI_HOME` to change; `DESIGNICEUI_REPO` to clone from somewhere else, a local
path works), or `git pull`s it if it is already there, then runs
`scripts/install-skills.sh` from that clone. The npm package carries only that file
(`"files"` in `package.json`), so publishing is instant and the engine always comes from git.

From a clone instead - for developing, or to keep your own designs in it:

```bash
git clone https://github.com/DavitGadyan/designiceui.git
cd designiceui
./scripts/install-skills.sh
```

The script is the whole install, and every step is reversible with `--uninstall`:

| Step | What | Where |
|---|---|---|
| CLI | symlink to `bin/designice` (self-locating launcher, no pip) | `~/.local/bin/designice` |
| Skills | `createui`, `properui`, `design-library`, `higgsfield-imagery` | `~/.claude/skills/` |
| Commands | `/design`, `/createui`, `/design-search`, `/design-add` | `~/.claude/commands/` |
| Agents | `design-critic` (the critique stage `/design` ends with) | `~/.claude/agents/` |
| MCP | `designice` server, user scope | `claude mcp add designice --scope user ...` |
| Index | builds the vector index once | `docs/designs/.designice/` |

The skills call the `designice` CLI, which finds the library and output folders relative
to the clone. So **keep the clone where it is**; if you move it, run the script again.
`/design` replaces Claude Code's built-in Design canvas while installed.

Inside the clone itself you will see an MCP "defined in multiple scopes" notice, because
`.mcp.json` also registers the server project-scoped for people who run without
installing. Both point at the same server; ignore it or `claude mcp remove designice -s project`.

---

## 1. Run in this repo (no setup)

Everything is project-scoped, so it works the moment you open the folder:

```bash
cd /path/to/designiceui
claude
```

Then, inside Claude Code:

```
/design Acme Ledger, invoicing for freelancers, website with Next.js React, primary #0F766E secondary #F59E0B
/design Nova Health, telehealth for patients, mobile app React Native, navy #1E3A8A and coral #F97316
/createui a dark scroll-driven landing page for a space startup
/design-search luxury watch shop
/design-add "My New Design"
```

Claude Code will ask once to approve the `designice` MCP server from `.mcp.json`. Say yes.
Generated projects land in `output/<company>/`.

Sanity check before the first run:

```bash
PYTHONPATH=src python3.12 -m pytest tests -q     # 55 passed
PYTHONPATH=src python3.12 -m designice status    # designs indexed, index current
```

---

## 2. Publish the repo so others can use it

Nothing about the skills is machine-specific. Commit and push; a clone works as in
section 1, and `scripts/install-skills.sh` in section 0 works from any clone.

```bash
git add -A
git commit -m "designiceui: design library, createui + properui skills, MCP server"
git remote add origin git@github.com:<you>/designiceui.git
git push -u origin main
```

Then, to make `npx designiceui` work (one time, then again for each version bump):

```bash
npm login
npm publish            # publishes the one-file bootstrapper; bump "version" in package.json first
```

If the name `designiceui` is taken on npm, rename in `package.json` and the README - the
`github:` form needs no npm at all. The community skills CLI also finds the skills
directly from GitHub (`npx skills add <you>/designiceui -g`), but that installs only the
`SKILL.md` files; users still need `npx designiceui` for the CLI, library and MCP server.

What travels with the repo:

| Path | Purpose |
|---|---|
| `package.json` + `bin/designiceui.js` | the `npx designiceui` bootstrapper |
| `scripts/install-skills.sh` | the installer (and `--uninstall`) |
| `bin/designice`, `bin/designice-mcp` | self-locating launchers for the CLI and MCP server |
| `.claude/skills/` | the four skills |
| `.claude/commands/` | `/design`, `/createui`, `/design-add`, `/design-search` |
| `.mcp.json` + `bin/designice-mcp` | the MCP server, self-locating, no install |
| `src/designice/` | the Python package |
| `docs/designs/` | the design library (descriptions + `meta.json`; screenshots too) |
| `evals/` | the eval definitions for both build skills |

What does not: `output/` (generated projects), `docs/designs/.designice/` (the index -
rebuilt on first use), `.claude/skills/*-workspace/` outputs (eval runs).

A collaborator who clones it needs nothing but Python 3.10+ and Node 18+ (Node 20.19+
for Expo). No pip install. `designice index` runs automatically on first search.

**On screenshots:** `docs/designs/` includes real product captures. Make sure you have the
right to publish them before pushing to a public remote; otherwise keep the repo private
or strip the images and leave the `meta.json` + descriptions, which are what the index
actually uses.

---

## 3. Install by hand (what the script does, step by step)

Use this if you want to place things yourself. Two parts: the skills need to be in
`~/.claude/skills/`, and the `designice` CLI needs to be on PATH and know where the
library is.

### 3a. Put `designice` on PATH

```bash
ln -sf /path/to/designiceui/bin/designice ~/.local/bin/designice   # no pip needed
# or, if you prefer a real install:  python3.12 -m pip install -e .
designice status                        # confirms it runs from anywhere
```

### 3b. Tell it where the library and output live

The CLI finds `docs/designs/` and `output/` relative to the repo when run from inside
it. From another project it needs to be told:

```bash
# ~/.zshrc (or wherever your shell config is)
export DESIGNICE_LIBRARY="/path/to/designiceui/docs/designs"
export DESIGNICE_OUTPUT="/path/to/designiceui/output"     # or wherever you want projects
```

### 3c. Install the skills and commands

Either copy the folders:

```bash
cp -r /path/to/designiceui/.claude/skills/{createui,properui,design-library,higgsfield-imagery} ~/.claude/skills/
cp /path/to/designiceui/.claude/commands/*.md ~/.claude/commands/
```

or install from the packaged `.skill` files (section 4).

### 3d. Register the MCP server globally

```bash
claude mcp add designice --scope user -- python3 /path/to/designiceui/bin/designice-mcp
```

The launcher self-locates its `src/`, so no `PYTHONPATH` is needed. Check with
`claude mcp list`.

Now `/design ...` works in any folder, and projects land in `$DESIGNICE_OUTPUT/<company>/`.

---

## 4. Distribute as `.skill` files

For handing a skill to someone without the whole repo:

```bash
./scripts/package-skills.sh
```

This validates each skill with skill-creator's checker and writes:

```
release/skills/createui.skill
release/skills/properui.skill
release/skills/design-library.skill
release/skills/higgsfield-imagery.skill
```

A `.skill` file is a zip of the skill folder. To install one:

```bash
unzip properui.skill -d ~/.claude/skills/          # personal - every project
unzip properui.skill -d .claude/skills/            # project - this repo only
```

The recipient still needs the `designice` CLI (section 3a) and a library
(`DESIGNICE_LIBRARY`), because the skills call the CLI. The `.skill` file carries the
instructions, not the engine.

---

## Optional: API keys

None are required. Set these to upgrade:

```bash
export OPENAI_API_KEY=...      # or VOYAGE_API_KEY - better semantic matching
designice index --backend openai

export HF_API_KEY_ID=...       # Higgsfield image generation
export HF_API_KEY_SECRET=...   # (without them, `designice images` returns the prompts)
```

`.env.example` lists them all.

---

## Checking it worked

```bash
designice status                                   # library found, index current
designice search "luxury watch shop" --require-media -k 3
claude mcp list                                    # designice listed (if registered)
```

Then in Claude Code, `/design` with any of the prompts in section 1. A correct run names
the matched template in one line before building, opens the screenshots, and lands the
project in `output/<company>/`.

## Re-running the evals

The skills were built with the skill-creator process. To re-run its benchmark after a
change:

```
/skill-creator:skill-creator run the eval loop for properui
```

Eval definitions are in `evals/<skill>/evals.json`; runs land in
`.claude/skills/<skill>-workspace/iteration-N/`.
