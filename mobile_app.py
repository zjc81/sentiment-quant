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
    import requests
    try:
        sid = _secid(stock_code)
        url = f"https://push2.eastmoney.com/api/qt/stock/get?secid={sid}&fields=f43,f44,f45,f46,f47,f48,f50,f51,f52,f55,f57,f58,f115,f117,f162,f167,f168,f169,f170,f171"
        resp = requests.get(url, headers=_headers(), timeout=10)
        d = resp.json().get("data", {})
        if not d:
            return None
        price = d.get("f43", 0) / 100 if d.get("f43") else 0
        pre = d.get("f44", 0) / 100 if d.get("f44") else 0
        chg = price - pre
        pct = chg / pre * 100 if pre else 0
        return {
            "code": stock_code, "name": "",
            "price": round(price, 2), "change": round(chg, 2), "pct_change": round(pct, 2),
            "volume": d.get("f48", 0) / 100 if d.get("f48") else 0,
            "amount": d.get("f50", 0) or 0,
            "high": round(d.get("f45", 0) / 100, 2) if d.get("f45") else 0,
            "low": round(d.get("f46", 0) / 100, 2) if d.get("f46") else 0,
            "open": round(d.get("f47", 0) / 100, 2) if d.get("f47") else 0,
            "pre_close": round(pre, 2),
            "turnover": d.get("f168", 0) / 100 if d.get("f168") else 0,
            "pe": d.get("f162", 0) / 100 if d.get("f162") else None,
            "market_cap": d.get("f116", d.get("f20", 0)) or 0,
            "circulating_cap": d.get("f117", d.get("f21", 0)) or 0,
        }
    except Exception:
        return None

def _cloud_get_kline_data(stock_code: str, period: str = "daily", days: int = 60):
    import requests
    try:
        sid = _secid(stock_code)
        klt = {"daily": 101, "weekly": 102, "monthly": 103}.get(period, 101)
        url = f"https://push2his.eastmoney.com/api/qt/stock/kline/get?secid={sid}&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61&klt={klt}&fqt=1&end=20500101&lmt={days + 30}"
        resp = requests.get(url, headers=_headers(), timeout=15)
        klines = resp.json().get("data", {}).get("klines", [])
        records = []
        for line in klines:
            parts = line.split(",")
            if len(parts) < 11:
                continue
            records.append({
                "date": parts[0], "open": float(parts[1]), "close": float(parts[2]),
                "high": float(parts[3]), "low": float(parts[4]),
                "volume": float(parts[5]), "amount": float(parts[6]),
            })
        records.sort(key=lambda x: x["date"])
        return records[-days:] if len(records) > days else records
    except Exception:
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
# 云端轻量 HTML 报告生成器（无 Plotly/pandas/numpy 依赖）
# =============================================================================

def _generate_cloud_report(stock_code, stock_name, sentiment_result, kline_data,
                           quote, market, fund_flow, announcements):
    """纯 Python 生成精美 HTML 分析报告"""
    overall = sentiment_result.get("overall_sentiment", {})
    score = overall.get("score", 0.5)
    label = overall.get("label", "未知")
    score_pct = int(score * 100)

    # 颜色（中国股市习惯：红涨绿跌）
    score_color = "#e74c3c" if score > 0.55 else "#27ae60" if score < 0.45 else "#f39c12"
    bg_gradient = f"linear-gradient(135deg, {score_color}22 0%, #f5f5f5 100%)"

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # === 行情概览 ===
    quote_rows = ""
    if quote:
        price = quote.get("price", "--")
        pct = quote.get("pct_change", 0)
        chg = quote.get("change", 0)
        pct_color = "#e74c3c" if pct >= 0 else "#27ae60"
        chg_sign = "+" if chg >= 0 else ""
        quote_rows += f"""
        <div style="display:flex;justify-content:center;gap:30px;flex-wrap:wrap;margin-bottom:20px;">
            <div style="text-align:center;">
                <div style="font-size:12px;color:#999;">最新价</div>
                <div style="font-size:24px;font-weight:700;color:{pct_color};">&yen;{price}</div>
            </div>
            <div style="text-align:center;">
                <div style="font-size:12px;color:#999;">涨跌额</div>
                <div style="font-size:18px;font-weight:600;color:{pct_color};">{chg_sign}{chg}</div>
            </div>
            <div style="text-align:center;">
                <div style="font-size:12px;color:#999;">涨跌幅</div>
                <div style="font-size:18px;font-weight:600;color:{pct_color};">{chg_sign}{pct}%</div>
            </div>
            <div style="text-align:center;">
                <div style="font-size:12px;color:#999;">换手率</div>
                <div style="font-size:16px;color:#333;">{quote.get('turnover', '--')}%</div>
            </div>
            <div style="text-align:center;">
                <div style="font-size:12px;color:#999;">市盈率</div>
                <div style="font-size:16px;color:#333;">{quote.get('pe', '--')}</div>
            </div>
        </div>"""

    # === 大盘指数 ===
    market_rows = ""
    if market:
        market_rows = '<div style="display:flex;justify-content:center;gap:20px;flex-wrap:wrap;margin-bottom:20px;">'
        for name, idx in market.items():
            mpct = idx.get("pct_change", 0)
            mc = "#e74c3c" if mpct >= 0 else "#27ae60"
            ms = "+" if mpct >= 0 else ""
            market_rows += f'<div style="background:#fff;padding:10px 16px;border-radius:8px;box-shadow:0 1px 4px rgba(0,0,0,0.08);text-align:center;"><div style="font-size:11px;color:#999;">{name}</div><div style="font-size:15px;font-weight:600;color:{mc};">{idx["price"]} <span style="font-size:12px;">{ms}{mpct}%</span></div></div>'
        market_rows += '</div>'

    # === 资金流向 ===
    fund_html = ""
    if fund_flow and fund_flow.get("main_net_avg", 0) != 0:
        fmain = fund_flow.get("main_net_avg", 0)
        fdir = fund_flow.get("net_direction", "流出")
        fd_color = "#e74c3c" if fmain > 0 else "#27ae60"
        fund_html = f'<div style="background:#fff;padding:15px 20px;border-radius:8px;box-shadow:0 1px 4px rgba(0,0,0,0.08);margin-bottom:20px;text-align:center;"><span style="color:#999;font-size:13px;">主力资金：</span><span style="font-size:18px;font-weight:600;color:{fd_color};">{fmain:.2f} 亿（{fdir}）</span></div>'

    # === K线统计 ===
    kline_stats = ""
    if kline_data and len(kline_data) >= 5:
        closes = [k["close"] for k in kline_data]
        volumes = [k["volume"] for k in kline_data]
        avg_close = sum(closes) / len(closes)
        max_close = max(closes)
        min_close = min(closes)
        avg_vol = sum(volumes) / len(volumes)
        kline_stats = f"""
        <div style="display:flex;justify-content:center;gap:20px;flex-wrap:wrap;margin-bottom:20px;">
            <div style="background:#fff;padding:10px 14px;border-radius:8px;box-shadow:0 1px 4px rgba(0,0,0,0.08);text-align:center;"><div style="font-size:11px;color:#999;">K线天数</div><div style="font-size:16px;font-weight:600;color:#333;">{len(kline_data)}</div></div>
            <div style="background:#fff;padding:10px 14px;border-radius:8px;box-shadow:0 1px 4px rgba(0,0,0,0.08);text-align:center;"><div style="font-size:11px;color:#999;">均价</div><div style="font-size:16px;font-weight:600;color:#333;">{avg_close:.2f}</div></div>
            <div style="background:#fff;padding:10px 14px;border-radius:8px;box-shadow:0 1px 4px rgba(0,0,0,0.08);text-align:center;"><div style="font-size:11px;color:#999;">最高</div><div style="font-size:16px;font-weight:600;color:#e74c3c;">{max_close:.2f}</div></div>
            <div style="background:#fff;padding:10px 14px;border-radius:8px;box-shadow:0 1px 4px rgba(0,0,0,0.08);text-align:center;"><div style="font-size:11px;color:#999;">最低</div><div style="font-size:16px;font-weight:600;color:#27ae60;">{min_close:.2f}</div></div>
            <div style="background:#fff;padding:10px 14px;border-radius:8px;box-shadow:0 1px 4px rgba(0,0,0,0.08);text-align:center;"><div style="font-size:11px;color:#999;">日均量</div><div style="font-size:16px;font-weight:600;color:#333;">{avg_vol/10000:.0f}万</div></div>
        </div>"""

    # === 时间趋势 ===
    time_trend = sentiment_result.get("time_analysis", {}).get("trend", [])
    trend_rows = ""
    for t in time_trend[:7]:
        ts = t.get("score", 0.5)
        tc = "#e74c3c" if ts > 0.55 else "#27ae60" if ts < 0.45 else "#f39c12"
        tp = int(ts * 100)
        trend_rows += f'<tr><td>{t["date"]}</td><td style="color:{tc};font-weight:600;">{tp}%</td><td>{", ".join(e.get("title","") for e in t.get("key_events",[])) or "--"}</td></tr>'

    time_html = ""
    if trend_rows:
        time_html = f"""
        <div style="margin-bottom:20px;">
            <h3 style="color:#333;border-bottom:2px solid #eee;padding-bottom:8px;">&#x1F4C8; 时间趋势</h3>
            <div style="overflow-x:auto;">
            <table style="width:100%;border-collapse:collapse;font-size:13px;">
                <thead><tr style="background:#f0f0f0;"><th style="padding:8px;text-align:left;">日期</th><th style="padding:8px;">情感得分</th><th style="padding:8px;">关键事件</th></tr></thead>
                <tbody>{trend_rows}</tbody>
            </table>
            </div>
            <p style="color:#666;font-size:13px;margin-top:8px;">{sentiment_result.get("time_analysis", {}).get("trend_prediction", "")}</p>
        </div>"""

    # === 主题分析 ===
    topic_data = sentiment_result.get("topic_analysis", {})
    topic_rows = ""
    topic_names = {"company_operation": "公司经营", "financial_performance": "财务表现", "market_competition": "市场竞争", "product_technology": "产品技术", "industry_policy": "行业政策", "capital_market": "资本市场"}
    for key, name in topic_names.items():
        td = topic_data.get(key, {})
        ts = td.get("score", 0.5)
        tc = "#e74c3c" if ts > 0.55 else "#27ae60" if ts < 0.45 else "#f39c12"
        tp = int(ts * 100)
        kps = ", ".join(td.get("key_points", [])[:2]) or "--"
        topic_rows += f'<tr><td style="font-weight:600;">{name}</td><td style="color:{tc};font-weight:600;">{tp}%</td><td style="font-size:12px;">{td.get("summary","")}</td></tr>'

    topic_html = f"""
    <div style="margin-bottom:20px;">
        <h3 style="color:#333;border-bottom:2px solid #eee;padding-bottom:8px;">&#x1F4CA; 多维度分析</h3>
        <table style="width:100%;border-collapse:collapse;font-size:13px;">
            <thead><tr style="background:#f0f0f0;"><th style="padding:8px;text-align:left;width:80px;">维度</th><th style="padding:8px;width:70px;">得分</th><th style="padding:8px;">概要</th></tr></thead>
            <tbody>{topic_rows}</tbody>
        </table>
    </div>"""

    # === 风险分析 ===
    risk = sentiment_result.get("risk_analysis", {})
    risk_level = risk.get("risk_level", "低")
    risk_color = "#e74c3c" if risk_level == "高" else "#f39c12" if risk_level == "中" else "#27ae60"
    risk_items = ""
    for rf in risk.get("risk_factors", [])[:5]:
        rs = rf.get("severity", "低")
        rsc = "#e74c3c" if rs == "高" else "#e67e22" if rs == "中" else "#999"
        risk_items += f'<div style="padding:6px 10px;background:#fff;border-radius:6px;margin-bottom:4px;border-left:3px solid {rsc};"><span style="color:{rsc};font-weight:600;">[{rs}风险]</span> {rf.get("factor","")}: {rf.get("description","")[:50]}</div>'

    risk_html = f"""
    <div style="margin-bottom:20px;">
        <h3 style="color:#333;border-bottom:2px solid #eee;padding-bottom:8px;">&#x26A0;&#xFE0F; 风险分析</h3>
        <div style="text-align:center;margin-bottom:10px;">
            <div style="display:inline-block;padding:8px 24px;background:{risk_color}15;border-radius:20px;font-size:18px;font-weight:700;color:{risk_color};">风险等级：{risk_level}</div>
        </div>
        {risk_items if risk_items else '<p style="color:#999;text-align:center;">暂未发现明显风险因子</p>'}
    </div>"""

    # === 公告 ===
    ann_html = ""
    if announcements:
        ann_rows = "".join(f'<div style="padding:6px 10px;background:#fff;border-radius:6px;margin-bottom:4px;"><span style="color:#999;">[{a["date"]}]</span> {a["title"]} <span style="color:#2980b9;font-size:11px;">({a.get("type","")})</span></div>' for a in announcements[:5])
        ann_html = f"""
        <div style="margin-bottom:20px;">
            <h3 style="color:#333;border-bottom:2px solid #eee;padding-bottom:8px;">&#x1F4CB; 近期公告</h3>
            {ann_rows}
        </div>"""

    # === 组装完整报告 ===
    pos_count = overall.get("positive_count", 0)
    neg_count = overall.get("negative_count", 0)
    neu_count = overall.get("neutral_count", 0)
    vol_pct = int(overall.get("volatility", 0) * 100)
    conf_pct = int(overall.get("confidence_index", 0) * 100)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{stock_name}({stock_code}) 市场情绪分析报告</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; background: {bg_gradient}; color: #333; min-height: 100vh; }}
.container {{ max-width: 700px; margin: 0 auto; padding: 20px 15px; }}
.header {{ text-align: center; padding: 30px 0 20px; }}
.header h1 {{ font-size: 24px; margin-bottom: 6px; }}
.header .sub {{ color: #999; font-size: 13px; }}
.score-circle {{ width: 140px; height: 140px; border-radius: 50%; background: conic-gradient({score_color} {score_pct}%, #eee {score_pct}%); display: flex; align-items: center; justify-content: center; margin: 20px auto; position: relative; }}
.score-inner {{ width: 110px; height: 110px; border-radius: 50%; background: white; display: flex; flex-direction: column; align-items: center; justify-content: center; }}
.score-number {{ font-size: 36px; font-weight: 800; color: {score_color}; }}
.score-label {{ font-size: 14px; color: #999; }}
.stats-grid {{ display: flex; justify-content: center; gap: 15px; flex-wrap: wrap; margin-bottom: 20px; }}
.stat-box {{ background: white; padding: 12px 16px; border-radius: 10px; box-shadow: 0 1px 6px rgba(0,0,0,0.06); text-align: center; min-width: 90px; }}
.stat-num {{ font-size: 20px; font-weight: 700; color: #333; }}
.stat-label {{ font-size: 11px; color: #999; margin-top: 2px; }}
.section {{ background: white; border-radius: 12px; padding: 20px; margin-bottom: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.04); }}
.footer {{ text-align: center; padding: 20px; color: #bbb; font-size: 11px; }}
</style>
</head>
<body>
<div class="container">

<div class="header">
    <h1>{stock_name} ({stock_code})</h1>
    <div class="sub">市场情绪分析报告 &middot; {now_str}</div>
</div>

<div class="section">
    <div class="score-circle">
        <div class="score-inner">
            <div class="score-number">{score_pct}</div>
            <div class="score-label">{label}</div>
        </div>
    </div>
    <p style="text-align:center;color:#666;font-size:14px;margin-top:12px;line-height:1.6;">{overall.get("summary", "")}</p>
    <p style="text-align:center;color:#888;font-size:13px;margin-top:6px;">{overall.get("market_expectation", "")}</p>

    <div class="stats-grid">
        <div class="stat-box"><div class="stat-num" style="color:#e74c3c;">{pos_count}</div><div class="stat-label">正面新闻</div></div>
        <div class="stat-box"><div class="stat-num" style="color:#999;">{neu_count}</div><div class="stat-label">中性新闻</div></div>
        <div class="stat-box"><div class="stat-num" style="color:#27ae60;">{neg_count}</div><div class="stat-label">负面新闻</div></div>
        <div class="stat-box"><div class="stat-num">{vol_pct}%</div><div class="stat-label">{overall.get("volatility_label", "")}</div></div>
        <div class="stat-box"><div class="stat-num">{conf_pct}%</div><div class="stat-label">置信度</div></div>
    </div>
</div>

<div class="section">
    <h3 style="color:#333;border-bottom:2px solid #eee;padding-bottom:8px;margin-bottom:12px;">钱 行情概览</h3>
    {quote_rows}
    {market_rows}
    {fund_html}
    {kline_stats}
</div>

<div class="section">
    {topic_html}
</div>

<div class="section">
    {time_html}
</div>

<div class="section">
    {risk_html}
</div>

{ann_html if ann_html else ''}

<div class="footer">
    <p>SentimentQuant &middot; 市场情绪量化系统</p>
    <p>免责声明：本报告仅供参考，不构成投资建议</p>
</div>

</div>
</body>
</html>"""
    return html


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
    try:
        data = request.get_json()
        stock_code = data.get("code", "").strip()
        stock_name = data.get("name", "").strip()
        cfg = _get_config()
        days = int(data.get("days", cfg["DEFAULT_LOOKBACK_DAYS"]))
        max_news = int(data.get("max_news", 20))
        if not stock_code:
            return jsonify({"success": False, "error": "请输入股票代码"})

        f = _get_fetchers()
        if not stock_name:
            info = f["get_stock_by_code"](stock_code)
            if info:
                stock_name = info.get("name", stock_code)

        news_list = f["get_stock_news"](stock_code, days=days, max_news=max_news)
        if not news_list:
            return jsonify({"success": False, "error": f"未找到 {stock_code} 的相关新闻"})

        analyzer = _get_sentiment_analyzer()
        if analyzer is None:
            return jsonify({"success": False, "error": "情感分析引擎初始化失败，请稍后重试"})
        sentiment_result = analyzer.analyze(news_list)
        del news_list
        _cleanup()

        kline_data = f["get_kline_data"](stock_code, days=max(60, days))
        quote = f["get_real_time_quote"](stock_code)
        market = f["get_market_index"]()
        fund_flow = f["get_fund_flow"](stock_code, days=min(5, days))
        announcements = f["get_company_announcements"](stock_code, days=days)

        if IS_RENDER:
            # 云端用纯 HTML 报告（无 Plotly 依赖）
            report_html = _generate_cloud_report(
                stock_code=stock_code, stock_name=stock_name,
                sentiment_result=sentiment_result, kline_data=kline_data,
                quote=quote, market=market, fund_flow=fund_flow,
                announcements=announcements
            )
            report_path = _get_report_dir() / f"sentiment_{stock_code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            try:
                report_path.write_text(report_html, encoding="utf-8")
            except Exception:
                report_path = None
        else:
            gen = _get_report_generator()
            report_path = gen.generate_sentiment_report(
                stock_code=stock_code, stock_name=stock_name,
                sentiment_result=sentiment_result, news_list=[],
                kline_data=kline_data, quote=quote, market=market,
                fund_flow=fund_flow, announcements=announcements
            )

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
            "news_count": sentiment_result.get("total_count", 0),
            "risk_level": sentiment_result.get("risk_analysis", {}).get("risk_level", "未知"),
            "impact_level": sentiment_result.get("impact_analysis", {}).get("importance_level", "未知"),
            "price": quote.get("price", "--") if quote else "--",
            "pct_change": quote.get("pct_change", "--") if quote else "--",
            "report_url": f"/reports/view/{Path(report_path).name}" if report_path else None
        }
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
    if IS_RENDER:
        return jsonify({"success": False, "error": "回测功能仅支持桌面版，云端暂不可用"})
    try:
        from core.backtest import compare_strategies
        data = request.get_json()
        stock_code = data.get("code", "").strip()
        stock_name = data.get("name", "").strip()
        cfg = _get_config()
        lookback = int(data.get("lookback", cfg["DEFAULT_LOOKBACK_DAYS"]))
        capital = float(data.get("capital", cfg["DEFAULT_START_CAPITAL"]))
        if not stock_code:
            return jsonify({"success": False, "error": "请输入股票代码"})
        if not stock_name:
            f = _get_fetchers()
            info = f["get_stock_by_code"](stock_code)
            if info:
                stock_name = info.get("name", stock_code)
        results = compare_strategies(stock_code=stock_code, stock_name=stock_name, capital=capital, lookback_days=lookback)
        all_results = list(results.values())
        gen = _get_report_generator()
        report_path = gen.generate_backtest_report(results=all_results, stock_name_map={r.stock_code: r.stock_name for r in all_results})
        summary = []
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
        best = max(summary, key=lambda x: x["total_return"])
        del results, all_results
        _cleanup()
        return jsonify({"success": True, "data": summary, "best_strategy": best, "stock_code": stock_code, "stock_name": stock_name, "report_url": f"/reports/view/{Path(report_path).name}"})
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
