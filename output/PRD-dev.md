# 半仓滚动 QMT · 开发版

> 给程序员/AI 编码助手的 PRD 精简版。30 分钟可开工。完整细节见 `PRD详细版.md`。

## 0. MVP 范围与阶段路线图

### 阶段一（本次交付 · 14 项）

F1 股票池配置 | F2 6 信号买卖 | F3 半仓滚动 | F4 限价单 | F5 真实账户 | F6 15% 止损 | F7 港股时段过滤 | F8 状态持久化 | F9 卖出优先 | F10 logging 日志 | F15 全局仓位上限 | F16 启动对账 | F18 止损恢复 override.json | F19 每日 14:55 统一判定

### 阶段二（后续 · 5 项）

F11 A 股 T+1 过滤 | F12 日内黑名单 | F14 下载重试 | F17 MA20 斜率趋势过滤 | F20 单日 2 次止损熔断

## 1. 运行环境

- 国金 QMT 内置模式（非 miniQMT），Windows
- Python 3.6-3.12，`xtquant`（QMT 自带）+ `numpy`
- F5 运行无法下单，必须在「模型交易」→「实盘模式」运行

## 2. 模块导入

```python
from xtquant import xtdata
from xtquant.xttrader import XtQuantTrader
from xtquant.xtconstant import *
```

不做多版本兼容层。

## 3. 股票池配置

```python
STOCK_POOL = {
    '603501.SH':   {'name': '韦尔股份', 'weight': 1.0},
    '00700.HGT':   {'name': '腾讯控股', 'weight': 0.5},
}
```

A 股 `.SH` / `.SZ`，港股通 `.HGT`（沪港通）/ `.SGT`（深港通）。

## 4. 信号体系

### 参数常量

```python
VOL_RATIO_LOW  = 0.7    # S2 缩量阈值
VOL_RATIO_MID  = 1.5    # S3/B2 放量阈值
VOL_RATIO_HIGH = 2.0    # B3 强放量阈值
SHADOW_RATIO   = 2.0    # 影线/实体比
SHADOW_PCT     = 0.40   # 影线/振幅比
TARGET_PCT     = 0.5    # 目标仓位比
B2_RATIO       = 1.0/3  # B2 买入比例
```

### 信号判定（优先级从左到右）

**卖出**：S1 > S2 > S3（触发一个即执行，不再检查后续）

| 信号 | 伪代码 |
|------|--------|
| S1 | `close < MA20 AND prev_close >= MA20` |
| S2 | `new_high20 AND vol_ratio <= 0.7` |
| S3 | `vol_ratio >= 1.5 AND long_upper AND close <= prev_close` |

**买入**：B1 > B2 > B3（同股同日卖出优先，卖出当天不买入）

| 信号 | 伪代码 |
|------|--------|
| B1 | `close > MA20 AND prev_close <= MA20` |
| B2 | `lower_shadow > body_abs × 2 AND lower_shadow > range × 0.4 AND vol_ratio >= 1.5` |
| B3 | `bullish AND close > MA5 AND close > MA10 AND close > MA20 AND vol_ratio >= 2.0` |

## 5. 技术指标

纯 numpy 实现。历史数据取 60 根日线。

```python
def calc_indicators(open_arr, high_arr, low_arr, close_arr, vol_arr):
    # 返回 dict，包含：
    # ma5, ma10, ma20          — SMA 均线
    # vol_ma5, vol_ratio       — 量能
    # body_abs, range_         — 实体/振幅
    # upper_shadow, lower_shadow — 影线
    # long_upper, long_lower   — 长影线 0/1
    # is_bullish               — 阳线 0/1
    # ma_bull                  — MA5>MA10>MA20 0/1
    # new_high20               — 创 20 日新高 0/1
    # close_ab_ma20            — 收盘在 MA20 之上 0/1
    # close_ab_ma20_prev       — 前一日 close_ab_ma20
    # break_3ma                — 一阳穿三线 0/1
```

## 6. 执行流程

### init(ContextInfo)

1. `_ctx = ContextInfo`
2. 遍历 STOCK_POOL：`xtdata.download_history_data(stock, period='1d')`（3 次重试）
3. 加载/创建 `state.json`
4. **启动对账**（F16）：遍历 STOCK_POOL，查 `query_stock_position`，对比 state.json。不一致以券商为准
5. 打印股票池摘要 + 初始化完成

### handlebar(ContextInfo) 

每约 3 秒触发一次。逻辑：

```python
def handlebar(ContextInfo):
    _ctx = ContextInfo
    now = datetime.datetime.now()
    today = now.strftime('%Y-%m-%d')
    now_time = now.strftime('%H:%M')

    # 跨日重置
    if today != G.last_date:
        reset_daily_state()
        G.last_date = today

    # 判断是否到达信号判定时间点
    market = get_active_market(now_time)  # 返回 'A' / 'HK_AM' / 'HK_PM' / None

    signal_time = get_signal_time(market)  # 14:55 / 11:55 / 15:55
    if now_time[:5] != signal_time:
        return  # 不是判定时间，跳过

    # 防重复
    if G.last_signal_time == f'{today}:{signal_time}':
        return
    G.last_signal_time = f'{today}:{signal_time}'

    # 全股票池信号判定
    for stock_code, cfg in STOCK_POOL.items():
        if not is_in_trading_hours(stock_code, now_time):
            continue
        if G.stop_loss_triggered.get(stock_code):
            continue

        # 获取行情 + 计算信号 + 执行
        bar = get_latest_bar(stock_code)
        sigs = calc_signals(indicators, bar)
        execute_sell(stock_code, sigs, cfg)   # 卖出优先
        execute_buy(stock_code, sigs, cfg)

    # 收盘快照
    if signal_time == '14:55' or signal_time == '15:55':
        write_state_snapshot()
```

## 7. 仓位计算

```python
# 单股目标仓位
target_value = total_asset × weight × TARGET_PCT  # TARGET_PCT = 0.5

# 全局仓位归一化（F15）
total_target = sum(weight × TARGET_PCT for all stocks)
if total_target > 1.0:
    target_value *= (1.0 / total_target)  # 等比例缩放

# 卖出量（每次卖 50% 持仓）
sell_qty = (cur_position // 2 // lot_size) × lot_size

# 买入量（买到目标仓位）
ideal_buy = max(int(target_value / price / lot_size) × lot_size - cur_position, 0)
max_by_cash = int(virtual_cash / price / lot_size) × lot_size
buy_qty = min(ideal_buy, max_by_cash)
```

## 8. 风控

### 15% 止损（F6）

```python
position = xt_trader.query_stock_position(account, stock_code)
if position.profit_rate <= -0.15:
    state['stocks'][stock_code]['stop_loss_triggered'] = True
    # 当日不再交易该股
```

### 限价单（F4）

```python
# 卖出
limit_price = round(current_price × 0.998, 2)

# 买入
limit_price = round(current_price × 1.002, 2)

passorder(opType=23/24, orderType=1101, prType=11, price=limit_price,
          volume=qty, quickTrade=1, ...)
```

## 9. 状态持久化（F8）

```json
{
  "date": "2026-07-02",
  "stocks": {
    "603501.SH": {
      "stop_loss_triggered": false,
      "trade_count_today": 3,
      "sold_today": false,
      "stop_loss_base": 95.5
    }
  },
  "daily_stop_count": 0
}
```

- 文件：策略 `.py` 同目录
- 跨日重置：`trade_count_today`、`sold_today`、`daily_stop_count`
- 跨日保留：`stop_loss_triggered`、`stop_loss_base`

### 止损恢复（F18）

用户创建 `override.json`：
```json
["603501.SH"]
```
策略启动时读取 → 重置对应 `stop_loss_triggered` → 删除该文件。

### 启动对账（F16）

```python
for stock_code in STOCK_POOL:
    pos = xt_trader.query_stock_position(account, stock_code)
    actual_qty = pos.volume if pos else 0
    expected_qty = state['stocks'][stock_code].get('expected_qty', 0)
    if actual_qty != expected_qty:
        log.warning(f'{stock_code}: 实际持仓 {actual_qty} ≠ 预期 {expected_qty}，以实际为准')
        state['stocks'][stock_code]['expected_qty'] = actual_qty
```

## 10. 港股适配

### 交易时段过滤（F7）

```python
def is_in_trading_hours(stock_code, now_time):
    if stock_code.endswith('.HGT') or stock_code.endswith('.SGT'):
        # 港股通：9:30-12:00, 13:00-16:00
        return ('09:30' <= now_time <= '12:00') or ('13:00' <= now_time <= '16:00')
    else:
        # A 股：9:30-11:30, 13:00-15:00
        return ('09:30' <= now_time <= '11:30') or ('13:00' <= now_time <= '15:00')
```

### 信号判定时间

| 市场 | 判定时间 |
|------|---------|
| A 股 | 14:55 |
| 港股早市 | 11:55 |
| 港股午市 | 15:55 |

## 11. 全局状态对象

```python
class G:
    trade_count_today: dict    # {stock_code: int}
    sold_today: dict           # {stock_code: bool}
    stop_loss_triggered: dict  # {stock_code: bool}
    last_signal_time: str      # "2026-07-02:14:55"
    daily_stop_count: int      # 当日止损次数
    last_date: str             # 跨日检测
```

`xtdata.get_full_tick()` / `query_stock_position()` / `query_stock_asset()` 每次实时调用，不缓存在 G 中。

## 12. 日志（F10）

```python
import logging

logger = logging.getLogger('V7')
handler = logging.FileHandler(f'logs/V7_{today}.log')
handler.setFormatter(logging.Formatter('%(asctime)s | %(levelname)-7s | %(stock)-12s | %(message)s'))
```

- 按日轮转，保留 30 天
- INFO+ 同步输出 QMT 控制台
- 同类错误 5 分钟内最多 3 条

## 13. 文件清单

| 文件 | 职责 |
|------|------|
| `half_position_rolling.py` | 策略主文件（~600 行） |
| `state.json` | 运行时状态（策略自动读写） |
| `override.json` | 止损恢复指令（用户手动创建，用完即删） |
| `logs/V7_YYYY-MM-DD.log` | 按日日志 |

## 14. 待验证假设

| ID | 假设 | 风险 |
|----|------|------|
| A-001 | 6 信号实盘胜率与回测一致 | 中 |
| A-002 | 港股与 A 股同参数有效 | 高 |
| A-003 | 14:55 日线数据足够完整 | 低 |
| A-004 | profit_rate 基于加权平均成本 | 中 |
| A-006 | QMT API 版本兼容 | 低 |
