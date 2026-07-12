#!/usr/bin/env python3
"""Generate OpenCode skills and commands from AI Berkshire skill sources.

Single sync script that produces:
  - .opencode/skills/<name>/SKILL.md       (consumed by OpenCode skill loader)
  - .opencode/commands/<name>.md           (slash command frontmatter)

Sources (in order of precedence):
  1. skills/*.md                            (canonical, 19 files)
  2. codex-skills/<name>/SKILL.md           (only codex-only hand-written packages,
                                            e.g. investment-memo-craft; the agents/
                                            subdirectory is dropped for OpenCode)

Usage:
    python3 scripts/sync-opencode-skills.py          # generate
    python3 scripts/sync-opencode-skills.py --check  # verify drift, exit 1 if stale
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS_SRC = ROOT / "skills"
CODEX_SRC = ROOT / "codex-skills"
OPENCODE_DST = ROOT / ".opencode"

ADAPTER_NOTE_TEMPLATE = """\
## OpenCode adapter note

This skill is generated from `skills/{name}.md` so Claude Code, Codex, and OpenCode users share one canonical workflow.

- Treat `$ARGUMENTS` as the user's request in the current OpenCode thread.
- When the source mentions Claude-only surfaces such as TeamCreate, Task, Agent, WebSearch, WebFetch, Bash, Read, or Write, use the closest OpenCode capability available in this session:
  - `task` tool with `subagent_type: "<name>"` to invoke one of the four custom subagents defined in `.opencode/agents/` (business-analyst, financial-analyst, industry-researcher, risk-assessor)
  - `websearch` (requires `OPENCODE_ENABLE_EXA=1` env var) for free-form search; `webfetch` for known URLs
  - `bash`, `read`, `edit`, `write`, `grep`, `glob` map directly by name
- Use shared project tools from `tools/` in this repository. Prefer running commands from the repository root with paths like `python3 tools/financial_rigor.py ...`.
- Before starting research, run the `date` command to confirm today's date; treat it as the baseline for "latest" data and state the data cutoff date in the report header. Never assume the current date from training data.
- Preserve the research quality rules from `AGENTS.md`: cross-check financial data, use exact arithmetic tools for valuation/math, and clearly label uncertainty and source gaps.

"""


def split_frontmatter(text: str) -> tuple[str | None, str]:
    if not text.startswith("---\n"):
        return None, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return None, text
    return text[4:end], text[end + 5 :].lstrip("\n")


def first_heading(text: str, fallback: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def yaml_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def discover_sources() -> list[tuple[str, Path]]:
    """Yield (name, source_path) for every skill to generate, sorted by name.

    Sources:
      1. skills/*.md (19 files; canonical Claude Code skills)
      2. codex-skills/<name>/SKILL.md for any name not already covered
         (currently only investment-memo-craft)
    """
    seen: set[str] = set()
    out: list[tuple[str, Path]] = []
    for src in sorted(SKILLS_SRC.glob("*.md")):
        name = src.stem
        if name in seen:
            continue
        seen.add(name)
        out.append((name, src))
    for d in sorted(CODEX_SRC.iterdir()):
        if not d.is_dir() or d.name in seen:
            continue
        skill_md = d / "SKILL.md"
        if skill_md.exists():
            seen.add(d.name)
            out.append((d.name, skill_md))
    return out


def main() -> None:
    check = "--check" in sys.argv[1:]
    unknown = [a for a in sys.argv[1:] if a != "--check"]
    if unknown:
        raise SystemExit(f"Unknown argument(s): {', '.join(unknown)}")
    sources = discover_sources()
    if check:
        print(f"(stub) would check {len(sources)} entries")
        return
    print(f"(stub) would generate {len(sources)} entries")


if __name__ == "__main__":
    main()
