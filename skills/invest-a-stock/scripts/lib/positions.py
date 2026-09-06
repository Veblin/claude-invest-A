"""持仓位置状态卡（P-1，v0.2.9）。

隔离纪律（host-docs/v0.2.9/deep-research/00-research-summary-2026-09-06.md §2-P
+ p-domain-behavioral-foundations-2026-09-05.md §2/§6）：
- 本模块只产"状态"，不产任何判断/建议/动作文本；
- 成本是计算输入，**永不进入输出行**（输出只含档位标签与派生量）——
  成本字段的显著性本身就是处置效应放大器（Frydman & Wang 2020, JF）。
- 展示层（调用方）负责弱显著渲染；档位分界为常量，调整只改 POSITION_BANDS。
"""

from __future__ import annotations

import datetime as _dt
import math
from typing import Any


class PositionError(ValueError):
    """位置卡输入非法。"""


# 四档分界（纯位置描述，非建议触发阈值）：深亏 / 浅亏 / 浮盈 / 浮盈厚
POSITION_BANDS: dict[str, str] = {
    "deep_loss": "深亏",
    "loss": "浅亏",
    "gain": "浮盈",
    "gain_thick": "浮盈厚",
    "unknown": "位置不可判",
}
_LOSS_FLOOR = -0.20   # ≤ 此值 → deep_loss（含边界）
_GAIN_THICK = 0.30    # > 此值 → gain_thick


def band_for_pnl(pnl_pct: float | None) -> str:
    if pnl_pct is None or (isinstance(pnl_pct, float) and math.isnan(pnl_pct)):
        return "unknown"
    if pnl_pct <= _LOSS_FLOOR:
        return "deep_loss"
    if pnl_pct <= 0.0:
        return "loss"
    if pnl_pct <= _GAIN_THICK:
        return "gain"
    return "gain_thick"


def _days_between(a: str, b: str) -> int:
    try:
        d0 = _dt.date.fromisoformat(a)
        d1 = _dt.date.fromisoformat(b)
    except ValueError as exc:
        raise PositionError(f"日期须为 YYYY-MM-DD: {exc}") from exc
    return (d1 - d0).days


def build_position_row(*, symbol: str, price: float | None,
                       cost: float | None, buy_date: str | None,
                       today: str, name: str | None = None,
                       weight: float | None = None) -> dict[str, Any]:
    """单标的位置状态行。cost 仅作计算输入，不进输出。

    Returns keys: symbol, name, weight, pnl_pct, band, holding_days, note
    """
    if not symbol.strip():
        raise PositionError("symbol 为空")
    pnl_pct: float | None = None
    holding_days: int | None = None
    note: str | None = None
    # NaN 守卫（code-review max F4）：isnan(cost)<=0 恒 False 会穿透旧校验
    if isinstance(cost, float) and math.isnan(cost):
        raise PositionError(f"{symbol}: cost 为 NaN")
    if isinstance(price, float) and math.isnan(price):
        note = "现价为 NaN，仅能确认持仓事实"
        price = None
    if cost is None or price is None:
        note = note or "缺成本或现价，仅能确认持仓事实（无法判盈亏档位）"
    else:
        if cost <= 0:
            raise PositionError(f"{symbol}: cost 须为正数")
        if price <= 0:
            note = "现价非正，仅能确认持仓事实"
        else:
            pnl_pct = price / cost - 1.0
    if buy_date:
        holding_days = _days_between(buy_date, today)
        if holding_days is not None and holding_days < 0:
            note = "buy_date 晚于 today，请检查买入日期"
            holding_days = None
    return {
        "symbol": symbol,
        "name": name,
        "weight": weight,
        "pnl_pct": round(pnl_pct, 6) if pnl_pct is not None else None,
        "band": band_for_pnl(pnl_pct),
        "holding_days": holding_days,
        "note": note,
    }


def build_position_rows_from_holdings(holdings: list[dict], today: str | None = None) -> list[dict[str, Any]]:
    """holdings → 位置状态行。现价取最近收盘（K 线统一前复权，仅作位置参考）；
    不可得 → price=None（档位 unknown）。网络失败单标的降级，不阻塞整表。

    code-review max 修复：
    - today 默认上海历 shanghai_today()（本地钟 UTC+8 以西 00:00-08:00 差一天）
    - 仅对"有 cost 的行"按 symbol 去重拉取一次 K 线（无 cost 行档位恒 unknown，不拉网络）
    - 记录现价所属交易日，窗口内停牌（现价陈旧 >3 自然日）时 note 标注，防停牌价渲染笃定档位
    """
    from ._invest_path import ensure_skills_lib_on_path
    ensure_skills_lib_on_path()
    from data_bridge import get_kline  # noqa: E402
    from .shared_dates import shanghai_days_ago as _days_ago, shanghai_today

    today = today or shanghai_today()
    price_by_sym: dict[str, tuple[float | None, str | None]] = {}   # (price, price_date)
    fetch_syms = sorted({
        str(h.get("symbol", "")).strip()
        for h in holdings
        if str(h.get("symbol", "")).strip() and h.get("cost") is not None
    })
    for sym in fetch_syms:
        price, pdate = None, None
        try:
            kdim = get_kline(sym, start_date=_days_ago(10))
            data = kdim.get("data") if isinstance(kdim, dict) else None
            if isinstance(data, list) and data:
                last = max(data, key=lambda r: str(r.get("trade_date") or ""))
                pdate = str(last.get("trade_date") or "")
                raw = last.get("close")
                price = float(raw) if raw is not None else None
        except Exception:
            price = None
        price_by_sym[sym] = (price, pdate)

    rows: list[dict[str, Any]] = []
    for h in holdings:
        sym = str(h.get("symbol", "")).strip()
        if not sym:
            continue
        price, pdate = price_by_sym.get(sym, (None, None))
        row = build_position_row(
            symbol=sym, price=price, cost=h.get("cost"), buy_date=h.get("buy_date"),
            today=today, name=h.get("name"), weight=h.get("weight"),
        )
        if price is not None and pdate:
            try:
                stale_days = (_dt.date.fromisoformat(today) - _dt.date.fromisoformat(pdate)).days
            except ValueError:
                stale_days = 0
            if stale_days > 3:
                row["note"] = (row.get("note") or "").strip() + f"；现价截至 {pdate}（或停牌/数据陈旧）"
        rows.append(row)
    return rows


def _fmt_weight(raw: Any) -> str:
    """weight 渲染归一（code-review max F2）：支持 fraction(0.4)、'40%' 字符串、
    裸整数 40（百分比直觉写法，>1 按 /100 显示——不静默渲染 '4000%'）。解析失败 → '—'。"""
    if raw is None:
        return "—"
    if isinstance(raw, str):
        s = raw.strip()
        if s.endswith("%"):
            try:
                return f"{float(s[:-1].strip()) / 100:.0%}"
            except ValueError:
                return "—"
        try:
            raw = float(s)
        except ValueError:
            return "—"
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return "—"
    if math.isnan(raw):
        return "—"
    if raw > 1.0:
        return f"{raw / 100:.0%}"   # 40 → 40%（百分比单位直觉）
    return f"{raw:.0%}"


def position_table(rows: list[dict[str, Any]]) -> str:
    """渲染位置表（弱显著：档位中文 + 天数，不带盈亏数值与成本）。"""
    head = "| 标的 | 名称 | 档位 | 持有天数 | 持仓占比 | 备注 |"
    sep = "|---|---|---|---|---|---|"
    lines = [head, sep]
    for r in rows:
        w = _fmt_weight(r.get("weight"))
        days = f"{r['holding_days']} 天" if r["holding_days"] is not None else "—"
        lines.append(
            f"| {r['symbol']} | {r.get('name') or '—'} | "
            f"{POSITION_BANDS.get(r['band'], r['band'])} | {days} "
            f"| {w} | {r.get('note') or ''} |"
        )
    lines.append("")
    lines.append("*位置状态表仅描述持仓事实（档位/天数/占比），不构成任何操作建议。*")
    return "\n".join(lines)
