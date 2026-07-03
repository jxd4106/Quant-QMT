# 信号判定 TDD 单元测试

> 模块：`calc_signals(ind, i)`
> 参数：`VOL_RATIO_LOW=0.7` `VOL_RATIO_MID=1.5` `VOL_RATIO_HIGH=2.0` `SHADOW_RATIO=2.0` `SHADOW_PCT=0.40`
> 基于：PRD详细版.md §4 信号体系 + 技术方案.md §3 numpy 约束
> 生成时间：2026-07-02

---

## 测试策略

- **方法**：纯函数，脱离 QMT，用 numpy 数组构造指标 dict 模拟输入
- **覆盖**：正常触发 / 触发边界 / 不触发边界 / 信号优先级 / 边界 i=0
- **格式**：Given（指标 dict + index i）→ When（调用 calc_signals）→ Then（6 元组期望）
- **断言风格**：`assert calc_signals(ind, i) == (0,0,0,0,0,0)` 精确值比对
- **用例 ID**：`U-SIG-NNN`，稳定、可追踪

### 指标 dict 字段一览

`ind` 是一个 `dict[str, np.ndarray]`，每个 value 是长度为 N（≥ 61）的一维 numpy float64 数组，包含以下字段：

| 字段 | 含义 | 类型 |
|------|------|------|
| `close` | 收盘价 | float64 |
| `open` | 开盘价 | float64 |
| `high` | 最高价 | float64 |
| `low` | 最低价 | float64 |
| `volume` | 成交量 | float64 |
| `vol_ma5` | 5 日均量 | float64 |
| `vol_ratio` | 当日量 / vol_ma5 | float64 |
| `ma20` | 20 日均线 | float64 |
| `close_ab_ma20` | close > ma20 → 1 else 0 | int |
| `body_abs` | abs(close - open) | float64 |
| `range_` | high - low | float64 |
| `upper_shadow` | high - max(open, close) | float64 |
| `lower_shadow` | min(open, close) - low | float64 |
| `long_upper` | 长上影判定（bool→1/0） | int |
| `long_lower` | 长下影判定（bool→1/0） | int |
| `new_high20` | 创 20 日新高（bool→1/0） | int |
| `break_3ma` | 三线突破（bool→1/0） | int |
| `is_bullish` | 阳线 close≥open（bool→1/0） | int |

---

## 辅助函数

```python
import numpy as np

def make_ind(N=65, **overrides):
    """构造指标 dict，默认所有值为 0/中性，通过 overrides 设特定索引值。
    N 默认为 65，保证有至少 60 根历史 bar + 5 根当前区间。
    所有数组长度 = N。
    """
    base = {
        'close':   np.full(N, 10.0, dtype=np.float64),
        'open':    np.full(N, 10.0, dtype=np.float64),
        'high':    np.full(N, 10.5, dtype=np.float64),
        'low':     np.full(N, 9.5, dtype=np.float64),
        'volume':  np.full(N, 1000000.0, dtype=np.float64),
        'vol_ma5': np.full(N, 1000000.0, dtype=np.float64),
        'vol_ratio': np.full(N, 1.0, dtype=np.float64),
        'ma20':    np.full(N, 10.0, dtype=np.float64),
        'close_ab_ma20': np.zeros(N, dtype=np.int32),
        'body_abs':    np.full(N, 0.5, dtype=np.float64),
        'range_':      np.full(N, 1.0, dtype=np.float64),
        'upper_shadow': np.full(N, 0.25, dtype=np.float64),
        'lower_shadow': np.full(N, 0.25, dtype=np.float64),
        'long_upper':  np.zeros(N, dtype=np.int32),
        'long_lower':  np.zeros(N, dtype=np.int32),
        'new_high20':  np.zeros(N, dtype=np.int32),
        'break_3ma':   np.zeros(N, dtype=np.int32),
        'is_bullish':  np.ones(N, dtype=np.int32),  # 默认阳线
    }
    for k, v in overrides.items():
        if isinstance(v, (int, float)):
            base[k][-1] = v  # 默认设 i = N-1（末尾）
        elif isinstance(v, np.ndarray):
            base[k] = v
        elif isinstance(v, list):
            base[k] = np.array(v, dtype=np.float64 if k not in (
                'close_ab_ma20','long_upper','long_lower','new_high20','break_3ma','is_bullish'
            ) else np.int32)
        elif isinstance(v, dict):
            # {idx: value} 形式逐索引赋值
            for idx, val in v.items():
                base[k][idx] = val
    return base
```

---

## 一、S1 破位卖出

> 条件：`close_ab_ma20[i] == 0` 且 `close_ab_ma20[i-1] == 1`（昨日线上、今日线下）
> 动作：卖出当前持仓 50%
> 优先级：卖出信号中最高

### U-SIG-001 S1 正常触发——昨日线上今日线下

| 项目 | 内容 |
|------|------|
| **Given** | `ind = make_ind(N=65)`，`ind['close_ab_ma20'][64] = 0`（i=64 今日线下），`ind['close_ab_ma20'][63] = 1`（i-1=63 昨日线上） |
| **When** | `calc_signals(ind, 64)` |
| **Then** | 返回 `(1, 0, 0, 0, 0, 0)`，仅 S1=1 |
| **预期失败原因** | S1 条件未检查 i-1 状态，或 close_ab_ma20 边界取值错误 |

### U-SIG-002 S1 仍在线上——不触发

| 项目 | 内容 |
|------|------|
| **Given** | `ind = make_ind(N=65)`，`ind['close_ab_ma20'][64] = 1`（今日线上），`ind['close_ab_ma20'][63] = 1`（昨日线上） |
| **When** | `calc_signals(ind, 64)` |
| **Then** | 返回 `(0, 0, 0, 0, 0, 0)`，S1=0 |
| **预期失败原因** | 将"线下"等同于"跌破"，忽略了需要 close_ab_ma20[i]==0 的 && 条件 |

### U-SIG-003 S1 昨日已线下——不触发（不是刚破）

| 项目 | 内容 |
|------|------|
| **Given** | `ind = make_ind(N=65)`，`ind['close_ab_ma20'][64] = 0`（今日线下），`ind['close_ab_ma20'][63] = 0`（昨日已线下） |
| **When** | `calc_signals(ind, 64)` |
| **Then** | 返回 `(0, 0, 0, 0, 0, 0)`，S1=0 |
| **预期失败原因** | 未检查 i-1 的线上状态，仅凭 close_ab_ma20[i]==0 就触发 |

### U-SIG-004 S1 昨日线上今日平线——不触发

| 项目 | 内容 |
|------|------|
| **Given** | close=ma20 刚好相等，`close_ab_ma20[i]` 应判定为 0（严格大于才算线上）。`ind = make_ind(N=65)`，`ind['close_ab_ma20'][64] = 0`，`ind['close_ab_ma20'][63] = 1`。此处 close[64]=ma20[64]=10.0 刚好相等 |
| **When** | `calc_signals(ind, 64)` |
| **Then** | 返回 `(1, 0, 0, 0, 0, 0)`（刚跌破即算破位，平线算线下） |
| **预期失败原因** | close_ab_ma20 的判定逻辑不一致——指标计算层用 > 还是 ≥ 决定了平线算线上还是线下，信号层只消费这个值 |

### U-SIG-005 S1 跳空低开直接破位——仍触发

| 项目 | 内容 |
|------|------|
| **Given** | `ind = make_ind(N=65)`，跳空低开：close[63]=11.0 在 MA20=10.0 之上，close[64]=9.0 掉到 MA20=10.0 之下。`close_ab_ma20[63]=1`，`close_ab_ma20[64]=0` |
| **When** | `calc_signals(ind, 64)` |
| **Then** | 返回 `(1, 0, 0, 0, 0, 0)` |
| **预期失败原因** | 跳空破位是 S1 的典型场景，只检查 close_ab_ma20 移位即可捕捉，不应遗漏 |

---

## 二、S2 量价背离卖出

> 条件：`new_high20[i] == 1` 且 `vol_ratio[i] <= 0.7`
> 动作：卖出当前持仓 50%
> 优先级：卖出信号中第二（S1 > S2 > S3）

### U-SIG-006 S2 正常触发——创新高且缩量

| 项目 | 内容 |
|------|------|
| **Given** | `ind = make_ind(N=65)`，`ind['new_high20'][64] = 1`，`ind['vol_ratio'][64] = 0.5`（≤0.7） |
| **When** | `calc_signals(ind, 64)` |
| **Then** | 返回 `(0, 1, 0, 0, 0, 0)`，仅 S2=1 |
| **预期失败原因** | vol_ratio 阈值比较用错符号（> 还是 ≤），或 new_high20 字段含义误解 |

### U-SIG-007 S2 创新高但放量——不触发

| 项目 | 内容 |
|------|------|
| **Given** | `ind = make_ind(N=65)`，`ind['new_high20'][64] = 1`，`ind['vol_ratio'][64] = 1.8`（>0.7，正常放量） |
| **When** | `calc_signals(ind, 64)` |
| **Then** | 返回 `(0, 0, 0, 0, 0, 0)`，S2=0 |
| **预期失败原因** | 创新高放量是健康的量价配合，不应触发 S2 |

### U-SIG-008 S2 缩量但非新高——不触发

| 项目 | 内容 |
|------|------|
| **Given** | `ind = make_ind(N=65)`，`ind['new_high20'][64] = 0`，`ind['vol_ratio'][64] = 0.3`（缩量） |
| **When** | `calc_signals(ind, 64)` |
| **Then** | 返回 `(0, 0, 0, 0, 0, 0)`，S2=0 |
| **预期失败原因** | 缩量不是新高=正常盘整，不应误判为量价背离 |

### U-SIG-009 S2 vol_ratio 刚好等于 0.7 边界——应触发

| 项目 | 内容 |
|------|------|
| **Given** | `ind = make_ind(N=65)`，`ind['new_high20'][64] = 1`，`ind['vol_ratio'][64] = 0.7`（等于阈值） |
| **When** | `calc_signals(ind, 64)` |
| **Then** | 返回 `(0, 1, 0, 0, 0, 0)`，S2=1（≤0.7 包含等号） |
| **预期失败原因** | 用了 < 0.7 而非 ≤ 0.7，边界值漏判 |

### U-SIG-010 S2 vol_ratio 刚好 0.71——不触发

| 项目 | 内容 |
|------|------|
| **Given** | `ind = make_ind(N=65)`，`ind['new_high20'][64] = 1`，`ind['vol_ratio'][64] = 0.71`（略大于阈值） |
| **When** | `calc_signals(ind, 64)` |
| **Then** | 返回 `(0, 0, 0, 0, 0, 0)`，S2=0 |
| **预期失败原因** | 浮点数比较未正确处理，0.71 被错误判为 ≤0.7 |

---

## 三、S3 放量长上影卖出

> 条件：`vol_ratio[i] >= 1.5` 且 `long_upper[i] == 1` 且 `close[i] <= close[i-1]`（收跌）
> 动作：卖出当前持仓 50%
> 优先级：卖出信号中第三

### U-SIG-011 S3 正常触发——放量+长上影+收跌

| 项目 | 内容 |
|------|------|
| **Given** | `ind = make_ind(N=65)`，`ind['vol_ratio'][64] = 2.0`（≥1.5），`ind['long_upper'][64] = 1`，`ind['close'][64] = 9.8`，`ind['close'][63] = 10.0`（9.8 ≤ 10.0 收跌） |
| **When** | `calc_signals(ind, 64)` |
| **Then** | 返回 `(0, 0, 1, 0, 0, 0)`，仅 S3=1 |
| **预期失败原因** | 三个条件漏判断任一；close 比较方向用反 |

### U-SIG-012 S3 放量+长上影但收涨——不触发

| 项目 | 内容 |
|------|------|
| **Given** | `ind = make_ind(N=65)`，`ind['vol_ratio'][64] = 1.8`（≥1.5），`ind['long_upper'][64] = 1`，`ind['close'][64] = 10.2`，`ind['close'][63] = 10.0`（收涨） |
| **When** | `calc_signals(ind, 64)` |
| **Then** | 返回 `(0, 0, 0, 0, 0, 0)`，S3=0 |
| **预期失败原因** | 放量长上影但收涨说明多方仍有承接，不应判为射击之星 |

### U-SIG-013 S3 收跌+长上影但未放量——不触发

| 项目 | 内容 |
|------|------|
| **Given** | `ind = make_ind(N=65)`，`ind['vol_ratio'][64] = 0.9`（<1.5），`ind['long_upper'][64] = 1`，`ind['close'][64] = 9.8`，`ind['close'][63] = 10.0`（收跌） |
| **When** | `calc_signals(ind, 64)` |
| **Then** | 返回 `(0, 0, 0, 0, 0, 0)`，S3=0 |
| **预期失败原因** | 缩量的长上影可能是随机波动，不算主力出货 |

### U-SIG-014 S3 放量+收跌但无长上影——不触发

| 项目 | 内容 |
|------|------|
| **Given** | `ind = make_ind(N=65)`，`ind['vol_ratio'][64] = 2.5`（≥1.5），`ind['long_upper'][64] = 0`，`ind['close'][64] = 9.8`，`ind['close'][63] = 10.0`（收跌） |
| **When** | `calc_signals(ind, 64)` |
| **Then** | 返回 `(0, 0, 0, 0, 0, 0)`，S3=0 |
| **预期失败原因** | 放量下跌≠射击之星，S3 需要长上影作为关键形态确认 |

### U-SIG-015 S3 vol_ratio 刚好等于 1.5 边界——应触发

| 项目 | 内容 |
|------|------|
| **Given** | `ind = make_ind(N=65)`，`ind['vol_ratio'][64] = 1.5`，`ind['long_upper'][64] = 1`，`ind['close'][64] = 9.8`，`ind['close'][63] = 10.0` |
| **When** | `calc_signals(ind, 64)` |
| **Then** | 返回 `(0, 0, 1, 0, 0, 0)`，S3=1（≥1.5 包含等号） |
| **预期失败原因** | 用了 > 1.5 而非 ≥ 1.5 |

### U-SIG-016 S3 close 刚好等于 close[i-1]（平收）——应触发

| 项目 | 内容 |
|------|------|
| **Given** | `ind = make_ind(N=65)`，`ind['vol_ratio'][64] = 1.7`，`ind['long_upper'][64] = 1`，`ind['close'][64] = 10.0`，`ind['close'][63] = 10.0`（平收，≤ 成立） |
| **When** | `calc_signals(ind, 64)` |
| **Then** | 返回 `(0, 0, 1, 0, 0, 0)`，S3=1 |
| **预期失败原因** | close[i] == close[i-1] 时 ≤ 成立，应用了 < 而非 ≤ |

---

## 四、B1 突破买入

> 条件：`close_ab_ma20[i] == 1` 且 `close_ab_ma20[i-1] == 0`（昨日线下、今日线上）
> 动作：买入到目标仓位
> 优先级：买入信号中最高

### U-SIG-017 B1 正常触发——昨日线下今日线上

| 项目 | 内容 |
|------|------|
| **Given** | `ind = make_ind(N=65)`，`ind['close_ab_ma20'][64] = 1`（今日线上），`ind['close_ab_ma20'][63] = 0`（昨日线下） |
| **When** | `calc_signals(ind, 64)` |
| **Then** | 返回 `(0, 0, 0, 1, 0, 0)`，仅 B1=1 |
| **预期失败原因** | B1 条件与 S1 对称但方向相反，容易写反 i 和 i-1 的取值 |

### U-SIG-018 B1 已在线上——不触发

| 项目 | 内容 |
|------|------|
| **Given** | `ind = make_ind(N=65)`，`ind['close_ab_ma20'][64] = 1`（今日线上），`ind['close_ab_ma20'][63] = 1`（昨日也在线上） |
| **When** | `calc_signals(ind, 64)` |
| **Then** | 返回 `(0, 0, 0, 0, 0, 0)`，B1=0 |
| **预期失败原因** | B1 是"刚突破"信号，持续在线上不应重复触发 |

### U-SIG-019 B1 昨日线上今日线下——不触发（那是 S1）

| 项目 | 内容 |
|------|------|
| **Given** | `ind = make_ind(N=65)`，`ind['close_ab_ma20'][64] = 0`，`ind['close_ab_ma20'][63] = 1` |
| **When** | `calc_signals(ind, 64)` |
| **Then** | 返回 `(1, 0, 0, 0, 0, 0)`（触发 S1，不是 B1） |
| **预期失败原因** | 方向搞反——这是破位不是突破 |

### U-SIG-020 B1 昨日线下今日平线——不触发

| 项目 | 内容 |
|------|------|
| **Given** | close=ma20 刚好相等，`close_ab_ma20[i]` 应判定为 0。`ind['close_ab_ma20'][64] = 0`，`ind['close_ab_ma20'][63] = 0` |
| **When** | `calc_signals(ind, 64)` |
| **Then** | 返回 `(0, 0, 0, 0, 0, 0)`，B1=0 |
| **预期失败原因** | 平线不算站上，B1 需要严格 > MA20 |

---

## 五、B2 长下影买入

> 条件：`long_lower[i] == 1`（下影 > 实体×2 且 > 振幅×0.4） 且 `vol_ratio[i] >= 1.5`
> 动作：买入到目标仓位 × 1/3
> 优先级：买入信号中第二

### U-SIG-021 B2 正常触发——长下影+放量

| 项目 | 内容 |
|------|------|
| **Given** | `ind = make_ind(N=65)`，`ind['long_lower'][64] = 1`，`ind['vol_ratio'][64] = 2.0`（≥1.5） |
| **When** | `calc_signals(ind, 64)` |
| **Then** | 返回 `(0, 0, 0, 0, 1, 0)`，仅 B2=1 |
| **预期失败原因** | long_lower 与 long_upper 字段混淆，或 vol_ratio 阈值用错 |

### U-SIG-022 B2 长下影但缩量——不触发

| 项目 | 内容 |
|------|------|
| **Given** | `ind = make_ind(N=65)`，`ind['long_lower'][64] = 1`，`ind['vol_ratio'][64] = 0.6`（<1.5） |
| **When** | `calc_signals(ind, 64)` |
| **Then** | 返回 `(0, 0, 0, 0, 0, 0)`，B2=0 |
| **预期失败原因** | 缩量长下影可能是偶然的价格波动，非主力承接 |

### U-SIG-023 B2 放量但无长下影——不触发

| 项目 | 内容 |
|------|------|
| **Given** | `ind = make_ind(N=65)`，`ind['long_lower'][64] = 0`，`ind['vol_ratio'][64] = 2.5`（≥1.5） |
| **When** | `calc_signals(ind, 64)` |
| **Then** | 返回 `(0, 0, 0, 0, 0, 0)`，B2=0 |
| **预期失败原因** | 放量下跌≠锤子线，B2 需要长下影形态确认 |

### U-SIG-024 B2 vol_ratio 刚好 1.5——应触发

| 项目 | 内容 |
|------|------|
| **Given** | `ind = make_ind(N=65)`，`ind['long_lower'][64] = 1`，`ind['vol_ratio'][64] = 1.5` |
| **When** | `calc_signals(ind, 64)` |
| **Then** | 返回 `(0, 0, 0, 0, 1, 0)`，B2=1 |
| **预期失败原因** | ≥1.5 应包含等号，用了 >1.5 会漏判 |

### U-SIG-025 B2 长下影边界——下影刚好等于实体×2 且等于振幅×0.4

| 项目 | 内容 |
|------|------|
| **Given** | `ind = make_ind(N=65)`。构造边界情况：open[64]=10.0，close[64]=9.5（收跌），low[64]=9.0，high[64]=10.5。则 body_abs=0.5，range_=1.5，lower_shadow=9.5-9.0=0.5。下影=0.5 = body_abs×2=1.0？不成立——所以下影不够。改用 open=10.5, close=10.0, low=9.0, high=11.0：body_abs=0.5, range_=2.0, lower_shadow=10.0-9.0=1.0。1.0 > 0.5×2=1.0？等于 2 倍，应触发 long_lower。且 `vol_ratio[64] = 1.5` |
| **When** | `calc_signals(ind, 64)` |
| **Then** | 若 long_lower 判定用了 > 实体的 >2 倍，则 `long_lower[64]` 由指标计算层决定。此处验证：若指标层算出的 long_lower[64]=1，则 B2=1> |
| **预期失败原因** | 本用例实际测试的是指标计算层对 long_lower 边界值的处理，信号层只消费。需要与指标层 TDD 交叉验证 |

---

## 六、B3 放量三线突破

> 条件：`is_bullish[i] == 1` 且 `break_3ma[i] == 1` 且 `vol_ratio[i] >= 2.0`
> 动作：买入到目标仓位
> 优先级：买入信号中第三（最低）

### U-SIG-026 B3 正常触发——阳线+三线突破+倍量

| 项目 | 内容 |
|------|------|
| **Given** | `ind = make_ind(N=65)`，`ind['is_bullish'][64] = 1`，`ind['break_3ma'][64] = 1`，`ind['vol_ratio'][64] = 2.5`（≥2.0） |
| **When** | `calc_signals(ind, 64)` |
| **Then** | 返回 `(0, 0, 0, 0, 0, 1)`，仅 B3=1 |
| **预期失败原因** | 三个条件漏判断；vol_ratio 阈值 2.0 vs 1.5 混淆 |

### U-SIG-027 B3 阴线——不触发

| 项目 | 内容 |
|------|------|
| **Given** | `ind = make_ind(N=65)`，`ind['is_bullish'][64] = 0`（阴线），`ind['break_3ma'][64] = 1`，`ind['vol_ratio'][64] = 3.0` |
| **When** | `calc_signals(ind, 64)` |
| **Then** | 返回 `(0, 0, 0, 0, 0, 0)`，B3=0 |
| **预期失败原因** | B3 要求阳线确认，阴线即使放量突破三线也不可靠（可能是假突破） |

### U-SIG-028 B3 放量不足——不触发

| 项目 | 内容 |
|------|------|
| **Given** | `ind = make_ind(N=65)`，`ind['is_bullish'][64] = 1`，`ind['break_3ma'][64] = 1`，`ind['vol_ratio'][64] = 1.8`（<2.0） |
| **When** | `calc_signals(ind, 64)` |
| **Then** | 返回 `(0, 0, 0, 0, 0, 0)`，B3=0 |
| **预期失败原因** | B3 需要强放量确认（2 倍以上），1.8 倍不算 |

### U-SIG-029 B3 未突破三线——不触发

| 项目 | 内容 |
|------|------|
| **Given** | `ind = make_ind(N=65)`，`ind['is_bullish'][64] = 1`，`ind['break_3ma'][64] = 0`，`ind['vol_ratio'][64] = 2.5` |
| **When** | `calc_signals(ind, 64)` |
| **Then** | 返回 `(0, 0, 0, 0, 0, 0)`，B3=0 |
| **预期失败原因** | break_3ma 是核心条件，未突破不算 B3 |

### U-SIG-030 B3 vol_ratio 刚好 2.0 边界——应触发

| 项目 | 内容 |
|------|------|
| **Given** | `ind = make_ind(N=65)`，`ind['is_bullish'][64] = 1`，`ind['break_3ma'][64] = 1`，`ind['vol_ratio'][64] = 2.0` |
| **When** | `calc_signals(ind, 64)` |
| **Then** | 返回 `(0, 0, 0, 0, 0, 1)`，B3=1（≥2.0 包含等号） |
| **预期失败原因** | 用了 >2.0 而非 ≥2.0 |

### U-SIG-031 B3 阳线但收盘刚好等于开盘（十字星）——需确认 is_bullish 语义

| 项目 | 内容 |
|------|------|
| **Given** | `ind = make_ind(N=65)`。close[64]=open[64]=10.0（十字星）。若 is_bullish 定义为 close ≥ open，则 is_bullish[64]=1。搭配 `break_3ma[64]=1`，`vol_ratio[64]=2.5` |
| **When** | `calc_signals(ind, 64)` |
| **Then** | 取决于 is_bullish 的语义——若 close≥open 算阳线则 B3=1；若严格 close>open 则 B3=0 |
| **预期失败原因** | 十字星到底算阳线还是阴线，由指标计算层定义。信号层只消费 is_bullish 字段 |

---

## 七、信号互斥与优先级

> 核心原则：同一 K 线可能同时满足多个信号条件。卖出与卖出竞争取最高优先级；买入与买入竞争取最高优先级。卖出优先于买入（同股同日，卖出信号存在则不执行买入）。

### U-SIG-032 S1 与 S2 同时满足——S1 胜出（卖出内部优先级）

| 项目 | 内容 |
|------|------|
| **Given** | `ind = make_ind(N=65)`，同时满足 S1（close_ab_ma20[64]=0, [63]=1）和 S2（new_high20[64]=1, vol_ratio[64]=0.5） |
| **When** | `calc_signals(ind, 64)` |
| **Then** | 返回 `(1, 0, 0, 0, 0, 0)` 或 `(1, 1, 0, 0, 0, 0)`。若策略只返回优先级最高的信号则前> |
| **预期失败原因** | 根据技术方案 §7.2 信号优先级在 `on_bar()` 层处理，`calc_signals()` 本身可能返回多个信号。需要明确函数契约——calc_signals 是返回所有满足的信号让上层选，还是内部已做互> |

### U-SIG-033 S2 与 S3 同时满足——S2 胜出

| 项目 | 内容 |
|------|------|
| **Given** | `ind = make_ind(N=65)`，同时满足 S2（new_high20[64]=1, vol_ratio[64]=0.5）和 S3（vol_ratio[64]=0.5 不满足 ≥1.5…）。需要同时满足 S2 和 S3：S2 要 vol≤0.7，S3 要 vol≥1.5，矛盾。此场景不可能同时触发。 |
| **When** | N/A |
| **Then** | N/A——S2 和 S3 的 vol_ratio 条件互斥（一个 ≤0.7，一个 ≥1.5），同一 K 线不可能同时满足 |
| **预期失败原因** | 此用例验证的是"不存在信号同时触发的场景"本身——如果意外触发，说明 vol_ratio 比较逻辑有 bug |

### U-SIG-034 B1 与 B2 同时满足——B1 胜出（买入内部优先级）

| 项目 | 内容 |
|------|------|
| **Given** | `ind = make_ind(N=65)`，同时满足 B1（close_ab_ma20[64]=1, [63]=0）和 B2（long_lower[64]=1, vol_ratio[64]=2.0） |
| **When** | `calc_signals(ind, 64)` |
| **Then** | 返回 `(0, 0, 0, 1, 1, 0)`——calc_signals 可能返回两个。上层 on_bar 应只执行 B1 |
| **预期失败原因** | 若 calc_signals 内部做了互斥则此处只应返回 B1；若没做互斥则上层的 on_bar 必须处理优先级。需明确函数边界 |

### U-SIG-035 B2 与 B3 同时满足——B2 胜出

| 项目 | 内容 |
|------|------|
| **Given** | `ind = make_ind(N=65)`，同时满足 B2（long_lower[64]=1, vol_ratio[64]=2.5）和 B3（is_bullish[64]=1, break_3ma[64]=1, vol_ratio[64]=2.5） |
| **When** | `calc_signals(ind, 64)` |
| **Then** | 返回 B2=1, B3=1 同时存在。上层 on_bar 应选 B2（买入优先级 B1>B2>B3） |
| **预期失败原因** | 买入内部优先级未在上层正确实现 |

### U-SIG-036 S1 与 B1 同时满足——卖出优先

| 项目 | 内容 |
|------|------|
| **Given** | 同一天不可能同时满足 S1 和 B1（S1 要求今日线下，B1 要求今日线上，互斥）。但假设因数据异常同时触发：close_ab_ma20[64]=0, [63]=0（今日线下昨日也线下）不会触发 B1。 |
| **When** | N/A |
| **Then** | 此场景在逻辑上不可能发生。S1 和 B1 的 close_ab_ma20 条件互斥 |
| **预期失败原因** | 如果同时触发，说明 close_ab_ma20 计算或使用有严重 bug |

### U-SIG-037 S3 与 B2 同时满足——卖出优先

| 项目 | 内容 |
|------|------|
| **Given** | 同时满足 S3（vol_ratio[64]=2.0, long_upper[64]=1, close[64]≤close[63]）和 B2（vol_ratio[64]=2.0≥1.5, long_lower[64]=1）。同一 K 线同时有长上影和长下影（十字星放量），且收跌 |
| **When** | `calc_signals(ind, 64)` |
| **Then** | 返回 S3=1, B2=1 同时存在。上层 on_bar 因 F9 卖出优先规则，应执行卖出不执行买入 |
| **预期失败原因** | 上层 on_bar 未实现卖出优先逻辑 |

---

## 八、边界 i=0

> `calc_signals(ind, i)` 中 i=0 时 `i-1` 不存在。
> S1 需 `close_ab_ma20[0]` 和 `[-1]`（不存在）。
> B1 需 `close_ab_ma20[0]` 和 `[-1]`（不存在）。
> S3 需 `close[0]` 和 `close[-1]`（不存在）。

### U-SIG-038 i=0 S1 判定——应返回 0

| 项目 | 内容 |
|------|------|
| **Given** | `ind = make_ind(N=65)`，`i = 0`。`close_ab_ma20[0]` 可被设为 0，但 `close_ab_ma20[-1]` 是 Python/numpy 中数组最后一个元素（索引 -1=64），不能当"前一日"用 |
| **When** | `calc_signals(ind, 0)` |
| **Then** | 返回 `(0, 0, 0, 0, 0, 0)`。i=0 时无前一日，所有需 i-1 的信号均不应触发 |
| **预期失败原因** | Python 的 -1 索引指向数组末尾，直接访问 close_ab_ma20[i-1] 当 i=0 时取到的是 arr[-1]=arr[N-1]（最后一日），误判为有前一> |

### U-SIG-039 i=0 B1 判定——应返回 0

| 项目 | 内容 |
|------|------|
| **Given** | `ind = make_ind(N=65)`，`i = 0`。`close_ab_ma20[0] = 1`，但 `close_ab_ma20[-1]` 不应被当作"前一日" |
| **When** | `calc_signals(ind, 0)` |
| **Then** | 返回 `(0, 0, 0, 0, 0, 0)`。B1=0 |
| **预期失败原因** | 同上——Python -1 索引绕到数组末尾 |

### U-SIG-040 i=0 S3 close[i] <= close[i-1] 判定——应安全处理

| 项目 | 内容 |
|------|------|
| **Given** | `ind = make_ind(N=65)`，`i = 0`。`vol_ratio[0] = 2.0`，`long_upper[0] = 1`。`close[0]` 和 `close[-1]` 的关系——若直接比较，close[-1] 取数组末尾值 |
| **When** | `calc_signals(ind, 0)` |
| **Then** | S3 应返回 0 或明确的错误处理。不应因数组末尾值让 S3 意外触发 |
| **预期失败原因** | close[i-1] 在 i=0 时取到 close[-1]=close[N-1]，导致 S3 的"收跌"判定使用了错误参照 |

### U-SIG-041 i=0 无需 i-1 的信号（S2、B3）——应正常判定

| 项目 | 内容 |
|------|------|
| **Given** | `ind = make_ind(N=65)`，`i = 0`。S2 条件：`new_high20[0] = 1`，`vol_ratio[0] = 0.5`（≤0.7）。B3 不满足（未设 break_3ma） |
| **When** | `calc_signals(ind, 0)` |
| **Then** | 返回 `(0, 1, 0, 0, 0, 0)`。S2 正常触发——S2 不需要 i-1 信息 |
| **预期失败原因** | i=0 的统一 guard 过于激进，误拦了不需要 i-1 的信号 |

---

## 九、综合场景

### U-SIG-042 所有信号均不满足——全零

| 项目 | 内容 |
|------|------|
| **Given** | `ind = make_ind(N=65)`，所有默认值：close_ab_ma20 全 0，vol_ratio=1.0（正常量），long_upper/long_lower/new_high20/break_3ma 全 0 |
| **When** | `calc_signals(ind, 64)` |
| **Then** | 返回 `(0, 0, 0, 0, 0, 0)` |
| **预期失败原因** | 默认值意外触发了某信号——检查默认值是否正确 |

### U-SIG-043 同时触发 S1+S3——S1 胜出

| 项目 | 内容 |
|------|------|
| **Given** | `ind = make_ind(N=65)`，同时满足 S1（close_ab_ma20[64]=0, [63]=1）和 S3（vol_ratio[64]=2.0, long_upper[64]=1, close[64]=9.8 < close[63]=10.0） |
| **When** | `calc_signals(ind, 64)` |
| **Then** | 返回 `(1, 0, 1, 0, 0, 0)` 或 `(1, 0, 0, 0, 0, 0)`，取决于 calc_signals 是否内部互斥。上层 on_bar 应只执行 S1 |
| **预期失败原因** | 若 calc_signals 不互斥，则 on_bar 必须按 S1>S2>S3 优先级过滤 |

### U-SIG-044 下跌趋势中 B2 触发——买入应谨慎

| 项目 | 内容 |
|------|------|
| **Given** | `ind = make_ind(N=65)`，B2 条件满足：`long_lower[64]=1`，`vol_ratio[64]=2.0`。但 close_ab_ma20[64]=0（价格在 MA20 下方） |
| **When** | `calc_signals(ind, 64)` |
| **Then** | 返回 `(0, 0, 0, 0, 1, 0)`。B2=1 正确触发 |
| **预期失败原因** | B2 信号定义中不含 MA20 趋势过滤（趋势过滤 F17 是阶段二功能），当前阶段应只按长下影+放量判定。若错误加了 MA20 条件会导致漏信号 |

### U-SIG-045 三卖信号全部独立，不存在三卖互斥之外的隐藏冲突

| 项目 | 内容 |
|------|------|
| **Given** | 逐一验证：S1 的 close_ab_ma20 条件，S2 的 new_high20+vol_ratio 条件，S3 的 vol_ratio+long_upper+收跌条件——三者之间无逻辑矛盾 |
| **When** | 构造同时满足 S1+S2+S3：需要(1)昨日线上今日线下，(2)创新高+缩量，(3)放量+长上影+收跌。S2 要 vol≤0.7，S3 要 vol≥1.5，矛盾——所以不可能三者同时满足 |
| **Then** | 最多同时满足 S1+S3（已覆盖），或 S1+S2（已验证完全不可能）。三卖不可能同时共存 |
| **预期失败原因** | 检验了信号定义的自洽性——如果三者同日触发，意味着 vol_ratio 同时 ≤0.7 且 ≥1.5，存在 bug |

---

## 用例汇总表

| ID | 信号 | 场景 | 期望结果 | 关键边界 |
|-----|------|------|---------|---------|
| U-SIG-001 | S1 | 昨日线上今日线下 | S1=1 | 正常触发 |
| U-SIG-002 | S1 | 仍在线上 | 全 0 | 持续在线不触发 |
| U-SIG-003 | S1 | 昨日已线下 | 全 0 | 不是刚破 |
| U-SIG-004 | S1 | 平线算线下 | S1=1 | 等号处理 |
| U-SIG-005 | S1 | 跳空低开破位 | S1=1 | 跳空场景 |
| U-SIG-006 | S2 | 创新高+缩量 | S2=1 | 正常触发 |
| U-SIG-007 | S2 | 创新高+放量 | 全 0 | 量价配合不触发 |
| U-SIG-008 | S2 | 缩量+非新高 | 全 0 | 缺新高条件 |
| U-SIG-009 | S2 | vol_ratio=0.7 | S2=1 | ≤ 含等号 |
| U-SIG-010 | S2 | vol_ratio=0.71 | 全 0 | >0.7 不触发 |
| U-SIG-011 | S3 | 放量+长上影+收跌 | S3=1 | 正常触发 |
| U-SIG-012 | S3 | 放量+长上影+收涨 | 全 0 | 收涨不触发 |
| U-SIG-013 | S3 | 收跌+长上影+未放量 | 全 0 | 量不足不触发 |
| U-SIG-014 | S3 | 放量+收跌+无长上影 | 全 0 | 缺形态不触发 |
| U-SIG-015 | S3 | vol_ratio=1.5 | S3=1 | ≥ 含等号 |
| U-SIG-016 | S3 | 平收（close=close[i-1]） | S3=1 | ≤ 含等号 |
| U-SIG-017 | B1 | 昨日线下今日线上 | B1=1 | 正常触发 |
| U-SIG-018 | B1 | 已在线上 | 全 0 | 持续在线不触发 |
| U-SIG-019 | B1 | 方向反了→S1 | S1=1 | 防方向错误 |
| U-SIG-020 | B1 | 平线算线下 | 全 0 | 严格>MA20 |
| U-SIG-021 | B2 | 长下影+放量 | B2=1 | 正常触发 |
| U-SIG-022 | B2 | 长下影+缩量 | 全 0 | 量不足不触发 |
| U-SIG-023 | B2 | 放量+无长下影 | 全 0 | 缺形态不触发 |
| U-SIG-024 | B2 | vol_ratio=1.5 | B2=1 | ≥ 含等号 |
| U-SIG-025 | B2 | long_lower 边界值 | B2=1→取决于指标层 | 交叉验证 |
| U-SIG-026 | B3 | 阳线+三线突破+倍量 | B3=1 | 正常触发 |
| U-SIG-027 | B3 | 阴线 | 全 0 | 阴线不触发 |
| U-SIG-028 | B3 | 放量不足 | 全 0 | <2.0 不触发 |
| U-SIG-029 | B3 | 未突破三线 | 全 0 | 缺核心条件 |
| U-SIG-030 | B3 | vol_ratio=2.0 | B3=1 | ≥ 含等号 |
| U-SIG-031 | B3 | 十字星 is_bullish 语义 | 取决于定义 | 需确认 |
| U-SIG-032 | 优先级 | S1+S2 同时 | S1 优先 | 卖出内部 |
| U-SIG-033 | 优先级 | S2+S3 不可共存 | 全 0 | 逻辑互斥验证 |
| U-SIG-034 | 优先级 | B1+B2 同时 | B1 优先 | 买入内部 |
| U-SIG-035 | 优先级 | B2+B3 同时 | B2 优先 | 买入内部 |
| U-SIG-036 | 优先级 | S1+B1 不可共存 | 全 0 | 逻辑互斥验证 |
| U-SIG-037 | 优先级 | S3+B2 同时 | 卖优先于买 | F9 规则 |
| U-SIG-038 | i=0 | S1 at i=0 | 全 0 | -1 索引陷阱 |
| U-SIG-039 | i=0 | B1 at i=0 | 全 0 | -1 索引陷阱 |
| U-SIG-040 | i=0 | S3 at i=0 | 全 0 | close[-1] 陷阱 |
| U-SIG-041 | i=0 | S2/B3 at i=0 | 正常判定 | 不过度防御 |
| U-SIG-042 | 综合 | 全中性 | 全 0 | 默认不触发 |
| U-SIG-043 | 综合 | S1+S3 同时 | S1 优先 | 多卖 |
| U-SIG-044 | 综合 | B2 在 MA20 下 | B2=1 | 无趋势过滤 |
| U-SIG-045 | 综合 | 三卖自洽性 | 不可能共存 | 自洽验证 |

---

## 实现契约（给 Coding Agent）

### calc_signals 函数签名

```python
def calc_signals(ind: dict, i: int) -> tuple[int, int, int, int, int, int]:
    """
    参数:
        ind: 指标 dict[str, np.ndarray]，每字段长度 N >= max(i, 60)
        i: 当前 K 线索引（0-based）

    返回:
        (sig_S1, sig_S2, sig_S3, sig_B1, sig_B2, sig_B3)  各 0/1

    契约:
        - 纯函数，不修改 ind，不访问外部状态
        - i < 1 时，所有依赖 i-1 的信号（S1/B1/S3 的收跌判定）返回 0
        - 不负责信号互斥——返回所有满足条件的信号（可能多信号=1）
        - 信号互斥由上层的 on_bar() 按优先级处理
    """
```

### 待确认项（需与设计/PRD 确认）

1. **calc_signals 是否内部做信号互斥**（U-SIG-032~037）。若内部互斥，每个 6 元组只应有一个 1；若不互斥，可以多个 1。
2. **is_bullish 对十字星的定义**（U-SIG-031）：close==open 算阳线（≥）还是阴线？影响 B3 判定。
3. **S2 和 S3 的 vol_ratio 条件互斥**已确认（≤0.7 vs ≥1.5），U-SIG-033 不可能触发属于自洽验证。
4. **i=0 的处理策略**：函数内部 guard（`if i < 1: return (0,0,0,0,0,0)`）还是分别对每个信号做 i>=1 检查？
