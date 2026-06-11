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
        resp = requests.get(url, headers=_get_headers(), timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == 1:
                for art in data.get("data", {}).get("list", []):
                    title = art.get("Art_Title", "").strip()
                    if not title:
                        continue
                    title = re.sub(r"<[^>]+>", "", title)

