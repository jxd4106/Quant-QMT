"""TDD tests for position calculation (仓位计算) — U-POS series."""
import numpy as np
import pytest
import sys
sys.path.insert(0, '.')
from half_position_rolling import (
    calc_target_value, calc_ideal_buy_qty, calc_b2_buy_qty,
    normalize_weights, align_lot_size, calc_sell_qty,
    calc_max_by_cash, calc_order_qty,
    TARGET_PCT, B2_RATIO
)


class TestTargetValue:
    def test_weight_1(self):
        """U-POS-001 · P0 · target = total × weight × 0.5"""
        assert calc_target_value(100000, 1.0) == 50000.0

    def test_weight_half(self):
        """U-POS-002 · P0 · weight=0.5"""
        assert calc_target_value(100000, 0.5) == 25000.0

    def test_weight_zero(self):
        """U-POS-003 · P1 · weight=0"""
        assert calc_target_value(100000, 0.0) == 0.0


class TestIdealBuyQty:
    def test_empty(self):
        """U-POS-007 · P0 · 空仓 → full buy"""
        qty = calc_ideal_buy_qty(50000, 10, 0, 100)
        assert qty == 5000  # 50000/10 = 5000 shares = 50 lots

    def test_full(self):
        """U-POS-008 · P0 · 满仓 → 0"""
        qty = calc_ideal_buy_qty(50000, 10, 5000, 100)
        assert qty == 0

    def test_half(self):
        """U-POS-010 · P1 · 半仓 →补差额"""
        qty = calc_ideal_buy_qty(50000, 10, 2500, 100)
        assert qty == 2500

    def test_price_zero(self):
        """U-POS-011 · P1 · price=0"""
        assert calc_ideal_buy_qty(50000, 0, 0, 100) == 0

    def test_one_lot_boundary(self):
        """U-POS-012 · P1 · exactly 1 lot"""
        qty = calc_ideal_buy_qty(1000, 10, 0, 100)
        assert qty == 100


class TestB2BuyQty:
    def test_normal(self):
        """U-POS-013 · P0 · B2 × 1/3"""
        qty = calc_b2_buy_qty(1500, 100)
        assert qty == 500  # 1500/3 = 500

    def test_less_than_lot(self):
        """U-POS-014 · P1 · < 1 lot → 0"""
        qty = calc_b2_buy_qty(200, 100)  # 200/3=66 → 0
        assert qty == 0

    def test_odd_lot(self):
        """U-POS-015 · P1 · odd lot truncation"""
        qty = calc_b2_buy_qty(500, 100)  # 500/3=166 → 100
        assert qty == 100

    def test_hk_lot_500(self):
        """U-POS-017 · P1 · HK lot=500"""
        qty = calc_b2_buy_qty(3000, 500)  # 3000/3=1000 → 1000
        assert qty == 1000


class TestNormalizeWeights:
    def test_two_not_scaled(self):
        """U-POS-020 · P0 · 总目标=1.0，不缩放"""
        pool = {'A': {'weight': 1.0}, 'B': {'weight': 1.0}}
        assert normalize_weights(pool) == 1.0  # sum=1.0

    def test_three_scaled(self):
        """U-POS-021 · P0 · 总目标=1.5，缩放"""
        pool = {'A': {'weight': 1.0}, 'B': {'weight': 1.0}, 'C': {'weight': 1.0}}
        assert normalize_weights(pool) == pytest.approx(0.6667, 0.001)

    def test_empty(self):
        """U-POS-023 · P1 · 空池"""
        assert normalize_weights({}) == 1.0


class TestAlignLotSize:
    def test_100_aligned(self):
        """U-POS-029 · P1 · lot=100"""
        assert align_lot_size(0, 100) == 0
        assert align_lot_size(99, 100) == 0
        assert align_lot_size(100, 100) == 100
        assert align_lot_size(150, 100) == 100
        assert align_lot_size(500, 100) == 500

    def test_hk_500(self):
        """U-POS-031 · P1 · lot=500"""
        assert align_lot_size(100, 500) == 0
        assert align_lot_size(500, 500) == 500
        assert align_lot_size(1200, 500) == 1000

    def test_lot_zero(self):
        """U-POS-034 · P1 · lot=0"""
        assert align_lot_size(100, 0) == 0


class TestSellQty:
    def test_1000_to_500(self):
        """U-POS-036 · P0 · 1000 → 500"""
        assert calc_sell_qty(1000, 100) == 500

    def test_100_to_0(self):
        """U-POS-037 · P1 · 100 → 0"""
        assert calc_sell_qty(100, 100) == 0

    def test_300_to_100(self):
        """U-POS-038 · P1 · 300 → 100"""
        assert calc_sell_qty(300, 100) == 100

    def test_zero(self):
        """U-POS-041 · P1 · 0"""
        assert calc_sell_qty(0, 100) == 0

    def test_two_lots(self):
        """U-POS-042 · P1 · 2 lots → 1 lot"""
        assert calc_sell_qty(200, 100) == 100


class TestMaxByCash:
    def test_sufficient(self):
        # 10000/(1.0003)=9997, int(9997/10/100)*100=900 (手续费扣除后)
        assert calc_max_by_cash(10000, 10, 100) == 900

    def test_zero_cash(self):
        assert calc_max_by_cash(0, 10, 100) == 0

    def test_zero_price(self):
        assert calc_max_by_cash(10000, 0, 100) == 0


class TestOrderQty:
    def test_b1_full_link(self):
        """U-POS-050 · P0 · B1 完整链路"""
        qty = calc_order_qty('B1', 50000, 10, 0, 100000, 100, scale=1.0)
        assert qty == 5000

    def test_b2_full_link(self):
        """U-POS-051 · P1 · B2 × 1/3"""
        qty = calc_order_qty('B2', 50000, 10, 0, 100000, 100, scale=1.0)
        assert qty == 1600  # 5000 * 1/3 = 1666 → 1600 aligned

    def test_sell_full_link(self):
        """U-POS-052 · P1 · 卖出"""
        qty = calc_order_qty('S1', 50000, 10, 1000, 100000, 100)
        assert qty == 500

    def test_capped_by_cash(self):
        """U-POS-053 · P1 · 资金不足"""
        qty = calc_order_qty('B1', 50000, 10, 0, 1000, 100, scale=1.0)
        assert qty < 5000  # capped


class TestEdgeCases:
    def test_negative_price(self):
        assert calc_ideal_buy_qty(50000, -10, 0, 100) == 0
        assert calc_max_by_cash(10000, -10, 100) == 0
