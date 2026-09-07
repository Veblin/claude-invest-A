"""港股日 K 线（腾讯 ifzq fqkline qfq，v0.2.9 港股数据引入 v1）。

2026-09-06 实测：`https://ifzq.gtimg.cn/appstock/app/fqkline/get?param=hk00700,day,,,N,qfq`
返回 JSON data.hk00700.day：每行 [date, open, close, high, low, volume, 复权注释对象]
（顺序实测：open→close→high→low；注释含 cqr 除权日/HGcontent 回购明细——可作事件线索）。

复权口径：腾讯 qfq 为累计因子乘法系（与引擎 A 股 tushare adj_factor 自算同族）；
东财 stock_hk_hist 的 qfq 为固定金额扣减（历史老股可能复权出负价）——v1 主用腾讯，
东财仅作 diagnose 探测。
"""
from __future__ import annotations

import json
from typing import Any

from hk_codes import parse_hk_symbol

FQKLINE_URL = "https://ifzq.gtimg.cn/appstock/app/fqkline/get"


def fetch_kline(sym: str, days: int = 250, timeout: float = 15.0) -> dict[str, Any]:
    """腾讯 qfq 日 K → data_bridge 同 shape：{dimension, data, status, source}。

    data 行：{trade_date, open, close, high, low, volume}（数字型，按 data_bridge 约定）
    """
    import requests
    code = parse_hk_symbol(sym)
    params = {"param": f"hk{code},day,,,{days},qfq"}
    resp = requests.get(FQKLINE_URL, params=params, timeout=timeout,
                        headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    payload = resp.json()
    node = ((payload.get("data") or {}).get(f"hk{code}") or {})
    rows_raw = node.get("day") or node.get("qfqday") or []
    rows = []
    for r in rows_raw:
        if not isinstance(r, list) or len(r) < 6:
            continue
        try:
            rows.append({
                "trade_date": str(r[0]),
                "open": float(r[1]),
                "close": float(r[2]),
                "high": float(r[3]),
                "low": float(r[4]),
                # 键名沿用 A 股 collector/technical 约定（compute 消费 r.get("vol")）
                "vol": float(r[5]),
            })
        except (TypeError, ValueError):
            continue
    if not rows:
        return {"dimension": "kline", "data": [], "status": "missing",
                "source": "tencent.fqkline"}
    # 升序（data_bridge 约定：technical 等消费方要求 asc）
    rows.sort(key=lambda r: r["trade_date"])
    return {"dimension": "kline", "data": rows, "status": "available",
            "source": "tencent.fqkline", "query_params": params}
