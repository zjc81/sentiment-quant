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
    return _plotly_div(uid, traces, layout)


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

    # MACD
    macd_line = [ema12[i] - ema26[i] for i in range(len(closes))]
    signal_line = _ema(macd_line, 9)
    macd_hist = [macd_line[i] - signal_line[i] for i in range(len(macd_line))]

    # 情绪信号对齐
    trend_data = sentiment_result.get("time_analysis", {}).get("trend", [])
    date_score = {t["date"]: t["score"] * 100 for t in trend_data}
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
    charts.append(f'<div class="chart-card">{_plotly_gauge(uid1, score*100,
        f"综合情感评分<br><span style=\'font-size:16px;color:{_label_color(label)}\'>{label}</span>",
        color="#00ff88", height=300)}</div>')

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
            <div style="display:flex;flex-wrap:wrap;margin-top:10px">{"\\n".join(events_parts)}</div>
        </div>
        ''' or ''}

        <div class="chart-grid">{"\\n".join(charts)}</div>

        {topic_details and f'''
        <div class="summary-box">
            <p><span class="label">🎯 主题分析详情</span></p>
            <div style="margin-top:10px">{topic_details}</div>
        </div>
        ''' or ''}

        {risk_parts and f'''
        <div class="summary-box">
            <p><span class="label">⚠️ 风险因素</span></p>
            <div style="margin-top:10px">{"\\n".join(risk_parts)}</div>
        </div>
        ''' or ''}

        {news_parts and f'''
        <div class="summary-box">
            <p><span class="label">📰 相关新闻 <span style="color:#888;font-size:13px">（仅展示前10条）</span></span></p>
            <div style="margin-top:10px">{"\\n".join(news_parts)}</div>
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
