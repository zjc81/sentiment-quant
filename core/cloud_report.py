"""
云端纯Python报告生成器 (无 Plotly/numpy/pandas 依赖)
使用 Plotly.js CDN 在客户端渲染交互式图表
完全匹配本地 visualization/report.py 的报告样式和质量
"""
import json
import math
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

from config import REPORT_DIR


# ======================================================================
# 工具函数
# ======================================================================

def _mean(vals):
    return sum(vals) / len(vals) if vals else 0.0

def _std(vals):
    if len(vals) < 2: return 0.0
    m = _mean(vals)
    return math.sqrt(sum((x - m) ** 2 for x in vals) / len(vals))

def _score_color(score):
    if score >= 0.65: return "#00ff88"
    elif score >= 0.35: return "#ffcc44"
    else: return "#ff4444"

def _label_color(label):
    m = {"极度看好":"#00ff88","看好":"#88cc44","中性":"#ffcc44","看空":"#ff8844","极度看空":"#ff4444"}
    return m.get(label, "#888")

def _uid():
    return uuid.uuid4().hex[:12]


# ======================================================================
# Plotly.js 图表生成器 (纯 Python → JavaScript)
# ======================================================================

def _plotly_gauge(uid, value, title, color="#00ff88", steps=None, number_suffix="%",
                  number_size=36, height=300, subtitle=""):
    """生成 Plotly 仪表盘图"""
    if steps is None:
        steps = [
            {"range": [0, 15], "color": "#ff4444"},
            {"range": [15, 35], "color": "#ff8844"},
            {"range": [35, 65], "color": "#ffcc44"},
            {"range": [65, 85], "color": "#88cc44"},
            {"range": [85, 100], "color": "#00ff88"},
        ]
    title_text = title
    if subtitle:
        title_text += f"<br><span style='font-size:14px;color:#aaa'>{subtitle}</span>"

    trace = {
        "type": "indicator",
        "mode": "gauge+number",
        "value": value,
        "number": {"font": {"color": color, "size": number_size}, "suffix": number_suffix},
        "gauge": {
            "axis": {"range": [0, 100], "tickcolor": "#666"},
            "bar": {"color": color, "thickness": 0.3},
            "steps": steps,
        },
        "title": {"text": title_text, "font": {"size": 16}},
    }
    layout = {
        "template": _dark_template(),
        "margin": {"l": 30, "r": 30, "t": 60, "b": 30},
        "height": height,
    }
    return _plotly_div(uid, [trace], layout)


def _plotly_line(uid, x, y, title, color="#00ff88", height=350, hlines=None, annotations=None):
    """生成 Plotly 折线图"""
    traces = [{
        "type": "scatter",
        "x": x, "y": y,
        "mode": "lines+markers",
        "name": title,
        "line": {"color": color, "width": 3},
        "marker": {"size": 8, "color": color, "symbol": "circle"},
        "fill": "tozeroy",
        "fillcolor": f"rgba({_hex_to_rgb(color)},0.1)",
    }]
    layout = {
        "template": _dark_template(),
        "xaxis": {"title": "日期", "gridcolor": "#2a2a4a"},
        "yaxis": {"title": "情感得分 (%)", "range": [0, 100], "gridcolor": "#2a2a4a"},
        "height": height,
        "hovermode": "x unified",
        "shapes": [],
        "annotations": [],
    }
    if hlines:
        for h in hlines:
            layout["shapes"].append({
                "type": "line", "x0": 0, "x1": 1, "xref": "x domain",
                "y0": h["y"], "y1": h["y"], "yref": "y",
                "line": {"color": h.get("color","#ffcc44"), "dash": "dash", "width": 1},
            })
            if h.get("label"):
                layout["annotations"].append({
                    "text": h["label"], "x": 1, "xanchor": "right", "xref": "x domain",
                    "y": h["y"], "yanchor": "bottom", "yref": "y",
                    "showarrow": False, "font": {"size": 10},
                })
    if annotations:
        for a in annotations:
            layout["annotations"].append(a)
    return _plotly_div(uid, traces, layout)


def _plotly_bar(uid, x, y, title, colors=None, text=None, height=350, hlines=None):
    """生成 Plotly 柱状图"""
    trace = {
        "type": "bar", "x": x, "y": y,
        "marker": {"color": colors or ("#00ff88" if isinstance(y[0], (int, float)) and y[0] > 50 else "#ff4444")},
        "text": text or [f"{v:.1f}" for v in y],
        "textposition": "outside",
        "textfont": {"size": 12},
    }
    layout = {
        "template": _dark_template(),
        "yaxis": {"range": [0, 100], "title": "评分 (%)", "gridcolor": "#2a2a4a"},
        "xaxis": {"gridcolor": "#2a2a4a"},
        "height": height,
        "hovermode": "x",
        "shapes": [],
    }
    if hlines:
        for h in hlines:
            layout["shapes"].append({
                "type": "line", "x0": 0, "x1": 1, "xref": "x domain",
                "y0": h["y"], "y1": h["y"], "yref": "y",
                "line": {"color": h.get("color","#ffcc44"), "dash": "dash", "width": 1},
            })
    return _plotly_div(uid, [trace], layout)


def _plotly_radar(uid, r, theta, title, color="#00ff88", height=400):
    """生成 Plotly 雷达图"""
    traces = [{
        "type": "scatterpolar",
        "r": r + [r[0]],
        "theta": theta + [theta[0]],
        "fill": "toself",
        "name": title,
        "line": {"color": color, "width": 3},
        "fillcolor": f"rgba({_hex_to_rgb(color)},0.2)",
    }]
    layout = {
        "template": _dark_template(),
        "polar": {
            "radialaxis": {"visible": True, "range": [0, 100], "color": "#888"},
            "bgcolor": "#16213e",
        },
        "height": height,
        "showlegend": False,
    }
    return _plotly_div(uid, traces, layout)


def _plotly_histogram(uid, values, title, color="#00ff88", nbins=10, height=300):
    """生成 Plotly 直方图"""
    traces = [{
        "type": "histogram",
        "x": values,
        "nbinsx": nbins,
        "marker": {"color": f"rgba({_hex_to_rgb(color)},0.6)",
                    "line": {"color": f"rgba({_hex_to_rgb(color)},0.9)", "width": 1}},
        "name": "新闻分布",
    }]
    mean_val = _mean(values)
    layout = {
        "template": _dark_template(),
        "xaxis": {"title": "情感得分 (%)", "range": [0, 100], "gridcolor": "#2a2a4a"},
        "yaxis": {"title": "新闻数量", "gridcolor": "#2a2a4a"},
        "height": height,
        "shapes": [
            {"type": "line", "x0": 35, "x1": 35, "xref": "x", "y0": 0, "y1": 1, "yref": "y domain",
             "line": {"color": "#ff4444", "dash": "dash", "width": 1}},
            {"type": "line", "x0": 65, "x1": 65, "xref": "x", "y0": 0, "y1": 1, "yref": "y domain",
             "line": {"color": "#00ff88", "dash": "dash", "width": 1}},
            {"type": "line", "x0": mean_val, "x1": mean_val, "xref": "x", "y0": 0, "y1": 1, "yref": "y domain",
             "line": {"color": "#4488ff", "width": 1.5}},
        ],
        "annotations": [
            {"x": mean_val, "y": 0.95, "xref": "x", "yref": "paper",
             "text": f"均值 {mean_val:.1f}%", "showarrow": False,
             "font": {"color": "#4488ff", "size": 11},
             "bgcolor": "rgba(22,33,62,0.8)"},
        ],
        "bargap": 0.05,
        "margin": {"l": 30, "r": 30, "t": 40, "b": 30},
    }
    return _plotly_div(uid, traces, layout)


def _plotly_dual_gauge(uid, left_val, left_title, left_color, right_val, right_title, right_color, height=250):
    """生成双仪表盘"""
    traces = [
        {"type": "indicator", "mode": "gauge+number",
         "value": left_val, "number": {"font": {"color": left_color, "size": 28}, "suffix": "%"},
         "gauge": {"axis": {"range": [0, 100]}, "bar": {"color": left_color, "thickness": 0.15},
                   "steps": [{"range": [0, 33], "color": "#224422"},
                             {"range": [33, 66], "color": "#444422"},
                             {"range": [66, 100], "color": "#442222"}]},
         "title": {"text": left_title, "font": {"size": 16}}, "domain": {"row": 0, "column": 0}},
        {"type": "indicator", "mode": "gauge+number",
         "value": right_val, "number": {"font": {"color": right_color, "size": 28}},
         "gauge": {"axis": {"range": [0, 100], "tickvals": [10, 50, 90], "ticktext": ["低", "中", "高"]},
                   "bar": {"color": right_color, "thickness": 0.15},
                   "steps": [{"range": [0, 33], "color": "#224422"},
                             {"range": [33, 66], "color": "#444422"},
                             {"range": [66, 100], "color": "#442222"}]},
         "title": {"text": right_title, "font": {"size": 16}}, "domain": {"row": 0, "column": 1}},
    ]
    layout = {
        "template": _dark_template(),
        "grid": {"rows": 1, "columns": 2},
        "height": height,
        "margin": {"l": 30, "r": 30, "t": 40, "b": 30},
    }
    return _plotly_div(uid, traces, layout)


def _plotly_kline(uid, kline_data, sentiment_result, height=500):
    """生成 K线图 + 情绪信号叠加 + MACD"""
    if not kline_data or len(kline_data) < 3:
        return ""

    try:
        dates_full = [k.get("date", "") for k in kline_data]
        dates_short = [d[-5:] if len(d) >= 10 else d for d in dates_full]
        opens = [k.get("open", 0) for k in kline_data]
        highs = [k.get("high", 0) for k in kline_data]
        lows = [k.get("low", 0) for k in kline_data]
        closes = [k.get("close", 0) for k in kline_data]

        # 计算均线 (纯Python)
        ma5 = _sma(closes, 5)
        ma20 = _sma(closes, 20)

        # EMA
        ema12 = _ema(closes, 12)
        ema26 = _ema(closes, 26)

        # MACD (安全处理长度不一致)
        n_min = min(len(ema12), len(ema26), len(closes))
        macd_line = [ema12[i] - ema26[i] for i in range(n_min)]
        signal_line = _ema(macd_line, 9)
        macd_hist = [macd_line[i] - signal_line[i] for i in range(len(macd_line))]

        # 情绪信号对齐 (安全访问，防止 KeyError)
        trend_data = sentiment_result.get("time_analysis", {}).get("trend", [])
        date_score = {}
        for t in trend_data:
            d = t.get("date")
            s = t.get("score")
            if d is not None and s is not None:
                date_score[d] = s * 100
        aligned_scores, aligned_dates = [], []
        for i, fd in enumerate(dates_full):
            if fd in date_score:
                aligned_scores.append(date_score[fd])
                aligned_dates.append(dates_short[i])

        traces = []
        # K线 (Candlestick)
        traces.append({
            "type": "candlestick",
            "x": dates_short, "open": opens, "high": highs, "low": lows, "close": closes,
            "name": "K线",
            "increasing": {"line": {"color": "#00ff88", "width": 1}, "fillcolor": "rgba(0,255,136,0.4)"},
            "decreasing": {"line": {"color": "#ff4444", "width": 1}, "fillcolor": "rgba(255,68,68,0.4)"},
            "xaxis": "x", "yaxis": "y",
        })
        # MA5
        traces.append({
            "type": "scatter", "x": dates_short, "y": ma5, "mode": "lines",
            "name": "MA5", "line": {"color": "#4488ff", "width": 1.2}, "xaxis": "x", "yaxis": "y",
        })
        # MA20
        traces.append({
            "type": "scatter", "x": dates_short, "y": ma20, "mode": "lines",
            "name": "MA20", "line": {"color": "#ff8844", "width": 1.2}, "xaxis": "x", "yaxis": "y",
        })
        # 情绪信号
        if aligned_scores:
            traces.append({
                "type": "scatter", "x": aligned_dates, "y": aligned_scores,
                "mode": "lines+markers", "name": "情绪信号",
                "line": {"color": "#00ff88", "width": 2.5},
                "marker": {"size": 6, "color": "#00ff88"},
                "fill": "tozeroy", "fillcolor": "rgba(0,255,136,0.15)",
                "xaxis": "x2", "yaxis": "y2",
            })
        # MACD 柱
        traces.append({
            "type": "bar", "x": dates_short, "y": macd_hist,
            "marker": {"color": ["#00ff88" if v >= 0 else "#ff4444" for v in macd_hist]},
            "name": "MACD柱", "opacity": 0.7, "xaxis": "x3", "yaxis": "y3",
        })
        # MACD线
        traces.append({
            "type": "scatter", "x": dates_short, "y": macd_line,
            "mode": "lines", "name": "DIF", "line": {"color": "#4488ff", "width": 1.5},
            "xaxis": "x3", "yaxis": "y3",
        })
        traces.append({
            "type": "scatter", "x": dates_short, "y": signal_line,
            "mode": "lines", "name": "DEA", "line": {"color": "#ff8844", "width": 1.5},
            "xaxis": "x3", "yaxis": "y3",
        })

        layout = {
            "template": _dark_template(),
            "height": height,
            "showlegend": True,
            "legend": {"x": 0.01, "y": 0.99, "bgcolor": "rgba(26,26,46,0.8)", "font": {"size": 11}},
            "hovermode": "x unified",
            "margin": {"l": 30, "r": 30, "t": 40, "b": 30},
            "grid": {"rows": 3, "columns": 1, "roworder": "top to bottom",
                     "pattern": "independent", "ygap": 0.02},
            "xaxis": {"anchor": "y", "domain": [0, 1], "rangeslider": {"visible": False}},
            "yaxis": {"anchor": "x", "domain": [0.48, 1], "title": "价格"},
            "xaxis2": {"anchor": "y2", "domain": [0, 1], "matches": "x"},
            "yaxis2": {"anchor": "x2", "domain": [0.24, 0.46], "title": "情绪%", "range": [0, 100]},
            "xaxis3": {"anchor": "y3", "domain": [0, 1], "matches": "x"},
            "yaxis3": {"anchor": "x3", "domain": [0, 0.22], "title": "MACD"},
            "shapes": [
                {"type": "line", "x0": 0, "x1": 1, "xref": "x2 domain", "y0": 65, "y1": 65, "yref": "y2",
                 "line": {"color": "#88cc44", "dash": "dash", "width": 1}},
                {"type": "line", "x0": 0, "x1": 1, "xref": "x2 domain", "y0": 35, "y1": 35, "yref": "y2",
                 "line": {"color": "#ff4444", "dash": "dash", "width": 1}},
            ],
            "annotations": [
                {"text": "积极", "x": 1, "xanchor": "right", "xref": "x2 domain",
                 "y": 65, "yanchor": "bottom", "yref": "y2", "showarrow": False},
                {"text": "消极", "x": 1, "xanchor": "right", "xref": "x2 domain",
                 "y": 35, "yanchor": "bottom", "yref": "y2", "showarrow": False},
            ],
        }
        return _plotly_div(uid, traces, layout)
    except Exception as e:
        return f'<div class="chart-error" style="color:#ff6644;padding:10px">K线图生成异常: {str(e)[:80]}</div>'


# ======================================================================
# 技术指标计算 (纯Python)
# ======================================================================

def _sma(values, period):
    """简单移动平均"""
    result = []
    for i in range(len(values)):
        if i < period - 1:
            result.append(None)
        else:
            result.append(sum(values[i-period+1:i+1]) / period)
    return result

def _ema(values, period):
    """指数移动平均"""
    result = []
    multiplier = 2 / (period + 1)
    for i in range(len(values)):
        if i == 0:
            result.append(values[0])
        else:
            result.append(values[i] * multiplier + result[-1] * (1 - multiplier))
    return result


# ======================================================================
# 辅助函数
# ======================================================================

def _dark_template():
    """Plotly.js 暗色主题"""
    return {
        "layout": {
            "font": {"color": "#e0e0e0", "family": "Arial, sans-serif"},
            "paper_bgcolor": "#1a1a2e",
            "plot_bgcolor": "#16213e",
            "hovermode": "x unified",
            "xaxis": {"gridcolor": "#2a2a4a", "showgrid": True, "zerolinecolor": "#3a3a5a"},
            "yaxis": {"gridcolor": "#2a2a4a", "showgrid": True, "zerolinecolor": "#3a3a5a"},
        }
    }

def _hex_to_rgb(hex_color):
    """#00ff88 → 0,255,136"""
    h = hex_color.lstrip("#")
    return f"{int(h[0:2],16)},{int(h[2:4],16)},{int(h[4:6],16)}"

def _plotly_div(uid, traces, layout):
    """生成 Plotly.newPlot() JavaScript 代码"""
    trace_json = json.dumps(traces, ensure_ascii=False)
    layout_json = json.dumps(layout, ensure_ascii=False)
    return f"""
    <div id="{uid}" style="width:100%;height:{layout.get('height',300)}px;"></div>
    <script>
        (function() {{
            var el = document.getElementById("{uid}");
            if (el && typeof Plotly !== 'undefined') {{
                Plotly.newPlot("{uid}", {trace_json}, {layout_json}, {{responsive: true}});
            }}
        }})();
    </script>"""


# ======================================================================
# AI 诊断
# ======================================================================

def _ai_conclusion(sentiment_result, news_list):
    overall = sentiment_result.get("overall_sentiment", {})
    score = overall.get("score", 0.5)
    label = overall.get("label", "中性")
    risk = sentiment_result.get("risk_analysis", {})
    risk_level = risk.get("risk_level", "低")
    trend_data = sentiment_result.get("time_analysis", {}).get("trend", [])

    trend_direction = "平稳"
    if len(trend_data) >= 2:
        recent = [t["score"] for t in trend_data][-3:]
        if len(recent) >= 2:
            if recent[-1] > recent[0] + 0.1:
                trend_direction = "改善中"
            elif recent[-1] < recent[0] - 0.1:
                trend_direction = "恶化中"

    if score > 0.65:
        advice = "情绪积极且风险可控，可关注" if risk_level == "低" else "情绪积极但存在风险，建议谨慎参与"
    elif score < 0.35:
        advice = "情绪偏空，建议观望或减仓"
    else:
        if trend_direction == "改善中":
            advice = "情绪中性但正在改善，可适度关注"
        elif trend_direction == "恶化中":
            advice = "情绪中性但有恶化迹象，建议暂时观望"
        else:
            advice = "情绪中性，方向不明确，建议耐心等待信号"

    n_news = len(news_list)
    pos_count = sum(1 for n in news_list if n.get("_score", 0.5) > 0.55)
    neg_count = sum(1 for n in news_list if n.get("_score", 0.5) < 0.45)

    conclusion = f"{label}（{score*100:.0f}分）| 趋势{trend_direction} | {pos_count}正/{neg_count}负/{n_news-pos_count-neg_count}中 | {advice}"
    return f"""<div class="ai-conclusion">
        <div class="ai-badge">🤖 AI 诊断</div>
        <div class="ai-text">{conclusion}</div>
    </div>"""


# ======================================================================
# 仪表盘卡片
# ======================================================================

def _dashboard(sentiment_result, quote=None, market=None, news_count=0, fund_flow=None):
    overall = sentiment_result.get("overall_sentiment", {})
    score = overall.get("score", 0.5)
    conf = overall.get("confidence_index", 0.0)
    volatility = overall.get("volatility", 0.0)
    pos_r = overall.get("positive_ratio", 0.0)
    neg_r = overall.get("negative_ratio", 0.0)
    pos_n = overall.get("positive_count", 0)
    neg_n = overall.get("negative_count", 0)
    neu_n = overall.get("neutral_count", 0)
    risk = sentiment_result.get("risk_analysis", {})
    risk_level = risk.get("risk_level", "低")
    risk_color = {"高": "#ff4444", "中": "#ff8844", "低": "#00ff88"}.get(risk_level, "#888")
    label_colors = {"极度看好": "#00ff88", "看好": "#88cc44", "中性": "#ffcc44", "看空": "#ff8844", "极度看空": "#ff4444"}
    score_color = label_colors.get(overall.get("label", ""), "#888")
    conf_color = "#00ff88" if conf > 0.6 else ("#ff8844" if conf > 0.3 else "#ff4444")
    vol_color = "#00ff88" if volatility < 0.15 else ("#ff8844" if volatility < 0.3 else "#ff4444")
    vol_pct = min(int(volatility * 333), 100)

    topic = sentiment_result.get("topic_analysis", {})
    topic_tags = ""
    topic_names = {"company_operation": "经营", "financial_performance": "财务",
                   "market_competition": "竞争", "product_technology": "技术",
                   "industry_policy": "政策", "capital_market": "资本"}
    for k, v in topic.items():
        s = v.get("score", 0.5)
        color = "#00ff88" if s > 0.55 else ("#ff4444" if s < 0.45 else "#ffcc44")
        name = topic_names.get(k, k)
        topic_tags += f'<span class="topic-tag" style="background:{color}20;color:{color};border:1px solid {color}40">{name} {s*100:.0f}%</span>'

    quote_html = ""
    if quote:
        pct_color = "#00ff88" if quote.get('pct_change', 0) >= 0 else "#ff4444"
        quote_html = f"""
        <div class="dashboard-quote">
            <span class="quote-price">¥{quote.get('price', 'N/A')}</span>
            <span class="quote-change" style="color:{pct_color}">{quote.get('pct_change', 0):+.2f}%</span>
            <span class="quote-divider">|</span>
            <span>换手 {quote.get('turnover', 'N/A')}%</span>
            <span class="quote-divider">|</span>
            <span>PE {quote.get('pe', 'N/A')}</span>
        </div>"""

    market_html = ""
    if market:
        sh = market.get("上证指数", {})
        sz = market.get("深证成指", {})
        sh_c = "#00ff88" if sh.get('pct_change', 0) >= 0 else "#ff4444"
        sz_c = "#00ff88" if sz.get('pct_change', 0) >= 0 else "#ff4444"
        market_html = f"""
        <div class="dashboard-market">
            <span>上证 <b style="color:{sh_c}">{sh.get('price','-')}</b> <span style="color:{sh_c}">{sh.get('pct_change',0):+.2f}%</span></span>
            <span style="margin-left:15px">深证 <b style="color:{sz_c}">{sz.get('price','-')}</b> <span style="color:{sz_c}">{sz.get('pct_change',0):+.2f}%</span></span>
            <span style="margin-left:15px;color:#888">📰 {news_count}条新闻</span>
        </div>"""

    fund_html = ""
    if fund_flow and fund_flow.get("main_net_avg") is not None:
        ff = fund_flow
        main_net = ff.get("main_net_avg", 0)
        dire = ff.get("net_direction", "")
        fc = "#00ff88" if main_net > 0 else "#ff4444"
        fund_html = f"""
        <div class="dashboard-market">
            <span>💰 主力净{dire}: <b style="color:{fc}">{main_net:+.2f}亿</b></span>
            <span style="margin-left:12px">散户: <b style="color:#888">{ff.get('retail_net_avg',0):+.2f}亿</b></span>
            <span style="margin-left:12px;color:#666">|</span>
            <span style="margin-left:8px">⏱️ 近{ff.get('days',5)}日</span>
        </div>"""

    return f"""{quote_html}
    {market_html}
    {fund_html}
    <div class="dash-grid dash-grid-5">
        <div class="dash-card">
            <div class="dash-value" style="color:{score_color}">{score*100:.0f}分</div>
            <div class="dash-label">综合情绪</div>
        </div>
        <div class="dash-card">
            <div class="dash-value" style="color:{conf_color}">{conf*100:.0f}%</div>
            <div class="dash-label">置信度</div>
        </div>
        <div class="dash-card">
            <div class="dash-value" style="color:{vol_color}">{volatility*100:.0f}%</div>
            <div class="dash-label">波动</div>
            <div class="vol-bar-bg"><div class="vol-bar-fg" style="width:{vol_pct}%;background:linear-gradient(90deg,#00ff88,#ff8844,#ff4444)"></div></div>
        </div>
        <div class="dash-card">
            <div class="dash-value" style="color:{risk_color}">{risk_level}</div>
            <div class="dash-label">风险</div>
        </div>
        <div class="dash-card wide-card">
            <div class="dash-label" style="margin-bottom:4px">正/负/中: {pos_n}/{neg_n}/{neu_n}</div>
            <div class="sentiment-ratio-bar" style="margin-bottom:4px">
                <div class="ratio-pos" style="flex:{pos_r*100}"></div>
                <div class="ratio-neu" style="flex:{max(0.0,(1-pos_r-neg_r))*100}"></div>
                <div class="ratio-neg" style="flex:{neg_r*100}"></div>
            </div>
            <div class="topic-tags">{topic_tags}</div>
        </div>
    </div>"""


# ======================================================================
# 完整报告生成
# ======================================================================

def generate_report(
    stock_code: str,
    stock_name: str,
    sentiment_result: Dict,
    news_list: List[Dict],
    kline_data: Optional[List] = None,
    quote: Optional[Dict] = None,
    market: Optional[Dict] = None,
    fund_flow: Optional[Dict] = None,
    announcements: Optional[List] = None,
    output_path: Optional[Path] = None,
) -> str:
    """生成完整的云端 HTML 报告"""

    overall = sentiment_result.get("overall_sentiment", {})
    time_analysis = sentiment_result.get("time_analysis", {})
    topic_analysis = sentiment_result.get("topic_analysis", {})
    source_analysis = sentiment_result.get("source_analysis", {})
    impact = sentiment_result.get("impact_analysis", {})
    risk = sentiment_result.get("risk_analysis", {})

    charts = []

    # Chart 1: 综合情感评分仪表盘
    score = overall.get("score", 0.5)
    label = overall.get("label", "中性")
    uid1 = f"gauge_{_uid()}"
    gauge1_title = "综合情感评分<br><span style='font-size:16px;color:" + _label_color(label) + "'>" + label + "</span>"
    gauge1_html = _plotly_gauge(uid1, score * 100, gauge1_title, color="#00ff88", height=300)
    charts.append('<div class="chart-card">' + gauge1_html + '</div>')

    # Chart 2: 置信度
    conf = overall.get("confidence_index", 0.0)
    uid2 = f"gauge_{_uid()}"
    charts.append(f'<div class="chart-card half-left"><div class="chart-title">🔒 置信度指数</div>{_plotly_gauge(uid2, conf*100, "置信度指数", color="#4488ff", steps=[{"range":[0,33],"color":"#442222"},{"range":[33,66],"color":"#444422"},{"range":[66,100],"color":"#224444"}], subtitle="数据可靠度", height=300)}</div>')

    # Chart 3: 投资者情绪
    investor = overall.get("investor_sentiment", "无")
    inv_val = int(investor) if investor != "无" else 50
    inv_note = "" if investor != "无" else "<br><span style='font-size:11px;color:#888'>暂无交易信号，默认中性</span>"
    uid3 = f"gauge_{_uid()}"
    charts.append(f'<div class="chart-card half-right"><div class="chart-title">📈 投资者情绪指数</div>{_plotly_gauge(uid3, inv_val, f"投资者情绪指数{inv_note}", color="#ff8844", steps=[{"range":[0,33],"color":"#442222"},{"range":[33,66],"color":"#444422"},{"range":[66,100],"color":"#224422"}], height=300)}</div>')

    # Chart 4+5: 时间趋势
    trend_data = time_analysis.get("trend", [])
    if trend_data:
        dates = [t["date"] for t in trend_data][::-1]
        scores = [t["score"] * 100 for t in trend_data][::-1]
        uid4 = f"line_{_uid()}"
        charts.append(f'<div class="chart-card full-width"><div class="chart-title">⏳ 情感时间趋势</div>{_plotly_line(uid4, dates, scores, "情感得分", "#00ff88", 350, hlines=[{"y":65,"color":"#ffcc44","label":"积极阈值"},{"y":35,"color":"#ff4444","label":"消极阈值"}])}</div>')

        # 事件标注版
        uid5 = f"line_{_uid()}"
        annotations = []
        for t in trend_data:
            for evt_idx, event in enumerate(t.get("key_events", [])):
                annotations.append({
                    "x": t["date"], "y": t["score"] * 100,
                    "text": event.get("title", ""),
                    "showarrow": True, "arrowhead": 2, "arrowcolor": "#ff8844",
                    "arrowsize": 1.5, "ax": 0, "ay": -40 - evt_idx * 32,
                    "font": {"size": 10, "color": "#ff8844"},
                    "bgcolor": "rgba(22,33,62,0.85)", "bordercolor": "#ff8844",
                    "borderwidth": 1, "borderpad": 3,
                })
        charts.append(f'<div class="chart-card full-width"><div class="chart-title">📍 关键事件标注</div>{_plotly_line(uid5, dates, scores, "情感得分", "#00ff88", 400, hlines=[{"y":65,"color":"#ffcc44"},{"y":35,"color":"#ff4444"}], annotations=annotations)}</div>')

    # Chart 6+7: 主题分析
    if topic_analysis:
        topic_names = ["公司经营", "财务表现", "市场竞争", "产品技术", "行业政策", "资本市场"]
        topic_keys = ["company_operation", "financial_performance", "market_competition",
                      "product_technology", "industry_policy", "capital_market"]
        topic_scores = [topic_analysis.get(k, {}).get("score", 0.5) * 100 for k in topic_keys]

        uid6 = f"radar_{_uid()}"
        charts.append(f'<div class="chart-card half-left"><div class="chart-title">🎯 主题分析雷达图</div>{_plotly_radar(uid6, topic_scores, topic_names, "主题评分", "#00ff88", 400)}</div>')

        colors = ["#00ff88" if s > 50 else "#ff4444" if s < 35 else "#ffcc44" for s in topic_scores]
        uid7 = f"bar_{_uid()}"
        charts.append(f'<div class="chart-card half-right"><div class="chart-title">📊 主题评分柱状图</div>{_plotly_bar(uid7, topic_names, topic_scores, "主题评分", colors, hlines=[{"y":65,"color":"#88cc44"},{"y":35,"color":"#ff4444"}])}</div>')

    # Chart 8: 来源分析
    if source_analysis:
        source_names = {"mainstream_media": "主流媒体", "industry_media": "行业媒体",
                        "self_media": "自媒体", "official_announcement": "官方公告"}
        s_names, s_scores, s_colors = [], [], []
        for sk, sn in source_names.items():
            s = source_analysis.get(sk, {}).get("score", 0.5)
            s_names.append(sn); s_scores.append(s * 100)
            s_colors.append("#4488ff" if sk == "official_announcement" else
                           "#00ff88" if sk == "mainstream_media" else
                           "#ff8844" if sk == "industry_media" else "#888")
        uid8 = f"bar_{_uid()}"
        charts.append(f'<div class="chart-card half-left"><div class="chart-title">📡 信息来源分析</div>{_plotly_bar(uid8, s_names, s_scores, "来源分析", s_colors, text=[f"{s:.1f}" for s in s_scores], height=300)}</div>')

    # Chart 9: 影响力+风险
    impact_score = impact.get("market_impact", {}).get("score", 0) * 100
    risk_level = risk.get("risk_level", "低")
    risk_color_val = {"高": "#ff4444", "中": "#ff8844", "低": "#00ff88"}.get(risk_level, "#888")
    risk_val = {"高": 90, "中": 50, "低": 10}.get(risk_level, 50)
    uid9 = f"dual_{_uid()}"
    impact_title = '市场影响力<br><span style="font-size:13px;color:#aaa">市场影响程度</span>'
    risk_title = f'风险等级: {risk_level}<br><span style="font-size:13px;color:#aaa">风险因素{len(risk.get("risk_factors",[]))}个</span>'
    charts.append(f'<div class="chart-card half-right"><div class="chart-title">⚠️ 影响力 & 风险评估</div>{_plotly_dual_gauge(uid9, impact_score, impact_title, "#4488ff", risk_val, risk_title, risk_color_val, 250)}</div>')

    # Chart 10: 情感得分分布
    items = sentiment_result.get("word_analysis", {}).get("items", [])
    if not items:
        # 用 news_list 的 _score 替代
        scores_raw = [n.get("_score", overall.get("score", 0.5)) for n in news_list if n.get("_score")]
        if not scores_raw:
            scores_raw = [max(0.01, min(0.99, overall.get("score", 0.5) + (i - 6) * 0.08)) for i in range(12)]
    else:
        scores_raw = [it.get("_score", 0.5) for it in items if "_score" in it]
    scores_pct = [s * 100 for s in scores_raw]
    nbins = max(5, min(12, len(scores_pct)))
    uid10 = f"hist_{_uid()}"
    charts.append(f'<div class="chart-card full-width"><div class="chart-title">📊 情感得分分布</div>{_plotly_histogram(uid10, scores_pct, "情感得分分布", "#00ff88", nbins, 300)}</div>')

    # Chart 11: K线 + 情绪叠加
    # 防御性截取：只保留最近120天K线数据（防止历史旧数据）
    if kline_data and len(kline_data) > 3:
        _orig_n = len(kline_data)
        from datetime import timedelta as _td
        _cut = (datetime.now() - _td(days=120)).strftime("%Y-%m-%d")
        _filt_k = [k for k in kline_data if k.get("date", "") >= _cut]
        if _filt_k and len(_filt_k) >= 3:
            kline_data = _filt_k
        else:
            kline_data = kline_data[-120:]
        if len(kline_data) != _orig_n:
            print(f"[REPORT] K线截取: {_orig_n}条 -> {len(kline_data)}条")
    if kline_data and len(kline_data) >= 3:
        uid11 = f"kline_{_uid()}"
        kline_chart = _plotly_kline(uid11, kline_data, sentiment_result, 550)
        if kline_chart:
            charts.append(f'<div class="chart-card full-width"><div class="chart-title">📈 K线走势 + 情绪信号 + MACD</div>{kline_chart}</div>')

    # ===== 非图表内容 =====
    summary_text = overall.get("summary", "")
    market_exp = overall.get("market_expectation", "")
    trend_pred = time_analysis.get("trend_prediction", "")

    # 新闻列表
    news_parts = []
    for news in news_list[:10]:
        title = news.get("title", "")
        source = news.get("source", "")
        pub_time = news.get("publish_time", "")
        content = news.get("content", "")[:150]
        url = news.get("url", "")
        news_parts.append(f"""<div class="news-item">
            <div class="news-title">{title}</div>
            <div class="news-meta">🕐 {pub_time} | 📰 {source}</div>
            <div class="news-content">{content}{'...' if len(news.get('content', '')) > 150 else ''}</div>
            {"<a class='news-link' href='" + url + "' target='_blank'>🔗 查看原文 →</a>" if url else ""}
        </div>""")

    # 风险因素
    risk_parts = []
    for rf in risk.get("risk_factors", []):
        factor = rf.get("factor", "")
        desc = rf.get("description", "")
        severity = rf.get("severity", "低")
        sev_color = {"高": "#ff4444", "中": "#ff8844", "低": "#88cc44"}.get(severity, "#888")
        risk_parts.append(f"""<div class="risk-item">
            <span class="risk-factor">{factor}</span>
            <span class="risk-desc">{desc}</span>
            <span class="risk-severity" style="background:{sev_color}">{severity}</span>
        </div>""")

    # 关键事件
    events_parts = []
    for trend in trend_data:
        date = trend.get("date", "")
        tscore = trend.get("score", 0.5)
        events = trend.get("key_events", [])
        if events:
            events_text = " | ".join([e.get("title", "") for e in events])
        else:
            events_text = "无突出事件"
        events_parts.append(f'<div class="event-chip"><span class="event-date">{date}</span><span class="event-text">{events_text}</span><span class="event-score" style="color:{_score_color(tscore)}">{tscore*100:.0f}%</span></div>')

    # 主题详情
    topic_details = ""
    for tk, tn in [("company_operation", "公司经营"), ("financial_performance", "财务表现"),
                   ("market_competition", "市场竞争"), ("product_technology", "产品技术"),
                   ("industry_policy", "行业政策"), ("capital_market", "资本市场")]:
        td = topic_analysis.get(tk, {})
        points = td.get("key_points", [])
        points_text = "<br>".join([f"• {p}" for p in points[:3]]) if points else "暂无要点"
        topic_details += f"""<div class="topic-block">
            <div class="topic-name">{tn}</div>
            <div class="topic-score" style="color:{_score_color(td.get('score', 0.5))}">{td.get('score', 0.5)*100:.1f}%</div>
            <div class="topic-summary">{td.get('summary', '')}</div>
            <div class="topic-points">{points_text}</div>
        </div>"""

    # 构建完整 HTML
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Python 3.11 兼容：f-string 表达式不能包含反斜杠，需提前定义变量
    _NL = "\n"

    full_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>📊 情绪分析报告 - {stock_name}({stock_code})</title>
    <script src="https://cdn.plot.ly/plotly-2.27.0.min.js" charset="utf-8"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            background: linear-gradient(135deg, #0f0c29, #16213e, #1a1a2e);
            color: #e0e0e0;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{ max-width: 1400px; margin: 0 auto; }}
        .report-header {{
            text-align: center; padding: 30px 20px;
            background: linear-gradient(135deg, rgba(26,26,46,0.9), rgba(22,33,62,0.9));
            border-radius: 20px; margin-bottom: 25px;
            border: 1px solid rgba(255,255,255,0.05); backdrop-filter: blur(10px);
        }}
        .report-header h1 {{ font-size: 28px; background: linear-gradient(90deg, #00ff88, #4488ff); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
        .report-header .subtitle {{ color: #888; font-size: 14px; margin-top: 8px; }}
        .summary-box {{
            background: rgba(26,26,46,0.8); border-radius: 15px; padding: 20px; margin-bottom: 25px;
            border: 1px solid rgba(0,255,136,0.1);
        }}
        .summary-box p {{ line-height: 1.8; color: #ccc; font-size: 15px; }}
        .summary-box .label {{ color: #4488ff; font-weight: bold; }}
        .chart-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-bottom: 25px; }}
        .chart-card {{
            background: rgba(26,26,46,0.8); border-radius: 15px; padding: 20px;
            border: 1px solid rgba(255,255,255,0.05); overflow: hidden;
        }}
        .chart-card > div {{ width: 100% !important; }}
        .chart-card.half-left {{ grid-column: 1; }}
        .chart-card.half-right {{ grid-column: 2; }}
        .chart-card.full-width {{ grid-column: 1 / -1; }}
        .chart-title {{ font-size: 16px; font-weight: bold; color: #ccc; margin-bottom: 10px; padding-bottom: 8px; border-bottom: 1px solid rgba(255,255,255,0.05); }}
        .news-item {{ background: rgba(26,26,46,0.6); border-radius: 12px; padding: 15px; margin-bottom: 10px; border-left: 3px solid #4488ff; }}
        .news-title {{ font-size: 15px; font-weight: bold; color: #e0e0e0; }}
        .news-meta {{ font-size: 12px; color: #888; margin: 5px 0; }}
        .news-content {{ font-size: 13px; color: #aaa; line-height: 1.6; }}
        .news-link {{ display: inline-block; margin-top: 8px; color: #4488ff; text-decoration: none; font-size: 13px; }}
        .news-link:hover {{ color: #00ff88; }}
        .risk-item {{ display: flex; align-items: center; gap: 15px; padding: 10px 15px; background: rgba(26,26,46,0.6); border-radius: 10px; margin-bottom: 15px; }}
        .risk-factor {{ font-weight: bold; color: #ff8844; min-width: 60px; font-size: 14px; }}
        .risk-desc {{ color: #aaa; flex: 1; font-size: 13px; }}
        .risk-severity {{ padding: 2px 10px; border-radius: 10px; font-size: 12px; color: white; }}
        .event-chip {{ display: inline-flex; align-items: center; gap: 15px; background: rgba(26,26,46,0.6); padding: 8px 15px; border-radius: 20px; margin: 5px; font-size: 13px; }}
        .event-date {{ color: #4488ff; }}
        .event-text {{ color: #ccc; }}
        .event-score {{ font-weight: bold; }}
        .topic-block {{ background: rgba(26,26,46,0.6); border-radius: 12px; padding: 15px; margin-bottom: 10px; border-left: 3px solid #4488ff; }}
        .topic-name {{ font-weight: bold; font-size: 15px; color: #e0e0e0; }}
        .topic-score {{ font-size: 14px; font-weight: bold; }}
        .topic-summary {{ font-size: 13px; color: #aaa; margin: 5px 0; }}
        .topic-points {{ font-size: 12px; color: #888; }}
        .ai-conclusion {{ background: linear-gradient(135deg, rgba(0,255,136,0.08), rgba(68,136,255,0.08)); border-radius: 10px; padding: 10px 18px; margin-bottom: 12px; border: 1px solid rgba(0,255,136,0.15); display: flex; align-items: center; gap: 15px; }}
        .ai-badge {{ background: linear-gradient(135deg, #00ff88, #4488ff); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-weight: bold; font-size: 14px; white-space: nowrap; }}
        .ai-text {{ color: #ccc; font-size: 12px; line-height: 1.4; }}
        .dash-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin-bottom: 12px; }}
        .dash-grid-5 {{ grid-template-columns: repeat(5, 1fr); }}
        .dash-card {{ background: rgba(26,26,46,0.8); border-radius: 10px; padding: 10px; text-align: center; border: 1px solid rgba(255,255,255,0.05); }}
        .dash-card.wide-card {{ grid-column: span 1; }}
        .dash-value {{ font-size: 26px; font-weight: bold; }}
        .dash-label {{ font-size: 11px; color: #888; margin-top: 2px; }}
        .dashboard-quote {{ background: rgba(26,26,46,0.8); border-radius: 10px; padding: 8px 16px; margin-bottom: 15px; border: 1px solid rgba(255,255,255,0.05); font-size: 14px; }}
        .quote-price {{ font-size: 28px; font-weight: bold; color: #e0e0e0; }}
        .quote-change {{ font-weight: bold; font-size: 14px; margin-left: 8px; }}
        .quote-divider {{ color: #444; margin: 0 8px; }}
        .dashboard-market {{ font-size: 13px; color: #888; margin-bottom: 10px; padding: 0 5px; }}
        .topic-tags {{ display: flex; flex-wrap: wrap; gap: 6px; }}
        .topic-tag {{ padding: 2px 8px; border-radius: 10px; font-size: 11px; white-space: nowrap; }}
        .vol-bar-bg {{ background: rgba(255,255,255,0.05); border-radius: 4px; height: 4px; overflow: hidden; }}
        .vol-bar-fg {{ height: 100%; border-radius: 4px; transition: width 0.5s; }}
        .sentiment-ratio-bar {{ display: flex; height: 6px; border-radius: 3px; overflow: hidden; gap: 1px; }}
        .ratio-pos {{ background: #00ff88; }}
        .ratio-neu {{ background: #ffcc44; }}
        .ratio-neg {{ background: #ff4444; }}
        @media (max-width: 768px) {{
            .chart-grid {{ grid-template-columns: 1fr; }}
            .chart-card.half-left, .chart-card.half-right {{ grid-column: 1; }}
            .dash-grid {{ grid-template-columns: repeat(2, 1fr); }}
            .ai-conclusion {{ flex-direction: column; text-align: center; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="report-header">
            <h1>📊 情绪分析报告 - {stock_name}({stock_code})</h1>
            <div class="subtitle">生成时间: {now_str}</div>
        </div>

        {_ai_conclusion(sentiment_result, news_list)}

        {_dashboard(sentiment_result, quote, market, len(news_list), fund_flow)}

        {summary_text and f'''
        <div class="summary-box">
            <p><span class="label">📝 分析总结:</span> {summary_text}</p>
            {market_exp and f'<p style="margin-top:10px"><span class="label">📊 市场预期:</span> {market_exp}</p>'}
            {trend_pred and f'<p style="margin-top:10px"><span class="label">🔮 趋势预测:</span> {trend_pred}</p>'}
        </div>
        ''' or ''}

        {events_parts and f'''
        <div class="summary-box">
            <p><span class="label">📍 关键事件时间线</span></p>
            <div style="display:flex;flex-wrap:wrap;margin-top:10px">{_NL.join(events_parts)}</div>
        </div>
        ''' or ''}

        <div class="chart-grid">{_NL.join(charts)}</div>

        {topic_details and f'''
        <div class="summary-box">
            <p><span class="label">🎯 主题分析详情</span></p>
            <div style="margin-top:10px">{topic_details}</div>
        </div>
        ''' or ''}

        {risk_parts and f'''
        <div class="summary-box">
            <p><span class="label">⚠️ 风险因素</span></p>
            <div style="margin-top:10px">{_NL.join(risk_parts)}</div>
        </div>
        ''' or ''}

        {news_parts and f'''
        <div class="summary-box">
            <p><span class="label">📰 相关新闻 <span style="color:#888;font-size:13px">（仅展示前10条）</span></span></p>
            <div style="margin-top:10px">{_NL.join(news_parts)}</div>
        </div>
        ''' or ''}
    </div>
</body>
</html>"""

    # 保存文件
    if output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"情绪分析_{stock_code}_{stock_name}_{timestamp}.html"
        output_path = REPORT_DIR / filename

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(full_html, encoding="utf-8")

    return str(output_path)


# ======================================================================
# 云端回测报告生成器 (纯 Python + Plotly.js CDN)
# ======================================================================

def generate_backtest_report(
    stock_code: str,
    stock_name: str,
    results: dict,           # {strategy_key: result_dict} from cloud_backtest
    capital: float = 100000,
    lookback_days: int = 7,
    kline_data: list = None,
    sentiment_result: dict = None,
    output_path: Path = None,
) -> str:
    """
    生成完整的云端 HTML 回测报告（零外部依赖，Plotly.js CDN 渲染）

    Args:
        stock_code: 股票代码
        stock_name: 股票名称
        results: compare_strategies_cloud() 返回的完整结果字典
        capital: 初始资金
        lookback_days: 回溯天数
        kline_data: K线数据（用于价格走势图）
        sentiment_result: 情感分析结果
        output_path: 输出路径，默认自动生成

    Returns:
        生成的HTML文件路径
    """
    # ---- 入口防御：检查最小数据要求 ----
    if not results:
        raise ValueError("回测结果为空")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    _NL = "\n"

    # ---- 策略数据整理 ----
    strategy_order = ["buy_hold", "sentiment_only", "sentiment_ma",
                      "rsi_mean_reversion", "bollinger_breakout", "momentum"]
    strat_names = {
        "buy_hold": "买入持有", "sentiment_only": "纯情绪信号",
        "sentiment_ma": "情绪+均线", "rsi_mean_reversion": "RSI均值回归",
        "bollinger_breakout": "布林带突破", "momentum": "动量策略",
    }

    valid_results = {}
    for key in strategy_order:
        if key in results and "error" not in results[key] and results[key].get("total_return") is not None:
            valid_results[key] = results[key]

    if not valid_results:
        raise ValueError("无有效回测结果可生成报告")

    # 找最佳策略
    best_key = max(valid_results.keys(), key=lambda k: valid_results[k].get("total_return", -999))
    best_res = valid_results[best_key]

    # ---- 防御性K线日期截取（防止历史旧数据污染图表） ----
    from datetime import timedelta
    _today_str = datetime.now().strftime("%Y-%m-%d")
    _cutoff_date = (datetime.now() - timedelta(days=lookback_days * 2)).strftime("%Y-%m-%d")
    if kline_data and len(kline_data) > 3:
        _original_count = len(kline_data)
        # 过滤：只保留最近 lookback_days*2 天的K线数据
        _filtered = [k for k in kline_data if k.get("date", "") >= _cutoff_date]
        if _filtered:
            # 确保至少有足够的数据点用于显示
            if len(_filtered) >= 3:
                kline_data = _filtered
            else:
                # 如果过滤后太少，取最后N条作为保底
                kline_data = kline_data[-max(lookback_days, 30):]
        else:
            # 过滤结果为空（日期格式可能不匹配），取最后N条
            kline_data = kline_data[-max(lookback_days, 30):]
        if len(kline_data) != _original_count:
            print(f"[BT-REPORT] K线截取: {_original_count}条 -> {len(kline_data)}条 ( cutoff={_cutoff_date} )")

    # ---- 图表1：权益曲线对比 ----
    equity_chart_html = ""
    if len(valid_results) >= 1:
        uid_eq = f"eq_{_uid()}"
        eq_traces = []
        colors_map = {"buy_hold": "#888888", "sentiment_only": "#00ff88",
                      "sentiment_ma": "#4488ff", "rsi_mean_reversion": "#ff8844",
                      "bollinger_breakout": "#ff44cc", "momentum": "#ffcc44"}

        # 收集所有日期（取并集）
        all_dates_set = set()
        eq_data = {}  # key -> [(date, value), ...]
        for key, res in valid_results.items():
            ec = res.get("equity_curve", [])
            if ec:
                eq_data[key] = [(e["date"], e["value"]) for e in ec]
                for e in ec:
                    all_dates_set.add(e["date"])

        all_dates = sorted(all_dates_set)

        if all_dates and eq_data:
            for key in strategy_order:
                if key not in eq_data:
                    continue
                val_map = dict(eq_data[key])
                # 对齐到所有日期（前值填充）
                aligned_vals = []
                last_v = None
                for d in all_dates:
                    if d in val_map:
                        last_v = val_map[d]
                    aligned_vals.append(last_v if last_v else capital)
                eq_traces.append({
                    "type": "scatter", "x": all_dates, "y": aligned_vals,
                    "mode": "lines", "name": strat_names.get(key, key),
                    "line": {"color": colors_map.get(key, "#00ff88"), "width": 2 if key == best_key else 1.5},
                    "opacity": 1.0 if key == best_key else 0.7,
                })

            if eq_traces:
                eq_layout = {
                    "template": _dark_template(),
                    "height": 450,
                    "showlegend": True,
                    "legend": {"x": 0.01, "y": 0.99, "bgcolor": "rgba(26,26,46,0.85)", "font": {"size": 11}},
                    "hovermode": "x unified",
                    "margin": {"l": 60, "r": 30, "t": 40, "b": 30},
                    "xaxis": {"title": "日期", "gridcolor": "#2a2a4a"},
                    "yaxis": {"title": "账户净值 (元)", "gridcolor": "#2a2a4a"},
                    "shapes": [
                        {"type": "line", "x0": all_dates[0], "x1": all_dates[-1] if all_dates else all_dates[0],
                         "xref": "x", "y0": capital, "y1": capital, "yref": "y",
                         "line": {"color": "#666666", "dash": "dot", "width": 1}},
                    ],
                    "annotations": [
                        {"x": 1, "xanchor": "right", "xref": "x",
                         "y": capital * 1.02, "yref": "y", "yanchor": "bottom",
                         "text": f"初始资金: {capital:,.0f}元", "showarrow": False,
                         "font": {"size": 11, "color": "#888"},
                         "bgcolor": "rgba(22,33,62,0.8)"},
                    ],
                }
                equity_chart_html = _plotly_div(uid_eq, eq_traces, eq_layout)

    # ---- 图表2：回撤对比 ----
    drawdown_chart_html = ""
    if len(valid_results) >= 1:
        uid_dd = f"dd_{_uid()}"
        dd_traces = []
        for key in strategy_order:
            if key not in valid_results:
                continue
            ec = valid_results[key].get("equity_curve", [])
            if not ec:
                continue
            values = [e["value"] for e in ec]
            dates = [e["date"] for e in ec]
            # 计算回撤
            dd_values = []
            peak = 0
            for v in values:
                if v > peak:
                    peak = v
                dd = (peak - v) / peak * 100 if peak > 0 else 0
                dd_values.append(round(dd, 2))
            dd_traces.append({
                "type": "scatter", "x": dates, "y": dd_values,
                "mode": "lines", "name": strat_names.get(key, key),
                "line": {"color": colors_map.get(key, "#00ff88"), "width": 1.5},
                "fill": "tozeroy" if key == best_key else "none",
                "fillcolor": f"rgba({_hex_to_rgb(colors_map.get(best_key, '#00ff88'))},0.1)" if key == best_key else None,
            })
        if dd_traces:
            dd_layout = {
                "template": _dark_template(),
                "height": 350,
                "showlegend": True,
                "legend": {"x": 0.01, "y": 0.99, "bgcolor": "rgba(26,26,46,0.85)", "font": {"size": 10}},
                "hovermode": "x unified",
                "margin": {"l": 50, "r": 30, "t": 30, "b": 30},
                "xaxis": {"title": "日期", "gridcolor": "#2a2a4a"},
                "yaxis": {"title": "回撤 (%)", "gridcolor": "#2a2a4a"},
            }
            drawdown_chart_html = _plotly_div(uid_dd, dd_traces, dd_layout)

    # ---- 图表3：收益/风险散点图 ----
    scatter_chart_html = ""
    if len(valid_results) >= 2:
        uid_sc = f"sc_{_uid()}"
        sc_traces = []
        sc_annotations = []
        for idx, (key, res) in enumerate(valid_results.items()):
            ret = res.get("total_return", 0)
            dd = res.get("max_drawdown", 0)
            name = strat_names.get(key, key)
            is_best = (key == best_key)
            sc_traces.append({
                "type": "scatter", "x": [dd], "y": [ret],
                "mode": "markers+text", "name": name,
                "marker": {"size": 18 if is_best else 14,
                          "color": colors_map.get(key, "#00ff88"),
                          "symbol": "star" if is_best else "circle",
                          "line": {"width": 2 if is_best else 1, "color": "#fff"}},
                "text": [name],
                "textposition": "top center",
                "textfont": {"size": 11, "color": "#ccc", "weight": "bold" if is_best else "normal"},
            })
        if sc_traces:
            sc_layout = {
                "template": _dark_template(),
                "height": 380,
                "showlegend": False,
                "hovermode": "closest",
                "margin": {"l": 55, "r": 30, "t": 30, "b": 40},
                "xaxis": {"title": "最大回撤 (%)", "gridcolor": "#2a2a4a"},
                "yaxis": {"title": "总收益率 (%)", "gridcolor": "#2a2a4a"},
                "shapes": [
                    {"type": "line", "x0": 0, "x1": 100, "xref": "x", "y0": 0, "y1": 0, "yref": "y",
                     "line": {"color": "#555", "width": 1}},
                ],
                "annotations": [
                    {"x": 5, "xref": "x", "y": 0.95, "yref": "paper",
                     "text": "左上角最优 (低回撤 + 高收益)",
                     "showarrow": False, "font": {"size": 10, "color": "#888"},
                     "bgcolor": "rgba(22,33,62,0.75)"},
                ],
            }
            scatter_chart_html = _plotly_div(uid_sc, sc_traces, sc_layout)

    # ---- 图表4：指标雷达图 ----
    radar_chart_html = ""
    if len(valid_results) >= 3:
        uid_rad = f"rad_{_uid()}"
        rad_categories = ["收益率", "夏普比率", "胜率", "(反向)最大回撤"]
        rad_traces = []
        for key in [best_key] + [k for k in valid_results if k != best_key][:2]:
            res = valid_results[key]
            # 归一化到 0-100
            ret_norm = max(0, min(100, (res.get("total_return", 0) + 50)))  # -50%~+150% → 0~200 clamp
            sharpe_norm = max(0, min(100, (res.get("sharpe_ratio", 0) + 3) * 16))  # -3~+3 → 0~100 approx
            win_norm = max(0, min(100, res.get("win_rate", 0)))
            dd_norm = max(0, min(100, 100 - res.get("max_drawdown", 0)))
            rvals = [ret_norm, sharpe_norm, win_norm, dd_norm]
            rad_traces.append({
                "type": "scatterpolar",
                "r": rvals + [rvals[0]],
                "theta": rad_categories + [rad_categories[0]],
                "fill": "toself",
                "name": strat_names.get(key, key),
                "line": {"color": colors_map.get(key, "#00ff88"),
                         "width": 3 if key == best_key else 1.5},
                "fillcolor": f"rgba({_hex_to_rgb(colors_map.get(key, '#00ff88'))},{"0.25" if key == best_key else "0.08"})",
            })

        if rad_traces:
            rad_layout = {
                "template": _dark_template(),
                "polar": {"radialaxis": {"visible": True, "range": [0, 100], "color": "#888"},
                         "bgcolor": "#16213e"},
                "height": 400,
                "showlegend": True,
                "legend": {"x": 0.01, "y": 0.99, "bgcolor": "rgba(26,26,46,0.8)", "font": {"size": 10}},
                "margin": {"l": 40, "r": 40, "t": 30, "b": 30},
            }
            radar_chart_html = _plotly_div(uid_rad, rad_traces, rad_layout)

    # ---- 策略详情表格行 ----
    def _fmt_pct(v, default="--"):
        try:
            fv = float(v)
            return f"{fv:+.2f}%"
        except (TypeError, ValueError):
            return default

    def _fmt_num(v, default="--"):
        try:
            return f"{float(v):,.2f}"
        except (TypeError, ValueError):
            return default

    table_rows = []
    for key in strategy_order:
        if key not in valid_results:
            continue
        res = valid_results[key]
        is_best = (key == best_key)
        tr = res.get("total_return", 0)
        clr = "#00ff88" if tr > 0 else "#ff4444"
        bg_highlight = "background:rgba(0,255,136,0.05);border-left:3px solid #00ff88;" if is_best else ""

        pf = res.get("profit_factor", 0)
        pf_str = f"{pf:.2f}" if pf != float("inf") else "+∞"

        row = f"""<tr style="{bg_highlight}">
            <td style="font-weight:{'bold' if is_best else 'normal'}">
                {'★ ' if is_best else ''}{strat_names.get(key, key)}
            </td>
            <td style="color:{clr};font-weight:bold">{_fmt_pct(tr)}</td>
            <td>{_fmt_pct(res.get('annual_return', 0))}</td>
            <td style="color:#ff4444">{_fmt_pct(res.get('max_drawdown', 0))}</td>
            <td>{_fmt_num(res.get('sharpe_ratio', 0))}</td>
            <td>{res.get('win_rate', 0):.1f}%</td>
            <td>{pf_str}</td>
            <td>{int(res.get('total_trades', 0))}</td>
            <td style="font-weight:bold">¥{_fmt_num(res.get('final_value', capital))}</td>
        </tr>"""
        table_rows.append(row)

    # ---- 最佳策略交易记录 ----
    best_trades = best_res.get("trades", [])
    trade_rows = ""
    for t in best_trades[:20]:  # 最多显示20条
        action = t.get("action", "")
        action_color = "#00ff88" if action == "buy" else "#ff4444"
        action_label = "买入" if action == "buy" else "卖出"
        reason = t.get("reason", "")
        trade_rows += f"""<tr>
            <td>{t.get('date', '')}</td>
            <td style="color:{action_color};font-weight:bold">{action_label}</td>
            <td>¥{t.get('price', 0):,.2f}</td>
            <td>{t.get('shares', 0)}</td>
            <td>¥{t.get('value', 0):,.2f}</td>
            <td>¥{t.get('commission', 0):,.2f}</td>
            <td style="font-size:12px;color:#aaa;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{reason}</td>
        </tr>"""

    # ---- 价格走势图（如果K线数据可用） ----
    price_chart_html = ""
    if kline_data and len(kline_data) >= 3:
        uid_pk = f"pk_{_uid()}"
        dates_p = [k.get("date", "")[-5:] if len(k.get("date", "")) >= 10 else k.get("date", "") for k in kline_data]
        closes_p = [k.get("close", 0) for k in kline_data]

        # 计算均线
        ma5_p = _sma(closes_p, 5)
        ma20_p = _sma(closes_p, 20)

        pk_traces = [
            {"type": "candlestick", "x": dates_p,
             "open": [k.get("open", 0) for k in kline_data],
             "high": [k.get("high", 0) for k in kline_data],
             "low": [k.get("low", 0) for k in kline_data],
             "close": closes_p,
             "name": "K线",
             "increasing": {"line": {"color": "#00ff88", "width": 1}, "fillcolor": "rgba(0,255,136,0.35)"},
             "decreasing": {"line": {"color": "#ff4444", "width": 1}, "fillcolor": "rgba(255,68,68,0.35)"},
             "xaxis": "x", "yaxis": "y"},
            {"type": "scatter", "x": dates_p, "y": ma5_p, "mode": "lines",
             "name": "MA5", "line": {"color": "#4488ff", "width": 1}, "xaxis": "x", "yaxis": "y"},
            {"type": "scatter", "x": dates_p, "y": ma20_p, "mode": "lines",
             "name": "MA20", "line": {"color": "#ff8844", "width": 1}, "xaxis": "x", "yaxis": "y"},
        ]

        # 叠加买卖信号点（仅最佳策略）
        if best_trades:
            buy_dates, buy_prices = [], []
            sell_dates, sell_prices = [], []
            for t in best_trades:
                td = t.get("date", "")
                td_short = td[-5:] if len(td) >= 10 else td
                tp = t.get("price", 0)
                if t.get("action") == "buy":
                    buy_dates.append(td_short)
                    buy_prices.append(tp)
                elif t.get("action") == "sell":
                    sell_dates.append(td_short)
                    sell_prices.append(tp)
            if buy_dates:
                pk_traces.append({"type": "scatter", "x": buy_dates, "y": buy_prices,
                                 "mode": "markers", "name": "买入信号",
                                 "marker": {"size": 12, "color": "#00ff88", "symbol": "triangle-up",
                                           "line": {"width": 1.5, "color": "#fff"}},
                                 "xaxis": "x", "yaxis": "y"})
            if sell_dates:
                pk_traces.append({"type": "scatter", "x": sell_dates, "y": sell_prices,
                                 "mode": "markers", "name": "卖出信号",
                                 "marker": {"size": 12, "color": "#ff4444", "symbol": "triangle-down",
                                           "line": {"width": 1.5, "color": "#fff"}},
                                 "xaxis": "x", "yaxis": "y"})

        pk_layout = {
            "template": _dark_template(),
            "height": 500,
            "showlegend": True,
            "legend": {"x": 0.01, "y": 0.99, "bgcolor": "rgba(26,26,46,0.8)", "font": {"size": 10}},
            "hovermode": "x unified",
            "margin": {"l": 30, "r": 30, "t": 30, "b": 30},
            "xaxis": {"rangeslider": {"visible": False}},
            "yaxis": {"title": "价格 (元)", "gridcolor": "#2a2a4a"},
        }
        price_chart_html = _plotly_div(uid_pk, pk_traces, pk_layout)

    # ---- 情绪信号叠加图 ----
    sentiment_overlay_html = ""
    if sentiment_result and kline_data and len(kline_data) >= 3:
        trend_data = sentiment_result.get("time_analysis", {}).get("trend", [])
        if trend_data:
            uid_so = f"so_{_uid()}"
            dates_so = [k.get("date", "")[-5:] if len(k.get("date", "")) >= 10 else k.get("date", "") for k in kline_data]

            date_score_map = {}
            for tr in trend_data:
                ds = tr.get("date", "")
                sc = tr.get("score", 0.5)
                if ds:
                    date_score_map[ds] = sc * 100

            aligned_scores_so = [date_score_map.get(k.get("date", ""), None) for k in kline_data]
            so_traces = [
                {"type": "scatter", "x": dates_so, "y": aligned_scores_so,
                 "mode": "lines+markers", "name": "情绪得分",
                 "line": {"color": "#ff8844", "width": 2},
                 "marker": {"size": 6, "color": "#ff8844"},
                 "fill": "tozeroy", "fillcolor": "rgba(255,136,68,0.12)"}
            ]
            so_layout = {
                "template": _dark_template(),
                "height": 250,
                "showlegend": True,
                "legend": {"font": {"size": 10}},
                "margin": {"l": 30, "r": 30, "t": 20, "b": 30},
                "yaxis": {"title": "情绪分", "range": [0, 100], "gridcolor": "#2a2a4a"},
                "shapes": [
                    {"type": "line", "x0": 0, "x1": 1, "xref": "x domain",
                     "y0": 65, "y1": 65, "yref": "y",
                     "line": {"color": "#88cc44", "dash": "dash", "width": 1}},
                    {"type": "line", "x0": 0, "x1": 1, "xref": "x domain",
                     "y0": 35, "y1": 35, "yref": "y",
                     "line": {"color": "#ff4444", "dash": "dash", "width": 1}},
                ]
            }
            sentiment_overlay_html = _plotly_div(uid_so, so_traces, so_layout)

    # ---- 构建完整 HTML ----
    full_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>📊 回测报告 - {stock_name}({stock_code})</title>
    <script src="https://cdn.plot.ly/plotly-2.27.0.min.js" charset="utf-8"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            background: linear-gradient(135deg, #0f0c29, #16213e, #1a1a2e);
            color: #e0e0e0;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
            min-height: 100vh;
            padding: 15px;
        }}
        .container {{ max-width: 1400px; margin: 0 auto; }}

        /* 头部 */
        .report-header {{
            text-align: center; padding: 28px 20px;
            background: linear-gradient(135deg, rgba(26,26,46,0.92), rgba(22,33,62,0.92));
            border-radius: 18px; margin-bottom: 20px;
            border: 1px solid rgba(255,255,255,0.06); backdrop-filter: blur(10px);
        }}
        .report-header h1 {{
            font-size: 27px;
            background: linear-gradient(90deg, #00ff88, #4488ff, #ff8844);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        }}
        .report-header .subtitle {{ color: #999; font-size: 13px; margin-top: 6px; }}

        /* 参数栏 */
        .params-bar {{
            display: flex; gap: 20px; justify-content: center; flex-wrap: wrap;
            background: rgba(26,26,46,0.7); border-radius: 12px; padding: 12px 20px;
            margin-bottom: 20px; border: 1px solid rgba(255,255,255,0.04);
        }}
        .param-item {{ font-size: 13px; color: #aaa; }}
        .param-item b {{ color: #e0e0e0; }}
        .param-highlight {{ color: #00ff88; font-weight:bold; }}

        /* 最佳策略卡片 */
        .best-card {{
            background: linear-gradient(135deg, rgba(0,255,136,0.08), rgba(68,136,255,0.05));
            border-radius: 15px; padding: 20px 24px; margin-bottom: 20px;
            border: 1px solid rgba(0,255,136,0.15); text-align:center;
        }}
        .best-label {{ font-size: 14px; color: #00ff88; margin-bottom: 4px; }}
        .best-name {{ font-size: 26px; font-weight: bold; color: #fff; }}
        .best-return {{ font-size: 36px; font-weight: bold; margin-top: 6px; }}
        .best-return.pos {{ color: #00ff88; }}
        .best-return.neg {{ color: #ff4444; }}
        .best-metrics {{ display:flex; gap:20px; justify-content:center; margin-top:12px; flex-wrap:wrap; }}
        .bm-item {{ text-align: center; }}
        .bm-val {{ font-size: 17px; font-weight: bold; color: #e0e0e0; }}
        .bm-lbl {{ font-size: 11px; color: #888; margin-top: 2px; }}

        /* 表格 */
        .table-card {{
            background: rgba(26,26,46,0.8); border-radius: 15px; padding: 18px; margin-bottom: 20px;
            border: 1px solid rgba(255,255,255,0.04); overflow-x:auto;
        }}
        .table-title {{ font-size: 16px; font-weight: bold; color: #ccc; margin-bottom: 12px; }}
        .bt-table {{
            width: 100%; border-collapse: collapse; font-size: 13px;
        }}
        .bt-table th {{
            background: rgba(0,255,136,0.08); color: #00ff88; padding: 10px 8px;
            text-align: center; font-size: 12px; white-space: nowrap; border-bottom: 1px solid rgba(255,255,255,0.06);
        }}
        .bt-table td {{
            padding: 9px 8px; text-align: center; border-bottom: 1px solid rgba(255,255,255,0.03);
            white-space: nowrap; font-size: 13px;
        }}
        .bt-table tr:hover {{ background: rgba(255,255,255,0.03); }}

        /* 图表 */
        .chart-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-bottom: 20px; }}
        .chart-card {{
            background: rgba(26,26,46,0.8); border-radius: 15px; padding: 18px;
            border: 1px solid rgba(255,255,255,0.04); overflow: hidden;
        }}
        .chart-card > div {{ width: 100% !important; }}
        .chart-card.full-width {{ grid-column: 1 / -1; }}
        .chart-title {{ font-size: 15px; font-weight: bold; color: #ccc; margin-bottom: 10px; padding-bottom: 8px; border-bottom: 1px solid rgba(255,255,255,0.05); }}

        /* 交易记录 */
        .trade-table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
        .trade-table th {{
            background: rgba(68,136,255,0.08); color: #4488ff; padding: 8px 6px;
            text-align: center; font-size: 11px; border-bottom: 1px solid rgba(255,255,255,0.06);
        }}
        .trade-table td {{
            padding: 7px 6px; text-align: center; border-bottom: 1px solid rgba(255,255,255,0.03);
            font-size: 12px;
        }}
        .trade-table tr:hover {{ background: rgba(255,255,255,0.03); }}

        /* 结论 */
        .conclusion-box {{
            background: linear-gradient(135deg, rgba(0,255,136,0.05), rgba(68,136,255,0.05));
            border-radius: 12px; padding: 16px 20px; margin-bottom: 20px;
            border: 1px solid rgba(0,255,136,0.1); font-size: 14px; line-height: 1.8; color: #bbb;
        }}
        .conclusion-box strong {{ color: #00ff88; }}

        /* 页脚 */
        .footer {{ text-align: center; color: #555; font-size: 11px; padding: 15px; margin-top: 10px; }}

        @media (max-width: 768px) {{
            .chart-grid {{ grid-template-columns: 1fr; }}
            .params-bar {{ flex-direction: column; gap: 8px; align-items: center; }}
            .bt-table {{ font-size: 11px; }}
            .bt-table th, .bt-table td {{ padding: 6px 4px; }}
            .best-metrics {{ flex-direction: column; gap: 8px; }}
        }}
    </style>
</head>
<body>
<div class="container">

    <!-- 头部 -->
    <div class="report-header">
        <h1>📊 策略回测报告</h1>
        <div class="subtitle">{stock_name} ({stock_code}) | 生成时间: {now_str}</div>
    </div>

    <!-- 参数 -->
    <div class="params-bar">
        <span class="param-item">初始资金: <b>¥{capital:,.0f}</b></span>
        <span class="param-item">回溯周期: <b>近{lookback_days}天</b></span>
        <span class="param-item">有效策略: <b>{len(valid_results)}个</b></span>
        <span class="param-item">K线数量: <b>{len(kline_data) if kline_data else 0}条</b></span>
    </div>

    <!-- 最佳策略 -->
    <div class="best-card">
        <div class="best-label">🏆 最佳策略</div>
        <div class="best-name">{strat_names.get(best_key, best_key)}</div>
        <div class="best-return {'pos' if best_res.get('total_return',0)>=0 else 'neg'}">
            {best_res.get('total_return',0):+.2f}%
        </div>
        <div class="best-metrics">
            <div class="bm-item"><div class="bm-val">¥{best_res.get('final_value',capital):,.0f}</div><div class="bm-lbl">最终净值</div></div>
            <div class="bm-item"><div class="bm-val">{best_res.get('annual_return',0):+.2f}%</div><div class="bm-lbl">年化收益</div></div>
            <div class="bm-item"><div class="bm-val" style="color:#ff4444">{best_res.get('max_drawdown',0):.2f}%</div><div class="bm-lbl">最大回撤</div></div>
            <div class="bm-item"><div class="bm-val">{best_res.get('sharpe_ratio',0):.2f}</div><div class="bm-lbl">夏普比率</div></div>
            <div class="bm-item"><div class="bm-val">{best_res.get('win_rate',0):.1f}%</div><div class="bm-lbl">胜率</div></div>
            <div class="bm-item"><div class="bm-val">{int(best_res.get('total_trades',0))}</div><div class="bm-lbl">交易次数</div></div>
        </div>
    </div>

    <!-- 策略对比表 -->
    <div class="table-card">
        <div class="table-title">📋 六策略详细对比</div>
        <table class="bt-table">
            <thead><tr>
                <th>策略名称</th><th>总收益率</th><th>年化收益</th><th>最大回撤</th>
                <th>夏普比率</th><th>胜率</th><th>盈亏比</th><th>交易次数</th><th>最终净值</th>
            </tr></thead>
            <tbody>{_NL.join(table_rows)}</tbody>
        </table>
    </div>

    <!-- 权益曲线 -->
    {f'<div class="chart-card full-width"><div class="chart-title">📈 各策略权益曲线对比</div>{equity_chart_html}</div>' if equity_chart_html else ''}

    <!-- 价格走势 + 信号 -->
    {f'<div class="chart-card full-width"><div class="chart-title">📉 价格走势与【{strat_names.get(best_key,best_key)}】交易信号</div>{price_chart_html}</div>' if price_chart_html else ''}
    {f'<div class="chart-card full-width"><div class="chart-title">💬 情绪信号时间序列</div>{sentiment_overlay_html}</div>' if sentiment_overlay_html else ''}

    <!-- 回撤对比 -->
    {f'<div class="chart-card full-width"><div class="chart-title">📉 各策略回撤曲线</div>{drawdown_chart_html}</div>' if drawdown_chart_html else ''}

    <!-- 收益/风险散点 + 雷达 -->
    {f'<div class="chart-grid">' + _NL.join([
        f'<div class="chart-card"><div class="chart-title">🎯 收益 vs 风险分布</div>{scatter_chart_html}</div>',
        f'<div class="chart-card"><div class="chart-title">🔸 核心指标雷达</div>{radar_chart_html}</div>'
    ]) + '</div>' if scatter_chart_html or radar_chart_html else ''}

    <!-- 交易记录 -->
    {f'''<div class="table-card">
        <div class="table-title">📝 【{strat_names.get(best_key,best_key)}】交易记录（最近{min(len(best_trades),20)}条）</div>
        <table class="trade-table">
            <thead><tr><th>日期</th><th>方向</th><th>价格</th><th>股数</th><th>金额</th><th>手续费</th><th>原因</th></tr></thead>
            <tbody>{trade_rows}</tbody>
        </table>
    </div>''' if trade_rows else ''}

    <!-- 结论 -->
    <div class="conclusion-box">
        <strong>回测结论：</strong>
        在近{lookback_days}天的回测周期内，
        <strong>{strat_names.get(best_key,best_key)}</strong>以<strong>{best_res.get('total_return',0):+.2f}%</strong>的收益率表现最佳，
        最大回撤为<strong style="color:#ff4444">{best_res.get('max_drawdown',0):.2f}%</strong>，
        夏普比率为<strong>{best_res.get('sharpe_ratio',0):.2f}</strong>。
        共执行了<strong>{int(best_res.get('total_trades',0))}</strong>笔交易，胜率达<strong>{best_res.get('win_rate',0):.1f}%</strong>。
        {"⚠️ 注意：回测结果不代表未来表现，仅供参考。" if lookback_days < 30 else "⚠️ 注意：历史回测不代表未来表现，市场有风险。"}
    </div>

    <div class="footer">
        SentimentQuant 回测引擎 · 云端版 (Render) · 纯 Python 零依赖计算
    </div>
</div>
</body>
</html>"""

    # 保存文件
    if output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"回测报告_{stock_code}_{stock_name}_{timestamp}.html"
        output_path = REPORT_DIR / filename

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(full_html, encoding="utf-8")

    return str(output_path)
