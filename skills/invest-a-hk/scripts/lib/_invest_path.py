"""invest-a-hk path shim（照抄 journal/etf 版：只转发 skills/lib 与 invest-a-stock scripts）。"""
from __future__ import annotations

import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parent
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

_SKILLS_LIB = _LIB.parents[3] / "lib"          # skills/lib（parents: lib→scripts→invest-a-hk→skills）
if str(_SKILLS_LIB) not in sys.path:
    sys.path.insert(0, str(_SKILLS_LIB))

from invest_path import ensure_invest_a_scripts_on_path  # noqa: E402
from invest_path import ensure_shared_lib_on_path        # noqa: E402

ensure_skills_lib_on_path = ensure_shared_lib_on_path    # 别名对齐既有 shim 命名
