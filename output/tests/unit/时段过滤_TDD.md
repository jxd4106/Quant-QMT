# 交易时段过滤 · TDD 单元测试

> 来源：PRD §2 交易时段过滤 · §3 F7 + F19 判定时机 · 技术方案 §6.3
> 测试层：单元层（纯函数，脱离 QMT 本地跑）
> 对应模块：
> - `is_trading_time(stock_code, now_time)` → bool
> - `get_signal_time(stock_code, now_time)` → '14:55' / '11:55' / '15:55' / None

---

## U-TIME-001：A 股时段内 — 返回 True（4 个采样点）

| 项目 | 内容 |
|------|------|
| **Given** | `stock_code='603501.SH'`（A 股后缀） |
| **When** | `now_time` 分别为 `'09:31'`、`'11:29'`、`'13:01'`、`'14:59'` |
| **Then** | 全部返回 `True` |
| **断言** | `for t in ['09:31', '11:29', '13:01', '14:59']: assert is_trading_time('603501.SH', t) is True` |
| **优先级** | P0 |
| **说明** | 覆盖 A 股早市（09:31/11:29）和午市（13:01/14:59）的典型盘中时刻 |
| **前条件** | 函数用字符串比较 `'09:30' <= now_time <= '11:30'` / `'13:00' <= now_time <= '15:00'` |
| **后条件** | 无 |

---

## U-TIME-002：A 股时段外 — 返回 False（4 个采样点）

| 项目 | 内容 |
|------|------|
| **Given** | `stock_code='603501.SH'` |
| **When** | `now_time` 分别为 `'09:29'`、`'11:31'`、`'12:30'`、`'15:01'` |
| **Then** | 全部返回 `False` |
| **断言** | `for t in ['09:29', '11:31', '12:30', '15:01']: assert is_trading_time('603501.SH', t) is False` |
| **优先级** | P0 |
| **说明** | 开盘前 1 分钟（09:29）、午休（11:31/12:30）、收盘后 1 分钟（15:01）均不应判定为交易时段 |
| **前条件** | 字符串比较包含边界（`<=`），09:30:00 和 11:30:00 由 U-TIME-007 专门覆盖 |
| **后条件** | 无 |

---

## U-TIME-003：港股早市时段内/外 — 返回 True/False（3 个采样点）

| 项目 | 内容 |
|------|------|
| **Given** | `stock_code='00700.HGT'`（港股通后缀） |
| **When** | `now_time` 分别为 `'09:31'`、`'11:59'`、`'12:01'` |
| **Then** | `09:31` → `True`；`11:59` → `True`（早市结束前最后 1 分钟）；`12:01` → `False`（午休开始后 1 分钟） |
| **断言** | `assert is_trading_time('00700.HGT', '09:31') is True`；`assert is_trading_time('00700.HGT', '11:59') is True`；`assert is_trading_time('00700.HGT', '12:01') is False` |
| **优先级** | P0 |
| **说明** | 港股早市 9:30-12:00，验证边界内外 |
| **前条件** | 代码后缀判定：`.HGT` / `.SGT` 走港股逻辑 |
| **后条件** | 无 |

---

## U-TIME-004：港股午市时段内/外 — 返回 True/False（3 个采样点）

| 项目 | 内容 |
|------|------|
| **Given** | `stock_code='01810.SGT'`（深港通后缀） |
| **When** | `now_time` 分别为 `'13:01'`、`'15:59'`、`'16:01'` |
| **Then** | `13:01` → `True`（午市开盘后 1 分钟）；`15:59` → `True`（收盘前 1 分钟）；`16:01` → `False`（收盘后 1 分钟） |
| **断言** | `assert is_trading_time('01810.SGT', '13:01') is True`；`assert is_trading_time('01810.SGT', '15:59') is True`；`assert is_trading_time('01810.SGT', '16:01') is False` |
| **优先级** | P0 |
| **说明** | 港股午市 13:00-16:00。同时验证 `.SGT` 后缀与 `.HGT` 行为一致 |
| **前条件** | 无 |
| **后条件** | 无 |

---

## U-TIME-005：跨市场混合判断 — 代码后缀决定时段逻辑

| 项目 | 内容 |
|------|------|
| **Given** | A 股代码 `603501.SH` 与港股代码 `00700.HGT` |
| **When** | `now_time='11:35'`（A 股午休 / 港股早市仍在交易） |
| **Then** | `603501.SH` → `False`（A 股午休）；`00700.HGT` → `True`（港股早市 12:00 才结束） |
| **When** | `now_time='14:30'`（两者都在交易） |
| **Then** | 两者均 `True` |
| **When** | `now_time='15:30'`（A 股已收盘 / 港股午市仍在交易） |
| **Then** | `603501.SH` → `False`；`00700.HGT` → `True` |
| **断言** | `is_trading_time('603501.SH', '11:35') is False`；`is_trading_time('00700.HGT', '11:35') is True`；`is_trading_time('603501.SH', '14:30') is True`；`is_trading_time('00700.HGT', '14:30') is True`；`is_trading_time('603501.SH', '15:30') is False`；`is_trading_time('00700.HGT', '15:30') is True` |
| **优先级** | P0 |
| **说明** | 最高价值用例：同一时刻不同市场股票返回不同结果，验证代码确实做了后缀区分而非全局单一判断 |
| **前条件** | 股票池可同时包含 A 股 + 港股 |
| **后条件** | 无 |

---

## U-TIME-006：信号判定时间点匹配

| 项目 | 内容 |
|------|------|
| **Given** | 函数 `get_signal_time(stock_code, now_time)` 返回应判定的信号时间点 |
| **When** | `stock_code='603501.SH'`, `now_time='14:55'` |
| **Then** | 返回 `'14:55'`（A 股判定时间点） |
| **When** | `stock_code='00700.HGT'`, `now_time='11:55'` |
| **Then** | 返回 `'11:55'`（港股早市判定时间点） |
| **When** | `stock_code='01810.SGT'`, `now_time='15:55'` |
| **Then** | 返回 `'15:55'`（港股午市判定时间点） |
| **When** | `stock_code='603501.SH'`, `now_time='10:30'`（非判定时刻） |
| **Then** | 返回 `None`（即 `should_execute_signals` 返回 `False`） |
| **When** | `stock_code='00700.HGT'`, `now_time='14:55'`（港股在此时间没有判定点） |
| **Then** | 返回 `None` |
| **断言** | `get_signal_time('603501.SH', '14:55') == '14:55'`；`get_signal_time('00700.HGT', '11:55') == '11:55'`；`get_signal_time('01810.SGT', '15:55') == '15:55'`；`get_signal_time('603501.SH', '10:30') is None`；`get_signal_time('00700.HGT', '14:55') is None` |
| **优先级** | P0 |
| **说明** | 验证三个判定时间点分别对各自市场生效，且不会错配 |
| **前条件** | 函数接受 `stock_code` 和 `now_time`（格式 `'HH:MM'` 字符串） |
| **后条件** | 返回值用于 `should_execute_signals` 的防重复 key 拼接 |

---

## U-TIME-007：边界——整点时刻包含（09:30 / 11:30 / 13:00 / 15:00 / 12:00 / 16:00）

| 项目 | 内容 |
|------|------|
| **Given** | 各市场开盘/收盘整点时刻 |
| **When** | `now_time='09:30'`, `stock_code='603501.SH'` | **Then** | `True`（A 股开盘，边界包含） |
| **When** | `now_time='11:30'`, `stock_code='603501.SH'` | **Then** | `True`（A 股早市收盘，边界包含） |
| **When** | `now_time='13:00'`, `stock_code='603501.SH'` | **Then** | `True`（A 股午市开盘，边界包含） |
| **When** | `now_time='15:00'`, `stock_code='603501.SH'` | **Then** | `True`（A 股收盘，边界包含） |
| **When** | `now_time='12:00'`, `stock_code='00700.HGT'` | **Then** | `True`（港股早市收盘，边界包含） |
| **When** | `now_time='16:00'`, `stock_code='00700.HGT'` | **Then** | `True`（港股午市收盘，边界包含） |
| **断言** | 以上 6 个整点组合全部 `True` |
| **优先级** | P1 |
| **说明** | 字符串比较 `'09:30' <= now_time <= '11:30'` 使用 `<=` 应包含边界。若使用 `<` 会导致 09:30:00 / 11:30:00 等整点被错误排除，造成信号判定在关键时间点漏判 |
| **前条件** | 函数内部使用 `<=` 而非 `<` 进行比较 |
| **后条件** | 无 |

---

## U-TIME-008：字符串比较依赖 HH:MM 格式（不处理秒）

| 项目 | 内容 |
|------|------|
| **Given** | `now_time` 格式为 `'HH:MM'`（两位小时 + 冒号 + 两位分钟） |
| **When** | 传入 `'09:30'`、`'15:00'` |
| **Then** | 字符串比较 `'09:30' <= '09:30' <= '11:30'` 正确，Python 字典序对零填充数字字符串的行为与时间顺序一致 |
| **When** | （回归测试）传入非标准格式如 `'9:30'` |
| **Then** | 若函数需要兼容零填充缺失，应在文档声明或抛出 `ValueError` |
| **断言** | `is_trading_time('603501.SH', '9:30')` 行为需明确定义（True/False 或 ValueError） |
| **优先级** | P2 |
| **说明** | 函数应假设调用者传入零填充字符串（`'09:30'`），若不能保证则需在函数入口做格式校验 |
| **前条件** | 实际调用链中 `now_time` 来源于 `datetime.now().strftime('%H:%M')`，格式天然零填充，因此本用例在 P2 |
| **后条件** | 无 |

---

## 测试文件模板（Python）

```python
"""交易时段过滤 · 单元测试（纯 Python，不需 QMT 环境）

测试对象：
  - is_trading_time(stock_code: str, now_time: str) -> bool
  - get_signal_time(stock_code: str, now_time: str) -> str | None

now_time 格式统一为 'HH:MM'（零填充，来自 datetime.now().strftime('%H:%M')）
"""

import pytest
from half_position_rolling import is_trading_time, get_signal_time


# ============================================================
# P0 · 交易时段判断
# ============================================================

class TestATradingTime:
    """A 股时段判断（.SH / .SZ）"""

    A_CODE = '603501.SH'

    # U-TIME-001
    @pytest.mark.parametrize('now_time', [
        '09:31',   # 早市开盘后
        '11:29',   # 早市收盘前
        '13:01',   # 午市开盘后
        '14:59',   # 午市收盘前
    ])
    def test_inside_a_share_hours_true(self, now_time):
        assert is_trading_time(self.A_CODE, now_time) is True

    # U-TIME-002
    @pytest.mark.parametrize('now_time', [
        '09:29',   # 开盘前 1 分钟
        '11:31',   # 午休开始后 1 分钟
        '12:30',   # 午休中间
        '15:01',   # 收盘后 1 分钟
    ])
    def test_outside_a_share_hours_false(self, now_time):
        assert is_trading_time(self.A_CODE, now_time) is False


class TestHKTradingTime:
    """港股时段判断（.HGT / .SGT）"""

    HK_HGT = '00700.HGT'
    HK_SGT = '01810.SGT'

    # U-TIME-003
    @pytest.mark.parametrize('code, now_time, expected', [
        ('00700.HGT', '09:31', True),   # 早市开盘后
        ('00700.HGT', '11:59', True),   # 早市收盘前 1 分钟
        ('00700.HGT', '12:01', False),  # 午休开始后 1 分钟
    ])
    def test_hk_morning_session(self, code, now_time, expected):
        assert is_trading_time(code, now_time) is expected

    # U-TIME-004
    @pytest.mark.parametrize('code, now_time, expected', [
        ('01810.SGT', '13:01', True),   # 午市开盘后
        ('01810.SGT', '15:59', True),   # 午市收盘前
        ('01810.SGT', '16:01', False),  # 收盘后
    ])
    def test_hk_afternoon_session(self, code, now_time, expected):
        assert is_trading_time(code, now_time) is expected


class TestCrossMarket:
    """跨市场混合判断 — 同一时刻不同市场返回不同结果"""

    A_CODE = '603501.SH'
    HK_CODE = '00700.HGT'

    # U-TIME-005
    def test_1135_a_share_noon_hk_still_trading(self):
        """11:35 A 股午休，港股早市仍在交易"""
        assert is_trading_time(self.A_CODE, '11:35') is False
        assert is_trading_time(self.HK_CODE, '11:35') is True

    def test_1430_both_trading(self):
        """14:30 两者都在交易"""
        assert is_trading_time(self.A_CODE, '14:30') is True
        assert is_trading_time(self.HK_CODE, '14:30') is True

    def test_1530_a_closed_hk_trading(self):
        """15:30 A 股已收盘，港股午市仍在交易"""
        assert is_trading_time(self.A_CODE, '15:30') is False
        assert is_trading_time(self.HK_CODE, '15:30') is True


# ============================================================
# P0 · 信号判定时间点
# ============================================================

class TestSignalTime:
    """U-TIME-006: 信号判定时间点匹配"""

    def test_a_share_signal_at_1455(self):
        assert get_signal_time('603501.SH', '14:55') == '14:55'

    def test_hk_morning_signal_at_1155(self):
        assert get_signal_time('00700.HGT', '11:55') == '11:55'

    def test_hk_afternoon_signal_at_1555(self):
        assert get_signal_time('01810.SGT', '15:55') == '15:55'

    def test_non_signal_time_returns_none(self):
        """非判定时刻返回 None"""
        assert get_signal_time('603501.SH', '10:30') is None

    def test_hk_at_1455_no_signal(self):
        """港股在 14:55 没有判定点"""
        assert get_signal_time('00700.HGT', '14:55') is None

    def test_a_share_no_morning_signal(self):
        """A 股早市没有 11:55 判定点"""
        assert get_signal_time('603501.SH', '11:55') is None


# ============================================================
# P1 · 边界整点
# ============================================================

class TestBoundaryExactHour:
    """U-TIME-007: 边界整点时刻应包含在内"""

    @pytest.mark.parametrize('code, now_time', [
        ('603501.SH', '09:30'),   # A 股早市开盘
        ('603501.SH', '11:30'),   # A 股早市收盘
        ('603501.SH', '13:00'),   # A 股午市开盘
        ('603501.SH', '15:00'),   # A 股收盘
        ('00700.HGT', '12:00'),   # 港股早市收盘
        ('00700.HGT', '16:00'),   # 港股午市收盘
    ])
    def test_boundary_inclusive(self, code, now_time):
        """整点边界使用 <= 必须返回 True"""
        assert is_trading_time(code, now_time) is True, \
            f"{code} 在 {now_time} 应为 True（边界包含）"


# ============================================================
# P2 · 格式校验
# ============================================================

class TestTimeFormat:
    """U-TIME-008: 字符串比较依赖零填充 HH:MM 格式"""

    def test_zero_padded_format_works(self):
        """标准 HH:MM 格式行为正确"""
        assert is_trading_time('603501.SH', '09:30') is True
        assert is_trading_time('603501.SH', '15:00') is True

    def test_non_zero_padded_may_fail(self):
        """非零填充格式 '9:30' 字符串比较会出问题（'9' > '1'），应抛出或文档声明"""
        # 方案 A：函数内部做格式校验，抛 ValueError
        # 方案 B：假设调用者保证格式，文档声明即可
        # 此处以方案 B 作为初始假设
        try:
            result = is_trading_time('603501.SH', '9:30')
            # 如果没抛异常，至少验证结果没崩溃
            assert isinstance(result, bool)
        except ValueError:
            # 如果抛了也接受
            pass
```
