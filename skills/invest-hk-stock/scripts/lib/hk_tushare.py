"""tushare 港股源（hk_basic/hk_daily，v0.2.9 增补接入）。

2026-09-06 实测：账号已具备港股接口权限（hk_basic 2000 分档）；
**hk_daily 数据有 1-2 交易日延迟**（end_date=20260906 实测最新到 0902）——
作 K 线第二源/交叉校验用，实时性以腾讯 r_hk 为准。
"""
from __future__ import annotations

from typing import Any

from hk_codes import parse_hk_symbol


def _client():
    """共享 TushareClient（invest-a-stock lib，token 三级降级）。"""
    from _invest_path import ensure_invest_a_scripts_on_path
    ensure_invest_a_scripts_on_path()
    from lib.tushare_client import TushareClient
    return TushareClient()


def fetch_basic(sym: str) -> dict[str, Any]:
    """hk_basic 单标的（名称/全称/市场/上市日/币种/交易单位）。失败 → {}。"""
    code = parse_hk_symbol(sym)
    try:
        df = _client().query("hk_basic", ts_code=f"{code}.HK")
    except Exception:
        return {}
    if df is None or df.empty:
        return {}
    r = df.iloc[0]
    return {
        "ts_code": str(r.get("ts_code") or ""),
        "name": str(r.get("name") or ""),
        "market": str(r.get("market") or ""),
        "list_date": str(r.get("list_date") or ""),
        "currency": str(r.get("curr_type") or r.get("currency") or ""),
        "trade_unit": r.get("trade_unit"),
        "source": "tushare.hk_basic",
    }


def fetch_daily_kline(sym: str, start_date: str = "", end_date: str = "") -> list[dict[str, Any]]:
    """hk_daily 日 K（不复权原始价）→ [{trade_date, open, high, low, close, vol}] 降序。

    注：不复权价在除净日跳变——仅作交叉校验/原始价展示，不复权序列勿直接
    喂 technical 计算（qfq 请用腾讯源）。失败 → []。
    """
    code = parse_hk_symbol(sym)
    kwargs: dict[str, Any] = {"ts_code": f"{code}.HK"}
    if start_date:
        kwargs["start_date"] = start_date
    if end_date:
        kwargs["end_date"] = end_date
    try:
        df = _client().query("hk_daily", **kwargs)
    except Exception:
        return []
    if df is None or df.empty:
        return []
    rows = []
    for _, r in df.iterrows():
        try:
            rows.append({
                "trade_date": str(r["trade_date"]),
                "open": float(r["open"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "close": float(r["close"]),
                "vol": float(r["vol"]),
            })
        except (TypeError, ValueError, KeyError):
            continue
    rows.sort(key=lambda r: r["trade_date"], reverse=True)
    return rows
