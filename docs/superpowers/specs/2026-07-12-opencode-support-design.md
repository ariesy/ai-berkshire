# OpenCode 支持设计 Spec

- **Date**: 2026-07-12
- **Branch**: `feature/opencode`
- **Status**: Draft — pending user review
- **Scope**: OpenCode 作为第三个 first-class harness,scope 见文末"实施拆分"

## 背景与目标

AI Berkshire 当前已支持 Claude Code(`skills/*.md`)和 Codex(`codex-skills/` + `codex-prompts/`)两套 harness。本次新增 OpenCode 作为第三个 first-class 引擎,目标:

1. 用户在 OpenCode TUI 中可以直接使用 `/<skill-name> <args>` 斜杠命令,体验与 Claude Code 一致
2. 投资研究框架的四角色并行(段永平 / 巴菲特 / 芒格 / 李录)在 OpenCode 上以 subagent 形式落地
3. 保持 `skills/*.md` 为唯一 canonical 源,所有 harness 共享同一份业务指令
4. 不破坏现有 Claude Code / Codex 用户的体验(diff 收敛在新增文件 + 少量 skill adapter note)

非目标:

- 不替换或重写 Claude Code / Codex 的生成逻辑
- 不引入除 OpenCode 外的第四个 harness
- 不改动 `tools/*.py`、报告目录、AGENTS.md 既有章节

## 已确认的关键决策

| ID | 决策 | 理由 |
|----|------|------|
| D1 | 4 个自定义 agent 文件(`.opencode/agents/<name>.md`) | 贴合 Claude Code 原 `investment-team.md` 的 4 角色设计 |
| D2 | 生成 `.opencode/skills/` 项目本地树 | self-contained,不依赖预先安装 Claude Code |
| D3 | 保留 websearch 调用语义,加 env-var precheck | 联网研究语义对齐 Claude Code |
| D4 | 提交 `opencode.example.json` 模板,真实 `opencode.json` 不入库 | 避免误提交 provider / 个人配置 |
| D5 | `investment-memo-craft` 镜像但丢弃 `agents/openai.yaml` | 保留 skill 内容,删除 Codex 私有元数据 |
| D6 | 单一 `sync-opencode-skills.py` 同时生成 skills/ 和 commands/ | 逻辑同源,避免两脚本漂移 |
| D7 | 生成产物 commit(`.opencode/skills/`、`.opencode/commands/`) | 与现有 `codex-skills/`、`codex-prompts/` 约定一致 |
| D8 | 安装到 `~/.config/opencode/`(`$OPENCODE_HOME` 可覆盖) | OpenCode 官方约定的用户级目录 |

## 文件布局

### 新增文件(committed)

```
scripts/
├── sync-opencode-skills.py          # 单一 sync 脚本,生成 skills/ 和 commands/
├── install-opencode.sh              # 安装到 ~/.config/opencode/
└── install-opencode.bat             # Windows 版(可选,scope 标记 stretch)

.opencode/
├── agents/                          # 4 个手写 subagent
│   ├── business-analyst.md          # 段永平视角
│   ├── financial-analyst.md         # 巴菲特视角
│   ├── industry-researcher.md       # 芒格视角
│   └── risk-assessor.md             # 李录视角
├── skills/<name>/SKILL.md           # 生成产物,19 个
└── commands/<name>.md               # 生成产物,19 个

opencode.example.json                # 配置模板
docs/superpowers/specs/
└── 2026-07-12-opencode-support-design.md   # 本 spec
```

### 改动文件

```
skills/investment-team.md            # 加 OpenCode adapter note,WebSearch precheck 改 harness-agnostic
skills/earnings-team.md              # 同上(若使用 Team/Task 模式)
.gitignore                           # 加 opencode.json
AGENTS.md                            # 加 "OpenCode support" 章节
```

### gitignored

```
opencode.json                        # 用户从 example.json 复制
```

## Sync 脚本设计

### 入口与 CLI

```bash
python3 scripts/sync-opencode-skills.py          # 写入模式,生成所有产物
python3 scripts/sync-opencode-skills.py --check  # 校验模式,drift 则 exit 1
```

### 源解析

```python
discover_sources():
    1. 扫 skills/*.md                                # 18 个
    2. 扫 codex-skills/<name>/SKILL.md (排除 #1)     # 1 个(仅 investment-memo-craft)
    3. 按 name 字典序返回 19 个 (name, source_path)
```

### SKILL.md 生成模板

```markdown
---
name: <name>
description: "<first heading 提取>"
---

## OpenCode adapter note

- $ARGUMENTS = 用户当前请求的标的 / 公司 / 主题
- Claude 私有工具名映射:
  - Task / TeamCreate → task 工具,subagent_type = "<name>"
  - WebSearch         → websearch (需 OPENCODE_ENABLE_EXA=1)
  - WebFetch          → webfetch
  - Bash/Read/Write/Edit/Grep/Glob → 同名
- 4 个自定义 subagent 名: business-analyst, financial-analyst,
  industry-researcher, risk-assessor
- 共享工具位于 tools/,从仓库根运行 python3 tools/<tool>.py
- 运行 date 取数据截止日,写到报告头部
- 严格遵守 AGENTS.md 的研究质量规则(交叉验证、精确算术、估算标注)

<skills/<name>.md 原始正文>
```

### commands/<name>.md 生成模板

```markdown
---
description: "<first heading>"
agent: <build | investment-team-specific override>
---

## OpenCode adapter note

(同 SKILL.md 的 8 行)

<skills/<name>.md 原始正文>
```

`agent` 字段默认 `build`。`investment-team` 和 `earnings-team` 显式 `agent: build`(已默认),避免 OpenCode "subagent 触发 subagent" 的歧义。

### memo-craft 特殊路径

`discover_sources` 第 2 步命中 `codex-skills/investment-memo-craft/SKILL.md` 时,只复制该文件到 `.opencode/skills/investment-memo-craft/SKILL.md`。`agents/openai.yaml` 子目录整段跳过。

### stale 清理

写入模式末尾,扫 `.opencode/skills/` 和 `.opencode/commands/`,删除不在 `discover_sources()` 输出中的条目。保证删除 `skills/foo.md` 后,`.opencode/skills/foo/` 也被清掉。

### `--check` 模式

逐文件 diff 期望输出与磁盘实际内容,任一不一致则输出 drift 列表并 exit 1。零不一致输出 "OpenCode artifacts current (N entries checked)" 并 exit 0。

## 4 个自定义 Subagent 设计

### 通用 frontmatter 模板

```markdown
---
description: <一句,视角 + 何时调用>
mode: subagent
temperature: <0.1 ~ 0.3>
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
  todowrite: allow                 # 显式开启(subagent 默认关)
---
```

`temperature` 由各 agent 自定:
- `business-analyst`: 0.2
- `financial-analyst`: 0.1
- `industry-researcher`: 0.3
- `risk-assessor`: 0.1

### 角色 prompt 摘要

每个 agent 文件正文 ~80-150 行,中文,结构:

1. **角色定位**:你是什么视角的分析师,在团队里负责什么
2. **分析框架**:核心问题清单(参考下方)
3. **数据规则**:强制 AGENTS.md 的研究质量约束
4. **输出格式**:300-800 字 markdown,结尾给出明确结论
5. **反偏见清单**:资料多≠确定、强制反面、事实 vs 观点、A/B/C 自评

各 agent 的分析框架差异:

| Agent | 核心问题 |
|-------|---------|
| business-analyst (段永平) | 生意本质、护城河 8 维度评分、"对的事"判定、反面:什么能摧毁护城河 |
| financial-analyst (巴菲特) | 内在价值三步法、owner earnings、ROIC、警惕 GAAP 数字游戏、资本回报 5 年滚动 |
| industry-researcher (芒格) | 波特五力、规模/网络/边际成本心智模型、反向思考"哪些'显而易见'的前提是错的" |
| risk-assessor (李录) | 管理层诚信 > 能力、激励机制、长期毁灭性风险(技术/监管/ESG/会计)、管理层言行一致性 |

### 任务指令

`investment-team.md` 在 OpenCode adapter note 中明确:

```
启动 4 个并行 subagent 时使用 task 工具:
  task(subagent_type="business-analyst", prompt="<角色 prompt + 公司>")
  task(subagent_type="financial-analyst", prompt="...")
  task(subagent_type="industry-researcher", prompt="...")
  task(subagent_type="risk-assessor", prompt="...")
```

子 agent 不改文件,只返回 markdown 文本给 team-lead。team-lead 主 agent(`build`)做汇总。

## opencode.example.json 模板

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

`permission.task` 用 last-match-wins 语义,先 `*` deny 兜底,再显式 allow 6 个 subagent。

## skill adapter 改造

### 范围确认

`grep -l "TeamCreate\\|Task(\\|SendMessage\\|WebSearch" skills/*.md` 命中的文件:

- `skills/investment-team.md`(确认)
- `skills/earnings-team.md`(待 PR 时实际验证,若不命中则不动)

其他文件不涉及 Claude 私有工具,无需改动。

### investment-team.md 改动

1. 顶部新增 `## OpenCode adapter note`,与现有 `## Codex adapter note` 并列。内容覆盖:
   - `$ARGUMENTS` 解释
   - `Task`/`TeamCreate` → `task` 工具 + 4 个 subagent_type
   - `WebSearch` → `websearch` + `OPENCODE_ENABLE_EXA=1` 提示
   - 其他工具同名映射
   - tools/ 调用方式
   - AGENTS.md 研究质量规则引用
2. WebSearch precheck 段改写为 harness-agnostic 版本:

```markdown
### 第一步¾:Web 搜索权限预检(关键 · 避免 Agent 静默退化)

启动任何后台 Agent 之前,先确认当前 harness 已放行 Web 搜索。

- **Claude Code**: WebSearch 必须在 .claude/settings.local.json 的 permissions.allow 白名单中。
- **OpenCode**: 需要环境变量 `OPENCODE_ENABLE_EXA=1`(websearch 工具由 Exa AI 提供)。
- **Codex**: 默认可用,无需预检。

任一未放行 → 停下来,不要启动 Agent,提示用户先放行。
```

具体 Bash 命令改为举例(放在附录或脚注):

```bash
# Claude Code 检查
grep -l '"WebSearch"' .claude/settings.local.json 2>/dev/null

# OpenCode 检查
test -n "$OPENCODE_ENABLE_EXA" && echo "exsearch enabled"
```

不删 Claude-specific 例子,只是补 OpenCode 分支。

### earnings-team.md 改动

若 grep 命中则同 `investment-team.md` 处理;若不命中则跳过。

## AGENTS.md 增量

在 "Skill authoring rules" 与 "Report layout" 之间新增章节:

```markdown
## OpenCode support

OpenCode 作为第三个 harness 受支持,使用方式与 Claude Code / Codex 并列。

### 同步产物

- `.opencode/skills/<name>/SKILL.md` — 从 `skills/*.md` 生成
- `.opencode/commands/<name>.md` — 从 `skills/*.md` 生成
- `.opencode/agents/<name>.md` — 4 个手写 subagent(committed)
- `opencode.example.json` — 配置模板

### Sync

改动 `skills/*.md` 后:

    python3 scripts/sync-opencode-skills.py
    python3 scripts/sync-opencode-skills.py --check

### 安装

    bash scripts/install-opencode.sh

把 `.opencode/skills/` 和 `.opencode/commands/` 拷贝到 `~/.config/opencode/`。
`agents/` 和 `opencode.example.json` 由 OpenCode 直接从项目根读取,无需拷贝。

### Web 搜索启用

`OPENCODE_ENABLE_EXA=1` 环境变量需在启动 OpenCode 前 export,否则
`websearch` 工具不可用,subagent 的联网研究能力降级。
```

## .gitignore 增量

```
# OpenCode per-user config(从 opencode.example.json 复制)
opencode.json
```

不忽略 `.opencode/skills/`、`.opencode/commands/`、`.opencode/agents/` —— 这些是项目级资产,需要入 git。

## 安装脚本设计

### scripts/install-opencode.sh

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${OPENCODE_HOME:-$HOME/.config/opencode}"

python3 "$ROOT/scripts/sync-opencode-skills.py"
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

Windows 版 `.bat` 为 stretch goal,本期可选。

## 验证计划

### 静态校验(必过)

1. `python3 scripts/sync-opencode-skills.py --check` exit 0
2. `python3 scripts/sync-codex-skills.py --check` exit 0(回归)
3. `python3 scripts/sync-codex-prompts.py --check` exit 0(回归)
4. `.opencode/skills/` 共 19 个 SKILL.md,`.opencode/commands/` 共 19 个 .md
5. `codex-skills/investment-memo-craft/` 有 `agents/`,`.opencode/skills/investment-memo-craft/` 无 `agents/`

### 动态验证(stretch,需 OpenCode TUI 环境)

6. 启动 `opencode`,输入 `/investment-team 测试公司`,验证:
   - 命令被识别(出现在 TUI 自动补全)
   - $ARGUMENTS = "测试公司"
   - WebSearch precheck 按 harness 执行
7. `@business-analyst` 在 @ 自动补全中可见
8. `OPENCODE_ENABLE_EXA=1 opencode` 下,subagent 可正常 websearch
9. `unset OPENCODE_ENABLE_EXA` 启动,subagent 在 precheck 阶段提示并 abort

### 验收(必过)

10. 不破坏 Claude Code 用户:在 Claude Code 中跑 `/investment-team <测试公司>` 仍按原逻辑执行
11. 不破坏 Codex 用户:在 Codex 中跑 `investment-team` skill 仍按 adapter note 执行

## 实施拆分(PR 序列)

### PR 1: 基础层(sync + agents + config)

- `scripts/sync-opencode-skills.py`(含 `--check` 模式 + stale 清理)
- `scripts/install-opencode.sh`
- `.opencode/agents/{business,financial,industry,risk}-analyst.md`
- `opencode.example.json`
- `.gitignore` 增量
- `docs/superpowers/specs/2026-07-12-opencode-support-design.md`(本 spec)

跑通验证 #1-#5。

### PR 2: 适配层(skill adapter + AGENTS.md)

- `skills/investment-team.md`:加 OpenCode adapter note,WebSearch precheck harness-agnostic
- `skills/earnings-team.md`:若 grep 命中则同处理
- `AGENTS.md`:加 OpenCode 章节

跑通验证 #2-#3(回归)+ 全文静态校验。

### PR 3(stretch): 文档与 Windows 安装脚本

- `scripts/install-opencode.bat`
- README 三方对照表更新(若有)
- CONTRIBUTING.md 注明 OpenCode 贡献路径

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| `task` 工具的实际 API 与 docs 描述有出入 | PR 1 后做一次 smoke test;不通过则 adapter note 改为"使用 OpenCode @mention 触发 subagent" |
| `OPENCODE_ENABLE_EXA=1` 默认不可用,subagent 静默失败 | precheck 阶段显式报错;报告中加 ⚠️ 标识 |
| 生成脚本与 codex-sync 漂移 | 两个脚本独立写、独立 `--check`,但共享同一份源解析约定,文档化 |
| `investment-team.md` 改动影响 Claude Code 用户 | adapter note 只追加,不删改原内容;WebSearch precheck 改为分支结构 |

## 后续可选工作(本 spec 范围外)

- OpenCode plugin 用于自动 inject `OPENCODE_ENABLE_EXA` 检测
- 跨 harness 的报告审计(把 `report_audit.py` 暴露为 OpenCode tool)
- 把 4 个 subagent 共享给 Codex(Codex 也支持 subagent,但默认没有这些)