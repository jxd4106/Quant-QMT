# -*- coding: utf-8 -*-
"""Half-Position Rolling V7 Strategy for Guojin QMT.

Sections: Constants / Indicators / Position Calc / Time Filter /
          State Persistence / Risk Control / Logging / QMT Entry Points

Env: Guojin QMT built-in Python 3.6-3.12, xtquant + numpy
"""
import numpy as np
import datetime
import os
import json
import time

# QMT internal imports -- module-level, NOT in try/except.
# QMT runs strategy via exec() so the import MUST be at top level.
from xtquant import xtdata

# ============================================================
# 1. Constants & Config
# ============================================================

SHADOW_RATIO = 2.0
SHADOW_PCT = 0.40
VOL_RATIO_LOW = 0.7
VOL_RATIO_MID = 1.5
VOL_RATIO_HIGH = 2.0
TARGET_PCT = 1.0
B2_RATIO = 1.0 / 3
STOP_LOSS_PCT = 0.15
MAX_TRADES_PER_DAY = 50

# Base data directory (F8). QMT runs strategy via exec, no __file__.
# Change this to match your QMT setup.
BASE_DIR = r'C:\qmt_data'

# Stock pool (F1): A-shares .SH/.SZ, HK Connect .HGT/.SGT
STOCK_POOL = {
    '603501.SH': {'name': 'Will-SH', 'weight': 1.0},
}

# Trading account ID (F19) -- required for passorder / get_trade_detail_data
ACCOUNT_ID = '8890326857'

# ============================================================
# 2. Technical Indicators
# ============================================================

def _rolling_mean(arr, window):
    n = len(arr)
    out = np.full(n, np.nan, dtype=float)
    if n < window:
        return out
    for i in range(window - 1, n):
        out[i] = np.mean(arr[i - window + 1:i + 1])
    return out


def calc_indicators(open_arr, high_arr, low_arr, close_arr, vol_arr):
    n = len(close_arr)
    ma5 = _rolling_mean(close_arr, 5)
    ma10 = _rolling_mean(close_arr, 10)
    ma20 = _rolling_mean(close_arr, 20)
    vol_ma5 = _rolling_mean(vol_arr, 5)
    safe_vol_ma5 = np.where((vol_ma5 > 0) & ~np.isnan(vol_ma5), vol_ma5, 1.0)
    vol_ratio = vol_arr / safe_vol_ma5
    body_abs = np.abs(close_arr - open_arr)
    range_ = high_arr - low_arr
    upper_shadow = high_arr - np.maximum(open_arr, close_arr)
    lower_shadow = np.minimum(open_arr, close_arr) - low_arr
    is_bullish = (close_arr > open_arr).astype(int)
    safe_body = np.where(body_abs > 0, body_abs, 0.001)
    safe_range = np.where(range_ > 0, range_, 0.001)
    long_upper = ((upper_shadow > safe_body * SHADOW_RATIO) &
                  (upper_shadow > safe_range * SHADOW_PCT)).astype(int)
    long_lower = ((lower_shadow > safe_body * SHADOW_RATIO) &
                  (lower_shadow > safe_range * SHADOW_PCT)).astype(int)
    ma_bull = np.zeros(n, dtype=int)
    valid = ~np.isnan(ma5) & ~np.isnan(ma10) & ~np.isnan(ma20)
    ma_bull[valid] = ((ma5[valid] > ma10[valid]) &
                      (ma10[valid] > ma20[valid])).astype(int)
    new_high20 = np.zeros(n, dtype=int)
    for i in range(20, n):
        if high_arr[i] > np.max(high_arr[i - 20:i]):
            new_high20[i] = 1
    break_3ma = np.zeros(n, dtype=int)
    for i in range(n):
        if (is_bullish[i] == 1 and
            not np.isnan(ma5[i]) and not np.isnan(ma10[i]) and not np.isnan(ma20[i]) and
            close_arr[i] > ma5[i] and close_arr[i] > ma10[i] and close_arr[i] > ma20[i] and
            vol_ratio[i] >= VOL_RATIO_HIGH):
            break_3ma[i] = 1
    close_ab_ma20 = np.zeros(n, dtype=int)
    for i in range(n):
        if not np.isnan(ma20[i]) and close_arr[i] > ma20[i]:
            close_ab_ma20[i] = 1
    close_ab_ma20_prev = np.zeros(n, dtype=int)
    close_ab_ma20_prev[0] = 1
    for i in range(1, n):
        close_ab_ma20_prev[i] = close_ab_ma20[i - 1]
    return {
        'ma5': ma5, 'ma10': ma10, 'ma20': ma20,
        'vol_ma5': vol_ma5, 'vol_ratio': vol_ratio,
        'body_abs': body_abs, 'range_': range_,
        'upper_shadow': upper_shadow, 'lower_shadow': lower_shadow,
        'is_bullish': is_bullish, 'long_upper': long_upper, 'long_lower': long_lower,
        'ma_bull': ma_bull, 'new_high20': new_high20,
        'break_3ma': break_3ma,
        'close_ab_ma20': close_ab_ma20, 'close_ab_ma20_prev': close_ab_ma20_prev,
        'close': close_arr,
    }


def calc_signals(ind, i):
    sig_S1 = 1 if (ind['close_ab_ma20'][i] == 0 and
                   ind['close_ab_ma20_prev'][i] == 1) else 0
    sig_S2 = 1 if (ind['new_high20'][i] == 1 and
                   ind['vol_ratio'][i] <= VOL_RATIO_LOW) else 0
    close_prev = ind['close'][i - 1] if i > 0 else ind['close'][i]
    sig_S3 = 1 if (ind['vol_ratio'][i] >= VOL_RATIO_MID and
                   ind['long_upper'][i] == 1 and
                   ind['close'][i] <= close_prev) else 0
    sig_B1 = 1 if (ind['close_ab_ma20'][i] == 1 and
                   ind['close_ab_ma20_prev'][i] == 0) else 0
    sig_B2 = 1 if (ind['long_lower'][i] == 1 and
                   ind['vol_ratio'][i] >= VOL_RATIO_MID) else 0
    sig_B3 = 1 if (ind['is_bullish'][i] == 1 and
                   ind['break_3ma'][i] == 1 and
                   ind['vol_ratio'][i] >= VOL_RATIO_HIGH) else 0
    return sig_S1, sig_S2, sig_S3, sig_B1, sig_B2, sig_B3


# ============================================================
# 3. Position Sizing
# ============================================================

def calc_initial_buy_qty(total_asset, weight, price, lot_size):
    """Initial entry: full position = total_asset * weight / price."""
    if price <= 0:
        return 0
    return align_lot_size(int(total_asset * weight / price), lot_size)


def calc_repurchase_qty(last_sell_qty, lot_size):
    """Repurchase: buy back remaining last_sell_qty."""
    return align_lot_size(last_sell_qty, lot_size)


def calc_b2_repurchase_qty(last_sell_qty, lot_size):
    """B2 repurchase: buy back 1/3 of last_sell_qty."""
    return align_lot_size(int(last_sell_qty * B2_RATIO), lot_size)


def align_lot_size(qty, lot_size):
    if lot_size <= 0:
        return 0
    return (qty // lot_size) * lot_size


def calc_sell_qty(cur_position, lot_size):
    if cur_position <= 0:
        return 0
    return align_lot_size(cur_position // 2, lot_size)


def calc_max_by_cash(cash, price, lot_size, buy_fee_rate=0.0003, hk_fixed_fee=0.0):
    if price <= 0 or cash <= 0:
        return 0
    cost_rate = 1.0 + buy_fee_rate
    cash_after_fee = cash / cost_rate - hk_fixed_fee
    if cash_after_fee <= 0:
        return 0
    return int(cash_after_fee / price / lot_size) * lot_size


def limit_price_sell(current_price):
    return round(current_price * 0.998, 2)


def limit_price_buy(current_price):
    return round(current_price * 1.002, 2)


# ============================================================
# 4. Trading Hours Filter (F7)
# ============================================================

def is_hk_stock(stock_code):
    return stock_code.endswith('.HGT') or stock_code.endswith('.SGT')


def is_in_trading_hours(stock_code, now_time):
    if is_hk_stock(stock_code):
        return ('09:30' <= now_time <= '12:00') or ('13:00' <= now_time <= '16:00')
    else:
        return ('09:30' <= now_time <= '11:30') or ('13:00' <= now_time <= '15:00')


def get_signal_time(now_time, stock_code):
    try:
        hh, mm = now_time.split(':')
        t = int(hh) * 60 + int(mm)
    except Exception:
        return None
    if is_hk_stock(stock_code):
        if 715 <= t <= 720:
            return '11:55'
        if 955 <= t <= 960:
            return '15:55'
        return None
    else:
        if t == 895:
            return '14:55'
        return None


# ============================================================
# 5. State Persistence (F8 / F16 / F18)
# ============================================================

def state_file_path():
    return os.path.join(BASE_DIR, 'state.json')


def override_file_path():
    return os.path.join(BASE_DIR, 'override.json')


def _default_state(today):
    return {
        'date': today,
        'stocks': {code: {'stop_loss_triggered': False, 'trade_count_today': 0,
                           'sold_today': False, 'stop_loss_base': None,
                           'last_sell_qty': 0, 'last_b2_price': None,
                           'last_b2_qty': 0, 'b2_used': False}
                   for code in STOCK_POOL},
        'daily_stop_count': 0,
    }


def read_state():
    path = state_file_path()
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, Exception):
        return None


def write_state(state):
    path = state_file_path()
    tmp = path + '.tmp'
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print('[STATE] write_state error: %s' % str(e))


def ensure_state():
    state = read_state()
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    if state is None:
        state = _default_state(today)
    for code in STOCK_POOL:
        if code not in state.get('stocks', {}):
            state.setdefault('stocks', {})[code] = {
                'stop_loss_triggered': False, 'trade_count_today': 0,
                'sold_today': False, 'stop_loss_base': None,
            }
        s = state['stocks'].setdefault(code, {})
        s.setdefault('last_sell_qty', 0)
        s.setdefault('last_b2_price', None)
        s.setdefault('last_b2_qty', 0)
        s.setdefault('b2_used', False)
    state.setdefault('daily_stop_count', 0)
    write_state(state)
    return state


def reset_daily_state(state, today):
    if state.get('date') != today:
        state['date'] = today
        state['daily_stop_count'] = 0
        for code in STOCK_POOL:
            s = state['stocks'].get(code, {})
            s['trade_count_today'] = 0
            s['sold_today'] = False
        return True
    return False


def process_override():
    path = override_file_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            codes = json.load(f)
        if not isinstance(codes, list):
            print('[OVERRIDE] override.json format error (not a list), skipped')
            return []
    except (json.JSONDecodeError, Exception) as e:
        print('[OVERRIDE] override.json parse error: %s' % str(e))
        return []
    state = ensure_state()
    reset_list = []
    for code in codes:
        if code in state.get('stocks', {}):
            state['stocks'][code]['stop_loss_triggered'] = False
            reset_list.append(code)
            print('[OVERRIDE] %s stop-loss reset' % code)
    if reset_list:
        write_state(state)
    try:
        os.remove(path)
    except OSError:
        pass
    return reset_list


def check_stop_loss(profit_rate):
    return profit_rate is not None and profit_rate <= -STOP_LOSS_PCT


# ============================================================
# 6. Simple logger (F10) -- uses print to file, no logging module
#    QMT built-in Python may lack the logging module.
# ============================================================

_LOG_FILE = None


def _log_print(level, msg, *args):
    """Print timestamped log to file + console. Replaces logging module."""
    global _LOG_FILE
    ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = '%s | %-7s | %s' % (ts, level, msg % args if args else msg)
    print(line)
    if _LOG_FILE is not None:
        try:
            with open(_LOG_FILE, 'a', encoding='utf-8') as f:
                f.write(line + '\n')
        except Exception:
            pass


def _setup_log():
    """Initialize log file for today. Call once in init()."""
    global _LOG_FILE
    log_dir = os.path.join(BASE_DIR, 'logs')
    try:
        os.makedirs(log_dir, exist_ok=True)
    except Exception:
        pass
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    _LOG_FILE = os.path.join(log_dir, 'V7_%s.log' % today)
    _clean_old_logs(log_dir, 30)


def _clean_old_logs(log_dir, keep_days):
    try:
        cutoff = time.time() - keep_days * 86400
        for fname in os.listdir(log_dir):
            if fname.startswith('V7_') and fname.endswith('.log'):
                fpath = os.path.join(log_dir, fname)
                if os.path.getmtime(fpath) < cutoff:
                    os.remove(fpath)
    except Exception:
        pass


# ============================================================
# 7. QMT Framework Entry Points
# ============================================================

class G:
    trade_count_today = {}
    sold_today = {}
    stop_loss_triggered = {}
    last_signal_time = ''
    last_scan_time = ''
    daily_stop_count = 0
    last_date = ''
    last_heartbeat = ''
    last_sell_qty = {}
    last_b2_price = {}
    last_b2_qty = {}
    b2_used = {}


g = G()
_ctx = None
_pool_codes = []
_HISTORY_CACHE = {}
_BEST_API = 'none'


def _heartbeat(now_time):
    """Print a heartbeat every 10 min so user knows the strategy is alive."""
    if g.last_heartbeat == '':
        g.last_heartbeat = '00:00'
    h, m = g.last_heartbeat.split(':')
    last_min = int(h) * 60 + int(m)
    h2, m2 = now_time.split(':')
    now_min = int(h2) * 60 + int(m2)
    # Reset across midnight boundary (e.g. 14:55 => next day 09:30)
    if now_min < last_min:
        g.last_heartbeat = '00:00'
        last_min = 0
    if now_min - last_min >= 10:
        g.last_heartbeat = now_time
        _log_print('INFO', '[HEARTBEAT] strategy running at %s', now_time)
        return True
    return False


def _diagnostic_scan(now_time):
    """Every 10 min (with heartbeat) scan all stocks & log signal status -- no trading.
    Does NOT filter by trading hours so it works even after market close."""
    for stock_code in _pool_codes:
        bar = _get_latest_bar(stock_code)
        if bar is None:
            _log_print('WARN', '[SCAN] %s skip: no bar data', stock_code)
            continue
        current_price = bar['close']
        hist = _get_history_bars(stock_code)
        if hist is None or len(hist['close']) < 60:
            _log_print('WARN', '[SCAN] %s skip: history=%s', stock_code,
                       'None' if hist is None else '%d bars' % len(hist['close']))
            continue

        close_arr = hist['close'].copy()
        open_arr = hist['open'].copy()
        high_arr = hist['high'].copy()
        low_arr = hist['low'].copy()
        vol_arr = hist['volume'].copy()
        # Replace last bar with live tick since it's today's partial bar
        close_arr[-1] = bar['close']
        open_arr[-1] = bar['open']
        high_arr[-1] = max(bar['high'], high_arr[-1])
        low_arr[-1] = min(bar['low'], low_arr[-1])
        vol_arr[-1] = vol_arr[-1] + bar['volume']
        ind = calc_indicators(open_arr, high_arr, low_arr, close_arr, vol_arr)
        i = len(close_arr) - 1
        s1, s2, s3, b1, b2, b3 = calc_signals(ind, i)

        sig_names = []
        if s1: sig_names.append('S1')
        if s2: sig_names.append('S2')
        if s3: sig_names.append('S3')
        if b1: sig_names.append('B1')
        if b2: sig_names.append('B2')
        if b3: sig_names.append('B3')
        sig_str = ','.join(sig_names) if sig_names else 'NONE'

        cfg = STOCK_POOL.get(stock_code, {})
        name = cfg.get('name', stock_code)
        above_ma20 = 'ABOVE' if ind['close_ab_ma20'][i] else 'BELOW'
        # Show last 5 history closes + current bar to debug MA20
        hist_tail = [round(x, 2) for x in close_arr[max(0, i-4):i].tolist()]
        _log_print('INFO', '[SCAN] %s(%s) price=%.2f ma20=%.2f %s signals=%s last_sell=%d b2=%s hist_tail=%s',
                   name, stock_code, current_price,
                   ind['ma20'][i] if not np.isnan(ind['ma20'][i]) else 0,
                   above_ma20, sig_str,
                   g.last_sell_qty.get(stock_code, 0),
                   'Y' if g.b2_used.get(stock_code) else 'N',
                   hist_tail)


def init(ContextInfo):
    global _ctx, _pool_codes
    _ctx = ContextInfo
    _setup_log()
    _pool_codes = list(STOCK_POOL.keys())

    _log_print('INFO', '=' * 60)
    _log_print('INFO', 'V7 Half-Position Rolling Strategy - Init')
    _log_print('INFO', 'Stocks: %d | Target: %.0f%% | Stop-loss: %.0f%%',
              len(STOCK_POOL), TARGET_PCT * 100, STOP_LOSS_PCT * 100)
    _log_print('INFO', '=' * 60)

    # === DIAGNOSTIC: dump ContextInfo API surface to find the right data method ===
    _log_print('INFO', '[DIAG] ContextInfo type: %s', type(ContextInfo).__name__)
    ctx_methods = sorted([attr for attr in dir(ContextInfo) if not attr.startswith('__')])
    _log_print('INFO', '[DIAG] ContextInfo attrs: %s', ','.join(ctx_methods))
    # Try every plausible data method and log what they return
    for method_name in ['get_market_data', 'get_market_data_ex', 'get_history_data',
                         'get_local_data', 'download_history_data']:
        if hasattr(ContextInfo, method_name):
            _log_print('INFO', '[DIAG] has method: %s', method_name)

    # === Download + Probe: use ContextInfo.get_market_data_ex (official recommended API) ===
    # Docs: ContextInfo.get_market_data_ex(
    #   fields=[], stock_code=[], period='1d', start_time='', end_time='',
    #   count=-1, dividend_type='front', fill_data=True, subscribe=True/False)
    global _BEST_API
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    _BEST_API = 'none'

    # QMT auto-maintains local cache via market data subscription.
    # get_market_data_ex(subscribe=False) reads it directly -- no manual download needed.

    # Step 2: probe all available APIs
    def _try_get_market_data_ex(stock):
        """ContextInfo.get_market_data_ex -- subscribe=False reads local cache only."""
        raw = ContextInfo.get_market_data_ex(
            fields=['close'], stock_code=[stock],
            period='1d', count=60, dividend_type='front',
            subscribe=False, fill_data=True)
        return _vals_from_raw(raw, stock)

    def _try_get_market_data_ex_sub(stock):
        """ContextInfo.get_market_data_ex -- subscribe=True fetches live + local."""
        raw = ContextInfo.get_market_data_ex(
            fields=['close'], stock_code=[stock],
            period='1d', count=60, dividend_type='front',
            subscribe=True, fill_data=True)
        return _vals_from_raw(raw, stock)

    def _try_get_market_data(stock):
        """ContextInfo.get_market_data -- legacy, positional args only."""
        raw = ContextInfo.get_market_data(['close'], [stock], '1d', 'none')
        return _vals_from_raw(raw, stock)

    def _try_xtdata_local(stock):
        """xtdata.get_local_data -- offline, reads downloaded cache."""
        raw = xtdata.get_local_data(
            field_list=[], stock_list=[stock],
            period='1d', start_time='', count=60,
            dividend_type='front', fill_data=True)
        return _vals_from_raw(raw, stock)

    def _try_xtdata_ex(stock):
        """xtdata.get_market_data_ex -- requires miniQMT running."""
        raw = xtdata.get_market_data_ex(
            field_list=[], stock_list=[stock],
            period='1d', start_time='', count=60,
            dividend_type='front', fill_data=True)
        return _vals_from_raw(raw, stock)

    def _vals_from_raw(raw, stock):
        if raw is None:
            return []
        if isinstance(raw, dict):
            df = raw.get(stock)
            if df is not None and hasattr(df, 'values'):
                vals = list(df['close'].values) if 'close' in df.columns else []
                return vals if vals else []
            return []
        if hasattr(raw, 'values'):
            return list(raw.values) if raw.values else []
        return []

    probes = [
        ('get_market_data_ex', _try_get_market_data_ex, 'ctx get_market_data_ex(subscribe=False)'),
        ('get_market_data_ex_sub', _try_get_market_data_ex_sub, 'ctx get_market_data_ex(subscribe=True)'),
        ('get_market_data', _try_get_market_data, 'ctx get_market_data'),
        ('xtdata_local', _try_xtdata_local, 'xtdata get_local_data'),
        ('xtdata_ex', _try_xtdata_ex, 'xtdata get_market_data_ex'),
    ]

    for stock_code in _pool_codes:
        for name, fn, label in probes:
            try:
                vals = fn(stock_code)
                actual_count = len(vals)
                first_val = vals[0] if actual_count > 0 else 0
                last_val = vals[-1] if actual_count > 0 else 0
                _log_print('INFO', '[PROBE] %s via %s => %d bars, %.2f~%.2f',
                           stock_code, label, actual_count, first_val, last_val)
                if actual_count >= 60 and first_val > 50:
                    _BEST_API = name
                    _log_print('INFO', '[PROBE] Selected: %s', label)
                    break
            except Exception as e:
                _log_print('WARN', '[PROBE] %s via %s: %s', stock_code, label, str(e))
        if _BEST_API != 'none':
            break

    if _BEST_API == 'none':
        _log_print('ERROR', '[PROBE] ALL APIs returned empty! QMT environment issue:')
        _log_print('ERROR', '[PROBE]   1) Make sure miniQMT is running')
        _log_print('ERROR', '[PROBE]   2) Make sure 603501.SH data is included in your QMT data package')
        _log_print('ERROR', '[PROBE]   3) In QMT GUI, right-click stock -> download history data for 1d')
        _BEST_API = 'get_market_data_ex'  # fallback to the recommended API

    state = ensure_state()
    reset_daily_state(state, today)

    _sync_g_from_state(state, today)
    _log_print('INFO', '[INIT] Ready.\n')


def handlebar(ContextInfo):
    global _ctx
    _ctx = ContextInfo
    now = datetime.datetime.now()
    today = now.strftime('%Y-%m-%d')
    now_time = now.strftime('%H:%M')

    # Cross-day reset
    if today != g.last_date:
        state = ensure_state()
        reset_daily_state(state, today)
        _sync_g_from_state(state, today)
        g.last_date = today
        g.daily_stop_count = 0
        _log_print('INFO', '[DAY] New day: %s', today)

    # Heartbeat + diagnostic scan every 10 minutes
    # At 14:55 signal time, also log diagnostic ONCE to capture the final trade decision
    fired = _heartbeat(now_time)
    sig_time = None
    for stock_code in _pool_codes:
        if is_in_trading_hours(stock_code, now_time):
            sig_time = get_signal_time(now_time, stock_code)
            if sig_time:
                break
    if fired:
        _diagnostic_scan(now_time)
    elif sig_time:
        # Signal time but NOT heartbeat time: scan once per signal minute
        sig_key = '%s:%s' % (today, sig_time)
        if g.last_scan_time != sig_key:
            g.last_scan_time = sig_key
            _diagnostic_scan(now_time)

    sig_ran_today = False
    for stock_code in _pool_codes:
        if not is_in_trading_hours(stock_code, now_time):
            continue
        sig_time = get_signal_time(now_time, stock_code)
        if sig_time is None:
            continue
        sig_ran_today = True
        time_key = '%s:%s:%s' % (today, stock_code, sig_time)
        if g.last_signal_time == time_key:
            continue
        g.last_signal_time = time_key

        if g.stop_loss_triggered.get(stock_code):
            continue

        bar = _get_latest_bar(stock_code)
        if bar is None:
            continue

        _process_signal(stock_code, bar, today)

    # End-of-day state write (after 15:00)
    if now_time >= '15:00':
        state = ensure_state()
        write_state(state)


def _sync_g_from_state(state, today):
    for code in STOCK_POOL:
        s = state.get('stocks', {}).get(code, {})
        g.trade_count_today[code] = s.get('trade_count_today', 0)
        g.sold_today[code] = s.get('sold_today', False)
        g.stop_loss_triggered[code] = s.get('stop_loss_triggered', False)
        g.last_sell_qty[code] = s.get('last_sell_qty', 0)
        g.last_b2_price[code] = s.get('last_b2_price', None)
        g.last_b2_qty[code] = s.get('last_b2_qty', 0)
        g.b2_used[code] = s.get('b2_used', False)
    g.daily_stop_count = state.get('daily_stop_count', 0)
    g.last_date = today


def _get_latest_bar(stock_code):
    try:
        ticks = _ctx.get_full_tick([stock_code])
        if not ticks or stock_code not in ticks:
            return None
        t = ticks[stock_code]
        bar = {'open': t.get('open', 0), 'high': t.get('high', 0),
               'low': t.get('low', 0), 'close': t.get('lastPrice', 0),
               'volume': t.get('volume', 0)}
        if bar['close'] <= 0:
            return None
        return bar
    except Exception as e:
        _log_print('WARN', '[WARN] _get_latest_bar %s: %s', stock_code, str(e))
        return None


def _process_signal(stock_code, bar, today):
    current_price = bar['close']

    hist = _get_history_bars(stock_code)
    if hist is None or len(hist['close']) < 60:
        _log_print('WARN', '[WARN] %s: insufficient history, skip', stock_code)
        return

    close_arr = np.append(hist['close'], bar['close'])
    open_arr = np.append(hist['open'], bar['open'])
    high_arr = np.append(hist['high'], bar['high'])
    low_arr = np.append(hist['low'], bar['low'])
    vol_arr = np.append(hist['volume'], bar['volume'])

    ind = calc_indicators(open_arr, high_arr, low_arr, close_arr, vol_arr)
    i = len(close_arr) - 1
    sig_S1, sig_S2, sig_S3, sig_B1, sig_B2, sig_B3 = calc_signals(ind, i)

    # DIAGNOSTIC: log signals FIRST, before any early-return
    sig_list = []
    if sig_S1: sig_list.append('S1')
    if sig_S2: sig_list.append('S2')
    if sig_S3: sig_list.append('S3')
    if sig_B1: sig_list.append('B1')
    if sig_B2: sig_list.append('B2')
    if sig_B3: sig_list.append('B3')
    sig_str = ','.join(sig_list) if sig_list else 'NONE'

    try:
        # Use get_trade_detail_data -- the official QMT strategy API for account/position queries
        accounts = get_trade_detail_data(ACCOUNT_ID, 'STOCK', 'ACCOUNT')
        total_asset = 0.0
        available_cash = 0.0
        if accounts:
            acc = accounts[0]
            total_asset = float(getattr(acc, 'm_dAsset', 0) or 0)
            available_cash = float(getattr(acc, 'm_dAvailable', 0) or 0)
    except Exception as e:
        _log_print('WARN', '[ACCT] get_trade_detail_data(ACCOUNT) error: %s', str(e))
        total_asset = 0.0
        available_cash = 0.0

    try:
        positions = get_trade_detail_data(ACCOUNT_ID, 'STOCK', 'POSITION')
        cur_pos = 0
        profit_rate = 0.0
        if positions:
            for p in positions:
                if getattr(p, 'm_strInstrumentID', '') == stock_code:
                    cur_pos = int(getattr(p, 'm_nVolume', 0) or 0)
                    profit_rate = float(getattr(p, 'm_dProfitRate', 0) or 0)
                    break
    except Exception as e:
        _log_print('WARN', '[POS] get_trade_detail_data(POSITION) error: %s', str(e))

    _log_print('INFO', '[SIG] %s signals=%s pos=%d price=%.2f last_sell=%d b2_used=%s',
               stock_code, sig_str, cur_pos, current_price,
               g.last_sell_qty.get(stock_code, 0),
               'Y' if g.b2_used.get(stock_code) else 'N')

    cfg = STOCK_POOL.get(stock_code, {})
    weight = cfg.get('weight', 0.0)
    lot_size = 100
    try:
        detail = xtdata.get_instrument_detail(stock_code)
        if detail and 'VolumeMultiple' in detail:
            lot_size = int(detail['VolumeMultiple'])
    except Exception:
        pass

    # Stop-loss check (F6)
    if check_stop_loss(profit_rate) and cur_pos > 0:
        g.stop_loss_triggered[stock_code] = True
        g.daily_stop_count += 1
        state = ensure_state()
        state['stocks'][stock_code]['stop_loss_triggered'] = True
        state['daily_stop_count'] = g.daily_stop_count
        state['stocks'][stock_code]['stop_loss_base'] = current_price
        write_state(state)
        _log_print('WARN', '[STOP] %s stop-loss hit profit_rate=%.2f%%', stock_code, profit_rate * 100)
        return

    if g.trade_count_today.get(stock_code, 0) >= MAX_TRADES_PER_DAY:
        _log_print('WARN', '[LIMIT] %s daily trade limit reached', stock_code)
        return

    # === B2 stop-loss: if price drops >= 3% from B2 entry, sell the B2 portion ===
    if g.b2_used.get(stock_code) and g.last_b2_price.get(stock_code) is not None:
        b2_entry = g.last_b2_price[stock_code]
        if current_price <= b2_entry * 0.97 and cur_pos > 0:
            b2_bought = g.last_b2_qty.get(stock_code, 0)
            sell_b2_qty = min(b2_bought, cur_pos)
            if sell_b2_qty > 0:
                lp = limit_price_sell(current_price)
                order_id = _do_order(stock_code, 24, sell_b2_qty, lp)
                if order_id:
                    g.trade_count_today[stock_code] = (g.trade_count_today.get(stock_code, 0) + 1)
                    # Undo B2: restore last_sell_qty by adding back the B2 portion
                    g.last_sell_qty[stock_code] = g.last_sell_qty.get(stock_code, 0) + sell_b2_qty
                    g.b2_used[stock_code] = False
                    g.last_b2_price[stock_code] = None
                    g.last_b2_qty[stock_code] = 0
                    _log_print('WARN', '[B2-STOP] %s B2 stop-loss %.2f => %.2f (-%.1f%%) sell=%d restored_sell=%d',
                               stock_code, b2_entry, current_price,
                               (1 - current_price / b2_entry) * 100, sell_b2_qty,
                               g.last_sell_qty.get(stock_code, 0))
                    state = ensure_state()
                    state['stocks'][stock_code]['last_sell_qty'] = g.last_sell_qty[stock_code]
                    state['stocks'][stock_code]['b2_used'] = False
                    state['stocks'][stock_code]['last_b2_price'] = None
                    state['stocks'][stock_code]['last_b2_qty'] = 0
                    write_state(state)
            return  # Skip buys after B2 stop-loss

    # === Sell priority (F9): S1 > S2 > S3 ===
    if cur_pos > 0 and not g.sold_today.get(stock_code, False):
        action = None
        if sig_S1:
            action = 'S1'
        elif sig_S2:
            action = 'S2'
        elif sig_S3:
            action = 'S3'
        if action:
            sell_qty = calc_sell_qty(cur_pos, lot_size)
            if sell_qty > 0:
                lp = limit_price_sell(current_price)
                order_id = _do_order(stock_code, 24, sell_qty, lp)
                if order_id:
                    g.trade_count_today[stock_code] = (g.trade_count_today.get(stock_code, 0) + 1)
                    g.sold_today[stock_code] = True
                    # Start new repurchase cycle
                    g.last_sell_qty[stock_code] = sell_qty
                    g.b2_used[stock_code] = False
                    g.last_b2_price[stock_code] = None
                    g.last_b2_qty[stock_code] = 0
                    _log_print('INFO', '[SELL] %s %s: %d @ %.2f last_sell=%d',
                               action, stock_code, sell_qty, lp, sell_qty)
                    # Persist state
                    state = ensure_state()
                    state['stocks'][stock_code]['last_sell_qty'] = sell_qty
                    state['stocks'][stock_code]['b2_used'] = False
                    state['stocks'][stock_code]['last_b2_price'] = None
                    state['stocks'][stock_code]['last_b2_qty'] = 0
                    write_state(state)
            return  # No buy on same day after sell

    # === Buy: B1 > B2 > B3 ===
    buy_action = None
    if sig_B1:
        buy_action = 'B1'
    elif sig_B2:
        buy_action = 'B2'
    elif sig_B3:
        buy_action = 'B3'

    if buy_action:
        last_sell = g.last_sell_qty.get(stock_code, 0)

        if cur_pos == 0:
            # Initial entry: full position
            raw_qty = calc_initial_buy_qty(total_asset, weight, current_price, lot_size)
        elif last_sell > 0:
            # Repurchase: buy back remaining last_sell_qty
            if buy_action == 'B2':
                if g.b2_used.get(stock_code):
                    _log_print('INFO', '[B2-SKIP] %s B2 already used this cycle', stock_code)
                    return
                raw_qty = calc_b2_repurchase_qty(last_sell, lot_size)
            else:
                raw_qty = calc_repurchase_qty(last_sell, lot_size)
        else:
            # Already full position, nothing to buy
            _log_print('INFO', '[BUY-SKIP] %s already full, last_sell=0', stock_code)
            return

        # Cash constraint
        max_cash_qty = calc_max_by_cash(available_cash, current_price, lot_size)
        buy_qty = min(raw_qty, max_cash_qty)

        if buy_qty > 0:
            lp = limit_price_buy(current_price)
            order_id = _do_order(stock_code, 23, buy_qty, lp)
            if order_id:
                g.trade_count_today[stock_code] = (g.trade_count_today.get(stock_code, 0) + 1)
                # Update repurchase state
                if cur_pos > 0:
                    remaining = last_sell - buy_qty
                    g.last_sell_qty[stock_code] = max(remaining, 0)
                    if buy_action == 'B2':
                        g.b2_used[stock_code] = True
                        g.last_b2_price[stock_code] = current_price
                        g.last_b2_qty[stock_code] = buy_qty
                    if g.last_sell_qty.get(stock_code, 0) <= 0:
                        # Fully repurchased, reset cycle
                        g.last_sell_qty[stock_code] = 0
                        g.b2_used[stock_code] = False
                        g.last_b2_price[stock_code] = None
                        g.last_b2_qty[stock_code] = 0
                _log_print('INFO', '[BUY] %s %s: %d @ %.2f remaining_sell=%d',
                           buy_action, stock_code, buy_qty, lp,
                           g.last_sell_qty.get(stock_code, 0))
                # Persist state
                state = ensure_state()
                state['stocks'][stock_code]['last_sell_qty'] = g.last_sell_qty.get(stock_code, 0)
                state['stocks'][stock_code]['b2_used'] = g.b2_used.get(stock_code, False)
                state['stocks'][stock_code]['last_b2_price'] = g.last_b2_price.get(stock_code, None)
                state['stocks'][stock_code]['last_b2_qty'] = g.last_b2_qty.get(stock_code, 0)
                write_state(state)
        else:
            _log_print('INFO', '[BUY-SKIP] %s raw=%d cash_max=%d cash=%.0f price=%.2f',
                       stock_code, raw_qty, max_cash_qty, available_cash, current_price)


def _build_history_return(result):
    return {'open': np.array(result['open']), 'high': np.array(result['high']),
            'low': np.array(result['low']), 'close': np.array(result['close']),
            'volume': np.array(result['volume'])}


def _get_history_bars(stock_code, count=60):
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    cache_key = '%s:%s' % (stock_code, today)
    if cache_key in _HISTORY_CACHE:
        result = _HISTORY_CACHE[cache_key]
        return _build_history_return(result)
    try:
        # Use the API mode detected at init
        api = _BEST_API
        fields = ['open', 'high', 'low', 'close', 'volume']

        if api in ('get_market_data_ex', 'get_market_data_ex_sub'):
            raw_data = _ctx.get_market_data_ex(
                fields=fields, stock_code=[stock_code],
                period='1d', count=count, dividend_type='front',
                subscribe=(api == 'get_market_data_ex_sub'),
                fill_data=True)
        elif api == 'get_market_data':
            raw_data = _ctx.get_market_data(fields, [stock_code], '1d', 'none')
        elif api == 'xtdata_local':
            raw_data = xtdata.get_local_data(
                field_list=[], stock_list=[stock_code],
                period='1d', start_time='', count=count,
                dividend_type='front', fill_data=True)
        elif api == 'xtdata_ex':
            raw_data = xtdata.get_market_data_ex(
                field_list=[], stock_list=[stock_code],
                period='1d', start_time='', count=count,
                dividend_type='front', fill_data=True)
        else:
            # fallback
            raw_data = _ctx.get_market_data_ex(
                fields=fields, stock_code=[stock_code],
                period='1d', count=count, dividend_type='front',
                subscribe=False, fill_data=True)

        # raw_data is {stock_code: DataFrame} from official API
        if isinstance(raw_data, dict) and stock_code in raw_data:
            df = raw_data[stock_code]
            result = {}
            for field in fields:
                if field in df.columns:
                    result[field] = list(df[field].values)
                else:
                    result[field] = []
        else:
            # fallback: old-style dict-of-series format
            result = {}
            for field in fields:
                series = raw_data.get(field)
                arr = list(series.values) if hasattr(series, 'values') else (list(series) if series else [])
                result[field] = arr
        closes = result['close']
        if len(closes) == 0:
            _log_print('WARN', '[DATA] %s returned empty history', stock_code)
            return None
        _log_print('INFO', '[DATA] %s loaded %d bars, close range: %.2f ~ %.2f',
                   stock_code, len(closes), closes[0], closes[-1])
        _HISTORY_CACHE[cache_key] = result
        return _build_history_return(result)
    except Exception as e:
        _log_print('ERROR', '[ERROR] get_market_data %s: %s', stock_code, str(e))
        return None


def _do_order(stock_code, op_type, qty, limit_price):
    """Use passorder -- the official QMT strategy order API.

    Signature: passorder(opType, orderType, accountid, orderCode, prType,
                         price, volume, strategyName, quickTrade, userOrderId, ContextInfo)
    opType: 23=buy, 24=sell
    orderType: 1101 = stock/count mode
    prType: 11 = limit; 5 = market (no price needed)
    """
    if qty <= 0:
        return None
    try:
        # quickTrade=2: immediate execution. Strategy already has trade-count guard.
        order_id = passorder(
            op_type,                          # 23 buy / 24 sell
            1101,                             # orderType: stock, count mode
            ACCOUNT_ID,                       # account ID
            stock_code,                       # orderCode: stock code
            11,                               # prType: limit order
            limit_price if limit_price else 0,  # limit price (0 = market)
            qty,                              # volume in shares
            '半仓滚动',                        # strategy name
            2,                                # quickTrade: 2 = immediate
            '',                               # userOrderId / remark
            _ctx,                             # ContextInfo
        )
        if order_id is None or order_id == '' or order_id == 0:
            _log_print('ERROR', '[ORDER] %s passorder failed, empty order_id', stock_code)
            return None
        return order_id
    except Exception as e:
        _log_print('ERROR', '[ORDER] %s passorder exception: %s', stock_code, str(e))
        return None
