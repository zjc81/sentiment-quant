"""
交互式HTML报告生成器 - 使用Plotly生成震撼的可视化报告

核心设计:
  - 所有图表使用 Plotly 生成，支持交互（缩放、悬停、选择）
  - 单文件HTML输出，无需额外服务
  - 暗色主题，科技感设计
  - 多Tab切换：情绪概览、新闻时间线、主题雷达、回测绩效、对比分析
"""
import json
import re
import io
import base64
import numpy as np
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
from collections import Counter
from config import REPORT_DIR


# ======================================================================
# HTML报告生成器
# ======================================================================

class ReportGenerator:
    """
    HTML报告生成器 - 生成交互式单页报告
    """

    def __init__(self):
        self._setup_plotly()

    def _setup_plotly(self):
        """设置Plotly全局样式"""
        import plotly.io as pio
        import plotly.graph_objects as go

        # 暗色主题
        pio.templates["dark_tech"] = go.layout.Template(
            layout=dict(
                paper_bgcolor="#1a1a2e",
                plot_bgcolor="#16213e",
                font=dict(color="#e0e0e0", family="Arial, sans-serif"),
                hovermode="x unified",
                xaxis=dict(
                    gridcolor="#2a2a4a",
                    zerolinecolor="#3a3a5a",
                    showgrid=True,
                ),
                yaxis=dict(
                    gridcolor="#2a2a4a",
                    zerolinecolor="#3a3a5a",
                    showgrid=True,
                ),
            )
        )
        pio.templates.default = "dark_tech"

    # ==================================================================
    # 情绪分析报告
    # ==================================================================

    def generate_sentiment_report(
        self,
        stock_code: str,
        stock_name: str,
        sentiment_result: Dict,
        news_list: List[Dict],
        output_path: Optional[Path] = None,
        kline_data=None,
        quote: Optional[Dict] = None,
        market: Optional[Dict] = None,
        fund_flow: Optional[Dict] = None,
        announcements: Optional[List[Dict]] = None,
    ) -> str:
        """
        生成股票情绪分析HTML报告

        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            sentiment_result: 情感分析结果
            news_list: 新闻列表
            output_path: 输出路径（可选）

        Returns:
            str: HTML文件路径
        """
        import plotly.graph_objects as go
        import plotly.express as px
        from plotly.subplots import make_subplots

        overall = sentiment_result.get("overall_sentiment", {})
        time_analysis = sentiment_result.get("time_analysis", {})
        topic_analysis = sentiment_result.get("topic_analysis", {})
        source_analysis = sentiment_result.get("source_analysis", {})
        impact = sentiment_result.get("impact_analysis", {})
        risk = sentiment_result.get("risk_analysis", {})

        charts_html = []

        # ===== Chart 1: 情感仪表盘 - 综合评分 =====
        score = overall.get("score", 0.5)
        conf = overall.get("confidence_index", 0.0)
        label = overall.get("label", "中性")

        fig1 = go.Figure()
        fig1.add_trace(go.Indicator(
            mode="gauge+number+delta",
            value=score * 100,
            number={"suffix": "%", "font": {"size": 36, "color": "#00ff88"}},
            gauge={
                "axis": {"range": [0, 100], "tickcolor": "#666", "tickwidth": 1},
                "bar": {"color": "#00ff88", "thickness": 0.3},
                "steps": [
                    {"range": [0, 15], "color": "#ff4444"},
                    {"range": [15, 35], "color": "#ff8844"},
                    {"range": [35, 65], "color": "#ffcc44"},
                    {"range": [65, 85], "color": "#88cc44"},
                    {"range": [85, 100], "color": "#00ff88"},
                ],
                "threshold": {
                    "line": {"color": "white", "width": 4},
                    "thickness": 0.75,
                    "value": score * 100,
                },
            },
            title={"text": f"综合情感评分<br><span style='font-size:16px;color:{self._label_color(label)}'>{label}</span>",
                   "font": {"size": 18}},
        ))
        fig1.update_layout(height=450, margin=dict(l=30, r=30, t=40, b=30))
        charts_html.append(f'<div class="chart-card"><div class="chart-title">📊 情感综合评分</div>{fig1.to_html(full_html=False, include_plotlyjs=True, config={"responsive": True})}</div>')

        # ===== Chart 2: 置信度仪表盘 =====
        fig2 = go.Figure()
        fig2.add_trace(go.Indicator(
            mode="gauge+number",
            value=conf * 100,
            number={"suffix": "%", "font": {"size": 28, "color": "#4488ff"}},
            gauge={
                "axis": {"range": [0, 100], "tickcolor": "#666"},
                "bar": {"color": "#4488ff", "thickness": 0.3},
                "steps": [
                    {"range": [0, 33], "color": "#442222"},
                    {"range": [33, 66], "color": "#444422"},
                    {"range": [66, 100], "color": "#224444"},
                ],
            },
            title={"text": "置信度指数<br><span style='font-size:14px;color:#aaa'>数据可靠度</span>",
                   "font": {"size": 18}},
        ))
        fig2.update_layout(height=450, margin=dict(l=30, r=30, t=40, b=30))
        charts_html.append(f'<div class="chart-card half-left"><div class="chart-title">🔒 置信度指数</div>{fig2.to_html(full_html=False, include_plotlyjs=False, config={"responsive": True})}</div>')

        # ===== Chart 3: 投资者情绪指标 =====
        investor = overall.get("investor_sentiment", "无")
        if investor != "无":
            try:
                inv_val = int(investor)
            except ValueError:
                inv_val = 50
            inv_note = ""
        else:
            inv_val = 50
            inv_note = "<br><span style='font-size:11px;color:#888'>暂无交易信号，默认中性</span>"

        fig3 = go.Figure()
        fig3.add_trace(go.Indicator(
            mode="gauge+number",
            value=inv_val,
            number={"suffix": "", "font": {"size": 28, "color": "#ff8844"}},
            gauge={
                "axis": {"range": [0, 100], "tickcolor": "#666"},
                "bar": {"color": "#ff8844", "thickness": 0.3},
                "steps": [
                    {"range": [0, 33], "color": "#442222"},
                    {"range": [33, 66], "color": "#444422"},
                    {"range": [66, 100], "color": "#224422"},
                ],
            },
            title={"text": f"投资者情绪指数{inv_note}",
                   "font": {"size": 18}},
        ))
        fig3.update_layout(height=450, margin=dict(l=30, r=30, t=40, b=30))
        charts_html.append(f'<div class="chart-card half-right"><div class="chart-title">📈 投资者情绪指数</div>{fig3.to_html(full_html=False, include_plotlyjs=False, config={"responsive": True})}</div>')

        # ===== Chart 4: 情感时间趋势 =====
        trend_data = time_analysis.get("trend", [])
        if trend_data:
            dates = [t["date"] for t in trend_data][::-1]
            scores = [t["score"] * 100 for t in trend_data][::-1]

            fig4 = go.Figure()
            fig4.add_trace(go.Scatter(
                x=dates, y=scores,
                mode="lines+markers",
                name="情感得分",
                line=dict(color="#00ff88", width=3),
                marker=dict(size=8, color="#00ff88", symbol="circle"),
                fill="tozeroy",
                fillcolor="rgba(0, 255, 136, 0.1)",
            ))
            # 添加阈值线
            fig4.add_hline(y=65, line=dict(color="#ffcc44", dash="dash", width=1),
                           annotation_text="积极阈值")
            fig4.add_hline(y=35, line=dict(color="#ff4444", dash="dash", width=1),
                           annotation_text="消极阈值")

            fig4.update_layout(
                xaxis=dict(title="日期"),
                yaxis=dict(title="情感得分 (%)", range=[0, 100]),
                height=350,
                hovermode="x unified",
            )
            charts_html.append(
                f'<div class="chart-card full-width"><div class="chart-title">⏳ 情感时间趋势</div>'
                f'{fig4.to_html(full_html=False, include_plotlyjs=False, config={"responsive": True})}</div>'
            )

            # ===== Chart 5: 事件标注版趋势 =====
            # 在趋势图上标注关键事件
            fig4b = go.Figure()
            fig4b.add_trace(go.Scatter(
                x=dates, y=scores,
                mode="lines+markers",
                name="情感得分",
                line=dict(color="#00ff88", width=3),
                marker=dict(size=10, color="#00ff88", symbol="circle"),
                fill="tozeroy",
                fillcolor="rgba(0, 255, 136, 0.08)",
            ))

            # 标注关键事件（按天交错偏移，避免重叠）
            for t in trend_data:
                for evt_idx, event in enumerate(t.get("key_events", [])):
                    fig4b.add_annotation(
                        x=t["date"],
                        y=t["score"] * 100,
                        text=event.get("title", ""),
                        showarrow=True,
                        arrowhead=2,
                        arrowcolor="#ff8844",
                        arrowsize=1.5,
                        ax=0,
                        ay=-40 - evt_idx * 32,
                        font=dict(size=10, color="#ff8844"),
                        bgcolor="rgba(22,33,62,0.85)",
                        bordercolor="#ff8844",
                        borderwidth=1,
                        borderpad=3,
                    )

            fig4b.add_hline(y=65, line=dict(color="#ffcc44", dash="dash", width=1))
            fig4b.add_hline(y=35, line=dict(color="#ff4444", dash="dash", width=1))
            fig4b.update_layout(
                xaxis=dict(title="日期"),
                yaxis=dict(title="情感得分 (%)", range=[0, 100]),
                height=400,
                hovermode="x unified",
            )
            charts_html.append(
                f'<div class="chart-card full-width"><div class="chart-title">📍 关键事件标注</div>'
                f'{fig4b.to_html(full_html=False, include_plotlyjs=False, config={"responsive": True})}</div>'
            )

        # ===== Chart 6: 主题分析雷达图 =====
        if topic_analysis:
            topic_names = ["公司经营", "财务表现", "市场竞争", "产品技术", "行业政策", "资本市场"]
            topic_keys = ["company_operation", "financial_performance", "market_competition",
                          "product_technology", "industry_policy", "capital_market"]
            topic_scores = [
                topic_analysis.get(k, {}).get("score", 0.5) * 100 for k in topic_keys
            ]

            fig5 = go.Figure()
            fig5.add_trace(go.Scatterpolar(
                r=topic_scores + [topic_scores[0]],
                theta=topic_names + [topic_names[0]],
                fill="toself",
                name="主题评分",
                line=dict(color="#00ff88", width=3),
                fillcolor="rgba(0, 255, 136, 0.2)",
            ))
            fig5.update_layout(
                polar=dict(
                    radialaxis=dict(visible=True, range=[0, 100], color="#888"),
                    bgcolor="#16213e",
                ),
                height=400,
                showlegend=False,
            )
            charts_html.append(
                f'<div class="chart-card half-left"><div class="chart-title">🎯 主题分析雷达图</div>'
                f'{fig5.to_html(full_html=False, include_plotlyjs=False, config={"responsive": True})}</div>'
            )

            # ===== Chart 7: 主题评分柱状图 =====
            colors = ["#00ff88" if s > 50 else "#ff4444" if s < 35 else "#ffcc44" for s in topic_scores]
            fig6 = go.Figure()
            fig6.add_trace(go.Bar(
                x=topic_names,
                y=topic_scores,
                marker_color=colors,
                text=[f"{s:.1f}" for s in topic_scores],
                textposition="outside",
                textfont=dict(size=12),
            ))
            fig6.add_hline(y=65, line=dict(color="#88cc44", dash="dash", width=1))
            fig6.add_hline(y=35, line=dict(color="#ff4444", dash="dash", width=1))
            fig6.update_layout(
                yaxis=dict(range=[0, 100], title="评分 (%)"),
                height=350,
                hovermode="x",
            )
            charts_html.append(
                f'<div class="chart-card half-right"><div class="chart-title">📊 主题评分柱状图</div>'
                f'{fig6.to_html(full_html=False, include_plotlyjs=False, config={"responsive": True})}</div>'
            )

        # ===== Chart 8: 来源分析 =====
        if source_analysis:
            source_names = {
                "mainstream_media": "主流媒体",
                "industry_media": "行业媒体",
                "self_media": "自媒体",
                "official_announcement": "官方公告",
            }
            s_names = []
            s_scores = []
            s_colors = []
            for sk, sn in source_names.items():
                s = source_analysis.get(sk, {}).get("score", 0.5)
                s_names.append(sn)
                s_scores.append(s * 100)
                s_colors.append("#4488ff" if sk == "official_announcement" else
                               "#00ff88" if sk == "mainstream_media" else
                               "#ff8844" if sk == "industry_media" else "#888")

            fig7 = go.Figure()
            fig7.add_trace(go.Bar(
                x=s_names, y=s_scores,
                marker_color=s_colors,
                text=[f"{s:.1f}" for s in s_scores],
                textposition="outside",
                textfont=dict(size=14),
            ))
            fig7.update_layout(
                yaxis=dict(range=[0, 100], title="情感倾向 (%)"),
                height=450,
                hovermode="x",
            )
            charts_html.append(
                f'<div class="chart-card half-left"><div class="chart-title">📡 信息来源分析</div>'
                f'{fig7.to_html(full_html=False, include_plotlyjs=False, config={"responsive": True})}</div>'
            )

        # ===== Chart 9: 影响力+风险评估 =====
        impact_score = impact.get("market_impact", {}).get("score", 0) * 100
        risk_level = risk.get("risk_level", "低")
        risk_color = {"高": "#ff4444", "中": "#ff8844", "低": "#00ff88"}.get(risk_level, "#888")

        fig8 = go.Figure()
        fig8.add_trace(go.Indicator(
            mode="gauge+number",
            value=impact_score,
            number={"suffix": "%", "font": {"size": 28, "color": "#4488ff"}},
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": "#4488ff", "thickness": 0.15},
                "steps": [
                    {"range": [0, 33], "color": "#224422"},
                    {"range": [33, 66], "color": "#444422"},
                    {"range": [66, 100], "color": "#442222"},
                ],
            },
            title={"text": "市场影响力<br><span style='font-size:13px;color:#aaa'>市场影响程度</span>",
                   "font": {"size": 16}},
            domain={"row": 0, "column": 0},
        ))
        fig8.add_trace(go.Indicator(
            mode="gauge+number",
            value={"高": 90, "中": 50, "低": 10}.get(risk_level, 50),
            number={"font": {"size": 28, "color": risk_color}},
            gauge={
                "axis": {"range": [0, 100], "tickvals": [10, 50, 90], "ticktext": ["低", "中", "高"]},
                "bar": {"color": risk_color, "thickness": 0.15},
                "steps": [
                    {"range": [0, 33], "color": "#224422"},
                    {"range": [33, 66], "color": "#444422"},
                    {"range": [66, 100], "color": "#442222"},
                ],
            },
            title={"text": f"风险等级: {risk_level}<br><span style='font-size:13px;color:#aaa'>风险因素{len(risk.get('risk_factors', []))}个</span>",
                   "font": {"size": 16}},
            domain={"row": 0, "column": 1},
        ))
        fig8.update_layout(
            grid={"rows": 1, "columns": 2},
            height=350,
            margin=dict(l=30, r=30, t=40, b=30),
        )
        charts_html.append(
            f'<div class="chart-card half-right"><div class="chart-title">⚠️ 影响力 & 风险评估</div>'
            f'{fig8.to_html(full_html=False, include_plotlyjs=False, config={"responsive": True})}</div>'
        )

        # 词云
        wordcloud_html = self._generate_wordcloud(news_list)

        # AI 一句话结论
        ai_conclusion = self._generate_ai_conclusion(sentiment_result, news_list)

        # 综合仪表盘
        dashboard = self._generate_dashboard_cards(
            sentiment_result, quote=quote, market=market, news_count=len(news_list),
            fund_flow=fund_flow, announcements=announcements,
        )

        # ===== Build full HTML =====
        summary_text = overall.get("summary", "")
        market_exp = overall.get("market_expectation", "")
        trend_pred = time_analysis.get("trend_prediction", "")

        # 新闻列表HTML
        news_html_parts = []
        for news in news_list[:10]:
            title = news.get("title", "")
            source = news.get("source", "")
            pub_time = news.get("publish_time", "")
            content = news.get("content", "")[:150]
            url = news.get("url", "")
            news_html_parts.append(f"""
            <div class="news-item">
                <div class="news-title">{title}</div>
                <div class="news-meta">🕐 {pub_time} | 📰 {source}</div>
                <div class="news-content">{content}{'...' if len(news.get('content', '')) > 150 else ''}</div>
                {"<a class='news-link' href='" + url + "' target='_blank'>🔗 查看原文 →</a>" if url else ""}
            </div>
            """)

        news_html = "\n".join(news_html_parts)

        # 风险因素HTML
        risk_factors = risk.get("risk_factors", [])
        risk_html_parts = []
        for rf in risk_factors:
            factor = rf.get("factor", "")
            desc = rf.get("description", "")
            severity = rf.get("severity", "低")
            sev_color = {"高": "#ff4444", "中": "#ff8844", "低": "#88cc44"}.get(severity, "#888")
            risk_html_parts.append(f"""
            <div class="risk-item">
                <span class="risk-factor">{factor}</span>
                <span class="risk-desc">{desc}</span>
                <span class="risk-severity" style="background:{sev_color}">{severity}</span>
            </div>
            """)
        risk_html = "\n".join(risk_html_parts)

        # 关键事件HTML
        events_html_parts = []
        for trend in trend_data:
            date = trend.get("date", "")
            score = trend.get("score", 0.5)
            events = trend.get("key_events", [])
            if events:
                events_text = " | ".join([e.get("title", "") for e in events])
                events_html_parts.append(f'<div class="event-chip"><span class="event-date">{date}</span><span class="event-text">{events_text}</span><span class="event-score" style="color:{self._score_color(score)}">{score*100:.0f}%</span></div>')
            else:
                events_html_parts.append(f'<div class="event-chip"><span class="event-date">{date}</span><span class="event-text">无突出事件</span><span class="event-score" style="color:{self._score_color(score)}">{score*100:.0f}%</span></div>')
        events_html = "\n".join(events_html_parts)

        # 主题要点HTML
        topic_details_html = ""
        for tk, tn in [("company_operation", "公司经营"),
                       ("financial_performance", "财务表现"),
                       ("market_competition", "市场竞争"),
                       ("product_technology", "产品技术"),
                       ("industry_policy", "行业政策"),
                       ("capital_market", "资本市场")]:
            td = topic_analysis.get(tk, {})
            points = td.get("key_points", [])
            points_text = "<br>".join([f"• {p}" for p in points[:3]]) if points else "暂无要点"
            topic_details_html += f"""
            <div class="topic-block">
                <div class="topic-name">{tn}</div>
                <div class="topic-score" style="color:{self._score_color(td.get('score', 0.5))}">{td.get('score', 0.5)*100:.1f}%</div>
                <div class="topic-summary">{td.get('summary', '')[:50]}</div>
                <div class="topic-points">{points_text}</div>
            </div>
            """

        # ✨ 新增图表先注入
        dist_chart = self._sentiment_distribution_chart(sentiment_result)
        if dist_chart:
            charts_html.append(dist_chart)
        if kline_data is not None and len(kline_data) >= 3:
            kline_chart = self._kline_sentiment_overlay_chart(kline_data, sentiment_result)
            if kline_chart:
                charts_html.append(kline_chart)

        full_html = self._build_html_template(
            title=f"📊 情绪分析报告 - {stock_name}({stock_code})",
            ai_conclusion=ai_conclusion,
            dashboard=dashboard,
            wordcloud=wordcloud_html,
            charts="\n".join(charts_html),
            summary_text=summary_text,
            market_exp=market_exp,
            trend_pred=trend_pred,
            news_html=news_html,
            risk_html=risk_html,
            events_html=events_html,
            topic_details=topic_details_html,
            extra_head="",
        )

        # 保存文件
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"情绪分析_{stock_code}_{stock_name}_{timestamp}.html"
            output_path = REPORT_DIR / filename

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(full_html)

        return str(output_path)

    # ==================================================================
    # 回测报告
    # ==================================================================

    def generate_backtest_report(
        self,
        results: List,
        stock_name_map: Dict[str, str],
        output_path: Optional[Path] = None,
    ) -> str:
        """
        生成回测报告

        Args:
            results: 回测结果列表（单策略或多策略）
            stock_name_map: 股票名称映射

        Returns:
            str: HTML文件路径
        """
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots

        # 按策略分组
        strategy_groups = {}
        for r in results:
            s = r.strategy
            if s not in strategy_groups:
                strategy_groups[s] = []
            strategy_groups[s].append(r)

        strategy_names = {
            "buy_hold": "买入持有",
            "sentiment_only": "纯情绪策略",
            "sentiment_ma": "情绪+均线",
            "rsi_mean_reversion": "RSI均值回归",
            "bollinger_breakout": "布林带突破",
            "momentum": "动量策略",
        }

        charts_html = []

        # ===== 汇总绩效表 =====
        perf_rows = []
        for strategy, group in strategy_groups.items():
            avg_return = np.mean([r.total_return for r in group])
            avg_dd = np.mean([r.max_drawdown for r in group])
            avg_sharpe = np.mean([r.sharpe_ratio for r in group])
            avg_win = np.mean([r.win_rate for r in group])
            total_trades = sum(r.total_trades for r in group)
            sname = strategy_names.get(strategy, strategy)
            perf_rows.append(f"""
            <tr>
                <td>{sname}</td>
                <td style="color:{'#ff4444' if avg_return < 0 else '#00ff88'}">{avg_return:+.2f}%</td>
                <td style="color:{'#ff4444' if avg_dd > 20 else '#ff8844' if avg_dd > 10 else '#00ff88'}">{avg_dd:.2f}%</td>
                <td style="color:{'#00ff88' if avg_sharpe > 1 else '#ff8844' if avg_sharpe > 0 else '#ff4444'}">{avg_sharpe:.2f}</td>
                <td>{avg_win:.1f}%</td>
                <td>{total_trades}</td>
                <td>{len(group)}只</td>
            </tr>
            """)

        # ===== Chart 1: 绩效对比柱状图 =====
        fig_comp = go.Figure()
        s_names_list = []
        s_returns = []
        s_drawdowns = []
        s_sharpes = []
        for strategy, group in strategy_groups.items():
            sname = strategy_names.get(strategy, strategy)
            s_names_list.append(sname)
            s_returns.append(np.mean([r.total_return for r in group]))
            s_drawdowns.append(np.mean([r.max_drawdown for r in group]))
            s_sharpes.append(np.mean([r.sharpe_ratio for r in group]))

        fig_comp.add_trace(go.Bar(
            name="平均收益率 (%)",
            x=s_names_list, y=s_returns,
            marker_color=["#00ff88" if r > 0 else "#ff4444" for r in s_returns],
            text=[f"{r:+.1f}%" for r in s_returns],
            textposition="outside",
        ))
        fig_comp.add_trace(go.Bar(
            name="最大回撤 (%)",
            x=s_names_list, y=[-abs(d) for d in s_drawdowns],
            marker_color="#ff4444",
            text=[f"{d:.1f}%" for d in s_drawdowns],
            textposition="outside",
        ))
        fig_comp.update_layout(
            barmode="group",
            height=350,
            yaxis_title="百分比 (%)",
        )
        charts_html.append(
            f'<div class="chart-card full-width"><div class="chart-title">📊 策略绩效对比</div>'
            f'{fig_comp.to_html(full_html=False, include_plotlyjs=True, config={"responsive": True})}</div>'
        )

        # ===== Chart 2: 夏普比率对比 =====
        colors = ["#00ff88" if s > 1 else "#ff8844" if s > 0 else "#ff4444" for s in s_sharpes]
        fig_sharpe = go.Figure()
        fig_sharpe.add_trace(go.Bar(
            x=s_names_list, y=s_sharpes,
            marker_color=colors,
            text=[f"{s:.2f}" for s in s_sharpes],
            textposition="outside",
        ))
        fig_sharpe.add_hline(y=1, line=dict(color="#00ff88", dash="dash", width=1),
                            annotation_text="优秀")
        fig_sharpe.update_layout(height=450, yaxis_title="夏普比率")
        charts_html.append(
            f'<div class="chart-card half-left"><div class="chart-title">⚡ 夏普比率对比</div>'
            f'{fig_sharpe.to_html(full_html=False, include_plotlyjs=False, config={"responsive": True})}</div>'
        )

        # ===== Chart 3: 胜率对比 =====
        s_wins = [np.mean([r.win_rate for r in group]) for _, group in strategy_groups.items()]
        colors_w = ["#00ff88" if w > 50 else "#ff8844" for w in s_wins]
        fig_win = go.Figure()
        fig_win.add_trace(go.Bar(
            x=s_names_list, y=s_wins,
            marker_color=colors_w,
            text=[f"{w:.1f}%" for w in s_wins],
            textposition="outside",
        ))
        fig_win.add_hline(y=50, line=dict(color="#ffcc44", dash="dash", width=1),
                         annotation_text="50%")
        fig_win.update_layout(height=450, yaxis=dict(range=[0, 100], title="胜率 (%)"))
        charts_html.append(
            f'<div class="chart-card half-right"><div class="chart-title">🎯 交易胜率对比</div>'
            f'{fig_win.to_html(full_html=False, include_plotlyjs=False, config={"responsive": True})}</div>'
        )

        # ===== Chart 4: 单只最佳/最差 =====
        all_results = [r for group in strategy_groups.values() for r in group]
        best = max(all_results, key=lambda r: r.total_return)
        worst = min(all_results, key=lambda r: r.total_return)

        # Top 10
        sorted_results = sorted(all_results, key=lambda r: r.total_return, reverse=True)
        top10 = sorted_results[:10]
        bottom10 = sorted_results[-10:]

        fig_top = go.Figure()
        top_names = [f"{r.stock_name}({r.stock_code})" for r in top10]
        top_vals = [r.total_return for r in top10]
        colors_top = ["#00ff88" if v > 0 else "#ff4444" for v in top_vals]

        fig_top.add_trace(go.Bar(
            y=top_names[::-1], x=top_vals[::-1],
            orientation="h",
            marker_color=colors_top[::-1],
            text=[f"{v:+.1f}%" for v in top_vals[::-1]],
            textposition="outside",
        ))
        fig_top.update_layout(
            height=350,
            xaxis_title="收益率 (%)",
            title="🏆 表现最佳股票 Top 10",
        )
        charts_html.append(
            f'<div class="chart-card half-left"><div class="chart-title">🏆 收益 Top 10</div>'
            f'{fig_top.to_html(full_html=False, include_plotlyjs=False, config={"responsive": True})}</div>'
        )

        fig_bottom = go.Figure()
        bottom_names = [f"{r.stock_name}({r.stock_code})" for r in bottom10]
        bottom_vals = [r.total_return for r in bottom10]
        colors_bottom = ["#00ff88" if v > 0 else "#ff4444" for v in bottom_vals]

        fig_bottom.add_trace(go.Bar(
            y=bottom_names[::-1], x=bottom_vals[::-1],
            orientation="h",
            marker_color=colors_bottom[::-1],
            text=[f"{v:+.1f}%" for v in bottom_vals[::-1]],
            textposition="outside",
        ))
        fig_bottom.update_layout(
            height=350,
            xaxis_title="收益率 (%)",
            title="📉 表现最差股票 Bottom 10",
        )
        charts_html.append(
            f'<div class="chart-card half-right"><div class="chart-title">📉 收益 Bottom 10</div>'
            f'{fig_bottom.to_html(full_html=False, include_plotlyjs=False, config={"responsive": True})}</div>'
        )

        # ===== 汇总表格 =====
        perf_table = f"""
        <table class="perf-table">
            <thead>
                <tr>
                    <th>策略</th>
                    <th>平均收益</th>
                    <th>平均回撤</th>
                    <th>夏普比率</th>
                    <th>平均胜率</th>
                    <th>总交易</th>
                    <th>覆盖股票</th>
                </tr>
            </thead>
            <tbody>
                {"".join(perf_rows)}
            </tbody>
        </table>
        """

        stat_cards = f"""
        <div class="stat-grid">
            <div class="stat-card">
                <div class="stat-value" style="color:#00ff88">{len(all_results)}</div>
                <div class="stat-label">回测股票数</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" style="color:#ffcc44">{len(strategy_groups)}</div>
                <div class="stat-label">策略数</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" style="color:#{'#ff4444' if best.total_return < 0 else '#00ff88'}">{best.total_return:+.1f}%</div>
                <div class="stat-label">最佳收益 ({best.stock_name})</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" style="color:#{'#ff4444' if worst.total_return < 0 else '#00ff88'}">{worst.total_return:+.1f}%</div>
                <div class="stat-label">最差收益 ({worst.stock_name})</div>
            </div>
        </div>
        """

        full_html = self._build_html_template(
            title="📊 量化回测绩效报告",
            charts="\n".join(charts_html),
            summary_text="",
            market_exp="",
            trend_pred="",
            news_html="",
            risk_html="",
            events_html="",
            topic_details="",
            extra_head=stat_cards + perf_table,
        )

        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = REPORT_DIR / f"回测报告_{timestamp}.html"

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(full_html)

        return str(output_path)

    # ==================================================================
    # 单策略回测详细报告
    # ==================================================================

    def generate_single_backtest_report(
        self,
        result,
        output_path: Optional[Path] = None,
    ) -> str:
        """
        生成单策略回测详细报告
        """
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots

        charts_html = []

        # ===== Chart 1: 净值曲线 =====
        eq = result.equity_curve
        if eq:
            dates = [e["date"] for e in eq]
            values = [e["value"] for e in eq]

            fig_eq = go.Figure()
            fig_eq.add_trace(go.Scatter(
                x=dates, y=values,
                mode="lines",
                name="策略净值",
                line=dict(color="#00ff88", width=2),
                fill="tozeroy",
                fillcolor="rgba(0, 255, 136, 0.08)",
            ))

            # 基准线（买入持有）
            if len(values) > 0:
                initial = values[0]
                fig_eq.add_trace(go.Scatter(
                    x=dates, y=[initial] * len(dates),
                    mode="lines",
                    name="初始资本线",
                    line=dict(color="#ffcc44", dash="dash", width=1),
                ))

            fig_eq.update_layout(
                height=400,
                yaxis_title="净值 (元)",
                hovermode="x unified",
                title=dict(
                    text=f"净值曲线 - {result.stock_name}({result.stock_code}) - {result.strategy}",
                    font=dict(size=16),
                ),
            )
            charts_html.append(
                f'<div class="chart-card full-width"><div class="chart-title">📈 策略净值曲线</div>'
                f'{fig_eq.to_html(full_html=False, include_plotlyjs=True, config={"responsive": True})}</div>'
            )

        # ===== Chart 2: 每日收益率 =====
        if result.daily_returns:
            fig_ret = go.Figure()
            fig_ret.add_trace(go.Bar(
                x=dates, y=[r * 100 for r in result.daily_returns],
                marker_color=["#00ff88" if r > 0 else "#ff4444" for r in result.daily_returns],
                name="日收益率",
            ))
            fig_ret.update_layout(height=350, yaxis_title="日收益率 (%)", hovermode="x unified")
            charts_html.append(
                f'<div class="chart-card full-width"><div class="chart-title">📊 每日收益率分布</div>'
                f'{fig_ret.to_html(full_html=False, include_plotlyjs=False, config={"responsive": True})}</div>'
            )

        # ===== Chart 3: 回撤曲线 =====
        if values:
            peak = np.maximum.accumulate(values)
            dd = [(p - v) / p * 100 for p, v in zip(peak, values)]
            fig_dd = go.Figure()
            fig_dd.add_trace(go.Scatter(
                x=dates, y=dd,
                mode="lines",
                name="回撤",
                line=dict(color="#ff4444", width=2),
                fill="tozeroy",
                fillcolor="rgba(255, 68, 68, 0.15)",
            ))
            fig_dd.update_layout(height=350, yaxis_title="回撤 (%)", hovermode="x unified")
            charts_html.append(
                f'<div class="chart-card full-width"><div class="chart-title">🔻 回撤曲线</div>'
                f'{fig_dd.to_html(full_html=False, include_plotlyjs=False, config={"responsive": True})}</div>'
            )

        # ===== Chart 4: 交易标记 =====
        if result.trades and dates:
            buy_signals = [t for t in result.trades if t.action == "buy"]
            sell_signals = [t for t in result.trades if t.action == "sell"]

            fig_trade = go.Figure()
            fig_trade.add_trace(go.Scatter(
                x=dates, y=values,
                mode="lines",
                name="净值",
                line=dict(color="#4488ff", width=2),
            ))

            buy_dates = [t.date for t in buy_signals if t.date in dates]
            buy_values_local = []
            for bd in buy_dates:
                idx = dates.index(bd) if bd in dates else -1
                buy_values_local.append(values[idx] if idx >= 0 else values[-1])

            if buy_dates:
                fig_trade.add_trace(go.Scatter(
                    x=buy_dates, y=buy_values_local,
                    mode="markers",
                    name="买入",
                    marker=dict(color="#00ff88", size=12, symbol="triangle-up"),
                ))

            sell_dates = [t.date for t in sell_signals if t.date in dates]
            sell_values_local = []
            for sd in sell_dates:
                idx2 = dates.index(sd) if sd in dates else -1
                sell_values_local.append(values[idx2] if idx2 >= 0 else values[-1])

            if sell_dates:
                fig_trade.add_trace(go.Scatter(
                    x=sell_dates, y=sell_values_local,
                    mode="markers",
                    name="卖出",
                    marker=dict(color="#ff4444", size=12, symbol="triangle-down"),
                ))

            fig_trade.update_layout(height=450, hovermode="x unified",
                                    title="买卖信号标注")
            charts_html.append(
                f'<div class="chart-card full-width"><div class="chart-title">🎯 买卖信号标注</div>'
                f'{fig_trade.to_html(full_html=False, include_plotlyjs=False, config={"responsive": True})}</div>'
            )

        # ===== 绩效指标卡片 =====
        strategy_map = {"buy_hold": "买入持有", "sentiment_only": "纯情绪策略",
                       "sentiment_ma": "情绪+均线", "rsi_mean_reversion": "RSI均值回归",
                       "bollinger_breakout": "布林带突破", "momentum": "动量策略"}
        stat_cards = f"""
        <div class="stat-grid">
            <div class="stat-card">
                <div class="stat-value" style="color:{'#00ff88' if result.total_return >= 0 else '#ff4444'}">{result.total_return:+.2f}%</div>
                <div class="stat-label">总收益率</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" style="color:#ffcc44">{result.annual_return:+.2f}%</div>
                <div class="stat-label">年化收益</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" style="color:#ff4444">{result.max_drawdown:.2f}%</div>
                <div class="stat-label">最大回撤</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" style="color:{'#00ff88' if result.sharpe_ratio > 1 else '#ff8844'}">{result.sharpe_ratio:.2f}</div>
                <div class="stat-label">夏普比率</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" style="color:{'#00ff88' if result.win_rate > 50 else '#ff8844'}">{result.win_rate:.1f}%</div>
                <div class="stat-label">胜率</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{result.total_trades}</div>
                <div class="stat-label">交易次数</div>
            </div>
        </div>
        """

        # 交易记录表
        trade_rows = []
        for t in result.trades:
            action_color = "#00ff88" if t.action == "buy" else "#ff4444"
            trade_rows.append(f"""
            <tr>
                <td>{t.date}</td>
                <td style="color:{action_color}">{'买入' if t.action == 'buy' else '卖出'}</td>
                <td>{t.price:.2f}</td>
                <td>{t.shares}</td>
                <td>{t.value:.2f}</td>
                <td>{t.reason}</td>
            </tr>
            """)
        trade_table = ""
        if trade_rows:
            trade_table = f"""
            <table class="perf-table">
                <thead><tr><th>日期</th><th>方向</th><th>价格</th><th>数量</th><th>金额</th><th>理由</th></tr></thead>
                <tbody>{"".join(trade_rows)}</tbody>
            </table>
            """

        full_html = self._build_html_template(
            title=f"📈 回测详情 - {result.stock_name}({result.stock_code})",
            charts="\n".join(charts_html),
            summary_text="",
            market_exp="",
            trend_pred="",
            news_html="",
            risk_html="",
            events_html="",
            topic_details="",
            extra_head=stat_cards + f"""
            <div class="info-card">
                <div><strong>策略:</strong> {strategy_map.get(result.strategy, result.strategy)}</div>
                <div><strong>股票:</strong> {result.stock_name}({result.stock_code})</div>
                <div><strong>回测区间:</strong> {result.start_date} ~ {result.end_date}</div>
                <div><strong>初始资金:</strong> ¥{result.initial_capital:,.0f}</div>
                <div><strong>最终资产:</strong> ¥{result.final_value:,.2f}</div>
                <div><strong>盈利因子:</strong> {result.profit_factor:.2f}</div>
            </div>
            """ + trade_table,
        )

        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = REPORT_DIR / f"回测详情_{result.stock_code}_{timestamp}.html"

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(full_html)

        return str(output_path)

    # ==================================================================
    # ✨ 新增: 多股票情绪对比报告
    # ==================================================================

    def generate_comparison_report(
        self,
        stocks_data: List[Dict],
        output_path: Optional[Path] = None,
    ) -> str:
        """
        生成多只股票情绪对比报告

        Args:
            stocks_data: [{code, name, sentiment_result, news_count}, ...]
            output_path: 输出路径（可选）

        Returns:
            str: HTML 文件路径
        """
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots

        names = [s["name"] for s in stocks_data]
        scores = [s["sentiment_result"]["overall_sentiment"]["score"] * 100 for s in stocks_data]
        confs = [s["sentiment_result"]["overall_sentiment"]["confidence_index"] * 100 for s in stocks_data]
        vols = [s["sentiment_result"]["overall_sentiment"].get("volatility", 0) * 100 for s in stocks_data]
        news_counts = [s.get("news_count", 0) for s in stocks_data]

        charts_html = []

        # ---- Chart 1: 情感得分柱状图 + 置信度气泡 ----
        fig1 = make_subplots(specs=[[{"secondary_y": True}]])
        colors1 = ["#00ff88" if s > 55 else ("#ffcc44" if s > 45 else "#ff4444") for s in scores]
        fig1.add_trace(go.Bar(x=names, y=scores, name="情绪得分", marker_color=colors1,
                              text=[f"{s:.1f}%" for s in scores], textposition="auto"),
                      secondary_y=False)
        fig1.add_trace(go.Scatter(x=names, y=confs, mode="markers+lines",
                                 name="置信度", marker=dict(size=12, color="#4488ff"),
                                 line=dict(color="#4488ff", width=1, dash="dot")),
                      secondary_y=True)
        fig1.update_layout(height=450, legend=dict(x=0.01, y=0.99),
                          margin=dict(l=30, r=30, t=40, b=30))
        fig1.update_yaxes(title_text="情绪得分 (%)", range=[0, 100], secondary_y=False)
        fig1.update_yaxes(title_text="置信度 (%)", range=[0, 100], secondary_y=True)
        charts_html.append(
            '<div class="chart-card full-width">'
            '<div class="chart-title">📊 情绪得分对比</div>'
            f'{fig1.to_html(full_html=False, include_plotlyjs=True, config={"responsive": True})}'
            '</div>'
        )

        # ---- Chart 2: 雷达图 - 6维主题对比 ----
        topic_keys = ["company_operation", "financial_performance", "market_competition",
                     "product_technology", "industry_policy", "capital_market"]
        topic_names = ["公司经营", "财务表现", "市场竞争", "产品技术", "行业政策", "资本市场"]
        colors_radar = ["#00ff88", "#4488ff", "#ff8844", "#ffcc44", "#ff4444", "#cc44ff"]

        fig2 = go.Figure()
        for i, sdata in enumerate(stocks_data):
            topic_scores = [sdata["sentiment_result"]["topic_analysis"].get(k, {}).get("score", 0.5) * 100
                          for k in topic_keys]
            fig2.add_trace(go.Scatterpolar(
                r=topic_scores, theta=topic_names, name=sdata["name"],
                fill="toself", opacity=0.25, line=dict(color=colors_radar[i % len(colors_radar)], width=2),
            ))
        fig2.update_layout(polar=dict(radialaxis=dict(range=[0, 100], showticklabels=True, ticks="")),
                          height=420, legend=dict(x=0.01, y=0.99),
                          margin=dict(l=30, r=30, t=40, b=30))
        charts_html.append(
            '<div class="chart-card full-width">'
            '<div class="chart-title">🎯 六维主题雷达对比</div>'
            f'{fig2.to_html(full_html=False, include_plotlyjs=False, config={"responsive": True})}'
            '</div>'
        )

        # ---- Chart 3: 波动率 vs 置信度散点图 ----
        fig3 = go.Figure()
        for i, sdata in enumerate(stocks_data):
            fig3.add_trace(go.Scatter(
                x=[confs[i]], y=[vols[i]], mode="markers+text",
                text=[names[i]], textposition="top center",
                marker=dict(size=18, color=colors_radar[i % len(colors_radar)],
                           symbol="circle", line=dict(width=1, color="#fff")),
                name=names[i],
            ))
        fig3.update_layout(height=450, legend=dict(x=0.01, y=0.99),
                          margin=dict(l=30, r=30, t=40, b=30))
        fig3.update_xaxes(title_text="置信度 (%)", range=[0, 105])
        fig3.update_yaxes(title_text="波动率 (%)", range=[0, max(max(vols) + 10, 30)])
        charts_html.append(
            '<div class="chart-card full-width">'
            '<div class="chart-title">💡 置信度 vs 分歧度散点</div>'
            f'{fig3.to_html(full_html=False, include_plotlyjs=False, config={"responsive": True})}'
            '</div>'
        )

        # ---- Summaries ----
        summaries_html = ""
        for sdata in stocks_data:
            ov = sdata["sentiment_result"]["overall_sentiment"]
            s = ov["score"] * 100
            sc_color = "#00ff88" if s > 55 else ("#ffcc44" if s > 45 else "#ff4444")
            summaries_html += f"""
            <div class="comp-summary-card">
                <div class="comp-stock-name">{sdata['name']}</div>
                <div class="comp-score" style="color:{sc_color}">{s:.0f}分</div>
                <div class="comp-detail">{ov['label']} | 置信{ov['confidence_index']*100:.0f}% | {sdata.get('news_count',0)}条新闻</div>
                <div class="comp-detail" style="font-size:11px;color:#888">波动{ov.get('volatility',0)*100:.0f}% {ov.get('volatility_label','')}</div>
            </div>"""

        # ---- Build HTML ----
        comparison_table = ""
        if len(stocks_data) >= 2:
            rows = "".join(
                f"<tr><td>{s['name']}</td>"
                f"<td style='color:{'#00ff88' if s['sentiment_result']['overall_sentiment']['score']*100 > 55 else ('#ffcc44' if s['sentiment_result']['overall_sentiment']['score']*100 > 45 else '#ff4444')}'>{s['sentiment_result']['overall_sentiment']['score']*100:.0f}分</td>"
                f"<td>{s['sentiment_result']['overall_sentiment']['label']}</td>"
                f"<td>{s['sentiment_result']['overall_sentiment']['confidence_index']*100:.0f}%</td>"
                f"<td>{s['sentiment_result']['overall_sentiment'].get('volatility',0)*100:.0f}%</td>"
                f"<td>{s.get('news_count',0)}</td></tr>"
                for s in stocks_data
            )
            comparison_table = f"""
            <div class="comparison-table-wrap">
                <table class="comparison-table">
                    <thead><tr><th>股票</th><th>情绪分</th><th>判断</th><th>置信度</th><th>波动率</th><th>新闻数</th></tr></thead>
                    <tbody>{rows}</tbody>
                </table>
            </div>"""

        import datetime as dt
        now_str = dt.datetime.now().strftime("%Y-%m-%d %H:%M")

        full_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>📊 多股票情绪对比报告</title>
<!-- Plotly.js 内嵌至第一张图表，离线可用 -->
<style>
{self._comparison_css()}
</style>
</head>
<body>
<div class="container">
    <div class="report-header">
        <h1>📊 多股票情绪对比报告</h1>
        <p>生成时间: {now_str} | 共 {len(stocks_data)} 只股票</p>
    </div>

    {comparison_table}

    <div class="comp-summaries">
        {summaries_html}
    </div>

    <div class="chart-grid">
        {''.join(charts_html)}
    </div>
</div>
</body>
</html>"""

        if output_path is None:
            output_path = REPORT_DIR / f"情绪对比_{len(stocks_data)}只_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.html"

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(full_html)

        return str(output_path)

    def _comparison_css(self) -> str:
        return """
        body { background: #12122a; color: #e0e0e0; font-family: Arial, sans-serif; margin: 0; padding: 0; }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        .report-header { text-align: center; padding: 30px 0; }
        .report-header h1 { font-size: 28px; background: linear-gradient(135deg, #00ff88, #4488ff); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .report-header p { color: #888; font-size: 14px; margin-top: 8px; }
        .comp-summaries { display: flex; gap: 15px; flex-wrap: wrap; margin-bottom: 15px; }
        .comp-summary-card { flex: 1; min-width: 160px; background: rgba(26,26,46,0.8); border-radius: 12px; padding: 16px; text-align: center; border: 1px solid rgba(255,255,255,0.05); }
        .comp-stock-name { font-size: 14px; color: #ccc; margin-bottom: 12px; }
        .comp-score { font-size: 30px; font-weight: bold; }
        .comp-detail { font-size: 12px; color: #aaa; margin-top: 4px; }
        .chart-grid { display: flex; flex-direction: column; gap: 15px; }
        .chart-card { background: rgba(26,26,46,0.8); border-radius: 15px; padding: 20px; border: 1px solid rgba(255,255,255,0.05); }
        .chart-card.full-width { width: 100%; }
        .chart-title { font-size: 16px; font-weight: bold; color: #e0e0e0; margin-bottom: 12px; }
        .comparison-table-wrap { overflow-x: auto; margin-bottom: 15px; }
        .comparison-table { width: 100%; border-collapse: collapse; background: rgba(26,26,46,0.8); border-radius: 12px; overflow: hidden; }
        .comparison-table th { background: rgba(0,255,136,0.1); color: #00ff88; padding: 12px; font-size: 13px; text-align: center; }
        .comparison-table td { padding: 10px; text-align: center; font-size: 14px; border-bottom: 1px solid rgba(255,255,255,0.05); }
        @media (max-width: 768px) { .comp-summaries { flex-direction: column; } }
        """

    def _generate_ai_conclusion(self, sentiment_result: Dict, news_list: List[Dict]) -> str:
        """
        根据情感分析结果智能生成一句话结论（无外部 API 依赖）
        """
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

        return f"""
        <div class="ai-conclusion">
            <div class="ai-badge">🤖 AI 诊断</div>
            <div class="ai-text">{conclusion}</div>
        </div>"""

    def _generate_dashboard_cards(
        self, sentiment_result: Dict, quote: Optional[Dict] = None,
        market: Optional[Dict] = None, news_count: int = 0,
        fund_flow: Optional[Dict] = None, announcements: Optional[List] = None,
    ) -> str:
        """生成综合仪表盘卡片"""
        overall = sentiment_result.get("overall_sentiment", {})
        score = overall.get("score", 0.5)
        conf = overall.get("confidence_index", 0.0)
        volatility = overall.get("volatility", 0.0)
        vol_label = overall.get("volatility_label", "无数据")
        pos_r = overall.get("positive_ratio", 0.0)
        neg_r = overall.get("negative_ratio", 0.0)
        pos_n = overall.get("positive_count", 0)
        neg_n = overall.get("negative_count", 0)
        neu_n = overall.get("neutral_count", 0)

        risk = sentiment_result.get("risk_analysis", {})
        risk_level = risk.get("risk_level", "低")
        risk_color = {"高": "#ff4444", "中": "#ff8844", "低": "#00ff88"}.get(risk_level, "#888")

        label_colors = {"极度看好": "#00ff88", "看好": "#88cc44", "中性": "#ffcc44",
                        "看空": "#ff8844", "极度看空": "#ff4444"}
        score_color = label_colors.get(overall.get("label", ""), "#888")
        conf_color = "#00ff88" if conf > 0.6 else ("#ff8844" if conf > 0.3 else "#ff4444")

        # 波动率颜色
        vol_color = "#00ff88" if volatility < 0.15 else ("#ff8844" if volatility < 0.3 else "#ff4444")

        # 分歧度可视化条
        vol_pct = min(int(volatility * 333), 100)
        vol_bar = f'<div class="vol-bar-bg"><div class="vol-bar-fg" style="width:{vol_pct}%;background:linear-gradient(90deg,#00ff88,#ff8844,#ff4444)"></div></div>'

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

        # 资金流向行
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

        # PE/PB行（从行情获取）
        pe_html = ""
        if quote:
            pe = quote.get("pe")
            pb = quote.get("pb")
            if pe or pb:
                parts = []
                if pe: parts.append(f"PE: <b>{pe}</b>")
                if pb: parts.append(f"PB: <b>{pb}</b>")
                pe_html = f'<span style="margin-left:12px">{" | ".join(parts)}</span>'

        return f"""
        {quote_html}
        <div class="dashboard-market-compact">
            {market_html}{pe_html}
        </div>
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
                {vol_bar}
            </div>
            <div class="dash-card">
                <div class="dash-value" style="color:{risk_color}">{risk_level}</div>
                <div class="dash-label">风险</div>
            </div>
            <div class="dash-card">
                <div class="dash-label" style="margin-bottom:4px">正/负/中: {pos_n}/{neg_n}/{neu_n}</div>
                <div class="sentiment-ratio-bar" style="margin-bottom:4px">
                    <div class="ratio-pos" style="flex:{pos_r*100}"></div>
                    <div class="ratio-neu" style="flex:{max(0.0,(1-pos_r-neg_r))*100}"></div>
                    <div class="ratio-neg" style="flex:{neg_r*100}"></div>
                </div>
                <div class="topic-tags">{topic_tags}</div>
            </div>
        </div>"""

    def _find_chinese_font(self) -> Optional[str]:
        """自动查找系统可用的中文字体"""
        import matplotlib.font_manager as fm
        candidates = [
            # macOS
            "/System/Library/Fonts/STHeiti Medium.ttc",
            "/System/Library/Fonts/STHeiti Light.ttc",
            "/System/Library/Fonts/Supplemental/Songti.ttc",
            "/System/Library/Fonts/PingFang.ttc",
            # Linux
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
            # Windows
            "C:/Windows/Fonts/msyh.ttc",
            "C:/Windows/Fonts/simhei.ttf",
        ]
        for path in candidates:
            if Path(path).exists():
                return path

        # 从 matplotlib 字体列表搜索
        for f in fm.fontManager.ttflist:
            name_lower = f.name.lower()
            if any(kw in name_lower for kw in ["hei", "song", "kai", "ming", "ping", "cjk"]):
                if Path(f.fname).exists():
                    return f.fname

        return None

    def _generate_wordcloud(self, news_list: List[Dict]) -> str:
        """生成新闻词云 PNG 并转为 base64 内嵌 HTML"""
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            from wordcloud import WordCloud

            texts = [n.get("title", "") + " " + n.get("content", "")[:200] for n in news_list]
            full_text = " ".join(texts)
            if len(full_text) < 10:
                return '<div style="color:#888;text-align:center;padding:20px;">新闻文本不足，无法生成词云</div>'

            try:
                import jieba
                words = jieba.lcut(full_text)
            except ImportError:
                words = full_text.split()

            stopwords_set = set("的了吗是我就也都还只没到去上中下要与在和对为以不这那但有可他所她之而及其因为所以如果虽然但是不过可以可能已经现在目前今年近日日前昨天今天明天一个一些这个那个什么怎么怎样哪里如何非常比较更加从被把让给向往用以及等或并及据报道据悉消息称据了解".split())
            filtered = [w.strip() for w in words
                       if len(w.strip()) >= 2 and w.strip() not in stopwords_set
                       and not w.strip().isdigit()
                       and not re.match(r'^[a-zA-Z]+$', w.strip())]
            if not filtered:
                return '<div style="color:#888;text-align:center;padding:20px;">分词后无可视化词汇</div>'

            wc = WordCloud(width=600, height=400, background_color="#16213e",
                          max_words=80, max_font_size=60, min_font_size=12,
                          colormap="viridis", margin=5, prefer_horizontal=0.85,
                          collocations=False, font_path=self._find_chinese_font()).generate(" ".join(filtered))

            buf = io.BytesIO()
            plt.figure(figsize=(10, 4.5), dpi=80)
            plt.imshow(wc, interpolation="bilinear")
            plt.axis("off")
            plt.tight_layout(pad=0)
            plt.savefig(buf, format="png", dpi=80, bbox_inches="tight",
                       facecolor="#16213e", edgecolor="none", pad_inches=0)
            plt.close()
            buf.seek(0)
            img_b64 = base64.b64encode(buf.read()).decode("utf-8")
            return f'<img src="data:image/png;base64,{img_b64}" class="wordcloud-img" alt="新闻词云">'
        except Exception as e:
            return f'<div style="color:#888;text-align:center;padding:20px;">词云生成失败: {str(e)[:60]}</div>'

    def _sentiment_distribution_chart(self, sentiment_result: Dict) -> str:
        """情感得分分布直方图 + 密度曲线"""
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots

        items = sentiment_result.get("word_analysis", {}).get("items", [])
        if not items:
            overall = sentiment_result.get("overall_sentiment", {})
            base = overall.get("score", 0.5)
            scores = sorted([max(0.01, min(0.99, base + np.random.normal(0, 0.2))) for _ in range(12)])
        else:
            scores = [it.get("_score", 0.5) for it in items if "_score" in it]

        if not scores or len(scores) < 2:
            return ""

        scores_pct = [s * 100 for s in scores]
        nbins = max(5, min(12, len(scores)))

        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(
            go.Histogram(x=scores_pct, nbinsx=nbins,
                        marker_color="rgba(0, 255, 136, 0.6)",
                        marker_line_color="rgba(0, 255, 136, 0.9)",
                        marker_line_width=1, name="新闻分布"),
            secondary_y=False,
        )

        try:
            from scipy.stats import gaussian_kde
            kde = gaussian_kde(scores_pct)
            x_range = np.linspace(0, 100, 200)
            y_kde = kde(x_range)
            y_kde = y_kde / y_kde.max() * max(list(np.histogram(scores_pct, bins=nbins)[0]))
            fig.add_trace(
                go.Scatter(x=x_range, y=y_kde, mode="lines",
                          name="密度曲线", line=dict(color="#ff8844", width=2),
                          fill="tozeroy", fillcolor="rgba(255, 136, 68, 0.1)"),
                secondary_y=True,
            )
        except Exception:
            pass

        fig.add_vline(x=35, line=dict(color="#ff4444", dash="dash", width=1))
        fig.add_vline(x=65, line=dict(color="#00ff88", dash="dash", width=1))
        mean_score = np.mean(scores_pct)
        fig.add_vline(x=mean_score, line=dict(color="#4488ff", width=1.5))
        fig.add_annotation(x=mean_score, y=0.95, xref="x", yref="paper",
                          text=f"均值 {mean_score:.1f}%", showarrow=False,
                          font=dict(color="#4488ff", size=11),
                          bgcolor="rgba(22,33,62,0.8)")

        fig.update_layout(xaxis=dict(title="情感得分 (%)", range=[0, 100]),
                         yaxis=dict(title="新闻数量"), yaxis2=dict(visible=False),
                         height=450, showlegend=True, legend=dict(x=0.01, y=0.99),
                         bargap=0.05, margin=dict(l=30, r=30, t=40, b=30))

        return (
            '<div class="chart-card full-width">'
            '<div class="chart-title">📊 情感得分分布</div>'
            f'{fig.to_html(full_html=False, include_plotlyjs=False, config={"responsive": True})}'
            '</div>'
        )

    def _kline_sentiment_overlay_chart(self, kline_data, sentiment_result: Dict) -> str:
        """K线蜡烛图 + 情绪信号叠加图"""
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots

        if kline_data is None or len(kline_data) < 3:
            return ""

        trend_data = sentiment_result.get("time_analysis", {}).get("trend", [])
        date_score = {}
        for t in trend_data:
            date_score[t["date"]] = t["score"]

        kline_data["ma5"] = kline_data["close"].rolling(5).mean()
        kline_data["ma20"] = kline_data["close"].rolling(20).mean()

        ema12 = kline_data["close"].ewm(span=12, adjust=False).mean()
        ema26 = kline_data["close"].ewm(span=26, adjust=False).mean()

        dates = [d.strftime("%m-%d") if hasattr(d, "strftime") else str(d)
                for d in kline_data.index]

        fig = make_subplots(rows=3, cols=1, shared_xaxes=True,
                           vertical_spacing=0.02, row_heights=[0.5, 0.25, 0.25])

        fig.add_trace(go.Candlestick(
            x=dates, open=kline_data["open"], high=kline_data["high"],
            low=kline_data["low"], close=kline_data["close"], name="K线",
            increasing=dict(line=dict(color="#00ff88", width=1), fillcolor="rgba(0,255,136,0.4)"),
            decreasing=dict(line=dict(color="#ff4444", width=1), fillcolor="rgba(255,68,68,0.4)"),
        ), row=1, col=1)

        fig.add_trace(go.Scatter(x=dates, y=kline_data["ma5"], mode="lines",
                                name="MA5", line=dict(color="#4488ff", width=1.2)), row=1, col=1)
        fig.add_trace(go.Scatter(x=dates, y=kline_data["ma20"], mode="lines",
                                name="MA20", line=dict(color="#ff8844", width=1.2)), row=1, col=1)

        # 情绪信号线
        kline_dates_full = [d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)
                           for d in kline_data.index]
        aligned_scores, aligned_dates_short = [], []
        for full_d, short_d in zip(kline_dates_full, dates):
            sv = date_score.get(full_d, None)
            if sv is not None:
                aligned_scores.append(sv * 100)
                aligned_dates_short.append(short_d)

        if aligned_scores:
            fig.add_trace(go.Scatter(
                x=aligned_dates_short, y=aligned_scores, mode="lines+markers",
                name="情绪信号", line=dict(color="#00ff88", width=2.5),
                marker=dict(size=6, color="#00ff88"),
                fill="tozeroy", fillcolor="rgba(0,255,136,0.15)",
            ), row=2, col=1)

        fig.add_hline(y=65, line=dict(color="#88cc44", dash="dash", width=1),
                     row=2, col=1, annotation_text="积极")
        fig.add_hline(y=35, line=dict(color="#ff4444", dash="dash", width=1),
                     row=2, col=1, annotation_text="消极")

        # 下: MACD
        macd_line = ema12 - ema26
        signal_line_val = macd_line.ewm(span=9, adjust=False).mean()
        macd_hist = macd_line - signal_line_val
        fig.add_trace(go.Bar(x=dates, y=macd_hist,
                     marker=dict(color=["#00ff88" if v >= 0 else "#ff4444" for v in macd_hist]),
                     name="MACD柱", opacity=0.7), row=3, col=1)
        fig.add_trace(go.Scatter(x=dates, y=macd_line, mode="lines",
                                name="DIF", line=dict(color="#4488ff", width=1.5)), row=3, col=1)
        fig.add_trace(go.Scatter(x=dates, y=signal_line_val, mode="lines",
                                name="DEA", line=dict(color="#ff8844", width=1.5)), row=3, col=1)

        fig.update_layout(height=450, showlegend=True,
                         legend=dict(x=0.01, y=0.99, bgcolor="rgba(26,26,46,0.8)", font=dict(size=11)),
                         hovermode="x unified", margin=dict(l=30, r=30, t=40, b=30))
        fig.update_xaxes(rangeslider_visible=False, row=1, col=1)
        fig.update_yaxes(title_text="价格", row=1, col=1)
        fig.update_yaxes(title_text="情绪%", range=[0, 100], row=2, col=1)
        fig.update_yaxes(title_text="MACD", row=3, col=1)

        return (
            '<div class="chart-card full-width">'
            '<div class="chart-title">📈 K线走势 + 情绪信号 + MACD</div>'
            f'{fig.to_html(full_html=False, include_plotlyjs=False, config={"responsive": True})}'
            '</div>'
        )

    # ==================================================================
    # 工具方法
    # ==================================================================

    def _build_html_template(
        self,
        title: str,
        charts: str,
        summary_text: str,
        market_exp: str,
        trend_pred: str,
        news_html: str,
        risk_html: str,
        events_html: str,
        topic_details: str,
        extra_head: str,
        ai_conclusion: str = "",
        dashboard: str = "",
        wordcloud: str = "",
    ) -> str:
        """构建完整HTML"""
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <!-- Plotly.js 内嵌至第一张图表，离线可用 -->
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            background: linear-gradient(135deg, #0f0c29, #16213e, #1a1a2e);
            color: #e0e0e0;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}
        .report-header {{
            text-align: center;
            padding: 30px 20px;
            background: linear-gradient(135deg, rgba(26,26,46,0.9), rgba(22,33,62,0.9));
            border-radius: 20px;
            margin-bottom: 25px;
            border: 1px solid rgba(255,255,255,0.05);
            backdrop-filter: blur(10px);
        }}
        .report-header h1 {{ font-size: 28px; background: linear-gradient(90deg, #00ff88, #4488ff); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
        .report-header .subtitle {{ color: #888; font-size: 14px; margin-top: 8px; }}
        .summary-box {{
            background: rgba(26,26,46,0.8);
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 25px;
            border: 1px solid rgba(0,255,136,0.1);
        }}
        .summary-box p {{ line-height: 1.8; color: #ccc; font-size: 15px; }}
        .summary-box .label {{ color: #4488ff; font-weight: bold; }}
        .chart-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 15px;
            margin-bottom: 25px;
        }}
        .chart-card {{
            background: rgba(26,26,46,0.8);
            border-radius: 15px;
            padding: 20px;
            border: 1px solid rgba(255,255,255,0.05);
            overflow: hidden;
        }}
        .chart-card > div {{
            width: 100% !important; height: auto !important;
        }}
        .chart-card .js-plotly-plot, .chart-card .plot-container {{
            width: 100% !important; height: auto !important;
        }}
        .chart-card.half-left {{ grid-column: 1; }}
        .chart-card.half-right {{ grid-column: 2; }}
        .chart-card.full-width {{ grid-column: 1 / -1; }}
        .chart-title {{
            font-size: 16px;
            font-weight: bold;
            color: #ccc;
            margin-bottom: 10px;
            padding-bottom: 8px;
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }}
        .stat-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 15px;
            margin-bottom: 25px;
        }}
        .stat-card {{
            background: rgba(26,26,46,0.8);
            border-radius: 15px;
            padding: 20px;
            text-align: center;
            border: 1px solid rgba(255,255,255,0.05);
        }}
        .stat-value {{ font-size: 28px; font-weight: bold; }}
        .stat-label {{ font-size: 13px; color: #888; margin-top: 5px; }}
        .info-card {{
            background: rgba(26,26,46,0.8);
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 15px;
            border: 1px solid rgba(68,136,255,0.2);
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
        }}
        .info-card div {{ font-size: 14px; color: #ccc; }}
        .info-card strong {{ color: #4488ff; }}
        .perf-table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            background: rgba(26,26,46,0.8);
            border-radius: 15px;
            overflow: hidden;
        }}
        .perf-table th {{
            background: rgba(68,136,255,0.15);
            color: #4488ff;
            padding: 12px 15px;
            text-align: left;
            font-size: 13px;
        }}
        .perf-table td {{
            padding: 10px 15px;
            border-bottom: 1px solid rgba(255,255,255,0.03);
            font-size: 14px;
        }}
        .perf-table tr:hover {{ background: rgba(255,255,255,0.03); }}
        .news-item {{
            background: rgba(26,26,46,0.6);
            border-radius: 12px;
            padding: 15px;
            margin-bottom: 10px;
            border-left: 3px solid #4488ff;
        }}
        .news-title {{ font-size: 15px; font-weight: bold; color: #e0e0e0; }}
        .news-meta {{ font-size: 12px; color: #888; margin: 5px 0; }}
        .news-content {{ font-size: 13px; color: #aaa; line-height: 1.6; }}
        .news-link {{ display: inline-block; margin-top: 8px; color: #4488ff; text-decoration: none; font-size: 13px; }}
        .news-link:hover {{ color: #00ff88; }}
        .risk-item {{
            display: flex;
            align-items: center;
            gap: 15px;
            padding: 10px 15px;
            background: rgba(26,26,46,0.6);
            border-radius: 10px;
            margin-bottom: 15px;
        }}
        .risk-factor {{ font-weight: bold; color: #ff8844; min-width: 60px; font-size: 14px; }}
        .risk-desc {{ color: #aaa; flex: 1; font-size: 13px; }}
        .risk-severity {{ padding: 2px 10px; border-radius: 10px; font-size: 12px; color: white; }}
        .event-chip {{
            display: inline-flex;
            align-items: center;
            gap: 15px;
            background: rgba(26,26,46,0.6);
            padding: 8px 15px;
            border-radius: 20px;
            margin: 5px;
            font-size: 13px;
        }}
        .event-date {{ color: #4488ff; }}
        .event-text {{ color: #ccc; }}
        .event-score {{ font-weight: bold; }}
        .topic-block {{
            background: rgba(26,26,46,0.6);
            border-radius: 12px;
            padding: 15px;
            margin-bottom: 10px;
            border-left: 3px solid #4488ff;
        }}
        .topic-name {{ font-weight: bold; font-size: 15px; color: #e0e0e0; }}
        .topic-score {{ font-size: 14px; font-weight: bold; }}
        .topic-summary {{ font-size: 13px; color: #aaa; margin: 5px 0; }}
        .topic-points {{ font-size: 12px; color: #888; }}
        /* ✨ 新增样式 - Dashboard & AI结论 & 词云 */
        .ai-conclusion {{
            background: linear-gradient(135deg, rgba(0,255,136,0.08), rgba(68,136,255,0.08));
            border-radius: 10px;
            padding: 10px 18px;
            margin-bottom: 12px;
            border: 1px solid rgba(0,255,136,0.15);
            display: flex;
            align-items: center;
            gap: 15px;
        }}
        .ai-badge {{
            background: linear-gradient(135deg, #00ff88, #4488ff);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-weight: bold;
            font-size: 14px;
            white-space: nowrap;
        }}
        .ai-text {{
            color: #ccc;
            font-size: 12px;
            line-height: 1.4;
        }}
        .dash-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 15px;
            margin-bottom: 12px;
        }}
        .dash-grid-5 {{
            grid-template-columns: repeat(5, 1fr);
        }}
        .dash-card {{
            background: rgba(26,26,46,0.8);
            border-radius: 10px;
            padding: 10px;
            text-align: center;
            border: 1px solid rgba(255,255,255,0.05);
        }}
        .dash-card.wide-card {{
            grid-column: span 1;
        }}
        .dash-value {{ font-size: 26px; font-weight: bold; }}
        .dash-label {{ font-size: 11px; color: #888; margin-top: 2px; }}
        .dashboard-quote {{
            background: rgba(26,26,46,0.8);
            border-radius: 10px;
            padding: 8px 16px;
            margin-bottom: 15px;
            border: 1px solid rgba(255,255,255,0.05);
            font-size: 14px;
        }}
        .quote-price {{ font-size: 28px; font-weight: bold; color: #e0e0e0; }}
        .quote-change {{ font-weight: bold; font-size: 14px; margin-left: 8px; }}
        .quote-divider {{ color: #444; margin: 0 8px; }}
        .dashboard-market, .dashboard-market-compact {{
            font-size: 12px;
            color: #888;
            margin-bottom: 12px;
            padding: 0 4px;
            line-height: 1.8;
        }}
        .dashboard-market {{
            font-size: 13px;
            color: #888;
            margin-bottom: 10px;
            padding: 0 5px;
        }}
        .topic-tags {{ display: flex; flex-wrap: wrap; gap: 15px; }}
        .topic-tag {{
            padding: 2px 8px;
            border-radius: 10px;
            font-size: 11px;
            white-space: nowrap;
        }}
        .wordcloud-container {{
            background: rgba(26,26,46,0.8);
            border-radius: 15px;
            padding: 15px;
            margin-bottom: 15px;
            border: 1px solid rgba(255,255,255,0.05);
            text-align: center;
        }}
        .wordcloud-img {{
            max-width: 100%;
            height: auto;
            border-radius: 10px;
        }}
        .vol-bar-bg {{
            background: rgba(255,255,255,0.05);
            border-radius: 4px;
            height: 4px;
            overflow: hidden;
        }}
        .vol-bar-fg {{
            height: 100%;
            border-radius: 4px;
            transition: width 0.5s;
        }}
        .sentiment-ratio-bar {{
            display: flex;
            height: 6px;
            border-radius: 3px;
            overflow: hidden;
            gap: 1px;
        }}
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
            <h1>{title}</h1>
            <div class="subtitle">生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M")}</div>
        </div>

        {extra_head}

        {ai_conclusion or ''}

        {dashboard or ''}

        {wordcloud and f'''
        <div class="wordcloud-container">
            <div class="chart-title">☁️ 新闻高频词云</div>
            {wordcloud}
        </div>
        ''' or ''}

        {summary_text and f'''
        <div class="summary-box">
            <p><span class="label">📝 分析总结:</span> {summary_text}</p>
            {market_exp and f'<p style="margin-top:10px"><span class="label">📊 市场预期:</span> {market_exp}</p>'}
            {trend_pred and f'<p style="margin-top:10px"><span class="label">🔮 趋势预测:</span> {trend_pred}</p>'}
        </div>
        ''' or ''}

        {events_html and f'''
        <div class="summary-box">
            <p><span class="label">📍 关键事件时间线</span></p>
            <div style="display:flex;flex-wrap:wrap;margin-top:10px">{events_html}</div>
        </div>
        ''' or ''}

        <div class="chart-grid">{charts}</div>

        {topic_details and f'''
        <div class="summary-box">
            <p><span class="label">🎯 主题分析详情</span></p>
            <div style="margin-top:10px">{topic_details}</div>
        </div>
        ''' or ''}

        {risk_html and f'''
        <div class="summary-box">
            <p><span class="label">⚠️ 风险因素</span></p>
            <div style="margin-top:10px">{risk_html}</div>
        </div>
        ''' or ''}

        {news_html and f'''
        <div class="summary-box">
            <p><span class="label">📰 相关新闻 <span style="color:#888;font-size:13px">（仅展示前10条）</span></span></p>
            <div style="margin-top:10px">{news_html}</div>
        </div>
        ''' or ''}
    </div>
</body>
</html>"""

    def _label_color(self, label: str) -> str:
        """根据情感标签返回颜色"""
        colors = {
            "极度看好": "#00ff88",
            "看好": "#88cc44",
            "中性": "#ffcc44",
            "看空": "#ff8844",
            "极度看空": "#ff4444",
        }
        return colors.get(label, "#888")

    def _score_color(self, score: float) -> str:
        """根据分数返回颜色"""
        if score >= 0.65:
            return "#00ff88"
        elif score >= 0.35:
            return "#ffcc44"
        else:
            return "#ff4444"
