#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
市场情绪分析与量化回测系统 (SentimentQuant)
=============================================================================

一站式A股市场情绪分析与量化回测工具

功能概览:
  1. 单只股票情绪分析     - 输入股票代码，获取多维度新闻情感分析 + 交互式HTML报告
  2. 多只股票批量分析     - 指定股票列表，批量生成情绪报告
  3. 回测策略对比         - 在单只股票上对比多种策略绩效
  4. 全市场选股回测       - 自动选择Top N只股票执行回测
  5. 查看历史报告         - 查看已生成的HTML报告

技术特色:
  - 无需API Key：使用本地 SnowNLP 进行中文情感分析
  - 全交互式HTML报告：Plotly 驱动的科技风可视报告
  - 智能容错：3次指数退避重试 + 多接口备选
  - 进度监控：tqdm进度条实时显示批量处理进度

=============================================================================
使用方法:
  python main.py

=============================================================================
"""

# ======================================================================
# 编码修复：Windows 控制台默认 GBK，无法输出 emoji，强制 UTF-8
# ======================================================================
import sys
import io

if sys.platform == "win32":
    # 重新包装 stdout/stderr，遇到无法编码的字符用 ? 替代，避免崩溃
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
import sys
import time
import random
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
import numpy as np

# 确保项目根目录在sys.path中
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import REPORT_DIR, DEFAULT_LOOKBACK_DAYS
from core.data_fetcher import (
    search_stocks, get_stock_news, get_stock_by_code,
    get_all_stocks, get_kline_data, get_real_time_quote,
    get_market_index, get_fund_flow, get_company_announcements,
)
from core.sentiment import analyze_stock_sentiment
from core.backtest import BacktestEngine, run_batch_backtest, compare_strategies
from core.backtest import grid_search_sentiment_threshold, grid_search_ma_params
from visualization.report import ReportGenerator


# ======================================================================
# 界面工具
# ======================================================================

def clear_screen():
    """清屏"""
    print("\033[2J\033[H", end="")


def print_header():
    """打印系统标题"""
    print("""
╔══════════════════════════════════════════════════════════════╗
║     📊 市场情绪分析与量化回测系统 v2.0                       ║
║     Sentiment-Based Quantitative Analysis System             ║
╚══════════════════════════════════════════════════════════════╝
    """)


def print_menu():
    """打印主菜单"""
    menu_items = [
        ("1", "🔍 单只股票情绪分析", "输入股票代码，获取情感分析+HTML报告"),
        ("2", "📊 多只股票批量分析", "指定多条股票，批量生成情绪报告"),
        ("3", "🔄 多策略回测对比", "在单只股票上对比多种策略绩效"),
        ("4", "⚡ 批量选股回测", "自动选Top N股票执行批量回测"),
        ("5", "📁 查看历史报告", "浏览已生成的HTML报告"),
        ("6", "ℹ️  系统说明", "了解系统工作原理和用法"),
        ("0", "🚪 退出系统", ""),
    ]
    for key, title, desc in menu_items:
        print(f"   {key}. {title}")
        if desc:
            print(f"      {desc}")
        print()


def print_progress_bar(iteration, total, prefix="", suffix="", length=40):
    """打印简易进度条"""
    percent = f"{100 * (iteration / float(total)):.1f}"
    filled = int(length * iteration // total)
    bar = "█" * filled + "░" * (length - filled)
    print(f"\r  {prefix} |{bar}| {percent}% {suffix}", end="")
    if iteration == total:
        print()


def ask_choice(prompt: str, valid_options: List[str]) -> str:
    """询问用户选择"""
    while True:
        choice = input(f"\n  {prompt} ").strip()
        if choice in valid_options:
            return choice
        print(f"  ⚠️ 请输入 {', '.join(valid_options)} 中的一个")


def ask_input(prompt: str, default: str = "") -> str:
    """询问用户输入"""
    if default:
        result = input(f"\n  {prompt} [默认: {default}]: ").strip()
        return result if result else default
    return input(f"\n  {prompt}: ").strip()


def ask_int(prompt: str, default: int = None, min_val: int = None, max_val: int = None) -> int:
    """询问整数输入"""
    while True:
        default_str = f" [默认: {default}]" if default is not None else ""
        raw = input(f"\n  {prompt}{default_str}: ").strip()
        if not raw and default is not None:
            return default
        try:
            val = int(raw)
            if min_val is not None and val < min_val:
                print(f"  ⚠️ 最小值: {min_val}")
                continue
            if max_val is not None and val > max_val:
                print(f"  ⚠️ 最大值: {max_val}")
                continue
            return val
        except ValueError:
            print("  ⚠️ 请输入有效数字")


def wait_for_enter():
    """等待用户按回车继续"""
    input("\n  ⏎ 按回车键继续...")


# ======================================================================
# 功能模块
# ======================================================================

def single_stock_analysis():
    """功能1: 单只股票情绪分析"""
    clear_screen()
    print_header()
    print("  ── 单只股票情绪分析 ──\n")

    # 1. 搜索股票
    while True:
        query = ask_input("请输入股票名称或代码 (输入q返回)").strip()
        if query.lower() == "q":
            return

        results = search_stocks(query)
        if not results:
            print("  ⚠️ 未找到匹配的股票，请重新输入")
            continue

        print(f"\n  ✅ 找到 {len(results)} 只匹配股票:")
        for i, stock in enumerate(results[:10]):
            print(f"     {i+1}. {stock['name']} ({stock['code']})")

        if len(results) == 1:
            selected = results[0]
            print(f"\n  → 自动选择: {selected['name']}({selected['code']})")
        else:
            idx = ask_int(f"请选择 (1-{min(len(results), 10)})", default=1,
                         min_val=1, max_val=min(len(results), 10))
            selected = results[idx - 1]

        print(f"\n  📌 选中: {selected['name']}({selected['code']})")
        confirm = ask_input("确认？(y/n)").lower()
        if confirm in ("y", "yes", ""):
            break

    stock_code = selected["code"]
    stock_name = selected["name"]

    # 2. 获取参数
    days = ask_int("分析最近几天的新闻", default=DEFAULT_LOOKBACK_DAYS, min_val=1, max_val=30)
    max_news = ask_int("最多分析新闻条数", default=15, min_val=5, max_val=50)

    # 3. 获取市场行情
    print("\n  📡 获取大盘行情...")
    market = get_market_index()
    if market:
        print(f"     上证指数: {market.get('上证指数', {}).get('price', 'N/A')}  "
              f"({'涨' if market.get('上证指数', {}).get('pct_change', 0) > 0 else '跌'}"
              f"{abs(market.get('上证指数', {}).get('pct_change', 0)):.2f}%)")
        print(f"     深证成指: {market.get('深证成指', {}).get('price', 'N/A')}  "
              f"({'涨' if market.get('深证成指', {}).get('pct_change', 0) > 0 else '跌'}"
              f"{abs(market.get('深证成指', {}).get('pct_change', 0)):.2f}%)")

    # 4. 获取行情
    print(f"\n  📡 获取 {stock_name}({stock_code}) 实时行情...")
    quote = get_real_time_quote(stock_code)
    if quote:
        print(f"     最新价: {quote['price']:.2f}  "
              f"涨跌幅: {quote['pct_change']:+.2f}%  "
              f"换手率: {quote['turnover']:.2f}%  "
              f"PE: {quote['pe'] or 'N/A'}")

    # 5. 获取新闻并分析
    print(f"\n  📰 获取新闻（最近{days}天，最多{max_news}条）...")
    news_list = get_stock_news(stock_code, days=days, max_news=max_news)
    print(f"  ✅ 获取到 {len(news_list)} 条新闻")

    if news_list:
        print(f"\n  🤖 正在进行情感分析 (本地SnowNLP，无需API)...")
        from core.sentiment import SentimentAnalyzer
        analyzer = SentimentAnalyzer()
        sentiment = analyzer.analyze(news_list)

        score = sentiment["overall_sentiment"]["score"]
        label = sentiment["overall_sentiment"]["label"]
        conf = sentiment["overall_sentiment"]["confidence_index"]
        print(f"  ✅ 分析完成! 得分: {score:.2f} | 标签: {label} | 置信度: {conf:.2f}")

        # 6. 生成HTML报告
        print(f"\n  🎨 生成交互式HTML报告...")
        # 获取K线数据用于叠加图
        kline_data = None
        try:
            kline_data = get_kline_data(stock_code, days=days + 10)
        except Exception:
            pass

        report_gen = ReportGenerator()
        fund_flow = get_fund_flow(stock_code)
        announcements = get_company_announcements(stock_code, days=days)
        report_path = report_gen.generate_sentiment_report(
            stock_code=stock_code,
            stock_name=stock_name,
            sentiment_result=sentiment,
            news_list=news_list,
            kline_data=kline_data,
            quote=quote,
            market=market,
            fund_flow=fund_flow,
            announcements=announcements,
        )
        print(f"\n  ✅ 报告已生成!")
        print(f"  📁 文件路径: {report_path}")

        # 7. 显示摘要
        print(f"\n  ── 分析摘要 ──")
        print(f"     综合情感得分: {score*100:.1f}%")
        print(f"     情感标签: {label}")
        print(f"     置信度: {conf*100:.1f}%")
        print(f"     情感总结: {sentiment['overall_sentiment']['summary']}")
        print(f"     趋势预测: {sentiment['time_analysis']['trend_prediction'][:50]}...")

        # 8. 询问是否打开
        open_choice = ask_input("是否在浏览器中打开报告？(y/n)").lower()
        if open_choice in ("y", "yes"):
            import webbrowser
            webbrowser.open(f"file://{report_path}")
            print("  ✅ 已打开浏览器")
    else:
        print("  ⚠️ 未获取到新闻，无法进行分析")

    wait_for_enter()


def batch_analysis():
    """功能2: 多只股票批量分析"""
    clear_screen()
    print_header()
    print("  ── 多只股票批量情绪分析 ──\n")

    print("  请选择输入方式:")
    print("     1. 手动输入股票代码（逗号分隔）")
    print("     2. 从文件读取（每行一个代码）")
    mode = ask_choice("请选择 [1/2]:", ["1", "2"])

    stocks = []
    if mode == "1":
        raw = ask_input("请输入股票代码（逗号或空格分隔）")
        codes = [c.strip() for c in raw.replace("，", ",").replace(" ", ",").split(",") if c.strip()]
        for code in codes:
            info = get_stock_by_code(code)
            if info:
                stocks.append(info)
            else:
                print(f"  ⚠️ 未找到 {code}，跳过")
    else:
        # 从文件读取
        file_path = ask_input("请输入文件路径")
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    code = line.strip()
                    if code:
                        info = get_stock_by_code(code)
                        if info:
                            stocks.append(info)
        except Exception as e:
            print(f"  ❌ 读取文件失败: {e}")
            wait_for_enter()
            return

    if not stocks:
        print("  ⚠️ 没有有效的股票")
        wait_for_enter()
        return

    print(f"\n  ✅ 共 {len(stocks)} 只股票:")
    for s in stocks[:10]:
        print(f"     {s['name']}({s['code']})")
    if len(stocks) > 10:
        print(f"     ... 还有 {len(stocks) - 10} 只")

    confirm = ask_input("\n确认开始分析？(y/n)").lower()
    if confirm not in ("y", "yes"):
        return

    days = ask_int("分析最近几天的新闻", default=DEFAULT_LOOKBACK_DAYS, min_val=1, max_val=30)
    max_news = ask_int("每只股票最多新闻数", default=10, min_val=5, max_val=30)

    print(f"\n  ⚡ 开始批量分析 {len(stocks)} 只股票...\n")

    from tqdm import tqdm
    from core.data_fetcher import batch_get_news
    from core.sentiment import SentimentAnalyzer
    report_gen = ReportGenerator()

    results = []
    news_map = batch_get_news(
        [s["code"] for s in stocks],
        days=days, max_news=max_news
    )

    for stock in tqdm(stocks, desc="情感分析", unit="只"):
        code = stock["code"]
        news = news_map.get(code, [])
        if news:
            analyzer = SentimentAnalyzer()
            sentiment = analyzer.analyze(news)
            results.append((stock, news, sentiment))

    print(f"\n  ✅ 完成 {len(results)} 只股票的情感分析")

    # 生成汇总报告
    if results:
        print("\n  🎨 生成汇总报告...")

        # 生成每个股票的报告
        report_paths = []
        for stock, news, sentiment in results:
            path = report_gen.generate_sentiment_report(
                stock_code=stock["code"],
                stock_name=stock["name"],
                sentiment_result=sentiment,
                news_list=news,
            )
            report_paths.append(path)

        # 显示结果排名
        print(f"\n  ── 情绪排名 Top 5 ──")
        sorted_results = sorted(results,
                               key=lambda x: x[2]["overall_sentiment"]["score"],
                               reverse=True)
        for i, (stock, _, sentiment) in enumerate(sorted_results[:5]):
            score = sentiment["overall_sentiment"]["score"]
            label = sentiment["overall_sentiment"]["label"]
            print(f"     {i+1}. {stock['name']}({stock['code']}): {score*100:.1f}% ({label})")

        print(f"\n  📁 共生成 {len(report_paths)} 份报告，保存在: {REPORT_DIR}")
    else:
        print("  ⚠️ 所有股票均分析失败")

    wait_for_enter()


def strategy_comparison():
    """功能3: 多策略回测对比"""
    clear_screen()
    print_header()
    print("  ── 多策略回测对比 ──\n")

    # 搜索股票
    query = ask_input("请输入股票名称或代码")
    results = search_stocks(query)
    if not results:
        print("  ⚠️ 未找到匹配的股票")
        wait_for_enter()
        return

    print(f"\n  ✅ 找到 {len(results)} 只:")
    for i, s in enumerate(results[:10]):
        print(f"     {i+1}. {s['name']}({s['code']})")

    idx = ask_int(f"请选择 (1-{min(len(results), 10)})", default=1,
                 min_val=1, max_val=min(len(results), 10))
    stock = results[idx - 1]
    print(f"\n  📌 {stock['name']}({stock['code']})")

    capital = ask_int("初始资金", default=100000, min_val=10000)
    days = ask_int("回测天数", default=60, min_val=20, max_val=365)

    print(f"\n  ⚡ 开始在 {stock['name']}({stock['code']}) 上对比策略...\n")
    print("  将运行以下策略:")
    print("    1. 买入持有 (基准)")
    print("    2. 纯情绪策略 (新闻情绪驱动)")
    print("    3. 情绪+均线过滤")
    print()

    from core.backtest import compare_strategies
    results = compare_strategies(
        stock_code=stock["code"],
        stock_name=stock["name"],
        capital=capital,
        lookback_days=days,
    )

    # 生成报告
    if results:
        print("\n  🎨 生成策略对比报告...")
        report_gen = ReportGenerator()
        report_path = report_gen.generate_single_backtest_report(
            list(results.values())[0]
        )
        # 生成一个完整对比报告
        all_results = list(results.values())

        # 生成综合对比报告
        from core.backtest import BacktestResult

        report_path = report_gen.generate_backtest_report(
            results=all_results,
            stock_name_map={stock["code"]: stock["name"]},
        )
        print(f"\n  ✅ 对比报告已生成: {report_path}")

        # 显示对比结果
        print(f"\n  ── 策略对比结果 ──")
        print(f"  {'策略':<16} {'总收益':<10} {'年化收益':<12} {'最大回撤':<10} {'夏普比率':<10} {'胜率':<8}")
        print(f"  {'-'*66}")
        strategy_map = {"buy_hold": "买入持有", "sentiment_only": "纯情绪策略", "sentiment_ma": "情绪+均线"}
        for sk, r in results.items():
            name = strategy_map.get(sk, sk)
            ret_c = "#00ff88" if r.total_return >= 0 else "#ff4444"
            print(f"  {name:<16} {r.total_return:>+7.2f}%  {r.annual_return:>+7.2f}%     {r.max_drawdown:>6.2f}%    {r.sharpe_ratio:>6.2f}    {r.win_rate:>5.1f}%")

        import webbrowser
        open_choice = ask_input("\n是否在浏览器中打开报告？(y/n)").lower()
        if open_choice in ("y", "yes"):
            webbrowser.open(f"file://{report_path}")

    wait_for_enter()


def batch_backtest():
    """功能4: 批量选股回测"""
    clear_screen()
    print_header()
    print("  ── 批量选股回测 ──\n")

    print("  ⚠️ 注意：批量回测需要逐个获取新闻并分析")
    print('     建议先使用"中等规模回测"快速验证策略\n')

    print("  请选择回测规模:")
    print("     1. 快速测试 (随机5只) - 约30秒")
    print("     2. 小规模回测 (20只) - 约3分钟")
    print("     3. 中等规模回测 (100只) - 约15分钟")
    print("     4. 完整回测 (全部A股，约5000只) - 可能数小时")
    print("     0. 自定义数量")

    scale = ask_choice("请选择 [0-4]:", ["0", "1", "2", "3", "4"])

    # 获取股票池
    print("\n  📡 加载全市场股票列表...")
    all_df = get_all_stocks()
    stocks = all_df.to_dict(orient="records")

    if scale == "1":
        count = 5
    elif scale == "2":
        count = 20
    elif scale == "3":
        count = 100
    elif scale == "4":
        count = len(stocks)
        print(f"\n  ⚠️ 完整回测将分析所有 {count} 只A股，预计耗时数小时!")
        confirm = ask_input("确认继续？(y/n)").lower()
        if confirm not in ("y", "yes"):
            return
    else:
        count = ask_int("自定义回测股票数量", default=50, min_val=1, max_val=5000)

    count = min(count, len(stocks))

    print("\n  请选择策略:")
    print("     1. 纯情绪策略 (sentiment_only)")
    print("     2. 情绪+均线 (sentiment_ma)")
    strat_choice = ask_choice("请选择 [1/2]:", ["1", "2"])
    strategy = "sentiment_only" if strat_choice == "1" else "sentiment_ma"

    capital = ask_int("每只股票初始资金", default=100000, min_val=10000)
    days = ask_int("回测天数", default=DEFAULT_LOOKBACK_DAYS, min_val=5, max_val=120)

    # 随机选择股票
    random.shuffle(stocks)
    selected_stocks = stocks[:count]
    codes = [s["code"] for s in selected_stocks]
    names = {s["code"]: s["name"] for s in selected_stocks}

    print(f"\n  ⚡ 开始批量回测: {count}只股票, 策略={strategy}")
    print(f"     初始资金: ¥{capital:,}, 回测天数: {days}天\n")

    # 批量回测
    from core.backtest import run_batch_backtest
    results = run_batch_backtest(
        stock_codes=codes,
        stock_names=names,
        strategy=strategy,
        capital=capital,
        lookback_days=days,
    )

    if results:
        print(f"\n  ✅ 回测完成! 成功: {len(results)}/{count}")

        # 生成报告
        print("\n  🎨 生成回测报告...")
        report_gen = ReportGenerator()
        report_path = report_gen.generate_backtest_report(
            results=results,
            stock_name_map=names,
        )
        print(f"\n  📁 报告已生成: {report_path}")

        # 显示汇总
        returns = [r.total_return for r in results]
        print(f"\n  ── 回测汇总 ──")
        print(f"     平均收益: {np.mean(returns):+.2f}%")
        print(f"     中位收益: {np.median(returns):+.2f}%")
        print(f"     最大收益: {max(returns):+.2f}%")
        print(f"     最小收益: {min(returns):+.2f}%")
        print(f"     盈利占比: {sum(1 for r in returns if r > 0) / len(returns) * 100:.1f}%")

        # 显示Top 5
        sorted_r = sorted(results, key=lambda r: r.total_return, reverse=True)
        print(f"\n  🏆 Top 5:")
        for i, r in enumerate(sorted_r[:5]):
            print(f"     {i+1}. {r.stock_name}({r.stock_code}): {r.total_return:+.2f}%")

        import webbrowser
        open_choice = ask_input("\n是否在浏览器中打开报告？(y/n)").lower()
        if open_choice in ("y", "yes"):
            webbrowser.open(f"file://{report_path}")
    else:
        print("  ❌ 所有股票回测均失败")

    wait_for_enter()


def show_history():
    """功能5: 查看历史报告"""
    clear_screen()
    print_header()
    print("  ── 历史报告 ──\n")

    if not REPORT_DIR.exists():
        print("  暂无报告")
        wait_for_enter()
        return

    reports = list(REPORT_DIR.glob("*.html"))
    if not reports:
        print("  暂无报告")
        wait_for_enter()
        return

    # 按修改时间排序
    reports.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    print(f"  共 {len(reports)} 份报告:\n")
    for i, path in enumerate(reports[:20]):
        size = path.stat().st_size / 1024
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        print(f"     {i+1}. {path.stem}")
        print(f"        大小: {size:.0f}KB | 时间: {mtime.strftime('%Y-%m-%d %H:%M')}")

    if len(reports) > 20:
        print(f"\n     ... 还有 {len(reports) - 20} 份")

    idx = ask_int(f"\n选择查看哪一份 (1-{min(len(reports), 20)}, 0返回)",
                 default=None, min_val=0, max_val=min(len(reports), 20))
    if idx == 0:
        return

    selected = reports[idx - 1]
    import webbrowser
    webbrowser.open(f"file://{selected}")
    print(f"  ✅ 已打开: {selected.name}")


    wait_for_enter()


def show_help():
    """功能6: 系统说明"""
    clear_screen()
    print_header()
    print("""
  ── 系统说明 ──

  📌 本系统能做什么？
     1. 输入A股股票代码，自动爬取相关新闻
     2. 使用本地AI引擎分析新闻情感倾向
     3. 生成科技风交互式HTML报告（可缩放、悬停、点击）
     4. 基于情感信号执行量化回测，验证策略有效性

  🔬 情感分析原理
     - 使用 SnowNLP (中文情感分析库) 对每条新闻打分
     - 从6个主题维度、4个来源维度进行细分
     - 计算置信度指数，评估结果可靠性
     - 关键词分析作为降级备选方案

  📊 回测策略说明
     - 买入持有: 始终持有，作为基准
     - 纯情绪策略: 情感积极→买入，情感消极→卖出
     - 情绪+均线: 情感积极 且 均线多头→买入，否则空仓

  🚀 新手快速上手
     1. 运行 python main.py
     2. 选择 [1] 单只股票情绪分析
     3. 输入股票代码（如 000001 或 "贵州茅台"）
     4. 等待分析完成，自动生成HTML报告
     5. 用浏览器打开报告，体验交互式可视化

  💡 提示
     - 首次运行需要联网下载数据
     - 所有分析均在本地完成，无需API Key
     - 建议先对小批量股票测试，再运行大规模回测

  📦 报告位置
     所有生成的HTML报告保存在:
     {REPORT_DIR}
    """)
    wait_for_enter()


# ======================================================================
# 主入口
# ======================================================================

def main():
    """主程序入口"""
    try:
        while True:
            clear_screen()
            print_header()
            print_menu()

            choice = ask_choice("请选择功能 [0-6]:",
                              ["0", "1", "2", "3", "4", "5", "6"])

            if choice == "1":
                single_stock_analysis()
            elif choice == "2":
                batch_analysis()
            elif choice == "3":
                strategy_comparison()
            elif choice == "4":
                batch_backtest()
            elif choice == "5":
                show_history()
            elif choice == "6":
                show_help()
            elif choice == "0":
                clear_screen()
                print("\n  👋 感谢使用，再见！\n")
                break

    except KeyboardInterrupt:
        print("\n\n  👋 用户中断，再见！\n")
    except Exception as e:
        print(f"\n  ❌ 系统异常: {e}")
        import traceback
        traceback.print_exc()
        wait_for_enter()


if __name__ == "__main__":
    main()
