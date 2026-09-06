"""持仓位置状态（P-1, v0.2.9）——纯状态描述，零判断文本（隔离纪律）。

设计依据：host-docs/v0.2.9/deep-research/00-research-summary-2026-09-06.md §2-P
与 p-domain-behavioral-foundations-2026-09-05.md（成本显著性 = 偏差放大器）。
"""

from __future__ import annotations

import pytest

from lib.positions import POSITION_BANDS, PositionError, band_for_pnl, build_position_row


def test_band_for_pnl_thresholds():
    # 四档：深亏 ≤ -20% / 浅亏 (-20%, 0] / 浮盈 (0, +30%] / 浮盈厚 > +30%
    assert band_for_pnl(-0.25) == "deep_loss"
    assert band_for_pnl(-0.20) == "deep_loss"      # 边界含 -20%
    assert band_for_pnl(-0.05) == "loss"
    assert band_for_pnl(0.0) == "loss"
    assert band_for_pnl(0.15) == "gain"
    assert band_for_pnl(0.30) == "gain"
    assert band_for_pnl(0.45) == "gain_thick"
    assert band_for_pnl(None) == "unknown"


def test_band_labels_no_numeric_no_direction():
    # 隔离纪律：档位标签不含数值与方向词（无"建议/应/止损/卖/买"）
    assert POSITION_BANDS["gain_thick"] == "浮盈厚"
    assert POSITION_BANDS["deep_loss"] == "深亏"
    assert all(not any(ch.isdigit() for ch in label) for label in POSITION_BANDS.values())
    banned = ("建议", "应", "止损", "止盈", "跑", "卖", "买")
    assert all(not any(w in label for w in banned) for label in POSITION_BANDS.values())


def test_build_position_row():
    row = build_position_row(
        symbol="300308", price=135.0,
        cost=150.0, buy_date="2025-06-01", today="2026-09-06",
        name="中际旭创", weight=0.4,
    )
    assert row["symbol"] == "300308"
    assert row["name"] == "中际旭创"
    assert row["pnl_pct"] == pytest.approx(-0.10, abs=1e-6)   # 135/150 - 1
    assert row["band"] == "loss"                                # 浅亏档
    assert row["holding_days"] == pytest.approx(462, abs=2)     # 2025-06-01 → 2026-09-06
    assert row["weight"] == 0.4
    assert "cost" not in row  # 输出层不带原始成本，防渲染污染


def test_build_position_row_no_cost_uses_unknown_band():
    # 无成本（只有市值权重）时：位置状态降级为"位置不可判"，而非用现价冒充成本
    row = build_position_row(symbol="600176", price=20.0, cost=None,
                             buy_date=None, today="2026-09-06")
    assert row["band"] == "unknown" and row["pnl_pct"] is None


def test_invalid_dates_rejected():
    with pytest.raises(PositionError):
        build_position_row(symbol="x", price=1.0, cost=1.0,
                           buy_date="2025/06/01", today="2026-09-06")


def test_build_position_rows_from_holdings_with_kline(monkeypatch):
    from unittest.mock import patch
    from lib._invest_path import ensure_skills_lib_on_path
    ensure_skills_lib_on_path()
    from lib import collector as col
    from lib.positions import build_position_rows_from_holdings

    with patch.object(col, "collect_kline", return_value={
        "dimension": "kline", "data": [{"trade_date": "2026-09-04", "close": 135.0}],
        "status": "available",
    }):
        rows = build_position_rows_from_holdings(
            [{"symbol": "300308", "weight": 0.4, "cost": 150.0, "buy_date": "2025-06-01"}],
            today="2026-09-05",
        )
    assert rows[0]["band"] == "loss"
    assert rows[0]["pnl_pct"] == pytest.approx(-0.10, abs=1e-6)


def test_build_position_rows_kline_failure_degrades_to_unknown():
    from unittest.mock import patch
    from lib._invest_path import ensure_skills_lib_on_path
    ensure_skills_lib_on_path()
    from lib import collector as col
    from lib.positions import build_position_rows_from_holdings

    with patch.object(col, "collect_kline", side_effect=RuntimeError("net down")):
        rows = build_position_rows_from_holdings(
            [{"symbol": "600176", "weight": 0.5, "cost": 20.0, "buy_date": "2026-01-05"}],
            today="2026-09-05",
        )
    assert rows[0]["band"] == "unknown" and rows[0]["pnl_pct"] is None
    assert rows[0]["note"]
