"""Portfolio risk characteristics (v0.1.9) — no rebalancing advice (LAW 6)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .nums import safe_float
from .positions import _a_share_symbol_ok
from .shared_dates import shanghai_days_ago as _days_ago


# P-1（v0.2.9）：holdings 可选位置字段（cost/buy_date 为位置卡输入；name/shares 为展示/计算辅助）
#
# 校验分层（code-review max 2026-09-06 两轮修复后定稿）：
# - load_holdings 为 pass-through 宽容加载（v0.1.9 语义）：纯风险评审/--stress 路径
#   不消费 P-1 字段，旧文件（字符串 cost/note 字段/缺 symbol 行）必须可加载——
#   Excel 导出的字符串 cost 曾让 `portfolio --stress` 整体崩溃（review2 A-4）
# - P-1 字段语义校验（类型/正数/非 NaN/Inf/真实日期）由**消费端 positions** 承担：
#   build_position_rows_from_holdings 逐行校验，非法行整行降级（note），不崩不静默


def load_holdings(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("holdings.json 须为 [{symbol, weight}, ...] 数组")
    for r in data:
        if not isinstance(r, dict):
            # review #12：pass-through 仅宽容字段，不涵盖行项形态——消费端逐行
            # .get() 会对非 dict 行 AttributeError，须在此以清晰 ValueError 拦截
            raise ValueError(f"holdings 项须为 dict，实为 {type(r).__name__}")
    return data


def _parse_portfolio_weight(raw: Any) -> tuple[float, str | None]:
    """Parse a holdings weight into a float fraction.

    Returns (weight, warning_note). warning_note is set when the raw value
    cannot be parsed and weight is degraded to 0.0.
    """
    if raw is None or raw == "":
        return 0.0, None
    parsed = safe_float(raw)
    if parsed is not None:
        return parsed, None
    if isinstance(raw, str) and raw.strip().endswith("%"):
        pct = safe_float(raw.strip()[:-1].strip())
        if pct is not None:
            return pct / 100.0, None
    return 0.0, f"无法解析 weight={raw!r}"


def _returns_from_kline(kline: list[dict]) -> list[tuple[str, float]]:
    from .technical import sort_kline_asc
    rows = sort_kline_asc(kline)
    out: list[tuple[str, float]] = []
    prev = None
    for r in rows:
        c = r.get("close")
        d = str(r.get("trade_date") or "")
        if c is None or not d:
            continue
        if prev is not None and prev > 0:
            out.append((d, float(c) / prev - 1))
        prev = float(c)
    return out


def review_portfolio(holdings: list[dict], *, stress: bool = False) -> dict[str, Any]:
    from ._invest_path import ensure_skills_lib_on_path
    ensure_skills_lib_on_path()
    from data_bridge import get_basic_info, get_kline  # noqa: E402

    industries: dict[str, float] = {}
    kline_by_sym: dict[str, dict[str, float]] = {}
    skipped: list[str] = []
    skipped_non_a: list[str] = []
    active_symbols: list[str] = []
    weights_by_sym: dict[str, float] = {}
    weight_parse_warnings: list[str] = []

    for h in holdings:
        sym = str(h.get("symbol", "")).strip()
        weight, w_note = _parse_portfolio_weight(h.get("weight", 0))
        if not sym:
            continue
        if w_note:
            weight_parse_warnings.append(f"{sym}: {w_note}")
        weights_by_sym[sym] = weight
        if not _a_share_symbol_ok(sym):
            # review #4（HK-3 同款防错路由，positions.py 语义唯一源）：港股 5 位码
            # （00700）经共享 codes zfill(6) 会被静默路由成 000700——非 A 股形态不进
            # A 股数据接口；权重仍计入（权重和/压力测试口径），行业/相关性不纳入
            skipped_non_a.append(sym)
            continue
        basic = get_basic_info(sym)
        data = basic.get("data") if isinstance(basic, dict) else {}
        industry = "未知"
        if isinstance(data, dict):
            industry = data.get("industry") or data.get("行业") or "未知"
        industries[industry] = industries.get(industry, 0) + weight

        kdim = get_kline(sym, start_date=_days_ago(150))
        kdata = kdim.get("data") if isinstance(kdim, dict) else None
        if not isinstance(kdata, list) or len(kdata) < 60:
            skipped.append(sym)
            continue
        active_symbols.append(sym)
        for d, ret in _returns_from_kline(kdata)[-120:]:
            kline_by_sym.setdefault(sym, {})[d] = ret

    # Industry concentration
    ind_table = sorted(industries.items(), key=lambda x: -x[1])

    # Correlation matrix (inner join dates) — only active_symbols
    corr: dict[str, Any] = {"skipped": "持仓 < 3 只，跳过相关性"}
    if len(active_symbols) >= 3:
        common_dates = None
        for sym in active_symbols:
            dates = set(kline_by_sym.get(sym, {}).keys())
            common_dates = dates if common_dates is None else common_dates & dates
        if common_dates and len(common_dates) >= 20:
            aligned = sorted(common_dates)[-120:]
            series = {
                sym: [kline_by_sym[sym][d] for d in aligned if d in kline_by_sym.get(sym, {})]
                for sym in active_symbols
            }
            corr = {"matrix": _corr_matrix(series), "n_days": len(aligned)}
        else:
            corr = {"error": "交集交易日不足"}

    # Weight sum over holdings that contributed (have symbol)
    w_sum = sum(weights_by_sym.values())
    weight_warning = None
    if weights_by_sym and abs(w_sum - 1.0) > 0.05:
        weight_warning = f"权重和={w_sum:.3f}，偏离 1.0 超过 5%"

    stress_result = None
    if stress:
        # beta≈1: portfolio moves with index; scale by w_sum if not normalized
        scale = w_sum if abs(w_sum - 1.0) > 0.05 else 1.0
        note = (
            "指数情景下组合市值估算变动（假设组合 beta≈1），非调仓建议"
            + ("；权重未归一，已按权重和缩放" if abs(w_sum - 1.0) > 0.05 else "")
        )
        stress_result = {
            "-10%": round(-0.10 * scale, 4),
            "-20%": round(-0.20 * scale, 4),
            "-30%": round(-0.30 * scale, 4),
            "note": note,
        }

    out: dict[str, Any] = {
        "industry_concentration": ind_table,
        "correlation": corr,
        "skipped_symbols": skipped,
        "skipped_non_a_symbols": skipped_non_a,
        "stress": stress_result,
        "disclaimer": "纯风险特征描述，不构成投资建议或调仓建议。",
    }
    if weight_parse_warnings:
        out["weight_parse_warnings"] = weight_parse_warnings
    if weight_warning:
        out["weight_warning"] = weight_warning
    return out




def _corr_matrix(series: dict[str, list[float]]) -> dict[str, dict[str, float | None]]:
    import statistics
    syms = list(series.keys())
    matrix: dict[str, dict[str, float | None]] = {}
    for a in syms:
        matrix[a] = {}
        for b in syms:
            sa, sb = series[a], series[b]
            n = min(len(sa), len(sb))
            if n < 12:
                matrix[a][b] = None
                continue
            ma, mb = statistics.mean(sa[:n]), statistics.mean(sb[:n])
            cov = sum((sa[i] - ma) * (sb[i] - mb) for i in range(n)) / (n - 1)
            va = sum((x - ma) ** 2 for x in sa[:n]) / (n - 1)
            vb = sum((x - mb) ** 2 for x in sb[:n]) / (n - 1)
            if va <= 0 or vb <= 0:
                matrix[a][b] = None
            else:
                matrix[a][b] = round(cov / (va ** 0.5 * vb ** 0.5), 3)
    return matrix


def format_portfolio_review(result: dict) -> str:
    lines = ["# 组合风险特征", ""]
    for note in result.get("weight_parse_warnings") or []:
        lines.append(f"⚠️ {note}")
    if result.get("weight_parse_warnings"):
        lines.append("")
    if result.get("weight_warning"):
        lines.append(f"⚠️ {result['weight_warning']}")
        lines.append("")
    lines.append("## 行业集中度（申万一级）")
    for ind, w in result.get("industry_concentration", []):
        lines.append(f"- {ind}: {w:.1%}")
    lines.append("")
    corr = result.get("correlation", {})
    if corr.get("matrix"):
        lines.append("## 持仓相关性矩阵（120日收益率）")
        for a, row in corr["matrix"].items():
            cells = ", ".join(f"{b}={v}" for b, v in row.items())
            lines.append(f"- {a}: {cells}")
    else:
        lines.append(f"## 相关性: {corr.get('skipped') or corr.get('error', '—')}")
    if result.get("skipped_symbols"):
        lines.append(f"\n数据不足跳过: {', '.join(result['skipped_symbols'])}")
    if result.get("skipped_non_a_symbols"):
        lines.append(
            f"\n非 A 股跳过（本工具组合特征仅覆盖 A 股，权重已计入压力测试口径）: "
            f"{', '.join(result['skipped_non_a_symbols'])}"
        )
    if result.get("stress"):
        lines.append("\n## 情景压力测试（指数下跌）")
        for k, v in result["stress"].items():
            if k != "note":
                lines.append(f"- 指数 {k}: 组合市值影响约 {v:.1%}")
        lines.append(f"\n*{result['stress'].get('note', '')}*")
    lines.append(f"\n*{result.get('disclaimer', '')}*")
    return "\n".join(lines)
