# 验收门禁与 GOAL 契约

> 生成时间：2026-07-02
> 基于：PRD详细版.md + 技术方案.md + 测试决策蓝图.md
> 本文件是 Coding Agent 的总入口——先读这份

## 1. 完成定义

> **三层全部 P0 + P1 用例转绿 = 交付。**

| 等级 | 要求 | 说明 |
| :--- | :--- | :--- |
| P0（64 条） | **必须全绿** | 核心算法正确性 + 核心边界容错 + 完整链路。P0 不绿 = 不可交付 |
| P1（102 条） | **必须全绿** | 边界/子场景/综合场景。P1 不绿 = 不可交付 |
| P2（31 条） | 尽力完成 | 极端值/数值稳定/防错。允许标 `SKIPPED` 但需注明理由 |

> **安全层特例**：不适用（无登录/鉴权/API/SQL 注入面）

## 2. 选中层与对应用例

| 层 | 文件 | 路径 | 用例数 | P0 | P1 |
| :--- | :--- | :--- | ---: | ---: | ---: |
| 单元 | 技术指标_TDD | `unit/技术指标_TDD.md` | 55 | 18 | 29 |
| 单元 | 信号判定_TDD | `unit/信号判定_TDD.md` | 45 | 20 | 19 |
| 单元 | 仓位计算_TDD | `unit/仓位计算_TDD.md` | 60 | 10 | 38 |
| 单元 | 限价单_TDD | `unit/限价单_TDD.md` | 7 | 2 | 3 |
| 单元 | 时段过滤_TDD | `unit/时段过滤_TDD.md` | 8 | 3 | 3 |
| 边界异常 | 边界异常_TDD | `crosscut/边界异常_TDD.md` | 16 | 5 | 10 |
| 集成 | QMT框架集成_TDD | `integration/QMT框架集成_TDD.md` | 6 | 6 | 0 |
| **合计** | **7 份** | | **197** | **64** | **102** |

## 3. Coding Agent 消费协议（GOAL 模式）

### 3.1 用什么跑

```bash
# 单元层 + 边界异常层 —— 可在本地 Python 直接跑（不需要 QMT）
cd 半仓滚动QMT/output/tests
pip install pytest numpy
pytest unit/ crosscut/ -v

# 集成层 —— 需要 mock QMT 环境（pytest monkeypatch）
pytest integration/ -v
```

### 3.2 GOAL 四步（红 → 绿 → 重构 → 回归证明）

```
对每条用例（按 测试索引.md 顺序）：

  STEP 1 · 红（Red）
  ├── 写最小可执行测试代码（pytest 函数）
  ├── 运行 → 预期失败 ✅（失败方式必须匹配「预期失败原因」）
  └── 如果预期失败原因不匹配 → 先修正测试代码，再继续

  STEP 2 · 绿（Green）
  ├── 写最小实现代码让测试通过
  └── pytest → PASSED

  STEP 3 · 重构（Refactor）
  ├── 优化代码结构、去重、加注释
  └── pytest → 仍然 PASSED（保持绿）

  STEP 4 · 回归证明
  ├── 每完成 10 条用例 → 跑全套 pytest → 确认无回退
  └── 记录到 测试索引.md 的完成状态栏
```

### 3.3 优先级执行顺序

```text
第一轮（核心数据流）：
  unit/技术指标_TDD.md 全 P0 → P1
  unit/信号判定_TDD.md 全 P0 → P1
  unit/仓位计算_TDD.md 全 P0 → P1

第二轮（执行逻辑）：
  unit/限价单_TDD.md 全 P0 → P1
  unit/时段过滤_TDD.md 全 P0 → P1

第三轮（容错与恢复）：
  crosscut/边界异常_TDD.md 全 P0 → P1

第四轮（端到端链路）：
  integration/QMT框架集成_TDD.md 全 P0

最后收尾：
  所有 P2 → 按时间允许逐条完成
```

### 3.4 什么算交付

```text
✅ 测试索引.md 中所有 P0 + P1 用例标记为 PASSED
✅ pytest 完整运行输出 0 failures / 0 errors
✅ P2 用例标记为 PASSED 或 SKIPPED（需理由）
✅ 每条 P0 用例的「红阶段」失败方式与预期失败原因一致记录
```

## 4. 覆盖率目标

| 层 | 目标 | 说明 |
| :--- | :---: | :--- |
| 单元层 | >90% | `calc_indicators` / `calc_signals` / 仓位函数 / 限价 / 时段 |
| 边界异常层 | >80% | state/override/数据容错函数 |
| 集成层 | >70% | QMT mock 链路（mock 覆盖不可能达 100%） |

## 5. 环境约束

| 约束 | 说明 |
| :--- | :--- |
| 测试框架 | **pytest**（QMT 外使用）+ **numpy**（QMT 自带） |
| 无 QMT SDK 依赖 | 单元层/边界异常层**不需要 xtquant/xttrader**——mock 数据驱动 |
| 集成层需要 mock | 用 pytest monkeypatch/unittest.mock 替代 xtdata/xttrader/passorder |
| Python 版本 | 3.6-3.12（建议测试环境用 3.9+，策略部署跟随 QMT 内置版本） |
| 文件路径 | 测试代码路径应与技术方案 §8.1 文件结构一致 |
