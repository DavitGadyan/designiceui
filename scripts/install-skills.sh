#!/usr/bin/env bash
# Install the designiceui skills into your Claude Code so /design, /createui,
# /design-search and /design-add work from any project.
#
# What it does, each step reversible with --uninstall:
#   1. symlinks bin/designice into ~/.local/bin        (the CLI the skills call)
#   2. copies .claude/skills/* into ~/.claude/skills   (the skills themselves)
#   3. copies .claude/commands/* into ~/.claude/commands
#   4. copies .claude/agents/* into ~/.claude/agents     (the design-critic subagent /design ends with)
#   5. registers the MCP server at user scope          (designice tools in every project)
#
# Nothing is pip-installed. The launchers self-locate this repo, so keep the
# clone where it is (or re-run this script after moving it).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SKILLS=(createui properui design-library higgsfield-imagery)
AGENTS=(design-critic)
BIN="$HOME/.local/bin"
CLAUDE="$HOME/.claude"

uninstall() {
  rm -f "$BIN/designice"
  for s in "${SKILLS[@]}"; do rm -rf "$CLAUDE/skills/$s"; done
  for c in "$ROOT"/.claude/commands/*.md; do rm -f "$CLAUDE/commands/$(basename "$c")"; done
  for a in "${AGENTS[@]}"; do rm -f "$CLAUDE/agents/$a.md"; done
  claude mcp remove designice --scope user >/dev/null 2>&1 || true
  echo "removed designiceui skills, commands, agents, CLI link and MCP server"
}

if [ "${1:-}" = "--uninstall" ]; then uninstall; exit 0; fi

# 1. CLI on PATH
mkdir -p "$BIN"
ln -sf "$ROOT/bin/designice" "$BIN/designice"
echo "cli        $BIN/designice -> $ROOT/bin/designice"
case ":$PATH:" in
  *":$BIN:"*) ;;
  *) echo "           ! $BIN is not on your PATH. Add to ~/.zshrc:  export PATH=\"\$HOME/.local/bin:\$PATH\"" ;;
esac

# 2. skills
mkdir -p "$CLAUDE/skills" "$CLAUDE/commands" "$CLAUDE/agents"
for s in "${SKILLS[@]}"; do
  rm -rf "$CLAUDE/skills/$s"
  cp -R "$ROOT/.claude/skills/$s" "$CLAUDE/skills/$s"
  echo "skill      ~/.claude/skills/$s"
done

# 3. commands
for c in "$ROOT"/.claude/commands/*.md; do
  cp "$c" "$CLAUDE/commands/"
  echo "command    /$(basename "$c" .md)"
done
echo "           note: /design replaces Claude Code's built-in Design canvas while installed"

# 4. agents
for a in "${AGENTS[@]}"; do
  cp "$ROOT/.claude/agents/$a.md" "$CLAUDE/agents/$a.md"
  echo "agent      $a  (the critique stage /design ends with)"
done
echo "           its screenshots need Playwright:  python3 -m pip install playwright && python3 -m playwright install chromium"

# 5. MCP server
if command -v claude >/dev/null 2>&1; then
  claude mcp remove designice --scope user >/dev/null 2>&1 || true
  claude mcp add designice --scope user -- python3 "$ROOT/bin/designice-mcp" >/dev/null
  echo "mcp        designice (user scope) -> $ROOT/bin/designice-mcp"
else
  echo "           ! 'claude' CLI not found; register the MCP server later with:"
  echo "             claude mcp add designice --scope user -- python3 $ROOT/bin/designice-mcp"
fi

# 6. make sure the library is indexed so the first search is instant
"$ROOT/bin/designice" index >/dev/null && echo "library    indexed $("$ROOT/bin/designice" status --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["designs_on_disk"])') designs"

cat <<MSG

Done. In any project, open Claude Code and try:

  /design Acme Ledger, invoicing for freelancers, website with Next.js React, primary #0F766E secondary #F59E0B
  /design Nova Health, telehealth for patients, mobile app React Native, navy #1E3A8A and coral #F97316
  /design-search luxury watch shop

Generated projects land in $ROOT/output/<company>/  (override with DESIGNICE_OUTPUT).
Uninstall:  $0 --uninstall
MSG
