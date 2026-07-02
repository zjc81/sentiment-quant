#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
SentimentQuant Mobile - Flask Web App (Render Cloud Edition)
市场情绪分析与量化回测系统 移动端版本
纯 HTTP 数据源，零 akshare/pandas 依赖，适配 Render 免费 512MB
=============================================================================
"""

import sys, os, io, json, threading, time, gc, functools
from pathlib import Path
from datetime import datetime, timedelta

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from flask import Flask, render_template, request, jsonify, send_from_directory

app = Flask(__name__)

# =============================================================================
# 环境检测
# =============================================================================

IS_RENDER = os.environ.get("RENDER") == "true"

# =============================================================================
# 通用 HTTP 辅助
# =============================================================================

def _headers():
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://quote.eastmoney.com/",
    }

def _secid(code):
    code = code[-6:] if len(code) > 6 else code
    return f"{'1' if code.startswith('6') else '0'}.{code}"


# =============================================================================
# 内置轻量数据源（纯 requests，无 akshare/pandas）
# =============================================================================

def _cloud_search_stocks(query: str, top_n: int = 20):
    import requests
    try:
        url = "https://searchapi.eastmoney.com/api/suggest/get"
        params = {"input": query, "type": 14, "token": "D43BF722C8E33BDC906FB84D85E326E8", "count": str(top_n)}
        resp = requests.get(url, params=params, headers=_headers(), timeout=10)
        items = resp.json().get("QuotationCodeTable", {}).get("Data", [])
        results = [{"code": it["Code"], "name": it["Name"]} for it in items if it.get("Code") and it.get("Name")]
        if results:
            return results[:top_n]
    except Exception:
        pass
    q = query.strip().upper()
    if q.isdigit() and len(q) >= 6:
        return [{"code": q[-6:], "name": q[-6:]}]
    return []

def _cloud_get_stock_by_code(code: str):
    results = _cloud_search_stocks(code, top_n=5)
    for r in results:
        if r["code"] == code or r["code"].endswith(code[-6:]):
            return r
    clean = code.strip()[-6:]
    return {"code": clean, "name": clean} if clean.isdigit() else {"code": code, "name": code}

def _cloud_get_market_index():
    import requests
    indices = {"上证指数": "1.000001", "深证成指": "0.399001", "创业板指": "0.399006"}
    result = {}
    for name, sid in indices.items():
        try:
            url = f"https://push2.eastmoney.com/api/qt/stock/get?secid={sid}&fields=f43,f44,f45,f46,f47,f48,f50"
            resp = requests.get(url, headers=_headers(), timeout=10)
            d = resp.json().get("data", {})
            if d:
                price = d.get("f43", 0) / 100 if d.get("f43") else 0
                pre = d.get("f44", 0) / 100 if d.get("f44") else 0
                chg = price - pre
                pct = chg / pre * 100 if pre else 0
                result[name] = {"price": round(price, 2), "change": round(chg, 2), "pct_change": round(pct, 2)}
        except Exception:
            continue
    return result if result else None

def _cloud_get_real_time_quote(stock_code: str):
    """获取实时行情（云端版），主源：东方财富push2，备源：腾讯财经qt"""
    import requests, math, time

    def _sf_eastmoney(key, div=100, default=0):
        raw = d.get(key)
        if raw is None or raw == "":
            return default
        try:
            v = float(raw)
            if math.isnan(v) or math.isinf(v):
                return default
            return v / div if div else v
        except (ValueError, TypeError):
            return default

    # ---- 主源：东方财富 push2 ----
    for attempt in range(2):
        try:
            sid = _secid(stock_code)
            url = f"https://push2.eastmoney.com/api/qt/stock/get?secid={sid}&fields=f43,f44,f45,f46,f47,f48,f50,f51,f52,f55,f57,f58,f115,f117,f162,f167,f168,f169,f170,f171"
            resp = requests.get(url, headers=_headers(), timeout=10)
            d = resp.json().get("data", {})
            if d:
                price = _sf_eastmoney("f43")
                pre = _sf_eastmoney("f44")
                if price > 0:
                    chg = price - pre
                    pct = round(chg / pre * 100, 2) if pre > 0 else 0
                    result = {
                        "code": stock_code, "name": d.get("f58", ""),
                        "price": round(price, 2), "change": round(chg, 2), "pct_change": pct,
                        "volume": _sf_eastmoney("f48"), "amount": _sf_eastmoney("f50", div=0),
                        "high": round(_sf_eastmoney("f45"), 2), "low": round(_sf_eastmoney("f46"), 2),
                        "open": round(_sf_eastmoney("f47"), 2), "pre_close": round(pre, 2),
                        "turnover": _sf_eastmoney("f168"),
                        "pe": round(_sf_eastmoney("f162"), 2) if _sf_eastmoney("f162") != 0 else None,
                        "market_cap": _sf_eastmoney("f116", div=0, default=0) or _sf_eastmoney("f20", div=0, default=0),
                        "circulating_cap": _sf_eastmoney("f117", div=0, default=0) or _sf_eastmoney("f21", div=0, default=0),
                    }
                    print(f"[QUOTE] {stock_code} (来源:eastmoney): 价格={result['price']}, 涨跌幅={result['pct_change']}%")
                    return result
            print(f"[QUOTE] {stock_code} (attempt {attempt+1}): eastmoney返回空或无有效价格")
            if attempt == 0:
                time.sleep(0.5)
        except Exception as e:
            print(f"[QUOTE] {stock_code} (attempt {attempt+1}) eastmoney异常: {e}")
            if attempt == 0:
                time.sleep(0.5)

    # ---- 备源：腾讯财经 qt.gtimg.cn ----
    print(f"[QUOTE] {stock_code}: eastmoney失败，尝试备源腾讯财经...")
    try:
        code_short = stock_code[-6:]
        market_prefix = "sh" if code_short.startswith("6") else "sz"
        qt_url = f"https://qt.gtimg.cn/q={market_prefix}{code_short}"
        resp = requests.get(qt_url, headers=_headers(), timeout=10)
        # 响应格式: v_sz000001="1~平安银行~000001~10.15~..."
        raw = resp.text.strip()
        # 用 find/rfind 提取引号内容（比正则更可靠）
        start = raw.find('"')
        end = raw.rfind('"')
        if start == -1 or end == -1 or end <= start:
            print(f"[QUOTE] {stock_code}: 腾讯财经无引号: {raw[:80]}")
            return None
        parts = raw[start+1:end].split("~")
        if len(parts) < 5:
            print(f"[QUOTE] {stock_code}: 腾讯财经字段不足: {len(parts)}")
            return None
        # 字段: [0]未知, [1]名称, [2]代码, [3]当前价, [4]昨收, [5]今开, ... [7]最高, [8]最低, [6]成交量(手), [37]换手率
        name = parts[1]
        price = float(parts[3])
        pre = float(parts[4])
        if price <= 0:
            print(f"[QUOTE] {stock_code}: 腾讯财经价格无效={price}")
            return None
        chg = price - pre
        pct = round(chg / pre * 100, 2) if pre > 0 else 0

        def _safe_float(s, default=0):
            try:
                return float(s)
            except (ValueError, TypeError):
                return default

        result = {
            "code": stock_code, "name": name,
            "price": round(price, 2), "change": round(chg, 2), "pct_change": pct,
            "volume": _safe_float(parts[6]) if len(parts) > 6 else 0,
            "amount": _safe_float(parts[37]) if len(parts) > 37 else 0,
            "high": round(_safe_float(parts[33]), 2) if len(parts) > 33 else 0,
            "low": round(_safe_float(parts[34]), 2) if len(parts) > 34 else 0,
            "open": round(_safe_float(parts[5]), 2) if len(parts) > 5 else 0,
            "pre_close": round(pre, 2),
            "turnover": _safe_float(parts[38]) if len(parts) > 38 else 0,
            "pe": _safe_float(parts[39]) if len(parts) > 39 else None,
            "market_cap": _safe_float(parts[45]) if len(parts) > 45 else 0,
            "circulating_cap": _safe_float(parts[44]) if len(parts) > 44 else 0,
        }
        print(f"[QUOTE] {stock_code} (来源:tencent): 价格={result['price']}, 涨跌幅={result['pct_change']}%")
        return result
    except Exception as e:
        print(f"[QUOTE] {stock_code}: 腾讯财经也失败了: {e}")

    print(f"[QUOTE] {stock_code}: 所有数据源均失败，返回None")
    return None

def _cloud_get_kline_data(stock_code: str, period: str = "daily", days: int = 60):
    """获取K线数据（云端版）。主源：东方财富push2his，备源：新浪财经"""
    import requests
    from datetime import datetime, timedelta

    def _parse_eastmoney_klines(klines_raw):
        """解析东方财富K线原始数据"""
        records = []
        for line in klines_raw:
            parts = line.split(",")
            if len(parts) < 11:
                continue
            records.append({
                "date": parts[0], "open": float(parts[1]), "close": float(parts[2]),
                "high": float(parts[3]), "low": float(parts[4]),
                "volume": float(parts[5]), "amount": float(parts[6]),
            })
        return records

    # ---- 主源：东方财富 push2his ----
    try:
        sid = _secid(stock_code)
        klt = {"daily": 101, "weekly": 102, "monthly": 103}.get(period, 101)
        beg_date = (datetime.now() - timedelta(days=days * 2)).strftime("%Y%m%d")
        url = (f"https://push2his.eastmoney.com/api/qt/stock/kline/get"
               f"?secid={sid}&fields1=f1,f2,f3,f4,f5,f6"
               f"&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
               f"&klt={klt}&fqt=1&end=20500101&beg={beg_date}&lmt={days + 10}")
        resp = requests.get(url, headers=_headers(), timeout=15)
        klines = resp.json().get("data", {}).get("klines", [])
        if klines:
            records = _parse_eastmoney_klines(klines)
            records.sort(key=lambda x: x["date"])
            result = records[-days:] if len(records) > days else records
            if result:
                print(f"[KLINE] {stock_code} (来源:eastmoney): {len(result)}条, "
                      f"范围 {result[0]['date']}~{result[-1]['date']}")
                return result
        print(f"[KLINE] {stock_code}: eastmoney返回空({len(klines)}条), 尝试备源...")
    except Exception as e:
        print(f"[KLINE] {stock_code}: eastmoney异常: {e}, 尝试备源...")

    # ---- 备源：新浪财经 K线API ----
    try:
        code_short = stock_code[-6:]
        market_prefix = "sh" if code_short.startswith("6") else "sz"
        sina_symbol = f"{market_prefix}{code_short}"
        # 新浪财经历史K线接口
        sina_url = (f"http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
                    f"CN_MarketData.getKLineData"
                    f"?symbol={sina_symbol}&scale=240&ma=no&datalen={days + 10}")
        resp = requests.get(sina_url, headers=_headers(), timeout=15)
        # 返回格式: [{"day":"2026-07-01","open":...,"close":..., ...}, ...]
        items = resp.json()
        if items and isinstance(items, list):
            records = []
            for item in items:
                d = item.get("day", "")
                if not d:
                    continue
                def _sf(k, default=0):
                    v = item.get(k)
                    if v is None or v == "":
                        return default
                    try:
                        return float(v)
                    except (ValueError, TypeError):
                        return default
                records.append({
                    "date": d,
                    "open": _sf("open"),
                    "close": _sf("close"),
                    "high": _sf("high"),
                    "low": _sf("low"),
                    "volume": _sf("volume") / 100 if _sf("volume") > 0 else 0,
                    "amount": _sf("turnover") * 10000 if _sf("turnover") > 0 else 0,
                })
            records.sort(key=lambda x: x["date"])
            result = records[-days:] if len(records) > days else records
            if result:
                print(f"[KLINE] {stock_code} (来源:sina): {len(result)}条, "
                      f"范围 {result[0]['date']}~{result[-1]['date']}")
                return result
            else:
                print(f"[KLINE] {stock_code}: sina有数据但过滤后为空")
        else:
            print(f"[KLINE] {stock_code}: sina返回: type={type(items).__name__}")
    except Exception as e:
        print(f"[KLINE] {stock_code}: sina备源也失败: {e}")

    print(f"[KLINE] {stock_code}: 所有数据源均失败，返回None")
    return None

def _cloud_get_stock_news(stock_code: str, days: int = 7, max_news: int = 50):
    import requests
    try:
        code = stock_code[-6:] if len(stock_code) > 6 else stock_code
        sid = _secid(code)
        url = f"https://np-listapi.eastmoney.com/comm/web/getListInfo?cb=&client=web&type=1&mTypeAndCode={sid}&pageSize={max_news}&pageIndex=1&token=&startTime=&endTime="
        resp = requests.get(url, headers=_headers(), timeout=15)
        if resp.status_code != 200:
            return []
        data = resp.json()
        if data.get("code") != 1:
            return []
        cutoff = datetime.now() - timedelta(days=days)
        news = []
        for art in data.get("data", {}).get("list", []):
            title = art.get("Art_Title", "").strip()
            if not title:
                continue
            import re
            title = re.sub(r"<[^>]+>", "", title)
            pub_str = art.get("Art_ShowTime", "")
            if not pub_str:
                continue
            try:
                pub = datetime.strptime(pub_str, "%Y-%m-%d %H:%M:%S")
            except Exception:
                continue
            if pub < cutoff:
                continue
            art_url = art.get("Art_Url", art.get("Art_OriginUrl", ""))
            news.append({
                "title": title[:200], "content": title[:2000],
                "publish_time": pub.strftime("%Y-%m-%d %H:%M:%S"),
                "date": pub.strftime("%Y-%m-%d"),
                "source": "东方财富", "url": art_url if art_url.startswith("http") else "",
            })
        seen = set()
        unique = []
        for n in news:
            k = (n["title"][:30], n["date"])
            if k not in seen:
                seen.add(k)
                unique.append(n)
        unique.sort(key=lambda x: x["publish_time"], reverse=True)
        return unique[:max_news]
    except Exception:
        return []

def _cloud_batch_get_news(stock_codes: list, days: int = 7, max_news: int = 50, desc: str = ""):
    result = {}
    for code in stock_codes:
        result[code] = _cloud_get_stock_news(code, days=days, max_news=max_news)
        time.sleep(0.3)
    return result

def _cloud_get_fund_flow(stock_code: str, days: int = 5):
    import requests
    try:
        sid = _secid(stock_code)
        url = f"https://push2.eastmoney.com/api/qt/stock/get?secid={sid}&fields=f62,f64,f66,f69,f70,f72,f74,f78"
        resp = requests.get(url, headers=_headers(), timeout=10)
        d = resp.json().get("data", {})
        main_net = d.get("f62", 0) / 1e8 if d.get("f62") else 0
        return {"stock_code": stock_code, "main_net_avg": round(main_net, 2), "total_net_avg": round(main_net, 2), "net_direction": "流入" if main_net > 0 else "流出", "records": [{"date": "", "main_net": round(main_net, 2)}]}
    except Exception:
        return {"stock_code": stock_code, "main_net_avg": 0, "total_net_avg": 0, "net_direction": "流出", "records": []}

def _cloud_get_company_announcements(stock_code: str, days: int = 7):
    import requests
    try:
        code = stock_code[-6:] if len(stock_code) > 6 else stock_code
        mkt = "SH" if code.startswith("6") else "SZ"
        url = f"https://np-anotice-stock.eastmoney.com/api/security/ann?page_size=10&page_index=1&ann_type=SHA&stock_list=gset{mkt}{code}01"
        resp = requests.get(url, headers=_headers(), timeout=10)
        items = resp.json().get("data", {}).get("list", [])
        cutoff = datetime.now() - timedelta(days=days)
        anns = []
        for it in items:
            try:
                ad = datetime.strptime(it.get("notice_date", ""), "%Y-%m-%d %H:%M:%S")
                if ad >= cutoff:
                    anns.append({"title": it.get("title_ch", it.get("title", "")), "date": ad.strftime("%Y-%m-%d"), "type": it.get("ann_type", "")})
            except Exception:
                continue
        return anns[:10]
    except Exception:
        return []


# =============================================================================
# 统一获取器入口
# =============================================================================

@functools.lru_cache(maxsize=1)
def _get_fetchers():
    """云端用内置HTTP，本地用data_fetcher"""
    if IS_RENDER:
        return {
            "search_stocks": _cloud_search_stocks,
            "get_stock_by_code": _cloud_get_stock_by_code,
            "get_market_index": _cloud_get_market_index,
            "get_real_time_quote": _cloud_get_real_time_quote,
            "get_kline_data": _cloud_get_kline_data,
            "get_stock_news": _cloud_get_stock_news,
            "batch_get_news": _cloud_batch_get_news,
            "get_fund_flow": _cloud_get_fund_flow,
            "get_company_announcements": _cloud_get_company_announcements,
        }
    from core.data_fetcher import (
        search_stocks, get_stock_news, get_stock_by_code,
        get_kline_data, get_real_time_quote, get_market_index,
        get_fund_flow, get_company_announcements, batch_get_news
    )
    return {
        "search_stocks": search_stocks,
        "get_stock_news": get_stock_news,
        "get_stock_by_code": get_stock_by_code,
        "get_kline_data": get_kline_data,
        "get_real_time_quote": get_real_time_quote,
        "get_market_index": get_market_index,
        "get_fund_flow": get_fund_flow,
        "get_company_announcements": get_company_announcements,
        "batch_get_news": batch_get_news,
    }


# =============================================================================
# 懒加载工具
# =============================================================================

@functools.lru_cache(maxsize=1)
def _get_config():
    from config import REPORT_DIR, DEFAULT_LOOKBACK_DAYS, DEFAULT_START_CAPITAL, DEFAULT_COMMISSION
    return {
        "REPORT_DIR": REPORT_DIR,
        "DEFAULT_LOOKBACK_DAYS": DEFAULT_LOOKBACK_DAYS,
        "DEFAULT_START_CAPITAL": DEFAULT_START_CAPITAL,
        "DEFAULT_COMMISSION": DEFAULT_COMMISSION,
    }

def _get_report_dir():
    return _get_config()["REPORT_DIR"]

@functools.lru_cache(maxsize=1)
def _get_sentiment_analyzer():
    try:
        from core.sentiment import SentimentAnalyzer
        return SentimentAnalyzer()
    except Exception as e:
        print(f"[WARN] SentimentAnalyzer init failed: {e}")
        return None

@functools.lru_cache(maxsize=1)
def _get_report_generator():
    try:
        from visualization.report import ReportGenerator
        return ReportGenerator()
    except Exception as e:
        print(f"[WARN] ReportGenerator init failed: {e}")
        return None

def _cleanup():
    gc.collect()

def _init_dirs():
    try:
        _get_report_dir().mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

_init_dirs()

# =============================================================================
# 云端启动预热（尽早发现依赖问题）
# =============================================================================

def _warmup():
    """预热：验证所有关键模块可正常加载"""
    print("[WARMUP] Starting dependency checks...")
    errors = []
    # 1. 测试 config
    try:
        from config import POSITIVE_KEYWORDS, NEGATIVE_KEYWORDS
        print(f"[WARMUP] config OK ({len(POSITIVE_KEYWORDS)} pos, {len(NEGATIVE_KEYWORDS)} neg keywords)")
    except Exception as e:
        errors.append(f"config: {e}")
    # 2. 测试 sentiment（含 snownlp）
    try:
        analyzer = _get_sentiment_analyzer()
        if analyzer:
            test_result = analyzer.analyze([{"title": "测试利好", "content": "业绩增长", "source": "测试", "publish_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "date": datetime.now().strftime("%Y-%m-%d")}])
            score = test_result.get("overall_sentiment", {}).get("score", -1)
            print(f"[WARMUP] sentiment OK (test score={score})")
        else:
            errors.append("sentiment: analyzer is None after init")
    except Exception as e:
        import traceback
        errors.append(f"sentiment: {e}\n{traceback.format_exc()}")
    # 3. 测试 cache
    try:
        from utils.cache import FileCache
        print("[WARMUP] cache OK")
    except Exception as e:
        errors.append(f"cache: {e}")

    if errors:
        print("[WARMUP] ERRORS:")
        for err in errors:
            print(f"  [ERR] {err}")
    else:
        print("[WARMUP] All checks passed! ✓")

_warmup()


# =============================================================================
# 云端报告生成器（纯 Python + Plotly.js CDN，零外部依赖）
# =============================================================================

from core.cloud_report import generate_report, generate_backtest_report


# =============================================================================
# 页面路由
# =============================================================================

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/analyze")
def analyze_page():
    return render_template("analyze.html")

@app.route("/batch")
def batch_page():
    return render_template("batch.html")

@app.route("/backtest")
def backtest_page():
    return render_template("backtest.html")

@app.route("/reports")
def reports_page():
    return render_template("reports.html")

@app.route("/about")
def about_page():
    return render_template("about.html")


# =============================================================================
# API 路由
# =============================================================================

@app.route("/api/search_stocks")
def api_search_stocks():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"success": False, "error": "请输入搜索关键词"})
    try:
        f = _get_fetchers()
        results = f["search_stocks"](q, top_n=20)
        _cleanup()
        return jsonify({"success": True, "data": results})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/quote")
def api_quote():
    code = request.args.get("code", "").strip()
    if not code:
        return jsonify({"success": False, "error": "请输入股票代码"})
    try:
        f = _get_fetchers()
        quote = f["get_real_time_quote"](code)
        _cleanup()
        if quote:
            return jsonify({"success": True, "data": quote})
        return jsonify({"success": False, "error": f"无法获取 {code} 的行情数据"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/market_index")
def api_market_index():
    try:
        f = _get_fetchers()
        data = f["get_market_index"]()
        _cleanup()
        if data:
            for info in data.values():
                info["price"] = round(info["price"], 2)
                info["change"] = round(info["change"], 2)
                info["pct_change"] = round(info["pct_change"], 2)
        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/single_analysis", methods=["POST"])
def api_single_analysis():
    _t0 = time.time()
    try:
        data = request.get_json()
        stock_code = data.get("code", "").strip()
        stock_name = data.get("name", "").strip()
        cfg = _get_config()
        days = int(data.get("days", cfg["DEFAULT_LOOKBACK_DAYS"]))
        max_news = int(data.get("max_news", 20))
        if not stock_code:
            return jsonify({"success": False, "error": "请输入股票代码"})

        print(f"[ANALYZE] 开始分析 {stock_code} (days={days}, max_news={max_news})")

        f = _get_fetchers()
        if not stock_name:
            info = f["get_stock_by_code"](stock_code)
            if info:
                stock_name = info.get("name", stock_code)

        news_list = f["get_stock_news"](stock_code, days=days, max_news=max_news)
        print(f"[ANALYZE] 新闻获取完成 ({len(news_list)}条, {time.time()-_t0:.1f}s)")
        if not news_list:
            return jsonify({"success": False, "error": f"未找到 {stock_code} 的相关新闻"})

        analyzer = _get_sentiment_analyzer()
        if analyzer is None:
            return jsonify({"success": False, "error": "情感分析引擎初始化失败，请稍后重试"})
        sentiment_result = analyzer.analyze(news_list)
        _cleanup()
        print(f"[ANALYZE] 情感分析完成 ({time.time()-_t0:.1f}s)")

        kline_data = f["get_kline_data"](stock_code, days=max(60, days))
        quote = f["get_real_time_quote"](stock_code)
        print(f"[ANALYZE] 行情获取: quote={'OK' if quote else 'None'}")
        market = f["get_market_index"]()
        fund_flow = f["get_fund_flow"](stock_code, days=min(5, days))
        announcements = f["get_company_announcements"](stock_code, days=days)
        print(f"[ANALYZE] 行情数据获取完成 ({time.time()-_t0:.1f}s)")

        if IS_RENDER:
            # 云端用 Plotly.js CDN 报告（完整的暗色主题 + 交互图表）
            report_path = generate_report(
                stock_code=stock_code, stock_name=stock_name,
                sentiment_result=sentiment_result, news_list=news_list,
                kline_data=kline_data, quote=quote, market=market,
                fund_flow=fund_flow, announcements=announcements
            )
        else:
            gen = _get_report_generator()
            report_path = gen.generate_sentiment_report(
                stock_code=stock_code, stock_name=stock_name,
                sentiment_result=sentiment_result, news_list=[],
                kline_data=kline_data, quote=quote, market=market,
                fund_flow=fund_flow, announcements=announcements
            )
        print(f"[ANALYZE] 报告生成完成 (总耗时 {time.time()-_t0:.1f}s)")

        overall = sentiment_result.get("overall_sentiment", {})
        summary = {
            "stock_code": stock_code, "stock_name": stock_name,
            "score": overall.get("score", 0), "label": overall.get("label", "未知"),
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
        }

        # 安全提取 price / pct_change，确保返回数字或 None（不返回字符串）
        def _safe_num(val, fallback=None):
            """将值安全转为 float，防止 NaN/None/Inf 进入 JSON"""
            if val is None:
                return fallback
            try:
                f = float(val)
                import math
                if math.isnan(f) or math.isinf(f):
                    return fallback
                return round(f, 2)
            except (ValueError, TypeError):
                return fallback

        _q = quote if isinstance(quote, dict) else {}
        summary["price"] = _safe_num(_q.get("price"))
        summary["pct_change"] = _safe_num(_q.get("pct_change"))
        # 日志：输出行情数据是否获取成功
        print(f"[QUOTE-OUT] price={summary['price']}, pct={summary['pct_change']}, quote_is_none={quote is None}")
        summary["report_url"] = f"/reports/view/{Path(report_path).name}" if report_path else None
        del sentiment_result, kline_data, quote, market, fund_flow, announcements
        _cleanup()
        return jsonify({"success": True, "data": summary})
    except Exception as e:
        import traceback
        traceback.print_exc()
        _cleanup()
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/batch_analysis", methods=["POST"])
def api_batch_analysis():
    try:
        data = request.get_json()
        codes_str = data.get("codes", "").strip()
        cfg = _get_config()
        days = int(data.get("days", cfg["DEFAULT_LOOKBACK_DAYS"]))
        max_news = int(data.get("max_news", 10))
        if not codes_str:
            return jsonify({"success": False, "error": "请输入股票代码"})
        codes = [c.strip() for c in codes_str.replace("\n", ",").replace(" ", ",").split(",") if c.strip()]
        if not codes:
            return jsonify({"success": False, "error": "无法解析股票代码"})

        f = _get_fetchers()
        analyzer = _get_sentiment_analyzer()
        if analyzer is None:
            return jsonify({"success": False, "error": "情感分析引擎初始化失败，请稍后重试"})
        results = []
        for code in codes:
            try:
                info = f["get_stock_by_code"](code)
                name = info.get("name", code) if info else code
                news_list = f["get_stock_news"](code, days=days, max_news=max_news)
                if news_list:
                    sr = analyzer.analyze(news_list)
                    ov = sr.get("overall_sentiment", {})
                    results.append({
                        "code": code, "name": name,
                        "score": round(ov.get("score", 0), 3),
                        "label": ov.get("label", "未知"),
                        "news_count": len(news_list),
                        "positive_ratio": ov.get("positive_ratio", 0),
                        "confidence": ov.get("confidence_index", 0),
                    })
                    del sr
                else:
                    results.append({"code": code, "name": name, "score": 0, "label": "无数据", "news_count": 0, "positive_ratio": 0, "confidence": 0})
                del news_list
                _cleanup()
            except Exception as e:
                results.append({"code": code, "name": code, "score": 0, "label": f"错误: {e}", "news_count": 0, "positive_ratio": 0, "confidence": 0})
        results.sort(key=lambda x: x["score"], reverse=True)
        _cleanup()
        return jsonify({"success": True, "data": results, "report_url": None})
    except Exception as e:
        import traceback
        traceback.print_exc()
        _cleanup()
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/backtest", methods=["POST"])
def api_backtest():
    _bt0 = time.time()
    try:
        data = request.get_json()
        stock_code = data.get("code", "").strip()
        stock_name = data.get("name", "").strip()
        cfg = _get_config()
        lookback = int(data.get("lookback", cfg["DEFAULT_LOOKBACK_DAYS"]))
        capital = float(data.get("capital", 100000))
        if not stock_code:
            return jsonify({"success": False, "error": "请输入股票代码"})

        f = _get_fetchers()
        if not stock_name:
            info = f["get_stock_by_code"](stock_code)
            if info:
                stock_name = info.get("name", stock_code)

        # 获取K线数据
        kline_data = f["get_kline_data"](stock_code, days=max(60, lookback * 3))
        print(f"[BT] K线获取: {len(kline_data) if kline_data else 0}条")

        # 获取新闻+情感分析（情绪策略需要）
        news_list = f["get_stock_news"](stock_code, days=lookback, max_news=30)
        sentiment_result = None
        if news_list:
            analyzer = _get_sentiment_analyzer()
            if analyzer:
                sentiment_result = analyzer.analyze(news_list)
                _cleanup()

        summary = []

        if IS_RENDER:
            # ===== 云端：使用零依赖纯Python回测引擎 + 生成HTML报告 =====
            from core.cloud_backtest import compare_strategies_cloud as cloud_bt
            results = cloud_bt(
                stock_code=stock_code, stock_name=stock_name,
                capital=capital, lookback_days=lookback,
                kline_data=kline_data or [], sentiment_result=sentiment_result or {},
            )
            for key, res in results.items():
                if "error" in res and not res.get("total_return"):
                    continue
                summary.append({
                    "strategy": key,
                    "strategy_name": res.get("strategy_name", _get_strategy_name(key)),
                    "total_return": res.get("total_return", 0),
                    "annual_return": res.get("annual_return", 0),
                    "max_drawdown": res.get("max_drawdown", 0),
                    "sharpe_ratio": res.get("sharpe_ratio", 0),
                    "win_rate": res.get("win_rate", 0),
                    "total_trades": res.get("total_trades", 0),
                    "final_value": res.get("final_value", capital),
                })
            # 生成云端回测报告（Plotly.js CDN 交互式图表）
            try:
                bt_report_path = generate_backtest_report(
                    stock_code=stock_code, stock_name=stock_name,
                    results=results, capital=capital,
                    lookback_days=lookback, kline_data=kline_data or [],
                    sentiment_result=sentiment_result or {},
                )
                report_url = f"/reports/view/{Path(bt_report_path).name}"
                print(f"[BT] 云端回测报告已生成: {bt_report_path}")
            except Exception as e:
                import traceback as tb
                print(f"[BT] 云端回测报告生成失败: {e}")
                print(f"[BT] 报告异常详情:\n{tb.format_exc()}")
                report_url = None

        else:
            # ===== 桌面版：使用完整pandas回测引擎 + Plotly报告 =====
            from core.backtest import compare_strategies
            results = compare_strategies(stock_code=stock_code, stock_name=stock_name, capital=capital, lookback_days=lookback)
            all_results = list(results.values())
            gen = _get_report_generator()
            report_path = gen.generate_backtest_report(results=all_results, stock_name_map={r.stock_code: r.stock_name for r in all_results})
            for strategy, result in results.items():
                summary.append({
                    "strategy": strategy, "strategy_name": _get_strategy_name(strategy),
                    "total_return": round(result.total_return, 2),
                    "annual_return": round(result.annual_return, 2),
                    "max_drawdown": round(result.max_drawdown, 2),
                    "sharpe_ratio": round(result.sharpe_ratio, 2),
                    "win_rate": round(result.win_rate, 2),
                    "total_trades": result.total_trades,
                    "final_value": round(result.final_value, 2),
                })
            report_url = f"/reports/view/{Path(report_path).name}"

        best = max(summary, key=lambda x: x["total_return"]) if summary else None
        del kline_data
        _cleanup()
        elapsed = time.time() - _bt0
        print(f"[BT] 回测总耗时: {elapsed:.1f}s | report_url={report_url}")

        # 兜底：如果报告文件生成失败，生成内联HTML返回给前端
        report_html_fallback = None
        if not report_url and IS_RENDER:
            try:
                report_html_fallback = _generate_inline_backtest_html(
                    stock_code, stock_name, results if 'results' in dir() else {},
                    capital, lookback, summary, best,
                )
                print(f"[BT] 已生成内联兜底报告: {len(report_html_fallback)} bytes")
            except Exception as e2:
                print(f"[BT] 内联报告也失败: {e2}")

        resp_data = {
            "success": True, "data": summary, "best_strategy": best,
            "stock_code": stock_code, "stock_name": stock_name,
            "report_url": report_url,
        }
        if report_html_fallback:
            resp_data["report_html"] = report_html_fallback
        return jsonify(resp_data)
    except Exception as e:
        import traceback
        traceback.print_exc()
        _cleanup()
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/reports")
def api_reports():
    try:
        report_dir = _get_report_dir()
        reports = []
        if report_dir.exists():
            for f in sorted(report_dir.glob("*.html"), key=lambda x: x.stat().st_mtime, reverse=True):
                reports.append({"name": f.name, "size": f.stat().st_size, "mtime": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M"), "url": f"/reports/view/{f.name}"})
        return jsonify({"success": True, "data": reports[:50]})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/reports/view/<filename>")
def view_report(filename):
    return send_from_directory(str(_get_report_dir()), filename)


# =============================================================================
# 错误处理（防止 worker 崩溃）
# =============================================================================

@app.errorhandler(404)
def not_found(e):
    if request.path.startswith("/api/"):
        return jsonify({"success": False, "error": f"API not found: {request.path}"}), 404
    return render_template("index.html")

@app.errorhandler(500)
def server_error(e):
    return jsonify({"success": False, "error": f"Internal error: {str(e)}"}), 500


# =============================================================================
# 健康检查
# =============================================================================

@app.route("/health")
def health():
    try:
        import psutil
        mem = psutil.Process().memory_info().rss / 1024 / 1024
        return jsonify({"status": "ok", "memory_mb": round(mem, 1)})
    except ImportError:
        return jsonify({"status": "ok", "memory_mb": -1})


# =============================================================================
# 辅助
# =============================================================================

def _get_strategy_name(strategy: str) -> str:
    return {
        "buy_hold": "买入持有", "sentiment_only": "纯情绪信号",
        "sentiment_ma": "情绪+均线", "rsi_mean_reversion": "RSI均值回归",
        "bollinger_breakout": "布林带突破", "momentum": "动量策略",
    }.get(strategy, strategy)


# =============================================================================
# 启动
# =============================================================================

if __name__ == "__main__":
    import socket
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    use_public = "--public" in sys.argv
    port = int(os.environ.get("PORT", 5000))
    print("=" * 60)
    print("  SentimentQuant Mobile - 市场情绪量化系统")
    print("=" * 60)
    print()
    print(f"  本地访问:    http://127.0.0.1:{port}")
    print(f"  局域网访问:  http://{local_ip}:{port}")
    if use_public:
        print()
        print("  正在创建公网隧道...")
        try:
            import subprocess, re
            proc = subprocess.Popen(
                ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
                 "-o", "ServerAliveInterval=30", "-o", "ConnectTimeout=10",
                 "-R", f"80:localhost:{port}", "nokey@localhost.run"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            def _tunnel():
                for line in proc.stdout:
                    m = re.search(r"https://([a-zA-Z0-9-]+\.lhr\.life)", line)
                    if m:
                        print(f"\n  *** 公网地址: {m.group(0)}")
                        break
            threading.Thread(target=_tunnel, daemon=True).start()
            time.sleep(8)
        except Exception as e:
            print(f"  公网隧道创建失败: {e}")
    print()
    print("  按 Ctrl+C 停止服务器")
    print("=" * 60)
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
