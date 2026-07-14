# Jaden · 项目纪要

- 项目目标：国金 QMT 半仓滚动量化策略，6 信号技术指标体系，A 股+港股通双市场
- 约束：Python 3.6-3.12，QMT 内置环境，numpy 纯数组，单文件 ~740 行

## 当前状态
- ✅ 已完成：PRD（详细版+摘要版+dev版）、技术方案、测试决策蓝图
- ✅ 已完成：`half_position_rolling.py` (758 行) — xtdata 已去 try/except，[SIG] 诊断日志已加，14:55 信号触发窗口已修复
- ✅ 已完成：Git 协作配置 → https://github.com/jxd4106/Quant-QMT (6 commits pushed)
- ✅ 已完成：memory/no-redundant-confirmation.md — 不再无意义重复确认

## 决策记录
- [07-14-2026 14:20] 禁止无意义重复确认规则已执行但无效｜背景：CLAUDE.md §12、memory/no-redundant-confirmation.md、MEMORY.md 均已写入，但助手仍然在无限 echo 循环｜结论：写入规则本身不足以阻止该行为——需要更根本的机制（见待解决问题）｜来源：用户指正
- [07-02-2026] GOAL 条件适配｜背景：原 GOAL 假定 Web 应用，本项目是 QMT 策略脚本｜结论：重定义交付标准｜来源：用户
- [07-03-2026 11:47] ⭐ xtdata import 是根因｜背景：用户指出另个策略正常、手动下载正常。`from xtquant import xtdata` 被 try/except 包裹，QMT exec 时 ImportError → xtdata=None → 所有行情 None → 策略静默跳过｜结论：module-level 直接导入，不用 try/except。数据下载重试恢复原版 V7 方式｜来源：用户指正 + AI