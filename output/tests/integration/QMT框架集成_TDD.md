# QMT 框架集成 TDD

> 测试层：QMT mock 集成层
> 产物类型：pytest 集成测试设计（monkeypatch / fixture mock 替代 xtdata / xttrader / passorder）
> 输入依据：PRD 详细版 §7 + 技术方案 §4-§7
> 验收约束：I-INT-001 ~ I-INT-006 全部转绿即本层通过

---

## 0. Mock 总则

### 0.1 需要 mock 的外部依赖（全部 5 个）

| 被 mock 对象 | mock 级别 | pytest 手段 | 备注 |
| :--- | :--- | :--- | :--- |
| `xtdata.download_history_data` | 函数级 | `monkeypatch` 替换为 stub | 验证调用次数 + 参数 |
| `ContextInfo.get_market_data_ex` | 方法级 | `unittest.mock.MagicMock` | 返回 60 根 numpy 日线 |
| `ContextInfo.get_full_tick` | 方法级 | `MagicMock` | 返回当前价格快照 |
| `xttrader.query_stock_position` | 方法级 | `MagicMock` | 返回持仓对象（profit_rate / volume / avg_price） |
| `xttrader.query_stock_asset` | 方法级 | `MagicMock` | 返回总资产 / 可用资金 |
| `passorder` | 模块级函数 | `monkeypatch` 替换为 spy | 验证下单参数 |

### 0.2 不需要 mock 的

- `calc_indicators()` / `calc_signals()` ——真实调用，验证接口契约
- `state.json` 读写 —— 用 `tmp_path` 隔离
- `override.json` —— 同上
- `logging` —— 用 `pytest-log-reader` 或手动捕获 handler
- `G` 全局对象 —— 测试中直接操作验证

### 0.3 Mock 约定：返回数据类型模拟

```python
# get_market_data_ex 返回格式（模拟）：
# { 'close': np.ndarray, 'open': np.ndarray, 'high': np.ndarray, 'low': np.ndarray, 'volume': np.ndarray }
# 每条数组长度 = 60

# get_full_tick 返回格式（模拟）：
# { 'lastPrice': 50.0, 'lastClose': 49.5, 'volume': 12345678, 'time': '14:55:01' }

# query_stock_position 返回对象属性（模拟）：
# .m_volume (int: 持仓数量), .m_avgPrice (float: 成本价), .m_profit (float: 浮动盈亏),
# .m_lastPrice (float: 最新价), 推导字段 profit_rate (float)

# query_stock_asset 返回对象属性（模拟）：
# .m_dBal (float: 总资产), .m_dCash (float: 可用资金)

# passorder 签名：
# passorder(opType, orderType, accountid, stock_code, prType, price, volume, strategyName, quickTrade, orderId, ctx)
```

---

## 用例 I-INT-001：init 启动流程

**用例 ID**：I-INT-001
**被测入口**：`init(ContextInfo)`
**优先级**：P0
**覆盖功能**：F1 股票池、F14 历史数据下载、F16 启动对账、F8 状态持久化、F10 日志

### Given（前置条件）

- STOCK_POOL = { '603501.SH': {…}, '00700.HGT': {…} }
- download_history_data stub：每次调用记入 `download_history_data.call_args_list`
- get_market_data_ex mock：每只股票返回 60 根有效日线（numpy 数组）
- query_stock_position mock：603501.SH 返回持仓 1000 股（与 state.json 一致），00700.HGT 返回持仓 0
- query_stock_asset mock：总资产 500,000，可用资金 200,000
- state.json 已存在（tmp_path / 内容有效）
- override.json 不存在
- 日志 handler：`caplog` 捕获

### When（动作）

```python
import half_position_rolling as strat

strat.init(ContextInfo)
```

### Then（验证）

| # | 断言 | 验证方式 |
| :--- | :--- | :--- |
| 1 | `download_history_data` 被调用 2 次（每只 STOCK_POOL 一次） | `assert download_history_data.call_count == 2` |
| 2 | 第 1 次调用参数为 `('603501.SH', '1d')` | `assert download_history_data.call_args_list[0].args[0] == '603501.SH'` |
| 3 | 第 2 次调用参数为 `('00700.HGT', '1d')` | `assert download_history_data.call_args_list[1].args[0] == '00700.HGT'` |
| 4 | state.json 文件被创建/更新（文件存在且可解析） | `assert state_path.exists(); json.load(open(state_path))` |
| 5 | 对账执行：`query_stock_position` 至少被调用 2 次（每只股票一次） | `assert position_mock.call_count >= 2` |
| 6 | 日志中包含"初始化完成"/"init complete"关键字 | `assert '初始化' in caplog.text or 'init' in caplog.text.lower()` |
| 7 | 下载失败（download_history_data 抛异常）时不崩溃，日志含 WARNING | 额外 Given：第 2 次调用 raise RuntimeError |

### 预期失败原因（红阶段）

- `init()` 尚未实现或未调用 `download_history_data`
- `state.json` 路径硬编码不存在于 pytest tmp_path
- 对账逻辑未调用 `query_stock_position`
- 日志未配置 handler，`caplog` 为空

### Mock 设置说明

```python
@pytest.fixture
def mock_xtdata(monkeypatch):
    calls = []
    def fake_download(stock, period='1d'):
        calls.append((stock, period))
        return True
    monkeypatch.setattr('xtquant.xtdata.download_history_data', fake_download)
    fake_download.call_args_list = calls  # 会被引用
    return fake_download
```

---

## 用例 I-INT-002：handlebar 非信号时段跳过

**用例 ID**：I-INT-002
**被测入口**：`handlebar(ContextInfo)`
**优先级**：P0
**覆盖功能**：F19 信号判定时机、F7 交易时段过滤、防重复逻辑

### Given（前置条件）

- 当前 mock 时间为 `10:30:00`（既不是 14:55 也不是 11:55 也不是 15:55）
- `ContextInfo.get_full_tick` 被 spy 包装，可记录调用
- `passorder` 被 spy 包装
- `G.last_signal_time` 初始为 `None`（或前一日期的时间）
- `g.on_bar` 被 spy 包装

### When（动作）

```python
strat.handlebar(ContextInfo)
```

### Then（验证）

| # | 断言 | 验证方式 |
| :--- | :--- | :--- |
| 1 | `on_bar` 未被调用 | `assert on_bar_spy.call_count == 0` |
| 2 | `passorder` 未被调用 | `assert passorder_spy.call_count == 0` |
| 3 | `G.last_signal_time` 未被更新 | `assert G.last_signal_time != '2026-07-02:10:30'` |
| 4 | handlebar 正常 return（无异常，< 1ms） | 时序断言 |

### 预期失败原因（红阶段）

- handlebar 未做时间判断，每次 tick 都调用 on_bar
- 时间字符串比较格式不一致（如 `"10:30"` vs `"10:30:00"`）
- `get_signal_time_for_now()` 对所有合法时间段返回非 None

### Mock 设置说明

```python
# 不需要 mock 行情数据——因为不会走到那一步
# 只需确保 ContextInfo 能被传入、时间能正确取到即可
# 时间 mock：monkeypatch 替换 datetime.now() 返回 10:30
@pytest.fixture
def mock_context():
    ctx = MagicMock()
    # handlebar 内部通过 _ctx 取时间，通常用 datetime.now() 而非 ContextInfo 属性
    return ctx
```

---

## 用例 I-INT-003：14:55 完整信号判定 + 下单

**用例 ID**：I-INT-003
**被测入口**：`handlebar(ContextInfo)` → `on_bar(stock_code, bar_dict)` → `calc_indicators()` / `calc_signals()` / `send_order()`
**优先级**：P0
**覆盖功能**：F2 信号体系、F3 半仓滚动、F4 限价单、F19 14:55 判定、F9 卖出优先、F10 日志

### Given（前置条件）

- 当前 mock 时间为 `14:55:01`
- STOCK_POOL 含 `603501.SH`
- `get_market_data_ex` mock：603501.SH 返回 60 根有效日线（numpy 数组）
- `get_full_tick` mock：`{'lastPrice': 50.0, 'lastClose': 49.0, 'volume': 500000, 'time': '14:55:01'}`
- 当前 bar：open=49.5, high=50.3, low=48.8, close=50.0, vol=500000
- 历史数据中 MA20 = 49.0，前日 close 在 MA20 以下
- 指标计算后满足 **B1 突破买入** 条件（close 50.0 > MA20 49.0 且前日 close < MA20）
- `query_stock_asset` mock：总资产 500,000，可用资金 200,000
- `query_stock_position` mock：603501.SH 持仓 0 股（空仓）
- weight = 1.0
- `G.last_signal_time` 为 `None`（尚未判定）
- `G.sold_today['603501.SH']` 为 `False`
- `G.stop_loss_triggered['603501.SH']` 为 `False`
- `G.trade_count_today['603501.SH']` = 0
- `passorder` spy 可记录参数

### When（动作）

```python
strat.handlebar(ContextInfo)
# handlebar 内部：
#   1. 时间判断 → 14:55 → 触发信号判定
#   2. 防重复 → G.last_signal_time != '2026-07-02:14:55' → 继续
#   3. 遍历 STOCK_POOL
#   4. 对 603501.SH：get_full_tick → 当前 bar → 追加到历史数组
#   5. calc_indicators() → 返回 15 个指标数组
#   6. calc_signals() → 返回 {'B1': True, 'B2': False, 'B3': False, 'S1': False, ...}
#   7. 仓位计算：目标仓位 = 500000 × 1.0 × 0.5 / 50.0 = 5000 股
#   8. passorder(23, 1101, ..., '603501.SH', 11, 50.0 * 1.002 = 50.1, 5000, ...)
```

### Then（验证）

| # | 断言 | 验证方式 |
| :--- | :--- | :--- |
| 1 | `get_full_tick` 被调用，参数为 `['603501.SH']` | `assert full_tick_mock.call_args is not None` |
| 2 | `passorder` 被调用 1 次 | `assert passorder_spy.call_count == 1` |
| 3 | `passorder` 的 `opType` 参数为 `23`（买入） | `assert call_args[0] == 23` |
| 4 | `passorder` 的 `price` 参数 = `50.0 * 1.002` = 50.1 | `assert call_args['price'] == pytest.approx(50.1, 0.01)` |
| 5 | `passorder` 的 `volume` 参数 = 5000 股（500000 * 1.0 * 0.5 / 50）| `assert call_args['volume'] == 5000` |
| 6 | `passorder` 的 `prType` = `11`（指定价限价单）| `assert call_args['prType'] == 11` |
| 7 | 日志包含 "603501.SH" + "B1" + "买入" 关键字 | `assert '603501.SH' in caplog.text and 'B1' in caplog.text` |
| 8 | `G.trade_count_today['603501.SH']` = 1 | 直接断言 |
| 9 | `G.last_signal_time` = `'2026-07-02:14:55'` | 直接断言 |
| 10 | handlebar 再次被同一个 time key 调用时不重复下单 | 再次调用 handlebar → `passorder_spy.call_count` 仍为 1 |

### 卖出优先验证

额外 Given：同时满足 B1（买入）和 S1（卖出），已有持仓 2000 股
Then：`passorder` 只有卖出调用（`opType=24`），无买入调用

### 预期失败原因（红阶段）

- `get_signal_time_for_now()` 返回 None（14:55 不在判定时间列表）
- `get_full_tick` 返回格式解析错误（键名不匹配 `lastPrice` vs `last_price`）
- B1 判定条件错误（`close > MA20` 时返回 False）
- 仓位计算未正确获取资产值
- passorder stub 未记录调用
- 卖出优先逻辑未在 on_bar 中实现

### Mock 设置说明

```python
@pytest.fixture
def mock_14_55_env(monkeypatch, tmp_path):
    # 时间固定为 14:55
    from unittest.mock import patch
    import datetime

    class FakeDatetime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 7, 2, 14, 55, 1)

    monkeypatch.setattr('datetime.datetime', FakeDatetime)

    # ContextInfo mock
    ctx = MagicMock()
    ctx.get_market_data_ex.return_value = {
        'close': np.array([...60根日线...]),
        'open': np.array([...]),
        'high': np.array([...]),
        'low': np.array([...]),
        'volume': np.array([...]),
    }
    ctx.get_full_tick.return_value = {
        'lastPrice': 50.0,
        'lastClose': 49.0,
        'volume': 500000,
        'time': '14:55:01'
    }
    return ctx
```

---

## 用例 I-INT-004：止损触发链路

**用例 ID**：I-INT-004
**被测入口**：`handlebar(ContextInfo)` → 止损检查逻辑
**优先级**：P0
**覆盖功能**：F6 15% 止损、F8 状态持久化、当日不再交易

### Given（前置条件）

- 当前 mock 时间为 `14:55:01`
- `query_stock_position` mock：603501.SH
  - `m_volume` = 5000
  - `m_avgPrice` = 58.8
  - `m_lastPrice` = 50.0
  - `profit_rate` = -0.18（即 -18%，低于 -15% 阈值）
- `state.json` 中 603501.SH 的 `stop_loss_triggered` = False
- `G.stop_loss_triggered['603501.SH']` = False
- `get_full_tick` mock：`lastPrice` = 50.0
- 行情数据 mock 正常（满足某个买入信号条件）

### When（动作）

```python
strat.handlebar(ContextInfo)
# on_bar 内部流程：
#   1. 查持仓 → profit_rate = -0.18
#   2. 止损检查 → profit_rate <= -0.15 → True
#   3. 标记 G.stop_loss_triggered['603501.SH'] = True
#   4. 写 state.json（stop_loss_triggered = true）
#   5. 返回，不下单（即使有买入信号）
```

### Then（验证）

| # | 断言 | 验证方式 |
| :--- | :--- | :--- |
| 1 | `G.stop_loss_triggered['603501.SH']` 变为 `True` | 直接断言 |
| 2 | `passorder` **未被调用**（止损优先于一切交易） | `assert passorder_spy.call_count == 0` |
| 3 | `state.json` 中 603501.SH 的 `stop_loss_triggered` 字段为 `true` | 读取 `tmp_path/state.json` 验证 |
| 4 | 日志包含 "603501.SH" + "止损" + "stop_loss" 关键字 | `caplog.text` 断言 |
| 5 | profit_rate = 0 时不触发止损（边界） | 额外 Given：profit_rate=0 → `stop_loss_triggered` 不变 |
| 6 | profit_rate = -0.14（-14%，未到阈值）时不触发 | 额外 Given：profit_rate=-0.14 → `stop_loss_triggered` 仍为 False |
| 7 | 当日后续 handlebar 不再交易该股 | 再次调用 handlebar → `passorder` 仍未被调用 |

### 预期失败原因（红阶段）

- 止损检查在信号判定之后执行（应先检查止损，再判定信号）
- `profit_rate` 字段名不匹配（如 `profit_rate` vs `m_profitRate`）
- 止损标记只更新 G 对象但未调用 `write_state_to_file()`
- 止损后 state.json 写了一半就崩溃（原子写验证）

### Mock 设置说明

```python
# 核心：mock query_stock_position 返回 profit_rate = -0.18
def make_position(volume, avg_price, last_price, profit_rate):
    """工厂函数：生成模拟持仓对象"""
    pos = MagicMock()
    type(pos).m_volume = PropertyMock(return_value=volume)
    type(pos).m_avgPrice = PropertyMock(return_value=avg_price)
    type(pos).m_lastPrice = PropertyMock(return_value=last_price)
    type(pos).profit_rate = PropertyMock(return_value=profit_rate)
    return pos

# 在 fixture 中注入
xttrader.query_stock_position.return_value = make_position(5000, 58.8, 50.0, -0.18)
```

---

## 用例 I-INT-005：override.json 恢复止损

**用例 ID**：I-INT-005
**被测入口**：`init(ContextInfo)`
**优先级**：P0
**覆盖功能**：F18 止损恢复

### Given（前置条件）

- `state.json` 中 603501.SH 的 `stop_loss_triggered` = True（历史触发过）
- `override.json` 存在，内容为 `["603501.SH"]`
- 策略代码：`init()` 启动时先读 `state.json`，再读 `override.json`

### When（动作）

```python
strat.init(ContextInfo)
# init 内部：
#   1. 加载 state.json → 603501.SH stop_loss_triggered = True
#   2. 检查 override.json 是否存在 → 存在
#   3. 解析内容 → ["603501.SH"]
#   4. 对列表中每只股票：G.stop_loss_triggered[code] = False
#   5. 更新 state.json 写到磁盘
#   6. os.remove(override.json)
```

### Then（验证）

| # | 断言 | 验证方式 |
| :--- | :--- | :--- |
| 1 | `G.stop_loss_triggered['603501.SH']` 变为 `False` | 直接断言 |
| 2 | `state.json` 中 603501.SH 的 `stop_loss_triggered` = `false` | 文件内容断言 |
| 3 | `override.json` 已被删除 | `assert not os.path.exists(override_path)` |
| 4 | 多只股票同时恢复（如 `["603501.SH", "00700.HGT"]`） | 额外 Given：两只会员都恢复 |
| 5 | `override.json` 不存在时正常启动不报错 | 额外 Given：文件不存在 → 无异常 |
| 6 | `override.json` 为空数组 `[]` 时正常启动 | 额外 Given：空数组 → 遍历但不重置任何股票 |
| 7 | `override.json` 格式错误（如 `{"abcd"}`）时：打印 WARNING，不崩溃，不删文件 | 额外 Given：畸形 JSON → WARNING 日志 + 文件保留 |
| 8 | `override.json` 包含不在 STOCK_POOL 中的代码 → 忽略该代码，不崩溃 | 额外 Given：`["999999.SH"]` → 跳过 |

### 预期失败原因（红阶段）

- `init()` 中没有读取 `override.json` 的逻辑
- 重置后忘记更新 `state.json`，下次重启又读到旧的 True
- 删除 `override.json` 在重置之前执行（先删文件，读不到内容）
- 文件不存在时 `os.remove()` 抛 `FileNotFoundError`

### Mock 设置说明

```python
@pytest.fixture
def mock_override(tmp_path, monkeypatch):
    """在 tmp_path 下构造 state.json 和 override.json"""
    state_dir = tmp_path / "qmt_strategy"
    state_dir.mkdir()
    state_file = state_dir / "state.json"
    override_file = state_dir / "override.json"

    # state.json：603501.SH 已止损
    state_file.write_text(json.dumps({
        "date": "2026-07-01",
        "stocks": {
            "603501.SH": {"stop_loss_triggered": True, "trade_count_today": 0, "sold_today": False, "stop_loss_base": 58.8}
        },
        "daily_stop_count": 1
    }))

    # override.json：恢复指令
    override_file.write_text(json.dumps(["603501.SH"]))

    # 所有路径指向 tmp_path
    # 注意：实际代码中路径可能硬编码，需要在 monkeypatch 或策略代码中用可配置路径
    return state_dir
```

---

## 用例 I-INT-006：启动对账不一致

**用例 ID**：I-INT-006
**被测入口**：`init(ContextInfo)`
**优先级**：P0
**覆盖功能**：F16 启动对账

### Given（前置条件）

- `state.json` 中 603501.SH 记录的预期持仓（从 `stop_loss_base` 推导或新字段 `expected_qty`）= 1000 股
- `query_stock_position` mock 返回：603501.SH `m_volume` = 2000 股（券商实际持仓比 state 记录多 1000）
- `query_stock_asset` mock：正常
- `download_history_data` stub：正常
- 其他 mock 正常

### When（动作）

```python
strat.init(ContextInfo)
# init 内部对账流程：
#   1. 遍历 STOCK_POOL
#   2. 对 603501.SH：查券商持仓 → volume = 2000
#   3. 从 state.json 读取预期 → expected = 1000
#   4. 2000 != 1000 → 不一致
#   5. 以券商为准：更新 state.json 中的记录，标记实际持仓 2000
#   6. 打印 WARNING 日志
```

### Then（验证）

| # | 断言 | 验证方式 |
| :--- | :--- | :--- |
| 1 | 日志包含 WARNING 级别记录 | `caplog` 级别断言 |
| 2 | 日志包含 "603501.SH" + "对账" 或 "持仓不一致" | `caplog.text` 文本断言 |
| 3 | 日志包含 "2000"（券商实际持仓）和 "1000"（state 预期持仓） | `caplog.text` 包含两者 |
| 4 | state.json 被更新为券商实际持仓值 | 读文件验证 stocks.603501.SH 的 volume 或等效字段 |
| 5 | 对账后策略继续正常运行（不崩溃） | finish init 后无异常 |
| 6 | 券商持仓 = state 预期时，不打印 WARNING（但可打印 INFO） | 额外 Given：两者都是 1000 → 无 WARNING |
| 7 | `query_stock_position` 返回 None 时（查不到持仓）→ 不崩溃，日志记录 | 额外 Given：返回 None → 无异常 + 日志 |

### 预期失败原因（红阶段）

- `init()` 中没有对账逻辑（F16 未实现）
- 对账只读不写——更新了日志但没有同步到 state.json
- `query_stock_position` 返回对象的属性名不匹配（如 `volume` vs `m_nVolume`）
- 空持仓时 `position.volume` 取不到，即使持仓为 0 也应正常处理

### Mock 设置说明

```python
@pytest.fixture
def mock_reconciliation(monkeypatch, tmp_path):
    """构造对账不一致的初始状态"""

    # state.json：预期 1000 股
    state_dir = tmp_path / "qmt_strategy"
    state_dir.mkdir()
    state_file = state_dir / "state.json"
    state_file.write_text(json.dumps({
        "date": "2026-07-01",
        "stocks": {
            "603501.SH": {
                "stop_loss_triggered": False,
                "trade_count_today": 0,
                "sold_today": False,
                "stop_loss_base": 50.0,
                "expected_qty": 1000
            }
        },
        "daily_stop_count": 0
    }))

    # 券商实际持仓 2000 股
    pos = MagicMock()
    type(pos).m_volume = PropertyMock(return_value=2000)
    type(pos).m_avgPrice = PropertyMock(return_value=50.0)
    type(pos).profit_rate = PropertyMock(return_value=0.0)
    monkeypatch.setattr('xtquant.xttrader.query_stock_position',
                        MagicMock(return_value=pos))

    return state_dir
```

---

## 附录 A：统一 Fixture 模板

```python
# conftest.py（放在 integration/ 目录下）
import pytest
import numpy as np
import json
from unittest.mock import MagicMock, PropertyMock, patch

@pytest.fixture
def mock_datetime_1455(monkeypatch):
    """固定时间为 2026-07-02 14:55:01"""
    import datetime
    class FakeDT(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 7, 2, 14, 55, 1)
    monkeypatch.setattr('datetime.datetime', FakeDT)
    return '2026-07-02', '14:55:01'

@pytest.fixture
def mock_datetime_1030(monkeypatch):
    """固定时间为 2026-07-02 10:30:00"""
    import datetime
    class FakeDT(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 7, 2, 10, 30, 0)
    monkeypatch.setattr('datetime.datetime', FakeDT)

@pytest.fixture
def mock_60bars_numpy():
    """生成 60 根标准日线的 numpy 数组"""
    rng = np.random.default_rng(42)
    base_price = 50.0
    dates = np.arange(60)

    close = base_price + np.cumsum(rng.normal(0, 0.5, 60))
    high  = close + rng.uniform(0.1, 1.0, 60)
    low   = close - rng.uniform(0.1, 1.0, 60)
    open_ = close - rng.normal(0, 0.3, 60)
    volume = rng.integers(200000, 2000000, 60)

    return {
        'close': close.astype(np.float64),
        'open': open_.astype(np.float64),
        'high': high.astype(np.float64),
        'low': low.astype(np.float64),
        'volume': volume.astype(np.float64),
    }

@pytest.fixture
def make_position():
    """工厂函数：按需构造模拟持仓对象"""
    def _make(m_volume=0, m_avgPrice=50.0, profit_rate=0.0):
        pos = MagicMock()
        type(pos).m_volume = PropertyMock(return_value=m_volume)
        type(pos).m_avgPrice = PropertyMock(return_value=m_avgPrice)
        type(pos).profit_rate = PropertyMock(return_value=profit_rate)
        return pos
    return _make

@pytest.fixture
def make_asset():
    """工厂函数：构造模拟总资产对象"""
    def _make(m_dBal=500000.0, m_dCash=200000.0):
        asset = MagicMock()
        type(asset).m_dBal = PropertyMock(return_value=m_dBal)
        type(asset).m_dCash = PropertyMock(return_value=m_dCash)
        return asset
    return _make
```

---

## 附录 B：passorder Spy 记录器

```python
@pytest.fixture
def passorder_spy(monkeypatch):
    """替换 passorder 为 spy，记录所有调用参数"""
    calls = []

    def spy_passorder(opType, orderType, accountid, stock_code,
                       prType, price, volume, strategyName,
                       quickTrade, orderId, ctx):
        calls.append({
            'opType': opType,
            'orderType': orderType,
            'accountid': accountid,
            'stock_code': stock_code,
            'prType': prType,
            'price': price,
            'volume': volume,
            'strategyName': strategyName,
            'quickTrade': quickTrade,
            'orderId': orderId,
        })
        return f'ORDER_ID_{len(calls):04d}'  # 返回伪订单 ID

    monkeypatch.setattr('half_position_rolling.passorder', spy_passorder)
    spy_passorder.call_count = property(lambda self: len(calls))
    spy_passorder.call_args_list = calls
    return spy_passorder
```

---

## 附录 C：G 对象重置 Fixture

```python
@pytest.fixture(autouse=True)
def reset_G(monkeypatch):
    """每个集成测试前重置全局 G 对象状态"""
    import half_position_rolling as strat
    from collections import defaultdict

    strat.g.trade_count_today = defaultdict(int)
    strat.g.sold_today = defaultdict(lambda: False)
    strat.g.stop_loss_triggered = defaultdict(lambda: False)
    strat.g.last_signal_time = None
    strat.g.daily_stop_count = 0
    strat.g.last_date = None

    # 重置 _ctx（避免前一个测试的 mock 泄漏）
    strat._ctx = None

    return strat.g
```

---

## 用例覆盖矩阵

| 用例 ID | 被测功能 | 入口函数 | 涉及 mock | 优先级 |
| :--- | :--- | :--- | :--- | :--- |
| I-INT-001 | F1 F14 F16 F8 F10 | `init()` | download + position + asset + state | P0 |
| I-INT-002 | F19 F7 防重复 | `handlebar()` | 时间 mock（无行情） | P0 |
| I-INT-003 | F2 F3 F4 F19 F9 F10 | `handlebar()` → `on_bar()` | full_tick + market_data + position + asset + passorder | P0 |
| I-INT-004 | F6 F8 | `handlebar()` → 止损检查 | position(profit_rate=-0.18) + passorder | P0 |
| I-INT-005 | F18 | `init()` | state.json + override.json | P0 |
| I-INT-006 | F16 | `init()` | position(volume=2000) vs state(expected=1000) | P0 |
