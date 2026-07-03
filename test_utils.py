"""TDD tests for limit price (限价单) and time filter (时段过滤)."""
import pytest
import sys
sys.path.insert(0, '.')
from half_position_rolling import (
    limit_price_sell, limit_price_buy,
    is_hk_stock, is_in_trading_hours, get_signal_time,
)


class TestLimitPrice:
    def test_sell_normal(self):
        """U-PRC-001 · P0 · 卖单价 0.998"""
        assert limit_price_sell(10.00) == 9.98

    def test_buy_normal(self):
        """U-PRC-002 · P0 · 买单价 1.002"""
        assert limit_price_buy(10.00) == 10.02

    def test_sell_low_boundary(self):
        """U-PRC-003 · P1 · 0.01"""
        assert limit_price_sell(0.01) == 0.01

    def test_sell_high(self):
        """U-PRC-004 · P1 · 9999.99"""
        assert limit_price_sell(9999.99) == pytest.approx(9980.0, 1)

    def test_rounding(self):
        """U-PRC-005 · P1 · 10.555"""
        assert limit_price_sell(10.555) == pytest.approx(10.53, 0.01)
        assert limit_price_buy(10.555) == pytest.approx(10.58, 0.01)


class TestHKStock:
    def test_a_shares(self):
        assert not is_hk_stock('603501.SH')
        assert not is_hk_stock('000001.SZ')

    def test_hk_shares(self):
        assert is_hk_stock('00700.HGT')
        assert is_hk_stock('01810.SGT')


class TestTradingHours:
    # A 股: 9:30-11:30, 13:00-15:00
    def test_a_inside(self):
        """U-TIME-001 · P0 · A 股交易时段内"""
        assert is_in_trading_hours('603501.SH', '09:31')
        assert is_in_trading_hours('603501.SH', '11:29')
        assert is_in_trading_hours('603501.SH', '13:01')
        assert is_in_trading_hours('603501.SH', '14:59')

    def test_a_outside(self):
        """U-TIME-001 · P0 · A 股交易时段外"""
        assert not is_in_trading_hours('603501.SH', '09:29')
        assert not is_in_trading_hours('603501.SH', '11:31')
        assert not is_in_trading_hours('603501.SH', '12:30')
        assert not is_in_trading_hours('603501.SH', '15:01')

    def test_hk_am_inside(self):
        """U-TIME-002 · P0 · 港股早市内"""
        assert is_in_trading_hours('00700.HGT', '09:31')
        assert is_in_trading_hours('00700.HGT', '11:59')

    def test_hk_am_outside(self):
        """U-TIME-002 · P0 · 港股早市外"""
        assert not is_in_trading_hours('00700.HGT', '09:29')
        assert not is_in_trading_hours('00700.HGT', '12:01')

    def test_hk_pm_inside(self):
        """U-TIME-003 · P1 · 港股午市内"""
        assert is_in_trading_hours('00700.HGT', '13:01')
        assert is_in_trading_hours('00700.HGT', '15:59')

    def test_hk_pm_outside(self):
        """U-TIME-003 · P1 · 港股午市外"""
        assert not is_in_trading_hours('00700.HGT', '12:59')
        assert not is_in_trading_hours('00700.HGT', '16:01')

    def test_cross_market(self):
        """U-TIME-004 · P0 · 同时刻 A/HK 不同结果"""
        assert is_in_trading_hours('603501.SH', '12:30') is False
        assert is_in_trading_hours('00700.HGT', '12:30') is False
        # 15:30 → A 股已收盘，港股仍在交易
        assert not is_in_trading_hours('603501.SH', '15:30')
        assert is_in_trading_hours('00700.HGT', '15:30')


class TestSignalTime:
    def test_a_signal(self):
        """U-TIME-005 · P1 · A 股 14:55"""
        assert get_signal_time('14:55', '603501.SH') == '14:55'

    def test_hk_am_signal(self):
        """U-TIME-005 · P1 · 港股早市 11:55"""
        assert get_signal_time('11:55', '00700.HGT') == '11:55'

    def test_hk_pm_signal(self):
        """U-TIME-005 · P1 · 港股午市 15:55"""
        assert get_signal_time('15:55', '00700.HGT') == '15:55'

    def test_not_signal_time(self):
        assert get_signal_time('10:30', '603501.SH') is None
        assert get_signal_time('14:30', '603501.SH') is None
        assert get_signal_time('10:30', '00700.HGT') is None

    def test_boundary_inclusive(self):
        """U-TIME-006 · P1 · 整点边界"""
        assert is_in_trading_hours('603501.SH', '09:30')
        assert is_in_trading_hours('603501.SH', '11:30')
        assert is_in_trading_hours('603501.SH', '13:00')
        assert is_in_trading_hours('603501.SH', '15:00')
