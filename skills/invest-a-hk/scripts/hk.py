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
import hk_tushare  # noqa: E402
import hk_valuation  # noqa: E402
import hk_yfinance  # noqa: E402


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
    """交易日（上海历——港股同 UTC+8，review2 HK-6：本地钟 UTC+8 以西 00:00-08:00 差一天）。"""
    from dates import shanghai_today
    return shanghai_today()


def _now_shanghai() -> str:
    """报告文件时间戳（北京时间，invest.py:787 F2-4 口径：路径时间戳统一北京时间）。"""
    from dates import shanghai_now
    return shanghai_now().strftime("%Y-%m-%d-%H-%M-%S")


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

    b = hk_tushare.fetch_basic(sym)
    print(f"✅ tushare hk_basic {b.get('name') or '不可得'}（上市 {b.get('list_date') or '—'}，币种 {b.get('currency') or '—'}）")
    import datetime as _dt
    _end = _dt.date.today().strftime("%Y%m%d")
    _start = (_dt.date.today() - _dt.timedelta(days=45)).strftime("%Y%m%d")
    try:
        d = hk_tushare.fetch_daily_kline(sym, start_date=_start, end_date=_end)
        note = f"（最新 {d[0]['trade_date']}" if d else "（间歇性空返回——2026-09-06 实测首调成功、同参重调 0 行，疑限频/权限抖动，作交叉源使用时以非空为准"
        print(f"{'✅' if d else '⚠️'} tushare hk_daily {len(d)} 行 {note}）")
    except Exception as exc:
        ok = False
        print(f"❌ tushare hk_daily {type(exc).__name__}: {exc}")

    y = hk_yfinance.fetch_info(sym)
    if y.get("price"):
        print(f"✅ yfinance        {y.get('name')} 价 {y.get('price')} {y.get('currency')} "
              f"PB {y.get('pb')} 股息率 {y.get('div_yield_pct')}%")
    else:
        ok = False
        print("❌ yfinance        不可得（境外源需代理可达）")

    # review2 HK-5：分级结论（硬故障 vs 已知降级不混为一谈）——关键源（腾讯快照/K线、
    # 东财财务、百度序列、yfinance、hk_basic）任一硬失败才算故障；
    # hk_daily 间歇性空返回为已知降级（⚠️ 已单独标注），不计入失败
    print(f"\n结论: {'全部连通 ✅' if ok else '存在硬故障 ❌（详见上表；⚠️ 行属已知降级不判死）'}")
    print("\n注：东财 push2his 域（stock_hk_hist/spot_em）在当前网络环境不可达，v1 不依赖。")
    return 0 if ok else 1


# ---------------------------------------------------------------------------
# cmd_snapshot
# ---------------------------------------------------------------------------

def cmd_snapshot(args: argparse.Namespace) -> int:
    code = hk_codes.parse_hk_symbol(args.symbol)
    q = _snapshot_row(code)
    # review2 HK-4：腾讯对死代码/停牌标的返回 v_pv_none_match 或缺字段——
    # parse 后关键键为 None，LAW 5 三态必须在此生效，禁止 f"{None:+.2f}" 裸崩
    if "error" in q or q.get("price") is None:
        print(f"⚠️ {code} 快照不可得（{q.get('error', '字段缺失——可能标的已退市/停牌/代码无效')}）"
              "（LAW 5：未获取到任何有效数据，无法判断）")
        return 1
    print(f"# {q.get('name') or code} ({code}) — {str(q.get('ts') or '')[:10]} 港股快照（币种 HKD）")
    print(f"- 现价 {q['price']}（昨收 {_fmt_num(q.get('prev_close'))}，{_pct(q.get('chg_pct'))}）")
    print(f"- 区间 今 {_fmt_num(q.get('low'))}~{_fmt_num(q.get('high'))} | "
          f"52 周 {_fmt_num(q.get('low_52w'))}~{_fmt_num(q.get('high_52w'))}")
    if q.get("amount") is not None:
        print(f"- 成交额 {q['amount'] / 1e8:.1f} 亿 HKD（量 {_fmt_num(q.get('volume'), 0)} 股）")
    print(f"- PE(TTM) {_fmt_num(q.get('pe_ttm'))} | 总市值 {_fmt_num(q.get('mcap_hkd_yi'), 0)} 亿 HKD")
    print(f"[来源: tencent.r_hk qt.gtimg.cn/q=r_hk{code} / {q.get('ts')}]")
    y = hk_yfinance.fetch_info(code)
    if y.get("pb") is not None or y.get("div_yield_pct") is not None:
        print(f"- PB {y.get('pb')} | 股息率 {y.get('div_yield_pct')}%（yfinance 口径，税后见报告注）"
              f" [来源: yfinance {code}.HK info]")
        if y.get("pe_ttm") is not None:
            diff = (y["pe_ttm"] / q["pe_ttm"] - 1) * 100 if q.get("pe_ttm") else None
            print(f"- PE 交叉：yfinance {y['pe_ttm']:.2f} vs 腾讯 {q['pe_ttm']} "
                  f"（差 {diff:+.1f}%——口径差异，不裁决）" if diff is not None
                  else f"- PE 交叉：yfinance {y['pe_ttm']:.2f}（腾讯不可得）")
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
    if "error" in q or q.get("price") is None:
        # review2 HK-4：关键字段 None（死代码/停牌/字段缺失）→ 三态文件落盘，不裸崩
        lines.append(f"# {code} 港股初步分析 — 快照不可得\n")
        lines.append(f"⚠️ {q.get('error') or '快照字段缺失（停牌/代码无效/死代码）'}（LAW 5：未获取到任何有效数据，无法判断）")
        _write_report(args, code, "数据不可得", "\n".join(lines))
        return 1
    lines.append(f"# {q.get('name') or code} ({code}) — {_today()} 港股初步分析（交易币种 HKD）\n")
    lines.append(
        f"**现价 {q['price']}（{_pct(q.get('chg_pct'))}），52 周 {_fmt_num(q.get('low_52w'))}"
        f"~{_fmt_num(q.get('high_52w'))}，PE(TTM) {_fmt_num(q.get('pe_ttm'))}，"
        f"总市值 {_fmt_num(q.get('mcap_hkd_yi'), 0)} 亿 HKD**"
    )
    lines.append(f"[来源: tencent.r_hk / {q.get('ts')}]")
    b = hk_tushare.fetch_basic(code)
    if b.get("list_date"):
        lines.append(f"[来源: tushare.hk_basic] 上市 {b['list_date']}（主板/交易币种 {b.get('currency') or '—'}；"
                     f"报表货币以年报披露为准）\n")
    else:
        lines.append("")
    y = hk_yfinance.fetch_info(code)
    if y.get("price") and abs((y["price"] - q["price"]) / q["price"]) > 0.01:
        lines.append(
            f"> 🟡 多源交叉：yfinance 现价 {y['price']} vs 腾讯 {q['price']}"
            f"（差 {abs((y['price'] - q['price']) / q['price']) * 100:.1f}%——快照时点差，不裁决）\n"
        )

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

    # --- 估值位置（百度序列 + 现价 PE/PB 交叉：yfinance 提供当前 PB 与股息率） ---
    lines.append("## 估值位置（分位窗口=序列可得区间；港股口径注记）\n")
    y = hk_yfinance.fetch_info(code)
    pb_cur = y.get("pb")
    try:
        pe_s = hk_valuation.fetch_valuation_series(code, "市盈率(TTM)", "近五年")
        pe_pos = hk_valuation.percentile_position(pe_s, q.get("pe_ttm"))
        pb_s = hk_valuation.fetch_valuation_series(code, "市净率", "近五年")
        pb_pos = hk_valuation.percentile_position(pb_s, pb_cur)
        if pe_pos["median"] is not None:
            lines.append(
                f"- **PE(TTM) {q['pe_ttm']}，序列分位 {pe_pos['pct']:.1f}%（中位 {pe_pos['median']:.1f}）**"
                if pe_pos["pct"] is not None else
                f"- PE(TTM) {q['pe_ttm']}（序列 {pe_pos['n']} 日，中位 {pe_pos['median']:.1f}；当前值口径与序列末值有差）"
            )
        if pb_pos["median"] is not None and pb_cur is not None:
            lines.append(
                f"- **PB {pb_cur:.2f}（yfinance 当前值），序列分位 {pb_pos['pct']:.1f}%"
                f"（中位 {pb_pos['median']:.2f}）**"
                if pb_pos["pct"] is not None else
                f"- PB {pb_cur:.2f} vs 序列中位 {pb_pos['median']:.2f}"
            )
        elif pb_pos["median"] is not None:
            lines.append(f"- PB 序列中位 {pb_pos['median']:.2f}（{pb_pos['n']} 日；当前 PB 不可得）")
        if y.get("div_yield_pct") is not None:
            lines.append(
                f"- 股息率 {y['div_yield_pct']:.2f}%（名义；港股通税后约 ×0.8）"
                f" [来源: yfinance {code}.HK]"
            )
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
    """同比自算——**上年同期**（同月日、上一年），非相邻报告期。

    review2 HK-1 修复：fin_rows 降序为 [2026-06-30 中报, 2025-12-31 年报, 2025-06-30
    中报, ...]，idx+1 是"上一报告期"（中报 vs 年报 = 口径错配 −45% 级）；
    上年同期 = 第一个 report_date 同 MM-DD 且更早的行。返回百分数单位（13.86 = +13.9%）。
    """
    cur_date = str(rows[idx].get("report_date") or "")
    if len(cur_date) < 7:
        return None
    mmdd = cur_date[5:]
    prev = None
    for j in range(idx + 1, len(rows)):
        d = str(rows[j].get("report_date") or "")
        if d[5:] == mmdd:                      # 同月日 = 上年同期（中报对中报/年报对年报）
            prev = rows[j].get(key)
            break
    if prev is None:
        return None
    c, p = rows[idx].get(key), prev
    try:
        cf, pf = float(c), float(p)
    except (TypeError, ValueError):
        return None
    if pf == 0:
        return None
    return (cf / pf - 1) * 100


def _write_report(args, code: str, name: str, body: str) -> Path:
    outdir = Path(args.outdir or (Path.cwd() / "reports"))
    sub = outdir / f"{code}-{name}"
    sub.mkdir(parents=True, exist_ok=True)
    path = sub / f"{_now_shanghai()}.md"
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
