"""价格归因分解（V-1，v0.2.9）。

口径（host-docs/v0.2.9/deep-research/v-domain-attribution-methodology §2/§3/§5.1）：
- 价格用总市值 = 不复权收盘 × 当时总股本（消除送转对"每股 × 总净利"的伪分解）
- 盈利用"当时可见 TTM 归母净利"（披露日判定）——端点口径差异可达 ±170pp，必须显式携带
- 恒等式：(1 + r_p) = (1 + g_E)(1 + g_M)；加法近似在宁德量级误差 -152pp，禁止用于结论
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "tests" / "fixtures" / "v0.2.9" / "catl_2021_2023_snapshot.json"
)


def decompose_move(*, start_price_ratio: float, end_price_ratio: float,
                   start_eps: float, end_eps: float) -> dict[str, Any]:
    """单段归因。price_ratio 用市值比（段内价格倍率）。返回 g_price/g_earnings/g_multiple。

    全部为小数（-0.48 = -48%）。校验行 g_check 使恒等式可机器验证。
    """
    # NaN/Infinity 守卫（code-review max F7）：NaN<=0 恒 False 曾穿透打印 "+nan%"
    import math
    for label, v in (("start_price_ratio", start_price_ratio), ("end_price_ratio", end_price_ratio),
                     ("start_eps", start_eps), ("end_eps", end_eps)):
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return {"error": f"{label} 含 NaN/Infinity，快照数据非法"}
    if start_eps <= 0 or end_eps <= 0:
        return {"error": "盈利须为正（亏损段归因无意义，不做 PE 负数分解）"}
    g_price = end_price_ratio / start_price_ratio - 1.0
    g_earnings = end_eps / start_eps - 1.0
    g_multiple = (1.0 + g_price) / (1.0 + g_earnings) - 1.0
    return {
        "g_price": round(g_price, 6),
        "g_earnings": round(g_earnings, 6),
        "g_multiple": round(g_multiple, 6),
        "g_check": round((1 + g_earnings) * (1 + g_multiple) - (1 + g_price), 12),
        "eps_note": "口径: 当时可见 TTM 归母净利（披露日判定）",
    }


def load_catl_fixture() -> dict[str, Any]:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))
