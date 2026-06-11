#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
SentimentQuant Mobile - Flask Web 应用
市场情绪分析与量化回测系统 移动端版本
=============================================================================
"""

import sys, os, io, json, threading, time
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from flask import Flask, render_template, request, jsonify, send_from_directory, url_for

from config import REPORT_DIR, DEFAULT_LOOKBACK_DAYS, DEFAULT_START_CAPITAL, DEFAULT_COMMISSION
from core.data_fetcher import (
    search_stocks, get_stock_news, get_stock_by_code,
    get_kline_data, get_real_time_quote, get_market_index,
    get_fund_flow, get_company_announcements, batch_get_news
)
from core.sentiment import SentimentAnalyzer
from core.backtest import compare_strategies
from visualization.report import ReportGenerator

app = Flask(__name__)

# 确保所有目录存在
REPORT_DIR.mkdir(parents=True, exist_ok=True)

sentiment_analyzer = SentimentAnalyzer()
report_generator = ReportGenerator()

# =============================================================================
# 页面路由
# =============================================================================

@app.route("/")
def index():
    """首页 - 仪表盘"""
    return render_template("index.html")


@app.route("/analyze")
def analyze_page():
    """单只股票分析页"""
    return render_template("analyze.html")


@app.route("/batch")
def batch_page():
    """批量分析页"""
    return render_template("batch.html")


@app.route("/backtest")
def backtest_page():
    """策略回测页"""
    return render_template("backtest.html")


@app.route("/reports")
def reports_page():
    """历史报告页"""
    return render_template("reports.html")


@app.route("/about")
def about_page():
    """关于页面"""
    return render_template("about.html")


# =============================================================================
# API 路由
# =============================================================================

@app.route("/api/search_stocks")
def api_search_stocks():
    """搜索股票"""
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"success": False, "error": "请输入搜索关键词"})
    try:
        results = search_stocks(q, top_n=20)
        return jsonify({"success": True, "data": results})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/quote")
def api_quote():
    """获取实时行情"""
    code = request.args.get("code", "").strip()
    if not code:
        return jsonify({"success": False, "error": "请输入股票代码"})
    try:
        quote = get_real_time_quote(code)
        if quote:
            return jsonify({"success": True, "data": quote})
        else:
            return jsonify({"success": False, "error": f"无法获取 {code} 的行情数据"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/market_index")
def api_market_index():
    """获取市场指数"""
    try:
        data = get_market_index()
        # 格式化价格和百分比，保留2位小数
        if data:
            for name, info in data.items():
                info["price"] = round(info["price"], 2)
                info["change"] = round(info["change"], 2)
                info["pct_change"] = round(info["pct_change"], 2)
        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/single_analysis", methods=["POST"])
def api_single_analysis():
    """单只股票完整分析"""
    try:
        data = request.get_json()
        stock_code = data.get("code", "").strip()
        stock_name = data.get("name", "").strip()
        days = int(data.get("days", DEFAULT_LOOKBACK_DAYS))
        max_news = int(data.get("max_news", 20))

        if not stock_code:
            return jsonify({"success": False, "error": "请输入股票代码"})

        # 获取股票信息
        if not stock_name:
            info = get_stock_by_code(stock_code)
            if info:
                stock_name = info.get("name", stock_code)

        # 获取新闻
        news_list = get_stock_news(stock_code, days=days, max_news=max_news)
        if not news_list:
            return jsonify({"success": False, "error": f"未找到 {stock_code} 的相关新闻"})

        # 情感分析
        sentiment_result = sentiment_analyzer.analyze(news_list)

        # 获取K线和行情
        kline_data = get_kline_data(stock_code, days=max(60, days))
        quote = get_real_time_quote(stock_code)
        market = get_market_index()
        fund_flow = get_fund_flow(stock_code, days=min(5, days))
        announcements = get_company_announcements(stock_code, days=days)

        # 生成报告
        report_path = report_generator.generate_sentiment_report(
            stock_code=stock_code,
            stock_name=stock_name,
            sentiment_result=sentiment_result,
            news_list=news_list,
            kline_data=kline_data,
            quote=quote,
            market=market,
            fund_flow=fund_flow,
            announcements=announcements
        )

        # 提取关键信息返回
        overall = sentiment_result.get("overall_sentiment", {})
        summary = {
            "stock_code": stock_code,
            "stock_name": stock_name,
            "score": overall.get("score", 0),
            "label": overall.get("label", "未知"),
            "summary_text": overall.get("summary", ""),
            "market_expectation": overall.get("market_expectation", ""),
            "investor_sentiment": overall.get("investor_sentiment", ""),
            "confidence": overall.get("confidence_index", 0),
            "volatility": overall.get("volatility", 0),
            "volatility_label": overall.get("volatility_label", ""),
            "positive_ratio": overall.get("positive_ratio", 0),
            "negative_ratio": overall.get("negative_ratio", 0),
            "positive_count": overall.get("positive_count", 0),
            "negative_count": overall.get("negative_count", 0),
            "neutral_count": overall.get("neutral_count", 0),
            "news_count": len(news_list),
            "risk_level": sentiment_result.get("risk_analysis", {}).get("risk_level", "未知"),
            "impact_level": sentiment_result.get("impact_analysis", {}).get("importance_level", "未知"),
            "price": quote.get("price", "--") if quote else "--",
            "pct_change": quote.get("pct_change", "--") if quote else "--",
            "report_url": f"/reports/view/{Path(report_path).name}"
        }
        return jsonify({"success": True, "data": summary})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/batch_analysis", methods=["POST"])
def api_batch_analysis():
    """批量分析"""
    try:
        data = request.get_json()
        codes_str = data.get("codes", "").strip()
        days = int(data.get("days", DEFAULT_LOOKBACK_DAYS))
        max_news = int(data.get("max_news", 10))

        if not codes_str:
            return jsonify({"success": False, "error": "请输入股票代码"})

        codes = [c.strip() for c in codes_str.replace("\n", ",").replace(" ", ",").split(",") if c.strip()]
        if not codes:
            return jsonify({"success": False, "error": "无法解析股票代码"})

        results = []
        for code in codes:
            try:
                info = get_stock_by_code(code)
                name = info.get("name", code) if info else code
                news_list = get_stock_news(code, days=days, max_news=max_news)
                if news_list:
                    sr = sentiment_analyzer.analyze(news_list)
                    overall = sr.get("overall_sentiment", {})
                    results.append({
                        "code": code,
                        "name": name,
                        "score": round(overall.get("score", 0), 3),
                        "label": overall.get("label", "未知"),
                        "news_count": len(news_list),
                        "positive_ratio": overall.get("positive_ratio", 0),
                        "confidence": overall.get("confidence_index", 0),
                    })
                else:
                    results.append({
                        "code": code, "name": name,
                        "score": 0, "label": "无数据",
                        "news_count": 0, "positive_ratio": 0, "confidence": 0
                    })
            except Exception as e:
                results.append({
                    "code": code, "name": code,
                    "score": 0, "label": f"错误: {e}",
                    "news_count": 0, "positive_ratio": 0, "confidence": 0
                })

        # 按得分排序
        results.sort(key=lambda x: x["score"], reverse=True)

        # 生成对比报告
        stocks_data = [
            {"code": r["code"], "name": r["name"],
             "sentiment_result": {"overall_sentiment": {"score": r["score"], "label": r["label"]}},
             "news_count": r["news_count"]}
            for r in results if r["news_count"] > 0
        ]

        report_path = None
        if len(stocks_data) >= 2:
            try:
                report_path = report_generator.generate_comparison_report(stocks_data)
            except:
                pass

        return jsonify({
            "success": True,
            "data": results,
            "report_url": f"/reports/view/{Path(report_path).name}" if report_path else None
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/backtest", methods=["POST"])
def api_backtest():
    """策略回测"""
    try:
        data = request.get_json()
        stock_code = data.get("code", "").strip()
        stock_name = data.get("name", "").strip()
        lookback = int(data.get("lookback", DEFAULT_LOOKBACK_DAYS))
        capital = float(data.get("capital", DEFAULT_START_CAPITAL))

        if not stock_code:
            return jsonify({"success": False, "error": "请输入股票代码"})

        if not stock_name:
            info = get_stock_by_code(stock_code)
            if info:
                stock_name = info.get("name", stock_code)

        # 六策略对比
        results = compare_strategies(
            stock_code=stock_code,
            stock_name=stock_name,
            capital=capital,
            lookback_days=lookback
        )

        # 生成报告
        all_results = list(results.values())
        report_path = report_generator.generate_backtest_report(
            results=all_results,
            stock_name_map={r.stock_code: r.stock_name for r in all_results}
        )

        # 提取摘要
        summary = []
        for strategy, result in results.items():
            summary.append({
                "strategy": strategy,
                "strategy_name": _get_strategy_name(strategy),
                "total_return": round(result.total_return, 2),
                "annual_return": round(result.annual_return, 2),
                "max_drawdown": round(result.max_drawdown, 2),
                "sharpe_ratio": round(result.sharpe_ratio, 2),
                "win_rate": round(result.win_rate, 2),
                "total_trades": result.total_trades,
                "final_value": round(result.final_value, 2),
            })

        # 找到最佳策略
        best = max(summary, key=lambda x: x["total_return"])

        return jsonify({
            "success": True,
            "data": summary,
            "best_strategy": best,
            "stock_code": stock_code,
            "stock_name": stock_name,
            "report_url": f"/reports/view/{Path(report_path).name}"
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/reports")
def api_reports():
    """获取报告列表"""
    try:
        reports = []
        if REPORT_DIR.exists():
            for f in sorted(REPORT_DIR.glob("*.html"), key=lambda x: x.stat().st_mtime, reverse=True):
                reports.append({
                    "name": f.name,
                    "size": f.stat().st_size,
                    "mtime": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
                    "url": f"/reports/view/{f.name}"
                })
        return jsonify({"success": True, "data": reports[:50]})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/reports/view/<filename>")
def view_report(filename):
    """查看报告"""
    return send_from_directory(str(REPORT_DIR), filename)


# =============================================================================
# 辅助函数
# =============================================================================

def _get_strategy_name(strategy: str) -> str:
    """策略英文名转中文名"""
    names = {
        "buy_hold": "买入持有",
        "sentiment_only": "纯情绪信号",
        "sentiment_ma": "情绪+均线",
        "rsi_mean_reversion": "RSI均值回归",
        "bollinger_breakout": "布林带突破",
        "momentum": "动量策略",
    }
    return names.get(strategy, strategy)


# =============================================================================
# 启动
# =============================================================================

if __name__ == "__main__":
    import socket
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)

    # 检查是否启用公网模式
    use_public = "--public" in sys.argv

    port = int(os.environ.get("PORT", 5000))

    print("=" * 60)
    print("  SentimentQuant Mobile - 市场情绪量化系统")
    print("=" * 60)
    print()
    print(f"  本地访问:    http://127.0.0.1:{port}")
    print(f"  局域网访问:  http://{local_ip}:{port}")

    public_url_container = [None]
    if use_public:
        print()
        print("  正在创建公网隧道...")
        try:
            from tunnel import start_public_tunnel
            # 在后台线程启动隧道，不阻塞Flask
            def tunnel_thread():
                try:
                    import subprocess, re
                    cmd = [
                        "ssh", "-o", "StrictHostKeyChecking=no",
                        "-o", "UserKnownHostsFile=/dev/null",
                        "-o", "ServerAliveInterval=30",
                        "-o", "ConnectTimeout=10",
                        "-R", f"80:localhost:{port}",
                        "nokey@localhost.run",
                    ]
                    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                    for line in proc.stdout:
                        match = re.search(r"https://([a-zA-Z0-9-]+\.lhr\.life)", line)
                        if match:
                            public_url_container[0] = match.group(0)
                            print(f"\n  *** 公网地址: {public_url_container[0]}")
                            print(f"  *** 手机随时随地可访问！")
                            break
                except Exception:
                    pass

            t = threading.Thread(target=tunnel_thread, daemon=True)
            t.start()
            print("  等待公网隧道建立...")
            time.sleep(8)
            public_url = public_url_container[0]
            if public_url:
                print(f"\n  公网地址:    {public_url}")
            else:
                print("  公网隧道正在建立中，请稍等...")
        except Exception as e:
            print(f"  公网隧道创建失败: {e}")

    print()
    print("  用手机浏览器打开地址即可使用")
    print("  按 Ctrl+C 停止服务器")
    print("=" * 60)

    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
