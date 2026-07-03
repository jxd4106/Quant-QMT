# V0 方案概要

## 解决思路

对现有 `qmt_v7_strategy_ascii.py` 做**三砍一补一加固**：

- **砍掉虚拟子账户**（整个 ISO capital manager，~300 行）：用真实券商账户 `query_stock_asset` / `query_stock_position` 替代
- **砍掉 xtrading 兼容层**：调研确认正确模块是 `xtquant.xttrader`，不存在 `xtrading`，兼容层在实盘全部失败
- **砍掉自研技术指标**：保留纯 numpy 实现（已验证，无需换）
- **补上多股可配置**：股票池从单只 tuple 改为 Python 字典，每只独立设仓位权重
- **补上港股时段过滤**：策略内判断当前时间是否在对应市场交易时段
- **补上单股止损**：通过 QMT `query_stock_position` 查询浮动盈亏比例，低于 -30% 暂停该股
- **补上状态持久化**：当日交易次数、止损标记、跨日标记写入 JSON 文件
- **加固错误处理**：所有 xtdata/xttrader 调用加 try-except + None 检查，日志写本地文件

## 交付物清单

| # | 文件 | 说明 |
|---|------|------|
| 1 | `half_position_rolling.py` | QMT 主策略文件（单文件，约 600 行） |
| 2 | `state.json` | 运行时状态文件（自动创建于 QMT 数据目录） |
| 3 | `logging.conf` 或内置配置 | 日志配置 |

## 功能清单（带优先级）

| ID | 功能 | 优先级 | 所属阶段 |
|----|------|--------|---------|
| F1 | 股票池配置（A 股+港股，每只独立权重） | P1 核心 | MVP |
| F2 | 6 信号买卖体系（S1/S2/S3 + B1/B2/B3） | P1 核心 | MVP |
| F3 | 半仓滚动（目标仓位 = 该股权益 × 50%） | P1 核心 | MVP |
| F4 | 限价单执行（卖 ×0.998 买 ×1.002） | P1 核心 | MVP |
| F5 | 真实券商账户核算 | P1 核心 | MVP |
| F6 | 单股 -30% 止损（查券商接口盈亏比） | P1 核心 | MVP |
| F7 | 港股交易时段过滤（含午市） | P1 核心 | MVP |
| F8 | 状态文件持久化（跨重启恢复） | P1 核心 | MVP |
| F9 | 卖出优先于买入（同股同日） | P1 核心 | MVP |
| F10 | logging 日志文件 | P1 核心 | MVP |
| F11 | A 股 T+1 约束（可卖数量过滤） | P2 重要 | MVP |
| F12 | 当日卖出黑名单（防止损反手循环） | P2 重要 | MVP |
| F13 | xttrader 兼容适配（不同 QMT 版本） | P2 重要 | MVP |
| F14 | 历史数据下载 + 重试 | P2 重要 | MVP |

## 关键设计决策

### 1. 架构：monolithic 单文件

整个策略是一个 `.py` 文件，QMT 内置编辑器可直接加载。不做模块拆分——QMT 的 import 路径机制不可靠。

### 2. 股票池配置

```python
STOCK_POOL = {
    '603501.SH': {'name': '韦尔股份', 'weight': 1.0},   # A 股
    '00700.HKSH': {'name': '腾讯控股', 'weight': 0.5},   # 沪港通
}
```

每只股的目标仓位 = `account_total_asset × weight × 0.5`

### 3. 状态持久化

```json
{
  "date": "2026-07-02",
  "stocks": {
    "603501.SH": {
      "stop_loss_triggered": false,
      "trade_count_today": 0,
      "sold_today": false,
      "stop_loss_base": 100000.0
    }
  }
}
```

- 跨日自动重置 `trade_count_today` 和 `sold_today`
- `stop_loss_triggered` 仅人工手动恢复
- `stop_loss_base` 首次启动记录，之后不变

### 4. 交易时段过滤

```python
def is_trading_hours(stock_code):
    if stock_code.endswith('.HGT') or stock_code.endswith('.SGT'):
        # 港股：早市 9:30-12:00，午市 13:00-16:00
        ...
    else:
        # A 股：9:30-11:30，13:00-15:00
        ...
```

### 5. 止损实现

不走虚拟子账户，直接从券商接口查：

```python
position = xt_trader.query_stock_position(account, stock_code)
profit_rate = position.profit_rate  # 浮动盈亏比例
if profit_rate <= -0.30:
    mark_stop_loss(stock_code)  # 暂停该股交易
```

### 6. QMT 框架适配（调研发现的关键修正）

- **ContextInfo 回滚**：所有状态存全局 `class G` 对象，不存 ContextInfo
- **handlebar 触发频率**：实盘每 3 秒一次，不是每根日线一次——加防重复处理
- **quickTrade=1**：日线最新 K 线立即触发（不能用 0）
- **实盘模式**：在模型交易界面以实盘模式运行，F5 测试仅用于调试
