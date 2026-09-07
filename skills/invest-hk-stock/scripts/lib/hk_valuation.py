"""港股估值历史（百度股市通序列，v0.2.9 港股数据引入 v1）。

`ak.stock_hk_valuation_baidu(symbol, indicator, period)` → {date, value} 日序列。
2026-09-06 实测：近一年 366 行；**最新值滞后约数日**（9/4-9/6 连续同值）——
分位/中位用序列计算时须显式标注"序列截至 {末日期}，最新快照见腾讯 r_hk"。
period 枚举：近一年/近三年/近五年/近十年/全部（分位窗口由调用方决定并标注）。

复用：skills/lib/stats 的 percentile/median（纯函数，与市场无关）。
"""
from __future__ import annotations

from typing import Any

from hk_codes import parse_hk_symbol


def fetch_valuation_series(sym: str, indicator: str = "市盈率(TTM)",
                           period: str = "近五年") -> list[dict[str, Any]]:
    """估值历史序列 → [{date, value}] 升序。失败 → []（调用方标注不可得）。"""
    import akshare as ak

    code = parse_hk_symbol(sym)
    try:
        df = ak.stock_hk_valuation_baidu(symbol=code, indicator=indicator, period=period)
    except Exception:
        return []
    rows = []
    for _, r in df.iterrows():
        try:
            rows.append({"date": str(r["date"])[:10], "value": float(r["value"])})
        except (TypeError, ValueError, KeyError):
            continue
    rows.sort(key=lambda r: r["date"])
    return rows


def percentile_position(series: list[dict[str, Any]], cur: float | None) -> dict[str, Any]:
    """序列分位 + 中位数（复用 skills/lib/stats 的 median/percentile_rank；A股同族口径）。

    返回 {pct, median, n, latest_value, latest_date, note}。序列空或全非正 → 仅标注。
    """
    from stats import median as _stats_median
    from stats import percentile_rank as _stats_pct_rank

    vals = [r["value"] for r in series]
    n = len(vals)
    out: dict[str, Any] = {
        "n": n,
        "latest_date": series[-1]["date"] if series else None,
        "latest_value": vals[-1] if vals else None,
    }
    if not series:
        out.update({"pct": None, "median": None, "note": "序列不可得"})
        return out
    pos = [v for v in vals if v is not None and v > 0]
    out["median"] = _stats_median(pos)
    if cur is None or cur <= 0 or not pos:
        out.update({"pct": None, "note": "仅作位置参考（非正或无当前值）"})
        return out
    pct = _stats_pct_rank(pos, cur)
    out["pct"] = round(pct, 4) if pct is not None else None
    out["note"] = f"窗口 {out['latest_date']} 前共 {n} 交易日（序列末值滞后，最新快照见 quote）"
    return out
