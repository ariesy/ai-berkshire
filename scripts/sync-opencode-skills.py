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


def _extract_description_and_body(source: Path, name: str) -> tuple[str, str]:
    text = source.read_text(encoding="utf-8")
    front, body = split_frontmatter(text)
    description_source = front if front is not None else text
    description = first_heading(description_source, name)
    body_text = body if front is not None else text
    return description, body_text


def skill_content(name: str, source: Path) -> str:
    description, body_text = _extract_description_and_body(source, name)
    note = ADAPTER_NOTE_TEMPLATE.format(name=name)
    return skill_frontmatter(name, description) + note + body_text.lstrip("\n").rstrip() + "\n"


# Note on codex-only hand-written packages (e.g. investment-memo-craft):
# discover_sources() points at codex-skills/investment-memo-craft/SKILL.md
# but write_skill() only writes a single SKILL.md into .opencode/skills/<name>/.
# The agents/openai.yaml sidecar (Codex agent picker metadata) is therefore
# never copied to OpenCode, which is the intended behavior per spec D5.


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


COMMAND_AGENT_OVERRIDES: dict[str, str] = {
    # investment-team and earnings-team orchestrate other agents, so they
    # must run as the primary build agent rather than a subagent.
}


def command_frontmatter(name: str, description: str, agent: str) -> str:
    return (
        "---\n"
        f"description: {yaml_quote(description)}\n"
        f"agent: {agent}\n"
        "---\n\n"
    )


def command_content(name: str, source: Path) -> str:
    description, body_text = _extract_description_and_body(source, name)
    agent = COMMAND_AGENT_OVERRIDES.get(name, "build")
    note = ADAPTER_NOTE_TEMPLATE.format(name=name)
    return (
        command_frontmatter(name, description, agent)
        + note
        + body_text.lstrip("\n").rstrip()
        + "\n"
    )


def write_command(name: str, source: Path, *, check: bool) -> bool:
    content = command_content(name, source)
    dst = OPENCODE_DST / "commands" / f"{name}.md"
    if check:
        if not dst.exists() or dst.read_text(encoding="utf-8") != content:
            print(f"  {dst.relative_to(ROOT)}")
            return True
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(content, encoding="utf-8")
    return False


def cleanup_stale(sources: list[tuple[str, Path]]) -> list[str]:
    """Remove .opencode/skills/<name>/ and .opencode/commands/<name>.md
    for any name not in `sources`. Returns list of removed paths."""
    valid = {name for name, _ in sources}
    removed: list[str] = []

    skills_dir = OPENCODE_DST / "skills"
    if skills_dir.exists():
        for entry in sorted(skills_dir.iterdir()):
            if entry.is_dir() and entry.name not in valid:
                import shutil
                shutil.rmtree(entry)
                removed.append(str(entry.relative_to(ROOT)))

    commands_dir = OPENCODE_DST / "commands"
    if commands_dir.exists():
        for entry in sorted(commands_dir.iterdir()):
            if entry.is_file() and entry.suffix == ".md" and entry.stem not in valid:
                entry.unlink()
                removed.append(str(entry.relative_to(ROOT)))

    return removed


def main() -> None:
    check = "--check" in sys.argv[1:]
    unknown = [a for a in sys.argv[1:] if a != "--check"]
    if unknown:
        raise SystemExit(f"Unknown argument(s): {', '.join(unknown)}")
    sources = discover_sources()
    if not check:
        (OPENCODE_DST / "skills").mkdir(parents=True, exist_ok=True)
        (OPENCODE_DST / "commands").mkdir(parents=True, exist_ok=True)
    drifted: list[str] = []
    for name, source in sources:
        if write_skill(name, source, check=check):
            drifted.append(name)
        if write_command(name, source, check=check):
            drifted.append(name)
    if not check:
        removed = cleanup_stale(sources)
        if removed:
            print(f"Removed {len(removed)} stale entries:")
            for path in removed:
                print(f"  {path}")
    if check:
        if drifted:
            print(f"OpenCode artifacts are out of date ({len(drifted)} entries):")
            for n in drifted:
                print(f"  .opencode/skills/{n}/SKILL.md")
                print(f"  .opencode/commands/{n}.md")
            raise SystemExit(1)
        print(
            f"Checked {len(sources)} OpenCode entries "
            f"({len(sources)} skills, {len(sources)} commands)"
        )
        return
    print(
        f"Generated {len(sources)} OpenCode entries "
        f"({len(sources)} skills, {len(sources)} commands)"
    )


if __name__ == "__main__":
    main()
