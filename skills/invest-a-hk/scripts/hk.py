#!/usr/bin/env python3
"""invest-a-hk CLI — 港股数据引入与初步分析（v0.2.9 v1；完整九模块功能归 0.3.0）。

子命令：
  diagnose               数据源连通性（腾讯 r_hk / 腾讯 K 线 / 东财财务 / 百度估值）
  snapshot SYMBOL        实时快照（腾讯 r_hk 字段，2026-09-06 实测定稿）
  report SYMBOL          初步分析报告（快照/估值分位/财务摘要/技术结构/港股风险层）

数据源：腾讯 qt.gtimg.cn（r_hk 快照 + ifzq fqkline K 线）｜东财 datacenter
（财务指标，需直连上下文）｜百度股市通（估值历史序列，末值滞后注记）。
币种纪律：一切价格/财务均为 HKD（报表用 CNY 的公司显式标注）。

运行：cd code && uv run python skills/invest-a-hk/scripts/hk.py <子命令> <代码>
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
_LIB = _THIS_DIR / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from _invest_path import ensure_invest_a_scripts_on_path, ensure_skills_lib_on_path  # noqa: E402

ensure_skills_lib_on_path()
ensure_invest_a_scripts_on_path()

import hk_codes  # noqa: E402
import hk_financials  # noqa: E402
import hk_kline  # noqa: E402
import hk_quote  # noqa: E402
import hk_valuation  # noqa: E402


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _snapshot_row(sym: str) -> dict:
    """腾讯 r_hk 快照；失败 → 返回含 error 的 dict（LAW 5 三态由渲染层处理）。"""
    try:
        q = hk_quote.fetch_quote(sym)
    except Exception as exc:  # 网络/解析失败——显式降级标注
        return {"error": f"腾讯快照不可得: {type(exc).__name__}"}
    return q


def _today() -> str:
    """港股与 A 股同处 UTC+8——复用共享 dates.shanghai_today（日历完整化归 0.3）。"""
    import datetime as _dt
    return _dt.date.today().isoformat()


# ---------------------------------------------------------------------------
# cmd_diagnose
# ---------------------------------------------------------------------------

def cmd_diagnose(args: argparse.Namespace) -> int:
    sym = args.symbol or "00700"
    print(f"# invest-a-hk diagnose — 数据源连通性（标的 {sym}）\n")
    ok = True

    try:
        q = hk_quote.fetch_quote(sym)
        print(f"✅ 腾讯 r_hk       {q.get('name')} 现价 {q.get('price')} HKD PE(TTM) {q.get('pe_ttm')}")
    except Exception as exc:
        ok = False
        print(f"❌ 腾讯 r_hk       {type(exc).__name__}: {exc}")

    try:
        k = hk_kline.fetch_kline(sym, days=30)
        n = len(k.get("data", []))
        print(f"✅ 腾讯 fqkline    {n} 行 K 线（qfq）" if n else "⚠️ 腾讯 fqkline    返回空")
        ok = ok and n > 0
    except Exception as exc:
        ok = False
        print(f"❌ 腾讯 fqkline    {type(exc).__name__}: {exc}")

    try:
        from lib.proxy import akshare_direct_session
        with akshare_direct_session():
            rows = hk_financials.fetch_financials(sym)
        print(f"✅ 东财财务        {len(rows)} 期（最新 {rows[0]['report_date'] if rows else '—'}）")
        ok = ok and bool(rows)
    except Exception as exc:
        ok = False
        print(f"❌ 东财财务        {type(exc).__name__}: {exc}")

    try:
        s = hk_valuation.fetch_valuation_series(sym, period="近一年")
        print(f"✅ 百度估值序列    {len(s)} 行（截至 {s[-1]['date'] if s else '—'}）")
        ok = ok and bool(s)
    except Exception as exc:
        ok = False
        print(f"❌ 百度估值序列    {type(exc).__name__}: {exc}")

    print(f"\n结论: {'全部连通 ✅' if ok else '部分不可得（详见上表，报告将三态标注）'}")
    print("\n注：东财 push2his 域（stock_hk_hist/spot_em）在当前网络环境不可达，v1 不依赖。")
    return 0 if ok else 1


# ---------------------------------------------------------------------------
# cmd_snapshot
# ---------------------------------------------------------------------------

def cmd_snapshot(args: argparse.Namespace) -> int:
    code = hk_codes.parse_hk_symbol(args.symbol)
    q = _snapshot_row(code)
    if "error" in q:
        print(q["error"])
        return 1
    print(f"# {q['name']} ({code}) — {q.get('ts', '')[:10]} 港股快照（币种 HKD）")
    print(f"- 现价 {q['price']}（昨收 {q['prev_close']}，{q['chg_pct']:+.2f}%）")
    print(f"- 区间 今 {q['low']}~{q['high']} | 52 周 {q['low_52w']}~{q['high_52w']}")
    print(f"- 成交额 {q['amount'] / 1e8:.1f} 亿 HKD（量 {q['volume'] / 1e6:.0f} 百万股）")
    print(f"- PE(TTM) {q['pe_ttm']} | 总市值 {q['mcap_hkd_yi']:.0f} 亿 HKD")
    print(f"[来源: tencent.r_hk qt.gtimg.cn/q=r_hk{code} / {q.get('ts')}]")
    return 0


# ---------------------------------------------------------------------------
# cmd_report（初步分析 v1）
# ---------------------------------------------------------------------------

_RSK = """
## 港股风险层（市场规则差异）
- 无涨跌停：单日波动无上限（唯一机制 VCM：大型股 ±10%/中型 ±15%/小型 ±20% 触发 5 分钟冷静期）
- 停牌风险：主板连续停牌 18 个月触发强制除牌（GEM 12 个月）
- 流动性：港股交投分化极大——日均成交额 ≥1 亿 HKD 为实务关注线（见快照成交额）
- 汇率：HKD 钉 USD（7.75–7.85）；人民币视角存在 USD/CNY 敞口
- 股息税：港股通 20%（红筹最高 28%）——股息率须标注税后口径
- 无业绩预告/季报制度：披露节奏 = 年报（年结后 3 个月内）+ 中报
"""


def cmd_report(args: argparse.Namespace) -> int:
    import datetime as _dt
    import json
    import os

    from lib.technical import compute as tech_compute

    code = hk_codes.parse_hk_symbol(args.symbol)
    lines: list[str] = []

    # --- 快照与多源一致性 ---
    q = _snapshot_row(code)
    if "error" in q:
        lines.append(f"# {code} 港股初步分析 — 快照不可得\n")
        lines.append(f"⚠️ {q['error']}（LAW 5：未获取到任何有效数据，无法判断）")
        _write_report(args, code, "数据不可得", "\n".join(lines))
        return 1
    lines.append(f"# {q['name']} ({code}) — {_today()} 港股初步分析（币种 HKD）\n")
    lines.append(f"**现价 {q['price']}（{q['chg_pct']:+.2f}%），52 周 {q['low_52w']}~{q['high_52w']}，"
                 f"PE(TTM) {q['pe_ttm']}，总市值 {q['mcap_hkd_yi']:.0f} 亿 HKD**")
    lines.append(f"[来源: tencent.r_hk / {q.get('ts')}]\n")

    # --- 财务摘要（东财，直连上下文） ---
    fin_rows: list[dict] = []
    try:
        from lib.proxy import akshare_direct_session
        with akshare_direct_session():
            fin_rows = hk_financials.fetch_financials(code)
    except Exception:
        fin_rows = []
    if fin_rows:
        cur = fin_rows[0].get("currency", "")
        lines.append("## 财务摘要（数值为东财港股财务接口原值）\n")
        lines.append("| 报告期 | 营收(亿) | 同比 | 归母净利(亿) | 同比 | 毛利率 | 净利率 | ROE | EPS |")
        lines.append("|---|---|---|---|---|---|---|---|---|")
        for i, r in enumerate(fin_rows[:4]):
            # YoY 自算（不信任东财 *_YOY 列——实测含异常占位值如 -99.4%）[来源: Python calc]
            rev_yoy = _self_yoy(fin_rows, i, "revenue")
            np_yoy = _self_yoy(fin_rows, i, "net_profit")
            lines.append(
                f"| {r['report_date']} | {_yi(r.get('revenue'))} | {_pct(rev_yoy)} | "
                f"{_yi(r.get('net_profit'))} | {_pct(np_yoy)} | "
                f"{_pct(r.get('gross_margin'))} | {_pct(r.get('net_margin'))} | "
                f"{_pct(r.get('roe'))} | {_fmt_num(r.get('eps'), 2)} |"
            )
        lines.append(f"\n*同比为引擎自算（本期/上年同期−1，[来源: Python calc]），非东财 YOY 列。*\n")
        lines.append(
            "> ⚠️ 币种核对：东财 CURRENCY 字段对部分 A+H 公司不可靠（比亚迪 H 实测："
            "数值为 CNY 报表值但字段标 HKD）。跨币种换算/对比前须以公司年报披露币种为准。\n"
        )
    else:
        lines.append("## 财务摘要\n数据不可得（东财财务接口不可达或标的无财务数据）——三态标注。\n")

    # --- 估值位置（百度序列 + 现价 PE 交叉） ---
    lines.append("## 估值位置（分位窗口=序列可得区间；港股口径注记）\n")
    try:
        pe_s = hk_valuation.fetch_valuation_series(code, "市盈率(TTM)", "近五年")
        pe_pos = hk_valuation.percentile_position(pe_s, q.get("pe_ttm"))
        pb_s = hk_valuation.fetch_valuation_series(code, "市净率", "近五年")
        pb_pos = hk_valuation.percentile_position(pb_s, None)  # PB 当前值腾讯无——仅序列中位
        if pe_pos["median"] is not None:
            lines.append(
                f"- **PE(TTM) {q['pe_ttm']}，序列分位 {pe_pos['pct']:.1f}%（中位 {pe_pos['median']:.1f}）**"
                if pe_pos["pct"] is not None else
                f"- PE(TTM) {q['pe_ttm']}（序列 {pe_pos['n']} 日，中位 {pe_pos['median']:.1f}；当前值口径与序列末值有差）"
            )
        if pb_pos["median"] is not None:
            lines.append(f"- PB 序列中位 {pb_pos['median']:.2f}（{pb_pos['n']} 日；当前 PB 见快照源交叉）")
        if pe_pos.get("note"):
            lines.append(f"- ⚠️ {pe_pos['note']}")
    except Exception as exc:
        lines.append(f"- 估值序列不可得: {type(exc).__name__}\n")
    lines.append("")

    # --- 技术结构（technical.compute 复用） ---
    try:
        k = hk_kline.fetch_kline(code, days=250)
        rows = k.get("data", [])
        if len(rows) >= 60:
            t = tech_compute(rows)
            ma = t["trend"]["ma"]
            def _ma_v(p):
                seq = ma.get(str(p), [])
                return seq[-1] if seq else None
            latest = t.get("latest_close")
            ma_vals = {p: _ma_v(p) for p in (5, 20, 60)}
            rel = " / ".join(f"MA{p}={v:.1f}" for p, v in ma_vals.items() if v)
            # 实测键位：MACD 在 momentum；RSI 在 overbought_oversold.rsi["12"].value
            macd = (t.get("momentum") or {}).get("macd") or {}
            rsi_box = t.get("overbought_oversold") or {}
            rsi12 = (rsi_box.get("rsi") or {}).get("12") or {}
            rsi = rsi12.get("value")
            lines.append("## 技术结构（状态描述，非交易信号）\n")
            lines.append(f"- 现价 {latest} vs {rel}")
            if macd.get("dif") is not None:
                lines.append(f"- MACD DIF {macd['dif']:.2f} / DEA {macd.get('dea')}")
            if rsi is not None:
                lines.append(f"- RSI(12) {rsi:.1f}（{rsi12.get('zone', '')}）")
            lines.append("")
        else:
            lines.append("## 技术结构\nK 线数据不足（<60 行）——标注不可得。\n")
    except Exception as exc:
        lines.append(f"## 技术结构\n计算失败: {type(exc).__name__}\n")

    lines.append(_RSK)
    lines.append("## 待验证项\n")
    lines.append("- 财务口径（HKFRS vs CAS）跨市场对比须折算与准则注记")
    lines.append("- 南向资金/CCASS 持仓/沽空数据：公开可查但 v0.2.9 未接入（0.3.0 范围）")
    lines.append("- 交易日历完整化（台风/圣诞休市）归 0.3.0；当前以自然日近似\n")
    lines.append("\n> ⚠️ 本报告由 invest-a-hk v0.2.9 自动生成，为初步数据引入分析（非九模块完整研究），")
    lines.append("> 不构成任何投资建议。数据来源见各行 [来源: ...]；币种 HKD（另注除外）。")

    body = "\n".join(lines)
    name = str(q.get("name") or code)
    path = _write_report(args, code, name, body)
    print(f"📝 报告: {path}\n")
    print(body[:4000])
    return 0


def _pct(v):
    if v is None:
        return "—"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "—"
    return f"{f:+.1f}%"


def _yi(v):
    """元 → 亿单位字符串（财务表显示，避免 15 位长数字）。"""
    if v is None:
        return "—"
    try:
        f = float(v) / 1e8
    except (TypeError, ValueError):
        return "—"
    return f"{f:,.1f}"


def _fmt_num(v, nd=2):
    if v is None:
        return "—"
    try:
        return f"{float(v):,.{nd}f}"
    except (TypeError, ValueError):
        return "—"


def _self_yoy(rows: list[dict], idx: int, key: str) -> float | None:
    """同比自算（本期/上年同期 −1）——不信任数据源 YOY 列的异常占位值。

    返回百分数单位（13.86 = +13.9%），与 _norm_row 的 gross_margin 等口径一致。
    """
    if idx + 1 >= len(rows):
        return None
    cur, prev = rows[idx].get(key), rows[idx + 1].get(key)
    if cur is None or prev is None:
        return None
    try:
        c, p = float(cur), float(prev)
    except (TypeError, ValueError):
        return None
    if p == 0:
        return None
    return (c / p - 1) * 100


def _write_report(args, code: str, name: str, body: str) -> Path:
    import datetime as _dt
    outdir = Path(args.outdir or (Path.cwd() / "reports"))
    sub = outdir / f"{code}-{name}"
    sub.mkdir(parents=True, exist_ok=True)
    ts = _dt.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    path = sub / f"{ts}.md"
    path.write_text(body, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="invest-a-hk — 港股数据引入与初步分析（v0.2.9 v1）")
    sub = p.add_subparsers(dest="command", required=True)

    pd = sub.add_parser("diagnose", help="数据源连通性诊断")
    pd.add_argument("symbol", nargs="?", default="00700", help="港股代码（默认 00700）")

    ps = sub.add_parser("snapshot", help="实时快照（腾讯 r_hk）")
    ps.add_argument("symbol")

    pr = sub.add_parser("report", help="初步分析报告（快照/估值/财务/技术/港股风险层）")
    pr.add_argument("symbol")
    pr.add_argument("--outdir", default="", help="报告输出目录（默认 code/reports）")
    return p


CMD_DISPATCH = {
    "diagnose": cmd_diagnose,
    "snapshot": cmd_snapshot,
    "report": cmd_report,
}


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command not in CMD_DISPATCH:
        print(f"未注册 CMD_DISPATCH 分发表: {args.command}", file=sys.stderr)
        return 1
    return CMD_DISPATCH[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
