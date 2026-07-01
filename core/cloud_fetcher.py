"""
云端轻量数据获取模块 - 纯 requests 实现，零 akshare/pandas 依赖
用于 Render 免费 512MB 实例，避免 akshare(250MB) + pandas(100MB) OOM
"""

import json
import time
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional

# ======================================================================
# 配置
# ======================================================================

DATA_DIR = Path(__file__).parent.parent / "data"
STOCK_LIST_CACHE = DATA_DIR / "stock_list_cache"
NEWS_CACHE_DIR = DATA_DIR / "news_cache"
REQUEST_TIMEOUT = 15
DEFAULT_LOOKBACK_DAYS = 7
MAX_NEWS_PER_STOCK = 50
NEWS_PER_DAY = 10


def _get_headers():
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://quote.eastmoney.com/",
    }


def _get_secid(code: str) -> str:
    """获取东方财富 secid"""
    if code.startswith("6"):
        return f"1.{code}"
    elif code.startswith(("0", "3")):
        return f"0.{code}"
    return f"1.{code}"


# ======================================================================
# 股票搜索
# ======================================================================

def search_stocks(query: str, top_n: int = 20) -> List[Dict]:
    """搜索股票（东方财富搜索接口）"""
    try:
        import requests
        url = "https://searchapi.eastmoney.com/api/suggest/get"
        params = {
            "input": query,
            "type": 14,
            "token": "D43BF722C8E33BDC906FB84D85E326E8",
            "count": str(top_n),
        }
        resp = requests.get(url, params=params, headers=_get_headers(), timeout=10)
        data = resp.json()
        items = data.get("QuotationCodeTable", {}).get("Data", [])
        results = []
        for item in items:
            code = item.get("Code", "")
            name = item.get("Name", "")
            if code and name:
                results.append({"code": code, "name": name})
        if results:
            return results[:top_n]
    except Exception:
        pass
    return []


def get_stock_by_code(code: str) -> Optional[Dict]:
    """根据代码获取股票信息"""
    results = search_stocks(code, top_n=5)
    for r in results:
        if r["code"] == code or r["code"].endswith(code[-6:]):
            return r
    return {"code": code, "name": code}


# ======================================================================
# 新闻获取（东方财富新闻列表 API）
# ======================================================================

def get_stock_news(stock_code: str, days: int = DEFAULT_LOOKBACK_DAYS,
                   max_news: int = MAX_NEWS_PER_STOCK, use_cache: bool = True) -> List[Dict]:
    """获取股票相关新闻"""
    import requests
    import re

    code = stock_code[-6:] if len(stock_code) > 6 else stock_code
    cutoff_date = datetime.now() - timedelta(days=days)
    news_list = []

    try:
        market_flag = "1" if code.startswith("6") else "0"
        secid = f"{market_flag}.{code}"
        url = (
            f"https://np-listapi.eastmoney.com/comm/web/getListInfo"
            f"?cb=&client=web&type=1"
            f"&mTypeAndCode={secid}"
            f"&pageSize={max_news}&pageIndex=1"
            f"&token=&startTime=&endTime="
        )
        resp = requests.get(url, headers=_get_headers(), timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == 1:
                for art in data.get("data", {}).get("list", []):
                    title = art.get("Art_Title", "").strip()
                    if not title:
                        continue
                    title = re.sub(r"<[^>]+>", "", title)

                    pub_time_str = art.get("Art_ShowTime", "")
                    if not pub_time_str:
                        continue
                    try:
                        pub_time = datetime.strptime(pub_time_str, "%Y-%m-%d %H:%M:%S")
                    except (ValueError, TypeError):
                        continue
                    if pub_time < cutoff_date:
                        continue

                    art_url = art.get("Art_Url", art.get("Art_OriginUrl", ""))
                    news_list.append({
                        "title": title[:200],
                        "content": title[:2000],
                        "publish_time": pub_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "date": pub_time.strftime("%Y-%m-%d"),
                        "source": "东方财富",
                        "url": art_url if art_url.startswith("http") else "",
                    })
    except Exception:
        pass

    # 去重 + 按日期分组
    seen = set()
    unique = []
    for n in news_list:
        key = (n["title"][:30], n["date"])
        if key not in seen:
            seen.add(key)
            unique.append(n)
    unique.sort(key=lambda x: x["publish_time"], reverse=True)

    date_groups: Dict[str, List] = {}
    for item in unique:
        d = item["date"]
        date_groups.setdefault(d, [])
        if len(date_groups[d]) < NEWS_PER_DAY:
            date_groups[d].append(item)

    sorted_dates = sorted(date_groups.keys(), reverse=True)[:days]
    result = []
    for d in sorted_dates:
        result.extend(date_groups[d])

    return result[:max_news]


def batch_get_news(stock_codes: List[str], days: int = DEFAULT_LOOKBACK_DAYS,
                   max_news: int = MAX_NEWS_PER_STOCK, desc: str = "获取新闻") -> Dict[str, List[Dict]]:
    """批量获取多只股票新闻"""
    result = {}
    for code in stock_codes:
        news = get_stock_news(code, days=days, max_news=max_news)
        result[code] = news
        time.sleep(0.3)
    return result


# ======================================================================
# K线数据（东方财富 push2his API）
# ======================================================================

def get_kline_data(stock_code: str, period: str = "daily", days: int = 60) -> Optional[List[Dict]]:
    """获取K线数据，返回 List[Dict]"""
    import requests

    try:
        secid = _get_secid(stock_code)
        klt = {"daily": 101, "weekly": 102, "monthly": 103}.get(period, 101)

        url = (
            f"https://push2his.eastmoney.com/api/qt/stock/kline/get"
            f"?secid={secid}"
            f"&fields1=f1,f2,f3,f4,f5,f6"
            f"&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
            f"&klt={klt}&fqt=1"
            f"&end=20500101&lmt={days + 30}"
        )

        resp = requests.get(url, headers=_get_headers(), timeout=8)
        data = resp.json()
        klines = data.get("data", {}).get("klines", [])

        records = []
        for line in klines:
            parts = line.split(",")
            if len(parts) < 11:
                continue
            records.append({
                "date": parts[0],
                "open": float(parts[1]),
                "close": float(parts[2]),
                "high": float(parts[3]),
                "low": float(parts[4]),
                "volume": float(parts[5]),
                "amount": float(parts[6]),
            })

        records.sort(key=lambda x: x["date"])
        return records[-days:] if len(records) > days else records

    except Exception:
        return None


# ======================================================================
# 实时行情（东方财富 push2 API）
# ======================================================================

def get_real_time_quote(stock_code: str) -> Optional[Dict]:
    """获取实时行情"""
    import requests

    try:
        secid = _get_secid(stock_code)
        url = (
            f"https://push2.eastmoney.com/api/qt/stock/get"
            f"?secid={secid}"
            f"&fields=f43,f44,f45,f46,f47,f48,f50,f51,f52,f55,f57,f58,f115,f117,f162,f167,f168,f169,f170,f171"
        )
        resp = requests.get(url, headers=_get_headers(), timeout=10)
        data = resp.json()
        d = data.get("data", {})
        if not d:
            return None

        # 安全解析数值字段（防止 None/非数字值导致 TypeError 或 NaN）
        def _safe_field(key, divisor=100, default=0):
            raw = d.get(key)
            if raw is None:
                return default
            try:
                val = float(raw)
                import math
                if math.isnan(val) or math.isinf(val):
                    return default
                return val / divisor if divisor else val
            except (ValueError, TypeError):
                return default

        price = _safe_field("f43")
        pre_close = _safe_field("f44")
        high = _safe_field("f45")
        low = _safe_field("f46")
        open_p = _safe_field("f47")
        volume = _safe_field("f48")
        amount = _safe_field("f50", divisor=0)
        turnover = _safe_field("f168")
        pe = _safe_field("f162", default=None)
        pb = _safe_field("f167", default=None)

        change = price - pre_close
        pct_change = round(change / pre_close * 100, 2) if pre_close > 0 else 0

        return {
            "code": stock_code, "name": "",
            "price": round(float(price), 2) if price else 0,
            "change": round(float(change), 2),
            "pct_change": float(pct_change),
            "volume": float(volume),
            "amount": float(amount) if amount else 0,
            "high": round(float(high), 2),
            "low": round(float(low), 2),
            "open": round(float(open_p), 2),
            "pre_close": round(float(pre_close), 2),
            "turnover": float(turnover),
            "pe": float(pe) if pe else None,
            "pb": float(pb) if pb else None,
            "market_cap": float(d.get("f116", d.get("f20", 0)) or 0),
            "circulating_cap": float(d.get("f117", d.get("f21", 0)) or 0),
        }
    except Exception:
        return None


# ======================================================================
# 大盘指数
# ======================================================================

def get_market_index() -> Optional[Dict]:
    """获取三大指数行情（并发优化版）"""
    import requests
    from concurrent.futures import ThreadPoolExecutor, as_completed

    indices = {
        "上证指数": "1.000001",
        "深证成指": "0.399001",
        "创业板指": "0.399006",
    }

    result = {}

    def _fetch_one(name, secid):
        try:
            url = (
                f"https://push2.eastmoney.com/api/qt/stock/get"
                f"?secid={secid}"
                f"&fields=f43,f44,f45,f46,f47,f48,f50,f51,f52,f55,f57,f58,f115,f117,f162,f167,f168,f169,f170,f171"
            )
            resp = requests.get(url, headers=_get_headers(), timeout=6)
            data = resp.json()
            d = data.get("data", {})
            if not d:
                return name, None
            price = d.get("f43", 0) / 100 if d.get("f43") else 0
            pre_close = d.get("f44", 0) / 100 if d.get("f44") else 0
            change = price - pre_close
            pct = change / pre_close * 100 if pre_close else 0
            return name, {
                "price": round(float(price), 2),
                "change": round(float(change), 2),
                "pct_change": round(float(pct), 2),
            }
        except Exception:
            return name, None

    # 并发请求 3 个指数（总耗时 ~ 最慢的 1 个，而非串行求和）
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(_fetch_one, n, s): n for n, s in indices.items()}
        for future in as_completed(futures, timeout=10):
            try:
                name, data = future.result()
                if data:
                    result[name] = data
            except Exception:
                pass
    return result if result else None


# ======================================================================
# 资金流向（东方财富 API）
# ======================================================================

def get_fund_flow(stock_code: str, days: int = 5) -> Optional[Dict]:
    """获取个股资金流向"""
    import requests

    try:
        secid = _get_secid(stock_code)
        url = (
            f"https://push2.eastmoney.com/api/qt/stock/get"
            f"?secid={secid}"
            f"&fields=f62,f64,f66,f69,f70,f72,f74,f78,f184,f184,f66,f72,f78"
        )
        resp = requests.get(url, headers=_get_headers(), timeout=10)
        data = resp.json()
        d = data.get("data", {})

        if not d:
            return {"stock_code": stock_code, "main_net_avg": 0, "records": []}

        main_net = d.get("f62", 0) / 1e8 if d.get("f62") else 0
        return {
            "stock_code": stock_code,
            "main_net_avg": round(main_net, 2),
            "total_net_avg": round(main_net, 2),
            "net_direction": "流入" if main_net > 0 else "流出",
            "records": [{"date": datetime.now().strftime("%Y%m%d"),
                         "main_net": round(main_net, 2)}],
        }
    except Exception:
        return {"stock_code": stock_code, "main_net_avg": 0, "records": []}


# ======================================================================
# 公司公告
# ======================================================================

def get_company_announcements(stock_code: str, days: int = 7) -> List[Dict]:
    """获取公司公告（东方财富公告接口）"""
    import requests

    try:
        code = stock_code[-6:] if len(stock_code) > 6 else stock_code
        market = "SH" if code.startswith("6") else "SZ"
        org_id = f"gset{market}{code}01"

        url = (
            f"https://np-anotice-stock.eastmoney.com/api/security/ann"
            f"?page_size=10&page_index=1&ann_type=SHA&stock_list={org_id}"
        )
        resp = requests.get(url, headers=_get_headers(), timeout=10)
        data = resp.json()
        items = data.get("data", {}).get("list", [])
        cutoff = datetime.now() - timedelta(days=days)

        anns = []
        for item in items:
            try:
                ann_date = datetime.strptime(
                    item.get("notice_date", ""), "%Y-%m-%d %H:%M:%S"
                )
                if ann_date < cutoff:
                    continue
                anns.append({
                    "title": item.get("title_ch", item.get("title", "")),
                    "date": ann_date.strftime("%Y-%m-%d"),
                    "type": item.get("ann_type", ""),
                })
            except Exception:
                continue
        return anns[:10]
    except Exception:
        return []
