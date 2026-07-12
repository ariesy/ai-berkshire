#!/usr/bin/env bash
# Install AI Berkshire OpenCode skills and commands to user-level OpenCode config.
# Project-local .opencode/agents/ and opencode.example.json are read in-place
# by OpenCode; no per-user copy is needed for those.
#
# Override destination with OPENCODE_HOME=/custom/path bash scripts/install-opencode.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${OPENCODE_HOME:-$HOME/.config/opencode}"

if [ ! -d "$ROOT/.opencode/skills" ] || [ ! -d "$ROOT/.opencode/commands" ]; then
    echo "Running sync to regenerate artifacts..." >&2
    python3 "$ROOT/scripts/sync-opencode-skills.py"
fi

mkdir -p "$DEST/skills" "$DEST/commands"

for skill_dir in "$ROOT"/.opencode/skills/*; do
    [ -d "$skill_dir" ] || continue
    name="$(basename "$skill_dir")"
    rm -rf "$DEST/skills/$name"
    cp -R "$skill_dir" "$DEST/skills/$name"
done

for cmd_file in "$ROOT"/.opencode/commands/*.md; do
    [ -f "$cmd_file" ] || continue
    cp "$cmd_file" "$DEST/commands/"
done

echo "Installed OpenCode skills/commands to $DEST"
echo "Project-local .opencode/agents/ and opencode.example.json are read"
echo "directly from the repo root by OpenCode; no per-user copy needed."
echo ""
echo "To enable websearch in sub-agents, set OPENCODE_ENABLE_EXA=1 before"
echo "starting OpenCode."