"""价格归因分解（V-1, v0.2.9）：(1+r_p) = (1+g_E)(1+g_M)，乘法恒等式精确成立。

口径依据：host-docs/v0.2.9/deep-research/v-domain-attribution-methodology-2026-09-05.md §3.2/§3.5
- 价格 = 总市值口径（不复权收盘 × 当时总股本）；宁德区间市值总涨跌 -47.7%
- 盈利 = 当时可见 TTM 归母净利（披露日判定）；文书 FY 口径为勘误历史记录
"""

from __future__ import annotations

import pytest

from lib.attribution import decompose_move, load_catl_fixture


def test_decompose_identity_exact():
    """文书历史数字（FY 159→441 亿、价格 -61%）仅作恒等式校验，不宣称现实口径。"""
    d = decompose_move(start_price_ratio=1.0, end_price_ratio=0.39,
                       start_eps=159.0, end_eps=441.0)
    assert d["g_earnings"] == pytest.approx(1.7736, abs=1e-3)
    # (1 + r_p) = (1+g_E)(1+g_M) 恒等——返回值为 6 位小数舍入，容差 1e-5；
    # 精确校验看 g_check（未舍入计算，残差 < 1e-9）
    assert (1 + d["g_price"]) == pytest.approx(
        (1 + d["g_earnings"]) * (1 + d["g_multiple"]), rel=1e-5)
    assert abs(d["g_check"]) < 1e-9


def test_decompose_no_move():
    d = decompose_move(start_price_ratio=1.0, end_price_ratio=1.0,
                       start_eps=1.0, end_eps=1.0)
    assert d["g_price"] == 0 and d["g_multiple"] == 0


def test_decompose_negative_earnings_rejected():
    d = decompose_move(start_price_ratio=1.0, end_price_ratio=0.5,
                       start_eps=-1.0, end_eps=2.0)
    assert "error" in d


def test_catl_fixture_canonical_band():
    """V-4：市值口径 canonical——调研 §3.2 可见 TTM 行（E: 99→443 亿，价格 -47.7%）。"""
    f = load_catl_fixture()
    d = decompose_move(
        start_price_ratio=1.0,
        end_price_ratio=f["end_mcap"] / f["start_mcap"],
        start_eps=f["start_np_ttm_visible"],
        end_eps=f["end_np_ttm_visible"],
    )
    assert d["g_price"] == pytest.approx(f["expected"]["g_price"], abs=0.005)
    assert d["g_earnings"] == pytest.approx(f["expected"]["g_earnings"], rel=0.01)
    assert -0.885 <= d["g_multiple"] <= -0.881   # 估值贡献 ≈ -88%（调研复核带）
    assert "-61%/-86%" in f["legacy_erratum"]     # 文书旧口径勘误记录在案


def test_catl_fy_caliber_matches_doc():
    """调研 §3.2 FY 行回归：159.31→441.21 亿 → 盈利 +177.0%、估值 -81.1%、价格 -47.7%。"""
    d = decompose_move(start_price_ratio=1.0, end_price_ratio=0.523,
                       start_eps=159.31, end_eps=441.21)
    assert d["g_earnings"] == pytest.approx(1.77, rel=0.002)
    assert d["g_multiple"] == pytest.approx(-0.811, abs=0.002)
