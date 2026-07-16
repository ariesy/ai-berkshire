#!/usr/bin/env python3
"""tdx_data.py — A-share 离线数据桥接到 tdx-chronos

通过 subprocess 调用 /app/tdx-chronos/scripts/query.py, 无网络依赖。
所有 A 股 + 场内基金 + 可转债 日 K 线、财务三表、股本变动全覆盖。

用法:
    python3 tools/tdx_data.py quote 688248
    python3 tools/tdx_data.py financials 688248
    python3 tools/tdx_data.py valuation 688248
    python3 tools/tdx_data.py kline 688248 --limit 5
    python3 tools/tdx_data.py search 688248
    python3 tools/tdx_data.py health

输出: 人类可读 (默认) 或 --json (程序化)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

TDS_QUERY = "/app/tdx-chronos/scripts/query.py"
TDS_VENV = "/app/tdx-chronos/.venv/bin/python"

# ─── helpers ──────────────────────────────────────────────────────────


def _run(command: str, *args: str) -> dict | list:
    """Call tdx-chronos CLI and return parsed JSON."""
    cmd = [TDS_VENV, TDS_QUERY, command] + list(args)
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60,
        )
    except subprocess.TimeoutExpired:
        return {"error": "tdx query timed out"}
    except FileNotFoundError:
        return {"error": f"tdx-chronos not found at {TDS_VENV}"}

    if proc.returncode != 0:
        return {"error": proc.stderr.strip() or f"exit code {proc.returncode}"}

    stderr = proc.stderr.strip()
    if stderr and "WARNING" not in stderr:
        return {"error": stderr}

    stdout = proc.stdout.strip()
    if not stdout:
        return {"error": "empty response"}

    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return {"error": f"json parse failed: {stdout[:200]}"}


def _fmt(val, unit="", decimals=2) -> str:
    """Human-readable number formatting."""
    if val is None:
        return "—"
    try:
        v = float(val)
        if abs(v) >= 1e8:
            return f"{v / 1e8:.{decimals}f}亿{unit}"
        elif abs(v) >= 1e4:
            return f"{v / 1e4:.{decimals}f}万{unit}"
        else:
            return f"{v:.{decimals}f}{unit}"
    except (ValueError, TypeError):
        return str(val)


def _table(headers: list[str], rows: list[list[str]]):
    """Print aligned Markdown-style table."""
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(cell)))
    sep = " | "
    header_line = sep.join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    print(header_line)
    print(sep.join("-" * col_widths[i] for i in range(len(headers))))
    for row in rows:
        print(sep.join(str(row[i]).ljust(col_widths[i]) for i in range(len(headers))))


def _sep(title: str):
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


# ─── subcommands ──────────────────────────────────────────────────────


def cmd_valuation(args):
    """Comprehensive valuation snapshot from K-line + FY2025 financials."""
    data = _run("valuation", args.code)
    if isinstance(data, dict) and "error" in data:
        print(f"❌ {data['error']}")
        return

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    d = data
    _sep(f"估值快照 — {d.get('symbol', args.code)}")

    print(f"  股价:     {d.get('price', '—')} 元  ({d.get('kl_date', '—')})")
    def _wan_to_yi(val):
        """万元 → 亿 (human-readable)."""
        if val is None:
            return "—"
        return f"{float(val) / 10000:.2f}亿"

    print(f"  市值:     {_fmt(d.get('market_cap_yi'), '元')}")
    if d.get('total_shares_yi'):
        print(f"  总股本:   {d['total_shares_yi']:.2f}亿股")
    print()

    _table(
        ["指标", "数值", "备注"],
        [
            ["PE", f"{d.get('pe', '—')}x", f"EPS={d.get('eps', '—')}元"],
            ["PB", f"{d.get('pb', '—')}x", f"BPS={d.get('bps', '—')}元"],
            ["ROE", f"{d.get('roe_pct', '—')}%", f"财年{d.get('fin_date', '—')}"],
            ["盈利收益率", f"{d.get('earnings_yield_pct', '—')}%", ""],
            ["股息率", f"{d.get('dividend_yield_pct', '—')}%", ""],
        ],
    )
    print()

    _table(
        ["经营指标", "数值"],
        [
            ["营收", _wan_to_yi(d.get('revenue_wan'))],
            ["归母净利润", _wan_to_yi(d.get('net_profit_wan'))],
            ["毛利率", f"{d.get('gross_margin_pct', '—')}%"],
            ["净利率", f"{d.get('net_margin_pct', '—')}%"],
            ["营收增速(YoY)", f"{d.get('rev_growth_pct', '—')}%"],
            ["利润增速(YoY)", f"{d.get('np_growth_pct', '—')}%"],
            ["资产负债率", f"{d.get('debt_ratio_pct', '—')}%"],
        ],
    )
    print()

    print(f"  总资产:   {_wan_to_yi(d.get('total_assets_wan'))}")
    print(f"  净资产:   {_wan_to_yi(d.get('net_assets_wan'))}")
    print(f"  总负债:   {_wan_to_yi(d.get('total_liabilities_wan'))}")
    print(f"  每股经营现金流: {d.get('op_cf_per_share', '—')} 元")
    print(f"  每股自由现金流: {d.get('fcf_per_share', '—')} 元")


def cmd_financials(args):
    """Multi-year financial statement comparison."""
    data = _run("financials", args.code)
    if isinstance(data, dict) and "error" in data:
        print(f"❌ {data['error']}")
        return

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    if not data or not isinstance(data, list):
        print("No financial data available.")
        return

    _sep(f"财务数据 — {args.code}")

    # Extract annual reports only (report_date ends in 1231)
    key_fields = [
        ("营业总收入(万元)", "营收(亿)"),
        ("近一年归母净利润（万元）", "归母净利(亿)"),
        ("基本每股收益", "EPS"),
        ("每股净资产", "BPS"),
        ("净资产收益率", "ROE(%)"),
        ("销售毛利率(%)(非金融类指标)", "毛利率(%)"),
        ("销售净利率(%)", "净利率(%)"),
        ("净利润增长率(%)", "利润增速(%)"),
    ]

    annual_rows = []
    for row in data:
        rd = str(row.get("report_date", ""))
        if not rd.endswith("1231"):
            continue
        year = rd[:4]
        vals = [year]
        for col, _ in key_fields:
            v = row.get(col)
            if v is not None:
                if "万元" in col:
                    vals.append(f"{float(v)/10000:.2f}")
                elif "%" in col or "率" in col:
                    vals.append(f"{float(v):.2f}")
                else:
                    vals.append(f"{float(v):.4f}")
            else:
                vals.append("—")
        annual_rows.append(vals)

    if annual_rows:
        headers = ["年份"] + [label for _, label in key_fields]
        _table(headers, annual_rows)
    else:
        print("  No annual reports found.")


def cmd_quote(args):
    """Quick quote snapshot from latest K-line."""
    data = _run("kline", args.code, "--limit", "1")
    if isinstance(data, dict) and "error" in data:
        print(f"❌ {data['error']}")
        return

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    if not data or not isinstance(data, list) or len(data) == 0:
        print("No K-line data available.")
        return

    row = data[0]
    _sep(f"行情快照 — {args.code}")
    print(f"  日期:  {row.get('date', '—')}")
    print(f"  开盘:  {row.get('open', '—')}")
    print(f"  最高:  {row.get('high', '—')}")
    print(f"  最低:  {row.get('low', '—')}")
    print(f"  收盘:  {row.get('close', '—')}")
    print(f"  成交量: {_fmt(row.get('vol', 0), '手')}")
    print(f"  成交额: {_fmt(row.get('amount', 0), '元')}")

    # Get valuation too
    val = _run("valuation", args.code)
    if isinstance(val, dict) and "error" not in val:
        print(f"\n  PE: {val.get('pe', '—')}x  |  PB: {val.get('pb', '—')}x  |  市值: {_fmt(val.get('market_cap_yi'), '元')}")


def cmd_kline(args):
    """Historical K-line data."""
    cli_args = [args.code]
    if args.start:
        cli_args.extend(["--start", args.start])
    if args.end:
        cli_args.extend(["--end", args.end])
    if args.limit:
        cli_args.extend(["--limit", str(args.limit)])
    if args.columns:
        cli_args.extend(["--columns", args.columns])

    data = _run("kline", *cli_args)
    if isinstance(data, dict) and "error" in data:
        print(f"❌ {data['error']}")
        return

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    if not data:
        print("No K-line data.")
        return

    _sep(f"K线 — {args.code}  ({len(data)} rows)")

    cols = ["date", "open", "high", "low", "close", "vol"]
    headers = ["日期", "开盘", "最高", "最低", "收盘", "成交量"]
    rows = []
    for row in data:
        vals = []
        for c in cols:
            v = row.get(c)
            if c == "date":
                vals.append(str(v))
            elif c == "vol":
                vals.append(_fmt(v, "手"))
            else:
                vals.append(f"{float(v):.2f}" if v else "—")
        rows.append(vals)
    _table(headers, rows[:20])
    if len(rows) > 20:
        print(f"  … 共 {len(rows)} 行, 显示前 20")


def cmd_search(args):
    """Search A-share symbols by code (TDX meta has no company names)."""
    keyword = args.keyword.strip().lower()
    clean = keyword.replace("sh", "").replace("sz", "").replace("bj", "")

    if clean.isdigit():
        # Exact code lookup first
        data = _run("symbol", keyword)
        if isinstance(data, dict) and "error" not in data and data.get("symbol"):
            data = [data]
        else:
            # Prefix match via search
            data = _run("search", clean, "--limit", str(args.limit or 50))
            if isinstance(data, dict) and "error" in data:
                data = []
    else:
        print(f"未找到匹配 '{keyword}' 的代码。")
        print("提示: tdx-chronos 元数据不含公司名称, 仅支持 6 位数字代码搜索。")
        print("      例如: python3 tools/tdx_data.py search 688248")
        return

    if isinstance(data, dict) and "error" in data:
        print(f"❌ {data['error']}")
        return

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    if not data:
        print(f"未找到匹配 '{keyword}' 的代码。")
        print("提示: 请使用 6 位数字代码搜索, 如 688248。")
        return

    _sep(f"搜索: '{keyword}' — {len(data)} 个结果")
    _table(
        ["代码", "市场", "上市日", "K线数"],
        [
            [
                r.get("symbol", ""),
                r.get("market", ""),
                str(r.get("first_listing_date", "")),
                str(r.get("record_count", "")),
            ]
            for r in data[:20]
        ],
    )
    if len(data) > 20:
        print(f"  … 共 {len(data)} 个, 显示前 20")


def cmd_health(args):
    """Data freshness and coverage check."""
    data = _run("health")
    if isinstance(data, dict) and "error" in data:
        print(f"❌ {data['error']}")
        return

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    _sep(f"tdx-chronos 数据健康 — {data.get('level', 'unknown')}")
    print(f"  总结: {data.get('summary', '—')}")
    print(f"  通过: {data.get('total_passed', 0)}/{data.get('total_checks', 0)}")
    print()

    checks = data.get("checks", [])
    _table(
        ["检查项", "状态", "详情"],
        [
            [c.get("name", ""), "✅" if c.get("passed") else "❌", c.get("detail", "")]
            for c in checks
        ],
    )

# ─── main ─────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="A股离线数据查询 — 基于 tdx-chronos 离线数据仓库",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 tools/tdx_data.py quote 688248          # 行情快照
  python3 tools/tdx_data.py valuation 688248       # 估值全貌
  python3 tools/tdx_data.py financials 688248      # 历年财报对比
  python3 tools/tdx_data.py kline 688248 --limit 5 # 最近 5 K线
  python3 tools/tdx_data.py search 南网            # 搜索股票
  python3 tools/tdx_data.py health                 # 数据健康检查
        """,
    )
    parser.add_argument("--json", action="store_true", help="JSON output (programmatic)")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("quote", help="行情快照 (最新K线)")
    p.add_argument("code")
    p.set_defaults(func=cmd_quote)

    p = sub.add_parser("valuation", help="估值全貌 (K线+财报)")
    p.add_argument("code")
    p.set_defaults(func=cmd_valuation)

    p = sub.add_parser("financials", help="历年财报对比")
    p.add_argument("code")
    p.set_defaults(func=cmd_financials)

    p = sub.add_parser("kline", help="历史日K线")
    p.add_argument("code")
    p.add_argument("--start", default=None, help="起始日期 YYYYMMDD")
    p.add_argument("--end", default=None, help="截止日期 YYYYMMDD")
    p.add_argument("--limit", type=int, default=None, help="显示最近N行")
    p.add_argument("--columns", default=None, help="列过滤 (逗号分隔)")
    p.set_defaults(func=cmd_kline)

    p = sub.add_parser("search", help="搜索股票代码/名称")
    p.add_argument("keyword")
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("health", help="数据健康检查")
    p.set_defaults(func=cmd_health)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
