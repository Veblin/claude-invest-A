"""invest-hk-stock 引擎 lib（v0.2.9 港股数据引入 v1）。

隔离纪律（同 etf/journal conftest 注释）：本目录不建 `lib` 子包、数据模块用顶层
命名（hk_*.py），`lib` 一词保留给 invest-a-stock/scripts/lib —— 防止跨 skill 同进程
并跑时遮蔽 invest-a-stock 的 lib 包。共享纯函数一律经 skills/lib 或 invest-a-stock lib。
"""
