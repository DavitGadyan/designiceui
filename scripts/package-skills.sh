#!/usr/bin/env bash
# Package every skill in .claude/skills into a distributable .skill file.
#
# A .skill file is a zip of the skill folder that Claude Code can install into
# ~/.claude/skills (personal) or <project>/.claude/skills (project). This uses
# the official skill-creator packager so the format stays in step with Claude Code.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/release/skills"
PY="${PYTHON:-python3.12}"

# Find the skill-creator plugin wherever Claude Code cached it.
SC="$(ls -d "$HOME"/.claude/plugins/cache/claude-plugins-official/skill-creator/*/skills/skill-creator 2>/dev/null | tail -1 || true)"
if [ -z "$SC" ]; then
  echo "skill-creator plugin not found. In Claude Code run: /plugin install skill-creator@claude-plugins-official" >&2
  exit 1
fi

mkdir -p "$OUT"
for skill in "$ROOT"/.claude/skills/*/; do
  name="$(basename "$skill")"
  case "$name" in *-workspace) continue ;; esac     # eval scratch, not a skill
  (cd "$SC" && "$PY" -m scripts.quick_validate "$skill" >/dev/null) || { echo "!! $name failed validation" >&2; exit 1; }
  (cd "$SC" && "$PY" -m scripts.package_skill "$skill" "$OUT" >/dev/null)
  echo "packaged  $OUT/$name.skill"
done
