# 限价单价格 · TDD 单元测试

> 来源：PRD §3 F4 · 技术方案 §5.1 下单参数
> 测试层：单元层（纯函数，脱离 QMT 本地跑）
> 对应模块：`calc_limit_price(direction, current_price)` — 返回限制价，round 到小数点后 2 位

---

## U-PRC-001：卖单标准价格计算

| 项目 | 内容 |
|------|------|
| **Given** | `direction='SELL'`, `current_price=10.00` |
| **When** | 调用 `calc_limit_price('SELL', 10.00)` |
| **Then** | 返回 `9.98`（即 `round(10.00 × 0.998, 2)` = 9.98） |
| **断言** | `assert calc_limit_price('SELL', 10.00) == 9.98` |
| **优先级** | P0 |
| **前条件** | 无 |
| **后条件** | 返回值即 `passorder(price=...)` 直接使用的限价 |

---

## U-PRC-002：买单标准价格计算

| 项目 | 内容 |
|------|------|
| **Given** | `direction='BUY'`, `current_price=10.00` |
| **When** | 调用 `calc_limit_price('BUY', 10.00)` |
| **Then** | 返回 `10.02`（即 `round(10.00 × 1.002, 2)` = 10.02） |
| **断言** | `assert calc_limit_price('BUY', 10.00) == 10.02` |
| **优先级** | P0 |
| **前条件** | 无 |
| **后条件** | 无 |

---

## U-PRC-003：边界——极低价格（0.01 元）

| 项目 | 内容 |
|------|------|
| **Given** | `current_price=0.01` |
| **When** | 调用 `calc_limit_price('SELL', 0.01)` |
| **Then** | 返回 `0.01`（`round(0.01 × 0.998, 2)` = `round(0.00998, 2)` = **0.01**，四舍五入到分） |
| **断言** | `assert calc_limit_price('SELL', 0.01) >= 0.01`；`assert calc_limit_price('BUY', 0.01) <= 0.02` |
| **优先级** | P1 |
| **说明** | 确保极低价不会因舍入变成 0（0 价格的下单会被 QMT 拒绝） |
| **前条件** | 不考虑 A 股最小报价单位 0.01 元之外的约束；`round` 到 2 位应保持非零 |
| **后条件** | 无 |

---

## U-PRC-004：边界——极高价格（9999.99 元）

| 项目 | 内容 |
|------|------|
| **Given** | `current_price=9999.99` |
| **When** | 调用 `calc_limit_price('SELL', 9999.99)` |
| **Then** | 返回 `9979.99`（`round(9999.99 × 0.998, 2)` = `round(9979.99002, 2)` = 9979.99） |
| **When** | 调用 `calc_limit_price('BUY', 9999.99)` |
| **Then** | 返回 `10019.99`（`round(9999.99 × 1.002, 2)` = `round(10019.98998, 2)` = 10019.99） |
| **断言** | `assert calc_limit_price('SELL', 9999.99) == 9979.99`；`assert calc_limit_price('BUY', 9999.99) == 10019.99` |
| **优先级** | P1 |
| **说明** | 验证大额浮点数乘法不发生精度丢失，`round` 到 2 位仍正确 |
| **前条件** | 无 |
| **后条件** | 无 |

---

## U-PRC-005：小数位精确到分位（price=10.555）

| 项目 | 内容 |
|------|------|
| **Given** | `current_price=10.555`（三位小数） |
| **When** | 调用 `calc_limit_price('SELL', 10.555)` |
| **Then** | 返回 `10.53`（`round(10.555 × 0.998, 2)` = `round(10.53389, 2)` = **10.53**） |
| **When** | 调用 `calc_limit_price('BUY', 10.555)` |
| **Then** | 返回 `10.58`（`round(10.555 × 1.002, 2)` = `round(10.57611, 2)` = **10.58**） |
| **断言** | `assert calc_limit_price('SELL', 10.555) == 10.53`；`assert calc_limit_price('BUY', 10.555) == 10.58` |
| **优先级** | P1 |
| **说明** | 港股存在价格非整数（如腾讯 380.2 HKD），输入可能是多位小数；函数必须始终保持输出为 2 位小数 |
| **前条件** | `round()` Python 内置函数行为稳定（banker's rounding 在 Python 3 中已改为 round-half-to-even，但对小数点后 2 位舍入，结果一致） |
| **后条件** | 返回值的 `decimal` 小数位数 ≤ 2 |

---

## U-PRC-006：乘数常量不可变

| 项目 | 内容 |
|------|------|
| **Given** | 函数依赖常量 `SELL_BUFFER = 0.998`、`BUY_BUFFER = 1.002` |
| **When** | 模块被导入 |
| **Then** | 这两个常量在模块级定义，不在函数内硬编码 |
| **断言** | `from <module> import SELL_BUFFER, BUY_BUFFER`；`assert SELL_BUFFER == 0.998`；`assert BUY_BUFFER == 1.002` |
| **优先级** | P2 |
| **说明** | 未来若需调整缓冲（如港股滑点更大），只改一处常量。本用例验证常量存在且正确，不测试函数行为 |
| **前条件** | 无 |
| **后条件** | 无 |

---

## U-PRC-007：无方向参数时安全返回

| 项目 | 内容 |
|------|------|
| **Given** | `direction` 不是 `'SELL'` 也不是 `'BUY'`（如 `None` / `'HOLD'` / 空字符串） |
| **When** | 调用 `calc_limit_price(unknown_direction, 10.00)` |
| **Then** | 抛 `ValueError` 或返回 `10.00`（原价，不下限价缓冲） |
| **断言** | 明确二选一：`pytest.raises(ValueError)` 或 `assert calc_limit_price('HOLD', 10.00) == 10.00` |
| **优先级** | P2 |
| **说明** | 决定该函数是"静默通过"还是"尽早报错"。建议选 `ValueError`：不应该有第三种方向进入限价计算，及早暴露 bug |
| **前条件** | 需团队确认——若选 `ValueError` 则此用例是 P1 |
| **后条件** | 无 |

---

## 测试文件模板（Python）

```python
"""限价单价格 · 单元测试（纯 Python，不需 QMT 环境）"""

import pytest
from half_position_rolling import calc_limit_price, SELL_BUFFER, BUY_BUFFER


class TestCalcLimitPrice:
    """U-PRC-001 ~ U-PRC-007"""

    # === P0 ===

    def test_sell_standard_price(self):
        """U-PRC-001: 卖 = current_price × 0.998，精确到分"""
        assert calc_limit_price('SELL', 10.00) == 9.98

    def test_buy_standard_price(self):
        """U-PRC-002: 买 = current_price × 1.002，精确到分"""
        assert calc_limit_price('BUY', 10.00) == 10.02

    # === P1 ===

    def test_low_price_boundary(self):
        """U-PRC-003: price=0.01 不归零"""
        sell_price = calc_limit_price('SELL', 0.01)
        assert sell_price >= 0.01, f"极低卖价不应低于 0.01，得到 {sell_price}"
        buy_price = calc_limit_price('BUY', 0.01)
        assert buy_price <= 0.02, f"极低买价不应超过 0.02，得到 {buy_price}"

    def test_high_price_boundary(self):
        """U-PRC-004: price=9999.99 精度不丢失"""
        assert calc_limit_price('SELL', 9999.99) == 9979.99
        assert calc_limit_price('BUY', 9999.99) == 10019.99

    def test_fractional_price_round_to_cent(self):
        """U-PRC-005: price=10.555 精确舍入到分"""
        assert calc_limit_price('SELL', 10.555) == 10.53
        assert calc_limit_price('BUY', 10.555) == 10.58

    # === P2 ===

    def test_constants_defined_and_correct(self):
        """U-PRC-006: 乘数常量存在且值正确"""
        assert SELL_BUFFER == 0.998
        assert BUY_BUFFER == 1.002

    def test_invalid_direction_raises(self):
        """U-PRC-007: 非法方向应抛 ValueError"""
        with pytest.raises(ValueError):
            calc_limit_price('HOLD', 10.00)
        with pytest.raises(ValueError):
            calc_limit_price(None, 10.00)
        with pytest.raises(ValueError):
            calc_limit_price('', 10.00)
```
