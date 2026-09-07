"""港股代码路由（v0.2.9 港股数据引入 v1）。

背景：A 股共享 `skills/lib/codes.py` 的 exchange_code 对 5 位港股码做 zfill(6)
（"00700" → "000700" → 误判 SZ 静默拉错标的）——本模块自建港股路由，
**不改共享 codes.py**（A 股引擎零风险）。

接受形态：`00700` / `00700.HK` / `hk00700` / `r_hk00700` → 归一 "00700"。
"""
from __future__ import annotations

import re

from typing import Any


class HkSymbolError(ValueError):
    """港股代码解析失败。"""


def parse_hk_symbol(raw: str) -> str:
    """归一港股代码为 5 位数字串（"00700"）。

    严格拒绝 A 股误入：6 位纯数字（600176）与 .SH/.SZ/.BJ 后缀显式报错——
    绝不静默截尾/补位（防 zfill 型错路由重演）。
    """
    if not raw or not isinstance(raw, str):
        raise HkSymbolError(f"港股代码为空或非法: {raw!r}")
    s = raw.strip().lower()
    s = re.sub(r"^r?_?hk", "", s)                      # 剥 hk/r_hk 前缀
    if s.endswith((".sh", ".sz", ".bj")):
        raise HkSymbolError(f"A 股代码 {raw!r} 不是港股（拒接，防错路由）")
    s = s.removesuffix(".hk")
    if not re.fullmatch(r"[0-9]+", s):
        raise HkSymbolError(f"港股代码含非数字字符: {raw!r}")
    if len(s) > 5:
        raise HkSymbolError(f"港股代码超过 5 位（疑 A 股 6 位码）: {raw!r}")
    return s.zfill(5)


def tencent_sym(sym: str) -> str:
    """腾讯行情代码（r_hk00700 / fqkline hk00700 均用 hk 前缀）。"""
    return f"hk{parse_hk_symbol(sym)}"


def em_secid(sym: str) -> str:
    """东财 secid（116.00700）。"""
    return f"116.{parse_hk_symbol(sym)}"


def tushare_ts_code(sym: str) -> str:
    """tushare ts_code（00700.HK）。"""
    return f"{parse_hk_symbol(sym)}.HK"


def exchange_code_hk(sym: str) -> dict[str, str]:
    """港股三格式映射（对齐 A 股 exchange_code 的 dict 形态）。"""
    s = parse_hk_symbol(sym)
    return {
        "canonical": s,
        "tencent": tencent_sym(s),
        "em": em_secid(s),
        "tushare": tushare_ts_code(s),
    }
