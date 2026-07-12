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


def skill_frontmatter(name: str, description: str) -> str:
    return (
        "---\n"
        f"name: {name}\n"
        f"description: {yaml_quote(description)}\n"
        "---\n\n"
    )


def skill_content(name: str, source: Path) -> str:
    text = source.read_text(encoding="utf-8")
    front, body = split_frontmatter(text)
    description_source = front if front is not None else text
    description = first_heading(description_source, name)
    body_text = body if front is not None else text
    note = ADAPTER_NOTE_TEMPLATE.format(name=name)
    return skill_frontmatter(name, description) + note + body_text.lstrip("\n").rstrip() + "\n"


def write_skill(name: str, source: Path, *, check: bool) -> bool:
    content = skill_content(name, source)
    dst = OPENCODE_DST / "skills" / name / "SKILL.md"
    if check:
        if not dst.exists() or dst.read_text(encoding="utf-8") != content:
            print(f"  {dst.relative_to(ROOT)}")
            return True
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(content, encoding="utf-8")
    return False


def main() -> None:
    check = "--check" in sys.argv[1:]
    unknown = [a for a in sys.argv[1:] if a != "--check"]
    if unknown:
        raise SystemExit(f"Unknown argument(s): {', '.join(unknown)}")
    sources = discover_sources()
    if not check:
        (OPENCODE_DST / "skills").mkdir(parents=True, exist_ok=True)
    drifted: list[str] = []
    for name, source in sources:
        if write_skill(name, source, check=check):
            drifted.append(name)
    if check:
        if drifted:
            print(f"OpenCode skills are out of date ({len(drifted)} entries):")
            for n in drifted:
                print(f"  .opencode/skills/{n}/SKILL.md")
            raise SystemExit(1)
        print(f"Checked {len(sources)} OpenCode skills in .opencode/skills")
        return
    print(f"Generated {len(sources)} OpenCode skills in .opencode/skills")


if __name__ == "__main__":
    main()
