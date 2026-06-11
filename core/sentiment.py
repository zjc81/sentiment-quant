"""
情感分析引擎 - 无需API Key的本地中文情感分析

方案说明:
  主方案: SnowNLP (本地运行，基于朴素贝叶斯的sentiment分析)
  备选: 增强关键词分析 (当SnowNLP不可用时的降级方案)
  融合: 主+备加权融合，取置信度高的结果

技术特点:
  - 完全本地运行，无需任何API Key
  - 支持多维度分析（整体、时间、主题、来源、影响、风险）
  - 置信度指数自动计算
  - 结果格式与原DeepSeek方案兼容
"""
import re
import math
import hashlib
import numpy as np
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from collections import defaultdict
from config import (
    POSITIVE_KEYWORDS, NEGATIVE_KEYWORDS,
    SENTIMENT_CACHE_DIR, CACHE_VALID_DAYS,
    MAX_NEWS_PER_STOCK,
)
from utils.cache import FileCache

# ======================================================================
# 主题分类（与原格式兼容）
# ======================================================================
NEWS_TOPICS = {
    "company_operation": "公司经营",
    "financial_performance": "财务表现",
    "market_competition": "市场竞争",
    "product_technology": "产品技术",
    "industry_policy": "行业政策",
    "capital_market": "资本市场",
}


# ======================================================================
# SnowNLP包装器（带备选）
# ======================================================================

class _SentimentBackend:
    """情感分析后端 - 尝试使用SnowNLP，失败时使用关键词方案"""

    def __init__(self):
        self._snownlp_available = False
        self._snownlp = None
        self._load_snownlp()

    def _load_snownlp(self):
        """尝试加载SnowNLP"""
        try:
            from snownlp import SnowNLP
            self._snownlp = SnowNLP
            self._snownlp_available = True
        except ImportError:
            self._snownlp_available = False

    def analyze_text(self, text: str) -> Tuple[float, bool]:
        """
        分析单段文本的情感得分

        Returns:
            Tuple[float, bool]: (得分0-1, 是否使用SnowNLP)
        """
        if self._snownlp_available and len(text) > 10:
            try:
                s = self._snownlp(text)
                score = s.sentiments  # 0-1范围
                return score, True
            except Exception:
                pass

        # 降级：关键词分析
        score = self._keyword_score(text)
        return score, False

    def _keyword_score(self, text: str) -> float:
        """关键词情感打分"""
        pos_count = sum(1 for w in POSITIVE_KEYWORDS if w in text)
        neg_count = sum(1 for w in NEGATIVE_KEYWORDS if w in text)
        total = pos_count + neg_count
        if total == 0:
            return 0.5  # 中性
        raw = (pos_count - neg_count) / (total + 2)  # Laplace平滑
        return max(0.0, min(1.0, (raw + 1) / 2))

    def get_source_reliability(self, source: str) -> float:
        """获取新闻来源的可靠性评分"""
        source_weights = {
            "公告": 1.0,
            "互动易": 0.9,
            "日报": 0.85,
            "新闻": 0.8,
            "时报": 0.8,
            "证券": 0.7,
            "财经": 0.65,
            "金融": 0.6,
            "网": 0.5,
            "自媒体": 0.3,
        }
        for keyword, weight in source_weights.items():
            if keyword in source:
                return weight
        return 0.4  # 默认


_backend = _SentimentBackend()


# ======================================================================
# 情感分析器（主类）
# ======================================================================

class SentimentAnalyzer:
    """
    多维度情感分析器

    输出格式兼容原DeepSeek版本，包含:
    - overall_sentiment: 整体情感
    - time_analysis: 时间趋势
    - topic_analysis: 主题分析
    - source_analysis: 来源分析
    - impact_analysis: 影响力分析
    - risk_analysis: 风险分析
    """

    def __init__(self):
        self.cache = FileCache(SENTIMENT_CACHE_DIR, valid_days=1)

    def analyze(self, news_list: List[Dict]) -> Dict:
        """
        执行完整的多维度情感分析

        Args:
            news_list: 新闻列表

        Returns:
            Dict: 完整分析结果
        """
        if not news_list:
            return self._empty_result()

        # 生成缓存键
        cache_key = self._make_cache_key(news_list)
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        # ===== 逐条分析 =====
        analyzed_items = []
        for news in news_list:
            text = news.get("title", "") + "。 " + news.get("content", "")
            score, is_llm = _backend.analyze_text(text)
            source_weight = _backend.get_source_reliability(news.get("source", ""))
            analyzed_items.append({
                **news,
                "_score": score,
                "_is_snownlp": is_llm,
                "_source_weight": source_weight,
            })

        # ===== 1. 整体情感 =====
        overall_score = np.mean([item["_score"] for item in analyzed_items])
        overall_label = self._score_to_label(overall_score)

        # 投资者情绪指数
        investor_sentiment = self._calc_investor_sentiment(analyzed_items)

        # 置信度
        confidence = self._calc_confidence(analyzed_items)

        # ===== 2. 时间趋势 =====
        time_analysis = self._build_time_analysis(analyzed_items)

        # ===== 3. 主题分析 =====
        topic_analysis = self._build_topic_analysis(analyzed_items)

        # ===== 4. 来源分析 =====
        source_analysis = self._build_source_analysis(analyzed_items)

        # ===== 5. 影响力分析 =====
        impact_analysis = self._build_impact_analysis(analyzed_items)

        # ===== 6. 风险分析 =====
        risk_analysis = self._build_risk_analysis(analyzed_items)

        # ===== 整合 =====
        # ✨ 新增: 情感波动率指标
        scores_array = np.array([it["_score"] for it in analyzed_items])
        sentiment_volatility = float(np.std(scores_array)) if len(scores_array) > 1 else 0.0
        sentiment_range = float(np.max(scores_array) - np.min(scores_array)) if len(scores_array) > 1 else 0.0
        # 变异系数 (CV = std/mean, 衡量相对分散度)
        mean_score = float(np.mean(scores_array)) if len(scores_array) > 0 else 0.5
        cv = sentiment_volatility / mean_score if mean_score > 0 else 0.0
        # 正/中/负 计数及占比
        pos_count = int(np.sum(scores_array > 0.55))
        neg_count = int(np.sum(scores_array < 0.45))
        neutral_count = len(scores_array) - pos_count - neg_count
        pos_ratio = pos_count / len(scores_array) if len(scores_array) > 0 else 0.0
        neg_ratio = neg_count / len(scores_array) if len(scores_array) > 0 else 0.0
        # 波动率标签
        if sentiment_volatility > 0.3:
            vol_label = "高度分歧"
        elif sentiment_volatility > 0.15:
            vol_label = "存在分歧"
        else:
            vol_label = "较为一致"

        result = {
            "overall_sentiment": {
                "score": round(float(overall_score), 4),
                "label": overall_label,
                "summary": self._build_summary(overall_score, overall_label, analyzed_items),
                "market_expectation": self._build_market_expectation(overall_score, analyzed_items),
                "investor_sentiment": investor_sentiment,
                "confidence_index": round(float(confidence), 4),
                # ✨ 波动率指标
                "volatility": round(sentiment_volatility, 4),
                "volatility_label": vol_label,
                "cv": round(cv, 4),
                "score_range": round(sentiment_range, 4),
                "positive_ratio": round(pos_ratio, 4),
                "negative_ratio": round(neg_ratio, 4),
                "positive_count": pos_count,
                "negative_count": neg_count,
                "neutral_count": neutral_count,
            },
            "time_analysis": time_analysis,
            "topic_analysis": topic_analysis,
            "source_analysis": source_analysis,
            "impact_analysis": impact_analysis,
            "risk_analysis": risk_analysis,
        }

        self.cache.set(cache_key, result)
        return result

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _make_cache_key(self, news_list: List[Dict]) -> str:
        """生成缓存键"""
        raw = "|".join(
            f"{n.get('title', '')}|{n.get('publish_time', '')}"
            for n in news_list[:MAX_NEWS_PER_STOCK]
        )
        return hashlib.md5(raw.encode()).hexdigest()

    def _score_to_label(self, score: float) -> str:
        """分数转标签"""
        if score >= 0.85:
            return "极度看好"
        elif score >= 0.65:
            return "看好"
        elif score >= 0.35:
            return "中性"
        elif score >= 0.15:
            return "看空"
        else:
            return "极度看空"

    def _calc_investor_sentiment(self, items: List[Dict]) -> str:
        """计算投资者情绪指数"""
        investor_keywords = {
            "买入": 1, "增持": 1, "回购": 1, "加仓": 1,
            "卖出": -1, "减持": -1, "减仓": -1, "出逃": -1,
        }
        sentiment_score = 0
        count = 0
        for item in items:
            text = item.get("title", "") + item.get("content", "")
            for kw, val in investor_keywords.items():
                if kw in text:
                    sentiment_score += val
                    count += 1

        if count == 0:
            return "无"

        normalized = max(0, min(100, int((sentiment_score / count + 1) * 50)))
        return str(normalized)

    def _calc_confidence(self, items: List[Dict]) -> float:
        """计算置信度指数"""
        if not items:
            return 0.0

        # 1. 来源可靠性 (40%)
        source_reliability = np.mean([item["_source_weight"] for item in items])

        # 2. 时效性 (30%)
        now = datetime.now()
        timeliness_scores = []
        for item in items:
            try:
                pub = datetime.strptime(item["publish_time"], "%Y-%m-%d %H:%M:%S")
                days_diff = (now - pub).days
                score = max(0.2, min(1.0, math.exp(-days_diff / 7)))
                timeliness_scores.append(score)
            except Exception:
                timeliness_scores.append(0.3)
        timeliness = np.mean(timeliness_scores)

        # 3. 一致性 (30%)
        scores = [item["_score"] for item in items]
        std_dev = np.std(scores) if len(scores) > 1 else 0.3
        consistency = max(0.0, min(1.0, 1 - std_dev))

        return 0.4 * source_reliability + 0.3 * timeliness + 0.3 * consistency

    def _build_time_analysis(self, items: List[Dict]) -> Dict:
        """构建时间维度分析"""
        date_groups = defaultdict(list)
        for item in items:
            d = item.get("date", item.get("publish_time", "")[:10])
            date_groups[d].append(item)

        trend = []
        for date in sorted(date_groups.keys(), reverse=True):
            group = date_groups[date]
            scores = [g["_score"] for g in group]
            avg = np.mean(scores)

            # 关键事件
            key_events = []
            for g in group:
                title = g.get("title", "")
                # 提取关键信息作为事件
                event_title = self._extract_event_title(title)
                if event_title:
                    key_events.append({
                        "title": event_title[:5],
                        "description": title[:20] if len(title) > 5 else title,
                    })

            trend.append({
                "date": date,
                "score": round(float(avg), 4),
                "key_events": key_events[:3],  # 每天最多3个关键事件
            })

        # 趋势预测
        if len(trend) >= 3:
            recent_scores = [t["score"] for t in trend[:3]]
            slope = recent_scores[0] - recent_scores[-1]
            if slope > 0.1:
                prediction = "近期情感呈上升趋势，市场情绪持续改善，预计短期内正面情绪有望延续。"
            elif slope < -0.1:
                prediction = "近期情感呈下降趋势，市场情绪有所转弱，需警惕潜在的负面因素发酵。"
            else:
                prediction = "近期情感处于震荡整理状态，多空力量相对均衡，短期趋势不明朗。"
        else:
            prediction = "数据量较少，无法形成有效趋势预测。"

        return {"trend": trend, "trend_prediction": prediction}

    def _extract_event_title(self, title: str) -> str:
        """从新闻标题提取关键事件"""
        # 尝试匹配常见的公告类型
        patterns = [
            (r"(利好|利空)", "利好/利空"),
            (r"(涨停|跌停)", "涨停/跌停"),
            (r"(增持|减持|回购)", "增减持"),
            (r"(中标|签约|合作)", "中标签约"),
            (r"(预警|预亏|扭亏)", "业绩预告"),
            (r"(获批|核准|通过)", "审批通过"),
            (r"(立案|调查|处罚)", "监管介入"),
            (r"(分红|送转|除权)", "分红送转"),
            (r"(解禁|减持)", "解禁减持"),
            (r"(收购|并购|重组)", "并购重组"),
        ]
        for pattern, default in patterns:
            if re.search(pattern, title):
                return default
        if len(title) <= 5:
            return title
        return title[:5]

    def _build_topic_analysis(self, items: List[Dict]) -> Dict:
        """构建主题维度分析"""
        # 主题关键词映射
        topic_keywords = {
            "company_operation": ["经营", "管理", "战略", "扩张", "裁员", "组织", "人事", "中标", "签约", "合作"],
            "financial_performance": ["营收", "利润", "净利", "亏损", "盈利", "增长", "下滑", "财报", "业绩", "分红"],
            "market_competition": ["竞争", "份额", "市场", "对手", "龙头", "排名", "替代", "占有率"],
            "product_technology": ["产品", "技术", "研发", "专利", "创新", "发布", "迭代", "升级", "量产"],
            "industry_policy": ["政策", "监管", "行业", "法规", "扶持", "补贴", "环保", "准入", "标准"],
            "capital_market": ["股价", "涨停", "跌停", "市值", "资金", "机构", "北向", "融资", "融券", "减持"],
        }

        result = {}
        for topic_key, topic_name in NEWS_TOPICS.items():
            # 找到匹配该主题的新闻
            matched = []
            for item in items:
                text = item.get("title", "") + item.get("content", "")
                kw_count = sum(1 for kw in topic_keywords.get(topic_key, []) if kw in text)
                if kw_count > 0:
                    matched.append((item, kw_count))

            if matched:
                # 加权平均得分（关键词匹配数作为权重）
                total_weight = sum(m[1] for m in matched)
                weighted_score = sum(m[0]["_score"] * m[1] for m in matched) / total_weight
                key_points = list(set(
                    m[0].get("title", "") for m in matched[:3]
                ))
                summary = (f"{topic_name}相关新闻{len(matched)}条，"
                          f"情感得分{weighted_score:.2f}，"
                          f"整体{'偏正面' if weighted_score > 0.5 else '偏负面' if weighted_score < 0.5 else '中性'}")
            else:
                weighted_score = 0.5
                key_points = []
                summary = f"未发现与{topic_name}直接相关的新闻报道"

            result[topic_key] = {
                "score": round(float(weighted_score), 4),
                "summary": summary,
                "key_points": key_points,
            }

        return result

    def _build_source_analysis(self, items: List[Dict]) -> Dict:
        """构建来源维度分析"""
        categories = {
            "mainstream_media": ["新闻", "日报", "时报", "晚报", "早报", "新华", "人民", "央视", "经济"],
            "industry_media": ["证券", "财经", "金融", "投行", "基金", "研报", "交易所"],
            "official_announcement": ["公告", "互动易", "官网", "官方", "监管", "证监会", "交易所"],
        }

        result = {}
        all_sources = set()
        for cat_key, keywords in categories.items():
            matched = []
            for item in items:
                source = item.get("source", "")
                all_sources.add(source)
                if any(kw in source for kw in keywords):
                    matched.append(item["_score"])

            if matched:
                avg_score = np.mean(matched)
                result[cat_key] = {
                    "score": round(float(avg_score), 4),
                    "summary": f"共{len(matched)}条来源",
                }
            else:
                result[cat_key] = {
                    "score": 0.5,
                    "summary": "未匹配到该类型来源",
                }

        # 自媒体 = 不属于上述任何类别的
        classified = set()
        for cat_key, keywords in categories.items():
            for item in items:
                source = item.get("source", "")
                if any(kw in source for kw in keywords):
                    classified.add(item["_score"])

        self_media_scores = [
            item["_score"] for item in items
            if item["_score"] not in classified
        ]
        if self_media_scores:
            result["self_media"] = {
                "score": round(float(np.mean(self_media_scores)), 4),
                "summary": f"共{len(self_media_scores)}条来源",
            }
        else:
            result["self_media"] = {"score": 0.5, "summary": "未匹配到"}

        return result

    def _build_impact_analysis(self, items: List[Dict]) -> Dict:
        """构建影响力分析"""
        scores = [item["_score"] for item in items]

        # 影响力得分 = 情感强度的平均（偏离0.5的程度）
        impact_scores = [abs(s - 0.5) * 2 for s in scores]
        avg_impact = np.mean(impact_scores)

        # 重要性等级
        avg_strength = abs(np.mean(scores) - 0.5) * 2
        news_count = len(items)
        if avg_strength > 0.6 and news_count > 10:
            importance = "高"
        elif avg_strength > 0.3 or news_count > 5:
            importance = "中"
        else:
            importance = "低"

        # 关键因素
        key_factors = []
        strong_positive = [item for item in items if item["_score"] > 0.75]
        strong_negative = [item for item in items if item["_score"] < 0.25]

        for item in strong_positive[:2]:
            key_factors.append(f"利好: {item.get('title', '')[:30]}")
        for item in strong_negative[:2]:
            key_factors.append(f"利空: {item.get('title', '')[:30]}")

        return {
            "importance_level": importance,
            "market_impact": {
                "score": round(float(avg_impact), 4),
                "duration": "短期" if avg_impact > 0.6 else "中期" if avg_impact > 0.3 else "长期",
                "key_factors": key_factors[:5],
            },
        }

    def _build_risk_analysis(self, items: List[Dict]) -> Dict:
        """构建风险分析"""
        scores = [item["_score"] for item in items]
        avg_score = np.mean(scores)

        # 负面新闻检测
        risk_factors = []
        seen_factors = set()

        for item in items:
            text = item.get("title", "") + item.get("content", "")
            for kw in NEGATIVE_KEYWORDS:
                if kw in text and kw not in seen_factors:
                    severity = "高" if item["_score"] < 0.2 else ("中" if item["_score"] < 0.4 else "低")
                    risk_factors.append({
                        "factor": kw,
                        "description": f"新闻「{item.get('title', '')[:20]}」中提到{kw}相关内容",
                        "severity": severity,
                    })
                    seen_factors.add(kw)

        # 风险等级
        neg_count = len(risk_factors)
        if avg_score < 0.3 or neg_count > 8:
            risk_level = "高"
        elif avg_score < 0.45 or neg_count > 4:
            risk_level = "中"
        else:
            risk_level = "低"

        return {
            "risk_level": risk_level,
            "risk_factors": risk_factors[:5],  # 最多展示5个
        }

    def _build_summary(self, score: float, label: str, items: List[Dict]) -> str:
        """构建分析总结"""
        pos_count = sum(1 for i in items if i["_score"] > 0.6)
        neg_count = sum(1 for i in items if i["_score"] < 0.4)
        neutral_count = len(items) - pos_count - neg_count

        status = "改善" if score > 0.55 else "恶化" if score < 0.45 else "平稳"
        return (
            f"基于{len(items)}条新闻分析，整体情感{label}（{score:.2f}），"
            f"其中正面新闻{pos_count}条、中性{neutral_count}条、负面{neg_count}条。"
            f"市场情绪总体{status}。"
        )

    def _build_market_expectation(self, score: float, items: List[Dict]) -> str:
        """构建市场预期"""
        if score > 0.7:
            return "短期内市场预期偏向乐观，关注利好因素的持续发酵。"
        elif score > 0.55:
            return "市场预期温和向好，投资者信心逐步恢复。"
        elif score > 0.45:
            return "市场预期中性，多空双方力量相对均衡，等待明确信号。"
        elif score > 0.3:
            return "市场预期偏谨慎，利空因素仍需消化。"
        else:
            return "市场预期较为悲观，需关注风险释放后的投资机会。"

    def _empty_result(self) -> Dict:
        """返回空分析结果"""
        return {
            "overall_sentiment": {
                "score": 0.5,
                "label": "中性",
                "summary": "没有可分析的新闻数据",
                "market_expectation": "无新闻数据",
                "investor_sentiment": "无",
                "confidence_index": 0.0,
                "volatility": 0.0,
                "volatility_label": "无数据",
                "cv": 0.0,
                "score_range": 0.0,
                "positive_ratio": 0.0,
                "negative_ratio": 0.0,
                "positive_count": 0,
                "negative_count": 0,
                "neutral_count": 0,
            },
            "time_analysis": {"trend": [], "trend_prediction": "无数据"},
            "topic_analysis": {
                k: {"score": 0.5, "summary": "无数据", "key_points": []}
                for k in NEWS_TOPICS
            },
            "source_analysis": {
                k: {"score": 0.5, "summary": "无数据"}
                for k in ["mainstream_media", "industry_media", "self_media", "official_announcement"]
            },
            "impact_analysis": {
                "importance_level": "低",
                "market_impact": {"score": 0.0, "duration": "", "key_factors": []},
            },
            "risk_analysis": {
                "risk_level": "低",
                "risk_factors": [],
            },
        }


# 快捷函数
def analyze_stock_sentiment(news_list: List[Dict]) -> Dict:
    """便捷的情感分析入口"""
    analyzer = SentimentAnalyzer()
    return analyzer.analyze(news_list)
