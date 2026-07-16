"""TDD tests for position calculation (仓位计算) — U-POS series.
Updated for v2: full-position initial buy + repurchase mechanism + B2 stop-loss."""

import pytest
import sys
sys.path.insert(0, '.')
from half_position_rolling import (
    calc_initial_buy_qty, calc_repurchase_qty, calc_b2_repurchase_qty,
    align_lot_size, calc_sell_qty, calc_max_by_cash,
    TARGET_PCT, B2_RATIO
)


# ============================================================
# calc_initial_buy_qty — 建仓：满仓买入
# ============================================================

class TestInitialBuyQty:
    def test_weight_1_full_position(self):
        """U-POS-001 · P0 · weight=1.0, 满仓"""
        qty = calc_initial_buy_qty(100000, 1.0, 10, 100)
        assert qty == 10000  # 100000/10 = 10000 shares = 100 lots

    def test_weight_half_reduced_position(self):
        """U-POS-002 · P0 · weight=0.5, 半仓位"""
        qty = calc_initial_buy_qty(100000, 0.5, 10, 100)
        assert qty == 5000  # 50000/10 = 5000

    def test_weight_zero_returns_zero(self):
        """U-POS-003 · P1 · weight=0, 不买入"""
        assert calc_initial_buy_qty(100000, 0.0, 10, 100) == 0

    def test_price_zero_safe(self):
        """U-POS-004 · P1 · price=0, 返回 0"""
        assert calc_initial_buy_qty(100000, 1.0, 0, 100) == 0

    def test_negative_price_safe(self):
        """U-POS-005 · P1 · price<0, 返回 0"""
        assert calc_initial_buy_qty(100000, 1.0, -10, 100) == 0

    def test_lot_size_alignment(self):
        """U-POS-006 · P1 · A 股手数对齐"""
        qty = calc_initial_buy_qty(10000, 1.0, 10.5, 100)
        raw = int(10000 / 10.5)  # ~952
        expected = (raw // 100) * 100  # 900
        assert qty == expected

    def test_hk_lot_size(self):
        """U-POS-007 · P1 · 港股手数对齐 lot=500"""
        qty = calc_initial_buy_qty(100000, 1.0, 50, 500)
        raw = int(100000 / 50)  # 2000
        assert qty == 2000  # aligned to 500

    def test_zero_asset(self):
        """U-POS-008 · P1 · total_asset=0"""
        assert calc_initial_buy_qty(0, 1.0, 10, 100) == 0


# ============================================================
# calc_repurchase_qty — B1/B3 回补：买回全部 last_sell_qty
# ============================================================

class TestRepurchaseQty:
    def test_exact_repurchase(self):
        """U-POS-009 · P0 · exact repurchase 50000 → 50000"""
        assert calc_repurchase_qty(50000, 100) == 50000

    def test_lot_align_down(self):
        """U-POS-010 · P1 · 50001 → 50000（向下取整手）"""
        assert calc_repurchase_qty(50001, 100) == 50000

    def test_zero_remainder(self):
        """U-POS-011 · P1 · last_sell_qty=0, 不买"""
        assert calc_repurchase_qty(0, 100) == 0

    def test_below_lot(self):
        """U-POS-012 · P1 · < 1 手 → 0"""
        assert calc_repurchase_qty(99, 100) == 0

    def test_hk_lot_align(self):
        """U-POS-013 · P1 · 港股 lot=500"""
        assert calc_repurchase_qty(3000, 500) == 3000
        assert calc_repurchase_qty(3100, 500) == 3000


# ============================================================
# calc_b2_repurchase_qty — B2 回补：last_sell_qty × 1/3
# ============================================================

class TestB2RepurchaseQty:
    def test_normal(self):
        """U-POS-014 · P0 · B2 × 1/3"""
        qty = calc_b2_repurchase_qty(50000, 100)
        assert qty == 16600  # 50000/3 ≈ 16666 → 16600 aligned

    def test_less_than_lot(self):
        """U-POS-015 · P1 · < 1 手 → 0"""
        qty = calc_b2_repurchase_qty(200, 100)  # 200/3=66 → 0
        assert qty == 0

    def test_odd_lot_truncation(self):
        """U-POS-016 · P1 · odd lot truncation"""
        qty = calc_b2_repurchase_qty(500, 100)  # 500/3=166 → 100
        assert qty == 100

    def test_hk_lot_500(self):
        """U-POS-017 · P1 · HK lot=500"""
        qty = calc_b2_repurchase_qty(3000, 500)  # 3000/3=1000 → 1000
        assert qty == 1000

    def test_small_last_sell(self):
        """U-POS-018 · P1 · last_sell small, B2 = 0"""
        qty = calc_b2_repurchase_qty(400, 100)  # 400/3=133 → 100
        assert qty == 100

    def test_zero_input(self):
        """U-POS-019 · P1 · last_sell=0"""
        assert calc_b2_repurchase_qty(0, 100) == 0


# ============================================================
# align_lot_size — unchanged, kept for regression
# ============================================================

class TestAlignLotSize:
    def test_100_aligned(self):
        assert align_lot_size(0, 100) == 0
        assert align_lot_size(99, 100) == 0
        assert align_lot_size(100, 100) == 100
        assert align_lot_size(150, 100) == 100
        assert align_lot_size(500, 100) == 500

    def test_hk_500(self):
        assert align_lot_size(100, 500) == 0
        assert align_lot_size(500, 500) == 500
        assert align_lot_size(1200, 500) == 1000

    def test_lot_zero(self):
        assert align_lot_size(100, 0) == 0


# ============================================================
# calc_sell_qty — unchanged
# ============================================================

class TestSellQty:
    def test_1000_to_500(self):
        assert calc_sell_qty(1000, 100) == 500

    def test_100_to_0(self):
        assert calc_sell_qty(100, 100) == 0

    def test_300_to_100(self):
        assert calc_sell_qty(300, 100) == 100

    def test_zero(self):
        assert calc_sell_qty(0, 100) == 0

    def test_two_lots(self):
        assert calc_sell_qty(200, 100) == 100


# ============================================================
# calc_max_by_cash — unchanged
# ============================================================

class TestMaxByCash:
    def test_sufficient(self):
        assert calc_max_by_cash(10000, 10, 100) == 900

    def test_zero_cash(self):
        assert calc_max_by_cash(0, 10, 100) == 0

    def test_zero_price(self):
        assert calc_max_by_cash(10000, 0, 100) == 0


# ============================================================
# Integrated scenarios — 完整半仓滚动链路
# ============================================================

class TestIntegratedScenarios:
    """端到端仓位计算场景."""

    def test_initial_buy_then_sell_then_repurchase(self):
        """完整半仓滚动链路：建仓 → 卖一半 → 回补."""
        total_asset = 100000
        weight = 1.0
        price = 10
        lot = 100

        # Step 1: B1 initial entry
        init_qty = calc_initial_buy_qty(total_asset, weight, price, lot)
        assert init_qty == 10000  # 满仓 100000/10

        # Step 2: Price rises to 20, S1 triggered → sell half
        cur_pos = 10000
        sell_qty = calc_sell_qty(cur_pos, lot)
        assert sell_qty == 5000  # 卖一半
        cur_pos -= sell_qty
        assert cur_pos == 5000

        # Step 3: B1 repurchase → buy back sell_qty
        buy_qty = calc_repurchase_qty(sell_qty, lot)
        cash = 100000  # from sale proceeds
        max_cash = calc_max_by_cash(cash, 22, lot)  # price now 22
        actual_buy = min(buy_qty, max_cash)
        # cash 100000 at price 22 with fees: ~100000 / 1.0003 / 22 ≈ 4543 → 4500 aligned
        assert actual_buy < buy_qty  # cash constrained
        assert actual_buy == 4500  # capped by cash

    def test_b2_then_b1_sequential(self):
        """B2 买入 1/3，之后 B1 补剩余 2/3."""
        last_sell_qty = 50000
        lot = 100

        # B2: buy 1/3
        b2_qty = calc_b2_repurchase_qty(last_sell_qty, lot)
        assert b2_qty == 16600

        remaining = last_sell_qty - b2_qty
        assert remaining == 33400

        # B1: buy back rest
        b1_qty = calc_repurchase_qty(remaining, lot)
        assert b1_qty == 33400

    def test_full_repurchase_resets_cycle(self):
        """全部回补后 last_sell_qty 归零."""
        last_sell_qty = 50000
        lot = 100

        qty = calc_repurchase_qty(last_sell_qty, lot)
        remaining = last_sell_qty - qty
        assert remaining == 0

    def test_cash_shortfall_partial_fill(self):
        """资金不足时部分回补，剩余留存."""
        last_sell_qty = 50000
        lot = 100
        price = 25
        cash = 100000  # can only buy ~3900 shares

        qty = calc_repurchase_qty(last_sell_qty, lot)
        max_cash = calc_max_by_cash(cash, price, lot)
        actual = min(qty, max_cash)
        assert actual == 3900  # cash-limited: 100000/1.0003/25 ≈ 3998 → 3900 aligned
        remaining = last_sell_qty - actual
        assert remaining == 46100  # still needs to repurchase


# ============================================================
# TARGET_PCT 常量验证
# ============================================================

class TestConstants:
    def test_target_pct_is_1(self):
        """TARGET_PCT 应当为 1.0（满仓）."""
        assert TARGET_PCT == 1.0

    def test_b2_ratio_is_third(self):
        """B2 应当是 1/3."""
        assert B2_RATIO == pytest.approx(1.0 / 3, 0.001)
