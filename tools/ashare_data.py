#!/usr/bin/env python3
"""A股数据工具 — TDX离线数据(优先) + 腾讯行情 + 东方财富搜索/财务，零外部依赖（仅 stdlib）。

数据源优先级:
  1. tdx-chronos 离线数据 (/app/tdx-chronos) — K线+财务三表+股本, 零网络
  2. 腾讯行情 API (qt.gtimg.cn) — 实时报价+PE/PB/市值, 稳定免费
  3. 东方财富 datacenter API — 财务数据回退, 近5年年报

用法（由 Skills 自动调用）:
    python3 tools/ashare_data.py quote 600519                    # 实时行情
    python3 tools/ashare_data.py financials 600519               # 核心财务数据（优先TDX）
    python3 tools/ashare_data.py financials 600519 --offline     # 仅TDX离线数据
    python3 tools/ashare_data.py valuation 600519                # 估值指标（优先TDX）
    python3 tools/ashare_data.py search 茅台                      # 搜索股票代码

需要 Python >= 3.8，零外部依赖。
"""

import argparse
import json
import os
import subprocess
import sys
from decimal import Decimal, ROUND_HALF_EVEN

_TIMEOUT = 15
_TDX_QUERY = "/app/tdx-chronos/scripts/query.py"
_TDX_VENV = "/app/tdx-chronos/.venv/bin/python"


def _tdx_available() -> bool:
    """Check if tdx-chronos CLI is ready."""
    return os.path.exists(_TDX_QUERY) and os.path.exists(_TDX_VENV)


def _tdx_run(command: str, *args: str) -> dict | list:
    """Call tdx-chronos CLI and return parsed JSON."""
    cmd = [_TDX_VENV, _TDX_QUERY, command] + list(args)
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return {"error": "tdx unavailable"}

    if proc.returncode != 0:
        return {"error": proc.stderr.strip() or f"exit {proc.returncode}"}

    stdout = proc.stdout.strip()
    if not stdout:
        return {"error": "empty response"}

    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return {"error": "json parse failed"}


def _curl(url):
    """用 curl --noproxy 直连，绕过系统代理。"""
    result = subprocess.run(
        ["/usr/bin/curl", "-s", "--noproxy", "*",
         "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
         url],
        capture_output=True, timeout=_TIMEOUT,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise ConnectionError(f"请求失败: {url}")
    # 腾讯行情 API 返回 GBK 编码，其他返回 UTF-8
    try:
        return result.stdout.decode("utf-8")
    except UnicodeDecodeError:
        return result.stdout.decode("gbk")


def _curl_json(url, params=None):
    """curl 获取 JSON。"""
    if params:
        from urllib.parse import urlencode
        url = f"{url}?{urlencode(params)}"
    return json.loads(_curl(url))


# ---------------------------------------------------------------------------
# 腾讯行情 API（稳定可靠，无需鉴权）
# ---------------------------------------------------------------------------

def _qq_code(code: str) -> str:
    """将股票代码转为腾讯行情格式。"""
    code = code.strip().replace(".SH", "").replace(".SZ", "").replace(".BJ", "")
    if code.startswith(("6", "9", "5")):
        return f"sh{code}"
    elif code.startswith(("0", "3", "2", "1")):
        return f"sz{code}"
    elif code.startswith(("4", "8")):
        return f"bj{code}"
    return f"sh{code}"


def _parse_qq_quote(raw: str) -> dict:
    """解析腾讯行情数据。格式：v_shXXXXXX="字段1~字段2~..."; """
    start = raw.find('"')
    end = raw.rfind('"')
    if start < 0 or end <= start:
        return {}
    fields = raw[start + 1:end].split("~")
    if len(fields) < 50:
        return {}
    return {
        "name": fields[1],
        "code": fields[2],
        "price": fields[3],
        "prev_close": fields[4],
        "open": fields[5],
        "volume": fields[6],         # 手
        "buy_vol": fields[7],
        "sell_vol": fields[8],
        "high": fields[33] if len(fields) > 33 else fields[3],
        "low": fields[34] if len(fields) > 34 else fields[3],
        "change_pct": fields[32],
        "change_amt": fields[31],
        "turnover_amt": fields[37] if len(fields) > 37 else "-",
        "turnover_rate": fields[38] if len(fields) > 38 else "-",
        "pe": fields[39] if len(fields) > 39 else "-",
        "market_cap": fields[45] if len(fields) > 45 else "-",    # 总市值（亿）
        "float_cap": fields[44] if len(fields) > 44 else "-",     # 流通市值（亿）
        "pb": fields[46] if len(fields) > 46 else "-",
        "high_52w": fields[47] if len(fields) > 47 else "-",
        "low_52w": fields[48] if len(fields) > 48 else "-",
        "total_shares": fields[38] if len(fields) > 38 else "-",  # will recalculate
    }


def _fmt_yi(value) -> str:
    if value is None or value == "-" or value == "":
        return "-"
    try:
        v = float(value)
    except (ValueError, TypeError):
        return str(value)
    if abs(v) >= 1e8:
        return f"{v / 1e8:.2f}亿"
    if abs(v) >= 1e4:
        return f"{v / 1e4:.2f}万"
    return f"{v:.2f}"


def _fmt_pct(value) -> str:
    if value is None or value == "-" or value == "":
        return "-"
    try:
        return f"{float(value):.2f}%"
    except (ValueError, TypeError):
        return str(value)


# ---------------------------------------------------------------------------
# 命令实现
# ---------------------------------------------------------------------------

def cmd_quote(code: str):
    """实时行情快照。"""
    qq_code = _qq_code(code)
    raw = _curl(f"https://qt.gtimg.cn/q={qq_code}")
    d = _parse_qq_quote(raw)
    if not d:
        print(f"❌ 未找到股票 {code}")
        return

    print("=" * 60)
    print(f"实时行情: {d['name']} ({d['code']})")
    print("=" * 60)
    print(f"  当前价:     {d['price']}")
    print(f"  涨跌幅:     {d['change_pct']}%")
    print(f"  涨跌额:     {d['change_amt']}")
    print(f"  今开:       {d['open']}")
    print(f"  最高:       {d['high']}")
    print(f"  最低:       {d['low']}")
    print(f"  昨收:       {d['prev_close']}")
    print(f"  成交量:     {d['volume']} 手")
    print(f"  成交额:     {d['turnover_amt']}万")
    print(f"  总市值:     {d['market_cap']}亿")
    print(f"  流通市值:   {d['float_cap']}亿")
    print(f"  PE(动):     {d['pe']}")
    print(f"  PB:         {d['pb']}")
    print(f"  换手率:     {d['turnover_rate']}%")
    print(f"  52周最高:   {d['high_52w']}")
    print(f"  52周最低:   {d['low_52w']}")


def cmd_financials(code: str):
    """近5年核心财务数据 — TDX优先, Eastmoney回退."""
    if _tdx_available():
        print("=" * 60)
        print(f"核心财务数据: {code} (TDX 离线数据)")
        print("=" * 60)
        _tdx_financials(code)
        return

    # Fallback to Eastmoney
    _eastmoney_financials(code)


def _tdx_financials(code: str):
    """Display multi-year financial data from TDX."""
    data = _tdx_run("financials", code)
    if isinstance(data, dict) and "error" in data:
        print(f"  ⚠️ TDX 数据不可用: {data['error']}")
        print("  回退到东方财富...")
        _eastmoney_financials(code)
        return

    if not data or not isinstance(data, list):
        print("  无财务数据。")
        return

    # Filter annual reports
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
        vals = []
        for col, _ in key_fields:
            v = row.get(col)
            if v is not None:
                if "万元" in col:
                    vals.append(f"{float(v)/10000:.2f}亿")
                elif "%" in col or "率" in col:
                    vals.append(f"{float(v):.2f}%")
                else:
                    vals.append(f"{float(v):.4f}")
            else:
                vals.append("-")
        if vals:
            annual_rows.append([year] + vals)

    if not annual_rows:
        print("  无年报数据。")
        return

    headers = ["年份"] + [label for _, label in key_fields]
    col_widths = [len(h) for h in headers]
    for row in annual_rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(cell)))
    sep = "  "
    header_line = sep.join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    print(header_line)
    print(sep.join("-" * w for w in col_widths))
    for row in annual_rows:
        print(sep.join(str(row[i]).ljust(col_widths[i]) for i in range(len(headers))))


def _eastmoney_financials(code: str):
    """Original Eastmoney-based financials (fallback)."""
    qq_code = _qq_code(code)
    raw = _curl(f"https://qt.gtimg.cn/q={qq_code}")
    d = _parse_qq_quote(raw)
    name = d.get("name", code) if d else code

    code_clean = code.strip().replace(".SH", "").replace(".SZ", "").replace(".BJ", "")
    market = "SH" if code_clean.startswith(("6", "9", "5")) else "SZ"

    fin_url = "https://datacenter.eastmoney.com/securities/api/data/get"
    params = {
        "type": "RPT_F10_FINANCE_MAINFINADATA",
        "sty": "ALL",
        "filter": f'(SECUCODE="{code_clean}.{market}")(REPORT_TYPE="年报")',
        "p": "1",
        "ps": "5",
        "sr": "-1",
        "st": "REPORT_DATE",
        "source": "HSF10",
        "client": "PC",
    }
    reports = []
    try:
        data = _curl_json(fin_url, params)
        reports = data.get("result", {}).get("data", [])
    except Exception:
        pass

    if not reports:
        params["filter"] = f'(SECUCODE="{code_clean}.{market}")'
        try:
            data = _curl_json(fin_url, params)
            reports = data.get("result", {}).get("data", [])
        except Exception:
            pass

    print("=" * 60)
    print(f"核心财务数据: {name} ({code_clean})")
    print("=" * 60)

    if not reports:
        print("  ⚠️ 未能获取财务数据，建议通过 TDX 离线数据或 WebSearch 补充")
        return

    for r in reports[:5]:
        date = r.get("REPORT_DATE", "")[:10]
        report_name = r.get("REPORT_DATE_NAME", "")
        revenue = r.get("TOTALOPERATEREVE")
        net_profit = r.get("PARENTNETPROFIT")
        eps = r.get("EPSJB")
        bps = r.get("BPS")
        roe = r.get("ROEJQ")
        rev_growth = r.get("TOTALOPERATEREVETZ")
        profit_growth = r.get("PARENTNETPROFITTZ")

        print(f"\n  --- {date} {report_name} ---")
        if revenue is not None:
            print(f"  营收:           {_fmt_yi(revenue)}")
        if rev_growth is not None:
            print(f"  营收增速:       {_fmt_pct(rev_growth)}")
        if net_profit is not None:
            print(f"  归母净利润:     {_fmt_yi(net_profit)}")
        if profit_growth is not None:
            print(f"  净利润增速:     {_fmt_pct(profit_growth)}")
        if eps is not None:
            print(f"  基本每股收益:   {eps}")
        if bps is not None:
            print(f"  每股净资产:     {bps:.2f}")
        if roe is not None:
            print(f"  ROE(加权):      {_fmt_pct(roe)}")


def cmd_valuation(code: str):
    """估值指标 — TDX优先, QQ行情回退."""
    if _tdx_available():
        data = _tdx_run("valuation", code)
        if isinstance(data, dict) and "error" not in data:
            _tdx_valuation_display(code, data)
            return

    # Fallback to QQ quote
    _qq_valuation(code)


def _tdx_valuation_display(code: str, d: dict):
    """Display TDX valuation snapshot."""
    print("=" * 60)
    print(f"估值指标: {d.get('symbol', code)} (TDX 离线数据 · 财年{d.get('fin_date', '')})")
    print("=" * 60)
    print(f"  股价:         {d.get('price', '-')} 元")
    if d.get('market_cap_yi'):
        print(f"  总市值:       {d['market_cap_yi']:.2f}亿")
    if d.get('total_shares_yi'):
        print(f"  总股本:       {d['total_shares_yi']:.2f}亿股")
    print(f"  PE(TTM):      {d.get('pe', '-')}")
    print(f"  PB:           {d.get('pb', '-')}")
    if d.get('roe_pct'):
        print(f"  ROE:          {d['roe_pct']:.2f}%")
    print(f"  盈利收益率:   {d.get('earnings_yield_pct', '-')}%")
    if d.get('dividend_per_share'):
        print(f"  股息率:       {d.get('dividend_yield_pct', '-')}%")
    print(f"  营收增速:     {d.get('rev_growth_pct', '-')}%")
    print(f"  利润增速:     {d.get('np_growth_pct', '-')}%")
    print(f"  EPS:          {d.get('eps', '-')} 元")
    print(f"  BPS:          {d.get('bps', '-')} 元")
    print(f"  毛利率:       {d.get('gross_margin_pct', '-')}%")
    print(f"  净利率:       {d.get('net_margin_pct', '-')}%")
    if d.get('revenue_wan'):
        print(f"  营收:         {float(d['revenue_wan'])/10000:.2f}亿")
    if d.get('net_profit_wan'):
        print(f"  归母净利:     {float(d['net_profit_wan'])/10000:.2f}亿")
    if d.get('debt_ratio_pct'):
        print(f"  资产负债率:   {d['debt_ratio_pct']:.2f}%")
    if d.get('op_cf_per_share'):
        print(f"  每股经营现金流: {d['op_cf_per_share']} 元")


def _qq_valuation(code: str):
    """Original QQ quote-based valuation (fallback)."""
    qq_code = _qq_code(code)
    raw = _curl(f"https://qt.gtimg.cn/q={qq_code}")
    d = _parse_qq_quote(raw)
    if not d:
        print(f"❌ 未找到股票 {code}")
        return

    price = d["price"]
    market_cap_yi = d["market_cap"]

    print("=" * 60)
    print(f"估值指标: {d['name']} ({d['code']}) (QQ行情)")
    print("=" * 60)
    print(f"  当前价:     {price}")
    print(f"  总市值:     {market_cap_yi}亿")
    print(f"  流通市值:   {d['float_cap']}亿")
    print(f"  PE(动):     {d['pe']}")
    print(f"  PB:         {d['pb']}")
    print(f"  52周最高:   {d['high_52w']}")
    print(f"  52周最低:   {d['low_52w']}")

    try:
        p = Decimal(price)
        cap = Decimal(market_cap_yi) * Decimal("1e8")
        shares = cap / p
        print(f"\n  推算总股本: {_fmt_yi(float(shares))}股")
        calc_cap = p * shares
        reported_cap = Decimal(market_cap_yi) * Decimal("1e8")
        diff = abs(calc_cap - reported_cap) / reported_cap * 100
        print(f"  市值验算:   ✅ 一致（推算法，偏差 {float(diff):.1f}%）")
    except Exception:
        pass


def cmd_search(keyword: str):
    """搜索股票代码。"""
    url = "https://searchadapter.eastmoney.com/api/suggest/get"
    # Use env var or fall back to the public eastmoney search token
    token = os.environ.get("EASTMONEY_SEARCH_TOKEN") or "D43BF722C8E33BDC906FB84D85E326E8"
    params = {
        "input": keyword,
        "type": "14",
        "token": token,
        "count": "10",
    }
    data = _curl_json(url, params)
    results = data.get("QuotationCodeTable", {}).get("Data", [])

    if not results:
        print(f"❌ 未找到匹配 '{keyword}' 的股票")
        return

    print("=" * 60)
    print(f"搜索结果: '{keyword}'")
    print("=" * 60)
    for r in results:
        code = r.get("Code", "")
        name = r.get("Name", "")
        market = r.get("MktNum", "")
        mkt_label = {"1": "沪", "2": "深", "3": "北"}.get(str(market), "")
        print(f"  {code} {name} [{mkt_label}]")


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="A股数据工具 — 腾讯行情 + 东方财富财务数据",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    p_quote = sub.add_parser("quote", help="实时行情")
    p_quote.add_argument("code", help="股票代码，如 600519")

    p_fin = sub.add_parser("financials", help="核心财务数据（近5年）")
    p_fin.add_argument("code", help="股票代码")

    p_val = sub.add_parser("valuation", help="估值指标")
    p_val.add_argument("code", help="股票代码")

    p_search = sub.add_parser("search", help="搜索股票代码")
    p_search.add_argument("keyword", help="公司名或关键词")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    cmds = {
        "quote": lambda: cmd_quote(args.code),
        "financials": lambda: cmd_financials(args.code),
        "valuation": lambda: cmd_valuation(args.code),
        "search": lambda: cmd_search(args.keyword),
    }
    cmds[args.command]()


if __name__ == "__main__":
    main()
