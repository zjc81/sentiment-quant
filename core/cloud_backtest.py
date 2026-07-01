"""
云端回测引擎 - 零依赖纯Python实现（适配 Render 512MB 免费版）

支持的6种策略（与 core/backtest.py 完全一致）:
  1. buy_hold:       基准策略（买入持有）
  2. sentiment_only: 纯情绪信号（新闻正面时持有，负面时空仓）
  3. sentiment_ma:   情绪+均线过滤（均线多头时才允许买入）
  4. rsi_mean_reversion: RSI均值回归（RSI<30买入，RSI>70卖出）
  5. bollinger_breakout: 布林带突破（突破上轨买入，跌破中轨卖出）
  6. momentum:       动量策略（动量>0+均线多头买入）
"""
import math
import time


# ======================================================================
# 纯 Python 技术指标计算
# ======================================================================

def _rolling_mean(values, period):
    """简单移动平均线（纯Python）"""
    result = []
    for i in range(len(values)):
        if i < period - 1:
            result.append(None)
        else:
            s = sum(values[i - period + 1:i + 1])
            result.append(s / period)
    return result


def _rolling_std(values, period):
    """滚动标准差（纯Python）"""
    means = _rolling_mean(values, period)
    result = []
    for i in range(len(values)):
        if i < period - 1 or means[i] is None:
            result.append(None)
        else:
            var = sum((values[j] - means[i]) ** 2 for j in range(i - period + 1, i + 1)) / period
            result.append(math.sqrt(var))
    return result


def _calc_indicators(kline):
    """为K线数据添加技术指标字段（原地修改）"""
    closes = [k["close"] for k in kline]
    volumes = [k["volume"] for k in kline]

    # MA5, MA20
    ma5 = _rolling_mean(closes, 5)
    ma20 = _rolling_mean(closes, 20)

    # RSI(14)
    rsi_list = [None] * len(closes)
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    for i in range(14, len(gains)):
        avg_g = sum(gains[i - 14:i + 1]) / 14
        avg_l = sum(losses[i - 14:i + 1]) / 14
        rs = avg_g / (avg_l + 1e-10)
        rsi_list[i + 1] = 100 - (100 / (1 + rs))

    # Bollinger Bands (20, 2)
    bb_mid = _rolling_mean(closes, 20)
    bb_std = _rolling_std(closes, 20)
    bb_upper = [(bb_mid[i] + 2 * bb_std[i]) if bb_mid[i] is not None and bb_std[i] is not None else None
                for i in range(len(closes))]
    bb_lower = [(bb_mid[i] - 2 * bb_std[i]) if bb_mid[i] is not None and bb_std[i] is not None else None
                for i in range(len(closes))]
    bb_width = [((bb_upper[i] - bb_lower[i]) / bb_mid[i]) if bb_mid[i] and bb_mid[i] > 0 and bb_upper[i] and bb_lower[i]
                else None for i in range(len(closes))]

    # Momentum(10)
    momentum = [None] * 10 + [closes[i] / closes[i - 10] - 1 for i in range(10, len(closes))]

    # Volume MA(5)
    vol_ma5 = _rolling_mean(volumes, 5)

    # 将所有指标挂到每条K线上
    for i, k in enumerate(kline):
        k["_ma5"] = ma5[i]
        k["_ma20"] = ma20[i]
        k["_rsi"] = rsi_list[i]
        k["_bb_upper"] = bb_upper[i]
        k["_bb_mid"] = bb_mid[i]
        k["_bb_width"] = bb_width[i]
        k["_momentum"] = momentum[i]
        k["_vol_ma5"] = vol_ma5[i]

    return kline


# ======================================================================
# 回测核心逻辑
# ======================================================================

def _build_sentiment_signals(kline, sentiment_result):
    """将情感分析结果对齐到交易日，生成信号序列"""
    date_score_map = {}
    for trend in sentiment_result.get("time_analysis", {}).get("trend", []):
        ds = trend.get("date", "")
        sc = trend.get("score", 0.5)
        if ds:
            date_score_map[ds] = sc

    signals = {}
    for k in kline:
        ds = k.get("date", "")
        sc = date_score_map.get(ds, 0.5)

        if sc > 0.65:
            sig = "strong_buy"
        elif sc > 0.5:
            sig = "buy"
        elif sc < 0.35:
            sig = "strong_sell"
        elif sc < 0.5:
            sig = "sell"
        else:
            sig = "hold"

        signals[ds] = {"score": sc, "signal": sig}

    return signals


def _finalize(start_date, end_date, final_value, capital, trades, equity_curve,
              daily_returns):
    """计算回测最终统计指标"""
    total_return = (final_value - capital) / capital * 100 if capital > 0 else 0

    # 年化收益率
    try:
        from datetime import datetime
        sd = datetime.strptime(start_date, "%Y-%m-%d")
        ed = datetime.strptime(end_date, "%Y-%m-%d")
        years = max((ed - sd).days / 365.0, 1 / 365.0)
        annual_return = ((1 + total_return / 100) ** (1 / years) - 1) * 100
    except Exception:
        annual_return = total_return

    # 最大回撤
    peak = -float("inf")
    max_dd = 0
    for e in equity_curve:
        v = e["value"]
        if v > peak:
            peak = v
        dd = (peak - v) / peak * 100 if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd

    # 夏普比率（纯Python）
    n = len(daily_returns)
    if n > 1:
        avg_r = sum(daily_returns) / n
        var_r = sum((r - avg_r) ** 2 for r in daily_returns) / n
        std_r = math.sqrt(var_r) if var_r > 0 else 1e-10
        sharpe = avg_r / (std_r + 1e-10) * math.sqrt(252)
    else:
        sharpe = 0

    # 胜率 & 盈亏比
    buy_trades = [t for t in trades if t["action"] == "buy"]
    sell_trades = [t for t in trades if t["action"] == "sell"]
    total_trades = len(buy_trades)

    win_trades = 0
    total_profit = 0
    total_loss = 0
    for i in range(min(len(buy_trades), len(sell_trades))):
        profit = sell_trades[i]["value"] - buy_trades[i]["value"]
        if profit > 0:
            win_trades += 1
            total_profit += profit
        else:
            total_loss += abs(profit)

    win_rate = win_trades / total_trades * 100 if total_trades > 0 else 0
    profit_factor = total_loss != 0 and round(total_profit / total_loss, 2) or float("inf")

    return {
        "total_return": round(total_return, 2),
        "annual_return": round(annual_return, 2),
        "max_drawdown": round(max_dd, 2),
        "sharpe_ratio": round(sharpe, 2),
        "total_trades": total_trades,
        "win_rate": round(win_rate, 2),
        "profit_factor": round(profit_factor, 2) if profit_factor != float("inf") else float("inf"),
        "final_value": round(final_value, 2),
        "equity_curve": equity_curve,
        "trades": trades,
    }


def _backtest_sentiment_only(kline, signals, capital, commission=0.0003, slippage=0.001):
    """策略1: 纯情绪信号"""
    cash = capital
    position = 0
    trades = []
    equity_curve = []
    daily_returns = []
    prev_value = capital
    start_date = kline[0]["date"] if kline else ""
    end_date = kline[-1]["date"] if kline else ""

    for k in kline:
        ds = k["date"]
        close = k["close"]
        sig = signals.get(ds, {"signal": "hold", "score": 0.5})

        if sig["signal"] in ("strong_buy", "buy") and position == 0:
            bp = close * (1 + slippage)
            shares = int(cash / bp / 100) * 100
            if shares > 0:
                cost = shares * bp
                comm = cost * commission
                cash -= (cost + comm)
                position = shares
                trades.append({"date": ds, "action": "buy", "price": round(bp, 2),
                               "shares": shares, "value": round(cost, 2), "commission": round(comm, 2),
                               "reason": f"情绪信号:{sig['signal']}({sig['score']:.2f})"})

        elif sig["signal"] in ("strong_sell", "sell") and position > 0:
            sp = close * (1 - slippage)
            val = position * sp
            comm = val * commission
            cash += (val - comm)
            trades.append({"date": ds, "action": "sell", "price": round(sp, 2),
                           "shares": position, "value": round(val, 2), "commission": round(comm, 2),
                           "reason": f"情绪信号:{sig['signal']}({sig['score']:.2f})"})
            position = 0

        cur_val = cash + position * close
        dr = (cur_val - prev_value) / prev_value if prev_value > 0 else 0
        daily_returns.append(dr)
        equity_curve.append({"date": ds, "value": round(cur_val, 2), "position_value": round(position * close, 2)})
        prev_value = cur_val

    if position > 0:
        last_c = kline[-1]["close"]
        sp = last_c * (1 - slippage)
        val = position * sp
        comm = val * commission
        cash += (val - comm)
        trades.append({"date": end_date, "action": "sell", "price": round(sp, 2),
                       "shares": position, "value": round(val, 2), "commission": round(comm, 2),
                       "reason": "回测结束平仓"})

    return _finalize(start_date, end_date, cash, capital, trades, equity_curve, daily_returns)


def _backtest_sentiment_ma(kline, signals, capital, commission=0.0003, slippage=0.001):
    """策略2: 情绪 + 均线过滤"""
    cash = capital
    position = 0
    trades = []
    equity_curve = []
    daily_returns = []
    prev_value = capital
    start_date = kline[0]["date"]
    end_date = kline[-1]["date"]

    for k in kline:
        ds = k["date"]
        close = k["close"]
        ma5 = k.get("_ma5")
        ma20 = k.get("_ma20")
        if ma5 is None or ma20 is None:
            continue

        sig = signals.get(ds, {"signal": "hold", "score": 0.5})
        ma_bullish = ma5 > ma20

        if sig["signal"] in ("strong_buy", "buy") and ma_bullish and position == 0:
            bp = close * (1 + slippage)
            shares = int(cash / bp / 100) * 100
            if shares > 0:
                cost = shares * bp
                comm = cost * commission
                cash -= (cost + comm)
                position = shares
                trades.append({"date": ds, "action": "buy", "price": round(bp, 2),
                               "shares": shares, "value": round(cost, 2), "commission": round(comm, 2),
                               "reason": f"情绪+均线多头:{sig['score']:.2f}"})

        elif sig["signal"] in ("strong_sell", "sell") and position > 0:
            sp = close * (1 - slippage)
            val = position * sp
            comm = val * commission
            cash += (val - comm)
            trades.append({"date": ds, "action": "sell", "price": round(sp, 2),
                           "shares": position, "value": round(val, 2), "commission": round(comm, 2),
                           "reason": f"情绪/均线转空:{sig['score']:.2f}"})
            position = 0

        cur_val = cash + position * close
        dr = (cur_val - prev_value) / prev_value if prev_value > 0 else 0
        daily_returns.append(dr)
        equity_curve.append({"date": ds, "value": round(cur_val, 2), "position_value": round(position * close, 2)})
        prev_value = cur_val

    if position > 0:
        sp = kline[-1]["close"] * (1 - slippage)
        val = position * sp
        cash += val - val * commission
        trades.append({"date": end_date, "action": "sell", "price": round(sp, 2),
                       "shares": position, "value": round(val, 2), "commission": round(val * commission, 2),
                       "reason": "回测结束平仓"})

    return _finalize(start_date, end_date, cash, capital, trades, equity_curve, daily_returns)


def _backtest_buy_hold(kline, capital, commission=0.0003, slippage=0.001):
    """策略3: 买入持有基准"""
    first_close = kline[0]["close"]
    last_close = kline[-1]["close"]
    start_date = kline[0]["date"]
    end_date = kline[-1]["date"]

    bp = first_close * (1 + slippage)
    shares = int(capital / bp / 100) * 100
    buy_comm = 0
    if shares > 0:
        buy_comm = shares * bp * commission
        cash = capital - shares * bp - buy_comm
    else:
        cash = capital

    trades = []
    if shares > 0:
        trades.append({"date": start_date, "action": "buy", "price": round(bp, 2),
                       "shares": shares, "value": round(shares * bp, 2), "commission": round(buy_comm, 2),
                       "reason": "期初建仓"})
        sp = last_close * (1 - slippage)
        val = shares * sp
        sell_comm = val * commission
        cash += val - sell_comm
        trades.append({"date": end_date, "action": "sell", "price": round(sp, 2),
                       "shares": shares, "value": round(val, 2), "commission": round(sell_comm, 2),
                       "reason": "期末平仓"})

    equity_curve = []
    daily_returns = []
    prev_value = capital
    total_comm = buy_comm + (shares > 0 and shares * last_close * (1 - slippage) * commission or 0)
    for k in kline:
        ds = k["date"]
        close = k["close"]
        ratio = close / first_close if first_close > 0 else 1
        cv = capital * ratio - total_comm
        dr = (cv - prev_value) / prev_value if prev_value > 0 else 0
        daily_returns.append(dr)
        equity_curve.append({"date": ds, "value": round(cv, 2), "position_value": round(cv, 2)})
        prev_value = cv

    return _finalize(start_date, end_date, cash, capital, trades, equity_curve, daily_returns)


def _backtest_rsi(kline, capital, commission=0.0003, slippage=0.001):
    """策略4: RSI均值回归"""
    kline = _calc_indicators(kline)
    cash = capital
    position = 0
    trades = []
    equity_curve = []
    daily_returns = []
    prev_value = capital
    start_date = kline[0]["date"]
    end_date = kline[-1]["date"]

    for k in kline:
        ds = k["date"]
        close = k["close"]
        rsi = k.get("_rsi")
        if rsi is None:
            continue

        if rsi < 30 and position == 0:
            bp = close * (1 + slippage)
            shares = int(cash / bp / 100) * 100
            if shares > 0:
                cost = shares * bp
                comm = cost * commission
                cash -= (cost + comm)
                position = shares
                trades.append({"date": ds, "action": "buy", "price": round(bp, 2),
                               "shares": shares, "value": round(cost, 2), "commission": round(comm, 2),
                               "reason": f"RSI超卖({rsi:.1f})"})
        elif rsi > 70 and position > 0:
            sp = close * (1 - slippage)
            val = position * sp
            comm = val * commission
            cash += (val - comm)
            trades.append({"date": ds, "action": "sell", "price": round(sp, 2),
                           "shares": position, "value": round(val, 2), "commission": round(comm, 2),
                           "reason": f"RSI超买({rsi:.1f})"})
            position = 0

        cv = cash + position * close
        dr = (cv - prev_value) / prev_value if prev_value > 0 else 0
        daily_returns.append(dr)
        equity_curve.append({"date": ds, "value": round(cv, 2), "position_value": round(position * close, 2)})
        prev_value = cv

    if position > 0:
        sp = kline[-1]["close"] * (1 - slippage)
        val = position * sp
        cash += val - val * commission
        trades.append({"date": end_date, "action": "sell", "price": round(sp, 2),
                       "shares": position, "value": round(val, 2), "commission": round(val * commission, 2),
                       "reason": "回测结束平仓"})

    return _finalize(start_date, end_date, cash, capital, trades, equity_curve, daily_returns)


def _backtest_bollinger(kline, capital, commission=0.0003, slippage=0.001):
    """策略5: 布林带突破"""
    kline = _calc_indicators(kline)
    cash = capital
    position = 0
    trades = []
    equity_curve = []
    daily_returns = []
    prev_value = capital
    start_date = kline[0]["date"]
    end_date = kline[-1]["date"]

    for k in kline:
        ds = k["date"]
        close = k["close"]
        bb_u = k.get("_bb_upper")
        bb_m = k.get("_bb_mid")
        bbw = k.get("_bb_width")
        ma5 = k.get("_ma5")
        vol_ma5 = k.get("_vol_ma5")

        if bb_u is None or bb_m is None:
            continue

        vol_confirm = True
        if vol_ma5 is not None and k.get("volume"):
            vol_confirm = k["volume"] > vol_ma5

        # 放量突破上轨 + MA在布林中轨之上
        if (close > bb_u and ma5 and ma5 > bb_m and (bbw or 0) > 0.05
                and vol_confirm and position == 0):
            bp = close * (1 + slippage)
            shares = int(cash / bp / 100) * 100
            if shares > 0:
                cost = shares * bp
                comm = cost * commission
                cash -= (cost + comm)
                position = shares
                trades.append({"date": ds, "action": "buy", "price": round(bp, 2),
                               "shares": shares, "value": round(cost, 2), "commission": round(comm, 2),
                               "reason": f"布林突破({(bbw or 0):.1%})"})
        elif close < bb_m and position > 0:
            sp = close * (1 - slippage)
            val = position * sp
            comm = val * commission
            cash += (val - comm)
            trades.append({"date": ds, "action": "sell", "price": round(sp, 2),
                           "shares": position, "value": round(val, 2), "commission": round(comm, 2),
                           "reason": "跌破中轨"})
            position = 0

        cv = cash + position * close
        dr = (cv - prev_value) / prev_value if prev_value > 0 else 0
        daily_returns.append(dr)
        equity_curve.append({"date": ds, "value": round(cv, 2), "position_value": round(position * close, 2)})
        prev_value = cv

    if position > 0:
        sp = kline[-1]["close"] * (1 - slippage)
        val = position * sp
        cash += val - val * commission
        trades.append({"date": end_date, "action": "sell", "price": round(sp, 2),
                       "shares": position, "value": round(val, 2), "commission": round(val * commission, 2),
                       "reason": "回测结束平仓"})

    return _finalize(start_date, end_date, cash, capital, trades, equity_curve, daily_returns)


def _backtest_momentum(kline, capital, commission=0.0003, slippage=0.001):
    """策略6: 动量策略"""
    kline = _calc_indicators(kline)
    cash = capital
    position = 0
    trades = []
    equity_curve = []
    daily_returns = []
    prev_value = capital
    start_date = kline[0]["date"]
    end_date = kline[-1]["date"]

    for k in kline:
        ds = k["date"]
        close = k["close"]
        mom = k.get("_momentum")
        ma5 = k.get("_ma5")
        ma20 = k.get("_ma20")
        vol_ma5 = k.get("_vol_ma5")

        if mom is None or ma5 is None or ma20 is None:
            continue

        vol_confirm = True
        if vol_ma5 is not None and k.get("volume"):
            vol_confirm = k["volume"] > vol_ma5

        ma_bullish = ma5 > ma20

        if mom > 0.02 and ma_bullish and vol_confirm and position == 0:
            bp = close * (1 + slippage)
            shares = int(cash / bp / 100) * 100
            if shares > 0:
                cost = shares * bp
                comm = cost * commission
                cash -= (cost + comm)
                position = shares
                trades.append({"date": ds, "action": "buy", "price": round(bp, 2),
                               "shares": shares, "value": round(cost, 2), "commission": round(comm, 2),
                               "reason": f"动量+{mom:.1%}多头"})
        elif (mom < -0.01 or (not ma_bullish)) and position > 0:
            sp = close * (1 - slippage)
            val = position * sp
            comm = val * commission
            cash += (val - comm)
            reason = f"动量{mom:.1%}" + ("死叉" if not ma_bullish else "")
            trades.append({"date": ds, "action": "sell", "price": round(sp, 2),
                           "shares": position, "value": round(val, 2), "commission": round(comm, 2),
                           "reason": reason})
            position = 0

        cv = cash + position * close
        dr = (cv - prev_value) / prev_value if prev_value > 0 else 0
        daily_returns.append(dr)
        equity_curve.append({"date": ds, "value": round(cv, 2), "position_value": round(position * close, 2)})
        prev_value = cv

    if position > 0:
        sp = kline[-1]["close"] * (1 - slippage)
        val = position * sp
        cash += val - val * commission
        trades.append({"date": end_date, "action": "sell", "price": round(sp, 2),
                       "shares": position, "value": round(val, 2), "commission": round(val * commission, 2),
                       "reason": "回测结束平仓"})

    return _finalize(start_date, end_date, cash, capital, trades, equity_curve, daily_returns)


# ======================================================================
# 策略名称映射
# ======================================================================

_STRATEGY_NAMES = {
    "buy_hold": "买入持有",
    "sentiment_only": "纯情绪信号",
    "sentiment_ma": "情绪+均线",
    "rsi_mean_reversion": "RSI均值回归",
    "bollinger_breakout": "布林带突破",
    "momentum": "动量策略",
}


def get_strategy_name(key):
    return _STRATEGY_NAMES.get(key, key)


# ======================================================================
# 主入口：多策略对比回测
# ======================================================================

def compare_strategies_cloud(
    stock_code,
    stock_name="",
    capital=100000,
    lookback_days=7,
    kline_data=None,
    sentiment_result=None,
):
    """
    云端版：对6种策略进行对比回测（零依赖）

    Args:
        stock_code: 股票代码
        stock_name: 股票名称
        capital: 初始资金
        lookback_days: 回溯天数
        kline_data: K线数据 List[Dict]（外部传入，避免重复获取）
        sentiment_result: 情感分析结果 Dict（外部传入）

    Returns:
        Dict: {strategy_key: result_dict}
    """
    if not kline_data or len(kline_data) < 15:
        raise ValueError(f"K线数据不足({len(kline_data) if kline_data else 0}条)，无法回测 {stock_code}")

    print(f"[BACKTEST] 开始回测 {stock_code} ({len(kline_data)}条K线, {lookback_days}天, 资金{capital})")
    t0 = time.time()

    # 构建情感信号
    signals = _build_sentiment_signals(kline_data, sentiment_result or {})

    strategies = [
        ("buy_hold", lambda: _backtest_buy_hold(kline_data, capital)),
        ("sentiment_only", lambda: _backtest_sentiment_only(kline_data, signals, capital)),
        ("sentiment_ma", lambda: _backtest_sentiment_ma(kline_data, signals, capital)),
        ("rsi_mean_reversion", lambda: _backtest_rsi(kline_data, capital)),
        ("bollinger_breakout", lambda: _backtest_bollinger(kline_data, capital)),
        ("momentum", lambda: _backtest_momentum(kline_data, capital)),
    ]

    results = {}
    for name, fn in strategies:
        try:
            res = fn()
            res["strategy"] = name
            res["strategy_name"] = get_strategy_name(name)
            results[name] = res
            print(f"  OK {name}: 收益={res['total_return']:+.2f}%, 回撤={res['max_drawdown']:.2f}%, 夏普={res['sharpe_ratio']:.2f}")
        except Exception as e:
            print(f"  FAIL {name}: {e}")
            results[name] = {"error": str(e)}

    elapsed = time.time() - t0
    print(f"[BACKTEST] 回测完成 ({elapsed:.1f}s)")
    return results
