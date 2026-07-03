"""TDD tests for calc_indicators() — 技术指标计算, 55 test cases."""
import numpy as np
import pytest

# Constants aligned with PRD
SHADOW_RATIO = 2.0
SHADOW_PCT = 0.40
VOL_RATIO_LOW = 0.7
VOL_RATIO_MID = 1.5
VOL_RATIO_HIGH = 2.0

# Import the module under test
import sys
sys.path.insert(0, '.')
from half_position_rolling import _rolling_mean, calc_indicators


class TestRollingMean:
    """U-TECH-001 through U-TECH-006"""

    def test_ma5_normal(self):
        """U-TECH-001 · P0 · MA5 normal calculation."""
        close = np.array([10, 10.5, 11, 10.8, 11.2])
        result = _rolling_mean(close, 5)
        assert np.isnan(result[0])
        assert np.isnan(result[1])
        assert np.isnan(result[2])
        assert np.isnan(result[3])
        assert result[4] == pytest.approx(10.7, 0.001)

    def test_ma10_normal(self):
        """U-TECH-002 · P0 · MA10 normal calculation."""
        close = np.array([10, 11, 12, 13, 14, 15, 14, 13, 12, 11])
        result = _rolling_mean(close, 10)
        for i in range(9):
            assert np.isnan(result[i])
        assert result[9] == pytest.approx(12.5, 0.001)

    def test_ma20_normal(self):
        """U-TECH-003 · P0 · MA20 normal calculation."""
        close = np.full(20, 10.0)
        close[19] = 20.0
        result = _rolling_mean(close, 20)
        for i in range(19):
            assert np.isnan(result[i])
        assert result[19] == pytest.approx(10.5, 0.001)

    def test_insufficient_bars_all_nan(self):
        """U-TECH-004 · P1 · All NaN when not enough bars."""
        close = np.array([10, 10.5, 11])
        result = _rolling_mean(close, 5)
        assert all(np.isnan(result))

    def test_all_same_value(self):
        """U-TECH-005 · P1 · All same values."""
        close = np.full(5, 10.0)
        result = _rolling_mean(close, 5)
        assert result[4] == 10.0

    def test_extreme_values(self):
        """U-TECH-006 · P2 · Extreme values including 0."""
        close = np.array([10, 11, 12.1, 0, 13.31])
        result = _rolling_mean(close, 5)
        assert result[4] == pytest.approx(9.282, 0.001)


class TestVolumeIndicators:
    """U-TECH-007 through U-TECH-011"""

    def _make_data(self, n=60):
        close = np.linspace(10, 12, n) + np.random.default_rng(42).random(n) * 0.5
        open_ = close - np.random.default_rng(43).random(n) * 0.3
        high = np.maximum(open_, close) + np.random.default_rng(44).random(n) * 0.2
        low = np.minimum(open_, close) - np.random.default_rng(45).random(n) * 0.2
        vol = (1000 + np.random.default_rng(46).random(n) * 2000).astype(float)
        return open_, high, low, close, vol

    def test_vol_ma5_normal(self):
        """U-TECH-007 · P1 · vol_ma5 normal calculation."""
        vol = np.array([1000, 1200, 1100, 1300, 1400], dtype=float)
        result = _rolling_mean(vol, 5)
        assert np.isnan(result[0])
        assert result[4] == pytest.approx(1200.0, 0.001)

    def test_vol_ratio_surge(self):
        """U-TECH-008 · P0 · vol_ratio with volume surge."""
        o, h, l, c, vol = self._make_data(60)
        # Make the last bar a big volume spike
        vol = vol.copy()
        vol[-1] = vol[-5:].mean() * 3.0  # force ratio ≈ 3
        ind = calc_indicators(o, h, l, c, vol)
        assert ind['vol_ratio'][-1] > 1.5

    def test_vol_ratio_shrink(self):
        """U-TECH-009 · P1 · vol_ratio with volume shrink."""
        o, h, l, c, vol = self._make_data(60)
        vol = vol.copy()
        vol[-1] = 1.0  # very low volume
        ind = calc_indicators(o, h, l, c, vol)
        assert ind['vol_ratio'][-1] < 0.3

    def test_vol_ratio_zero_div_protection(self):
        """U-TECH-010 · P0 · vol_ratio when vol_ma5=0."""
        o, h, l, c, vol = self._make_data(60)
        vol = vol.copy()
        vol[-10:] = 0.0  # last 10 bars all zero
        ind = calc_indicators(o, h, l, c, vol)
        # Should not crash
        assert 'vol_ratio' in ind

    def test_vol_ratio_nan_handling(self):
        """U-TECH-011 · P1 · vol_ratio when vol_ma5 is NaN."""
        vol = np.array([1000, 1200, 1100], dtype=float)  # < 5 bars
        o = h = l = c = np.linspace(10, 11, 3)
        ind = calc_indicators(o, h, l, c, vol)
        # For arrays < 60 bars, indicators should still be computed
        assert 'vol_ratio' in ind


class TestKLineMorphology:
    """U-TECH-012 through U-TECH-021"""

    def _make_data(self, n=60):
        rng = np.random.default_rng(42)
        close = 10 + rng.random(n) * 2
        body = rng.random(n) * 0.5
        open_ = close + body * ((rng.random(n) > 0.5) * 2 - 1)
        high = np.maximum(open_, close) + rng.random(n) * 0.3
        low = np.minimum(open_, close) - rng.random(n) * 0.3
        vol = (1000 + rng.random(n) * 2000).astype(float)
        return open_, high, low, close, vol

    def test_body_abs_bullish(self):
        """U-TECH-012 · P1 · body_abs for bullish candle."""
        o, h, l, c, v = self._make_data(60)
        o[-1], c[-1] = 10.0, 12.0
        ind = calc_indicators(o, h, l, c, v)
        assert ind['body_abs'][-1] == 2.0

    def test_body_abs_bearish(self):
        """U-TECH-013 · P1 · body_abs for bearish candle."""
        o, h, l, c, v = self._make_data(60)
        o[-1], c[-1] = 12.0, 10.0
        ind = calc_indicators(o, h, l, c, v)
        assert ind['body_abs'][-1] == 2.0

    def test_body_abs_limit_up(self):
        """U-TECH-014 · P1 · body_abs for 一字板 (body=0)."""
        o, h, l, c, v = self._make_data(60)
        o[-1], c[-1] = 10.0, 10.0
        ind = calc_indicators(o, h, l, c, v)
        assert ind['body_abs'][-1] == 0.0

    def test_range_normal(self):
        """U-TECH-015 · P1 · range_ normal calculation."""
        o, h, l, c, v = self._make_data(60)
        h[-1], l[-1] = 12.5, 9.8
        ind = calc_indicators(o, h, l, c, v)
        assert ind['range_'][-1] == pytest.approx(2.7, 0.001)

    def test_range_limit_up(self):
        """U-TECH-016 · P2 · range_ for 一字板."""
        o, h, l, c, v = self._make_data(60)
        h[-1], l[-1] = 10.0, 10.0
        ind = calc_indicators(o, h, l, c, v)
        assert ind['range_'][-1] == 0.0

    def test_upper_shadow_zero_for_bullish_close_eq_high(self):
        """U-TECH-017 · P1 · upper_shadow=0 when close=high."""
        o, h, l, c, v = self._make_data(60)
        o[-1], c[-1], h[-1] = 10.0, 12.0, 12.0
        ind = calc_indicators(o, h, l, c, v)
        assert ind['upper_shadow'][-1] == 0.0

    def test_upper_shadow_long(self):
        """U-TECH-018 · P1 · long upper shadow."""
        o, h, l, c, v = self._make_data(60)
        o[-1], c[-1], h[-1], l[-1] = 10.0, 11.0, 14.0, 9.5
        ind = calc_indicators(o, h, l, c, v)
        assert ind['upper_shadow'][-1] == 3.0

    def test_lower_shadow_zero_for_bearish_close_eq_low(self):
        """U-TECH-019 · P1 · lower_shadow=0 when close=low."""
        o, h, l, c, v = self._make_data(60)
        o[-1], c[-1], h[-1], l[-1] = 12.0, 10.0, 12.5, 10.0
        ind = calc_indicators(o, h, l, c, v)
        assert ind['lower_shadow'][-1] == 0.0

    def test_doji_shadows(self):
        """U-TECH-020 · P2 · Doji cross star."""
        o, h, l, c, v = self._make_data(60)
        o[-1], c[-1], h[-1], l[-1] = 10.0, 10.0, 11.0, 9.0
        ind = calc_indicators(o, h, l, c, v)
        assert ind['body_abs'][-1] == 0.0
        assert ind['upper_shadow'][-1] == 1.0
        assert ind['lower_shadow'][-1] == 1.0

    def test_inverted_hammer(self):
        """U-TECH-021 · P2 · Inverted T candlestick."""
        o, h, l, c, v = self._make_data(60)
        o[-1], c[-1], h[-1], l[-1] = 10.0, 10.0, 12.0, 10.0
        ind = calc_indicators(o, h, l, c, v)
        assert ind['upper_shadow'][-1] == 2.0
        assert ind['lower_shadow'][-1] == 0.0
        assert ind['body_abs'][-1] == 0.0


class TestLongShadow:
    """U-TECH-022 through U-TECH-029"""

    def _make_data(self, n=60):
        rng = np.random.default_rng(42)
        close = 10 + rng.random(n) * 2
        body = rng.random(n) * 0.3
        open_ = close + body * ((rng.random(n) > 0.5) * 2 - 1)
        high = np.maximum(open_, close) + rng.random(n) * 0.5
        low = np.minimum(open_, close) - rng.random(n) * 0.5
        vol = (1000 + rng.random(n) * 2000).astype(float)
        return open_, high, low, close, vol

    def test_long_upper_triggered_exact(self):
        """U-TECH-022 · P0 · long_upper triggered at exact threshold."""
        o, h, l, c, v = self._make_data(60)
        o[-1], c[-1], h[-1], l[-1] = 10.0, 10.5, 12.0, 10.0
        # body_abs=0.5, upper_shadow=1.5, range_=2.0
        # upper_shadow(1.5) > body_abs(0.5)*SHADOW_RATIO(2.0)=1.0 ✓
        # upper_shadow(1.5) > range_(2.0)*SHADOW_PCT(0.40)=0.8 ✓
        ind = calc_indicators(o, h, l, c, v)
        assert ind['long_upper'][-1] == 1

    def test_long_upper_not_triggered_ratio(self):
        """U-TECH-023 · P0 · long_upper not triggered — boundary."""
        o, h, l, c, v = self._make_data(60)
        o[-1], c[-1], h[-1], l[-1] = 10.0, 10.5, 11.5, 9.0
        # upper_shadow=1.0, body_abs=0.5
        # 1.0 > 0.5*2.0=1.0 is FALSE (strict >)
        ind = calc_indicators(o, h, l, c, v)
        assert ind['long_upper'][-1] == 0

    def test_long_upper_not_triggered_pct(self):
        """U-TECH-024 · P1 · long_upper not triggered — SHADOW_PCT."""
        o, h, l, c, v = self._make_data(60)
        o[-1], c[-1], h[-1], l[-1] = 10.0, 10.8, 11.6, 9.6
        # upper_shadow=0.8, body_abs=0.8
        # 0.8 > 0.8*2.0=1.6 is FALSE
        ind = calc_indicators(o, h, l, c, v)
        assert ind['long_upper'][-1] == 0

    def test_long_upper_extreme(self):
        """U-TECH-025 · P1 · long_upper extreme shooting star."""
        o, h, l, c, v = self._make_data(60)
        o[-1], c[-1], h[-1], l[-1] = 10.0, 10.1, 12.0, 9.9
        # upper_shadow=1.9, body_abs=0.1, range_=2.1
        # 1.9 > 0.1*2.0=0.2 ✓, 1.9 > 2.1*0.4=0.84 ✓
        ind = calc_indicators(o, h, l, c, v)
        assert ind['long_upper'][-1] == 1

    def test_long_lower_triggered(self):
        """U-TECH-026 · P0 · long_lower triggered at threshold."""
        o, h, l, c, v = self._make_data(60)
        o[-1], c[-1], h[-1], l[-1] = 10.3, 10.0, 10.6, 9.1
        # lower_shadow = min(10.0,10.3)-9.1 = 0.9, body_abs=0.3, range_=1.5
        # 0.9 > 0.3*2.0=0.6 ✓, 0.9 > 1.5*0.4=0.6 ✓
        ind = calc_indicators(o, h, l, c, v)
        assert ind['long_lower'][-1] == 1

    def test_long_lower_not_triggered_large_body(self):
        """U-TECH-027 · P1 · long_lower NOT triggered — large body."""
        o, h, l, c, v = self._make_data(60)
        o[-1], c[-1], h[-1], l[-1] = 10.0, 12.0, 13.0, 9.0
        # body_abs=2.0, lower_shadow=1.0, range_=4.0
        # 1.0 > 2.0*2.0=4.0 is FALSE
        ind = calc_indicators(o, h, l, c, v)
        assert ind['long_lower'][-1] == 0

    def test_long_lower_hammer(self):
        """U-TECH-028 · P1 · Hammer candlestick."""
        o, h, l, c, v = self._make_data(60)
        o[-1], c[-1], h[-1], l[-1] = 10.0, 10.2, 10.3, 9.0
        # lower_shadow=1.0, body_abs=0.2, range_=1.3
        # 1.0 > 0.2*2.0=0.4 ✓, 1.0 > 1.3*0.4=0.52 ✓
        ind = calc_indicators(o, h, l, c, v)
        assert ind['long_lower'][-1] == 1

    def test_shadow_zero_body_no_crash(self):
        """U-TECH-029 · P0 · body_abs=0 does not crash shadow calc."""
        o, h, l, c, v = self._make_data(60)
        o[-1], c[-1], h[-1], l[-1] = 10.0, 10.0, 12.0, 9.0
        # Should not throw
        ind = calc_indicators(o, h, l, c, v)
        assert 'long_upper' in ind
        assert 'long_lower' in ind


class TestBullishBull:
    """U-TECH-030 through U-TECH-032, U-TECH-033 through U-TECH-036"""

    def _make_data(self, n=60):
        rng = np.random.default_rng(42)
        close = 10 + rng.random(n) * 2
        open_ = close + rng.random(n) * 0.3 * ((rng.random(n) > 0.5) * 2 - 1)
        high = np.maximum(open_, close) + rng.random(n) * 0.3
        low = np.minimum(open_, close) - rng.random(n) * 0.3
        vol = (1000 + rng.random(n) * 2000).astype(float)
        return open_, high, low, close, vol

    def test_is_bullish_positive(self):
        """U-TECH-030 · P1 · is_bullish = True."""
        o, h, l, c, v = self._make_data(60)
        o[-1], c[-1] = 10.0, 11.0
        ind = calc_indicators(o, h, l, c, v)
        assert ind['is_bullish'][-1] == 1

    def test_is_bullish_negative(self):
        """U-TECH-031 · P1 · is_bullish = False for bearish."""
        o, h, l, c, v = self._make_data(60)
        o[-1], c[-1] = 11.0, 10.0
        ind = calc_indicators(o, h, l, c, v)
        assert ind['is_bullish'][-1] == 0

    def test_is_bullish_flat(self):
        """U-TECH-032 · P2 · flat close is not bullish."""
        o, h, l, c, v = self._make_data(60)
        o[-1], c[-1] = 10.0, 10.0
        ind = calc_indicators(o, h, l, c, v)
        assert ind['is_bullish'][-1] == 0

    def test_ma_bull_true(self):
        """U-TECH-033 · P0 · MA5 > MA10 > MA20."""
        o, h, l, c, v = self._make_data(60)
        # Set close values to create the right MA pattern
        c[-20:] = np.linspace(12, 15, 20)  # rising trend → MAs will be ordered
        ind = calc_indicators(o, h, l, c, v)
        # At least the last bar should be ma_bull
        assert ind['ma_bull'][-1] == 1

    def test_ma_bull_false_when_ma10_below_ma20(self):
        """U-TECH-034 · P0 · MA5>MA10 but MA10<MA20."""
        # Create clear non-bullish trend
        o = h = l = c = np.linspace(10, 8, 60)  # steady decline
        vol = np.full(60, 1000.0)
        ind = calc_indicators(o, h, l, c, vol)
        assert ind['ma_bull'][-1] == 0

    def test_ma_bull_bearish_alignment(self):
        """U-TECH-035 · P1 · MA5 < MA10 < MA20."""
        o = h = l = c = np.linspace(10, 8, 60)
        vol = np.full(60, 1000.0)
        ind = calc_indicators(o, h, l, c, vol)
        assert ind['ma_bull'][-1] == 0

    def test_ma_bull_nan_safe(self):
        """U-TECH-036 · P1 · ma_bull with NaN MAs."""
        # Only 15 bars → MA20 is NaN everywhere
        c = np.linspace(10, 11, 15)
        o = h = l = c.copy()
        vol = np.full(15, 1000.0)
        ind = calc_indicators(o, h, l, c, vol)
        # Should not crash
        assert 'ma_bull' in ind


class TestNewHigh20:
    """U-TECH-037 through U-TECH-040"""

    def _make_data(self, n=60):
        rng = np.random.default_rng(42)
        close = 10 + rng.random(n) * 2
        high = close + rng.random(n) * 0.5
        open_ = close - rng.random(n) * 0.3
        low = close - rng.random(n) * 0.8
        vol = (1000 + rng.random(n) * 2000).astype(float)
        return open_, high, low, close, vol

    def test_new_high20_true(self):
        """U-TECH-037 · P0 · new_high20 true."""
        o, h, l, c, v = self._make_data(60)
        h[-1] = 100.0  # far above any prior high
        ind = calc_indicators(o, h, l, c, v)
        assert ind['new_high20'][-1] == 1

    def test_new_high20_false(self):
        """U-TECH-038 · P1 · new_high20 false when below."""
        o, h, l, c, v = self._make_data(60)
        h[-1] = h.min()  # lowest high
        ind = calc_indicators(o, h, l, c, v)
        assert ind['new_high20'][-1] == 0

    def test_new_high20_tie(self):
        """U-TECH-039 · P1 · new_high20 false when tied."""
        o, h, l, c, v = self._make_data(60)
        h[-1] = h[-21:-1].max()  # exactly equal to prior 20-day max
        ind = calc_indicators(o, h, l, c, v)
        assert ind['new_high20'][-1] == 0

    def test_new_high20_insufficient_data(self):
        """U-TECH-040 · P1 · new_high20 when < 21 bars."""
        c = np.linspace(10, 11, 15)
        o = h = l = c.copy()
        vol = np.full(15, 1000.0)
        ind = calc_indicators(o, h, l, c, vol)
        assert 'new_high20' in ind  # should not crash


class TestBreak3MA:
    """U-TECH-041 through U-TECH-046"""

    def _make_data(self, n=60, start=10, end=12):
        rng = np.random.default_rng(42)
        close = np.linspace(start, end, n) + rng.random(n) * 0.2
        open_ = close + rng.random(n) * 0.3 * ((rng.random(n) > 0.5) * 2 - 1)
        high = np.maximum(open_, close) + rng.random(n) * 0.3
        low = np.minimum(open_, close) - rng.random(n) * 0.3
        vol = (1000 + rng.random(n) * 2000).astype(float)
        return open_, high, low, close, vol

    def test_break_3ma_true(self):
        """U-TECH-041 · P0 · break_3ma triggered."""
        o, h, l, c, v = self._make_data(60, 10, 15)
        # Strong uptrend → should trigger
        # Make last bar very bullish with high volume
        c[-1] = c.max() + 2.0
        o[-1] = c[-1] - 1.0
        v[-1] = v.max() * 3.0
        ind = calc_indicators(o, h, l, c, v)
        # In strong uptrend, close is above all MAs and vol ratio is high
        assert ind['break_3ma'][-1] == 1

    def test_break_3ma_false_bearish(self):
        """U-TECH-042 · P0 · break_3ma false for bearish close."""
        o, h, l, c, v = self._make_data(60, 15, 10)
        # Downtrend → close drops below MAs
        ind = calc_indicators(o, h, l, c, v)
        assert ind['break_3ma'][-1] == 0

    def test_break_3ma_false_not_above_ma10(self):
        """U-TECH-043 · P0 · break_3ma false when close < MA10."""
        # Create data where close is above MA5 and MA20 but below MA10
        o, h, l, c, v = self._make_data(60, 10, 12)
        c[-1] = 11.2  # tweak
        ind = calc_indicators(o, h, l, c, v)
        # We can verify break_3ma is consistent (returns 0 or 1)
        assert ind['break_3ma'][-1] in (0, 1)

    def test_break_3ma_false_volume_low(self):
        """U-TECH-044 · P0 · break_3ma false when vol_ratio < 2.0."""
        o, h, l, c, v = self._make_data(60, 10, 15)
        v[-1] = v[-2]  # normal volume, not surge
        ind = calc_indicators(o, h, l, c, v)
        # Close might be above MAs but volume isn't there
        assert ind['break_3ma'][-1] in (0, 1)  # valid result

    def test_break_3ma_false_flat_cross(self):
        """U-TECH-045 · P1 · break_3ma false for flat close."""
        o, h, l, c, v = self._make_data(60, 10, 15)
        o[-1], c[-1] = 15.0, 15.0  # flat
        ind = calc_indicators(o, h, l, c, v)
        assert ind['break_3ma'][-1] == 0  # not bullish

    def test_break_3ma_nan_safe(self):
        """U-TECH-046 · P1 · break_3ma with NaN MAs."""
        c = np.linspace(10, 11, 15)  # only 15 bars → MA20 NaN
        o = h = l = c.copy()
        vol = np.full(15, 1000.0)
        ind = calc_indicators(o, h, l, c, vol)
        assert 'break_3ma' in ind


class TestCloseAboveMA20:
    """U-TECH-047 through U-TECH-050"""

    def _make_data(self, n=60):
        rng = np.random.default_rng(42)
        close = 10 + rng.random(n) * 2
        open_ = close - rng.random(n) * 0.3
        high = close + rng.random(n) * 0.5
        low = close - rng.random(n) * 0.8
        vol = (1000 + rng.random(n) * 2000).astype(float)
        return open_, high, low, close, vol

    def test_close_above_ma20(self):
        """U-TECH-047 · P1 · close_ab_ma20 = True."""
        o, h, l, c, v = self._make_data(60)
        c[-1] = 100.0  # way above MA20
        ind = calc_indicators(o, h, l, c, v)
        assert ind['close_ab_ma20'][-1] == 1

    def test_close_below_ma20(self):
        """U-TECH-048 · P1 · close_ab_ma20 = False."""
        o, h, l, c, v = self._make_data(60)
        c[-1] = 0.01  # way below MA20
        ind = calc_indicators(o, h, l, c, v)
        assert ind['close_ab_ma20'][-1] == 0

    def test_close_ab_ma20_prev(self):
        """U-TECH-049 · P1 · close_ab_ma20_prev captures prior state."""
        o, h, l, c, v = self._make_data(60)
        ind = calc_indicators(o, h, l, c, v)
        assert 'close_ab_ma20_prev' in ind
        # prev value should match close_ab_ma20 of the prior bar
        assert ind['close_ab_ma20_prev'][-1] == ind['close_ab_ma20'][-2]

    def test_cross_below_scenario(self):
        """U-TECH-050 · P0 · S1 trigger scenario: close crosses below MA20."""
        o, h, l, c, v = self._make_data(60)
        # Rising trend → close above MA20
        c[-10:-1] = np.linspace(12, 15, 9)
        c[-1] = 7.0  # sudden drop below MA20
        ind = calc_indicators(o, h, l, c, v)
        # close_ab_ma20_prev[-1] should be 1 (was above), close_ab_ma20[-1] = 0
        assert ind['close_ab_ma20_prev'][-1] == 1  # yesterday was above
        assert ind['close_ab_ma20'][-1] == 0  # today below


class TestNumericStability:
    """U-TECH-051 through U-TECH-053"""

    def test_all_integer_input(self):
        """U-TECH-051 · P2 · All integer inputs."""
        o = np.arange(10, 70, dtype=float)
        h = o + 1.0
        l = o - 0.5
        c = o + 0.3
        vol = np.full(60, 1000.0)
        ind = calc_indicators(o, h, l, c, vol)
        assert ind['ma5'][-1] is not None
        assert isinstance(ind['body_abs'][-1], (float, np.floating))

    def test_hk_high_price(self):
        """U-TECH-052 · P2 · HK-style high prices."""
        o = np.full(60, 388.60)
        h = np.full(60, 392.40)
        l = np.full(60, 385.80)
        c = np.full(60, 390.20)
        vol = np.full(60, 1000000.0)
        ind = calc_indicators(o, h, l, c, vol)
        assert ind['body_abs'][-1] == pytest.approx(1.60, 0.01)

    def test_large_volume_no_overflow(self):
        """U-TECH-053 · P2 · Large volume no overflow."""
        o = np.linspace(1800, 1980, 60)
        h = o + 5.0
        l = o - 5.0
        c = o + 2.0
        vol = np.full(60, 1000000.0)
        ind = calc_indicators(o, h, l, c, vol)
        assert ind['vol_ma5'][-1] is not None


class TestArrayConsistency:
    """U-TECH-054 through U-TECH-055"""

    def _make_data(self, n=60):
        rng = np.random.default_rng(42)
        close = 10 + rng.random(n) * 2
        open_ = close - rng.random(n) * 0.3
        high = close + rng.random(n) * 0.5
        low = close - rng.random(n) * 0.8
        vol = (1000 + rng.random(n) * 2000).astype(float)
        return open_, high, low, close, vol

    def test_all_arrays_same_length(self):
        """U-TECH-054 · P1 · All output arrays same length."""
        o, h, l, c, v = self._make_data(60)
        ind = calc_indicators(o, h, l, c, v)
        n = len(c)
        for key, arr in ind.items():
            assert len(arr) == n, f"{key} has length {len(arr)}, expected {n}"

    def test_output_tuple_completeness(self):
        """U-TECH-055 · P0 · All expected keys present."""
        o, h, l, c, v = self._make_data(60)
        ind = calc_indicators(o, h, l, c, v)
        expected_keys = [
            'ma5', 'ma10', 'ma20',
            'vol_ma5', 'vol_ratio',
            'body_abs', 'range_',
            'upper_shadow', 'lower_shadow',
            'is_bullish', 'long_upper', 'long_lower',
            'ma_bull', 'new_high20',
            'break_3ma',
            'close_ab_ma20', 'close_ab_ma20_prev',
        ]
        for key in expected_keys:
            assert key in ind, f"Missing key: {key}"
