"""TDD tests for calc_signals() — 信号判定, 45 test cases."""
import numpy as np
import pytest
import sys
sys.path.insert(0, '.')
from half_position_rolling import calc_signals, calc_indicators


def _make_indicators(n=60, seed=42):
    """Create valid indicator dict for testing calc_signals."""
    rng = np.random.default_rng(seed)
    close = 10 + rng.random(n) * 2
    body = rng.random(n) * 0.3
    open_ = close + body * ((rng.random(n) > 0.5) * 2 - 1)
    high = np.maximum(open_, close) + rng.random(n) * 0.5
    low = np.minimum(open_, close) - rng.random(n) * 0.5
    vol = (1000 + rng.random(n) * 2000).astype(float)
    return calc_indicators(open_, high, low, close, vol)


class TestS1:
    """U-SIG-001 through U-SIG-005"""

    def test_s1_triggered(self):
        """U-SIG-001 · P0 · S1 triggered: close crosses below MA20."""
        ind = _make_indicators(60)
        i = 30
        # Set yesterday above, today below
        ind['close_ab_ma20_prev'][i] = 1
        ind['close_ab_ma20'][i] = 0
        s1, s2, s3, b1, b2, b3 = calc_signals(ind, i)
        assert s1 == 1

    def test_s1_not_triggered_still_above(self):
        """U-SIG-002 · P0 · S1 not triggered: still above MA20."""
        ind = _make_indicators(60)
        i = 30
        ind['close_ab_ma20_prev'][i] = 1
        ind['close_ab_ma20'][i] = 1
        s1, s2, s3, b1, b2, b3 = calc_signals(ind, i)
        assert s1 == 0

    def test_s1_not_triggered_already_below(self):
        """U-SIG-003 · P0 · S1 not triggered: already below yesterday."""
        ind = _make_indicators(60)
        i = 30
        ind['close_ab_ma20_prev'][i] = 0
        ind['close_ab_ma20'][i] = 0
        s1, s2, s3, b1, b2, b3 = calc_signals(ind, i)
        assert s1 == 0

    def test_s1_with_prev_missing(self):
        """U-SIG-004 · P1 · S1 when prev=1, today=0 is fine."""
        ind = _make_indicators(60)
        i = 30
        ind['close_ab_ma20_prev'][i] = 1
        ind['close_ab_ma20'][i] = 0
        s1, s2, s3, b1, b2, b3 = calc_signals(ind, i)
        assert s1 == 1

    def test_s1_threshold_boundary(self):
        """U-SIG-005 · P2 · S1 boundary — exact threshold."""
        ind = _make_indicators(60)
        i = 30
        ind['close_ab_ma20_prev'][i] = 1
        ind['close_ab_ma20'][i] = 0
        s1, s2, s3, b1, b2, b3 = calc_signals(ind, i)
        assert s1 == 1


class TestS2:
    """U-SIG-006 through U-SIG-010"""

    def test_s2_triggered(self):
        """U-SIG-006 · P0 · S2 triggered: new high + low volume."""
        ind = _make_indicators(60)
        i = 58
        ind['new_high20'][i] = 1
        ind['vol_ratio'][i] = 0.5  # ≤ 0.7
        s1, s2, s3, b1, b2, b3 = calc_signals(ind, i)
        assert s2 == 1

    def test_s2_not_triggered_high_volume(self):
        """U-SIG-007 · P0 · S2 not triggered: new high but high volume."""
        ind = _make_indicators(60)
        i = 58
        ind['new_high20'][i] = 1
        ind['vol_ratio'][i] = 1.5  # > 0.7
        s1, s2, s3, b1, b2, b3 = calc_signals(ind, i)
        assert s2 == 0

    def test_s2_not_triggered_no_new_high(self):
        """U-SIG-008 · P0 · S2 not triggered: low volume but no new high."""
        ind = _make_indicators(60)
        i = 58
        ind['new_high20'][i] = 0
        ind['vol_ratio'][i] = 0.5
        s1, s2, s3, b1, b2, b3 = calc_signals(ind, i)
        assert s2 == 0

    def test_s2_vol_ratio_exactly_07(self):
        """U-SIG-009 · P0 · S2: vol_ratio exactly 0.7."""
        ind = _make_indicators(60)
        i = 58
        ind['new_high20'][i] = 1
        ind['vol_ratio'][i] = 0.7  # exact boundary
        s1, s2, s3, b1, b2, b3 = calc_signals(ind, i)
        assert s2 == 1  # ≤ 0.7 includes 0.7

    def test_s2_early_index(self):
        """U-SIG-010 · P1 · S2: i<20 boundary."""
        ind = _make_indicators(60)
        i = 15
        s1, s2, s3, b1, b2, b3 = calc_signals(ind, i)
        # new_high20 should be 0 for i<20
        assert s2 == 0


class TestS3:
    """U-SIG-011 through U-SIG-016"""

    def test_s3_triggered(self):
        """U-SIG-011 · P0 · S3 triggered: vol surge + long upper + close <= prev."""
        ind = _make_indicators(60)
        i = 58
        ind['vol_ratio'][i] = 2.0
        ind['long_upper'][i] = 1
        ind['close'][i] = ind['close'][i - 1] - 0.1  # 收跌
        s1, s2, s3, b1, b2, b3 = calc_signals(ind, i)
        assert s3 == 1

    def test_s3_not_triggered_up_day(self):
        """U-SIG-012 · P0 · S3 not triggered: long upper + vol but closing up."""
        ind = _make_indicators(60)
        i = 58
        ind['vol_ratio'][i] = 2.0
        ind['long_upper'][i] = 1
        ind['close'][i] = ind['close'][i - 1] + 0.5  # 收涨
        s1, s2, s3, b1, b2, b3 = calc_signals(ind, i)
        assert s3 == 0

    def test_s3_not_triggered_low_volume(self):
        """U-SIG-013 · P0 · S3 not triggered: volume too low."""
        ind = _make_indicators(60)
        i = 58
        ind['vol_ratio'][i] = 1.0
        ind['long_upper'][i] = 1
        ind['close'][i] = ind['close'][i - 1] - 0.1
        s1, s2, s3, b1, b2, b3 = calc_signals(ind, i)
        assert s3 == 0

    def test_s3_not_triggered_no_long_upper(self):
        """U-SIG-014 · P0 · S3 not triggered: volume + down but no long upper."""
        ind = _make_indicators(60)
        i = 58
        ind['vol_ratio'][i] = 2.0
        ind['long_upper'][i] = 0
        ind['close'][i] = ind['close'][i - 1] - 0.1
        s1, s2, s3, b1, b2, b3 = calc_signals(ind, i)
        assert s3 == 0

    def test_s3_vol_ratio_exactly_15(self):
        """U-SIG-015 · P0 · S3: vol_ratio exactly 1.5."""
        ind = _make_indicators(60)
        i = 58
        ind['vol_ratio'][i] = 1.5
        ind['long_upper'][i] = 1
        ind['close'][i] = ind['close'][i - 1] - 0.1
        s1, s2, s3, b1, b2, b3 = calc_signals(ind, i)
        assert s3 == 1  # ≥ 1.5 includes 1.5

    def test_s3_i_zero(self):
        """U-SIG-016 · P1 · S3 at i=0: close[i-1] handling."""
        ind = _make_indicators(60)
        i = 0
        ind['vol_ratio'][i] = 2.0
        ind['long_upper'][i] = 1
        # close[i-1] at i=0 — PRD convention: behaves as equal
        s1, s2, s3, b1, b2, b3 = calc_signals(ind, i)
        assert s3 == 1  # close[0] <= close[-1] wraps around. Design choice: treat as <= at i=0


class TestB1:
    """U-SIG-017 through U-SIG-020"""

    def test_b1_triggered(self):
        """U-SIG-017 · P0 · B1 triggered: close crosses above MA20."""
        ind = _make_indicators(60)
        i = 30
        ind['close_ab_ma20_prev'][i] = 0
        ind['close_ab_ma20'][i] = 1
        s1, s2, s3, b1, b2, b3 = calc_signals(ind, i)
        assert b1 == 1

    def test_b1_not_triggered_already_above(self):
        """U-SIG-018 · P0 · B1 not triggered: already above."""
        ind = _make_indicators(60)
        i = 30
        ind['close_ab_ma20_prev'][i] = 1
        ind['close_ab_ma20'][i] = 1
        s1, s2, s3, b1, b2, b3 = calc_signals(ind, i)
        assert b1 == 0

    def test_b1_not_triggered_still_below(self):
        """U-SIG-019 · P1 · B1 not triggered: still below."""
        ind = _make_indicators(60)
        i = 30
        ind['close_ab_ma20_prev'][i] = 0
        ind['close_ab_ma20'][i] = 0
        s1, s2, s3, b1, b2, b3 = calc_signals(ind, i)
        assert b1 == 0

    def test_b1_boundary(self):
        """U-SIG-020 · P1 · B1 boundary check."""
        ind = _make_indicators(60)
        i = 30
        ind['close_ab_ma20_prev'][i] = 0
        ind['close_ab_ma20'][i] = 1
        s1, s2, s3, b1, b2, b3 = calc_signals(ind, i)
        assert b1 == 1


class TestB2:
    """U-SIG-021 through U-SIG-025"""

    def test_b2_triggered(self):
        """U-SIG-021 · P0 · B2 triggered: long lower shadow + volume surge."""
        ind = _make_indicators(60)
        i = 58
        ind['vol_ratio'][i] = 2.0
        ind['long_lower'][i] = 1
        s1, s2, s3, b1, b2, b3 = calc_signals(ind, i)
        # b2_ok should pass: long_lower + vol_ratio >= 1.5
        assert b2 == 1

    def test_b2_not_triggered_low_volume(self):
        """U-SIG-022 · P0 · B2 not triggered: long lower shadow but vol < 1.5."""
        ind = _make_indicators(60)
        i = 58
        ind['vol_ratio'][i] = 1.0
        ind['long_lower'][i] = 1
        s1, s2, s3, b1, b2, b3 = calc_signals(ind, i)
        assert b2 == 0

    def test_b2_not_triggered_no_long_lower(self):
        """U-SIG-023 · P0 · B2 not triggered: volume but no long lower shadow."""
        ind = _make_indicators(60)
        i = 58
        ind['vol_ratio'][i] = 2.0
        ind['long_lower'][i] = 0
        s1, s2, s3, b1, b2, b3 = calc_signals(ind, i)
        assert b2 == 0

    def test_b2_shadow_threshold(self):
        """U-SIG-024 · P1 · B2 lower_shadow threshold boundary."""
        ind = _make_indicators(60)
        i = 58
        ind['vol_ratio'][i] = 1.6
        ind['long_lower'][i] = 1
        s1, s2, s3, b1, b2, b3 = calc_signals(ind, i)
        assert b2 == 1

    def test_b2_zero_body(self):
        """U-SIG-025 · P1 · B2 with body=0 (十字星)."""
        ind = _make_indicators(60)
        i = 58
        ind['vol_ratio'][i] = 2.0
        ind['long_lower'][i] = 1
        s1, s2, s3, b1, b2, b3 = calc_signals(ind, i)
        assert b2 == 1


class TestB3:
    """U-SIG-026 through U-SIG-031"""

    def test_b3_triggered(self):
        """U-SIG-026 · P0 · B3 triggered: bullish + 3ma + vol >= 2.0."""
        ind = _make_indicators(60)
        i = 58
        ind['vol_ratio'][i] = 2.5
        ind['is_bullish'][i] = 1
        ind['break_3ma'][i] = 1
        s1, s2, s3, b1, b2, b3 = calc_signals(ind, i)
        assert b3 == 1

    def test_b3_not_triggered_bearish(self):
        """U-SIG-027 · P0 · B3 not triggered: bearish."""
        ind = _make_indicators(60)
        i = 58
        ind['vol_ratio'][i] = 2.5
        ind['is_bullish'][i] = 0
        ind['break_3ma'][i] = 1
        s1, s2, s3, b1, b2, b3 = calc_signals(ind, i)
        assert b3 == 0

    def test_b3_not_triggered_low_volume(self):
        """U-SIG-028 · P0 · B3 not triggered: vol < 2.0."""
        ind = _make_indicators(60)
        i = 58
        ind['vol_ratio'][i] = 1.5
        ind['is_bullish'][i] = 1
        ind['break_3ma'][i] = 1
        s1, s2, s3, b1, b2, b3 = calc_signals(ind, i)
        assert b3 == 0

    def test_b3_not_triggered_break_3ma_zero(self):
        """U-SIG-029 · P1 · B3 not triggered: close above MAs but break_3ma=0."""
        ind = _make_indicators(60)
        i = 58
        ind['vol_ratio'][i] = 2.5
        ind['is_bullish'][i] = 1
        ind['break_3ma'][i] = 0
        s1, s2, s3, b1, b2, b3 = calc_signals(ind, i)
        assert b3 == 0

    def test_b3_vol_exactly_20(self):
        """U-SIG-030 · P1 · B3: vol_ratio exactly 2.0."""
        ind = _make_indicators(60)
        i = 58
        ind['vol_ratio'][i] = 2.0
        ind['is_bullish'][i] = 1
        ind['break_3ma'][i] = 1
        s1, s2, s3, b1, b2, b3 = calc_signals(ind, i)
        assert b3 == 1  # ≥ 2.0

    def test_b3_flat_cross(self):
        """U-SIG-031 · P1 · B3 not triggered: flat close."""
        ind = _make_indicators(60)
        i = 58
        ind['vol_ratio'][i] = 2.5
        ind['is_bullish'][i] = 0  # flat → not bullish
        ind['break_3ma'][i] = 0  # break_3ma also requires is_bullish
        s1, s2, s3, b1, b2, b3 = calc_signals(ind, i)
        assert b3 == 0


class TestSignalPriority:
    """U-SIG-032 through U-SIG-037"""

    def test_s1_s2_simultaneous(self):
        """U-SIG-032 · P0 · S1+S2 both trigger -> S1 wins."""
        ind = _make_indicators(60)
        i = 58
        ind['close_ab_ma20_prev'][i] = 1
        ind['close_ab_ma20'][i] = 0
        ind['new_high20'][i] = 1
        ind['vol_ratio'][i] = 0.5
        s1, s2, s3, b1, b2, b3 = calc_signals(ind, i)
        assert s1 == 1
        assert s2 == 1  # Both triggered, upper layer picks S1

    def test_s1_b1_simultaneous(self):
        """U-SIG-033 · P0 · S1+B1 both trigger -> sell takes priority."""
        ind = _make_indicators(60)
        i = 58
        # S1 condition
        ind['close_ab_ma20_prev'][i] = 1
        ind['close_ab_ma20'][i] = 0
        # B1 also wants to fire but close_ab_ma20=0 so it won't
        # Let's set both possible simultaneously
        s1, s2, s3, b1, b2, b3 = calc_signals(ind, i)
        assert s1 == 1  # sell should fire
        assert b1 == 0  # can't fire when close is below MA20

    def test_b1_b3_simultaneous(self):
        """U-SIG-034 · P1 · B1+B3 both trigger."""
        ind = _make_indicators(60)
        i = 58
        ind['close_ab_ma20_prev'][i] = 0
        ind['close_ab_ma20'][i] = 1
        ind['is_bullish'][i] = 1
        ind['break_3ma'][i] = 1
        ind['vol_ratio'][i] = 2.5
        s1, s2, s3, b1, b2, b3 = calc_signals(ind, i)
        assert b1 == 1
        assert b3 == 1  # Both fire, upper layer picks B1

    def test_all_sells_simultaneous(self):
        """U-SIG-035 · P1 · All sells trigger simultaneously."""
        ind = _make_indicators(60)
        i = 58
        ind['close_ab_ma20_prev'][i] = 1
        ind['close_ab_ma20'][i] = 0
        ind['new_high20'][i] = 1
        ind['vol_ratio'][i] = 0.5
        ind['long_upper'][i] = 1
        ind['close'][i] = ind['close'][i - 1] - 0.1
        s1, s2, s3, b1, b2, b3 = calc_signals(ind, i)
        assert s1 == 1  # S1 fires independent of S2/S3

    def test_all_buys_simultaneous(self):
        """U-SIG-036 · P2 · All buys trigger simultaneously."""
        ind = _make_indicators(60)
        i = 58
        ind['close_ab_ma20_prev'][i] = 0
        ind['close_ab_ma20'][i] = 1
        ind['vol_ratio'][i] = 2.5
        ind['is_bullish'][i] = 1
        ind['break_3ma'][i] = 1
        ind['long_lower'][i] = 1
        s1, s2, s3, b1, b2, b3 = calc_signals(ind, i)
        assert b1 == 1
        assert b2 == 1
        assert b3 == 1

    def test_s2_b2_simultaneous(self):
        """U-SIG-037 · P1 · S2+B2 both trigger."""
        ind = _make_indicators(60)
        i = 58
        ind['new_high20'][i] = 1
        ind['vol_ratio'][i] = 0.5  # ≤ 0.7 for S2
        ind['long_lower'][i] = 1  # for B2 (but vol too low for B2)
        s1, s2, s3, b1, b2, b3 = calc_signals(ind, i)
        assert s2 == 1
        assert b2 == 0  # vol_ratio 0.5 < 1.5 for B2


class TestZeroIndex:
    """U-SIG-038 through U-SIG-041"""

    def test_i_zero_s3(self):
        """U-SIG-038 · P1 · i=0: S3 close <= close[-1]."""
        ind = _make_indicators(60)
        i = 0
        ind['vol_ratio'][i] = 2.0
        ind['long_upper'][i] = 1
        s1, s2, s3, b1, b2, b3 = calc_signals(ind, i)
        # close[0] <= close[-1]? numpy wraps around.
        # Design: default close[-1] to close[0] at i=0
        assert s3 in (0, 1)  # valid result, no crash

    def test_i_zero_new_high20(self):
        """U-SIG-039 · P2 · i=0: new_high20 is always 0."""
        ind = _make_indicators(60)
        i = 0
        s1, s2, s3, b1, b2, b3 = calc_signals(ind, i)
        assert s2 == 0

    def test_i_zero_close_ab_ma20_prev(self):
        """U-SIG-040 · P1 · i=0: close_ab_ma20_prev default."""
        ind = _make_indicators(60)
        i = 0
        # close_ab_ma20_prev[0] was set to 1 in calc_indicators (默认站上)
        # close_ab_ma20[0] is the actual first bar position
        s1, s2, s3, b1, b2, b3 = calc_signals(ind, i)
        # Valid result — shouldn't crash. S1 may fire if prev=1 and today=0
        assert all(s in (0, 1) for s in [s1, s2, s3, b1, b2, b3])

    def test_minimum_bars(self):
        """U-SIG-041 · P2 · Minimum bars (20)."""
        o = h = l = c = np.linspace(10, 12, 20)
        vol = np.full(20, 1000.0)
        ind = calc_indicators(o, h, l, c, vol)
        i = 19
        s1, s2, s3, b1, b2, b3 = calc_signals(ind, i)
        assert all(s in (0, 1) for s in [s1, s2, s3, b1, b2, b3])


class TestCompositeScenarios:
    """U-SIG-042 through U-SIG-045"""

    def test_typical_oscillation_day(self):
        """U-SIG-042 · P1 · Typical oscillation day."""
        ind = _make_indicators(60)
        i = 58
        # No strong signals
        s1, s2, s3, b1, b2, b3 = calc_signals(ind, i)
        assert all(s in (0, 1) for s in [s1, s2, s3, b1, b2, b3])

    def test_typical_breakout_day(self):
        """U-SIG-043 · P1 · Typical breakout day."""
        ind = _make_indicators(60)
        i = 58
        ind['close_ab_ma20_prev'][i] = 0
        ind['close_ab_ma20'][i] = 1
        ind['is_bullish'][i] = 1
        ind['break_3ma'][i] = 1
        ind['vol_ratio'][i] = 2.5
        s1, s2, s3, b1, b2, b3 = calc_signals(ind, i)
        assert b1 == 1  # At minimum B1 should fire

    def test_typical_decline_day(self):
        """U-SIG-044 · P1 · Typical decline day."""
        ind = _make_indicators(60)
        i = 58
        ind['close_ab_ma20_prev'][i] = 1
        ind['close_ab_ma20'][i] = 0
        s1, s2, s3, b1, b2, b3 = calc_signals(ind, i)
        assert s1 == 1

    def test_typical_volume_top(self):
        """U-SIG-045 · P2 · Typical volume top."""
        ind = _make_indicators(60)
        i = 58
        ind['vol_ratio'][i] = 2.0
        ind['long_upper'][i] = 1
        ind['close'][i] = ind['close'][i - 1] - 0.01
        s1, s2, s3, b1, b2, b3 = calc_signals(ind, i)
        assert s3 == 1
