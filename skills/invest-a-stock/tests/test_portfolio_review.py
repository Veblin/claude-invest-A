"""Tests for lib.portfolio_review (v0.1.9 review fixes)."""

from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _isolate_data_bridge_cache(tmp_path, monkeypatch):
    """隔离 data_bridge 全局缓存（真实目录），避免污染测试。

    review_portfolio 经 data_bridge.get_* 获取数据；若真实缓存里已有
    该 symbol 的条目（如上次真实运行），mock 的 collector 不会生效。
    """
    from lib._invest_path import ensure_skills_lib_on_path
    ensure_skills_lib_on_path()

    import data_bridge
    from cache import DataCache

    monkeypatch.setattr(data_bridge, "_cache", DataCache(cache_dir=tmp_path / "cache"))


def _fake_kline(_sym, start_date=""):
    return {
        "data": [
            {
                "trade_date": f"2024{(i // 28) + 1:02d}{(i % 28) + 1:02d}",
                "close": 10.0 + i * 0.1,
            }
            for i in range(80)
        ]
    }


def _fake_basic(_sym):
    return {"data": {"industry": "制造业"}}


class TestPortfolioReview:
    def test_missing_symbol_no_keyerror(self):
        from lib import portfolio_review as pr
        import lib.collector as col

        holdings = [
            {"weight": 0.5},  # missing symbol — quietly skipped
            {"symbol": "600176", "weight": 0.5},
        ]
        with patch.object(col, "collect_basic_info", side_effect=_fake_basic), \
             patch.object(col, "collect_kline", side_effect=_fake_kline):
            result = pr.review_portfolio(holdings, stress=False)
        assert "disclaimer" in result
        # Empty-symbol holding is continue'd — must not appear in skipped_symbols
        skipped = result.get("skipped_symbols") or []
        assert "" not in skipped
        # Valid symbol with mocked kline should be reviewed, not skipped
        assert "600176" not in skipped
        # Only the valid symbol contributes to industry concentration
        conc = result["industry_concentration"]
        assert conc == [("制造业", 0.5)]


    def test_stress_weight_warning(self):
        from lib import portfolio_review as pr
        import lib.collector as col

        holdings = [
            {"symbol": "600176", "weight": 0.5},
            {"symbol": "000858", "weight": 0.3},
        ]
        with patch.object(col, "collect_basic_info", side_effect=_fake_basic), \
             patch.object(col, "collect_kline", side_effect=_fake_kline):
            result = pr.review_portfolio(holdings, stress=True)

        assert result.get("weight_warning")
        assert "偏离" in result["weight_warning"]
        assert result["stress"]["-10%"] == round(-0.10 * 0.8, 4)

    def test_industry_concentration(self):
        """行业集中度按权重降序排列."""
        from lib import portfolio_review as pr
        import lib.collector as col

        holdings = [
            {"symbol": "600176", "weight": 0.4},
            {"symbol": "000858", "weight": 0.35},
            {"symbol": "600519", "weight": 0.25},
        ]
        industries = {"600176": "建材", "000858": "食品饮料", "600519": "食品饮料"}

        def _basic(sym):
            return {"data": {"industry": industries.get(sym, "未知")}}

        with patch.object(col, "collect_basic_info", side_effect=_basic), \
             patch.object(col, "collect_kline", side_effect=_fake_kline):
            result = pr.review_portfolio(holdings, stress=False)

        conc = result["industry_concentration"]
        assert len(conc) >= 1
        # 食品饮料 应合并权重 0.35+0.25=0.6，排第一
        assert conc[0][0] == "食品饮料"
        assert conc[0][1] == 0.6

    def test_correlation_skipped_when_under_three(self):
        """持仓 < 3 只 → 相关性跳过."""
        from lib import portfolio_review as pr
        import lib.collector as col

        holdings = [
            {"symbol": "600176", "weight": 0.6},
            {"symbol": "000858", "weight": 0.4},
        ]
        with patch.object(col, "collect_basic_info", side_effect=_fake_basic), \
             patch.object(col, "collect_kline", side_effect=_fake_kline):
            result = pr.review_portfolio(holdings, stress=False)

        assert "skipped" in result["correlation"]
        assert "3" in result["correlation"]["skipped"]

    def test_correlation_matrix_with_three_symbols(self):
        """≥3 标的 → 输出相关性矩阵."""
        from lib import portfolio_review as pr
        import lib.collector as col

        holdings = [
            {"symbol": "600176", "weight": 0.4},
            {"symbol": "000858", "weight": 0.3},
            {"symbol": "600519", "weight": 0.3},
        ]
        with patch.object(col, "collect_basic_info", side_effect=_fake_basic), \
             patch.object(col, "collect_kline", side_effect=_fake_kline):
            result = pr.review_portfolio(holdings, stress=False)

        assert "matrix" in result["correlation"]
        matrix = result["correlation"]["matrix"]
        # 3×3 对称矩阵（review #4：符号须为 A 股 6 位码——假字母符号被非 A 股守卫跳过）
        assert len(matrix) == 3
        for sym in ("600176", "000858", "600519"):
            assert sym in matrix
            assert sym in matrix[sym]
            # 自相关应为 1.0（或接近）
            assert matrix[sym][sym] == 1.0

    def test_empty_holdings_no_crash(self):
        """空持仓列表不崩溃."""
        from lib import portfolio_review as pr

        result = pr.review_portfolio([], stress=False)
        assert result["industry_concentration"] == []
        assert result["correlation"]["skipped"] == "持仓 < 3 只，跳过相关性"

    def test_missing_weight_defaults_to_zero(self):
        """无 weight 字段 → 默认 0."""
        from lib import portfolio_review as pr
        import lib.collector as col

        holdings = [
            {"symbol": "600176"},  # no weight
            {"symbol": "000858", "weight": 0.3},
        ]
        with patch.object(col, "collect_basic_info", side_effect=_fake_basic), \
             patch.object(col, "collect_kline", side_effect=_fake_kline):
            result = pr.review_portfolio(holdings, stress=False)

        # 权重和=0.3，偏离 1.0 → 有 warning
        assert result.get("weight_warning")

    def test_stress_no_warning_when_normalized(self):
        """权重和 ≈ 1.0 → 无 weight_warning."""
        from lib import portfolio_review as pr
        import lib.collector as col

        holdings = [
            {"symbol": "A", "weight": 0.5},
            {"symbol": "B", "weight": 0.5},
        ]
        with patch.object(col, "collect_basic_info", side_effect=_fake_basic), \
             patch.object(col, "collect_kline", side_effect=_fake_kline):
            result = pr.review_portfolio(holdings, stress=True)

        assert result.get("weight_warning") is None
        assert result["stress"]["-10%"] == -0.1  # scale=1.0

    def test_hk_symbol_not_routed_to_a_share_data(self):
        """review #4：港股 5 位码不得喂 A 股 get_basic_info/get_kline（共享 codes
        zfill(6) 会静默路由成 000700）；权重仍计入，行业不纳入，符号列于
        skipped_non_a_symbols。"""
        from lib import portfolio_review as pr
        import lib.collector as col

        def _a_share_only_basic(sym):
            if sym == "00700":
                raise AssertionError("港股码不得进 A 股采集")
            return _fake_basic(sym)

        def _a_share_only_kline(sym, start_date=""):
            if sym == "00700":
                raise AssertionError("港股码不得进 A 股采集")
            return _fake_kline(sym)

        holdings = [
            {"symbol": "00700", "weight": 0.4},
            {"symbol": "600176", "weight": 0.6},
        ]
        with patch.object(col, "collect_basic_info", side_effect=_a_share_only_basic), \
             patch.object(col, "collect_kline", side_effect=_a_share_only_kline):
            result = pr.review_portfolio(holdings, stress=False)

        assert result["skipped_non_a_symbols"] == ["00700"]
        assert "600176" not in result["skipped_non_a_symbols"]
        # 行业集中度仅含 A 股符号
        assert result["industry_concentration"] == [("制造业", 0.6)]
        assert result["stress"] is None

    def test_disclaimer_present(self):
        """输出包含 LAW 6 免责声明."""
        from lib import portfolio_review as pr
        import lib.collector as col

        holdings = [{"symbol": "600176", "weight": 1.0}]
        with patch.object(col, "collect_basic_info", side_effect=_fake_basic), \
             patch.object(col, "collect_kline", side_effect=_fake_kline):
            result = pr.review_portfolio(holdings, stress=False)

        assert "不构成投资建议" in result["disclaimer"]

    def test_weight_percent_string_parsed(self):
        """weight='10%' → 解析为 0.1，无 weight_parse_warnings."""
        from lib import portfolio_review as pr
        import lib.collector as col

        holdings = [{"symbol": "600176", "weight": "10%"}]
        with patch.object(col, "collect_basic_info", side_effect=_fake_basic), \
             patch.object(col, "collect_kline", side_effect=_fake_kline):
            result = pr.review_portfolio(holdings, stress=False)

        assert result.get("weight_parse_warnings") is None
        conc = result["industry_concentration"]
        assert conc == [("制造业", 0.1)]

    def test_invalid_weight_emits_parse_warning(self):
        """weight='N/A' → weight_parse_warnings 含 symbol，权重按 0 计入."""
        from lib import portfolio_review as pr
        import lib.collector as col

        holdings = [
            {"symbol": "600176", "weight": "N/A"},
            {"symbol": "000858", "weight": 0.5},
        ]
        with patch.object(col, "collect_basic_info", side_effect=_fake_basic), \
             patch.object(col, "collect_kline", side_effect=_fake_kline):
            result = pr.review_portfolio(holdings, stress=False)

        warns = result.get("weight_parse_warnings") or []
        assert any("600176" in w and "无法解析" in w for w in warns)
        # N/A → 0；有效权重仅 0.5
        conc = dict(result["industry_concentration"])
        assert conc.get("制造业") == 0.5


class TestLoadHoldingsPositionFields:
    """P-1（v0.2.9）：load_holdings pass-through 宽容（review2 A-4 定稿）——
    纯风险评审/--stress 路径不消费 P-1 字段，旧文件必须可加载；
    P-1 语义校验职责在消费端 positions（见 test_positions.py TestReviewFixes）。"""

    def test_load_holdings_optional_position_fields(self, tmp_path):
        import json
        from lib import portfolio_review as pr

        p = tmp_path / "holdings.json"
        p.write_text(json.dumps([
            {"symbol": "300308", "weight": 0.4, "cost": 150.0, "buy_date": "2025-06-01"},
            {"symbol": "600176", "weight": 0.6},
        ]), encoding="utf-8")
        h = pr.load_holdings(p)
        assert h[0]["cost"] == 150.0 and h[0]["buy_date"] == "2025-06-01"
        assert "cost" not in h[1]  # 可选字段缺失不报错

    def test_load_holdings_tolerates_legacy_fields_and_empty_symbol(self, tmp_path):
        """BC 兼容：缺 symbol/多余字段/Excel 字符串 cost/旧日期格式全容忍——
        review_portfolio 消费端 continue 空 symbol；字符串 cost 仅 P-1 路径消费时降级。"""
        import json
        from lib import portfolio_review as pr

        p = tmp_path / "holdings.json"
        p.write_text(json.dumps([
            {"weight": 0.5},                                    # 缺 symbol（旧测试：quietly skipped）
            {"symbol": "600176", "weight": 0.5, "note": "legacy", "target": 99},
            {"symbol": "300308", "cost": "150.0"},              # Excel 导出字符串（review2 A-4）
            {"symbol": "000858", "weight": 0.2, "cost": -5},    # 非法 cost 也不拦（评审路径无涉）
        ]), encoding="utf-8")
        h = pr.load_holdings(p)
        assert len(h) == 4

    def test_load_holdings_still_requires_list_shape(self, tmp_path):
        """数组形态校验保留（非数组仍是文件级错误）。"""
        import json
        from lib import portfolio_review as pr

        p = tmp_path / "holdings.json"
        p.write_text(json.dumps({"symbol": "600176"}), encoding="utf-8")
        with pytest.raises(ValueError, match="须为"):
            pr.load_holdings(p)

    def test_load_holdings_rejects_non_dict_rows(self, tmp_path):
        """review #12：非 dict 行恢复 ValueError（pass-through 仅限字段宽容，不涵盖
        行项形态——消费端逐行 .get() 会对非 dict 行 AttributeError）。"""
        import json
        from lib import portfolio_review as pr

        p = tmp_path / "holdings.json"
        p.write_text(json.dumps([{"symbol": "600176"}, ["oops"]]), encoding="utf-8")
        with pytest.raises(ValueError, match="须为 dict"):
            pr.load_holdings(p)
