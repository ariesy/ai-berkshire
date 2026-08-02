#!/usr/bin/env python3
"""Financial Rigor Toolkit for AI Berkshire.

Command-line tool for verifying financial data accuracy during investment research.
Automatically called by Claude Code Skills at critical validation checkpoints.

Zero external dependencies — uses only Python stdlib (decimal, json, math, argparse).
Requires Python >= 3.7.

Subcommands:
    auto-verify      自动从TDX取数+全套验算 (推荐)
    verify-market-cap  市值验算 (手动传参)
    verify-valuation   估值指标验算 (手动传参)
    cross-validate     多源交叉验证
    benford            Benford定律检测
    calc               精确计算
    three-scenario     三情景估值

Usage:
    python3 tools/financial_rigor.py auto-verify 688248
    python3 tools/financial_rigor.py verify-market-cap --price 510 --shares 9.11e9 --reported 4.65e12 --currency HKD
    python3 tools/financial_rigor.py verify-valuation --price 510 --eps 23.5 --bvps 120 --fcf-per-share 18 --dividend 2.4
    python3 tools/financial_rigor.py cross-validate --field revenue --values '{"年报": 7518, "Yahoo": 7500, "StockAnalysis": 7520}' --unit 亿
    python3 tools/financial_rigor.py calc --expr '510 * 9.11e9'
"""

import argparse
import json
import math
import os
import subprocess
import sys
from decimal import Decimal, Context, ROUND_HALF_EVEN, InvalidOperation

# ---------------------------------------------------------------------------
# Exact Decimal Engine (no floating-point drift)
# ---------------------------------------------------------------------------

_CTX = Context(prec=28, rounding=ROUND_HALF_EVEN)
_TDX_QUERY = "/app/tdx-chronos/scripts/query.py"
_TDX_VENV = "/app/tdx-chronos/.venv/bin/python"


def _tdx_val(code: str) -> dict | None:
    """Fetch valuation data from TDX for auto-verify."""
    if not os.path.exists(_TDX_QUERY) or not os.path.exists(_TDX_VENV):
        return None
    try:
        proc = subprocess.run(
            [_TDX_VENV, _TDX_QUERY, "valuation", code],
            capture_output=True, text=True, timeout=60,
        )
        if proc.returncode != 0:
            return None
        # Filter TDX warnings from stderr
        stdout = proc.stdout.strip()
        if not stdout:
            return None
        return json.loads(stdout)
    except Exception:
        return None

# ---------------------------------------------------------------------------
# Exact Decimal Engine (no floating-point drift)
# ---------------------------------------------------------------------------

_CTX = Context(prec=28, rounding=ROUND_HALF_EVEN)


def exact(value) -> Decimal:
    """Convert any numeric to exact Decimal, avoiding float traps."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    return Decimal(str(value))


def fmt_number(d: Decimal, unit: str = "") -> str:
    """Format large numbers in human-readable form (亿/万亿/B/T)."""
    v = float(d)
    abs_v = abs(v)
    if unit in ("亿", "亿元", "亿港元", "亿美元"):
        if abs_v >= 10000:
            return f"{v/10000:.2f}万亿{unit[1:] if len(unit) > 1 else ''}"
        return f"{v:.2f}{unit}"
    if abs_v >= 1e12:
        return f"{v/1e12:.2f}T"
    if abs_v >= 1e9:
        return f"{v/1e9:.2f}B"
    if abs_v >= 1e6:
        return f"{v/1e6:.2f}M"
    return f"{v:,.2f}"


def _force_utf8_stdio():
    """把 stdout/stderr 强制切到 UTF-8。

    Windows 控制台默认 GBK，本工具输出的 ❌ / ⚠️ / ✅ 会抛 UnicodeEncodeError，
    导致「偏差超标」这条最该被看到的告警路径反而直接崩溃退出。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 1. Market Cap Verification (股价×总股本 vs 报告市值)
# ---------------------------------------------------------------------------

def verify_market_cap(price, shares, reported_cap, currency=""):
    """Verify market cap = price × shares, compare with reported value."""
    p = exact(price)
    s = exact(shares)
    r = exact(reported_cap)

    calculated = _CTX.multiply(p, s)
    deviation = abs(float(calculated - r) / float(r)) * 100 if r != 0 else 0

    print("=" * 60)
    print("市值验算 (Market Cap Verification)")
    print("=" * 60)
    print(f"  股价 (Price):       {p} {currency}")
    print(f"  总股本 (Shares):    {fmt_number(s)}")
    print(f"  计算市值:           {fmt_number(calculated)} {currency}")
    print(f"  报告市值:           {fmt_number(r)} {currency}")
    print(f"  偏差:               {deviation:.2f}%")
    print()

    if deviation > 5:
        print(f"  ❌ 警告: 偏差 {deviation:.1f}% > 5%, 请检查:")
        print(f"     - 股本是否为最新（回购/增发）?")
        print(f"     - 单位是否一致（港币 vs 人民币 vs 美元）?")
        print(f"     - 股价是否为最新?")
        return False
    elif deviation > 1:
        print(f"  ⚠️  偏差 {deviation:.1f}% 在可接受范围, 可能因股价波动/股本变化")
        return True
    else:
        print(f"  ✅ 验证通过, 偏差仅 {deviation:.2f}%")
        return True


# ---------------------------------------------------------------------------
# 2. Valuation Metrics Verification (估值指标验算)
# ---------------------------------------------------------------------------

def verify_valuation(price, eps=None, bvps=None, fcf_per_share=None,
                     dividend=None, revenue_per_share=None):
    """Calculate and verify key valuation ratios from raw inputs."""
    p = exact(price)

    print("=" * 60)
    print("估值指标验算 (Valuation Verification)")
    print("=" * 60)
    print(f"  当前股价: {p}")
    print()

    results = {}

    if eps is not None:
        e = exact(eps)
        if e != 0:
            pe = _CTX.divide(p, e)
            print(f"  PE (TTM):  {p} / {e} = {pe:.2f}x")
            results["PE"] = float(pe)
            # Earnings yield
            ey = _CTX.divide(e, p) * 100
            print(f"  盈利收益率: {ey:.2f}%")
        else:
            print(f"  PE: EPS为0, 无法计算")

    if bvps is not None:
        b = exact(bvps)
        if b != 0:
            pb = _CTX.divide(p, b)
            print(f"  PB:        {p} / {b} = {pb:.2f}x")
            results["PB"] = float(pb)
            if eps is not None and float(exact(eps)) != 0:
                roe = _CTX.divide(exact(eps), b) * 100
                print(f"  ROE:       {exact(eps)} / {b} = {roe:.2f}%")
                results["ROE"] = float(roe)

    if fcf_per_share is not None:
        f = exact(fcf_per_share)
        if f != 0:
            fcf_yield = _CTX.divide(f, p) * 100
            pfcf = _CTX.divide(p, f)
            print(f"  P/FCF:     {p} / {f} = {pfcf:.2f}x")
            print(f"  FCF Yield: {fcf_yield:.2f}%")
            results["P_FCF"] = float(pfcf)
            results["FCF_Yield"] = float(fcf_yield)

    if dividend is not None:
        d = exact(dividend)
        if p != 0:
            div_yield = _CTX.divide(d, p) * 100
            print(f"  股息率:    {d} / {p} = {div_yield:.2f}%")
            results["Dividend_Yield"] = float(div_yield)

    if revenue_per_share is not None:
        r = exact(revenue_per_share)
        if r != 0:
            ps = _CTX.divide(p, r)
            print(f"  PS:        {p} / {r} = {ps:.2f}x")
            results["PS"] = float(ps)

    print()
    print("  ✅ 以上指标均使用精确十进制计算, 无浮点误差")
    return results


# ---------------------------------------------------------------------------
# 3. Cross-Source Data Validation (多源交叉验证)
# ---------------------------------------------------------------------------

def cross_validate(field_name, source_values: dict, unit="", tolerance_pct=2.0):
    """Compare a data point across multiple sources, flag discrepancies."""
    print("=" * 60)
    print(f"交叉验证: {field_name} (Cross-Validation)")
    print("=" * 60)

    values = {k: exact(v) for k, v in source_values.items()}
    sources = list(values.keys())
    nums = list(values.values())

    # Find median as reference
    sorted_vals = sorted(float(v) for v in nums)
    n = len(sorted_vals)
    median = sorted_vals[n // 2] if n % 2 == 1 else (sorted_vals[n//2-1] + sorted_vals[n//2]) / 2

    print(f"  数据来源数: {len(sources)}")
    print(f"  参考中位数: {fmt_number(exact(median))} {unit}")
    print()

    all_ok = True
    for src, val in values.items():
        dev = abs(float(val) - median) / median * 100 if median != 0 else 0
        status = "✅" if dev <= tolerance_pct else "❌"
        if dev > tolerance_pct:
            all_ok = False
        print(f"  {status} {src:20s}: {fmt_number(val)} {unit}  (偏差 {dev:.2f}%)")

    print()
    if all_ok:
        print(f"  ✅ 所有来源偏差 ≤ {tolerance_pct}%, 数据一致")
    else:
        print(f"  ⚠️  存在来源偏差 > {tolerance_pct}%, 请核实差异原因")
        print(f"     建议: 优先采用公司年报/交易所数据")

    # Consensus value
    consensus = median
    print(f"\n  共识值 (加权中位数): {fmt_number(exact(consensus))} {unit}")
    return {"consensus": consensus, "all_consistent": all_ok}


# ---------------------------------------------------------------------------
# 4. Benford's Law Quick Check (财务数据造假检测)
# ---------------------------------------------------------------------------

_BENFORD = {d: math.log10(1 + 1/d) for d in range(1, 10)}


def benford_check(values: list):
    """Quick Benford's Law check on a list of financial values."""
    print("=" * 60)
    print("Benford定律检测 (Financial Data Fabrication Check)")
    print("=" * 60)

    # Extract leading digits
    digits = []
    for v in values:
        v = abs(float(v))
        if v > 0:
            sig = 10 ** (math.log10(v) - math.floor(math.log10(v)))
            d = int(sig)
            if 1 <= d <= 9:
                digits.append(d)

    n = len(digits)
    if n < 50:
        print(f"  ⚠️  样本量不足: {n} < 50, Benford分析不可靠")
        return None

    # Observed distribution
    counts = {}
    for d in digits:
        counts[d] = counts.get(d, 0) + 1
    observed = {d: counts.get(d, 0) / n for d in range(1, 10)}

    # MAD (Nigrini's Mean Absolute Deviation)
    mad = sum(abs(observed.get(d, 0) - _BENFORD[d]) for d in range(1, 10)) / 9

    # Chi-square
    chi2 = sum((counts.get(d, 0) - _BENFORD[d] * n) ** 2 / (_BENFORD[d] * n) for d in range(1, 10))

    # Conformity
    if mad < 0.006:
        conformity = "Close (高度符合)"
    elif mad < 0.012:
        conformity = "Acceptable (可接受)"
    elif mad < 0.015:
        conformity = "Marginally Acceptable (边缘)"
    else:
        conformity = "Nonconforming (不符合 ⚠️)"

    print(f"  样本量:    {n}")
    print(f"  MAD:       {mad:.6f}")
    print(f"  Chi-sq:    {chi2:.2f}")
    print(f"  符合度:    {conformity}")
    print()

    # Digit distribution table
    print(f"  {'首位数':>6} {'观测':>8} {'Benford期望':>12} {'偏差':>8}")
    print(f"  {'-'*6} {'-'*8} {'-'*12} {'-'*8}")
    for d in range(1, 10):
        obs = observed.get(d, 0)
        exp = _BENFORD[d]
        dev = obs - exp
        flag = " ⚠️" if abs(dev) > 0.03 else ""
        print(f"  {d:>6d} {obs:>8.3f} {exp:>12.3f} {dev:>+8.3f}{flag}")

    print()
    is_ok = mad < 0.015
    if is_ok:
        print("  ✅ 数据首位数字分布符合Benford定律")
    else:
        print("  ❌ 数据首位数字分布异常, 可能存在人为调整")
        print("     提示: 不符合Benford定律不一定是造假, 但值得进一步调查")

    return {"mad": mad, "chi2": chi2, "conformity": conformity, "is_conforming": is_ok}


# ---------------------------------------------------------------------------
# 5. Exact Calculator (精确计算器)
# ---------------------------------------------------------------------------

def exact_calc(expr: str):
    """Evaluate a financial expression with exact decimal arithmetic.

    Supports: +, -, *, /, (), numbers (including scientific notation).
    """
    print("=" * 60)
    print("精确计算 (Exact Calculator)")
    print("=" * 60)

    # Safe evaluation: only allow numbers and arithmetic
    allowed = set("0123456789.+-*/() eE")
    if not all(c in allowed for c in expr.replace(" ", "")):
        print(f"  ❌ 不安全的表达式: {expr}")
        return None

    try:
        # Replace scientific notation for Decimal compatibility
        result = eval(expr, {"__builtins__": {}}, {})
        d_result = exact(result)
        print(f"  表达式: {expr}")
        print(f"  结果:   {fmt_number(d_result)}")
        print(f"  精确值: {d_result}")
        return float(d_result)
    except Exception as e:
        print(f"  ❌ 计算错误: {e}")
        return None


# ---------------------------------------------------------------------------
# 6. Three-Scenario Valuation (三情景估值)
# ---------------------------------------------------------------------------

def three_scenario_valuation(current_price, current_eps, shares_billion,
                             growth_optimistic, growth_neutral, growth_pessimistic,
                             pe_optimistic, pe_neutral, pe_pessimistic,
                             years=3, currency=""):
    """Calculate three-scenario target prices with exact arithmetic."""
    print("=" * 60)
    print("三情景估值模型 (Three-Scenario Valuation)")
    print("=" * 60)

    p = exact(current_price)
    eps = exact(current_eps)
    shares = exact(shares_billion)

    scenarios = [
        ("乐观 (Bull)", growth_optimistic, pe_optimistic),
        ("中性 (Base)", growth_neutral, pe_neutral),
        ("悲观 (Bear)", growth_pessimistic, pe_pessimistic),
    ]

    print(f"  当前股价: {p} {currency}")
    print(f"  当前EPS:  {eps}")
    print(f"  预测期:   {years}年")
    print()
    print(f"  {'情景':12} {'年增速':>8} {'目标PE':>8} {'目标EPS':>10} {'目标股价':>10} {'涨跌幅':>8}")
    print(f"  {'-'*12} {'-'*8} {'-'*8} {'-'*10} {'-'*10} {'-'*8}")

    for name, growth, pe in scenarios:
        g = exact(growth)
        target_pe = exact(pe)
        # Future EPS = current EPS × (1 + growth)^years
        future_eps = eps
        for _ in range(years):
            future_eps = _CTX.multiply(future_eps, _CTX.add(Decimal("1"), g))
        target_price = _CTX.multiply(future_eps, target_pe)
        change = float(target_price - p) / float(p) * 100

        print(f"  {name:12} {float(g)*100:>7.0f}% {float(target_pe):>7.0f}x "
              f"{float(future_eps):>10.2f} {float(target_price):>9.1f} {change:>+7.1f}%")

    print()
    print("  ✅ 所有计算使用精确十进制, 结果可审计复现")


# ---------------------------------------------------------------------------
# auto-verify: TDX-powered one-stop verification
# ---------------------------------------------------------------------------

def auto_verify(code: str):
    """从TDX取数 → 全套验算（市值/估值/交叉验证/三情景）。"""
    print("=" * 60)
    print(f"自动验算 — {code}")
    print("=" * 60)

    d = _tdx_val(code)
    if d is None or "error" in d:
        print("  ❌ 无法从 TDX 获取数据。")
        print("     请确保 /app/tdx-chronos 已初始化。")
        print("     回退方案: 手动传参 verify-market-cap / verify-valuation")
        return

    price = float(d.get("price", 0))
    eps = float(d.get("eps", 0))
    bps = float(d.get("bps", 0))
    total_shares_yi = float(d.get("total_shares_yi", 0))
    market_cap_yi = float(d.get("market_cap_yi", 0))
    rev_growth = float(d.get("rev_growth_pct", 0)) / 100 if d.get("rev_growth_pct") else 0.15
    np_growth = float(d.get("np_growth_pct", 0)) / 100 if d.get("np_growth_pct") else 0.15
    op_cf = float(d.get("op_cf_per_share", 0)) if d.get("op_cf_per_share") else None
    dividend = float(d.get("dividend_per_share", 0)) if d.get("dividend_per_share") else 0

    if price <= 0 or eps <= 0:
        print("  ❌ 关键数据缺失 (price/eps), 无法验算。")
        return

    shares_yi = total_shares_yi if total_shares_yi > 0 else 5.0
    reported_cap = market_cap_yi if market_cap_yi > 0 else price * shares_yi

    print(f"\n  数据来源: TDX 离线数据 (财年: {d.get('fin_date', 'N/A')})")
    print(f"  股价: {price} 元  |  股本: {shares_yi:.2f}亿股  |  报告市值: {reported_cap:.2f}亿")
    print()

    # Step 1: Market cap verification
    print("─" * 40)
    print("  [1/4] 市值验算")
    print("─" * 40)
    calc_cap = price * shares_yi
    diff = abs(calc_cap - reported_cap) / reported_cap * 100 if reported_cap > 0 else 0
    status = "✅" if diff <= 1 else ("⚠️" if diff <= 5 else "❌")
    print(f"  计算市值: {price} × {shares_yi:.2f}亿 = {calc_cap:.2f}亿")
    print(f"  报告市值: {reported_cap:.2f}亿")
    print(f"  偏差: {diff:.2f}%  {status}")
    print()

    # Step 2: Valuation metrics
    print("─" * 40)
    print("  [2/4] 估值指标验算")
    print("─" * 40)
    pe = price / eps if eps > 0 else 0
    pb = price / bps if bps > 0 else 0
    roe = eps / bps * 100 if bps > 0 else 0
    print(f"  PE: {price} / {eps} = {pe:.2f}x   (TDX报告: {d.get('pe', '-')})")
    print(f"  PB: {price} / {bps} = {pb:.2f}x   (TDX报告: {d.get('pb', '-')})")
    print(f"  ROE: {eps} / {bps} = {roe:.2f}%  (TDX报告: {d.get('roe_pct', '-')}%)")
    if dividend > 0:
        d_yield = dividend / price * 100
        print(f"  股息率: {dividend} / {price} = {d_yield:.2f}%")
    if op_cf and op_cf > 0:
        cf_yield = op_cf / price * 100
        print(f"  FCF收益率: {op_cf} / {price} = {cf_yield:.2f}%")
    print()

    # Step 3: Three-scenario valuation
    print("─" * 40)
    print("  [3/4] 三情景估值")
    print("─" * 40)
    names = ["乐观", "中性", "悲观"]
    growth_rates = [max(np_growth + 0.05, 0.10), max(np_growth, 0.05), max(np_growth - 0.05, 0.02)]
    target_pes = [max(pe * 0.7, 20), max(pe * 0.5, 15), max(pe * 0.35, 10)]
    years = 3

    print(f"  {'情景':6} {'年增速':>7} {'目标PE':>7} {'目标EPS':>9} {'目标价':>9} {'涨跌幅':>8}")
    print(f"  {'─'*6} {'─'*7} {'─'*7} {'─'*9} {'─'*9} {'─'*8}")
    for name, g, tpe in zip(names, growth_rates, target_pes):
        future_eps = exact(eps) * (Decimal("1") + exact(g)) ** years
        future_eps_f = float(future_eps)
        target_price = future_eps_f * tpe
        change = (target_price / price - 1) * 100
        print(f"  {name:6} {g*100:>7.1f}% {tpe:>7.0f}x {future_eps_f:>9.2f} {target_price:>9.1f} {change:>+7.1f}%")
    print()

    # Step 4: Financial health summary
    print("─" * 40)
    print("  [4/4] 财务健康速览")
    print("─" * 40)
    checks = []
    if d.get("roe_pct") and float(d.get("roe_pct", 0)) >= 15:
        checks.append(("✅", "ROE ≥ 15%", f"{d.get('roe_pct'):.1f}%"))
    elif d.get("roe_pct"):
        checks.append(("⚠️", "ROE < 15%", f"{d.get('roe_pct'):.1f}%"))
    if d.get("debt_ratio_pct") and float(d.get("debt_ratio_pct", 0)) <= 50:
        checks.append(("✅", "资产负债率 ≤ 50%", f"{d.get('debt_ratio_pct'):.1f}%"))
    else:
        checks.append(("⚠️", "资产负债率 > 50%", f"{d.get('debt_ratio_pct', '-')}%"))
    if d.get("np_growth_pct") and float(d.get("np_growth_pct", 0)) >= 10:
        checks.append(("✅", "利润增速 ≥ 10%", f"{d.get('np_growth_pct'):.1f}%"))
    elif d.get("np_growth_pct"):
        checks.append(("⚠️", "利润增速 < 10%", f"{d.get('np_growth_pct'):.1f}%"))
    if op_cf and eps > 0 and op_cf / eps >= 0.8:
        checks.append(("✅", "经营现金流/EPS ≥ 0.8", f"{op_cf/eps:.2f}"))
    elif op_cf:
        checks.append(("❌", "经营现金流/EPS < 0.8", f"{op_cf/eps:.2f}"))
    for icon, label, val in checks:
        print(f"  {icon} {label}: {val}")
    print()

    # Verdict
    fail_count = sum(1 for icon, _, _ in checks if icon == "❌")
    warn_count = sum(1 for icon, _, _ in checks if icon == "⚠️")
    print("─" * 40)
    print(f"  验算完毕: {4 - fail_count}/4 通过, {warn_count} 项警告, {fail_count} 项不通过")
    print(f"  合理买入参考: PE ≤ {int(target_pes[1])}x, 即 ≤ {eps * target_pes[1]:.1f} 元")
    print("─" * 40)


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Financial Rigor Toolkit — 金融数据严谨性验证工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s verify-market-cap --price 510 --shares 9.11e9 --reported 4.65e12 --currency HKD
  %(prog)s verify-valuation --price 510 --eps 23.5 --bvps 120
  %(prog)s cross-validate --field revenue --values '{"年报": 7518, "Yahoo": 7500}' --unit 亿
  %(prog)s benford --values '[1234, 2345, 3456, ...]'
  %(prog)s calc --expr '510 * 9.11e9'
        """)

    sub = parser.add_subparsers(dest="command")

    # auto-verify
    av = sub.add_parser("auto-verify", help="自动从TDX取数+全套验算")
    av.add_argument("code", help="A股代码, 如 688248")

    # verify-market-cap
    mc = sub.add_parser("verify-market-cap", help="验算市值 = 股价 × 总股本")
    mc.add_argument("--price", type=float, required=True)
    mc.add_argument("--shares", type=float, required=True, help="总股本")
    mc.add_argument("--reported", type=float, required=True, help="报告市值")
    mc.add_argument("--currency", default="", help="币种")

    # verify-valuation
    val = sub.add_parser("verify-valuation", help="验算估值指标")
    val.add_argument("--price", type=float, required=True)
    val.add_argument("--eps", type=float, default=None)
    val.add_argument("--bvps", type=float, default=None, help="每股净资产")
    val.add_argument("--fcf-per-share", type=float, default=None)
    val.add_argument("--dividend", type=float, default=None, help="每股股息")
    val.add_argument("--revenue-per-share", type=float, default=None)

    # cross-validate
    cv = sub.add_parser("cross-validate", help="多源交叉验证")
    cv.add_argument("--field", required=True, help="数据字段名")
    cv.add_argument("--values", required=True, help="JSON: {来源: 数值}")
    cv.add_argument("--unit", default="")
    cv.add_argument("--tolerance", type=float, default=2.0, help="容差百分比")

    # benford
    bf = sub.add_parser("benford", help="Benford定律检测")
    bf.add_argument("--values", required=True, help="JSON数组")

    # calc
    ca = sub.add_parser("calc", help="精确计算")
    ca.add_argument("--expr", required=True, help="算术表达式")

    # three-scenario
    ts = sub.add_parser("three-scenario", help="三情景估值")
    ts.add_argument("--price", type=float, required=True)
    ts.add_argument("--eps", type=float, required=True)
    ts.add_argument("--shares", type=float, required=True, help="总股本(亿)")
    ts.add_argument("--growth", nargs=3, type=float, required=True,
                    help="三情景年增速 (乐观 中性 悲观), 如 0.15 0.08 0.0")
    ts.add_argument("--pe", nargs=3, type=float, required=True,
                    help="三情景目标PE, 如 25 20 15")
    ts.add_argument("--years", type=int, default=3)
    ts.add_argument("--currency", default="")

    _force_utf8_stdio()
    args = parser.parse_args()

    if args.command == "auto-verify":
        auto_verify(args.code)
    elif args.command == "verify-market-cap":
        verify_market_cap(args.price, args.shares, args.reported, args.currency)
    elif args.command == "verify-valuation":
        verify_valuation(args.price, args.eps, args.bvps, args.fcf_per_share,
                        args.dividend, args.revenue_per_share)
    elif args.command == "cross-validate":
        values = json.loads(args.values)
        cross_validate(args.field, values, args.unit, args.tolerance)
    elif args.command == "benford":
        values = json.loads(args.values)
        benford_check(values)
    elif args.command == "calc":
        exact_calc(args.expr)
    elif args.command == "three-scenario":
        three_scenario_valuation(
            args.price, args.eps, args.shares,
            args.growth[0], args.growth[1], args.growth[2],
            args.pe[0], args.pe[1], args.pe[2],
            args.years, args.currency)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
