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
TARGET_PCT = 0.5
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

def calc_target_value(total_asset, weight):
    return total_asset * weight * TARGET_PCT


def calc_ideal_buy_qty(target_value, price, cur_position, lot_size):
    if price <= 0:
        return 0
    target_shares = int(target_value / price)
    ideal = max(target_shares - cur_position, 0)
    return align_lot_size(ideal, lot_size)


def calc_b2_buy_qty(ideal_buy_qty, lot_size):
    return align_lot_size(int(ideal_buy_qty * B2_RATIO), lot_size)


def normalize_weights(stock_pool, target_pct=None):
    if target_pct is None:
        target_pct = TARGET_PCT
    total_target = sum(cfg['weight'] * target_pct for cfg in stock_pool.values())
    if total_target > 0:
        return min(1.0, 1.0 / total_target)
    return 1.0


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


def calc_order_qty(signal_type, target_value, price, cur_position, cash, lot_size,
                   buy_fee_rate=0.0003, hk_fixed_fee=0.0, scale=1.0):
    if price <= 0:
        return 0
    tv_scaled = target_value * scale
    ideal_buy = calc_ideal_buy_qty(tv_scaled, price, cur_position, lot_size)
    if signal_type.startswith('S'):
        return calc_sell_qty(cur_position, lot_size)
    elif signal_type == 'B2':
        buy_qty = calc_b2_buy_qty(ideal_buy, lot_size)
    else:
        buy_qty = ideal_buy
    max_cash = calc_max_by_cash(cash, price, lot_size, buy_fee_rate, hk_fixed_fee)
    return min(buy_qty, max_cash)


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
                           'sold_today': False, 'stop_loss_base': None}
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
    daily_stop_count = 0
    last_date = ''
    last_heartbeat = ''


g = G()
_ctx = None
_pool_codes = []
_HISTORY_CACHE = {}


def _heartbeat(now_time):
    """Print a heartbeat every 30 min so user knows the strategy is alive."""
    if g.last_heartbeat == '':
        g.last_heartbeat = '00:00'
    h, m = g.last_heartbeat.split(':')
    last_min = int(h) * 60 + int(m)
    h2, m2 = now_time.split(':')
    now_min = int(h2) * 60 + int(m2)
    # Reset across midnight boundary (e.g. 14:55 → next day 09:30)
    if now_min < last_min:
        g.last_heartbeat = '00:00'
        last_min = 0
    if now_min - last_min >= 30:
        g.last_heartbeat = now_time
        _log_print('INFO', '[HEARTBEAT] strategy running at %s', now_time)


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

    for stock_code, cfg in STOCK_POOL.items():
        for attempt in range(1, 4):
            try:
                xtdata.download_history_data(stock_code, period='1d')
                _log_print('INFO', '[INIT] %s data ready', cfg['name'])
                break
            except Exception as e:
                _log_print('WARN', '[INIT] %s attempt %d/3 failed: %s', stock_code, attempt, str(e))
                if attempt < 3:
                    time.sleep(2)
        else:
            _log_print('ERROR', '[INIT] %s download failed 3x, skipped', cfg['name'])

    state = ensure_state()
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    reset_daily_state(state, today)

    reset_codes = process_override()
    if reset_codes:
        _log_print('INFO', '[OVERRIDE] stop-loss reset: %s', ','.join(reset_codes))

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

    # Heartbeat: print once every 30 minutes so user knows strategy is alive
    _heartbeat(now_time)

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

    try:
        asset = xtrading.query_account_data()
        if asset is None:
            return 0.0, 0.0
        total_asset = float(getattr(asset, 'm_dAsset', 0.0) or 0.0)
        available_cash = float(getattr(asset, 'm_dAvailable', 0.0) or 0.0)
    except Exception:
        total_asset = 0.0
        available_cash = 0.0

    try:
        pos = xtrading.query_stock_position(stock_code)
        cur_pos = int(getattr(pos, 'm_dAvailable', 0) or 0)
        profit_rate = float(getattr(pos, 'profit_rate', 0) or 0)
    except Exception:
        cur_pos = 0
        profit_rate = 0.0

    # DIAGNOSTIC: log signals at decision time so user can see why no trade fires
    sig_list = []
    if sig_S1: sig_list.append('S1')
    if sig_S2: sig_list.append('S2')
    if sig_S3: sig_list.append('S3')
    if sig_B1: sig_list.append('B1')
    if sig_B2: sig_list.append('B2')
    if sig_B3: sig_list.append('B3')
    sig_str = ','.join(sig_list) if sig_list else 'NONE'
    _log_print('INFO', '[SIG] %s signals=%s pos=%d price=%.2f',
               stock_code, sig_str, cur_pos, current_price)

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
        state['stocks'][stock_code]['stop_loss_base'] = (
            float(getattr(pos, 'avg_price', 0) or 0))
        write_state(state)
        _log_print('WARN', '[STOP] %s stop-loss hit profit_rate=%.2f%%', stock_code, profit_rate * 100)
        return

    if g.trade_count_today.get(stock_code, 0) >= MAX_TRADES_PER_DAY:
        _log_print('WARN', '[LIMIT] %s daily trade limit reached', stock_code)
        return

    scale = normalize_weights(STOCK_POOL)
    target_value = calc_target_value(total_asset, weight)

    # Sell priority (F9): S1 > S2 > S3
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
                    _log_print('INFO', '[SELL] %s %s: %d @ %.2f', action, stock_code, sell_qty, lp)
            return  # No buy on same day after sell

    # Buy: B1 > B2 > B3
    buy_action = None
    if sig_B1:
        buy_action = 'B1'
    elif sig_B2:
        buy_action = 'B2'
    elif sig_B3:
        buy_action = 'B3'

    if buy_action:
        buy_qty = calc_order_qty(buy_action, target_value, current_price,
                                 cur_pos, available_cash, lot_size, scale=scale)
        if buy_qty > 0:
            lp = limit_price_buy(current_price)
            order_id = _do_order(stock_code, 23, buy_qty, lp)
            if order_id:
                g.trade_count_today[stock_code] = (g.trade_count_today.get(stock_code, 0) + 1)
                _log_print('INFO', '[BUY] %s %s: %d @ %.2f', buy_action, stock_code, buy_qty, lp)


def _get_history_bars(stock_code, count=60):
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    cache_key = '%s:%s' % (stock_code, today)
    if cache_key in _HISTORY_CACHE:
        result = _HISTORY_CACHE[cache_key]
        return {'open': np.array(result['open']), 'high': np.array(result['high']),
                'low': np.array(result['low']), 'close': np.array(result['close']),
                'volume': np.array(result['volume'])}
    try:
        data = _ctx.get_market_data(
            ['open', 'high', 'low', 'close', 'volume'],
            stock_code=[stock_code], period='1d', dividend_type='front', count=count)
    except Exception as e:
        _log_print('ERROR', '[ERROR] get_market_data %s: %s', stock_code, str(e))
        return None
    if data is None:
        return None
    result = {}
    for field in ('open', 'high', 'low', 'close', 'volume'):
        try:
            val = data.get(field)
            if isinstance(val, dict):
                val = val.get(stock_code)
            if val is None or len(val) == 0:
                return None
            result[field] = list(val)
        except Exception:
            return None
    _HISTORY_CACHE[cache_key] = result
    return {'open': np.array(result['open']), 'high': np.array(result['high']),
            'low': np.array(result['low']), 'close': np.array(result['close']),
            'volume': np.array(result['volume'])}


def _do_order(stock_code, op_type, qty, limit_price):
    """Use xtrading.order_stock -- standard QMT strategy API."""
    if qty <= 0:
        return None
    try:
        kwargs = {}
        if limit_price is not None:
            kwargs['limit_price'] = limit_price
            kwargs['price_type'] = xtrading.ORDER_PRICE_TYPE_LIMIT
        order_id = xtrading.order_stock(stock_code, qty, op_type, **kwargs)
        if order_id is None or order_id == '':
            _log_print('ERROR', '[ORDER] %s order failed, empty order_id', stock_code)
            return None
        return order_id
    except Exception as e:
        _log_print('ERROR', '[ORDER] %s order exception: %s', stock_code, str(e))
        return None


# --- xtrading / xttrader compatibility ---
try:
    from xtquant import xtrading
except ImportError:
    try:
        import xtrading
    except ImportError:
        try:
            from xtquant import xttrader as xtrading
        except ImportError:
            try:
                import xttrader as xtrading
            except ImportError:
                class _XtradingStub:
                    ORDER_TYPE_BUY = 23
                    ORDER_TYPE_SELL = 24
                    ORDER_PRICE_TYPE_LIMIT = 50
                    ORDER_PRICE_TYPE_MARKET = 51

                    @staticmethod
                    def query_stock_position(stock_code):
                        return None

                    @staticmethod
                    def query_account_data():
                        return None

                    @staticmethod
                    def order_stock(stock_code, qty, order_type, **kwargs):
                        print('[STUB] order %s %d type=%s' % (stock_code, qty, order_type))
                        return 'stub_order_%s' % stock_code

                xtrading = _XtradingStub()
                print('[WARN] xtrading/xttrader not found, using stub')

# --- xttrader compat patches ---
_mod_name = getattr(xtrading, '__name__', '')
if 'xttrader' in _mod_name and 'stub' not in _mod_name.lower():
    if not hasattr(xtrading, 'query_stock_position'):
        xtrading.query_stock_position = lambda stock_code: None
    if not hasattr(xtrading, 'query_account_data'):
        xtrading.query_account_data = lambda: None
    if not hasattr(xtrading, 'ORDER_TYPE_BUY'):
        xtrading.ORDER_TYPE_BUY = 23
        xtrading.ORDER_TYPE_SELL = 24
        xtrading.ORDER_PRICE_TYPE_LIMIT = 50
        xtrading.ORDER_PRICE_TYPE_MARKET = 51
    if not hasattr(xtrading, 'order_stock'):
        xtrading.order_stock = lambda stock_code, qty, order_type, **kwargs: 'stub_%s' % stock_code
    print('[WARN] xttrader detected, patched with xtrading compat stubs')
