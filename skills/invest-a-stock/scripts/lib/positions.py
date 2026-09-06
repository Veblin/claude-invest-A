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
    if pnl_pct is None:
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
    if cost is None or price is None:
        note = "缺成本或现价，仅能确认持仓事实（无法判盈亏档位）"
    else:
        if cost <= 0:
            raise PositionError(f"{symbol}: cost 须为正数")
        if price <= 0:
            note = "现价非正，仅能确认持仓事实"
        else:
            pnl_pct = price / cost - 1.0
    if buy_date:
        holding_days = _days_between(buy_date, today)
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
    """
    from ._invest_path import ensure_skills_lib_on_path
    ensure_skills_lib_on_path()
    from data_bridge import get_kline  # noqa: E402
    from .shared_dates import shanghai_days_ago as _days_ago

    today = today or _dt.date.today().isoformat()
    rows: list[dict[str, Any]] = []
    for h in holdings:
        sym = str(h.get("symbol", "")).strip()
        if not sym:
            continue
        price = None
        try:
            kdim = get_kline(sym, start_date=_days_ago(10))
            data = kdim.get("data") if isinstance(kdim, dict) else None
            if isinstance(data, list) and data:
                last = max(data, key=lambda r: str(r.get("trade_date") or ""))
                raw = last.get("close")
                price = float(raw) if raw is not None else None
        except Exception:
            price = None
        rows.append(build_position_row(
            symbol=sym, price=price, cost=h.get("cost"), buy_date=h.get("buy_date"),
            today=today, name=h.get("name"), weight=h.get("weight"),
        ))
    return rows


def position_table(rows: list[dict[str, Any]]) -> str:
    """渲染位置表（弱显著：档位中文 + 天数，不带盈亏数值与成本）。"""
    head = "| 标的 | 名称 | 档位 | 持有天数 | 持仓占比 | 备注 |"
    sep = "|---|---|---|---|---|---|"
    lines = [head, sep]
    for r in rows:
        w = f"{r['weight']:.0%}" if r.get("weight") is not None else "—"
        days = f"{r['holding_days']} 天" if r["holding_days"] is not None else "—"
        lines.append(
            f"| {r['symbol']} | {r.get('name') or '—'} | "
            f"{POSITION_BANDS.get(r['band'], r['band'])} | {days} "
            f"| {w} | {r.get('note') or ''} |"
        )
    lines.append("")
    lines.append("*位置状态表仅描述持仓事实（档位/天数/占比），不构成任何操作建议。*")
    return "\n".join(lines)
