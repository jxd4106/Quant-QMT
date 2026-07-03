/Users/jaden/Documents/Claude_200w/半仓滚动QMT/half_position_rolling_v8.py — 从原版 V7 出发的改动清单
=====================================================================================

砍掉虚拟子账户（整个 ISO capital manager, lines 75-393）:
  删除: _iso_* 全部函数、cm_* 全部别名、_ISO_STATE_FILE 等常量
  改为: 直接用 xtrading.query_account_data() + xtrading.query_stock_position()

砍掉虚拟子账户在 on_bar 中的使用:
  删除: _get_virtual_equity(), _update_v7_equity()
  改为: get_account_info() 已存在，直接复用

砍掉虚拟子账户在 init 中的使用:
  删除: cm_init(STRATEGY_NAME, V7_INITIAL_CAPITAL)
  删除: init 中 _update_v7_equity() 调用
  删除: handlebar 中 _update_v7_equity(), cm_snapshot(), cm_print_summary()
  删除: handlebar 中 cm_check_stop_loss()

砍掉 on_bar 中虚拟持仓逻辑:
  删除: acct = _iso_get_acct(STRATEGY_NAME)
  删除: vpos_info = acct.get('positions', ...)
  改为: cur_pos = get_position(stock_code)  ← 直接用券商接口

砍掉 on_bar 中虚拟资金逻辑:
  删除: virtual_cash = cm_get_cash(STRATEGY_NAME), equity = ..., target_value = equity * TARGET_PCT
  改为: total_asset, available_cash = get_account_info(), target_value = total_asset * weight * TARGET_PCT

砍掉 do_order / on_bar 中对 ISO cm_record_trade 的调用:
  删除: cm_record_trade(...)
  → 改为写日志即可

新增: STOCK_POOL 字典（替换原来的 STOCKS tuple 列表） + weight 字段
新增: STOP_LOSS_PCT = 0.15, MAX_TRADES_PER_DAY = 50
新增: normalize_weights() 全局仓位归一化（F15）
新增: calc_order_qty() 综合下单量计算
新增: State persistence system（state.json + override.json, F8/F18）
新增: is_hk_stock 支持 .HGT/.SGT（除原来 .HK 外）
新增: is_in_trading_hours() 交易时段过滤（F7）
新增: get_signal_time() 信号判定时间点（F19）
新增: check_stop_loss() 15% 止损（F6，用 profit_rate）
新增: logging 日志模块（F10）
新增: init 中 process_override() + 启动对账（F16）
修改: handlebar 加交易时段过滤 + 信号判定时间门控 + 防重复 + 止损
修改: on_bar 改用 get_position/get_account_info 真实账户
修改: on_bar 加全局仓位归一化
修改: is_hk_stock 也匹配 .HGT/.SGT（港股通格式）

不动的部分（原封保留）:
  - 整个 xtrading 兼容导入链（lines 22-68）
  - calc_indicators() 全部（lines 429-516）
  - calc_signals() 全部（lines 523-556）
  - get_lot_size() 全部（lines 566-596）
  - _fetch_history_bars() / get_history_bars() 全部（lines 603-678）
  - get_buy_fee_rate / get_sell_fee_rate / get_hk_fixed_fee 全部
  - _get_latest_bar() 全部
  - do_order() 全部（lines 737-761）
  - _HISTORY_CACHE 全部
  - _LOT_SIZE_CACHE 全部
