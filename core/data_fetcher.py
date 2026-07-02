"""
数据获取模块 - 通过AKShare接口获取A股数据
提供带重试、带缓存的统一数据访问层
"""
import time
import json
import re
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Callable, Any
from tqdm import tqdm
from config import (
    DATA_DIR, NEWS_CACHE_DIR, STOCK_LIST_CACHE,
    REQUEST_TIMEOUT, MAX_RETRIES, RETRY_BACKOFF,
    MAX_NEWS_PER_STOCK, DEFAULT_LOOKBACK_DAYS,
    NEWS_PER_DAY
)
from utils.retry import retry_with_backoff, fetch_with_fallback
from utils.cache import FileCache, MemoryCache


# ======================================================================
# 全局缓存实例
# ======================================================================
_stock_cache = MemoryCache(max_size=5000)
_news_file_cache = FileCache(NEWS_CACHE_DIR, valid_days=1)


# ======================================================================
# 工具函数
# ======================================================================

@retry_with_backoff(max_retries=3, base_delay=1.0, backoff_factor=2.0,
                    on_retry=lambda a, e, s: print(f"  ⚠️ 第{a}次重试（{e.__class__.__name__}），等待{s:.1f}秒..."))
def _safe_ak_call(func: Callable, *args, **kwargs) -> Any:
    """安全的AKShare调用封装"""
    return func(*args, **kwargs)


# ======================================================================
# 股票列表
# ======================================================================

def get_all_stocks(force_refresh: bool = False) -> pd.DataFrame:
    """
    获取全市场A股列表

    Args:
        force_refresh: 是否强制刷新缓存

    Returns:
        pd.DataFrame: 包含 code 和 name 列的股票列表
    """
    cache_file = STOCK_LIST_CACHE / "all_stocks.json"

    if not force_refresh and cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if (datetime.now() - datetime.fromisoformat(data["_cached_at"])).days <= 7:
                return pd.DataFrame(data["stocks"])
        except Exception:
            pass

    try:
        import akshare as ak
        df = _safe_ak_call(ak.stock_info_a_code_name)
        df = df.rename(columns={"code": "code", "name": "name"})
        data = {
            "_cached_at": datetime.now().isoformat(),
            "stocks": df.to_dict(orient="records"),
        }
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return df
    except Exception as e:
        if cache_file.exists():
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return pd.DataFrame(data["stocks"])
        raise RuntimeError(f"无法获取股票列表且无缓存: {e}")



def search_stocks(query: str, top_n: int = 20) -> List[Dict]:
    """
    搜索股票（按代码或名称）

    Args:
        query: 搜索关键词
        top_n: 最多返回数量

    Returns:
        List[Dict]: [{"code": "000001", "name": "平安银行"}, ...]
    """
    df = _stock_cache.get_or_set("all_stocks", lambda: get_all_stocks())

    if query.isdigit():
        matched = df[df["code"].str.contains(query)]
    else:
        matched = df[df["name"].str.contains(query)]

    result = matched.head(top_n).to_dict(orient="records")

    # 精确匹配排前面
    exact_code = df[df["code"] == query]
    if not exact_code.empty:
        result = exact_code.to_dict(orient="records") + [
            r for r in result if r["code"] != query
        ][: top_n - 1]

    return result


def get_stock_by_code(code: str) -> Optional[Dict]:
    """根据股票代码获取股票信息"""
    df = _stock_cache.get_or_set("all_stocks", lambda: get_all_stocks())
    matched = df[df["code"] == code]
    if matched.empty:
        return None
    row = matched.iloc[0]
    return {"code": row["code"], "name": row["name"]}


# ======================================================================
# 新闻获取
# ======================================================================

def get_stock_news(
    stock_code: str,
    days: int = DEFAULT_LOOKBACK_DAYS,
    max_news: int = MAX_NEWS_PER_STOCK,
    use_cache: bool = True,
) -> List[Dict]:
    """
    获取股票相关新闻（直接调用东方财富新闻列表API）

    Args:
        stock_code: 股票代码（如 "000001" 或 "sh000001"）
        days: 回溯天数
        max_news: 最大新闻条数
        use_cache: 是否使用缓存

    Returns:
        List[Dict]: 新闻列表
    """
    # 标准化股票代码：取后6位
    code = stock_code[-6:] if len(stock_code) > 6 else stock_code
    cache_key = f"news_{code}_{days}_{max_news}"

    if use_cache:
        cached = _news_file_cache.get(cache_key)
        if cached is not None:
            return cached

    cutoff_date = datetime.now() - timedelta(days=days)
    news_list = []

    # ===== 直接调用东方财富新闻列表API =====
    try:
        import requests
        import json
        import re

        # secid: 沪市=1, 深市=0
        market_flag = "1" if code.startswith("6") else "0"
        secid = f"{market_flag}.{code}"

        url = (
            f"https://np-listapi.eastmoney.com/comm/web/getListInfo"
            f"?cb=&client=web&type=1"
            f"&mTypeAndCode={secid}"
            f"&pageSize={max_news}&pageIndex=1"
            f"&token=&startTime=&endTime="
        )
        headers = {
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://data.eastmoney.com/",
        }

        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == 1:
                articles = data.get("data", {}).get("list", [])
                for art in articles:
                    title = art.get("Art_Title", "").strip()
                    if not title:
                        continue
                    title_clean = re.sub(r"<[^>]+>", "", title)

                    pub_time_str = art.get("Art_ShowTime", "")
                    if not pub_time_str:
                        continue
                    try:
                        pub_time = datetime.strptime(pub_time_str, "%Y-%m-%d %H:%M:%S")
                    except (ValueError, TypeError):
                        continue

                    if pub_time < cutoff_date:
                        continue

                    url = art.get("Art_Url", art.get("Art_OriginUrl", ""))

                    news_list.append({
                        "title": title_clean[:200],
                        "content": title_clean[:2000],
                        "publish_time": pub_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "date": pub_time.strftime("%Y-%m-%d"),
                        "source": "东方财富",
                        "url": url if url.startswith("http") else "",
                    })

                print(f"  东方财富API获取到 {len(news_list)} 条新闻")
            else:
                print(f"  东方财富API返回异常: code={data.get('code')}")
    except Exception as e:
        print(f"  新闻API获取失败: {e}")

    # ===== 处理去重和分组 =====
    result = _deduplicate_and_group(news_list, days)

    if use_cache:
        _news_file_cache.set(cache_key, result)

    return result[:max_news]


def _parse_akshare_news(news_df, days: int) -> List[Dict]:
    """解析AKShare返回的新闻DataFrame"""
    cutoff_date = datetime.now() - timedelta(days=days)
    news_list = []

    for _, row in news_df.iterrows():
        try:
            pub_time_str = str(row.get("发布时间", ""))
            if not pub_time_str or pub_time_str == "nan":
                continue

            pub_time = None
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S"):
                try:
                    pub_time = datetime.strptime(pub_time_str, fmt)
                    break
                except ValueError:
                    continue
            if pub_time is None or pub_time < cutoff_date:
                continue

            title = str(row.get("新闻标题", "")).strip()
            content = str(row.get("新闻内容", "")).strip()
            if not content or content == "nan":
                content = title
            if len(content) < 10:
                continue

            source = str(row.get("文章来源", ""))
            url = str(row.get("新闻链接", ""))
            news_list.append({
                "title": title,
                "content": content,
                "publish_time": pub_time_str,
                "date": pub_time_str.split()[0] if " " in pub_time_str else pub_time_str,
                "source": source.strip() if source != "nan" else "未知",
                "url": url.strip() if url != "nan" else "",
            })
        except Exception:
            continue

    return _deduplicate_and_group(news_list, days)


def _fetch_news_via_api(stock_code: str, days: int) -> List[Dict]:
    """
    通过东方财富新闻搜索API获取新闻

    使用东方财富的搜索接口：https://search-api-web.eastmoney.com/search/jsonp
    """
    import requests
    import json
    import re

    cutoff_date = datetime.now() - timedelta(days=days)
    news_list = []

    # 尝试先获取股票名称
    stock_name = ""
    try:
        info = get_stock_by_code(stock_code)
        if info:
            stock_name = info["name"]
    except Exception:
        pass

    keywords = [stock_code]
    if stock_name:
        keywords.append(stock_name)

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://so.eastmoney.com/",
    }

    for keyword in keywords:
        try:
            url = (
                f"https://so.eastmoney.com/api/suggest/v2?"
                f"input={requests.utils.quote(keyword)}&"
                f"type=14&token=44&count=30"
            )
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code != 200:
                continue

            data = resp.json()
            news_items = _parse_eastmoney_suggest(data, cutoff_date)
            news_list.extend(news_items)
        except Exception:
            continue

    # 去重
    seen = set()
    unique_news = []
    for n in news_list:
        key = n["title"] + n["publish_time"]
        if key not in seen:
            seen.add(key)
            unique_news.append(n)

    return _deduplicate_and_group(unique_news, days)


def _parse_eastmoney_suggest(data: dict, cutoff_date: datetime) -> List[Dict]:
    """解析东方财富suggest接口返回的新闻数据"""
    news_list = []
    try:
        items = data.get("Data", []) or data.get("data", [])
        if isinstance(items, dict):
            items = items.get("items", items.get("list", []))

        for item in items:
            title = item.get("title", item.get("Title", item.get("Art_Title", "")))
            content = item.get("content", item.get("Content", item.get("Art_Content", "")))
            pub_time_str = item.get("date", item.get("Date", item.get("Art_Date", "")))
            source = item.get("source", item.get("Source", item.get("Media", "东方财富")))
            url = item.get("url", item.get("Url", item.get("Art_Url", "")))

            if not title:
                continue

            # 清理HTML标签
            import re
            title = re.sub(r"<[^>]+>", "", title).strip()
            content = re.sub(r"<[^>]+>", "", content).strip() if content else title
            if len(content) < 10:
                content = title

            # 解析时间
            pub_time = None
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S",
                        "%Y-%m-%dT%H:%M:%S", "%Y年%m月%d日 %H:%M"):
                try:
                    pub_time = datetime.strptime(pub_time_str, fmt)
                    break
                except (ValueError, TypeError):
                    continue
            if pub_time is None or pub_time < cutoff_date:
                continue

            news_list.append({
                "title": title[:200],
                "content": content[:2000],
                "publish_time": pub_time.strftime("%Y-%m-%d %H:%M:%S"),
                "date": pub_time.strftime("%Y-%m-%d"),
                "source": source if source and source != "nan" else "东方财富",
                "url": url if url and url.startswith("http") else "",
            })
    except Exception:
        pass

    return news_list


def _deduplicate_and_group(news_list: List[Dict], days: int) -> List[Dict]:
    """去重并按日期分组"""
    # 去重
    seen_titles = set()
    unique = []
    for n in news_list:
        t = n["title"][:30]
        if t not in seen_titles:
            seen_titles.add(t)
            unique.append(n)

    # 按时间排序（最新的在前）
    unique.sort(key=lambda x: x["publish_time"], reverse=True)

    # 按日期分组，每天最多NEWS_PER_DAY条
    date_groups: Dict[str, List] = {}
    for item in unique:
        d = item["date"]
        if d not in date_groups:
            date_groups[d] = []
        if len(date_groups[d]) < NEWS_PER_DAY:
            date_groups[d].append(item)

    # 按日期排序，取最近days天
    sorted_dates = sorted(date_groups.keys(), reverse=True)[:days]
    result = []
    for d in sorted_dates:
        result.extend(date_groups[d])

    return result


# ======================================================================
# 行情数据
# ======================================================================

def get_kline_data(
    stock_code: str,
    period: str = "daily",
    days: int = 60,
) -> Optional[pd.DataFrame]:
    """
    获取K线数据（通过东方财富 push2his API）

    Args:
        stock_code: 股票代码
        period: 周期 ("daily", "weekly", "monthly")
        days: 获取最近N天的数据

    Returns:
        Optional[pd.DataFrame]: K线数据
    """
    try:
        import requests

        # 判断市场代码
        if stock_code.startswith("6"):
            secid = f"1.{stock_code}"
        elif stock_code.startswith(("0", "3")):
            secid = f"0.{stock_code}"
        else:
            secid = f"1.{stock_code}"

        klt = {"daily": 101, "weekly": 102, "monthly": 103}.get(period, 101)

        @retry_with_backoff(max_retries=3, base_delay=1.0,
                            on_retry=lambda a, e, s: print(f"    ⚠️ K线获取第{a}次重试..."))
        def _fetch_kline():
            url = (
                f"https://push2his.eastmoney.com/api/qt/stock/kline/get"
                f"?secid={secid}"
                f"&fields1=f1,f2,f3,f4,f5,f6"
                f"&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
                f"&klt={klt}&fqt=1"
                f"&end=20500101&lmt={days + 30}"
            )
            headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"}
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code != 200:
                raise Exception(f"HTTP {resp.status_code}")
            data = resp.json()
            klines = data.get("data", {}).get("klines", [])
            if not klines:
                raise Exception("Empty kline data")
            return klines

        klines = _fetch_kline()

        # 解析K线数据
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
                "amplitude": float(parts[7]),
                "pct_change": float(parts[8]),
                "change": float(parts[9]),
                "turnover": float(parts[10]),
            })

        if not records:
            return None

        df = pd.DataFrame(records)
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date", ascending=True).reset_index(drop=True)
        return df.tail(days)

    except Exception as e:
        print(f"  获取K线失败: {e}")
        return None


def get_real_time_quote(stock_code: str) -> Optional[Dict]:
    """
    获取实时行情（通过东方财富push2 API）

    Args:
        stock_code: 股票代码

    Returns:
        Optional[Dict]: 实时行情数据
    """
    try:
        import requests

        # 判断市场代码
        if stock_code.startswith("6"):
            secid = f"1.{stock_code}"
        elif stock_code.startswith(("0", "3")):
            secid = f"0.{stock_code}"
        else:
            secid = f"1.{stock_code}"

        url = (
            f"https://push2.eastmoney.com/api/qt/stock/get"
            f"?secid={secid}"
            f"&fields=f43,f44,f45,f46,f47,f48,f50,f51,f52,f55,f57,f58,f115,f117,f162,f167,f168,f169,f170,f171"
        )
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"}

        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return None

        data = resp.json()
        d = data.get("data", {})
        if not d:
            return None

        price = d.get("f43", 0) / 100 if d.get("f43") else 0
        if price == 0:
            # 价格字段可能是整数
            price = d.get("f43", 0)

        pre_close = d.get("f44", 0) / 100 if d.get("f44") else 0
        high = d.get("f45", 0) / 100 if d.get("f45") else 0
        low = d.get("f46", 0) / 100 if d.get("f46") else 0
        open_p = d.get("f47", 0) / 100 if d.get("f47") else 0

        volume = d.get("f48", 0) / 100 if d.get("f48") else 0
        amount = d.get("f49", d.get("f50", 0))  # 成交额

        change = price - pre_close
        pct_change = change / pre_close * 100 if pre_close else 0
        turnover = d.get("f168", 0) / 100 if d.get("f168") else 0
        pe = d.get("f162", 0) / 100 if d.get("f162") else None
        pb = d.get("f167", 0) / 100 if d.get("f167") else None
        market_cap = d.get("f116", d.get("f20", 0))
        circ_cap = d.get("f117", d.get("f21", 0))

        return {
            "code": stock_code,
            "name": "",
            "price": round(float(price), 2),
            "change": round(float(change), 2),
            "pct_change": round(float(pct_change), 2),
            "volume": float(volume),
            "amount": float(amount),
            "high": round(float(high), 2),
            "low": round(float(low), 2),
            "open": round(float(open_p), 2),
            "pre_close": round(float(pre_close), 2),
            "turnover": float(turnover),
            "pe": float(pe) if pe else None,
            "pb": float(pb) if pb else None,
            "market_cap": float(market_cap),
            "circulating_cap": float(circ_cap),
        }

    except Exception as e:
        print(f"  获取实时行情失败: {e}")
        return None


def get_market_index() -> Optional[Dict]:
    """
    获取大盘指数行情
    """
    import requests
    try:
        import akshare as ak
        indices = {
            "上证指数": "sh000001",
            "深证成指": "sz399001",
            "创业板指": "sz399006",
        }
        result = {}
        for name, code in indices.items():
            try:
                data = ak.stock_zh_index_daily(symbol=code)
                if data is not None and not data.empty:
                    latest = data.iloc[-1]
                    prev = data.iloc[-2]
                    change = latest["close"] - prev["close"]
                    pct = change / prev["close"] * 100
                    result[name] = {"price": float(latest["close"]), "change": float(change), "pct_change": float(pct)}
            except Exception:
                continue
        if result:
            return result
    except Exception:
        pass
    # 回退：东方财富HTTP接口（无需akshare）
    indices_http = {"上证指数": "1.000001", "深证成指": "0.399001", "创业板指": "0.399006"}
    result = {}
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"}
    for name, secid in indices_http.items():
        try:
            url = f"https://push2.eastmoney.com/api/qt/stock/get?secid={secid}&fields=f43,f44,f45,f46,f47"
            resp = requests.get(url, headers=headers, timeout=10)
            d = resp.json().get("data", {})
            if d:
                price = d.get("f43", 0) / 100 if d.get("f43") else 0
                pre_close = d.get("f44", 0) / 100 if d.get("f44") else 0
                result[name] = {"price": round(float(price), 2), "change": round(float(price - pre_close), 2), "pct_change": round(float((price - pre_close) / pre_close * 100), 2) if pre_close else 0}
        except Exception:
            continue
    return result if result else None



# ======================================================================
# 批量获取（带进度条）
# ======================================================================

def batch_get_news(
    stock_codes: List[str],
    days: int = DEFAULT_LOOKBACK_DAYS,
    max_news: int = MAX_NEWS_PER_STOCK,
    desc: str = "获取新闻",
) -> Dict[str, List[Dict]]:
    """
    批量获取多只股票新闻（带进度条）

    Args:
        stock_codes: 股票代码列表
        days: 回溯天数
        max_news: 每只股票最大新闻数
        desc: 进度条描述

    Returns:
        Dict[str, List[Dict]]: {股票代码: 新闻列表}
    """
    result = {}
    for code in tqdm(stock_codes, desc=desc, unit="只"):
        news = get_stock_news(code, days=days, max_news=max_news)
        result[code] = news
        time.sleep(0.3)  # 避免请求过快被限流
    return result


# ======================================================================
# ✨ 新增: 资金流向 + 公司公告 + 技术指标
# ======================================================================

@retry_with_backoff(max_retries=3, base_delay=1.0, backoff_factor=2.0)
def get_fund_flow(stock_code: str, days: int = 5) -> Optional[Dict]:
    """获取个股资金流向"""
    import requests
    try:
        import akshare as ak
        # ... 原有akshare逻辑保持不变 ...
        market_id = "1" if stock_code.startswith("6") else "0"
        full_code = f"{market_id}.{stock_code}"
        result = {"stock_code": stock_code, "days": days, "records": []}
        total_main = 0.0
        count = 0
        for day_offset in range(min(days, 10)):
            try:
                df = ak.stock_individual_fund_flow(stock=stock_code, market="sh" if stock_code.startswith("6") else "sz")
                if df is not None and len(df) > 0:
                    latest = df.iloc[-1]
                    main_in = float(latest.get("主力净流入", latest.get("主力净流入-净额", 0)))
                    total_main += main_in
                    count += 1
            except Exception:
                continue
        avg = round(total_main / max(count, 1), 2)
        result["main_net_avg"] = avg
        result["total_net_avg"] = avg
        result["net_direction"] = "流入" if avg > 0 else "流出"
        result["records"] = [{"date": "", "main_net": avg}]
        return result
    except Exception:
        pass
    # 回退：东方财富HTTP接口
    try:
        secid = f"{'1' if stock_code.startswith('6') else '0'}.{stock_code}"
        url = f"https://push2.eastmoney.com/api/qt/stock/get?secid={secid}&fields=f62,f64,f66,f69,f70,f72,f74,f78"
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"}
        resp = requests.get(url, headers=headers, timeout=10)
        d = resp.json().get("data", {})
        main_net = d.get("f62", 0) / 1e8 if d.get("f62") else 0
        return {"stock_code": stock_code, "main_net_avg": round(main_net, 2), "total_net_avg": round(main_net, 2), "net_direction": "流入" if main_net > 0 else "流出", "records": [{"date": "", "main_net": round(main_net, 2)}]}
    except Exception:
        return {"stock_code": stock_code, "main_net_avg": 0, "total_net_avg": 0, "net_direction": "流出", "records": []}
        
def get_company_announcements(stock_code: str, days: int = 7) -> List[Dict]:
    """获取公司公告"""
    import requests
    try:
        import akshare as ak
        df = ak.stock_notice_report(symbol="sh" if stock_code.startswith("6") else "sz", date="")
        if df is not None and len(df) > 0:
            cutoff = datetime.now() - timedelta(days=days)
            anns = []
            for _, row in df.iterrows():
                try:
                    ann_date = pd.to_datetime(row.get("公告日期", row.get("notice_date", "")))
                    if ann_date >= cutoff:
                        anns.append({"title": str(row.get("公告标题", row.get("notice_title", ""))), "date": ann_date.strftime("%Y-%m-%d"), "type": str(row.get("公告类型", ""))})
                except Exception:
                    continue
            return anns[:10]
    except Exception:
        pass
    # 回退：东方财富公告接口
    try:
        code = stock_code[-6:] if len(stock_code) > 6 else stock_code
        market = "SH" if code.startswith("6") else "SZ"
        org_id = f"gset{market}{code}01"
        url = f"https://np-anotice-stock.eastmoney.com/api/security/ann?page_size=10&page_index=1&ann_type=SHA&stock_list={org_id}"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=10)
        data = resp.json()
        items = data.get("data", {}).get("list", [])
        cutoff = datetime.now() - timedelta(days=days)
        anns = []
        for item in items:
            try:
                ann_date = datetime.strptime(item.get("notice_date", ""), "%Y-%m-%d %H:%M:%S")
                if ann_date >= cutoff:
                    anns.append({"title": item.get("title_ch", item.get("title", "")), "date": ann_date.strftime("%Y-%m-%d"), "type": item.get("ann_type", "")})
            except Exception:
                continue
        return anns[:10]
    except Exception:
        return []


def calc_tech_indicators(df) -> dict:
    """预计算 MACD/ATR/RSI，返回指标 dict"""
    if df is None or len(df) < 5:
        return {}
    close, high, low = df["close"], df["high"], df["low"]
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    histogram = macd_line - signal_line
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / (avg_loss + 1e-10)
    rsi = 100 - (100 / (1 + rs))
    return {
        "macd_line": macd_line.tolist(), "signal_line": signal_line.tolist(),
        "macd_hist": histogram.tolist(), "atr": atr.tolist(), "rsi": rsi.tolist(),
    }
