# 技术指标计算 单元测试

> 生成时间：2026-07-02
> 基于 PRD：output/PRD详细版.md §5 + 技术方案 output/技术方案.md §3
> 测试框架：pytest + numpy
> 对应模块：`calc_indicators()` + `_rolling_mean()`

## 元信息

- **层**：单元
- **对应模块**：`calc_indicators(open_arr, high_arr, low_arr, close_arr, vol_arr)` —— 返回 15 个指标数组
- **辅助函数**：`_rolling_mean(arr, window)` —— 简单移动平均，前 window-1 位置填充 np.nan
- **约束**：纯 numpy 实现，不依赖 pandas；QMT 内置 Python 环境
- **测试框架**：pytest + numpy
- **输入来源**：PRD §5 指标列表 + 技术方案 §3 numpy 约束
- **指标总数**：15
  - 基础均线：`ma5, ma10, ma20`
  - 量能：`vol_ma5, vol_ratio`
  - K 线形态：`body_abs, range_, upper_shadow, lower_shadow, is_bullish`
  - 高级形态：`long_upper, long_lower`
  - 趋势判定：`ma_bull, new_high20`
  - 复合信号：`break_3ma, close_ab_ma20, close_ab_ma20_prev`

### 核心阈值常量

| 常量 | 值 | 用途 |
|------|-----|------|
| `SHADOW_RATIO` | 2.0 | 长影线判定：影线长 > 实体 × 2 |
| `SHADOW_PCT` | 0.40 | 长影线判定：影线长 > 振幅 × 40% |
| `VOL_RATIO_LOW` | 0.7 | S2 缩量阈值 |
| `VOL_RATIO_MID` | 1.5 | S3/B2 放量阈值 |
| `VOL_RATIO_HIGH` | 2.0 | B3 强放量阈值 |

> **注意**：`close_ab_ma20` / `close_ab_ma20_prev` 表示收盘价相对于 MA20 的位置状态，涉及跨日状态切换。本测试文档聚焦单次 `calc_indicators()` 计算出的布尔值，跨日切换逻辑在信号判定测试中覆盖。

---

## 用例

### U-TECH-001 · MA5 正常计算
- **优先级**：P0
- **Given**：收盘价 `[10, 10.5, 11, 10.8, 11.2]`，窗口=5
- **When**：调用 `_rolling_mean(close_arr, 5)`
- **Then**：
  - `result[0..3]` 均为 `np.nan`（前 window-1=4 个位置）
  - `result[4] ≈ 10.7`（即 `(10 + 10.5 + 11 + 10.8 + 11.2) / 5`）
- **预期失败原因**：若初版未正确处理 NaN 填充，前 4 个值会报错或返回 0；若除法写成整数除法，结果不是浮点数

### U-TECH-002 · MA10 正常计算
- **优先级**：P0
- **Given**：10 日收盘价 `[10, 11, 12, 13, 14, 15, 14, 13, 12, 11]`
- **When**：调用 `_rolling_mean(close_arr, 10)`
- **Then**：
  - `result[0..8]` 均为 `np.nan`
  - `result[9] = 12.5`（总和 125 / 10）
- **预期失败原因**：NaN 填充逻辑偏移一位（window-1 写成 window），导致最后一个有效值位置错误

### U-TECH-003 · MA20 正常计算
- **优先级**：P0
- **Given**：20 日收盘价，前 19 日为 10，第 20 日为 20
- **When**：调用 `_rolling_mean(close_arr, 20)`
- **Then**：
  - `result[0..18]` 均为 `np.nan`
  - `result[19] = (19 × 10 + 20) / 20 = 10.5`
- **预期失败原因**：数据长度刚好等于窗口时边界处理错误；`np.convolve` 模式选 `'full'` 会导致长度不对

### U-TECH-004 · 不足窗口长度时全部 NaN
- **优先级**：P1
- **Given**：收盘价 `[10, 10.5, 11]`（仅 3 根），窗口=5
- **When**：调用 `_rolling_mean(close_arr, 5)`
- **Then**：全部 3 个值均为 `np.nan`（因为没有任何位置能凑够 5 根）
- **预期失败原因**：numpy 的 `convolve` 在数据短于窗口时仍会输出部分有效值（取决于 mode），需显式用 NaN 覆盖

### U-TECH-005 · MA 全是相同值
- **优先级**：P1
- **Given**：5 日收盘价均为 `[10, 10, 10, 10, 10]`
- **When**：调用 `_rolling_mean(close_arr, 5)`
- **Then**：`result[4] = 10.0`
- **预期失败原因**：无。此用例为 sanity check —— 确保等值数组不会触发异常除零或类型错误

### U-TECH-006 · MA 含涨停跳空（极端涨跌幅）
- **优先级**：P2
- **Given**：收盘价 `[10, 11, 12.1, 0, 13.31]`（含涨停跳空 10% 和跌停到极值场景）
- **When**：调用 `_rolling_mean(close_arr, 5)`
- **Then**：`result[4] = (10 + 11 + 12.1 + 0 + 13.31) / 5 = 9.282`
- **预期失败原因**：数据中 0 值不应被视为缺失数据——是真实的跌停价；若误判 0 为无效值而剔除，会导致均值虚高

---

### U-TECH-007 · vol_ma5 正常计算
- **优先级**：P1
- **Given**：成交量 `[1000, 1200, 1100, 1300, 1400]`
- **When**：调用 `_rolling_mean(vol_arr, 5)`
- **Then**：`vol_ma5[4] = 1200.0`，`vol_ma5[0..3]` 为 `np.nan`
- **预期失败原因**：同 MA5，NaN 填充位置偏移

### U-TECH-008 · vol_ratio 正常放量
- **优先级**：P0
- **Given**：当日量=2000，`vol_ma5[-1]=1000`
- **When**：调用 `calc_indicators()` 计算 vol_ratio
- **Then**：`vol_ratio[-1] = 2.0`
- **预期失败原因**：vol_ratio 依赖 vol_ma5 的有效值——若 vol_ma5 还是 NaN，vol_ratio 也会是 NaN，导致信号判定跳过

### U-TECH-009 · vol_ratio 正常缩量
- **优先级**：P1
- **Given**：当日量=500，`vol_ma5[-1]=1000`
- **When**：计算 `vol_ratio`
- **Then**：`vol_ratio[-1] = 0.5`
- **预期失败原因**：同 U-TECH-008

### U-TECH-010 · vol_ratio 除零保护 —— vol_ma5 为 0
- **优先级**：P0
- **Given**：当日量=1000，`vol_ma5[-1]=0`（成交量为 0 的极端情况，如长期停牌后刚复牌无量的几日）
- **When**：计算 `vol_ratio`
- **Then**：不应抛出异常（如 `ZeroDivisionError`）；`vol_ratio[-1]` 应为 `np.inf` 或一个安全的大值（如 `np.nan` 并附带日志告警）
- **预期失败原因**：直接做 `vol / vol_ma5` 不带保护，导致 `ZeroDivisionWarning` 或 `inf` 传播到后续比较逻辑引发不可预期的布尔判定

### U-TECH-011 · vol_ratio 除零保护 —— vol_ma5 为 NaN
- **优先级**：P1
- **Given**：数据不足 5 根日线，`vol_ma5[-1]` 为 `np.nan`
- **When**：计算 `vol_ratio`
- **Then**：`vol_ratio[-1]` 为 `np.nan`（不崩溃）
- **预期失败原因**：numpy 的 NaN 除法本身不抛异常，但下游使用 `vol_ratio >= 1.5` 时 NaN 比较始终为 False。若期望放量买入信号，NaN 会静默跳过——需日志告警或调用方检查

---

### U-TECH-012 · body_abs 阳线实体
- **优先级**：P1
- **Given**：open=10, close=12（收涨 20%）
- **When**：计算 `body_abs = abs(close - open)`
- **Then**：`body_abs = 2.0`
- **预期失败原因**：若写成 `close - open` 不带 abs，阴线时得到负值，后续 `long_upper` / `long_lower` 比较会因正负号错误判定

### U-TECH-013 · body_abs 阴线实体
- **优先级**：P1
- **Given**：open=12, close=10（收跌）
- **When**：计算 `body_abs = abs(close - open)`
- **Then**：`body_abs = 2.0`（阳线阴线结果相同）
- **预期失败原因**：同上——不带 abs 导致负数实体长度

### U-TECH-014 · body_abs 一字板（实体为 0）
- **优先级**：P1
- **Given**：open=10, close=10（一字涨停/跌停，或极端平收）
- **When**：计算 `body_abs`
- **Then**：`body_abs = 0.0`
- **预期失败原因**：无。纯功能验证——确保 0 实体不会导致后续除法异常

### U-TECH-015 · range_ 正常计算
- **优先级**：P1
- **Given**：high=12.5, low=9.8
- **When**：计算 `range_ = high - low`
- **Then**：`range_ = 2.7`
- **预期失败原因**：基本减法，不易出错；但若数据顺序传错（如 open 和 high 弄反），结果会异常

### U-TECH-016 · range_ 一字板（振幅为 0）
- **优先级**：P2
- **Given**：high=10, low=10（一字板）
- **When**：计算 `range_`
- **Then**：`range_ = 0.0`
- **预期失败原因**：同 U-TECH-014 —— 确保 `range_ = 0` 时后续 `SHADOW_PCT` 判定不触发除零

---

### U-TECH-017 · upper_shadow 光头阳线（上影=0）
- **优先级**：P1
- **Given**：open=10, close=12, high=12（收盘价=最高价）
- **When**：计算 `upper_shadow = high - max(open, close)`
- **Then**：`upper_shadow = 0.0`
- **预期失败原因**：若误写为 `high - close`（不取 max），阳线结果正确但阴线会错；若误写为 `high - open`，阴线可能对但阳线错

### U-TECH-018 · upper_shadow 带长上影阳线
- **优先级**：P1
- **Given**：open=10, close=11, high=14（冲高大幅回落）
- **When**：计算 `upper_shadow`
- **Then**：`upper_shadow = 14 - max(10, 11) = 3.0`
- **预期失败原因**：同 U-TECH-017 —— `max(open, close)` 是正确写法，写成 `max(close, open)` 也正确（交换律），写错成单一值才是 bug

### U-TECH-019 · lower_shadow 光脚阴线（下影=0）
- **优先级**：P1
- **Given**：open=12, close=10, low=10（最低价=收盘价）
- **When**：计算 `lower_shadow = min(open, close) - low`
- **Then**：`lower_shadow = 0.0`
- **预期失败原因**：若误写为 `close - low`，阳线时 close > open 导致下影偏大

### U-TECH-020 · lower_shadow 十字星（上下影均 > 实体）
- **优先级**：P2
- **Given**：open=10, close=10, high=11, low=9（标准十字星）
- **When**：计算 `upper_shadow` 和 `lower_shadow`
- **Then**：
  - `body_abs = 0.0`
  - `upper_shadow = 1.0`
  - `lower_shadow = 1.0`
- **预期失败原因**：`body_abs = 0` 时后续 `SHADOW_RATIO` 计算会触发除零——需要用 `np.where` 或 `if body == 0` 保护

### U-TECH-021 · 倒 T 字线（上影长、下影=0、实体=0）
- **优先级**：P2
- **Given**：open=10, close=10, high=12, low=10（收盘=开盘=最低价）
- **When**：计算影线
- **Then**：
  - `upper_shadow = 2.0`
  - `lower_shadow = 0.0`
  - `body_abs = 0.0`
- **预期失败原因**：除零保护——十字星/倒 T 字/正 T 字都是 `body_abs = 0`，`long_upper` 判定需处理此情况

---

### U-TECH-022 · long_upper 触发 —— 刚好满足阈值
- **优先级**：P0
- **Given**：
  - open=10, close=10.5（`body_abs = 0.5`）
  - high=12（`upper_shadow = 1.5`）
  - low=10（`lower_shadow = 0`）
  - `range_ = 2.0`
  - `SHADOW_RATIO = 2.0, SHADOW_PCT = 0.40`
- **When**：计算 `long_upper`
- **Then**：
  - `upper_shadow > body_abs × SHADOW_RATIO` → `1.5 > 0.5 × 2.0 = 1.0` ✅
  - `upper_shadow > range_ × SHADOW_PCT` → `1.5 > 2.0 × 0.40 = 0.8` ✅
  - `long_upper = True`
- **预期失败原因**：两个条件用 `&` 或 `and` 的判断逻辑——若写成 `or` 会过度触发；`>` 写成 `>=` 会多触发边界

### U-TECH-023 · long_upper 不触发 —— 差一点不满足 SHADOW_RATIO
- **优先级**：P0
- **Given**：
  - open=10, close=10.5（`body_abs = 0.5`）
  - high=11.5（`upper_shadow = 1.0`）
  - `upper_shadow（1.0）<= body_abs（0.5）× 2.0（=1.0）`，刚好等于不算 `>`
- **When**：计算 `long_upper`
- **Then**：`long_upper = False`
- **预期失败原因**：`>` 写成 `>=` 会在此边界误判为 True

### U-TECH-024 · long_upper 不触发 —— 差一点不满足 SHADOW_PCT
- **优先级**：P1
- **Given**：
  - open=10, close=10.2（`body_abs = 0.2`）
  - high=11.6（`upper_shadow = 1.4`）
  - low=9.6（`range_ = 2.0`）
  - `upper_shadow(1.4) > body_abs(0.2) × 2.0(=0.4)` ✅
  - `upper_shadow(1.4) > range_(2.0) × 0.40(=0.8)` ✅ — 等等，1.4 > 0.8 满足，这个场景会触发

    修正为刚好不满足 SHADOW_PCT 的场景：
  - open=10, close=10.8（`body_abs = 0.8`）
  - high=11.6（`upper_shadow = 0.8`）
  - low=9.6（`range_ = 2.0`）
  - `upper_shadow(0.8) > body_abs(0.8) × 2.0(=1.6)` ❌ 不满足第一条件
  - `long_upper = False`
- **预期失败原因**：两个条件必须同时满足，漏判其中一个即为 bug

### U-TECH-025 · long_upper 触发 —— 极端长上影（射击之星典型）
- **优先级**：P1
- **Given**：
  - open=10, close=10.1（`body_abs = 0.1`，纺锤线）
  - high=12（`upper_shadow = 1.9`）
  - low=9.9（`range_ = 2.1`）
  - `upper_shadow(1.9) > body_abs(0.1) × 2.0(=0.2)` ✅
  - `upper_shadow(1.9) > range_(2.1) × 0.40(=0.84)` ✅
- **When**：计算 `long_upper`
- **Then**：`long_upper = True`
- **预期失败原因**：极端值下浮点数精度问题——`1.9 > 0.84` 不应被浮点误差吞掉

### U-TECH-026 · long_lower 触发 —— 刚好满足阈值
- **优先级**：P0
- **Given**：
  - open=10.5, close=10（`body_abs = 0.5`，阴线）
  - high=11, low=9.5（`lower_shadow = 0.5`）
  - `range_ = 1.5`
  - `lower_shadow(0.5) > body_abs(0.5) × 2.0(=1.0)` → `0.5 > 1.0` ❌

    重新设计使刚好满足：
  - open=10.3, close=10（`body_abs = 0.3`）
  - high=10.6, low=9.1（`lower_shadow = min(10, 10.3) - 9.1 = 10 - 9.1 = 0.9`）
  - `range_ = 1.5`
  - `lower_shadow(0.9) > body_abs(0.3) × 2.0(=0.6)` ✅
  - `lower_shadow(0.9) > range_(1.5) × 0.40(=0.6)` ✅
- **When**：计算 `long_lower`
- **Then**：`long_lower = True`
- **预期失败原因**：阴线时 `min(open, close) = close`，若误用 open 计算下影会导致值偏大

### U-TECH-027 · long_lower 不触发 —— 影线够长但实体也很长
- **优先级**：P1
- **Given**：
  - open=10, close=12（`body_abs = 2.0`，大阳线）
  - high=13, low=9（`lower_shadow = 1.0, range_ = 4.0`）
  - `lower_shadow(1.0) > body_abs(2.0) × 2.0(=4.0)` ❌
- **When**：计算 `long_lower`
- **Then**：`long_lower = False`（大阳线即使有下影也不够长——因为实体太大了）
- **预期失败原因**：只检查了影线长度，忽略了实体比例约束

### U-TECH-028 · long_lower 触发 —— 锤子线（大下影+小实体）
- **优先级**：P1
- **Given**：
  - open=10, close=10.2（`body_abs = 0.2`）
  - high=10.3, low=9.0（`lower_shadow = min(10, 10.2) - 9.0 = 1.0`）
  - `range_ = 1.3`
  - `lower_shadow(1.0) > body_abs(0.2) × 2.0(=0.4)` ✅
  - `lower_shadow(1.0) > range_(1.3) × 0.40(=0.52)` ✅
- **When**：计算 `long_lower`
- **Then**：`long_lower = True`
- **预期失败原因**：同 U-TECH-026——阴线/阳线对下影计算影响不同

### U-TECH-029 · long_upper/long_lower 当 body_abs=0 时不崩溃
- **优先级**：P0
- **Given**：十字星：open=10, close=10（`body_abs = 0`），high=12, low=9
- **When**：计算 `long_upper` 和 `long_lower`
- **Then**：
  - 计算不被除零中断
  - 根据设计：`long_upper = True`（`upper_shadow=2 > 0×2.0=0` 且 `2 > 3×0.4=1.2`）或 `False`（若实现中对 body=0 特殊处理为 False）
  - **无论哪种设计，不得抛异常**
- **预期失败原因**：`body_abs × SHADOW_RATIO = 0`，与 `upper_shadow > 0` 的比较不会出错；但若实现中某处做了 `upper_shadow / body_abs` 则必然除零崩溃

---

### U-TECH-030 · is_bullish 阳线
- **优先级**：P1
- **Given**：open=10, close=11
- **When**：计算 `is_bullish`
- **Then**：`is_bullish = True`
- **预期失败原因**：若写成 `close >= open` 会把平收也算阳线；S1 破位卖出和 B1 突破买入都依赖 `close > open` 的严格判断

### U-TECH-031 · is_bullish 阴线
- **优先级**：P1
- **Given**：open=11, close=10
- **When**：计算 `is_bullish`
- **Then**：`is_bullish = False`
- **预期失败原因**：基本比较，不易出错；但若后续代码在多处重复实现 `is_bullish`（不一致），可能出现某处用了 `>=`

### U-TECH-032 · is_bullish 平收
- **优先级**：P2
- **Given**：open=10, close=10
- **When**：计算 `is_bullish`
- **Then**：`is_bullish = False`（平收不算阳线）
- **预期失败原因**：`close > open` vs `close >= open` 的选择直接影响 B3 信号——平收一字板不应触发"阳线+站上三线"

---

### U-TECH-033 · ma_bull 成立 —— MA5 > MA10 > MA20
- **优先级**：P0
- **Given**：`ma5[-1]=12.0 > ma10[-1]=11.5 > ma20[-1]=10.0`
- **When**：计算 `ma_bull`
- **Then**：`ma_bull = True`
- **预期失败原因**：三条均线需同时比较，若写成 `ma5 > ma10 and ma10 > ma20` 是对的；若写成 `ma5 > ma10 > ma20` 在 Python 中也是对的（链式比较），在 numpy 中需要用 `&` 和对 NaN 的保护

### U-TECH-034 · ma_bull 不成立 —— MA5 > MA10 但 MA10 < MA20
- **优先级**：P0
- **Given**：`ma5[-1]=12.0 > ma10[-1]=11.5`，但 `ma10[-1]=11.5 < ma20[-1]=12.0`
- **When**：计算 `ma_bull`
- **Then**：`ma_bull = False`（短中期多头但中期弱于长期=不是多头排列）
- **预期失败原因**：若只检查 `ma5 > ma20` 而漏了 `ma10` 的中间层，或者三条比较中有 NaN 导致判断被短路

### U-TECH-035 · ma_bull 不成立 —— MA5 < MA10 < MA20（空头排列）
- **优先级**：P1
- **Given**：`ma5[-1]=9.0 < ma10[-1]=10.0 < ma20[-1]=11.0`
- **When**：计算 `ma_bull`
- **Then**：`ma_bull = False`
- **预期失败原因**：无。纯功能验证——确保空头排列不被误判

### U-TECH-036 · ma_bull 均线含 NaN 时不崩溃
- **优先级**：P1
- **Given**：数据不足 20 日，`ma20[-1]` 为 `np.nan`，`ma5[-1]` 和 `ma10[-1]` 有效
- **When**：计算 `ma_bull`
- **Then**：`ma_bull = False`（含 NaN 的比较一律返回 False，不抛异常）
- **预期失败原因**：numpy 中 `np.nan > 10` 返回 `False`（不是异常），但若用 Python 原生 `float('nan') > 10` 也返回 `False`。关键是确保结果合理——数据不足时不误判为多头

---

### U-TECH-037 · new_high20 创新高
- **优先级**：P0
- **Given**：当日最高价=100，前 20 日（不含当日）最高价=98
- **When**：计算 `new_high20`
- **Then**：`new_high20 = True`
- **预期失败原因**：前 20 日范围的界定——是取 `high[-21:-1]`（不含当日）还是 `high[-20:]`（含当日）。若含当日，`max` 永远是当日自己，`new_high20` 恒为 False。正确做法是不含当日，即取 `high[-21:-1]` 或 `high[:-1][-20:]`

### U-TECH-038 · new_high20 不成立 —— 当日最高低于前高
- **优先级**：P1
- **Given**：当日最高价=98，前 20 日最高价=100
- **When**：计算 `new_high20`
- **Then**：`new_high20 = False`
- **预期失败原因**：同 U-TECH-037——窗口范围错误；另需确认比较是 `>`（严格大于）还是 `>=`

### U-TECH-039 · new_high20 不成立 —— 持平前高
- **优先级**：P1
- **Given**：当日最高价=100，前 20 日最高价=100（刚好等于前高）
- **When**：计算 `new_high20`
- **Then**：`new_high20 = False`（持平不算"创新高"）
- **预期失败原因**：`>` vs `>=` 的选择——S2 量价背离卖出信号用"创 20 日新高"作为条件，持平不算新高是合理的。若用 `>=`，持平时也会触发，可能导致假信号

### U-TECH-040 · new_high20 数据不足 21 根时不崩溃
- **优先级**：P1
- **Given**：总共只有 15 根 K 线（不满足 20 日前高的最低数据量）
- **When**：计算 `new_high20`
- **Then**：`new_high20 = False` 或 `np.nan`（取决于实现），但不崩溃
- **预期失败原因**：索引越界——`high[-21:-1]` 在数组只有 15 个元素时，`-21` 已溢出，但 numpy 的负索引会静默取到更早的元素（行为不确定）。需要用 `if len(high) < 21: return False` 做保护


### U-TECH-041 · break_3ma 成立 —— 阳线 + 站上三线 + 放量
- **优先级**：P0
- **Given**：
  - 收盘价=12（阳线，open=11）
  - `ma5[-1]=11.5, ma10[-1]=11.0, ma20[-1]=10.5`
  - 收盘价 > 三条均线全部
  - `vol_ratio[-1] = 2.5 > VOL_RATIO_HIGH(2.0)`
- **When**：计算 `break_3ma`
- **Then**：`break_3ma = True`
- **预期失败原因**：多个条件组合——阳线+站上 MA5+站上 MA10+站上 MA20+vol_ratio>2.0。任何一个条件漏判都会导致错误

### U-TECH-042 · break_3ma 不成立 —— 站上但阴线
- **优先级**：P0
- **Given**：
  - 收盘价=12（阴线，open=13 > close=12）
  - 收盘价 > MA5/MA10/MA20 全部
  - `vol_ratio = 2.5`
- **When**：计算 `break_3ma`
- **Then**：`break_3ma = False`（阴线不构成 B3 信号）
- **预期失败原因**：B3 信号明确要求"阳线"+"站上三线"+"放量"。阴线可能是假突破——高开低走收在均线上方，看跌含义

### U-TECH-043 · break_3ma 不成立 —— 阳线但未站上 MA10
- **优先级**：P0
- **Given**：
  - 收盘价=11.2（阳线）
  - `ma5[-1]=11.0, ma10[-1]=11.5, ma20[-1]=10.5`
  - 收盘价 > MA5 且 > MA20，但 < MA10
- **When**：计算 `break_3ma`
- **Then**：`break_3ma = False`
- **预期失败原因**：站上三线是三个独立条件的与——站上 MA5 AND 站上 MA10 AND 站上 MA20。用 `all(close > [ma5, ma10, ma20])` 是正确写法

### U-TECH-044 · break_3ma 不成立 —— 阳线上穿但量不足
- **优先级**：P0
- **Given**：
  - 收盘价=12（阳线）
  - 收盘价 > MA5/MA10/MA20
  - `vol_ratio = 1.8`（< 2.0）
- **When**：计算 `break_3ma`
- **Then**：`break_3ma = False`（量不足不构成 B3）
- **预期失败原因**：`VOL_RATIO_HIGH = 2.0` 是严格大于还是大于等于？PRD 写的"成交量 >= 5 日均量 × 2.0"。若实现为 `>` 会漏掉刚好 2.0 的情况

### U-TECH-045 · break_3ma 不成立 —— 一字板平收
- **优先级**：P1
- **Given**：
  - open=12, close=12（平收，非阳线）
  - 收盘价 > MA5/MA10/MA20
  - vol_ratio = 2.5
- **When**：计算 `break_3ma`
- **Then**：`break_3ma = False`
- **预期失败原因**：`is_bullish` 用 `>` 而非 `>=`，正确匹配此预期。若误用 `>=` 会在平收时误判

### U-TECH-046 · break_3ma 均线含 NaN 时不崩溃
- **优先级**：P1
- **Given**：数据不足 20 日，`ma20[-1]` 为 `np.nan`
- **When**：计算 `break_3ma`
- **Then**：`break_3ma = False`（不崩溃）
- **预期失败原因**：`close > np.nan` 返回 `False`，不会崩溃。但若用 `all([close>ma5, close>ma10, close>ma20])` 且其中某个是 Python float NaN，行为一致。关键是结果语义正确——数据不足时不应给出信号

---

### U-TECH-047 · close_ab_ma20 收盘站上 MA20
- **优先级**：P1
- **Given**：`close[-1]=12.0 > ma20[-1]=11.5`
- **When**：计算 `close_ab_ma20`（收盘价相对 MA20 的位置）
- **Then**：`close_ab_ma20 = True` 或 `= 1`（表示收盘价在 MA20 之上）
- **预期失败原因**：语义定义——是布尔还是枚举？若用布尔则跨日状态切换需额外变量（close_ab_ma20_prev）；若用整数则需约定。假设本模块返回布尔值 `True=站上, False=线下`

### U-TECH-048 · close_ab_ma20 收盘在 MA20 之下
- **优先级**：P1
- **Given**：`close[-1]=10.0 < ma20[-1]=11.5`
- **When**：计算 `close_ab_ma20`
- **Then**：`close_ab_ma20 = False`（或 `= -1`）
- **预期失败原因**：同 U-TECH-047

### U-TECH-049 · close_ab_ma20_prev 上一日状态
- **优先级**：P1
- **Given**：上日 `close[-2]=11.0 < ma20[-2]=12.0`（前日在 MA20 之下）
- **When**：计算 `close_ab_ma20_prev`
- **Then**：回传上日的 close_ab_ma20 状态（False/线下）
- **预期失败原因**：需要跨状态访问——`calc_indicators()` 是纯函数还是带状态？若纯函数，`close_ab_ma20_prev` 需调用方传入；若带状态，需在模块内缓存前日值。纯函数设计更可测

### U-TECH-050 · close_ab_ma20/prev 破位切换场景
- **优先级**：P0
- **Given**：
  - `close_ab_ma20 = False`（今日收盘在 MA20 之下）
  - `close_ab_ma20_prev = True`（昨日收盘在 MA20 之上）
- **When**：信号判定层检查 S1 破位卖出条件
- **Then**：`close_ab_ma20_prev == True AND close_ab_ma20 == False` → S1 触发
- **预期失败原因**：这是 S1 信号的**直接输入**——破位卖出依赖"从 MA20 之上掉到之下"的状态切换。若 `calc_indicators()` 不能正确返回前日位置，S1 永远无法触发。此用例虽在信号判定层执行判断，但指标计算层必须正确产出这两个值

---

### U-TECH-051 · 数值稳定性 —— 全整数输入
- **优先级**：P2
- **Given**：全部输入为整数（open/high/low/close/vol 均为 Python int 或 numpy int64）
- **When**：调用 `calc_indicators()`
- **Then**：
  - 所有浮点指标（ma5/ma10/ma20/vol_ma5/vol_ratio）为 `float64`
  - 所有布尔指标为 `bool_`
  - 不因整数除法丢失精度
- **预期失败原因**：QMT `get_market_data_ex` 返回的行情数据可能是整数类型（尤其是成交量）。若使用 `np.mean` 应自动转浮点，但若手写了 `sum(x)/len(x)` 且 x 是 int，在 Python 3 中是安全的（真除法），Python 2 不是——但 QMT 用 Python 3，所以此风险低

### U-TECH-052 · 数值稳定性 —— 浮点小数位
- **优先级**：P2
- **Given**：
  - A 股价格：open=10.37, high=10.58, low=10.22, close=10.45
  - 港股价格：open=388.60, high=392.40, low=385.80, close=390.20（腾讯常见价格区间）
- **When**：计算 `close_ab_ma20`、`body_abs`、`range_` 等
- **Then**：浮点运算精度在合理范围（如 `body_abs = abs(10.45 - 10.37) = 0.08` 而非 `0.079999999`）
- **预期失败原因**：浮点减法的累积误差很小（单次减法基本精确）。但 `np.mean` 涉及多次累加，在数据量大时有细微误差。30 根以内影响可忽略

### U-TECH-053 · 数值稳定性 —— 极大价格（港股高价股 + 涨停跳空）
- **优先级**：P2
- **Given**：
  - 腾讯控股：close=400.00（港股无涨跌停，但可能大幅波动）
  - 贵州茅台：close=1800.00, 涨停=1980.00
  - 成交量：1000000（百万级）
- **When**：分别计算 `ma5` 和 `vol_ratio`
- **Then**：
  - `ma5` 在 400 量级正确
  - `vol_ratio` 在百万级成交量下不溢出（`int64` 足以承载）
- **预期失败原因**：`int32` 溢出——numpy 默认 `int64`，但 QMT 接口返回的数据类型不确定。`vol_ratio` 分母是 float（vol_ma5），分子被自动提升，无溢出风险

### U-TECH-054 · 数组长度一致性 —— open/high/low/close/vol 等长
- **优先级**：P1
- **Given**：5 个数组均为 60 根日线（标准场景）
- **When**：调用 `calc_indicators()`
- **Then**：所有返回数组长度均为 60
- **预期失败原因**：numpy 的数组运算不检查长度，若某个数组意外短了，广播（broadcasting）可能导致静默的错误结果。防御措施：函数入口处 `assert len(open_arr) == len(high_arr) == len(low_arr) == len(close_arr) == len(vol_arr)`

### U-TECH-055 · 15 个返回值完整性与顺序
- **优先级**：P0
- **Given**：任意有效 60 根日线输入
- **When**：调用 `calc_indicators()`
- **Then**：
  - 返回一个 tuple，长度 = 15
  - 顺序为：`(ma5, ma10, ma20, vol_ma5, vol_ratio, body_abs, range_, upper_shadow, lower_shadow, is_bullish, long_upper, long_lower, ma_bull, new_high20, close_ab_ma20, close_ab_ma20_prev)`
  - 注意：这里是 **16 个值**（15 个指标中 `close_ab_ma20` 和 `close_ab_ma20_prev` 各算一个），需确认返回 tuple 的实际元素数
  - 每个数组的 dtype 正确（bool_ 或 float64）
- **预期失败原因**：调用方按位置索引取指标（如 `indicators[13]` 取 `break_3ma`），若顺序与文档不符则全部信号错乱。此用例是回归测试的基石

---

## 测试数据约定

### 构造 60 根 K 线的辅助函数
```python
def make_ohlcv(n_bars=60, seed=None):
    """构造 n 根日线数据。默认 60 根（满足策略最小要求）。"""
    rng = np.random.default_rng(seed)
    close = 10 + rng.random(n_bars) * 2  # 10~12 区间
    body = rng.random(n_bars) * 0.5
    open_ = close - body * (rng.random(n_bars) > 0.5) * 2 + body
    high = np.maximum(open_, close) + rng.random(n_bars) * 0.5
    low = np.minimum(open_, close) - rng.random(n_bars) * 0.5
    vol = (1000 + rng.random(n_bars) * 2000).astype(int)
    return open_, high, low, close, vol
```

### 边界场景的精确数据
各用例中 Given 段直接给出精确数组值（如 U-TECH-001 的 `[10, 10.5, 11, 10.8, 11.2]`），策略是：测试基础计算用精确值，测试形态判定用精确构造，测试数值稳定性用随机大样本。

---

## 优先级汇总

| 优先级 | 用例 ID | 数量 | 覆盖范围 |
|--------|---------|------|---------|
| **P0** | U-TECH-001~003, 008, 010, 022~023, 026, 029, 033~034, 037, 041~044, 050, 055 | 18 | MA 计算 / vol_ratio / long_upper / long_lower / ma_bull / new_high20 / break_3ma / 返回值完整性 |
| **P1** | U-TECH-004~005, 007, 009, 011~015, 017~019, 024~025, 027~028, 030~031, 035~036, 038~040, 045~049, 054 | 29 | 影线基础 / is_bullish / 边界不触发 / close_ab_ma20 / 数组一致性 |
| **P2** | U-TECH-006, 016, 020~021, 032, 051~053 | 8 | 极端值 / 十字星 / 倒 T 字 / 数值稳定性 |
| **合计** | | **55** | |

## 验收门禁

- P0 全绿（18 用例）→ 核心判定输入可靠
- P0 + P1 全绿（47 用例）→ 指标计算完整正确，信号判定层可依赖
- P2 全绿（55 用例）→ 极端/边界场景也覆盖
