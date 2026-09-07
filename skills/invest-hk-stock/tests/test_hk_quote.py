"""hk_quote parser 单测——fixture 为 2026-09-06 实抓原文（离线）。"""

from __future__ import annotations

import pytest

from hk_codes import HkSymbolError
from hk_quote import parse_tencent_hk

# 2026-09-06 实测抓取（截取，保留全部下标位）
FIXTURE_00700 = 'v_r_hk00700="100~腾讯控股~00700~442.800~433.000~442.400~24025286.0~0~0~442.800~0~0~0~0~0~0~0~0~0~442.800~0~0~0~0~0~0~0~0~0~24025286.0~2026/09/04 16:08:06~9.800~2.26~447.600~440.000~442.800~24025286.0~10664922337.702~0~16.19~~0~0~1.76~40308.7654~40308.7654~TENCENT~1.20~677.700~411.000~1.12~-26.08~0~0~0~0~0~14.87~3.10~0.26~100~-25.42~-2.72~GP~20.41~11.00~-3.11~-7.52~-4.90~9103153877.00~9103153877.00~15.34~5.309~443.904~-25.85~HKD~1~50"'

FIXTURE_01211 = 'v_r_hk01211="100~比亚迪股份~01211~86.150~85.700~85.700~20988366.0~0~0~86.150~0~0~0~0~0~0~0~0~0~86.150~0~0~0~0~0~0~0~0~0~20988366.0~2026/09/04 16:08:04~0.450~0.53~86.900~85.400~86.150~20988366.0~1808162118.850~0~21.75~~0~0~0.48~3173.2491~7854.4657~BYD COMPANY~1.20~114.989~71.400~1.12~-10.74~0~0~0~0~0~6.11~3.86~0.26~100~-11.74~-1.28~GP~20.41~11.00~-3.11~-7.52~-4.90~3683400000.00~3683400000.00~13.51~5.019~85.319~-10.26~HKD~1~50"'


def test_parse_00700_fields():
    q = parse_tencent_hk(FIXTURE_00700)
    assert q["name"] == "腾讯控股" and q["code"] == "00700"
    assert q["price"] == pytest.approx(442.8)
    assert q["chg_pct"] == pytest.approx(2.26)
    assert q["pe_ttm"] == pytest.approx(16.19)
    assert q["mcap_hkd_yi"] == pytest.approx(40308.7654)   # 总市值亿 HKD
    assert q["high_52w"] == pytest.approx(677.7)
    assert q["low_52w"] == pytest.approx(411.0)
    assert q["currency"] == "HKD"


def test_parse_01211_self_consistent():
    """比亚迪 H：量×价 ≈ 额（单位自洽校验）→ 字段语义确认。"""
    q = parse_tencent_hk(FIXTURE_01211)
    assert q["name"] == "比亚迪股份"
    assert q["price"] == pytest.approx(86.15)
    assert q["pe_ttm"] == pytest.approx(21.75)
    # 量(股)×价 ≈ 成交额(元)：20988366 × 86.15 ≈ 1.808e9 ✓
    assert q["amount"] == pytest.approx(q["volume"] * q["price"], rel=0.03)
    # 52 周区间含现价
    assert q["low_52w"] <= q["price"] <= q["high_52w"]


def test_parse_missing_fields_become_none():
    q = parse_tencent_hk('v_r_hk00700="100~A~00700~10.0~9.5~9.8"')
    assert q["price"] == pytest.approx(10.0)
    assert q["pe_ttm"] is None and q["mcap_hkd_yi"] is None


def test_parse_malformed_raises():
    with pytest.raises(ValueError):
        parse_tencent_hk("not a quote")
