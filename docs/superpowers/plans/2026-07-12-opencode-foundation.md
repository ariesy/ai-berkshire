# OpenCode 基础层 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立 OpenCode 作为第三个 first-class harness 的基础层:单一 sync 脚本生成 `.opencode/skills/` + `.opencode/commands/`,4 个手写 subagent,`opencode.example.json` 模板,install 脚本,`.gitignore` 增量。

**Architecture:** 复用 `scripts/sync-codex-skills.py` 的模式但适配 OpenCode 约定(`.opencode/skills/<name>/SKILL.md` 而非 `codex-skills/<name>/SKILL.md`),并新增 commands 生成。源解析双路径:`skills/*.md` + `codex-skills/investment-memo-craft/`(丢弃 `agents/` 子目录)。单一 sync 脚本同时处理两种产物。

**Tech Stack:** Python 3.7+ stdlib only, bash 4+, JSON, YAML frontmatter in markdown。

**Scope:** PR 1 only。后续 PR 2(skill adapter notes + AGENTS.md 增量)、PR 3(README + .bat)不在本计划范围。

## Global Constraints

- **Spec 文档**:`docs/superpowers/specs/2026-07-12-opencode-support-design.md` —— 所有 D1-D8 决策的权威源。
- **Python stdlib only**:不引入 `pip install` 依赖,沿用 `tools/` 和 `scripts/` 现有约定。
- **零项目级 opencode.json**:只提交 `opencode.example.json`;用户的真实配置从 example 复制,gitignored。
- **生成产物 commit**:`.opencode/skills/` 与 `.opencode/commands/` 入库,与 `codex-skills/`、`codex-prompts/` 约定一致。
- **分支**:`feature/opencode`,从 `main` HEAD 拉出(`git log --oneline -1 main` 应为 `459c0c2`)。
- **中文 commit message**:描述"改了什么、为什么"。
- **不回归现有 codex sync**:`python3 scripts/sync-codex-skills.py --check` 与 `sync-codex-prompts.py --check` 在 PR 末尾必须仍然 exit 0。
- **AGENTS.md 第 47 行 rule 不可破**:不重写 `reports/`、`实盘记录/`、`筛选公司/`,不重命名 `reports/portfolio-latest.md`。

---

## 文件结构

### 本计划新增(committed)

```
scripts/
├── sync-opencode-skills.py          # 单一 sync,生成 skills/ + commands/
└── install-opencode.sh              # 装到 $HOME/.config/opencode/

.opencode/
├── agents/                          # 4 个手写 subagent
│   ├── business-analyst.md
│   ├── financial-analyst.md
│   ├── industry-researcher.md
│   └── risk-assessor.md
├── skills/<name>/SKILL.md           # 19 个生成产物
└── commands/<name>.md               # 19 个生成产物

opencode.example.json                # 配置模板
docs/superpowers/plans/
└── 2026-07-12-opencode-foundation.md  # 本计划
```

### 本计划改动

```
.gitignore                           # 加 opencode.json
```

### 本计划 gitignored

```
opencode.json                        # 用户从 example 复制
```

### 测试约定

本仓库无 pytest/test 框架,沿用 `tools/` 和 `scripts/` 现有约定:**shell-based smoke test**,通过 bash one-liner 验证 CLI 行为,不引入新依赖。每个 task 的"测试"步骤用 bash 命令验证文件存在/内容匹配/退出码。

---

## Task 1: Sync 脚本骨架 + 源解析

**Files:**
- Create: `scripts/sync-opencode-skills.py`

**Interfaces:**
- Produces: 模块 `sync_opencode_skills` 含 `discover_sources() -> list[tuple[str, Path]]`、`split_frontmatter(text) -> tuple[str|None, str]`、`first_heading(text, fallback) -> str`、`yaml_quote(value) -> str`

- [ ] **Step 1: 创建脚本骨架**

写 `scripts/sync-opencode-skills.py`:

```python
#!/usr/bin/env python3
"""Generate OpenCode skills and commands from AI Berkshire skill sources.

Single sync script that produces:
  - .opencode/skills/<name>/SKILL.md       (consumed by OpenCode skill loader)
  - .opencode/commands/<name>.md           (slash command frontmatter)

Sources (in order of precedence):
  1. skills/*.md                            (canonical, 18 files)
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
      1. skills/*.md (18 files; canonical Claude Code skills)
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
```

- [ ] **Step 2: 跑通 stub**

Run:
```bash
chmod +x scripts/sync-opencode-skills.py
python3 scripts/sync-opencode-skills.py
```
Expected output: `(stub) would generate 19 entries`

- [ ] **Step 3: 验证源解析数量**

Run:
```bash
python3 -c "
import sys; sys.path.insert(0, 'scripts')
from sync_opencode_skills import discover_sources
sources = discover_sources()
assert len(sources) == 19, f'expected 19, got {len(sources)}'
print('OK:', sorted(n for n, _ in sources))
"
```
Expected: `OK: ['bottleneck-hunter', 'deep-company-series', ..., 'wechat-article']`(19 个,字典序)

- [ ] **Step 4: 验证 memo-craft 来自 codex-skills**

Run:
```bash
python3 -c "
import sys; sys.path.insert(0, 'scripts')
from sync_opencode_skills import discover_sources
sources = dict(discover_sources())
assert sources['investment-memo-craft'].name == 'SKILL.md'
assert 'codex-skills' in str(sources['investment-memo-craft'])
print('OK: memo-craft sourced from codex-skills/')
"
```
Expected: `OK: memo-craft sourced from codex-skills/`

- [ ] **Step 5: Commit**

```bash
git add scripts/sync-opencode-skills.py
git commit -m "新增 sync-opencode-skills.py 骨架与源解析

discover_sources() 双路径扫描 skills/*.md (18 个) +
codex-skills/<name>/SKILL.md (1 个, 仅 investment-memo-craft)。

main() 当前是 stub,后续 task 逐步加 SKILL.md/commands 生成、
memo-craft 特殊路径、stale 清理、--check 模式。"
```

---

## Task 2: SKILL.md 生成

**Files:**
- Modify: `scripts/sync-opencode-skills.py`

**Interfaces:**
- Produces: 函数 `write_skill(name: str, source: Path, *, check: bool) -> bool`(返回 True 表示 drift)

- [ ] **Step 1: 加 `write_skill()` 与 SKILL.md 模板**

替换 `main()` 之前的 stub 行为,在 `discover_sources` 后追加 `write_skill` 函数,改写 `main()` 调用之:

```python
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
```

`main()` 替换为:

```python
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
```

- [ ] **Step 2: 运行 sync 生成所有 SKILL.md**

Run:
```bash
python3 scripts/sync-opencode-skills.py
```
Expected: `Generated 19 OpenCode skills in .opencode/skills`

- [ ] **Step 3: 验证文件数**

Run:
```bash
find .opencode/skills -name SKILL.md | wc -l
```
Expected: `19`

- [ ] **Step 4: 验证 frontmatter 与 adapter note**

Run:
```bash
head -20 .opencode/skills/investment-team/SKILL.md
```
Expected 前 20 行包含:
- 第 1 行: `---`
- 第 2 行: `name: investment-team`
- 第 3 行: `description: "..."`
- 第 4 行: `---`
- 第 5 行: 空行
- 第 6 行: `## OpenCode adapter note`
- 含 `$ARGUMENTS`、`task`、`OPENCODE_ENABLE_EXA`、`tools/`

- [ ] **Step 5: 验证 --check 干净**

Run:
```bash
python3 scripts/sync-opencode-skills.py --check
```
Expected: `Checked 19 OpenCode skills in .opencode/skills`,exit 0。

- [ ] **Step 6: 验证 --check 检测 drift**

Run:
```bash
echo "tampered" >> .opencode/skills/investment-team/SKILL.md
python3 scripts/sync-opencode-skills.py --check
echo "exit=$?"
```
Expected: 输出含 `.opencode/skills/investment-team/SKILL.md`,`exit=1`。

然后恢复:
```bash
python3 scripts/sync-opencode-skills.py
python3 scripts/sync-opencode-skills.py --check
echo "exit=$?"
```
Expected: `exit=0`。

- [ ] **Step 7: Commit**

```bash
git add scripts/sync-opencode-skills.py .opencode/skills/
git commit -m "实现 sync-opencode-skills.py 的 SKILL.md 生成与 --check

每个生成产物:
- YAML frontmatter (name, description 取自源首标题)
- ## OpenCode adapter note 解释 $ARGUMENTS、task 工具映射、
  websearch 需 OPENCODE_ENABLE_EXA、tools/ 调用约定
- 源 skills/<name>.md 正文

--check 模式对比文件内容,drift 列出并 exit 1,clean exit 0。"
```

---

## Task 3: commands/<name>.md 生成

**Files:**
- Modify: `scripts/sync-opencode-skills.py`

**Interfaces:**
- Produces: 函数 `write_command(name: str, source: Path, *, check: bool) -> bool`

- [ ] **Step 1: 加 `write_command()`**

在 `write_skill` 后追加:

```python
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
    text = source.read_text(encoding="utf-8")
    front, body = split_frontmatter(text)
    description_source = front if front is not None else text
    description = first_heading(description_source, name)
    body_text = body if front is not None else text
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
```

`main()` 替换为:

```python
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
```

- [ ] **Step 2: 运行 sync**

Run:
```bash
python3 scripts/sync-opencode-skills.py
```
Expected: `Generated 19 OpenCode entries (19 skills, 19 commands)`

- [ ] **Step 3: 验证 commands 文件**

Run:
```bash
find .opencode/commands -name "*.md" | wc -l
head -10 .opencode/commands/investment-team.md
```
Expected:
- `19`
- frontmatter 含 `agent: build` 和 `description: "<标题>"`

- [ ] **Step 4: --check 干净**

Run:
```bash
python3 scripts/sync-opencode-skills.py --check
```
Expected: 干净,exit 0。

- [ ] **Step 5: Commit**

```bash
git add scripts/sync-opencode-skills.py .opencode/commands/
git commit -m "实现 sync-opencode-skills.py 的 commands/<name>.md 生成

每个生成产物:
- frontmatter 含 description 和 agent (默认 build)
- ## OpenCode adapter note
- 源 skills/<name>.md 正文

COMMAND_AGENT_OVERRIDES 字典预留用于 investment-team /
earnings-team 等需要显式主 agent 的 skill,目前留空。"
```

---

## Task 4: memo-craft 特殊路径

**Files:**
- Modify: `scripts/sync-opencode-skills.py`

- [ ] **Step 1: 加 memo-craft 特殊处理**

`discover_sources` 函数体结尾 `out.append(...)` 后,加 memo-craft 检测与 SKILL.md 内容前移除 `agents/` 子目录的注释:

(实际实现:`write_skill` 已只生成 SKILL.md 单文件,从不复制 `agents/` 子目录,所以无需额外代码。只需加注释说明 + 测试验证。)

在 `write_skill` 函数上方加注释块:

```python
# Note on codex-only hand-written packages (e.g. investment-memo-craft):
# discover_sources() points at codex-skills/investment-memo-craft/SKILL.md
# but write_skill() only writes a single SKILL.md into .opencode/skills/<name>/.
# The agents/openai.yaml sidecar (Codex agent picker metadata) is therefore
# never copied to OpenCode, which is the intended behavior per spec D5.
```

- [ ] **Step 2: 验证 memo-craft 产物不含 agents/**

Run:
```bash
ls .opencode/skills/investment-memo-craft/
test ! -d .opencode/skills/investment-memo-craft/agents && echo "no agents/ OK"
```
Expected: 仅 `SKILL.md`,`no agents/ OK`

- [ ] **Step 3: 验证 memo-craft SKILL.md frontmatter 有效**

Run:
```bash
python3 -c "
import re
text = open('.opencode/skills/investment-memo-craft/SKILL.md').read()
assert text.startswith('---\n'), 'must start with frontmatter'
m = re.match(r'^---\nname: ([a-z0-9-]+)\n', text)
assert m, f'name field missing or invalid: {text[:200]}'
assert m.group(1) == 'investment-memo-craft'
print('OK')
"
```
Expected: `OK`

- [ ] **Step 4: --check 仍干净**

Run:
```bash
python3 scripts/sync-opencode-skills.py --check
```
Expected: 干净,exit 0。

- [ ] **Step 5: Commit**

```bash
git add scripts/sync-opencode-skills.py
git commit -m "memo-craft 特殊路径:验证 OpenCode 端不复制 agents/ 子目录

discover_sources() 指向 codex-skills/investment-memo-craft/SKILL.md,
但 write_skill() 仅写单个 SKILL.md,自然不会把 Codex 私有元数据
agents/openai.yaml 复制到 .opencode/。加注释说明 + 测试验证。"
```

---

## Task 5: stale 清理

**Files:**
- Modify: `scripts/sync-opencode-skills.py`

**Interfaces:**
- Produces: 函数 `cleanup_stale(sources: list[tuple[str, Path]]) -> list[str]` 返回被删路径

- [ ] **Step 1: 加 `cleanup_stale()`**

在 `main()` 之前加:

```python
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
```

`main()` 在生成循环结束后、`if check:` 之前插入:

```python
    if not check:
        removed = cleanup_stale(sources)
        if removed:
            print(f"Removed {len(removed)} stale entries:")
            for path in removed:
                print(f"  {path}")
```

- [ ] **Step 2: 创建 dummy stale 目录测试**

Run:
```bash
mkdir -p .opencode/skills/zzz-dummy-skill
echo "stale" > .opencode/skills/zzz-dummy-skill/SKILL.md
touch .opencode/commands/zzz-dummy-cmd.md
ls .opencode/skills/ .opencode/commands/
```
Expected: 看到 `zzz-dummy-skill/` 和 `zzz-dummy-cmd.md`。

- [ ] **Step 3: 跑 sync 触发清理**

Run:
```bash
python3 scripts/sync-opencode-skills.py
```
Expected: 输出含 `Removed 2 stale entries:`,列出两个 stale 路径。

- [ ] **Step 4: 验证清理结果**

Run:
```bash
test ! -d .opencode/skills/zzz-dummy-skill && echo "skills cleaned OK"
test ! -f .opencode/commands/zzz-dummy-cmd.md && echo "commands cleaned OK"
ls .opencode/skills/ | wc -l
ls .opencode/commands/ | wc -l
```
Expected:
- `skills cleaned OK`
- `commands cleaned OK`
- `19` 和 `19`

- [ ] **Step 5: --check 不报 stale(因为已清干净)**

Run:
```bash
python3 scripts/sync-opencode-skills.py --check
```
Expected: 干净,exit 0。

- [ ] **Step 6: Commit**

```bash
git add scripts/sync-opencode-skills.py
git commit -m "实现 stale 清理:删除源集合外的 .opencode/skills/<name>/ 和 commands/<name>.md

写入模式下,生成完毕后扫描 .opencode/,删除不在 discover_sources()
输出中的条目。--check 模式下不清理(只比对内容,删除是写操作)。"
```

---

## Task 6: install 脚本

**Files:**
- Create: `scripts/install-opencode.sh`

- [ ] **Step 1: 写 install 脚本**

`scripts/install-opencode.sh`:

```bash
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
```

- [ ] **Step 2: 语法检查**

Run:
```bash
bash -n scripts/install-opencode.sh && echo "syntax OK"
```
Expected: `syntax OK`

- [ ] **Step 3: Dry-run 到临时目录**

Run:
```bash
OPENCODE_HOME="$(mktemp -d)" bash scripts/install-opencode.sh
find "$OPENCODE_HOME" -name "SKILL.md" | wc -l
find "$OPENCODE_HOME" -name "*.md" -path "*/commands/*" | wc -l
```
Expected: `19` 和 `19`。

- [ ] **Step 4: 验证 install 是幂等的(再跑一次)**

Run:
```bash
OPENCODE_HOME="$(mktemp -d)" bash scripts/install-opencode.sh
OPENCODE_HOME="$OPENCODE_HOME" bash scripts/install-opencode.sh
echo "exit=$?"
```
Expected: `exit=0`,无报错(`rm -rf` 前先清空)。

- [ ] **Step 5: 清理临时目录**

Run:
```bash
rm -rf "${OPENCODE_HOME:-/tmp/nonexistent}"
```

- [ ] **Step 6: Commit**

```bash
git add scripts/install-opencode.sh
git commit -m "新增 install-opencode.sh:装到 ~/.config/opencode/

- 默认装到 \$HOME/.config/opencode/,OPENCODE_HOME 可覆盖
- 先跑 sync 确保产物最新
- 拷贝 .opencode/skills/ 与 .opencode/commands/ 到用户级目录
- 提示用户设 OPENCODE_ENABLE_EXA=1 启用 websearch"
```

---

## Task 7: 4 个 subagent 文件

**Files:**
- Create: `.opencode/agents/business-analyst.md`
- Create: `.opencode/agents/financial-analyst.md`
- Create: `.opencode/agents/industry-researcher.md`
- Create: `.opencode/agents/risk-assessor.md`

- [ ] **Step 1: 创建 `.opencode/agents/` 目录**

Run:
```bash
mkdir -p .opencode/agents
```

- [ ] **Step 2: 写 `business-analyst.md`(段永平视角)**

`.opencode/agents/business-analyst.md`:

```markdown
---
description: 段永平视角的商业模式与护城河分析师。在 investment-team 框架中负责评估"对的事"和生意本质。Use when running /investment-team, /earnings-team, or any task needing business-model deep dive.
mode: subagent
temperature: 0.2
permission:
  edit: deny
  write: deny
  bash:
    "python3 tools/*": allow
    "date": allow
    "*": ask
  webfetch: allow
  websearch: allow
  skill: allow
  todowrite: allow
---

你是 AI Berkshire 投研团队的商业模式分析师,采用段永平视角。

## 你的任务

对 $ARGUMENTS 给定的公司,产出一份"商业模式与护城河"分析报告,
供 team-lead 汇总到最终投资判断中。

## 分析框架

1. **生意本质**:这家公司到底在卖什么?用户为什么付钱?
   用一句话概括"谁付钱、为什么付、什么是稀缺、什么在重复"。
2. **护城河**:逐项评估(品牌/定价权/切换成本/网络效应/规模/成本优势/牌照/资源稀缺/技术),
   每项标注 ★1-5,并说明过去 3-5 年护城河是变宽还是变窄。
3. **"对的事"判定**:段永平:"Stop trying to predict the future,
   focus on what is right in front of you"。这家公司的"对的事"是什么?
4. **反面检验**:什么能摧毁这个护城河?不是竞争对手,而是监管/技术变迁/需求消失?
   即使答案"短期没有",也要明确写出。

## 数据规则

- 关键数字(收入/毛利/客户数/留存率)必须两个独立来源交叉验证,
  误差 >1% 必须标注。
- 用 `python3 tools/financial_rigor.py calc` 做精确算术,
  不要手算。
- 报告开头写明数据截止日(运行 `date` 取)。

## 输出格式

中文 markdown,300-800 字。结尾给出明确结论:
- 通过 / 有条件通过 / 灰色 / 否决
- 1-2 句说明核心依据
- 不确定项诚实标"数据不足"

## 反偏见

- 资料多 ≠ 确定;资料少 ≠ 不确定
- 强制呈现反面("但另一方面...")
- 区分事实(数据支撑)和观点(标注"观点"或"推测")
- 信息丰富度自评 A/B/C

不要执行文件写入或编辑——只返回 markdown 文本给 team-lead。
```

- [ ] **Step 3: 写 `financial-analyst.md`(巴菲特视角)**

`.opencode/agents/financial-analyst.md`(frontmatter 同上,`temperature: 0.1`,正文如下):

```markdown
你是 AI Berkshire 投研团队的财务与估值分析师,采用巴菲特视角。

## 你的任务

对 $ARGUMENTS 给定的公司,产出一份"财务质量与内在价值"分析报告,
供 team-lead 汇总到最终投资判断中。

## 分析框架

1. **内在价值三步法**:
   - 估算 owner earnings(净利润 + 折旧摊销 - 维持性资本支出)
   - 选定折现率(通常 8-12%)
   - 算出现值,与当前市值对比,得出安全边际
2. **资本回报**:ROIC 而非 ROE;长期股权回报率 5 年滚动。
   警惕"高 ROE 但低 ROIC"(靠杠杆堆出来的回报不是真回报)。
3. **GAAP 数字游戏**:非经常性损益、商誉减值、研发资本化、
   折旧政策选择,这些都让 GAAP 数字偏离真实现金流。
4. **管理层资本配置**:留存的每一块钱创造了多少市值?
   回购/分红/并购的纪律性如何?
5. **反面检验**:即使财务漂亮,管理层有没有毁损股东价值的扩张冲动?
   (常见:为增长而并购、为规模而并购、为管理层自尊而并购)

## 数据规则

- 用 `python3 tools/financial_rigor.py verify-valuation` 校验估值
- 用 `python3 tools/financial_rigor.py verify-market-cap` 校验市值
- 跨源数据用 `cross-validate` 工具
- 任何估算标注"估计"

## 输出格式

中文 markdown,300-800 字。结尾给出明确结论 + 合理买入价区间。

## 反偏见

同 business-analyst。

不要执行文件写入或编辑——只返回 markdown 文本给 team-lead。
```

- [ ] **Step 4: 写 `industry-researcher.md`(芒格视角)**

`.opencode/agents/industry-researcher.md`(frontmatter 同上,`temperature: 0.3`,正文):

```markdown
你是 AI Berkshire 投研团队的产业格局与心智模型分析师,采用芒格视角。

## 你的任务

对 $ARGUMENTS 给定的行业 / 公司,产出一份"行业格局 + 反向思考"分析报告,
供 team-lead 汇总到最终投资判断中。

## 分析框架

1. **波特五力**:供应商议价、客户议价、新进入者、替代品、行业内竞争烈度。
   每项标 ★1-5。
2. **心智模型清单**:规模效应/网络效应/边际成本/反摩尔/激励机制扭曲/
   幸存者偏差/锚定效应。挑出与本案最相关的 3 个,展开说。
3. **主动反向思考**:"哪些'显而易见'的前提其实是错的?"
   列出 3 个最被市场共识接受的假设,逐一反转。
4. **赢家时间窗口**:即使行业赢家已定,什么会让它再次变差?
   (监管、颠覆性技术、需求结构变化、人口结构)
5. **反面检验**:芒格:"Invert, always invert"。如果这家公司的投资逻辑
   错了,会错在哪里?列出最可能的 3 种错法。

## 数据规则

- 行业数据至少两个独立来源(IDC/Gartner/Euromonitor/国家统计局)
- 引用具体数字,不要"行业普遍认为"这种模糊表述

## 输出格式

中文 markdown,400-900 字。结尾给出对行业"赢家通吃 vs 群雄割据"的判断。

## 反偏见

同 business-analyst。

不要执行文件写入或编辑——只返回 markdown 文本给 team-lead。
```

- [ ] **Step 5: 写 `risk-assessor.md`(李录视角)**

`.opencode/agents/risk-assessor.md`(frontmatter 同上,`temperature: 0.1`,正文):

```markdown
你是 AI Berkshire 投研团队的风险与管理层评估分析师,采用李录视角。

## 你的任务

对 $ARGUMENTS 给定的公司,产出一份"管理层与长期风险"评估报告,
供 team-lead 汇总到最终投资判断中。

## 分析框架

1. **管理层**:诚信 > 能力。
   - 历史言行一致性(说过的话 vs 做过的事)
   - 激励机制与股东利益的对齐程度
   - 管理层自身持仓(是否与股东共担风险)
2. **公司治理**:
   - 董事会独立性(独立董事占比、是否真的敢投反对票)
   - 关联交易占比
   - 信息披露质量(财报电话会的坦诚度)
3. **长期毁灭性风险**(每个标 概率 × 影响):
   - 技术替代(下一代技术会不会让现有产品过时?)
   - 监管(政策方向是否在收紧?)
   - ESG / 社会舆论风险
   - 地缘 / 跨境风险
   - 会计造假的可能性
4. **反面检验**:即使管理层优秀、财报干净,什么外部事件会让好公司变质?
   列出 3 个最可能的"黑天鹅"。

## 数据规则

- 管理层背景用 LinkedIn + 公司 IR 页交叉验证
- 关联交易从年报附注扒具体数字
- 监管风险看最近 3 年政策动向,不要凭印象

## 输出格式

中文 markdown,400-900 字。结尾给出风险等级:低/中/高/极高,
并列出最值得监控的 3 个预警指标。

## 反偏见

同 business-analyst。

不要执行文件写入或编辑——只返回 markdown 文本给 team-lead。
```

- [ ] **Step 6: 验证 4 个文件 frontmatter 可解析**

Run:
```bash
python3 -c "
import re
import yaml
for name in ['business-analyst', 'financial-analyst', 'industry-researcher', 'risk-assessor']:
    text = open(f'.opencode/agents/{name}.md').read()
    m = re.match(r'^---\n(.*?)\n---\n', text, re.DOTALL)
    assert m, f'{name}: frontmatter not found'
    fm = yaml.safe_load(m.group(1))
    assert fm['mode'] == 'subagent', f'{name}: mode must be subagent'
    assert 'description' in fm
    print(f'OK: {name} mode={fm[\"mode\"]}')
"
```
Expected: 4 行 `OK: <name> mode=subagent`

(若 `yaml` 模块不可用,改用正则提取 `description` 字段。)

- [ ] **Step 7: 验证 4 个文件都存在**

Run:
```bash
ls .opencode/agents/
```
Expected:
```
business-analyst.md
financial-analyst.md
industry-researcher.md
risk-assessor.md
```

- [ ] **Step 8: Commit**

```bash
git add .opencode/agents/
git commit -m "新增 4 个 OpenCode subagent:business/financial/industry/risk 视角

- business-analyst (段永平, temperature 0.2)
- financial-analyst (巴菲特, 0.1)
- industry-researcher (芒格, 0.3)
- risk-assessor (李录, 0.1)

每个文件:mode=subagent, edit/write deny, bash 白名单
(python3 tools/* + date), webfetch/websearch/skill/todowrite 允许。
正文是结构化 prompt:分析框架 + 数据规则 + 输出格式 + 反偏见清单。
team-lead 通过 task(subagent_type=<name>, prompt=...) 调用。"
```

---

## Task 8: opencode.example.json 模板

**Files:**
- Create: `opencode.example.json`

- [ ] **Step 1: 写 `opencode.example.json`**

```json
{
  "$schema": "https://opencode.ai/config.json",
  "instructions": ["AGENTS.md", "ai_CLAUDE.md"],

  "skills": {
    "paths": [".opencode/skills"]
  },

  "permission": {
    "edit": { "*": "ask", "reports/**/*.md": "allow", "tools/*.py": "allow" },
    "write": { "*": "ask", "reports/**/*.md": "allow" },
    "bash": {
      "*": "ask",
      "python3 tools/*": "allow",
      "date": "allow",
      "git status*": "allow",
      "git log*": "allow",
      "git diff*": "allow",
      "python3 scripts/sync-*": "allow"
    },
    "webfetch": "allow",
    "websearch": "allow",
    "skill": "allow"
  },

  "agent": {
    "build": {
      "permission": {
        "task": {
          "*": "deny",
          "business-analyst": "allow",
          "financial-analyst": "allow",
          "industry-researcher": "allow",
          "risk-assessor": "allow",
          "explore": "allow",
          "general": "allow",
          "scout": "allow"
        }
      }
    }
  }
}
```

- [ ] **Step 2: 验证 JSON 合法**

Run:
```bash
python3 -c "import json; print(json.dumps(json.load(open('opencode.example.json')), indent=2)[:200])"
```
Expected: 输出首行 `\`$schema\`: \`https://opencode.ai/config.json\`` 或类似。

- [ ] **Step 3: 验证 \$schema URL 正确**

Run:
```bash
python3 -c "
import json
cfg = json.load(open('opencode.example.json'))
assert cfg['\$schema'] == 'https://opencode.ai/config.json'
assert 'AGENTS.md' in cfg['instructions']
assert cfg['permission']['websearch'] == 'allow'
assert cfg['agent']['build']['permission']['task']['business-analyst'] == 'allow'
print('OK')
"
```
Expected: `OK`

- [ ] **Step 4: 验证 task 权限兜底**

Run:
```bash
python3 -c "
import json
cfg = json.load(open('opencode.example.json'))
task_perms = cfg['agent']['build']['permission']['task']
# last-match-wins: '*': deny should be FIRST key, specific allows AFTER
keys = list(task_perms.keys())
assert keys[0] == '*' and task_perms['*'] == 'deny', 'must start with deny-all'
specific_allows = [k for k in keys if task_perms[k] == 'allow']
assert 'business-analyst' in specific_allows
print('OK: last-match-wins with deny-all first')
"
```
Expected: `OK: last-match-wins with deny-all first`

- [ ] **Step 5: Commit**

```bash
git add opencode.example.json
git commit -m "新增 opencode.example.json:项目级 OpenCode 配置模板

- \$schema 指向官方 schema URL
- instructions: 自动加载 AGENTS.md + ai_CLAUDE.md
- skills.paths: .opencode/skills (项目本地)
- permission:
  - edit/write 默认 ask,reports/ 和 tools/ 允许(投研工作流)
  - bash 白名单只放已知安全命令(issue #58 精神)
  - webfetch/websearch/skill 允许
- agent.build.permission.task: last-match-wins 兜底
  (* deny,然后显式 allow 4 个自定义 + 3 个内置 subagent)

用户从本文件复制为 opencode.json 后即可使用。"
```

---

## Task 9: .gitignore + 最终验证

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: 检查现有 .gitignore**

Run:
```bash
cat .gitignore
```
找到合适的注释分组(在 `# 本地资料区` 附近或文件末尾)。

- [ ] **Step 2: 加 `opencode.json` 忽略**

在 `.gitignore` 末尾追加(若已有 `# OpenCode` 段则合并):

```
# OpenCode per-user config(从 opencode.example.json 复制)
opencode.json
```

- [ ] **Step 3: 验证 git status 干净**

Run:
```bash
touch opencode.json
git status --short opencode.json
git clean -f opencode.json
```
Expected: `?? opencode.json`(未跟踪,符合 gitignore 行为),`rm` 后无残留。

- [ ] **Step 4: 运行所有 sync 验证**

Run:
```bash
python3 scripts/sync-opencode-skills.py
python3 scripts/sync-opencode-skills.py --check
python3 scripts/sync-codex-skills.py --check
python3 scripts/sync-codex-prompts.py --check
```
Expected: 4 个命令全 exit 0,无 drift。

- [ ] **Step 5: 验证最终文件清单**

Run:
```bash
echo "=== scripts ==="
ls scripts/install-opencode.sh scripts/sync-opencode-skills.py
echo "=== agents ==="
ls .opencode/agents/
echo "=== skills count ==="
find .opencode/skills -name SKILL.md | wc -l
echo "=== commands count ==="
find .opencode/commands -name "*.md" | wc -l
echo "=== config ==="
ls opencode.example.json
echo "=== gitignore ==="
grep -c opencode.json .gitignore
```
Expected:
- 2 个脚本文件
- 4 个 agent 文件
- `19` skills, `19` commands
- `opencode.example.json` 存在
- `grep -c` 返回 `1`(忽略了一行)

- [ ] **Step 6: 全局 git status 检查**

Run:
```bash
git status --short
```
Expected: 仅看到本计划的 9 个 commit 改动文件,无意外修改。

- [ ] **Step 7: Commit**

```bash
git add .gitignore
git commit -m "添加 opencode.json 到 .gitignore

真实 OpenCode 用户配置从 opencode.example.json 复制,不入库。
opencode.example.json 模板本身提交。"
```

---

## 自查清单

- **Spec 覆盖**:D1 (4 agents) → Task 7;D2 (项目本地 skills) → Task 2;D3 (websearch+env) → Task 2 adapter note,Task 8 permission.websearch;D4 (example.json 模板) → Task 8;D5 (memo-craft 丢 agents/) → Task 4;D6 (单一 sync) → Tasks 1-5;D7 (生成产物 commit) → Task 2/3 末尾;D8 (装到 ~/.config/opencode/) → Task 6。
- **占位符**:0 处 "TBD"/"TODO"/"实现细节见 X"。所有 shell 命令和 Python 代码都完整。
- **类型一致**:`discover_sources()`、`write_skill()`、`write_command()`、`cleanup_stale()` 名字跨 task 一致。
- **回归保护**:Task 9 Step 4 显式跑 `sync-codex-skills.py --check` 和 `sync-codex-prompts.py --check`,确保不破坏现有 codex 同步。