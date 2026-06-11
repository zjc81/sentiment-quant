"""
回测引擎 - 基于市场情绪信号的量化回测

策略说明:
  本回测引擎将情感分析与量化交易结合。
  核心假设：正面情绪→买入信号，负面情绪→卖出/空仓信号。

支持的策略:
  1. sentiment_only: 纯情绪信号（新闻正面时持有，负面时空仓）
  2. sentiment_ma: 情绪+均线过滤（均线多头时才允许买入）
  3. sentiment_momentum: 情绪+动量过滤
  4. buy_hold: 基准策略（买入持有）
"""
import time
import math
import json
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Callable
from dataclasses import dataclass, field
from tqdm import tqdm
from config import (
    DATA_DIR, REPORT_DIR, DEFAULT_START_CAPITAL,
    DEFAULT_COMMISSION, DEFAULT_SLIPPAGE,
    DEFAULT_LOOKBACK_DAYS,
)
from core.data_fetcher import get_kline_data, batch_get_news
from core.sentiment import analyze_stock_sentiment


# ======================================================================
# 数据结构
# ======================================================================

@dataclass
class TradeRecord:
    """交易记录"""
    date: str               # 交易日期
    action: str             # buy/sell
    price: float            # 成交价格
    shares: int             # 成交数量
    value: float            # 成交金额
    commission: float       # 手续费
    reason: str = ""        # 交易理由


@dataclass
class BacktestResult:
    """回测结果"""
    stock_code: str
    stock_name: str
    strategy: str
    start_date: str
    end_date: str
    initial_capital: float
    final_value: float
    total_return: float
    annual_return: float
    max_drawdown: float
    sharpe_ratio: float
    total_trades: int
    win_rate: float
    profit_factor: float
    trades: List[TradeRecord] = field(default_factory=list)
    equity_curve: List[Dict] = field(default_factory=list)
    daily_returns: List[float] = field(default_factory=list)
    sentiment_signals: List[Dict] = field(default_factory=list)


# ======================================================================
# 回测引擎
# ======================================================================

class BacktestEngine:
    """
    量化回测引擎，支持多种策略
    """

    def __init__(
        self,
        capital: float = DEFAULT_START_CAPITAL,
        commission: float = DEFAULT_COMMISSION,
        slippage: float = DEFAULT_SLIPPAGE,
    ):
        self.capital = capital
        self.commission = commission
        self.slippage = slippage
        self.results: Dict[str, BacktestResult] = {}

    def run_single(
        self,
        stock_code: str,
        stock_name: str = "",
        strategy: str = "sentiment_only",
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
        sentiment_threshold: float = 0.5,
    ) -> BacktestResult:
        """
        对单只股票执行回测

        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            strategy: 策略名称
            lookback_days: 回溯天数
            sentiment_threshold: 情感阈值（高于此值考虑买入）

        Returns:
            BacktestResult: 回测结果
        """
        # ===== 1. 获取K线数据 =====
        kline = get_kline_data(stock_code, days=lookback_days + 30)
        if kline is None or len(kline) < 20:
            raise ValueError(f"K线数据不足，无法回测 {stock_code}")

        # ===== 2. 获取新闻并分析 =====
        from core.data_fetcher import get_stock_news
        news_list = get_stock_news(stock_code, days=lookback_days)
        sentiment_result = analyze_stock_sentiment(news_list)

        # ===== 3. 构建情感信号 =====
        # 将情感分析结果与交易日对齐
        sentiment_signals = self._align_sentiment_to_dates(
            kline, sentiment_result, lookback_days
        )

        # ===== 4. 执行回测 =====
        if strategy == "sentiment_only":
            result = self._backtest_sentiment_only(
                kline, sentiment_signals, stock_code, stock_name
            )
        elif strategy == "sentiment_ma":
            result = self._backtest_sentiment_ma(
                kline, sentiment_signals, stock_code, stock_name
            )
        elif strategy == "buy_hold":
            result = self._backtest_buy_hold(
                kline, stock_code, stock_name
            )
        elif strategy == "rsi_mean_reversion":
            result = self._backtest_rsi_mean_reversion(
                kline, stock_code, stock_name
            )
        elif strategy == "bollinger_breakout":
            result = self._backtest_bollinger_breakout(
                kline, stock_code, stock_name
            )
        elif strategy == "momentum":
            result = self._backtest_momentum(
                kline, stock_code, stock_name
            )
        else:
            result = self._backtest_sentiment_only(
                kline, sentiment_signals, stock_code, stock_name
            )

        result.strategy = strategy
        result.sentiment_signals = sentiment_signals
        self.results[f"{stock_code}_{strategy}"] = result
        return result

    def _align_sentiment_to_dates(
        self, kline: pd.DataFrame, sentiment: Dict, lookback_days: int
    ) -> List[Dict]:
        """
        将情感分析结果对齐到交易日

        由于情感分析基于新闻，而新闻并非每天都有，
        我们需要将每日情感映射到交易日。
        """
        # 构建日期->情感映射
        date_score_map = {}
        for trend in sentiment.get("time_analysis", {}).get("trend", []):
            date_str = trend.get("date", "")
            score = trend.get("score", 0.5)
            if date_str:
                date_score_map[date_str] = score

        signals = []
        for _, row in kline.iterrows():
            date_str = row["date"].strftime("%Y-%m-%d")
            score = date_score_map.get(date_str, 0.5)  # 默认中性

            # 信号：根据情感得分生成
            if score > 0.65:
                signal = "strong_buy"
            elif score > 0.5:
                signal = "buy"
            elif score < 0.35:
                signal = "strong_sell"
            elif score < 0.5:
                signal = "sell"
            else:
                signal = "hold"

            signals.append({
                "date": date_str,
                "score": score,
                "signal": signal,
                "close": float(row["close"]),
            })

        return signals

    def _calc_indicators(self, kline: pd.DataFrame) -> pd.DataFrame:
        """计算常用技术指标：RSI、布林带、动量"""
        close = kline["close"]
        # RSI(14)
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = (-delta).where(delta < 0, 0.0)
        avg_gain = gain.rolling(14).mean()
        avg_loss = loss.rolling(14).mean()
        rs = avg_gain / (avg_loss + 1e-10)
        kline["rsi"] = 100 - (100 / (1 + rs))
        # 布林带(20,2)
        kline["bb_mid"] = close.rolling(20).mean()
        bb_std = close.rolling(20).std()
        kline["bb_upper"] = kline["bb_mid"] + 2 * bb_std
        kline["bb_lower"] = kline["bb_mid"] - 2 * bb_std
        kline["bb_width"] = (kline["bb_upper"] - kline["bb_lower"]) / kline["bb_mid"]
        # 动量(10)
        kline["momentum"] = close / close.shift(10) - 1
        kline["vol_ma5"] = kline["volume"].rolling(5).mean()
        return kline

    def _backtest_sentiment_only(
        self,
        kline: pd.DataFrame,
        signals: List[Dict],
        stock_code: str,
        stock_name: str,
    ) -> BacktestResult:
        """纯情绪信号策略"""
        cash = self.capital
        position = 0  # 持有股数
        trades = []
        equity_curve = []
        daily_returns = []

        prev_value = cash
        start_date = kline.iloc[0]["date"].strftime("%Y-%m-%d") if len(kline) > 0 else ""
        end_date = kline.iloc[-1]["date"].strftime("%Y-%m-%d") if len(kline) > 0 else ""

        # 使用日期建立快速索引
        signal_map = {s["date"]: s for s in signals}

        for _, row in kline.iterrows():
            date_str = row["date"].strftime("%Y-%m-%d")
            close = float(row["close"])
            sig = signal_map.get(date_str, {"signal": "hold", "score": 0.5})
            signal = sig["signal"]

            # 开仓逻辑
            if signal in ("strong_buy", "buy") and position == 0:
                buy_price = close * (1 + self.slippage)
                shares = int(cash / buy_price / 100) * 100  # 整手
                if shares > 0:
                    cost = shares * buy_price
                    commission = cost * self.commission
                    cash -= (cost + commission)
                    position = shares
                    trades.append(TradeRecord(
                        date=date_str, action="buy", price=buy_price,
                        shares=shares, value=cost, commission=commission,
                        reason=f"情绪信号: {sig['signal']} (得分{sig['score']:.2f})"
                    ))

            # 平仓逻辑
            elif signal in ("strong_sell", "sell") and position > 0:
                sell_price = close * (1 - self.slippage)
                value = position * sell_price
                commission = value * self.commission
                cash += (value - commission)
                trades.append(TradeRecord(
                    date=date_str, action="sell", price=sell_price,
                    shares=position, value=value, commission=commission,
                    reason=f"情绪信号: {sig['signal']} (得分{sig['score']:.2f})"
                ))
                position = 0

            # 计算每日净值
            current_value = cash + position * close
            daily_return = (current_value - prev_value) / prev_value if prev_value > 0 else 0
            daily_returns.append(daily_return)

            equity_curve.append({
                "date": date_str,
                "value": round(current_value, 2),
                "position_value": round(position * close, 2),
                "cash": round(cash, 2),
            })
            prev_value = current_value

        # 最后平仓
        if position > 0:
            last_close = float(kline.iloc[-1]["close"])
            sell_price = last_close * (1 - self.slippage)
            value = position * sell_price
            commission = value * self.commission
            cash += (value - commission)
            trades.append(TradeRecord(
                date=kline.iloc[-1]["date"].strftime("%Y-%m-%d"),
                action="sell", price=sell_price,
                shares=position, value=value, commission=commission,
                reason="回测结束平仓"
            ))
            position = 0

        final_value = cash
        return self._finalize_result(
            stock_code, stock_name, start_date, end_date,
            final_value, trades, equity_curve, daily_returns,
            "sentiment_only"
        )

    def _backtest_sentiment_ma(
        self,
        kline: pd.DataFrame,
        signals: List[Dict],
        stock_code: str,
        stock_name: str,
    ) -> BacktestResult:
        """情绪+均线过滤策略"""
        cash = self.capital
        position = 0
        trades = []
        equity_curve = []
        daily_returns = []

        prev_value = cash
        start_date = kline.iloc[0]["date"].strftime("%Y-%m-%d") if len(kline) > 0 else ""
        end_date = kline.iloc[-1]["date"].strftime("%Y-%m-%d") if len(kline) > 0 else ""

        # 计算均线
        kline["ma5"] = kline["close"].rolling(5).mean()
        kline["ma20"] = kline["close"].rolling(20).mean()

        signal_map = {s["date"]: s for s in signals}

        for idx, row in kline.iterrows():
            date_str = row["date"].strftime("%Y-%m-%d")
            close = float(row["close"])
            ma5 = row.get("ma5", close)
            ma20 = row.get("ma20", close)

            if pd.isna(ma5) or pd.isna(ma20):
                continue

            sig = signal_map.get(date_str, {"signal": "hold", "score": 0.5})
            signal = sig["signal"]
            ma_bullish = ma5 > ma20  # 均线多头排列

            # 开仓：情绪正面 + 均线多头
            if signal in ("strong_buy", "buy") and ma_bullish and position == 0:
                buy_price = close * (1 + self.slippage)
                shares = int(cash / buy_price / 100) * 100
                if shares > 0:
                    cost = shares * buy_price
                    commission = cost * self.commission
                    cash -= (cost + commission)
                    position = shares
                    trades.append(TradeRecord(
                        date=date_str, action="buy", price=buy_price,
                        shares=shares, value=cost, commission=commission,
                        reason=f"情绪+均线多头: {sig['score']:.2f}"
                    ))

            # 平仓：情绪负面 或 均线死叉
            elif signal in ("strong_sell", "sell") and position > 0:
                sell_price = close * (1 - self.slippage)
                value = position * sell_price
                commission = value * self.commission
                cash += (value - commission)
                trades.append(TradeRecord(
                    date=date_str, action="sell", price=sell_price,
                    shares=position, value=value, commission=commission,
                    reason=f"情绪/均线转空: {sig['score']:.2f}"
                ))
                position = 0

            current_value = cash + position * close
            daily_return = (current_value - prev_value) / prev_value if prev_value > 0 else 0
            daily_returns.append(daily_return)

            equity_curve.append({
                "date": date_str,
                "value": round(current_value, 2),
                "position_value": round(position * close, 2),
                "cash": round(cash, 2),
            })
            prev_value = current_value

        if position > 0:
            last_close = float(kline.iloc[-1]["close"])
            sell_price = last_close * (1 - self.slippage)
            value = position * sell_price
            commission = value * self.commission
            cash += (value - commission)
            trades.append(TradeRecord(
                date=kline.iloc[-1]["date"].strftime("%Y-%m-%d"),
                action="sell", price=sell_price,
                shares=position, value=value, commission=commission,
                reason="回测结束平仓"
            ))
            position = 0

        return self._finalize_result(
            stock_code, stock_name, start_date, end_date,
            cash, trades, equity_curve, daily_returns,
            "sentiment_ma"
        )

    def _backtest_buy_hold(
        self, kline: pd.DataFrame, stock_code: str, stock_name: str
    ) -> BacktestResult:
        """买入持有基准策略"""
        start_date = kline.iloc[0]["date"].strftime("%Y-%m-%d") if len(kline) > 0 else ""
        end_date = kline.iloc[-1]["date"].strftime("%Y-%m-%d") if len(kline) > 0 else ""
        trades = []
        equity_curve = []
        daily_returns = []

        first_close = float(kline.iloc[0]["close"])
        last_close = float(kline.iloc[-1]["close"])

        # 期初买入
        buy_price = first_close * (1 + self.slippage)
        shares = int(self.capital / buy_price / 100) * 100
        buy_commission = 0.0
        if shares > 0:
            cost = shares * buy_price
            buy_commission = cost * self.commission
            cash = self.capital - cost - buy_commission
            trades.append(TradeRecord(
                date=start_date, action="buy", price=buy_price,
                shares=shares, value=cost, commission=buy_commission,
                reason="期初建仓"
            ))
        else:
            cash = self.capital

        # 期末卖出
        sell_price = last_close * (1 - self.slippage)
        sell_commission = 0.0
        if shares > 0:
            value = shares * sell_price
            sell_commission = value * self.commission
            cash += value - sell_commission
            trades.append(TradeRecord(
                date=end_date, action="sell", price=sell_price,
                shares=shares, value=value, commission=sell_commission,
                reason="期末平仓"
            ))

        total_commission = buy_commission + sell_commission

        # 净值曲线
        prev_value = self.capital
        for _, row in kline.iterrows():
            date_str = row["date"].strftime("%Y-%m-%d")
            close = float(row["close"])
            ratio = close / first_close if first_close > 0 else 1
            current_value = self.capital * ratio - total_commission

            daily_return = (current_value - prev_value) / prev_value if prev_value > 0 else 0
            daily_returns.append(daily_return)

            equity_curve.append({
                "date": date_str,
                "value": round(current_value, 2),
                "position_value": round(current_value, 2),
                "cash": round(cash, 2) if shares == 0 else 0,
            })
            prev_value = current_value

        final_value = cash
        return self._finalize_result(
            stock_code, stock_name, start_date, end_date,
            final_value, trades, equity_curve, daily_returns,
            "buy_hold"
        )

    def _backtest_rsi_mean_reversion(
        self, kline: pd.DataFrame, stock_code: str, stock_name: str
    ) -> BacktestResult:
        """RSI 均值回归策略：RSI < 30 超卖买入，RSI > 70 超买卖出"""
        kline = self._calc_indicators(kline)
        cash = self.capital
        position = 0
        trades = []
        equity_curve = []
        daily_returns = []
        prev_value = cash
        start_date = kline.iloc[0]["date"].strftime("%Y-%m-%d") if len(kline) > 0 else ""
        end_date = kline.iloc[-1]["date"].strftime("%Y-%m-%d") if len(kline) > 0 else ""

        for _, row in kline.iterrows():
            date_str = row["date"].strftime("%Y-%m-%d")
            close = float(row["close"])
            rsi = row.get("rsi", 50)

            if pd.isna(rsi):
                continue

            # 超卖买入
            if rsi < 30 and position == 0:
                buy_price = close * (1 + self.slippage)
                shares = int(cash / buy_price / 100) * 100
                if shares > 0:
                    cost = shares * buy_price
                    commission = cost * self.commission
                    cash -= (cost + commission)
                    position = shares
                    trades.append(TradeRecord(
                        date=date_str, action="buy", price=buy_price,
                        shares=shares, value=cost, commission=commission,
                        reason=f"RSI超卖({rsi:.1f})买入"
                    ))
            # 超买卖出
            elif rsi > 70 and position > 0:
                sell_price = close * (1 - self.slippage)
                value = position * sell_price
                commission = value * self.commission
                cash += (value - commission)
                trades.append(TradeRecord(
                    date=date_str, action="sell", price=sell_price,
                    shares=position, value=value, commission=commission,
                    reason=f"RSI超买({rsi:.1f})卖出"
                ))
                position = 0

            current_value = cash + position * close
            daily_return = (current_value - prev_value) / prev_value if prev_value > 0 else 0
            daily_returns.append(daily_return)
            equity_curve.append({
                "date": date_str, "value": round(current_value, 2),
                "position_value": round(position * close, 2), "cash": round(cash, 2),
            })
            prev_value = current_value

        if position > 0:
            last_close = float(kline.iloc[-1]["close"])
            sell_price = last_close * (1 - self.slippage)
            value = position * sell_price
            commission = value * self.commission
            cash += (value - commission)
            trades.append(TradeRecord(
                date=kline.iloc[-1]["date"].strftime("%Y-%m-%d"),
                action="sell", price=sell_price, shares=position,
                value=value, commission=commission, reason="回测结束平仓"
            ))
            position = 0

        return self._finalize_result(
            stock_code, stock_name, start_date, end_date,
            cash, trades, equity_curve, daily_returns, "rsi_mean_reversion"
        )

    def _backtest_bollinger_breakout(
        self, kline: pd.DataFrame, stock_code: str, stock_name: str
    ) -> BacktestResult:
        """布林带突破策略：价格突破上轨买入，跌破中轨卖出"""
        kline = self._calc_indicators(kline)
        kline["ma5"] = kline["close"].rolling(5).mean()
        kline["ma20"] = kline["close"].rolling(20).mean()
        cash = self.capital
        position = 0
        trades = []
        equity_curve = []
        daily_returns = []
        prev_value = cash
        start_date = kline.iloc[0]["date"].strftime("%Y-%m-%d") if len(kline) > 0 else ""
        end_date = kline.iloc[-1]["date"].strftime("%Y-%m-%d") if len(kline) > 0 else ""

        for _, row in kline.iterrows():
            date_str = row["date"].strftime("%Y-%m-%d")
            close = float(row["close"])
            bb_upper = row.get("bb_upper", None)
            bb_mid = row.get("bb_mid", None)
            bb_width = row.get("bb_width", 0.1)
            ma5 = row.get("ma5", close)

            if pd.isna(bb_upper) or pd.isna(bb_mid):
                continue

            # 放量突破上轨买入（布林带宽 > 5% 避免窄幅）
            volume_confirm = row.get("volume", 0) > row.get("vol_ma5", 0) if not pd.isna(row.get("vol_ma5")) else True
            if close > bb_upper and ma5 > bb_mid and bb_width > 0.05 and volume_confirm and position == 0:
                buy_price = close * (1 + self.slippage)
                shares = int(cash / buy_price / 100) * 100
                if shares > 0:
                    cost = shares * buy_price
                    commission = cost * self.commission
                    cash -= (cost + commission)
                    position = shares
                    trades.append(TradeRecord(
                        date=date_str, action="buy", price=buy_price,
                        shares=shares, value=cost, commission=commission,
                        reason=f"布林突破上轨(带宽{bb_width:.1%})买入"
                    ))
            # 跌破中轨卖出
            elif close < bb_mid and position > 0:
                sell_price = close * (1 - self.slippage)
                value = position * sell_price
                commission = value * self.commission
                cash += (value - commission)
                trades.append(TradeRecord(
                    date=date_str, action="sell", price=sell_price,
                    shares=position, value=value, commission=commission,
                    reason="跌破布林中轨卖出"
                ))
                position = 0

            current_value = cash + position * close
            daily_return = (current_value - prev_value) / prev_value if prev_value > 0 else 0
            daily_returns.append(daily_return)
            equity_curve.append({
                "date": date_str, "value": round(current_value, 2),
                "position_value": round(position * close, 2), "cash": round(cash, 2),
            })
            prev_value = current_value

        if position > 0:
            last_close = float(kline.iloc[-1]["close"])
            sell_price = last_close * (1 - self.slippage)
            value = position * sell_price
            commission = value * self.commission
            cash += (value - commission)
            trades.append(TradeRecord(
                date=kline.iloc[-1]["date"].strftime("%Y-%m-%d"),
                action="sell", price=sell_price, shares=position,
                value=value, commission=commission, reason="回测结束平仓"
            ))
            position = 0

        return self._finalize_result(
            stock_code, stock_name, start_date, end_date,
            cash, trades, equity_curve, daily_returns, "bollinger_breakout"
        )

    def _backtest_momentum(
        self, kline: pd.DataFrame, stock_code: str, stock_name: str
    ) -> BacktestResult:
        """动量策略：动量 > 0 且均线多头买入，动量转负或死叉卖出"""
        kline = self._calc_indicators(kline)
        kline["ma5"] = kline["close"].rolling(5).mean()
        kline["ma20"] = kline["close"].rolling(20).mean()
        cash = self.capital
        position = 0
        trades = []
        equity_curve = []
        daily_returns = []
        prev_value = cash
        start_date = kline.iloc[0]["date"].strftime("%Y-%m-%d") if len(kline) > 0 else ""
        end_date = kline.iloc[-1]["date"].strftime("%Y-%m-%d") if len(kline) > 0 else ""

        for _, row in kline.iterrows():
            date_str = row["date"].strftime("%Y-%m-%d")
            close = float(row["close"])
            momentum = row.get("momentum", 0)
            ma5 = row.get("ma5", close)
            ma20 = row.get("ma20", close)
            vol_confirm = row.get("volume", 0) > row.get("vol_ma5", 0) if not pd.isna(row.get("vol_ma5")) else True

            if pd.isna(momentum) or pd.isna(ma5) or pd.isna(ma20):
                continue

            ma_bullish = ma5 > ma20
            # 动量转正 + 均线多头 + 量增 买入
            if momentum > 0.02 and ma_bullish and vol_confirm and position == 0:
                buy_price = close * (1 + self.slippage)
                shares = int(cash / buy_price / 100) * 100
                if shares > 0:
                    cost = shares * buy_price
                    commission = cost * self.commission
                    cash -= (cost + commission)
                    position = shares
                    trades.append(TradeRecord(
                        date=date_str, action="buy", price=buy_price,
                        shares=shares, value=cost, commission=commission,
                        reason=f"动量+{momentum:.1%}均线多头买入"
                    ))
            # 动量转负 或 死叉 卖出
            elif (momentum < -0.01 or (ma5 < ma20 and position > 0)) and position > 0:
                sell_price = close * (1 - self.slippage)
                value = position * sell_price
                commission = value * self.commission
                cash += (value - commission)
                trades.append(TradeRecord(
                    date=date_str, action="sell", price=sell_price,
                    shares=position, value=value, commission=commission,
                    reason=f"动量{momentum:.1%}" + ("死叉" if ma5 < ma20 else "") + "卖出"
                ))
                position = 0

            current_value = cash + position * close
            daily_return = (current_value - prev_value) / prev_value if prev_value > 0 else 0
            daily_returns.append(daily_return)
            equity_curve.append({
                "date": date_str, "value": round(current_value, 2),
                "position_value": round(position * close, 2), "cash": round(cash, 2),
            })
            prev_value = current_value

        if position > 0:
            last_close = float(kline.iloc[-1]["close"])
            sell_price = last_close * (1 - self.slippage)
            value = position * sell_price
            commission = value * self.commission
            cash += (value - commission)
            trades.append(TradeRecord(
                date=kline.iloc[-1]["date"].strftime("%Y-%m-%d"),
                action="sell", price=sell_price, shares=position,
                value=value, commission=commission, reason="回测结束平仓"
            ))
            position = 0

        return self._finalize_result(
            stock_code, stock_name, start_date, end_date,
            cash, trades, equity_curve, daily_returns, "momentum"
        )

    def _finalize_result(
        self,
        stock_code: str,
        stock_name: str,
        start_date: str,
        end_date: str,
        final_value: float,
        trades: List[TradeRecord],
        equity_curve: List[Dict],
        daily_returns: List[float],
        strategy: str,
    ) -> BacktestResult:
        """计算并返回最终结果"""
        total_return = (final_value - self.capital) / self.capital * 100

        # 年化收益率
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d")
            years = max((end - start).days / 365.0, 1 / 365.0)
            annual_return = ((1 + total_return / 100) ** (1 / years) - 1) * 100
        except Exception:
            annual_return = total_return

        # 最大回撤
        max_dd = 0
        peak = -float("inf")
        values = [e["value"] for e in equity_curve]
        for v in values:
            if v > peak:
                peak = v
            dd = (peak - v) / peak * 100
            if dd > max_dd:
                max_dd = dd

        # 夏普比率
        if len(daily_returns) > 1:
            returns_arr = np.array(daily_returns)
            excess_returns = returns_arr - 0.0  # 无风险利率设为0
            sharpe = np.mean(excess_returns) / (np.std(excess_returns) + 1e-10) * np.sqrt(252)
        else:
            sharpe = 0

        # 交易统计
        buy_trades = [t for t in trades if t.action == "buy"]
        sell_trades = [t for t in trades if t.action == "sell"]
        total_trades = len(buy_trades)

        win_trades = 0
        total_profit = 0
        total_loss = 0
        for i in range(min(len(buy_trades), len(sell_trades))):
            profit = sell_trades[i].value - buy_trades[i].value
            if profit > 0:
                win_trades += 1
                total_profit += profit
            else:
                total_loss += abs(profit)

        win_rate = win_trades / total_trades * 100 if total_trades > 0 else 0
        profit_factor = total_profit / total_loss if total_loss > 0 else float("inf")

        return BacktestResult(
            stock_code=stock_code,
            stock_name=stock_name or stock_code,
            strategy=strategy,
            start_date=start_date,
            end_date=end_date,
            initial_capital=self.capital,
            final_value=round(final_value, 2),
            total_return=round(total_return, 2),
            annual_return=round(annual_return, 2),
            max_drawdown=round(max_dd, 2),
            sharpe_ratio=round(sharpe, 2),
            total_trades=total_trades,
            win_rate=round(win_rate, 2),
            profit_factor=round(profit_factor, 2) if profit_factor != float("inf") else float("inf"),
            trades=trades,
            equity_curve=equity_curve,
            daily_returns=daily_returns,
        )


# ======================================================================
# 批量回测
# ======================================================================

def run_batch_backtest(
    stock_codes: List[str],
    stock_names: Dict[str, str] = None,
    strategy: str = "sentiment_only",
    capital: float = DEFAULT_START_CAPITAL,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> List[BacktestResult]:
    """
    批量回测多只股票

    Args:
        stock_codes: 股票代码列表
        stock_names: 股票名称字典 {code: name}
        strategy: 策略名称
        capital: 初始资金
        lookback_days: 回溯天数

    Returns:
        List[BacktestResult]: 回测结果列表
    """
    engine = BacktestEngine(capital=capital)
    results = []
    stock_names = stock_names or {}

    for code in tqdm(stock_codes, desc=f"批量回测[{strategy}]", unit="只"):
        try:
            result = engine.run_single(
                stock_code=code,
                stock_name=stock_names.get(code, ""),
                strategy=strategy,
                lookback_days=lookback_days,
            )
            results.append(result)
        except Exception as e:
            print(f"  ⚠️ {code} 回测失败: {e}")
        time.sleep(0.5)  # 避免请求过快

    return results


# ======================================================================
# ✨ 新增: 网格搜索参数优化
# ======================================================================

def grid_search_sentiment_threshold(
    stock_code: str,
    stock_name: str = "",
    capital: float = DEFAULT_START_CAPITAL,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    thresholds: Optional[List[float]] = None,
) -> Dict:
    """
    对纯情绪策略的买入/卖出阈值进行网格搜索优化
    """
    if thresholds is None:
        thresholds = [0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7]

    from core.data_fetcher import get_kline_data, get_stock_news
    from core.sentiment import analyze_stock_sentiment

    kline = get_kline_data(stock_code, days=lookback_days + 30)
    if kline is None or len(kline) < 20:
        return {"error": "K线数据不足"}

    news_list = get_stock_news(stock_code, days=lookback_days)
    sentiment_result = analyze_stock_sentiment(news_list)

    matrix = []
    best_return = -float("inf")
    best_threshold = 0.5
    best_result = None

    for buy_th in tqdm(thresholds, desc="网格搜索", unit="组"):
        engine = BacktestEngine(capital=capital)
        try:
            sentiment_signals = engine._align_sentiment_to_dates(kline, sentiment_result, lookback_days)
            result = engine._backtest_sentiment_only(kline, sentiment_signals, stock_code, stock_name)
            composite = result.total_return * 0.4 - result.max_drawdown * 0.3 + result.sharpe_ratio * 5
            matrix.append({"buy_threshold": round(buy_th, 2), "total_return": result.total_return,
                          "sharpe": result.sharpe_ratio, "max_dd": result.max_drawdown,
                          "win_rate": result.win_rate, "trades": result.total_trades, "composite": round(composite, 2)})
            if composite > best_return:
                best_return = composite
                best_threshold = buy_th
                best_result = result
        except Exception as e:
            matrix.append({"buy_threshold": round(buy_th, 2), "error": str(e)})
        time.sleep(0.2)

    return {"stock_code": stock_code, "stock_name": stock_name,
            "best_threshold": round(best_threshold, 2), "best_result": best_result,
            "matrix": sorted(matrix, key=lambda m: m.get("total_return", -999), reverse=True)}


def grid_search_ma_params(
    stock_code: str,
    stock_name: str = "",
    capital: float = DEFAULT_START_CAPITAL,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    ma_shorts: Optional[List[int]] = None,
    ma_longs: Optional[List[int]] = None,
) -> Dict:
    """对情绪+均线策略的均线周期进行网格搜索"""
    if ma_shorts is None:
        ma_shorts = [3, 5, 7, 10]
    if ma_longs is None:
        ma_longs = [15, 20, 25, 30]

    from core.data_fetcher import get_kline_data, get_stock_news
    from core.sentiment import analyze_stock_sentiment

    kline = get_kline_data(stock_code, days=lookback_days + 30)
    if kline is None or len(kline) < 20:
        return {"error": "K线数据不足"}

    news_list = get_stock_news(stock_code, days=lookback_days)
    sentiment_result = analyze_stock_sentiment(news_list)
    engine = BacktestEngine(capital=capital)
    sentiment_signals = engine._align_sentiment_to_dates(kline, sentiment_result, lookback_days)

    matrix = []
    best_return = -float("inf")
    best_params = (5, 20)

    for ms in tqdm(ma_shorts, desc="MA网格搜索", unit="短"):
        for ml in ma_longs:
            if ml <= ms:
                continue
            try:
                kline_cp = kline.copy()
                kline_cp["ma5_tmp"] = kline_cp["close"].rolling(ms).mean()
                kline_cp["ma20_tmp"] = kline_cp["close"].rolling(ml).mean()
                kline_cp["ma5"] = kline_cp["ma5_tmp"]
                kline_cp["ma20"] = kline_cp["ma20_tmp"]
                result = engine._backtest_sentiment_ma(kline_cp, sentiment_signals, stock_code, stock_name)
                composite = result.total_return * 0.4 - result.max_drawdown * 0.3 + result.sharpe_ratio * 5
                matrix.append({"ma_short": ms, "ma_long": ml, "total_return": result.total_return,
                              "sharpe": result.sharpe_ratio, "max_dd": result.max_drawdown,
                              "composite": round(composite, 2)})
                if composite > best_return:
                    best_return = composite
                    best_params = (ms, ml)
            except Exception as e:
                matrix.append({"ma_short": ms, "ma_long": ml, "error": str(e)})
            time.sleep(0.1)

    return {"stock_code": stock_code, "stock_name": stock_name,
            "best_ma_short": best_params[0], "best_ma_long": best_params[1],
            "matrix": sorted(matrix, key=lambda m: m.get("composite", -999), reverse=True)}


def compare_strategies(
    stock_code: str,
    stock_name: str = "",
    capital: float = DEFAULT_START_CAPITAL,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> Dict[str, BacktestResult]:
    """
    对比多种策略在单只股票上的表现

    Returns:
        Dict[str, BacktestResult]: {策略名: 结果}
    """
    strategies = ["buy_hold", "sentiment_only", "sentiment_ma",
                  "rsi_mean_reversion", "bollinger_breakout", "momentum"]
    results = {}

    for strategy in strategies:
        engine = BacktestEngine(capital=capital)
        try:
            result = engine.run_single(
                stock_code=stock_code,
                stock_name=stock_name,
                strategy=strategy,
                lookback_days=lookback_days,
            )
            results[strategy] = result
            print(f"  ✅ {strategy}: 收益{result.total_return:+.2f}%, 最大回撤{result.max_drawdown:.2f}%")
        except Exception as e:
            print(f"  ⚠️ {strategy} 回测失败: {e}")
        time.sleep(0.3)

    return results
