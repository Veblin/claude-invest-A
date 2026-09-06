"""hk_kline / hk_financials / hk_valuation 映射单测（fixture 离线，不联网）。"""

from __future__ import annotations

import pytest

import hk_financials as fin
import hk_valuation as val


# ---- hk_financials：东财行 → 引擎键映射（2026-09-06 实测列）----

def test_financial_row_mapping_percent_and_currency():
    raw = {
        "REPORT_DATE": "2025-12-31 00:00:00",
        "OPERATE_INCOME": 751766000000,
        "OPERATE_INCOME_YOY": 0.1386,      # 东财给小数
        "HOLDER_PROFIT": 215000000000,
        "GROSS_PROFIT_RATIO": 0.5215,      # 小数 → 52.15
        "NET_PROFIT_RATIO": 28.6,          # 已是百分数
        "ROE_AVG": 0.2472,
        "BASIC_EPS": 24.749,
        "BPS": 126.786,
        "CURRENCY": "HKD",
    }
    row = fin._norm_row(raw)
    assert row["report_date"] == "2025-12-31"
    assert row["revenue"] == 751766000000
    assert row["gross_margin"] == pytest.approx(52.15)
    assert row["net_margin"] == pytest.approx(28.6)      # >1 不放大
    assert row["roe"] == pytest.approx(24.72)
    assert row["currency"] == "HKD"


def test_financial_rows_sorted_desc_and_cny_flagged():
    rows = [
        {"REPORT_DATE": "2025-12-31 00:00:00", "HOLDER_PROFIT": 1, "CURRENCY": "HKD"},
        {"REPORT_DATE": "2024-12-31 00:00:00", "HOLDER_PROFIT": 2, "CURRENCY": "HKD"},
        {"REPORT_DATE": "2026-06-30 00:00:00", "HOLDER_PROFIT": 3, "CURRENCY": "CNY"},
    ]
    out = sorted((fin._norm_row(r) for r in rows), key=lambda r: r["report_date"], reverse=True)
    assert out[0]["report_date"] == "2026-06-30" and out[0]["currency"] == "CNY"
    assert out[2]["report_date"] == "2024-12-31"


# ---- hk_valuation：分位/中位（复用 skills/lib/stats）----

def _mk_series(vals, start="2021-01-01"):
    return [{"date": f"{start[:4]}-{(i // 28) + 1:02d}-01", "value": v}
            for i, v in enumerate(vals)]


def test_percentile_position_uses_positive_only():
    s = _mk_series([10, 20, 30, 40, 50, -5, 60])
    out = val.percentile_position(s, cur=25.0)
    assert out["median"] == pytest.approx(35.0)     # 正数中位（30/40 中值）
    # percentile_rank 输出 0-100（与 A 股引擎分位口径一致：25 在 [10,20,30,40,50,60] → 33.3）
    assert out["pct"] == pytest.approx(100 * 2 / 6, abs=0.5)
    assert out["n"] == 7
    assert "滞后" in out["note"]


def test_percentile_negative_current_position_only():
    s = _mk_series([10, 20, 30])
    out = val.percentile_position(s, cur=-3.0)
    assert out["pct"] is None and "位置参考" in out["note"]


def test_percentile_empty_series():
    out = val.percentile_position([], cur=10.0)
    assert out["n"] == 0 and out["median"] is None
