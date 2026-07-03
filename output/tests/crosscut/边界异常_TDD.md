# 边界异常层 TDD 测试设计

> 目标策略：`half_position_rolling.py`（QMT 内置 Python 量化策略）
> 覆盖范围：状态持久化容错 / 数据异常处理 / 下单边界 / 跨日重置 / 资源不足
> 产物版本：v1.0 | 2026-07-02
> 验收门禁：全部 P0 + P1 用例通过 = 边界异常层通过

---

## 测试策略说明

边界异常层的测试目的不是"验证正常路径"，而是"证明策略在脏数据 / 坏环境 / 资源不足时不会崩溃，且行为可预期"。

**关键假设**（来自技术方案 / PRD）：
- 状态文件格式为 JSON，原子写（`.tmp` → `os.replace`）
- override.json 为简单的一维数组 `["code1", "code2"]`
- 历史数据取 60 根日线，不足 60 跳过
- 每日跨日时：`trade_count_today` / `sold_today` / `daily_stop_count` 归零；`stop_loss_triggered` 保留
- 下单失败（order_id=None）→ 当日不再重试该股
- init 阶段下载失败 → 重试 3 次，仍失败跳过

---

## C-EDGE-001 state.json 缺失——首次启动自动创建默认状态

**严重级**：P0（策略启动失败 = 无法运行）
**触发条件**：策略所在目录不存在 `state.json`
**来源**：PRD §8 风控体系 / 技术方案 §4.3 状态持久化

### Given

- 策略首次部署，运行目录下仅有 `half_position_rolling.py`，无 `state.json`
- `STOCK_POOL` 定义了 3 只股票：`["603501.SH", "00700.HGT", "01810.SGT"]`

### When

`init()` 执行到状态加载阶段，调用 `load_state()` → `os.path.exists('state.json')` 返回 `False`

### Then

1. 日志输出 `INFO | 首次启动，未找到 state.json，将创建默认状态文件`
2. `state.json` 被创建，内容为默认结构：

```json
{
  "date": "<当前日期>",
  "stocks": {
    "603501.SH": {
      "stop_loss_triggered": false,
      "trade_count_today": 0,
      "sold_today": false,
      "stop_loss_base": null
    },
    "00700.HGT": { ... },
    "01810.SGT": { ... }
  },
  "daily_stop_count": 0
}
```

3. 策略正常继续执行（init 不中断，handlebar 可正常触发）
4. `init()` 完成后日志输出 `INFO | state.json 初始化完成，共 3 只股票`

### 预期失败原因

若 `load_state()` 对文件缺失直接抛异常而不创建默认文件，`init()` 将中断，导致策略无法运行——首次部署即失败。

---

## C-EDGE-002 state.json 损坏——JSON 解析失败，重建默认状态

**严重级**：P0（状态文件损坏 = 策略无法启动）
**触发条件**：`state.json` 内容非法（如意外写入一半、手动编辑出错、磁盘故障导致文件截断）
**来源**：PRD §11 附录 C 故障排查 #6 / 技术方案 §4.3

### Given

- `state.json` 存在但内容损坏，例如缺少闭合括号：

```json
{"date": "2026-07-02", "stocks": {"603501.SH": {"stop_loss_trig
```

### When

`init()` 调用 `json.load()` 解析 `state.json`，触发 `json.JSONDecodeError`

### Then

1. WARNING 日志包含：
   - 错误原因（`JSONDecodeError: ...`）
   - 文件路径
   - 提示"state.json 解析失败，将重建默认状态"
2. 策略**不崩溃**，创建新的默认 `state.json`（同 C-EDGE-001 结构）
3. **重要行为取舍**：原文件内容全部丢失（含止损标记）。WARNING 日志中明确提示"止损状态可能需要手动恢复"
4. 策略正常继续执行

### 预期失败原因

若 `json.load()` 异常未被捕获，策略直接崩溃退出，无法自愈。

---

## C-EDGE-003 state.json 字段缺失——补默认值不崩溃

**严重级**：P1（部分字段缺失 = 功能降级但不中断）
**触发条件**：`state.json` 合法但缺少某些字段（版本升级新增字段、手动编辑遗漏）
**来源**：技术方案 §4.3 STATE_SCHEMA / 测试决策蓝图 §2 边界异常层

### 场景 3a：`stocks` 为空对象 `{}`

#### Given

```json
{"date": "2026-07-02", "stocks": {}, "daily_stop_count": 0}
```

（例如用户手动编辑 state.json 清空了 stocks，但策略中 STOCK_POOL 有 3 只股票）

#### When

`init()` 加载 state 后，遍历 `STOCK_POOL` 初始化各股状态

#### Then

1. 对 `STOCK_POOL` 中的每只股票，若在 `stocks` 中不存在，自动补入默认条目
2. WARNING 日志：`603501.SH 在 state.json 中缺失，已补默认值`
3. 最终 `state.json` 写回完整结构
4. 策略正常继续

#### 预期失败原因

若代码直接 `state["stocks"]["603501.SH"]["stop_loss_triggered"]` 而不检查键是否存在，`KeyError` 导致崩溃。

### 场景 3b：某只股票缺少部分字段

#### Given

```json
{
  "date": "2026-07-02",
  "stocks": {
    "603501.SH": {
      "stop_loss_triggered": false
    }
  },
  "daily_stop_count": 0
}
```

（`603501.SH` 缺少 `trade_count_today` / `sold_today` / `stop_loss_base` 字段）

#### When

`init()` 或 `handlebar()` 中读取该股状态字段

#### Then

1. 缺失字段自动补默认值：`trade_count_today=0`, `sold_today=False`, `stop_loss_base=None`
2. WARNING 日志：`603501.SH 状态字段不完整（缺少 trade_count_today,sold_today,stop_loss_base），已补默认值`
3. 策略不崩溃，信号判定正常执行

### 场景 3c：`daily_stop_count` 字段缺失

#### Given

```json
{"date": "2026-07-02", "stocks": { "603501.SH": {...} }}
```

#### When

跨日重置逻辑读取 `daily_stop_count`

#### Then

1. `daily_stop_count` 补默认值 `0`
2. 策略正常继续，不崩溃

---

## C-EDGE-004 override.json 存在且合法——重置止损标记，删除文件

**严重级**：P0（止损恢复流程的核心路径）
**触发条件**：用户手动创建 `override.json` 写入 `["603501.SH"]`
**来源**：PRD §8 F18 止损恢复 / 技术方案 §4.3 override.json 结构

### Given

- `state.json` 中 `603501.SH.stop_loss_triggered = true`
- 用户创建 `override.json`，内容：`["603501.SH"]`（合法 JSON 数组）

### When

`init()` 执行 `load_state()` → 检测 `os.path.exists('override.json')` → `True` → 解析

### Then

1. `603501.SH.stop_loss_triggered` 重置为 `false`
2. `603501.SH.trade_count_today` 重置为 `0`（恢复当日可交易）
3. INFO 日志：`override.json 检测到 1 只股票，已重置止损标记: ['603501.SH']`
4. `override.json` 被**删除**（一次性指令，不能重复执行）
5. 更新后的状态写入 `state.json`
6. 对应股票后续可正常交易

---

## C-EDGE-005 override.json 存在但损坏——跳过恢复，不崩溃不删除

**严重级**：P1（用户操作出错不应导致策略崩溃）
**触发条件**：`override.json` 格式错误——非数组 / 缺括号 / 内含非字符串 / 乱码
**来源**：技术方案 §4.3 / 测试决策蓝图 §2 边界异常层

### 场景 5a：override.json 不是数组

#### Given

- `override.json` 内容：`{"603501.SH": true}`（JSON 对象而非数组）

#### When

`init()` 解析 `override.json`，`json.load()` 返回 `dict` 而非 `list`

#### Then

1. WARNING 日志：`override.json 格式错误：期望数组（list），实际为 dict。已忽略，文件未删除`
2. **不崩溃**
3. **文件不删除**（保留坏文件供用户排查）
4. 策略正常启动，止损状态不变

### 场景 5b：override.json JSON 解析失败

#### Given

- `override.json` 内容：`["603501.SH",`（缺闭合括号）

#### When

`init()` 调用 `json.load()` 触发 `JSONDecodeError`

#### Then

1. WARNING 日志：`override.json 解析失败：JSONDecodeError: ...。已忽略，文件未删除，请手动修复`
2. **不崩溃，不删除文件**
3. 策略正常启动

### 场景 5c：override.json 内含非字符串元素

#### Given

- `override.json` 内容：`["603501.SH", 123, true]`（包含数字和布尔）

#### When

`init()` 遍历数组中每个元素做止损重置

#### Then

1. WARNING 日志：`override.json 元素 #2 不是合法股票代码（类型 int），已跳过`
2. 合法的 `"603501.SH"` 正常重置
3. 所有合法项处理后，`override.json` 被删除
4. 策略正常继续

### 场景 5d：override.json 内包含未知股票代码

#### Given

- `override.json` 内容：`["000001.SZ"]`（不在 STOCK_POOL 中）

#### When

`init()` 尝试重置对应股票

#### Then

1. WARNING 日志：`override.json 中的 000001.SZ 不在当前股票池中，已跳过`
2. 不崩溃
3. `override.json` 仍被删除（已处理的指令）
4. 策略正常继续

---

## C-EDGE-006 override.json 存在且为空数组——无操作，正常删除

**严重级**：P2（边界行为，不应出错）
**触发条件**：用户创建了 `override.json`，但内容为 `[]`

### Given

- `override.json` 内容：`[]`

### When

`init()` 解析 `override.json`，得到空列表

### Then

1. INFO 日志：`override.json 为空数组，无股票需恢复`
2. `override.json` 被删除
3. 策略正常启动，止损状态不变

---

## C-EDGE-007 历史数据不足 60 根——该股当日跳过，不打 ERROR

**严重级**：P1（新股常见场景，不应中断策略）
**触发条件**：某只股票上市不足 60 个交易日
**来源**：PRD §5 实现约束 / 技术方案 §3.2

### Given

- `STOCK_POOL` 中有一只新股（上市仅 15 天），其余 2 只为老股
- `get_market_data_ex()` 返回该新股仅 15 根日线数据

### When

`handlebar()` 在 14:55 执行信号判定，遍历股票池

### Then

1. 对该新股：检测到 `len(close_array) < 60`
2. INFO 日志：`<code> 历史数据不足 60 根（实际 15 根），该股今日跳过信号判定`
3. **不打印 ERROR**——这是预期场景（新股），不是程序异常
4. 策略继续处理下一只股票
5. 股票池中其他正常股票不受影响

### 预期失败原因

若将此场景当成 ERROR 打印，会污染错误监控，掩盖真正需要关注的异常。

---

## C-EDGE-008 行情返回 None——该股跳过，不崩溃

**严重级**：P1（行情数据偶发缺失不应崩溃）
**触发条件**：`ContextInfo.get_full_tick([stock_code])` 返回 `None`
**来源**：PRD §9 错误处理策略 / 技术方案 §4.1

### Given

- 14:55 信号判定时，`get_full_tick(['603501.SH'])` 返回 `None`（网络抖动 / 数据未就绪）

### When

`handlebar()` 中调用 `get_full_tick` 后检查返回值为 `None`

### Then

1. WARNING 日志：`603501.SH 实时行情返回 None，该股今日跳过信号判定`
2. 不为该股计算指标、不判定信号、不下单
3. 策略继续处理股票池中下一只股票
4. 日志不打印 traceback

### 预期失败原因

若直接访问 `tick['close']` 而不判断 `None`，`TypeError: 'NoneType' object is not subscriptable` 导致 handlebar 崩溃。

---

## C-EDGE-009 行情返回空字段——close/open 为 0，跳过不崩溃

**严重级**：P1（数据异常不应进入信号计算）
**触发条件**：`get_full_tick` 返回了 dict 但 `close` / `open` 字段为 `0` 或不存在
**来源**：技术方案 §4.1 / PRD §9

### Given

- `get_full_tick(['603501.SH'])` 返回 `{'close': 0, 'open': 0, 'high': 0, ...}`（涨跌停或数据异常）

### When

`handlebar()` 中获取 tick 后检查关键字段值

### Then

1. WARNING 日志：`603501.SH 行情字段异常（close=0），该股今日跳过信号判定`
2. 不执行信号判定和下单
3. 策略继续处理下一只股票

### 场景 9b：字段缺失

#### Given

- `get_full_tick` 返回 `{'high': 45.2, 'low': 44.1}`（缺少 `close` / `open` 字段）

#### When

代码尝试读取 `tick['close']`

#### Then

1. 使用 `.get('close')` 安全访问，返回 `None` → 检测为无效
2. WARNING 日志：`603501.SH 行情缺少 close 字段，该股今日跳过信号判定`
3. 不崩溃

---

## C-EDGE-010 可用资金不足——跳过买入，打 INFO 或 WARNING

**严重级**：P1（资金不足是正常业务场景，不是错误）
**触发条件**：`query_stock_asset().cash` < 买入所需资金
**来源**：PRD §3 F15 全局仓位上限 / 技术方案 §4.2

### Given

- 策略判定 B1 信号触发，需买入 200 股 × 120 元 = 24000 元
- `query_stock_asset().cash` 返回 5000 元（T+2 资金未到账 / 仓位已满）

### When

`handlebar()` 执行买入逻辑，计算 `cost = qty × price × 1.002`

### Then

1. INFO 日志：`603501.SH B1 买入信号触发，但可用资金不足（需要 ¥24000.00，可用 ¥5000.00），跳过买入`
2. 该股买入信号**不执行**
3. 不打印 ERROR（不是程序异常）
4. 策略继续处理下一只股票

### 预期失败原因

若资金检查遗漏，`passorder` 会因资金不足被 QMT 拦截，可能返回错误订单——依赖券商底层拦防不可靠，策略层应做检查。

---

## C-EDGE-011 持仓为 0 时触发卖出信号——跳过，不报错

**严重级**：P1（无持仓卖出是逻辑分支，不应报错）
**触发条件**：`query_stock_position` 返回持仓数量为 0 或 `None`，但信号判定触发了 S1/S2/S3
**来源**：测试决策蓝图 §2 边界异常层

### Given

- `query_stock_position('603501.SH')` 返回 `pos.volume = 0`（可能是信号触发后当日已卖出、或止损后已清仓、或状态与券商不一致）
- 信号判定返回 `S1`（close 跌破 MA20）

### When

`handlebar()` 执行卖出逻辑

### Then

1. INFO 日志：`603501.SH S1 卖出信号触发，但当前持仓为 0，跳过卖出`
2. 不调用 `passorder`
3. 不打印 WARNING 或 ERROR（持仓为 0 是正常状态漂移）
4. 若该信号是当日第一次判定，不做额外标记

### 预期失败原因

若不检查持仓直接计算 `卖出量 = 0 // 2 = 0`，虽然 `passorder` 可能拦截 0 量订单，但不应发出无效请求。

---

## C-EDGE-012 跨日重置——每日状态字段归零

**严重级**：P0（每日交易计数正确性 = 风控基础）
**触发条件**：`date` 发生变化（从 07-01 变为 07-02）
**来源**：PRD §6 状态持久化 / 技术方案 §7.2 G 对象

### Given

- 前一日 (07-01) 状态：
  - `603501.SH.trade_count_today = 3`
  - `603501.SH.sold_today = True`
  - `00700.HGT.trade_count_today = 1`
  - `daily_stop_count = 1`
- 当日 (07-02) 第一次 `handlebar()` 触发

### When

`handlebar()` 检测到 `g.last_date != today`，执行跨日重置

### Then

1. 所有股票的 `trade_count_today` → `0`
2. 所有股票的 `sold_today` → `False`
3. `daily_stop_count` → `0`
4. `g.last_date` → `"2026-07-02"`
5. `state.json` 写回更新后的值
6. INFO 日志：`跨日检测：2026-07-01 → 2026-07-02，每日状态已重置`

### 场景 12b：非交易日跳日（周末/节假日）

#### Given

- `last_date = "2026-07-03"`（周五），新一次 handlebar `today = "2026-07-06"`（周一）

#### When

跨日检测触发

#### Then

1. 正常执行跨日重置（逻辑不区分是否有交易日间隔）
2. INFO 日志：`跨日检测：2026-07-03 → 2026-07-06，每日状态已重置`

---

## C-EDGE-013 跨日不重置止损——stop_loss_triggered 跨日保留

**严重级**：P0（止损标记持久性是风控核心）
**触发条件**：`date` 变化后 `stop_loss_triggered` 必须保持
**来源**：PRD §6 "跨日不重置" / 技术方案 §7.2

### Given

- 07-01 盘中 `603501.SH` 触发止损：
  - `603501.SH.stop_loss_triggered = true`
  - `state.json` 已持久化
- 07-02 第一次 `handlebar()` 触发

### When

跨日重置逻辑执行

### Then

1. `trade_count_today` / `sold_today` / `daily_stop_count` 已归零（C-EDGE-012）
2. `603501.SH.stop_loss_triggered` **保持 `true`**，不被重置
3. WARNING 日志：`603501.SH 止损标记仍为触发状态（跨日保留）。如需恢复，请创建 override.json`
4. 该股当日不参与信号判定，不下单
5. `state.json` 中 `stop_loss_triggered` 字段保持不变

### 预期失败原因

若跨日重置时将 `stop_loss_triggered` 也归零，止损保护将失效——第二天止损股重新买入，违背"持久暂停"设计意图。

---

## C-EDGE-014 手数为 0——计算出的下单量 < 1 手，不下单

**严重级**：P1（无效下单不应发出）
**触发条件**：目标买入量不足 1 手（资金太少 / 股价太高 / 港股 lot_size 大）
**来源**：技术方案 §5.4 港股手数查询 / PRD §3 F3 半仓滚动

### 场景 14a：A 股买入量 < 100 股

#### Given

- `603501.SH` 目标买入量 = 80 股（资金不足）

#### When

买入逻辑计算后，`qty < 100`

#### Then

1. INFO 日志：`603501.SH 买入量 80 股不足 1 手（100 股），跳过买入`
2. 不调用 `passorder`

### 场景 14b：A 股卖出量 < 100 股

#### Given

- 当前持仓 = 120 股，卖出量 = `120 // 2 = 60` 股

#### When

卖出逻辑计算后，`qty < 100`

#### Then

1. INFO 日志：`603501.SH 卖出量 60 股不足 1 手（100 股），跳过卖出`

### 场景 14c：港股整手对齐后为 0

#### Given

- `00700.HGT` 目标买入量 = 50 股（资金不足）
- `get_instrument_detail` 返回 `VolumeMultiple = 100`

#### When

`qty = (qty // 100) * 100 → 0`

#### Then

1. INFO 日志：`00700.HGT 买入量 50 股整手对齐后为 0，跳过买入`
2. 不调用 `passorder`

### 场景 14d：手数为负（bug 防御）

#### Given

- 因计算异常，`qty = -50`

#### When

买入/卖出逻辑检测到负值

#### Then

1. WARNING 日志：`603501.SH 下单量计算异常（qty=-50），跳过本次交易`
2. 不调用 `passorder`

---

## C-EDGE-015 下单返回 None——记录 ERROR，当日不再重试该股

**严重级**：P1（下单失败需要记录，但不中断策略）
**触发条件**：`passorder()` 返回 `None` 或空字符串
**来源**：PRD §9 错误处理策略 / 技术方案 §5.2 下单错误处理

### Given

- 14:55 信号判定触发 B1 买入
- `passorder(...)` 返回 `order_id = None`（券商拒绝 / 网络异常）

### When

`order_id` 检查为 `None`

### Then

1. ERROR 日志：`603501.SH 下单失败，passorder 返回空订单ID。原因可能：网络异常 / 券商拒绝 / 参数无效`
2. 该股**当日不再重试下单**（设置当日黑名单标记）
3. 策略继续处理股票池中下一只股票
4. 当日后续 `handlebar()` 不再为该股重复发单
5. 次日（跨日后）该标记随 `sold_today` 等一同重置

### 预期失败原因

若不设当日不再重试标记，每个 3 秒 tick 都会重复调用 `passorder`，可能造成大量无效请求甚至重复下单。

---

## C-EDGE-016 init 阶段数据下载失败——重试 3 次，仍失败跳过该股

**严重级**：P1（单股数据缺失不应阻塞整个策略初始化）
**触发条件**：`xtdata.download_history_data()` 在 init 阶段抛异常
**来源**：PRD §9 错误处理策略 / 技术方案 §8.6 风险与缓解

### Given

- `STOCK_POOL` 中 `603501.SH` 数据下载失败（网络超时 / QMT 未登录）
- 其余 2 只股票数据下载正常

### When

`init()` 遍历股票池调用 `download_history_data()`，第 1 次失败 → 等 2 秒 → 重试 → 第 2 次失败 → 等 2 秒 → 重试 → 第 3 次失败

### Then

1. 每次失败：WARNING 日志 `603501.SH 历史数据下载失败（第 N/3 次重试）：<异常信息>`
2. 3 次均失败后：ERROR 日志 `603501.SH 历史数据下载 3 次重试全部失败，该股将从今日股票池中排除`
3. 该股加入当日排除列表（不参与 handlebar 信号判定）
4. `init()` **不中断**，继续下载下一只股票
5. init 完成摘要中注明：`股票池 3 只，实际可用 2 只（603501.SH 数据下载失败）`
6. 日志中 WARNING 和 ERROR 均受限频规则管控

### 场景 16b：全部股票下载失败

#### Given

- 所有 3 只股票 `download_history_data()` 均失败

#### When

`init()` 全部重试 3 次后均失败

#### Then

1. ERROR 日志：`所有 3 只股票历史数据下载均失败，策略将正常运行但无股票可用于信号判定`
2. `init()` 不崩溃，策略正常进入 handlebar 循环
3. 每个 `handlebar()` 中检测到无可用股票时，跳过信号判定
4. 控制台每分钟心跳输出：`股票池 3 只，实际可用 0 只——请检查网络和 QMT 登录状态`

### 场景 16c：重试期间部分成功

#### Given

- 第 1 次下载：全部 3 只失败
- 第 2 次重试：`603501.SH` 成功，其余 2 只仍失败
- 第 3 次重试：2 只仍失败

#### When

每次重试只针对本轮失败的股票

#### Then

1. `603501.SH` 在第 2 次成功后从重试列表中移除
2. 剩余 2 只在 3 次失败后标记排除
3. 最终结果：1 只可用，2 只排除
4. init 完成摘要准确反映最终状态

---

## 用例优先级汇总

| 优先级 | 条数 | 用例 ID |
|--------|------|---------|
| **P0** | 5 | C-EDGE-001, 002, 004, 012, 013 |
| **P1** | 10 | C-EDGE-003, 005, 007, 008, 009, 010, 011, 014, 015, 016 |
| **P2** | 1 | C-EDGE-006 |

**P0 = STOP-SHIP**：任意一条不通过就不能上线，因为涉及策略启动失败 / 止损标记丢失 / 跨日状态污染。

**P1 = 必须修复**：数据/行情异常时策略不应崩溃，未覆盖的场景可能导致实盘中因网络抖动或新股数据不足而整体中断。

---

## 测试环境要求

| 维度 | 要求 |
|------|------|
| 执行环境 | 本地 Python 3.x（脱离 QMT 运行） |
| Mock 对象 | `json.load` / `os.path` / `os.replace` 可通过 monkeypatch 控制行为 |
| 行情 Mock | 模拟 `get_full_tick` / `get_market_data_ex` 返回 None/空/异常数据 |
| 交易 Mock | 模拟 `passorder` 返回 None/合法 ID |
| 文件系统 | 使用 `tmp_path` 隔离，不污染实际项目目录 |
| 测试框架 | `pytest` + fixtures |
