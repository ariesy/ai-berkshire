# AI Berkshire Codex Guide

Investment research workflow repository. Source for four-master framework
research skills (巴菲特 / 芒格 / 段永平 / 李录). Maintains dual compatibility
with Claude Code and Codex — never break either side.

## Today's baseline

Before any research, run `date` and treat that output as the latest data
cutoff. State it explicitly in the report header. Never assume the current
date from training data — knowledge cutoff is January 2026.

## Project layout

```
skills/*.md                   Claude Code slash-command sources (canonical)
codex-skills/<name>/SKILL.md  Codex skill packages; generated from skills/
codex-prompts/*.md            Generated Codex custom prompts; compat layer
tools/*.py                    Financial validation / data tools (stdlib only)
reports/                      Research outputs
  <公司名>/                   Per-company report folder (most reports live here)
  portfolio-latest.md         Private (gitignored); do not commit
  community/<公司名>/          External contributors' reports
data/                         Reference data files (watchlist, fundamentals, CSVs)
research/                     In-flight research scratch
筛选公司/                       Pre-screen & recall lists (private)
实盘记录/                       Public weight snapshots (private ledgers go in local/)
assets/                       Static images and logos
docs/                         Long-form essays / roadmap
logs/                         Command logs (most gitignored)
local/                        Personal-only artifacts (entire dir is gitignored)
```

## Skill authoring rules

- `skills/*.md` is the canonical source. Edit there first.
- After changing anything in `skills/`, regenerate Codex artifacts:
  ```
  python3 scripts/sync-codex-skills.py
  python3 scripts/sync-codex-prompts.py   # only when slash prompts matter
  ```
- Before declaring done, verify drift without writing:
  ```
  python3 scripts/sync-codex-skills.py --check
  python3 scripts/sync-codex-prompts.py --check
  ```
- Do not hand-edit generated `codex-skills/<name>/SKILL.md`. Fix the source.
- `codex-skills/investment-memo-craft/` is the one Codex-only hand-written
  package (has `agents/openai.yaml`). Do not create `skills/investment-memo-craft.md`
  unless intentionally adopting it for Claude Code too.

## Report layout

Per-company reports live in `reports/<公司名>/`. Root of `reports/` is reserved
for cross-cutting outputs (industry reports, funnel screens, portfolio,
multi-company comparisons). File naming follows `<公司名>-<skill>-<YYYYMMDD>.md`
(Chinese names, English skill tag, date suffix). Earnings windows use the
quarter tag instead, e.g. `-earnings-2025Q4.md`. See `CLAUDE.md` for the full
naming table.

When producing or modifying a report, preserve siblings in the same folder —
do not rewrite unrelated reports while changing a skill, tool, or script.

## Research quality rules

- Two-source rule: every key financial figure (price, market cap, revenue,
  margin, balance-sheet line) must be cross-checked against at least two
  independent sources before publication.
- Market cap must be hand-verified (price × total shares) and compared against
  the reported figure; flag any gap >1%.
- Currency must be explicit on every figure (CNY / HKD / USD / etc.). Never
  silently mix.
- Estimates are labelled 估计. Don't pass estimates as facts.
- Use the exact-arithmetic engine for math that matters:
  ```
  python3 tools/financial_rigor.py verify-market-cap --price ... --shares ... --reported ...
  python3 tools/financial_rigor.py verify-valuation  --price ... --eps ... --bvps ...
  python3 tools/financial_rigor.py cross-validate   --field ... --values '{...}' --unit ...
  python3 tools/financial_rigor.py calc             --expr '510 * 9.11e9'
  ```
- Run the report audit before treating any generated research as publishable:
  ```
  python3 tools/report_audit.py extract --report reports/<公司名>/<file>.md
  # ...fetch each sampled value from a reliable source...
  python3 tools/report_audit.py verdict --results '[...]'
  ```
- Label low-confidence conclusions, missing data, and source gaps in-line.
  This project is research/learning, not investment advice.

## Writing rules (apply to every skill)

- Chinese. Direct, sharp, no filler.
- Force a conclusion (通过 / 有条件通过 / 灰色 / 否决) with a price band.
  Do not hedge into "it depends" without a concrete decision.
- For every core claim, present the inverse ("但另一方面…") so the reader
  weighs both sides. Never use "我认为 / 显然 / 显然地".
- Distinguish fact (data-backed) from view (labelled 观点 or 推测).
- Rate information richness as A / B / C up front; C-grade outputs say
  "数据不足" honestly rather than padding to look complete.
- Use ★ (1–5, no half-stars) for scoring.

## Editing rules

- Preserve existing report files unless the task explicitly asks to change them.
  `实盘记录/`, `筛选公司/`, and `reports/portfolio-latest.md` are
  personal artifacts — never rewrite or migrate them.
- Keep diffs scoped to the requested skill / tool / script / doc.
- Personal scratch belongs in `local/` (gitignored) or in a temp path under
  `/tmp/opencode/`, never in committed directories.
- Commit messages in Chinese, describing what changed and why.
- Before pushing, `git pull --rebase origin main` — the remote frequently
  receives commits from other sessions.

## Toolchain notes

- Python ≥ 3.7; all tools use only the standard library (no `pip install`).
- `tools/` modules expose CLI subcommands; check `--help` before writing
  ad-hoc Python that duplicates them.
- `tools/xueqiu_scraper.py` writes login state to `/tmp/xueqiu_state.json`
  (gitignored). Do not commit it.
- `logs/command-log.jsonl` is gitignored but `tools/log-command.sh` may append
  to per-report paths (e.g. `reports/美团/command-log.jsonl`) — also gitignored.