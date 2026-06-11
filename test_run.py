#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动化测试脚本 - 测试系统各个核心模块是否正常工作
非交互式运行，用于环境验证和debug
"""
import sys
import json
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import REPORT_DIR, DATA_DIR

test_results = {"passed": [], "failed": [], "warnings": []}


def test_header(name):
    print(f"\n{'='*60}")
    print(f"  测试: {name}")
    print(f"{'='*60}")


def test_ok(name, detail=""):
    test_results["passed"].append(name)
    detail_str = f" ({detail})" if detail else ""
    print(f"  ✅ {name} 通过{detail_str}")


def test_fail(name, error=""):
    test_results["failed"].append({"name": name, "error": str(error)})
    print(f"  ❌ {name} 失败: {error}")


def test_warn(name, msg=""):
    test_results["warnings"].append({"name": name, "msg": msg})
    print(f"  ⚠️ {name}: {msg}")


# ============================
# 1. 测试基础导入
# ============================
test_header("基础模块导入")

try:
    from core.data_fetcher import (
        search_stocks, get_stock_news, get_kline_data,
        get_real_time_quote, get_market_index, get_all_stocks,
        get_fund_flow, get_company_announcements, batch_get_news,
    )
    test_ok("core.data_fetcher 导入")
except Exception as e:
    test_fail("core.data_fetcher 导入", e)

try:
    from core.sentiment import SentimentAnalyzer, analyze_stock_sentiment
    test_ok("core.sentiment 导入")
except Exception as e:
    test_fail("core.sentiment 导入", e)

try:
    from core.backtest import BacktestEngine, run_batch_backtest, compare_strategies
    test_ok("core.backtest 导入")
except Exception as e:
    test_fail("core.backtest 导入", e)

try:
    from visualization.report import ReportGenerator
    test_ok("visualization.report 导入")
except Exception as e:
    test_fail("visualization.report 导入", e)

try:
    from utils.retry import retry_with_backoff, fetch_with_fallback
    test_ok("utils.retry 导入")
except Exception as e:
    test_fail("utils.retry 导入", e)

try:
    from utils.cache import FileCache, MemoryCache
    test_ok("utils.cache 导入")
except Exception as e:
    test_fail("utils.cache 导入", e)


# ============================
# 2. 测试数据获取
# ============================
test_header("数据获取模块")

# 2.1 大盘指数
try:
    market = get_market_index()
    if market:
        index_names = list(market.keys())
        test_ok(f"大盘指数获取 ({', '.join(index_names)})")
    else:
        test_warn("大盘指数获取", "返回空数据（可能网络问题）")
except Exception as e:
    test_warn("大盘指数获取", str(e)[:100])

# 2.2 股票搜索
try:
    results = search_stocks("平安银行")
    if results:
        test_ok(f"股票搜索 (找到{len(results)}只)")
        print(f"     示例: {results[0]['name']}({results[0]['code']})")
    else:
        test_warn("股票搜索", "未找到结果")
except Exception as e:
    test_fail("股票搜索", e)

# 2.3 获取全市场股票列表
try:
    all_stocks = get_all_stocks()
    if len(all_stocks) > 0:
        test_ok(f"全市场股票列表 (共{len(all_stocks)}只)")
    else:
        test_warn("全市场股票列表", "返回空")
except Exception as e:
    test_fail("全市场股票列表", e)

# 2.4 获取单只股票新闻
try:
    news = get_stock_news("000001", days=3, max_news=10)
    if news:
        test_ok(f"股票新闻获取 (获取到{len(news)}条)")
        print(f"     示例: {news[0].get('title', '')[:50]}...")
    else:
        test_warn("股票新闻获取", "获取到0条新闻（可能股票代码无新闻数据）")
except Exception as e:
    test_fail("股票新闻获取", str(e)[:150])

# 2.5 获取K线数据
try:
    kline = get_kline_data("000001", days=30)
    if kline is not None and len(kline) > 0:
        test_ok(f"K线数据获取 ({len(kline)}条)")
    else:
        test_warn("K线数据获取", "返回空")
except Exception as e:
    test_fail("K线数据获取", str(e)[:150])

# 2.6 获取实时行情
try:
    quote = get_real_time_quote("000001")
    if quote:
        test_ok(f"实时行情获取 (价格:{quote['price']}, 涨跌:{quote['pct_change']:+.2f}%)")
    else:
        test_warn("实时行情获取", "返回空")
except Exception as e:
    test_fail("实时行情获取", str(e)[:150])

# 2.7 获取资金流向
try:
    fund = get_fund_flow("000001", days=3)
    if fund and fund.get("records"):
        test_ok(f"资金流向获取 ({len(fund['records'])}天)")
    else:
        test_warn("资金流向获取", "返回空或API不可用")
except Exception as e:
    test_warn("资金流向获取", str(e)[:100])


# ============================
# 3. 测试情感分析
# ============================
test_header("情感分析引擎")

try:
    # 构造模拟新闻数据
    mock_news = [
        {
            "title": "公司业绩大幅增长",
            "content": "该公司发布最新财报，营收同比增长30%，净利润创新高，多项业务取得突破性进展。",
            "publish_time": "2026-06-10 15:30:00",
            "date": "2026-06-10",
            "source": "证券时报",
            "url": "https://example.com/1",
        },
        {
            "title": "行业政策利好频出",
            "content": "国务院发布新政策，大力支持相关行业发展，预计将为公司带来新的增长机遇。",
            "publish_time": "2026-06-09 10:00:00",
            "date": "2026-06-09",
            "source": "新华网",
            "url": "https://example.com/2",
        },
        {
            "title": "机构看好后市表现",
            "content": "多家券商发布研报，给予买入评级，认为公司估值处于历史低位，具有较高安全边际。",
            "publish_time": "2026-06-08 09:00:00",
            "date": "2026-06-08",
            "source": "财经日报",
            "url": "https://example.com/3",
        },
        {
            "title": "市场波动加剧",
            "content": "近期市场整体表现不佳，受外部环境影响，大盘指数出现回调，投资者情绪谨慎。",
            "publish_time": "2026-06-07 14:00:00",
            "date": "2026-06-07",
            "source": "金融界",
            "url": "https://example.com/4",
        },
    ]

    analyzer = SentimentAnalyzer()
    result = analyzer.analyze(mock_news)

    overall = result.get("overall_sentiment", {})
    score = overall.get("score", 0.5)
    label = overall.get("label", "未知")
    conf = overall.get("confidence_index", 0)

    test_ok(f"情感分析 (得分:{score:.2f}, 标签:{label}, 置信度:{conf:.2f})")

    # 检查所有维度
    dimensions = ["time_analysis", "topic_analysis", "source_analysis",
                  "impact_analysis", "risk_analysis"]
    missing = [d for d in dimensions if d not in result]
    if missing:
        test_warn("情感分析维度", f"缺失: {missing}")
    else:
        test_ok("情感分析多维度完整性")

    # 检查波动率指标
    vol = overall.get("volatility", 0)
    vol_label = overall.get("volatility_label", "")
    print(f"     波动率: {vol:.4f} ({vol_label}), CV: {overall.get('cv', 0):.4f}")

except Exception as e:
    test_fail("情感分析", str(e)[:200])
    traceback.print_exc()


# ============================
# 4. 测试报告生成
# ============================
test_header("HTML报告生成")

try:
    report_gen = ReportGenerator()

    # 构造模拟的分析结果
    mock_sentiment = {
        "overall_sentiment": {
            "score": 0.72,
            "label": "看好",
            "summary": "基于4条新闻分析，整体情绪看好，正面新闻占比75%",
            "market_expectation": "市场预期温和向好",
            "investor_sentiment": "65",
            "confidence_index": 0.78,
            "volatility": 0.12,
            "volatility_label": "较为一致",
            "cv": 0.15,
            "score_range": 0.30,
            "positive_ratio": 0.75,
            "negative_ratio": 0.00,
            "positive_count": 3,
            "negative_count": 0,
            "neutral_count": 1,
        },
        "time_analysis": {
            "trend": [
                {"date": "2026-06-10", "score": 0.85, "key_events": [{"title": "业绩增长", "description": "业绩大幅增长"}]},
                {"date": "2026-06-09", "score": 0.78, "key_events": [{"title": "政策利好", "description": "行业新政策"}]},
                {"date": "2026-06-08", "score": 0.68, "key_events": []},
                {"date": "2026-06-07", "score": 0.45, "key_events": []},
            ],
            "trend_prediction": "近期情感呈上升趋势，市场情绪持续改善",
        },
        "topic_analysis": {
            "financial_performance": {"score": 0.85, "summary": "财务状况良好", "key_points": ["业绩增长"]},
            "industry_policy": {"score": 0.78, "summary": "政策利好", "key_points": ["行业政策"]},
            "company_operation": {"score": 0.70, "summary": "经营稳定", "key_points": []},
            "market_competition": {"score": 0.65, "summary": "竞争优势", "key_points": []},
            "product_technology": {"score": 0.60, "summary": "技术领先", "key_points": []},
            "capital_market": {"score": 0.55, "summary": "市场关注", "key_points": []},
        },
        "source_analysis": {
            "mainstream_media": {"score": 0.80, "summary": "共2条"},
            "industry_media": {"score": 0.68, "summary": "共2条"},
            "official_announcement": {"score": 0.50, "summary": "无"},
            "self_media": {"score": 0.50, "summary": "无"},
        },
        "impact_analysis": {
            "importance_level": "中",
            "market_impact": {
                "score": 0.6,
                "duration": "中期",
                "key_factors": ["利好: 业绩增长", "利空: 市场波动"],
            },
        },
        "risk_analysis": {
            "risk_level": "低",
            "risk_factors": [],
        },
    }

    mock_news = [
        {"title": "业绩增长", "content": "营收增长30%", "publish_time": "2026-06-10", "source": "证券时报", "url": ""},
        {"title": "政策利好", "content": "行业新政策", "publish_time": "2026-06-09", "source": "新华网", "url": ""},
    ]

    mock_quote = {
        "code": "000001", "name": "平安银行", "price": 12.50,
        "change": 0.30, "pct_change": 2.46, "turnover": 0.52,
        "pe": 5.2, "pb": 0.65, "volume": 50000000, "amount": 625000000,
    }

    mock_market = {
        "上证指数": {"price": 3250.00, "change": 15.00, "pct_change": 0.46},
        "深证成指": {"price": 10500.00, "change": 30.00, "pct_change": 0.29},
    }

    mock_fund = {"main_net_avg": 0.52, "retail_net_avg": -0.18, "net_direction": "流入"}

    # 创建临时输出目录
    test_report_dir = REPORT_DIR / "test"
    test_report_dir.mkdir(parents=True, exist_ok=True)

    report_path = report_gen.generate_sentiment_report(
        stock_code="000001",
        stock_name="平安银行",
        sentiment_result=mock_sentiment,
        news_list=mock_news,
        kline_data=None,
        quote=mock_quote,
        market=mock_market,
        fund_flow=mock_fund,
        announcements=[],
        output_path=test_report_dir / "test_report.html",
    )

    if Path(report_path).exists():
        size_kb = Path(report_path).stat().st_size / 1024
        test_ok(f"HTML报告生成 ({size_kb:.0f}KB)")
    else:
        test_fail("HTML报告生成", "文件未创建")

except Exception as e:
    test_fail("HTML报告生成", str(e)[:200])
    traceback.print_exc()


# ============================
# 5. 测试回测引擎
# ============================
test_header("回测引擎（技术架构验证）")

try:
    engine = BacktestEngine(capital=100000)

    # 构造模拟K线数据
    import pandas as pd
    from datetime import datetime, timedelta

    dates = []
    price = 10.0
    n_days = 30
    for i in range(n_days):
        d = datetime(2026, 5, 1) + timedelta(days=i)
        if d.weekday() >= 5:
            continue
        dates.append(d)
        price += (0.5 - 0.3) * 0.2  # 模拟随机波动
        price = max(price, 9.0)

    mock_kline = pd.DataFrame({
        "date": dates,
        "open": [price * (0.98 + 0.04 * (i % 3)) for i in range(len(dates))],
        "close": [price * (1.0 + 0.02 * (i % 5 - 2)) for i in range(len(dates))],
        "high": [price * 1.02 for _ in range(len(dates))],
        "low": [price * 0.98 for _ in range(len(dates))],
        "volume": [10000000 + i * 100000 for i in range(len(dates))],
        "amount": [price * 5000000 for _ in range(len(dates))],
        "amplitude": [0.04 for _ in range(len(dates))],
        "pct_change": [0.01 for _ in range(len(dates))],
        "change": [0.1 for _ in range(len(dates))],
        "turnover": [0.5 for _ in range(len(dates))],
    })

    mock_kline["date"] = pd.to_datetime(mock_kline["date"])

    # 构造模拟情感信号
    mock_signals = []
    for _, row in mock_kline.iterrows():
        date_str = row["date"].strftime("%Y-%m-%d")
        score = 0.55 if row.name % 3 == 0 else (0.45 if row.name % 5 == 0 else 0.50)
        signal = "buy" if score > 0.5 else ("sell" if score < 0.5 else "hold")
        mock_signals.append({
            "date": date_str, "score": score, "signal": signal,
            "close": float(row["close"]),
        })

    # 测试买入持有策略
    result_bh = engine._backtest_buy_hold(mock_kline, "TEST01", "测试股票")
    test_ok(f"买入持有策略 (收益率:{result_bh.total_return:+.2f}%)")

    # 测试纯情绪策略
    result_s = engine._backtest_sentiment_only(mock_kline, mock_signals, "TEST01", "测试股票")
    test_ok(f"纯情绪策略 (收益率:{result_s.total_return:+.2f}%, 交易{result_s.total_trades}次)")

    # 测试情绪+均线策略
    mock_kline["ma5"] = mock_kline["close"].rolling(5).mean()
    mock_kline["ma20"] = mock_kline["close"].rolling(20).mean()
    result_ma = engine._backtest_sentiment_ma(mock_kline, mock_signals, "TEST01", "测试股票")
    test_ok(f"情绪+均线策略 (收益率:{result_ma.total_return:+.2f}%, 最大回撤:{result_ma.max_drawdown:.2f}%)")

    # 测试RSI策略
    result_rsi = engine._backtest_rsi_mean_reversion(mock_kline, "TEST01", "测试股票")
    test_ok(f"RSI策略 (收益率:{result_rsi.total_return:+.2f}%)")

    # 测试布林带策略
    result_bb = engine._backtest_bollinger_breakout(mock_kline, "TEST01", "测试股票")
    test_ok(f"布林带策略 (收益率:{result_bb.total_return:+.2f}%)")

    # 测试动量策略
    result_mom = engine._backtest_momentum(mock_kline, "TEST01", "测试股票")
    test_ok(f"动量策略 (收益率:{result_mom.total_return:+.2f}%)")

except Exception as e:
    test_fail("回测引擎", str(e)[:200])
    traceback.print_exc()


# ============================
# 汇总
# ============================
test_header("测试汇总")

passed = len(test_results["passed"])
failed = len(test_results["failed"])
warnings = len(test_results["warnings"])
total = passed + failed + warnings

print(f"\n  测试总数: {total}")
print(f"  ✅ 通过: {passed}")
print(f"  ⚠️ 警告: {warnings}")
print(f"  ❌ 失败: {failed}")

if test_results["warnings"]:
    print(f"\n  警告详情:")
    for w in test_results["warnings"]:
        print(f"    - {w['name']}: {w.get('msg', '-')}")

if test_results["failed"]:
    print(f"\n  失败详情:")
    for f in test_results["failed"]:
        print(f"    - {f['name']}: {f['error']}")

print()

# 输出JSON结果
results_json = {
    "timestamp": str(datetime.now()),
    "passed": passed,
    "failed": failed,
    "warnings": warnings,
    "details": test_results,
}
print(json.dumps(results_json, ensure_ascii=False, indent=2))

# 成功则退出0，否则1
sys.exit(1 if failed > 0 else 0)
