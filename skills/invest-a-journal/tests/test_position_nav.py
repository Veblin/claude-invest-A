"""P-2（v0.2.9）：journal show --portfolio 持仓位置导航参考（三隔离，纯状态）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_SKILL_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS = _SKILL_ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import journal  # noqa: E402


def _fake_entry(symbol: str = "300308", **over) -> dict:
    e = {
        "id": 1, "symbol": symbol, "direction": "buy", "asset_type": "stock",
        "driver": "AI 光模块景气", "hypothesis": "800G 放量",
        "wrong_conditions": "北美 capex 增速转负", "position_pct": 40,
        "entry_price": 150.0, "entry_date": "2025-06-01",
        "created_at": "2025-06-01 10:00",
    }
    e.update(over)
    return e


@pytest.fixture(autouse=True)
def _invest_a_lib(monkeypatch):
    from _invest_path import ensure_invest_a_scripts_on_path
    ensure_invest_a_scripts_on_path()
    monkeypatch.setattr(journal, "get_journal", lambda jid: _fake_entry())


def _patch_kline(close: float):
    from lib import collector as col
    return patch.object(col, "collect_kline", return_value={
        "dimension": "kline",
        "data": [{"trade_date": "2026-09-04", "close": close}],
        "status": "available",
    })


def test_show_with_portfolio_renders_nav(tmp_path, capsys):
    holdings = tmp_path / "h.json"
    holdings.write_text(json.dumps(
        [{"symbol": "300308", "weight": 0.4, "cost": 150.0, "buy_date": "2025-06-01"}],
        ensure_ascii=False,
    ), encoding="utf-8")
    with _patch_kline(135.0):
        rc = journal.cmd_show(1, portfolio=str(holdings))
    out = capsys.readouterr().out
    assert rc == 0
    assert "持仓位置导航参考" in out
    assert "导航参考" in out
    nav = out.split("持仓位置导航参考")[-1]
    assert "档位" in nav
    assert "浅亏" in nav            # 档位词渲染
    assert "150" not in nav         # 位置卡不渲染成本数值（正常 show 的入场价行除外）
    assert "135" not in nav         # 位置卡不渲染现价/盈亏数值
    assert "不构成任何操作建议" in nav


def test_show_symbol_not_in_holdings_skips_nav(tmp_path, monkeypatch, capsys):
    holdings = tmp_path / "h.json"
    holdings.write_text(json.dumps([{"symbol": "600176", "weight": 1.0}]), encoding="utf-8")
    rc = journal.cmd_show(1, portfolio=str(holdings))
    out = capsys.readouterr().out
    assert rc == 0
    assert "跳过位置导航参考" in out
    assert "=== 日志 #1 ===" in out    # 正常 show 输出不受影响
    assert "持仓位置导航参考（三隔离" not in out


def test_show_symbol_case_insensitive_match(tmp_path, monkeypatch, capsys):
    """journal DB 入库即 upper()；holdings 小写也应匹配（R4b 修复）。"""
    from unittest.mock import patch
    from lib import collector as col

    entry = _fake_entry(symbol="SH600176")   # db 侧规范化形态
    monkeypatch.setattr(journal, "get_journal", lambda jid: entry)
    holdings = tmp_path / "h.json"
    holdings.write_text(json.dumps([{"symbol": "sh600176", "weight": 1.0}]), encoding="utf-8")
    with patch.object(col, "collect_kline", return_value={
        "dimension": "kline", "data": [{"trade_date": "2026-09-04", "close": 20.0}],
        "status": "available",
    }):
        rc = journal.cmd_show(1, portfolio=str(holdings))
    out = capsys.readouterr().out
    assert rc == 0
    assert "持仓位置导航参考" in out
    assert "跳过位置导航参考" not in out


def test_show_broken_holdings_file_no_crash(tmp_path, capsys):
    missing = tmp_path / "nope.json"
    rc = journal.cmd_show(1, portfolio=str(missing))
    out = capsys.readouterr().out
    assert rc == 0
    assert "读取失败" in out


def test_parser_accepts_portfolio_flag():
    args = journal.build_parser().parse_args(["show", "1", "--portfolio", "x.json"])
    assert args.portfolio == "x.json"
