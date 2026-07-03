# Jaden · 项目纪要

- 项目目标：国金 QMT 半仓滚动量化策略，6 信号技术指标体系，A 股+港股通双市场
- 约束：Python 3.6-3.12，QMT 内置环境，numpy 纯数组，单文件 ~740 行

## 当前状态
- ✅ 已完成：PRD（详细版+摘要版+dev版）、技术方案、测试决策蓝图
- ✅ 已完成：`half_position_rolling.py` (744 行) — xtdata import 移回文件顶部 module-level，编译/ruff/167 tests 全过
- ✅ 已完成：`__file__` 清除 → `BASE_DIR` 硬编码
- ✅ 已完成：`logging` 清除 → `_log_print` + print
- ✅ 已完成：`passorder` 清除 → `xtrading.order_stock` 兼容链
- ✅ 已完成：`from xtquant import xtdata` module-level 直接导入
- ✅ 已完成：每 30 分钟心跳日志
- 14 项 MVP 功能全部实现

## 决策记录
- [07-02-2026] GOAL 条件适配｜背景：原 GOAL 假定 Web 应用，本项目是 QMT 策略脚本｜结论：重定义交付标准｜来源：用户
- [07-03-2026 11:47] ⭐ xtdata import 是根因｜背景：用户指出另个策略正常、手动下载正常。`from xtquant import xtdata` 被 try/except 包裹，QMT exec 时 ImportError → xtdata=None → 所有行情 None → 策略静默跳过｜结论：module-level 直接导入，不用 try/except。数据下载重试恢复原版 V7 方式｜来源：用户指正 + AI