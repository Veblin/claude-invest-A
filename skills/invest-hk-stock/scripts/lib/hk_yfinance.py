"""yfinance（Yahoo）港股源（v0.2.9 增补接入）。

2026-09-06 实测（0700.HK）：现价 442.8 与腾讯 r_hk 一致 ✓；priceToBook 3.00
（腾讯真实 PB——r_hk 无 PB 字段，[42]=1.76 与真实值不符已证伪）；dividendYield 1.2%；
trailingPE 14.90 vs r_hk 16.19/百度 14.87 存在口径差（GAAP EPS 含一次性 vs 东财口径）
——多源交叉时差异显式呈现，不自行裁决（LAW 5）。

**代理纪律**：Yahoo 为境外源——必须走代理（与东财/腾讯 DIRECT 方向相反）。
"""
from __future__ import annotations

from typing import Any

from hk_codes import parse_hk_symbol

# 港股 Yahoo 代码形态：00700 → 0700.HK（Yahoo 4 位补零——实测 "700.HK" 返回
# "Quote not found" 404，2026-09-06）
def _yahoo_sym(sym: str) -> str:
    code = parse_hk_symbol(sym)
    return f"{int(code):04d}.HK"


def fetch_info(sym: str) -> dict[str, Any]:
    """yfinance Ticker.info 关键字段（失败 → {}，调用方标注不可得）。

    注：yfinance 1.7.0 Ticker 构造不接受 timeout kwarg（曾致 TypeError 被吞 → 空）。
    """
    try:
        import yfinance as yf
    except ImportError:
        return {}
    try:
        t = yf.Ticker(_yahoo_sym(sym))
        info = t.info or {}
    except Exception:
        return {}
    out = {
        "name": info.get("shortName") or info.get("longName"),
        "price": info.get("currentPrice") or info.get("regularMarketPrice"),
        "pe_ttm": info.get("trailingPE"),
        "pb": info.get("priceToBook"),
        "div_yield_pct": info.get("dividendYield"),      # Yahoo 给小数（0.012 = 1.2%）
        "mcap": info.get("marketCap"),
        "high_52w": info.get("fiftyTwoWeekHigh"),
        "low_52w": info.get("fiftyTwoWeekLow"),
        "currency": info.get("currency"),
        "source": "yfinance.info",
    }
    out["div_yield_pct"] = _norm_div_yield(out.get("div_yield_pct"))
    return out


def _norm_div_yield(d) -> float | None:
    """dividendYield 归一（百分数单位直用）。yfinance 1.7 实测为百分数
    （0700=1.2、01211=0.48）；早年版本曾为小数（0.012）——单位漂移风险：
    >25% 判脏值丢弃（防 01211 旧归一 ×100 → 48% 类错误）。"""
    if d is None:
        return None
    try:
        f = float(d)
    except (TypeError, ValueError):
        return None
    return f if 0 < f <= 25 else None


def fetch_kline(sym: str, days: int = 250) -> list[dict[str, Any]]:
    """yfinance 历史日 K（复权 close=adjusted）——备用源；失败 → []。"""
    try:
        import yfinance as yf
    except ImportError:
        return []
    try:
        df = yf.Ticker(_yahoo_sym(sym)).history(period=f"{days}d")
    except Exception:
        return []
    if df is None or df.empty:
        return []
    rows = []
    for idx, r in df.iterrows():
        try:
            rows.append({
                "trade_date": str(idx.date()),
                "open": float(r["Open"]),
                "high": float(r["High"]),
                "low": float(r["Low"]),
                "close": float(r["Close"]),
                "vol": float(r["Volume"]),
            })
        except (TypeError, ValueError, KeyError):
            continue
    rows.sort(key=lambda r: r["trade_date"])
    return rows
