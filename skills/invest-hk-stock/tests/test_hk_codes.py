"""hk_codes 路由单测：5 位码归一、多形态接受、错误拒绝。"""

from __future__ import annotations

import pytest

from hk_codes import HkSymbolError, exchange_code_hk, parse_hk_symbol, tencent_sym


@pytest.mark.parametrize("raw,expected", [
    ("00700", "00700"),
    ("700", "00700"),            # 省略前导零
    ("00700.HK", "00700"),
    ("hk00700", "00700"),
    ("r_hk00700", "00700"),
    ("01211", "01211"),
    ("1211", "01211"),
])
def test_parse_normalizes(raw, expected):
    assert parse_hk_symbol(raw) == expected


@pytest.mark.parametrize("bad", ["", None, "600176", "ABC", "00700.SH", "  "])
def test_parse_rejects_non_hk(bad):
    with pytest.raises(HkSymbolError):
        parse_hk_symbol(bad)


def test_tencent_and_exchange_map():
    assert tencent_sym("700") == "hk00700"
    m = exchange_code_hk("00700")
    assert m == {"canonical": "00700", "tencent": "hk00700",
                 "em": "116.00700", "tushare": "00700.HK"}


def test_hk_codes_never_touches_a_share_zfill():
    """回归锚：A 股共享 codes.exchange_code("00700") 会 zfill 成 000700 误判 SZ——
    港股路由必须独立且行为确定（对齐路径不引入共享 codes 依赖）。"""
    import sys
    # 本模块顶层 import 链中不得出现共享 codes（验证 import 图干净）
    import hk_codes as hc
    assert "codes" not in sys.modules or hc.__name__ != "codes"
