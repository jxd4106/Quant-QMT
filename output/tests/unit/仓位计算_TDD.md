# 仓位计算 TDD 单元测试

> 模块：仓位计算（仓位数学）
> 来源：PRD §3 F3 半仓滚动 + F15 全局仓位上限 + 技术方案 §5 交易执行层 + §6.2 全局仓位归一化
> 编号：U3
> 生成时间：2026-07-02

---

## 测试环境

```python
import pytest
import numpy as np

# 被测函数均脱离 QMT 运行，使用纯 Python + numpy
# 函数签名约定在每条用例的 Given 中给出
```

### 被测函数清单

| 函数 | 说明 | 所属层 |
|------|------|--------|
| `calc_target_value(total_asset, weight)` | 单股目标仓位金额 | 基础计算 |
| `calc_ideal_buy_qty(target_value, price, cur_pos)` | 理想买入股数（未归一化、未折比例） | 基础计算 |
| `calc_b2_buy_qty(ideal_buy, lot_size)` | B2 信号买入量（× 1/3，手数对齐） | 信号差异化 |
| `normalize_weights(weights)` | 全局仓位归一化，返回 scale + 各股缩放后 weight | F15 |
| `align_lot_size(qty, lot_size)` | 手数对齐取整（向下取整手） | 手数适配 |
| `calc_sell_qty(cur_pos, lot_size)` | 卖出量计算（cur_pos // 2，手数对齐） | 半仓卖出 |
| `calc_max_by_cash(cash_after_fee, price, lot_size)` | 可用资金约束的上限股数 | 资金约束 |
| `calc_order_qty(target_value, price, cur_pos, cash_after_fee, lot_size, signal_type)` | **组合入口**：综合以上完成最终下单量 | 组合逻辑 |

### 共享 Fixtures

```python
@pytest.fixture
def default_cash():
    """默认可用资金 100000"""
    return 100000.0

@pytest.fixture
def a_share_lot():
    """A 股一手 = 100"""
    return 100

@pytest.fixture
def hk_lot():
    """港股腾讯一手 = 100"""
    return 100
```

---

## 场景 1：单股目标仓位（calc_target_value）

### 函数签名

```python
def calc_target_value(total_asset: float, weight: float, target_pct: float = 0.5) -> float:
    """计算单股目标仓位金额。
    
    Args:
        total_asset: 账户总资产
        weight: 该股权重（来自 STOCK_POOL）
        target_pct: 目标仓位比例，默认 0.5（半仓）
    
    Returns:
        目标仓位金额
    """
```

---

### U-POS-001：标准权重 1.0 计算目标仓位

| 项目 | 内容 |
|------|------|
| **Given** | total_asset=100000，weight=1.0，target_pct=0.5 |
| **When** | 调用 `calc_target_value(100000, 1.0)` |
| **Then** | 返回 50000.0 |

```python
def test_target_value_weight_1():
    assert calc_target_value(100000.0, 1.0) == 50000.0
```

---

### U-POS-002：权重 0.5 计算目标仓位

| 项目 | 内容 |
|------|------|
| **Given** | total_asset=100000，weight=0.5 |
| **When** | 调用 `calc_target_value(100000, 0.5)` |
| **Then** | 返回 25000.0 |

```python
def test_target_value_weight_half():
    assert calc_target_value(100000.0, 0.5) == 25000.0
```

---

### U-POS-003：权重 0 不计入目标仓位

| 项目 | 内容 |
|------|------|
| **Given** | total_asset=100000，weight=0 |
| **When** | 调用 `calc_target_value(100000, 0.0)` |
| **Then** | 返回 0.0 |

```python
def test_target_value_weight_zero():
    assert calc_target_value(100000.0, 0.0) == 0.0
```

---

### U-POS-004：资产为 0 时目标仓位为 0

| 项目 | 内容 |
|------|------|
| **Given** | total_asset=0，weight=1.0 |
| **When** | 调用 `calc_target_value(0, 1.0)` |
| **Then** | 返回 0.0（不崩溃） |

```python
def test_target_value_asset_zero():
    assert calc_target_value(0.0, 1.0) == 0.0
```

---

### U-POS-005：资产为负数时返回 0

| 项目 | 内容 |
|------|------|
| **Given** | total_asset=-1000，weight=0.5（异常输入） |
| **When** | 调用 `calc_target_value(-1000, 0.5)` |
| **Then** | 返回 0.0 或抛出 ValueError（防御性） |

```python
def test_target_value_negative_asset():
    # 防御：负数资产返回 0
    result = calc_target_value(-1000.0, 0.5)
    assert result == 0.0
```

---

### U-POS-006：不同 total_asset 下的比例稳定

| 项目 | 内容 |
|------|------|
| **Given** | total_asset 在 [1e4, 1e5, 1e6, 5e5] 下 weight=1.0 |
| **When** | 分别调用 `calc_target_value(asset, 1.0)` |
| **Then** | 每次返回 total_asset × 0.5 |

```python
@pytest.mark.parametrize("asset", [10000, 100000, 500000, 1000000])
def test_target_value_linear_scale(asset):
    assert calc_target_value(float(asset), 1.0) == asset * 0.5
```

---

## 场景 2：理想买入量计算（calc_ideal_buy_qty）

### 函数签名

```python
def calc_ideal_buy_qty(target_value: float, price: float, cur_pos: int) -> int:
    """计算理想买入股数（手数对齐前）。
    
    Args:
        target_value: 目标仓位金额
        price: 当前股价
        cur_pos: 当前持仓股数
    
    Returns:
        理想买入股数（整数，不检查手数对齐）
    """
```

---

### U-POS-007：空仓全部买入

| 项目 | 内容 |
|------|------|
| **Given** | target_value=50000，price=100，cur_pos=0 |
| **When** | 调用 `calc_ideal_buy_qty(50000, 100, 0)` |
| **Then** | 返回 500（目标 50000/100=500 股） |

```python
def test_ideal_buy_empty_position():
    assert calc_ideal_buy_qty(50000.0, 100.0, 0) == 500
```

---

### U-POS-008：已满仓不买入

| 项目 | 内容 |
|------|------|
| **Given** | target_value=50000，price=100，cur_pos=500（已满仓） |
| **When** | 调用 `calc_ideal_buy_qty(50000, 100, 500)` |
| **Then** | 返回 0（目标 - 持仓 ≤ 0） |

```python
def test_ideal_buy_full_position():
    assert calc_ideal_buy_qty(50000.0, 100.0, 500) == 0
```

---

### U-POS-009：已超仓不买入

| 项目 | 内容 |
|------|------|
| **Given** | target_value=50000，price=100，cur_pos=600（超仓） |
| **When** | 调用 `calc_ideal_buy_qty(50000, 100, 600)` |
| **Then** | 返回 0（不允许买入补超仓） |

```python
def test_ideal_buy_over_position():
    assert calc_ideal_buy_qty(50000.0, 100.0, 600) == 0
```

---

### U-POS-010：半仓补仓

| 项目 | 内容 |
|------|------|
| **Given** | target_value=50000，price=100，cur_pos=250（半仓 250 股） |
| **When** | 调用 `calc_ideal_buy_qty(50000, 100, 250)` |
| **Then** | 返回 250（目标 500 - 持有 250 = 250 股） |

```python
def test_ideal_buy_half_position():
    assert calc_ideal_buy_qty(50000.0, 100.0, 250) == 250
```

---

### U-POS-011：价格 0 时除零保护

| 项目 | 内容 |
|------|------|
| **Given** | target_value=50000，price=0，cur_pos=0 |
| **When** | 调用 `calc_ideal_buy_qty(50000, 0, 0)` |
| **Then** | 返回 0（除零保护，不抛出异常） |

```python
def test_ideal_buy_price_zero():
    assert calc_ideal_buy_qty(50000.0, 0.0, 0) == 0
```

---

### U-POS-012：当前持仓刚好 1 手

| 项目 | 内容 |
|------|------|
| **Given** | target_value=50000，price=100，cur_pos=100（刚好 1 手 A 股） |
| **When** | 调用 `calc_ideal_buy_qty(50000, 100, 100)` |
| **Then** | 返回 400（目标 500 - 持有 100 = 400） |

```python
def test_ideal_buy_one_lot_held():
    assert calc_ideal_buy_qty(50000.0, 100.0, 100) == 400
```

---

## 场景 3：B2 信号买入量（calc_b2_buy_qty）

### 函数签名

```python
B2_RATIO = 1 / 3

def calc_b2_buy_qty(ideal_buy: int, lot_size: int) -> int:
    """B2 信号买入量：理想买入量 × 1/3，手数对齐。
    
    Args:
        ideal_buy: 理想买入股数
        lot_size: 每手股数（A 股=100，港股查 VolumeMultiple）
    
    Returns:
        B2 买入股数（lot_size 的整数倍）
    """
```

---

### U-POS-013：B2 标准 1/3 买入并手数对齐

| 项目 | 内容 |
|------|------|
| **Given** | ideal_buy=600，lot_size=100 |
| **When** | 调用 `calc_b2_buy_qty(600, 100)` |
| **Then** | 返回 200（600 × 1/3 = 200，200 % 100 = 0，不需取整） |

```python
def test_b2_buy_standard():
    assert calc_b2_buy_qty(600, 100) == 200
```

---

### U-POS-014：B2 买入量不足 1 手时返回 0

| 项目 | 内容 |
|------|------|
| **Given** | ideal_buy=200，lot_size=100 |
| **When** | 调用 `calc_b2_buy_qty(200, 100)` |
| **Then** | 返回 0（200 × 1/3 ≈ 66，66 // 100 × 100 = 0） |

```python
def test_b2_buy_less_than_one_lot():
    assert calc_b2_buy_qty(200, 100) == 0
```

---

### U-POS-015：B2 买入 odd 股数下取整

| 项目 | 内容 |
|------|------|
| **Given** | ideal_buy=500，lot_size=100 |
| **When** | 调用 `calc_b2_buy_qty(500, 100)` |
| **Then** | 返回 100（500 × 1/3 ≈ 166，166 // 100 × 100 = 100） |

```python
def test_b2_buy_round_down():
    assert calc_b2_buy_qty(500, 100) == 100
```

---

### U-POS-016：B2 买入量恰好是整手的精确倍数

| 项目 | 内容 |
|------|------|
| **Given** | ideal_buy=300 股（刚好 3 手），lot_size=100 |
| **When** | 调用 `calc_b2_buy_qty(300, 100)` |
| **Then** | 返回 100（300 × 1/3 = 100，100 % 100 = 0，精确 1 手） |

```python
def test_b2_buy_exact_lot():
    assert calc_b2_buy_qty(300, 100) == 100
```

---

### U-POS-017：B2 港股手数（腾讯 100 股/手）

| 项目 | 内容 |
|------|------|
| **Given** | ideal_buy=500，lot_size=100（港股腾讯） |
| **When** | 调用 `calc_b2_buy_qty(500, 100)` |
| **Then** | 返回 100（500 × 1/3 ≈ 166，下取整到 1 手） |

```python
def test_b2_buy_hk_lot_tencent():
    assert calc_b2_buy_qty(500, 100) == 100
```

---

### U-POS-018：B2 港股手数（比亚迪 500 股/手）

| 项目 | 内容 |
|------|------|
| **Given** | ideal_buy=3000（比亚迪理想买入），lot_size=500 |
| **When** | 调用 `calc_b2_buy_qty(3000, 500)` |
| **Then** | 返回 1000（3000 × 1/3 = 1000，1000 % 500 = 0，恰 2 手） |

```python
def test_b2_buy_hk_lot_byd():
    assert calc_b2_buy_qty(3000, 500) == 1000
```

---

### U-POS-019：ideal_buy 为 0 时 B2 买入为 0

| 项目 | 内容 |
|------|------|
| **Given** | ideal_buy=0，lot_size=100 |
| **When** | 调用 `calc_b2_buy_qty(0, 100)` |
| **Then** | 返回 0 |

```python
def test_b2_buy_zero_ideal():
    assert calc_b2_buy_qty(0, 100) == 0
```

---

## 场景 4：全局仓位归一化（normalize_weights）

### 函数签名

```python
def normalize_weights(weights: dict[str, float], target_pct: float = 0.5) -> tuple[float, dict[str, float]]:
    """全局仓位归一化（F15）。
    
    若 Σ(weight_i × target_pct) > 1.0，按比例缩放至 1.0。
    
    Args:
        weights: {stock_code: weight} 股票池权重
        target_pct: 目标仓位比例，默认 0.5
    
    Returns:
        (scale, normalized_weights)
        scale: 全局缩放因子（≤ 1.0）
        normalized_weights: {stock_code: scaled_weight}，scaled_weight = weight × scale × target_pct
    """
```

---

### U-POS-020：2 只各 weight=1.0 不缩放

| 项目 | 内容 |
|------|------|
| **Given** | weights={'A': 1.0, 'B': 1.0}，target_pct=0.5 |
| **When** | 调用 `normalize_weights(weights)` |
| **Then** | scale=1.0，总目标仓位=1.0×0.5+1.0×0.5=1.0，不缩放 |

```python
def test_normalize_two_stocks_no_scale():
    weights = {'603501.SH': 1.0, '000001.SZ': 1.0}
    scale, norm = normalize_weights(weights)
    assert scale == 1.0
    assert norm == {
        '603501.SH': 0.5,
        '000001.SZ': 0.5,
    }
```

---

### U-POS-021：3 只各 weight=1.0 触发缩放

| 项目 | 内容 |
|------|------|
| **Given** | weights={'A': 1.0, 'B': 1.0, 'C': 1.0} |
| **When** | 调用 `normalize_weights(weights)` |
| **Then** | 总目标=1.5 > 1.0，scale=1/1.5≈0.6667，归一化后总目标=1.0 |

```python
def test_normalize_three_stocks_scaled():
    weights = {'603501.SH': 1.0, '00700.HGT': 1.0, '01810.SGT': 1.0}
    scale, norm = normalize_weights(weights)
    expected_scale = 1.0 / 1.5  # ≈ 0.666666...
    assert scale == pytest.approx(expected_scale, rel=1e-9)
    # 归一化后每只 weight × scale × 0.5 应总和为 0.5（因为总仓位归一化到 1.0 但 × 0.5target_pct）
    # 不对——修正：normalize 返回的是 scaled_weight（已含 target_pct），总和应为 1.0
    total = sum(norm.values())
    assert total == pytest.approx(1.0, rel=1e-9)
```

---

### U-POS-022：混合权重缩放

| 项目 | 内容 |
|------|------|
| **Given** | weights={'A': 1.0, 'B': 0.5, 'C': 0.5} |
| **When** | 调用 `normalize_weights(weights)` |
| **Then** | 总目标=2.0×0.5=1.0，scale=1.0，不缩放 |

```python
def test_normalize_mixed_weights_no_scale():
    weights = {'603501.SH': 1.0, '00700.HGT': 0.5, '01810.SGT': 0.5}
    scale, norm = normalize_weights(weights)
    assert scale == 1.0
    assert norm['603501.SH'] == 0.5
    assert norm['00700.HGT'] == 0.25
    assert norm['01810.SGT'] == 0.25
```

---

### U-POS-023：空权重表返回 scale=1.0

| 项目 | 内容 |
|------|------|
| **Given** | weights={}（空股票池） |
| **When** | 调用 `normalize_weights({})` |
| **Then** | scale=1.0，norm={} |

```python
def test_normalize_empty():
    scale, norm = normalize_weights({})
    assert scale == 1.0
    assert norm == {}
```

---

### U-POS-024：全部 weight=0 仍返回 scale=1.0

| 项目 | 内容 |
|------|------|
| **Given** | weights={'A': 0, 'B': 0} |
| **When** | 调用 `normalize_weights(weights)` |
| **Then** | scale=1.0（除零保护），norm={'A': 0, 'B': 0} |

```python
def test_normalize_all_zero():
    weights = {'603501.SH': 0.0, '00700.HGT': 0.0}
    scale, norm = normalize_weights(weights)
    assert scale == 1.0
    assert norm['603501.SH'] == 0.0
    assert norm['00700.HGT'] == 0.0
```

---

### U-POS-025：精确边界刚好 1.0 不触发缩放

| 项目 | 内容 |
|------|------|
| **Given** | weights={'A': 2.0}（权重=2.0）× 0.5 = 1.0 恰好等于边界 |
| **When** | 调用 `normalize_weights(weights)` |
| **Then** | scale=1.0（≤ 1.0 不缩放，包含等于 1.0 情况） |

```python
def test_normalize_exact_boundary():
    weights = {'603501.SH': 2.0}
    scale, norm = normalize_weights(weights)
    assert scale == 1.0
    assert norm['603501.SH'] == 1.0  # 2.0 × 0.5 = 1.0
```

---

## 场景 5：归一化后 B2 比例仍适用

### 关键规则

> **B2 的 1/3 比例在「原始理想买入量」上应用，不在归一化后的目标仓位上再乘 1/3。**
>
> 即：归一化只影响 target_value，不影响 B2_RATIO。B2 买入量 = calc_ideal_buy_qty(normalized_target_value) × B2_RATIO → 手数对齐。

---

### U-POS-026：归一化后 B1 买入不受比例折扣

| 项目 | 内容 |
|------|------|
| **Given** | 3 只各 weight=1.0，归一化后 scaled_weight≈0.3333；
| | total_asset=150000，price=100，cur_pos=0，signal=B1 |
| **When** | 归一化后 target_value = 150000 × 0.3333 ≈ 50000（因为按比例缩放）；
| | `calc_ideal_buy_qty(50000, 100, 0) = 500` |
| | B1 不折比例，最终买入量 = `align_lot_size(500, 100)` |
| **Then** | 买入量 = 500 股 |

```python
def test_b1_after_normalize_no_ratio_penalty():
    weights = {'A': 1.0, 'B': 1.0, 'C': 1.0}
    _, norm = normalize_weights(weights)
    # 归一化后 scaled_weight 约 0.3333
    target_value = calc_target_value(150000.0, list(norm.values())[0])
    ideal = calc_ideal_buy_qty(target_value, 100.0, 0)
    # B1 不折比例
    final = align_lot_size(ideal, 100)
    assert final == 500
```

---

### U-POS-027：归一化后 B2 买入在原始 ideal_buy 上 × 1/3

| 项目 | 内容 |
|------|------|
| **Given** | 3 只各 weight=1.0，归一化后 scaled_weight≈0.3333；
| | total_asset=150000，price=100，cur_pos=0，signal=B2 |
| **When** | 归一化后 target_value = 150000 × 0.3333 ≈ 50000；
| | ideal_buy = `calc_ideal_buy_qty(50000, 100, 0)` = 500；
| | B2 折比例 = 500 × 1/3 = 166 → 手数对齐 = 100 |
| **Then** | 最终 B2 买入量 = 100 股（1 手） |

```python
def test_b2_after_normalize_applies_ratio():
    weights = {'A': 1.0, 'B': 1.0, 'C': 1.0}
    _, norm = normalize_weights(weights)
    target_value = calc_target_value(150000.0, list(norm.values())[0])
    ideal = calc_ideal_buy_qty(target_value, 100.0, 0)
    # B2 在 ideal 上 × 1/3 然后手数对齐
    b2_qty = calc_b2_buy_qty(ideal, 100)
    assert b2_qty == 100
```

---

### U-POS-028：归一化后 B2 买入＜1 手下单量为 0

| 项目 | 内容 |
|------|------|
| **Given** | 4 只各 weight=1.0，归一化 scale=1/(4×0.5)=0.5；
| | total_asset=30000，price=100，cur_pos=0，signal=B2 |
| **When** | 归一化后 scaled_weight = 1.0 × 0.5 × 0.5 = 0.25；
| | target_value = 30000 × 0.25 = 7500；
| | ideal_buy = 7500/100 = 75 股；
| | B2 = 75 × 1/3 = 25 < 100 → 0 |
| **Then** | 最终 B2 买入量 = 0（不买） |

```python
def test_b2_after_normalize_less_than_lot():
    weights = {'A': 1.0, 'B': 1.0, 'C': 1.0, 'D': 1.0}
    _, norm = normalize_weights(weights)
    target_value = calc_target_value(30000.0, list(norm.values())[0])
    ideal = calc_ideal_buy_qty(target_value, 100.0, 0)
    b2_qty = calc_b2_buy_qty(ideal, 100)
    assert b2_qty == 0
```

---

## 场景 6：手数对齐（align_lot_size）

### 函数签名

```python
def align_lot_size(qty: int, lot_size: int) -> int:
    """下单量手数对齐，向下取整到整手。
    
    Args:
        qty: 原始股数
        lot_size: 每手股数
    
    Returns:
        对齐后股数（lot_size 的整数倍）
    """
```

---

### U-POS-029：A 股 603501.SH 手数 100 标准对齐

| 项目 | 内容 |
|------|------|
| **Given** | qty=345，lot_size=100 |
| **When** | 调用 `align_lot_size(345, 100)` |
| **Then** | 返回 300（345 // 100 × 100 = 300） |

```python
def test_align_a_share_standard():
    assert align_lot_size(345, 100) == 300
```

---

### U-POS-030：港股 00700.HGT 腾讯手数 100 对齐

| 项目 | 内容 |
|------|------|
| **Given** | qty=250，lot_size=100（腾讯 VolumeMultiple=100） |
| **When** | 调用 `align_lot_size(250, 100)` |
| **Then** | 返回 200 |

```python
def test_align_hk_tencent():
    assert align_lot_size(250, 100) == 200
```

---

### U-POS-031：港股比亚迪手数 500 对齐

| 项目 | 内容 |
|------|------|
| **Given** | qty=1800，lot_size=500（比亚迪 VolumeMultiple=500） |
| **When** | 调用 `align_lot_size(1800, 500)` |
| **Then** | 返回 1500（3 手 × 500） |

```python
def test_align_hk_byd():
    assert align_lot_size(1800, 500) == 1500
```

---

### U-POS-032：不足 1 手返回 0

| 项目 | 内容 |
|------|------|
| **Given** | qty=80，lot_size=100 |
| **When** | 调用 `align_lot_size(80, 100)` |
| **Then** | 返回 0 |

```python
def test_align_less_than_one_lot():
    assert align_lot_size(80, 100) == 0
```

---

### U-POS-033：恰好 1 手

| 项目 | 内容 |
|------|------|
| **Given** | qty=100，lot_size=100 |
| **When** | 调用 `align_lot_size(100, 100)` |
| **Then** | 返回 100（不变化） |

```python
def test_align_exact_one_lot():
    assert align_lot_size(100, 100) == 100
```

---

### U-POS-034：qty=0 时返回 0

| 项目 | 内容 |
|------|------|
| **Given** | qty=0，lot_size=100 |
| **When** | 调用 `align_lot_size(0, 100)` |
| **Then** | 返回 0 |

```python
def test_align_zero_qty():
    assert align_lot_size(0, 100) == 0
```

---

### U-POS-035：lot_size 异常为 0 的防御

| 项目 | 内容 |
|------|------|
| **Given** | qty=500，lot_size=0（异常） |
| **When** | 调用 `align_lot_size(500, 0)` |
| **Then** | 返回 0（除零保护）或抛出 ValueError |

```python
def test_align_lot_size_zero():
    # 防御除零
    with pytest.raises(ValueError):
        align_lot_size(500, 0)
```

---

## 场景 7：卖出量计算（calc_sell_qty）

### 函数签名

```python
def calc_sell_qty(cur_pos: int, lot_size: int) -> int:
    """卖出量 = cur_pos // 2，手数对齐。
    
    Args:
        cur_pos: 当前持仓股数
        lot_size: 每手股数
    
    Returns:
        卖出股数（lot_size 倍数）
    """
```

---

### U-POS-036：持仓 1000 股卖 500

| 项目 | 内容 |
|------|------|
| **Given** | cur_pos=1000，lot_size=100 |
| **When** | 调用 `calc_sell_qty(1000, 100)` |
| **Then** | 返回 500（1000 // 2 = 500，500 % 100 = 0） |

```python
def test_sell_qty_1000():
    assert calc_sell_qty(1000, 100) == 500
```

---

### U-POS-037：持仓 100 股卖 50 → 手数对齐 = 0

| 项目 | 内容 |
|------|------|
| **Given** | cur_pos=100，lot_size=100 |
| **When** | 调用 `calc_sell_qty(100, 100)` |
| **Then** | 返回 0（100 // 2 = 50，50 < 100，手数对齐后为 0） |

```python
def test_sell_qty_100():
    assert calc_sell_qty(100, 100) == 0
```

---

### U-POS-038：持仓 300 股卖 150 → 手数对齐 = 100

| 项目 | 内容 |
|------|------|
| **Given** | cur_pos=300，lot_size=100 |
| **When** | 调用 `calc_sell_qty(300, 100)` |
| **Then** | 返回 100（300 // 2 = 150，150 // 100 × 100 = 100） |

```python
def test_sell_qty_300():
    assert calc_sell_qty(300, 100) == 100
```

---

### U-POS-039：持仓 < 1 手卖 0

| 项目 | 内容 |
|------|------|
| **Given** | cur_pos=50，lot_size=100 |
| **When** | 调用 `calc_sell_qty(50, 100)` |
| **Then** | 返回 0（50 // 2 = 25 < 100 → 手数对齐后 = 0） |

```python
def test_sell_qty_less_than_lot():
    assert calc_sell_qty(50, 100) == 0
```

---

### U-POS-040：持仓 250 股（odd 手）卖 125 → 手数对齐 = 100

| 项目 | 内容 |
|------|------|
| **Given** | cur_pos=250，lot_size=100 |
| **When** | 调用 `calc_sell_qty(250, 100)` |
| **Then** | 返回 100（250 // 2 = 125，125 // 100 × 100 = 100） |

```python
def test_sell_qty_250_odd():
    assert calc_sell_qty(250, 100) == 100
```

---

### U-POS-041：港股比亚迪 500 股/手，持仓 1500 卖 500

| 项目 | 内容 |
|------|------|
| **Given** | cur_pos=1500，lot_size=500（比亚迪 500 股/手） |
| **When** | 调用 `calc_sell_qty(1500, 500)` |
| **Then** | 返回 500（1500 // 2 = 750，750 // 500 × 500 = 500 = 1 手） |

```python
def test_sell_qty_hk_byd():
    assert calc_sell_qty(1500, 500) == 500
```

---

### U-POS-042：持仓为 0 时卖出为 0

| 项目 | 内容 |
|------|------|
| **Given** | cur_pos=0，lot_size=100 |
| **When** | 调用 `calc_sell_qty(0, 100)` |
| **Then** | 返回 0 |

```python
def test_sell_qty_zero_pos():
    assert calc_sell_qty(0, 100) == 0
```

---

### U-POS-043：持仓刚好 2 手

| 项目 | 内容 |
|------|------|
| **Given** | cur_pos=200，lot_size=100 |
| **When** | 调用 `calc_sell_qty(200, 100)` |
| **Then** | 返回 100（200 // 2 = 100，恰好 1 手） |

```python
def test_sell_qty_exact_two_lots():
    assert calc_sell_qty(200, 100) == 100
```

---

## 场景 8：可用资金约束（calc_max_by_cash）

### 函数签名

```python
def calc_max_by_cash(cash_after_fee: float, price: float, lot_size: int) -> int:
    """可用资金能买入的最大手数对齐股数。
    
    Args:
        cash_after_fee: 扣除手续费后的可用资金
        price: 当前股价
        lot_size: 每手股数
    
    Returns:
        最大可买股数（lot_size 的整数倍）
    """
```

---

### U-POS-044：资金足够时不受限

| 项目 | 内容 |
|------|------|
| **Given** | cash_after_fee=100000，price=100，lot_size=100 |
| **When** | 调用 `calc_max_by_cash(100000, 100, 100)` |
| **Then** | 返回 1000 股（100000/100 = 1000，1000 % 100 = 0） |

```python
def test_max_by_cash_sufficient():
    assert calc_max_by_cash(100000.0, 100.0, 100) == 1000
```

---

### U-POS-045：资金不足时受限

| 项目 | 内容 |
|------|------|
| **Given** | cash_after_fee=8000，price=100，lot_size=100 |
| **When** | 调用 `calc_max_by_cash(8000, 100, 100)` |
| **Then** | 返回 80 股 → 手数对齐 = 0（不够 1 手） |

```python
def test_max_by_cash_insufficient():
    assert calc_max_by_cash(8000.0, 100.0, 100) == 0
```

---

### U-POS-046：资金刚好 1 手

| 项目 | 内容 |
|------|------|
| **Given** | cash_after_fee=10000，price=100，lot_size=100 |
| **When** | 调用 `calc_max_by_cash(10000, 100, 100)` |
| **Then** | 返回 100 股（10000/100 = 100，恰好 1 手） |

```python
def test_max_by_cash_exact_one_lot():
    assert calc_max_by_cash(10000.0, 100.0, 100) == 100
```

---

### U-POS-047：资金足够但有 odd 股数，对齐取整

| 项目 | 内容 |
|------|------|
| **Given** | cash_after_fee=12500，price=100，lot_size=100 |
| **When** | 调用 `calc_max_by_cash(12500, 100, 100)` |
| **Then** | 返回 100 股（12500/100 = 125，125 // 100 × 100 = 100，1 手） |

```python
def test_max_by_cash_round_down():
    assert calc_max_by_cash(12500.0, 100.0, 100) == 100
```

---

### U-POS-048：price=0 除零保护

| 项目 | 内容 |
|------|------|
| **Given** | cash_after_fee=100000，price=0，lot_size=100 |
| **When** | 调用 `calc_max_by_cash(100000, 0, 100)` |
| **Then** | 返回 0（除零保护） |

```python
def test_max_by_cash_price_zero():
    assert calc_max_by_cash(100000.0, 0.0, 100) == 0
```

---

### U-POS-049：cash_after_fee=0 时返回 0

| 项目 | 内容 |
|------|------|
| **Given** | cash_after_fee=0，price=100，lot_size=100 |
| **When** | 调用 `calc_max_by_cash(0, 100, 100)` |
| **Then** | 返回 0 |

```python
def test_max_by_cash_zero_cash():
    assert calc_max_by_cash(0.0, 100.0, 100) == 0
```

---

## 场景 9：综合入口 calc_order_qty

### 函数签名

```python
def calc_order_qty(
    total_asset: float,
    weight: float,
    price: float,
    cur_pos: int,
    cash_after_fee: float,
    lot_size: int,
    signal_type: str,  # 'B1' / 'B2' / 'B3' / 'S1' / 'S2' / 'S3'
    scale: float = 1.0,  # 全局归一化缩放因子
) -> tuple[str, int]:
    """综合计算最终下单量。
    
    Args:
        total_asset: 账户总资产
        weight: 该股权重（已归一化）
        price: 当前股价
        cur_pos: 当前持仓
        cash_after_fee: 可用资金（扣手续费后）
        lot_size: 每手股数
        signal_type: 信号类型
        scale: 全局归一化缩放因子（默认 1.0 不缩放）
    
    Returns:
        ('buy', qty) 或 ('sell', qty) 或 ('skip', 0)
    """
```

---

### U-POS-050：B1 买入全量，资金足够

| 项目 | 内容 |
|------|------|
| **Given** | total_asset=100000，weight=1.0，price=100，cur_pos=0，
| | cash_after_fee=80000，lot_size=100，signal=B1，scale=1.0 |
| **When** | 调用 `calc_order_qty(...)` |
| **Then** | 返回 ('buy', 500)（目标=50000→500股，资金够，不折比例） |

```python
def test_order_b1_full_buy():
    direction, qty = calc_order_qty(
        total_asset=100000.0, weight=1.0, price=100.0, cur_pos=0,
        cash_after_fee=80000.0, lot_size=100, signal_type='B1', scale=1.0
    )
    assert direction == 'buy'
    assert qty == 500
```

---

### U-POS-051：B2 买入 1/3，资金足够

| 项目 | 内容 |
|------|------|
| **Given** | total_asset=100000，weight=1.0，price=100，cur_pos=0，
| | cash_after_fee=80000，lot_size=100，signal=B2，scale=1.0 |
| **When** | 调用 `calc_order_qty(...)` |
| **Then** | 返回 ('buy', 100)（目标=500股→ B2=500/3≈166→手数对齐=100） |

```python
def test_order_b2_third_buy():
    direction, qty = calc_order_qty(
        total_asset=100000.0, weight=1.0, price=100.0, cur_pos=0,
        cash_after_fee=80000.0, lot_size=100, signal_type='B2', scale=1.0
    )
    assert direction == 'buy'
    assert qty == 100
```

---

### U-POS-052：B2 买入但资金不足 1 手

| 项目 | 内容 |
|------|------|
| **Given** | total_asset=100000，weight=1.0，price=100，cur_pos=0，
| | cash_after_fee=5000（只够 0.5 手），lot_size=100，signal=B2 |
| **When** | 调用 `calc_order_qty(...)` |
| **Then** | 返回 ('skip', 0)（资金不足 1 手） |

```python
def test_order_b2_insufficient_cash():
    direction, qty = calc_order_qty(
        total_asset=100000.0, weight=1.0, price=100.0, cur_pos=0,
        cash_after_fee=5000.0, lot_size=100, signal_type='B2', scale=1.0
    )
    assert direction == 'skip'
    assert qty == 0
```

---

### U-POS-053：S1 卖出半仓

| 项目 | 内容 |
|------|------|
| **Given** | cur_pos=600，lot_size=100，signal=S1 |
| **When** | 调用 `calc_order_qty(...)` |
| **Then** | 返回 ('sell', 300)（600 // 2 = 300，手数对齐恰好 3 手） |

```python
def test_order_s1_sell_half():
    direction, qty = calc_order_qty(
        total_asset=100000.0, weight=1.0, price=100.0, cur_pos=600,
        cash_after_fee=80000.0, lot_size=100, signal_type='S1', scale=1.0
    )
    assert direction == 'sell'
    assert qty == 300
```

---

### U-POS-054：S1 卖出但持仓为 0

| 项目 | 内容 |
|------|------|
| **Given** | cur_pos=0，signal=S1 |
| **When** | 调用 `calc_order_qty(...)` |
| **Then** | 返回 ('skip', 0)（无持仓可卖） |

```python
def test_order_s1_no_position():
    direction, qty = calc_order_qty(
        total_asset=100000.0, weight=1.0, price=100.0, cur_pos=0,
        cash_after_fee=80000.0, lot_size=100, signal_type='S1', scale=1.0
    )
    assert direction == 'skip'
    assert qty == 0
```

---

### U-POS-055：B1 买入但资金约束缩减买入量

| 项目 | 内容 |
|------|------|
| **Given** | total_asset=100000，weight=1.0，price=100，cur_pos=0，
| | cash_after_fee=20000（只够 2 手），lot_size=100，signal=B1 |
| **When** | 调用 `calc_order_qty(...)` |
| **Then** | 返回 ('buy', 200)（ideal=500但资金只够200） |

```python
def test_order_b1_cash_constrained():
    direction, qty = calc_order_qty(
        total_asset=100000.0, weight=1.0, price=100.0, cur_pos=0,
        cash_after_fee=20000.0, lot_size=100, signal_type='B1', scale=1.0
    )
    assert direction == 'buy'
    assert qty == 200
```

---

### U-POS-056：B1 已满仓跳过

| 项目 | 内容 |
|------|------|
| **Given** | total_asset=100000，weight=1.0，price=100，cur_pos=500（满仓），
| | cash_after_fee=80000，lot_size=100，signal=B1 |
| **When** | 调用 `calc_order_qty(...)` |
| **Then** | 返回 ('skip', 0) |

```python
def test_order_b1_full_position_skip():
    direction, qty = calc_order_qty(
        total_asset=100000.0, weight=1.0, price=100.0, cur_pos=500,
        cash_after_fee=80000.0, lot_size=100, signal_type='B1', scale=1.0
    )
    assert direction == 'skip'
    assert qty == 0
```

---

### U-POS-057：price=0 时入口防崩溃

| 项目 | 内容 |
|------|------|
| **Given** | price=0，其他正常 |
| **When** | 调用 `calc_order_qty(...)` |
| **Then** | 返回 ('skip', 0)（不崩溃） |

```python
def test_order_price_zero_defense():
    direction, qty = calc_order_qty(
        total_asset=100000.0, weight=1.0, price=0.0, cur_pos=0,
        cash_after_fee=80000.0, lot_size=100, signal_type='B1', scale=1.0
    )
    assert direction == 'skip'
    assert qty == 0
```

---

### U-POS-058：未知信号类型跳过

| 项目 | 内容 |
|------|------|
| **Given** | signal_type='UNKNOWN' |
| **When** | 调用 `calc_order_qty(...)` |
| **Then** | 返回 ('skip', 0) |

```python
def test_order_unknown_signal():
    direction, qty = calc_order_qty(
        total_asset=100000.0, weight=1.0, price=100.0, cur_pos=0,
        cash_after_fee=80000.0, lot_size=100, signal_type='UNKNOWN', scale=1.0
    )
    assert direction == 'skip'
    assert qty == 0
```

---

### U-POS-059：归一化 scale 影响 target_value

| 项目 | 内容 |
|------|------|
| **Given** | total_asset=100000，weight=1.0，scale=0.5，price=100，cur_pos=0，
| | cash_after_fee=80000，lot_size=100，signal=B1 |
| **When** | 调用 `calc_order_qty(...)` |
| **Then** | 返回 ('buy', 250)（target_value = 100000 × 1.0 × 0.5 × 0.5 = 25000，25000/100 = 250） |

```python
def test_order_with_scale():
    direction, qty = calc_order_qty(
        total_asset=100000.0, weight=1.0, price=100.0, cur_pos=0,
        cash_after_fee=80000.0, lot_size=100, signal_type='B1', scale=0.5
    )
    assert direction == 'buy'
    assert qty == 250
```

---

### U-POS-060：total_asset=0 时返回 skip

| 项目 | 内容 |
|------|------|
| **Given** | total_asset=0，weight=1.0，price=100，cur_pos=0，signal=B1 |
| **When** | 调用 `calc_order_qty(...)` |
| **Then** | 返回 ('skip', 0) |

```python
def test_order_zero_asset():
    direction, qty = calc_order_qty(
        total_asset=0.0, weight=1.0, price=100.0, cur_pos=0,
        cash_after_fee=80000.0, lot_size=100, signal_type='B1', scale=1.0
    )
    assert direction == 'skip'
    assert qty == 0
```

---

## 用例索引

| ID | 场景 | 被测函数 | 关键输入 | 期望输出 |
|----|------|---------|---------|---------|
| U-POS-001 | 标准权重 1.0 | `calc_target_value` | asset=100000, w=1.0 | 50000.0 |
| U-POS-002 | 权重 0.5 | `calc_target_value` | asset=100000, w=0.5 | 25000.0 |
| U-POS-003 | 权重=0 | `calc_target_value` | w=0 | 0.0 |
| U-POS-004 | 资产=0 | `calc_target_value` | asset=0 | 0.0 |
| U-POS-005 | 资产负数 | `calc_target_value` | asset=-1000 | 0.0 |
| U-POS-006 | 比例稳定性 | `calc_target_value` | 多组 asset × w=1.0 | asset × 0.5 |
| U-POS-007 | 空仓全买 | `calc_ideal_buy_qty` | pos=0 | 500 |
| U-POS-008 | 满仓不买 | `calc_ideal_buy_qty` | pos=500 | 0 |
| U-POS-009 | 超仓不买 | `calc_ideal_buy_qty` | pos=600 | 0 |
| U-POS-010 | 半仓补仓 | `calc_ideal_buy_qty` | pos=250 | 250 |
| U-POS-011 | 价格=0 保护 | `calc_ideal_buy_qty` | price=0 | 0 |
| U-POS-012 | 持仓刚好 1 手 | `calc_ideal_buy_qty` | pos=100 | 400 |
| U-POS-013 | B2 标准 1/3 | `calc_b2_buy_qty` | ideal=600 | 200 |
| U-POS-014 | B2 不足 1 手 | `calc_b2_buy_qty` | ideal=200 | 0 |
| U-POS-015 | B2 odd 取整 | `calc_b2_buy_qty` | ideal=500 | 100 |
| U-POS-016 | B2 精确整手 | `calc_b2_buy_qty` | ideal=300 | 100 |
| U-POS-017 | B2 港股腾讯 | `calc_b2_buy_qty` | ideal=500, lot=100 | 100 |
| U-POS-018 | B2 港股比亚迪 | `calc_b2_buy_qty` | ideal=3000, lot=500 | 1000 |
| U-POS-019 | B2 ideal=0 | `calc_b2_buy_qty` | ideal=0 | 0 |
| U-POS-020 | 2 股不缩放 | `normalize_weights` | w={1.0,1.0} | scale=1.0 |
| U-POS-021 | 3 股触发缩放 | `normalize_weights` | w={1.0,1.0,1.0} | scale≈0.6667 |
| U-POS-022 | 混合权重不缩放 | `normalize_weights` | w={1.0,0.5,0.5} | scale=1.0 |
| U-POS-023 | 空池 | `normalize_weights` | w={} | scale=1.0, {} |
| U-POS-024 | 全零权重 | `normalize_weights` | w={0,0} | scale=1.0 |
| U-POS-025 | 边界 1.0 | `normalize_weights` | w={2.0} | scale=1.0 |
| U-POS-026 | 归一化后 B1 不折 | 组合 | 3 股 归一化 + B1 | 500 |
| U-POS-027 | 归一化后 B2 × 1/3 | 组合 | 3 股 归一化 + B2 | 100 |
| U-POS-028 | 归一化后 B2 < 1 手 | 组合 | 4 股 归一化 + B2 | 0 |
| U-POS-029 | A 股标准手对齐 | `align_lot_size` | 345, lot=100 | 300 |
| U-POS-030 | 港股腾讯对齐 | `align_lot_size` | 250, lot=100 | 200 |
| U-POS-031 | 港股比亚迪对齐 | `align_lot_size` | 1800, lot=500 | 1500 |
| U-POS-032 | < 1 手 | `align_lot_size` | 80, lot=100 | 0 |
| U-POS-033 | 恰好 1 手 | `align_lot_size` | 100, lot=100 | 100 |
| U-POS-034 | qty=0 | `align_lot_size` | 0, lot=100 | 0 |
| U-POS-035 | lot=0 异常 | `align_lot_size` | 500, lot=0 | ValueError |
| U-POS-036 | 卖 1000 股 | `calc_sell_qty` | pos=1000 | 500 |
| U-POS-037 | 卖 100 股 | `calc_sell_qty` | pos=100 | 0 |
| U-POS-038 | 卖 300 股 | `calc_sell_qty` | pos=300 | 100 |
| U-POS-039 | 卖 < 1 手 | `calc_sell_qty` | pos=50 | 0 |
| U-POS-040 | 卖 odd 手 | `calc_sell_qty` | pos=250 | 100 |
| U-POS-041 | 卖港股比亚迪 | `calc_sell_qty` | pos=1500, lot=500 | 500 |
| U-POS-042 | 卖 0 持仓 | `calc_sell_qty` | pos=0 | 0 |
| U-POS-043 | 卖 2 手 | `calc_sell_qty` | pos=200 | 100 |
| U-POS-044 | 资金足够 | `calc_max_by_cash` | cash=100000, P=100 | 1000 |
| U-POS-045 | 资金不足 | `calc_max_by_cash` | cash=8000, P=100 | 0 |
| U-POS-046 | 资金刚 1 手 | `calc_max_by_cash` | cash=10000, P=100 | 100 |
| U-POS-047 | 资金 odd 取整 | `calc_max_by_cash` | cash=12500, P=100 | 100 |
| U-POS-048 | price=0 | `calc_max_by_cash` | cash=100000, P=0 | 0 |
| U-POS-049 | cash=0 | `calc_max_by_cash` | cash=0 | 0 |
| U-POS-050 | B1 全量买入 | `calc_order_qty` | 空仓, B1 | ('buy', 500) |
| U-POS-051 | B2 1/3 买入 | `calc_order_qty` | 空仓, B2 | ('buy', 100) |
| U-POS-052 | B2 资金不足 | `calc_order_qty` | cash=5000, B2 | ('skip', 0) |
| U-POS-053 | S1 卖出半仓 | `calc_order_qty` | pos=600, S1 | ('sell', 300) |
| U-POS-054 | S1 无持仓 | `calc_order_qty` | pos=0, S1 | ('skip', 0) |
| U-POS-055 | B1 资金约束 | `calc_order_qty` | cash=20000, B1 | ('buy', 200) |
| U-POS-056 | B1 满仓跳过 | `calc_order_qty` | pos=500, B1 | ('skip', 0) |
| U-POS-057 | price=0 防御 | `calc_order_qty` | price=0 | ('skip', 0) |
| U-POS-058 | 未知信号 | `calc_order_qty` | signal=UNKNOWN | ('skip', 0) |
| U-POS-059 | 归一化影响 | `calc_order_qty` | scale=0.5, B1 | ('buy', 250) |
| U-POS-060 | 资产=0 | `calc_order_qty` | asset=0 | ('skip', 0) |

---

## 验收门禁

| 维度 | 标准 |
|------|------|
| **用例数** | 60 条（U-POS-001 ~ U-POS-060） |
| **覆盖场景** | 9 个场景 × 多边界组合 |
| **通过标准** | 60/60 全绿 |
| **覆盖函数** | 8 个被测函数全部覆盖 |
| **边界覆盖** | price=0、asset=0、cash=0、pos=0、pos 边界（1 手/2 手/满仓/超仓）、weight=0、空池、归一化边界 1.0、未知信号 |
| **市场适配** | A 股 lot=100 + 港股 lot=100(腾讯) + lot=500(比亚迪) |
