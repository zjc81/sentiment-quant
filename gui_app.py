#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
市场情绪分析与量化回测系统 v2.0 - Windows GUI版本
=============================================================================
"""

import sys, io, os, threading, webbrowser
from pathlib import Path
from datetime import datetime

if sys.platform == "win32" and sys.stdout is not None:
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

import customtkinter as ctk
from tkinter import messagebox, filedialog
import tkinter as tk

from config import REPORT_DIR, DEFAULT_LOOKBACK_DAYS
from core.data_fetcher import (
    search_stocks, get_stock_news, get_stock_by_code,
    get_kline_data, get_real_time_quote, get_market_index,
    get_fund_flow, get_company_announcements, batch_get_news
)
from core.sentiment import SentimentAnalyzer
from core.backtest import compare_strategies
from visualization.report import ReportGenerator

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

_dark_bg = "#1a1a2e"
_accent = "#00d2ff"
_green = "#00ff88"
_red = "#ff4757"


def _make_label(parent, text, size=14, bold=False, color=None, **kw):
    font = ctk.CTkFont(size=size, weight="bold" if bold else "normal")
    lbl = ctk.CTkLabel(parent, text=text, font=font, **kw)
    if color: lbl.configure(text_color=color)
    return lbl


def _make_btn(parent, text, cmd, height=40, size=14, bold=False, **kw):
    f = ctk.CTkFont(size=size, weight="bold" if bold else "normal")
    return ctk.CTkButton(parent, text=text, command=cmd, height=height, font=f, **kw)


class SentimentQuantApp:
    def __init__(self):
        self.root = ctk.CTk()
        self.root.title("SentimentQuant v2.0 - 市场情绪分析与量化回测系统")
        self.root.geometry("1400x900")
        self.root.minsize(1100, 680)
        try: self.root.iconbitmap(default="")
        except: pass

        self.reporter = ReportGenerator()
        self._nav_idx = 0
        self._nav_btns = []

        self._build_ui()
        self._show_page("home")

    def run(self): self.root.mainloop()

    # -- UI construction -------------------------------------------------
    def _build_ui(self):
        self._top = ctk.CTkFrame(self.root, corner_radius=0)
        self._top.pack(fill="x", padx=0, pady=0)
        self._top.grid_columnconfigure(1, weight=1)

        _make_label(self._top, "  SentimentQuant", 22, True).grid(row=0, column=0, padx=20, pady=12, sticky="w")
        _make_label(self._top, "市场情绪分析与量化回测系统",
                     12, color="gray").grid(row=0, column=1, padx=20, pady=12, sticky="e")

        self._body = ctk.CTkFrame(self.root, corner_radius=0)
        self._body.pack(fill="both", expand=True, padx=0, pady=0)
        self._body.grid_columnconfigure(1, weight=1)
        self._body.grid_rowconfigure(1, weight=1)

        # -- sidebar --
        self._sidebar = ctk.CTkFrame(self._body, width=240, corner_radius=0, fg_color=_dark_bg)
        self._sidebar.grid(row=0, column=0, rowspan=3, sticky="nsew")
        self._sidebar.grid_rowconfigure(10, weight=1)

        _make_label(self._sidebar, "导航菜单", 16, True).pack(pady=(20, 15))

        items = [
            ("首页 / 仪表盘",    "home"),
            ("单只股票分析","single"),
            ("批量分析",       "batch"),
            ("策略回测",    "backtest"),
            ("历史报告",      "reports"),
            ("系统说明",          "help"),
        ]
        for i, (title, page) in enumerate(items):
            btn = _make_btn(self._sidebar, f"  {title}",
                            lambda p=page, idx=i: self._nav_to(p, idx),
                            height=38, size=13, fg_color="transparent",
                            anchor="w")
            btn.pack(fill="x", padx=10, pady=3)
            self._nav_btns.append(btn)
        # theme switch
        self._theme_sw = ctk.CTkSwitch(self._sidebar, text="深色模式",
                                        command=self._toggle_theme,
                                        fg_color=_accent)
        self._theme_sw.pack(side="bottom", padx=20, pady=(0, 15), anchor="w")
        self._theme_sw.select()

        # -- main panel --
        self._title_lbl = ctk.CTkFrame(self._body, height=55, corner_radius=0)
        self._title_lbl.grid(row=0, column=1, sticky="ew")
        self._page_title = _make_label(self._title_lbl, "首页", 24, True)
        self._page_title.pack(anchor="w", padx=30, pady=12)

        self._content = ctk.CTkScrollableFrame(self._body, corner_radius=0)
        self._content.grid(row=1, column=1, sticky="nsew")

        # -- status bar --
        self._status = ctk.CTkFrame(self._body, height=36, corner_radius=0)
        self._status.grid(row=2, column=1, sticky="ew")
        self._status_txt = _make_label(self._status, "就绪", 12, color="gray")
        self._status_txt.pack(side="left", padx=20, pady=5)
        self._progress = ctk.CTkProgressBar(self._status, width=200)
        self._progress.set(0)
        self._progress.pack(side="right", padx=20, pady=5)
        self._progress.pack_forget()

    # -- navigation ------------------------------------------------------
    def _nav_to(self, page, idx):
        self._nav_idx = idx
        for i, b in enumerate(self._nav_btns):
            b.configure(fg_color=_accent if i == idx else "transparent")
        self._show_page(page)

    def _show_page(self, page):
        self._page_title.configure(text={
            "home":"首页仪表盘","single":"单只股票情绪分析",
            "batch":"批量股票分析","backtest":"策略回测对比",
            "reports":"历史报告","help":"系统说明"}.get(page,""))
        for w in self._content.winfo_children(): w.destroy()
        {
            "home": self._page_home, "single": self._page_single,
            "batch": self._page_batch, "backtest": self._page_backtest,
            "reports": self._page_reports, "help": self._page_help,
        }[page]()

    # -- progress / status -----------------------------------------------
    def _set_status(self, msg, progress=None):
        self._status_txt.configure(text=msg)
        if progress is not None:
            self._progress.pack(side="right", padx=20, pady=5)
            self._progress.set(progress)
        else:
            self._progress.pack_forget()

    def _run_bg(self, fn, status="正在处理...", on_done=None):
        self._set_status(status, 0)
        def worker():
            try:
                fn()
                self.root.after(0, lambda: self._set_status("就绪"))
                if on_done: self.root.after(0, on_done)
            except Exception as e:
                import traceback
                tb = traceback.format_exc()
                self.root.after(0, lambda: self._set_status(f"错误: {e}"))
                self.root.after(0, lambda: messagebox.showerror("错误", str(e)))
        threading.Thread(target=worker, daemon=True).start()

    # ====================================================================
    #  PAGES
    # ====================================================================

    def _page_home(self):
        _make_label(self._content, "欢迎使用 SentimentQuant", 28, True).pack(pady=(40,5))
        _make_label(self._content, "基于AI的A股市场情绪分析与量化回测系统",
                     14, color="gray").pack(pady=(0,35))

        cards = [
            ("单只股票分析", "输入股票代码，获取情绪评分 + 交互式HTML报告",
             lambda: self._nav_to("single", 1)),
            ("批量分析", "一次性分析多只股票，对比情绪排名",
             lambda: self._nav_to("batch", 2)),
            ("策略回测", "对比多种交易策略的完整性能指标",
             lambda: self._nav_to("backtest", 3)),
            ("历史报告", "浏览和打开之前生成的HTML报告",
             lambda: self._nav_to("reports", 4)),
        ]
        row = ctk.CTkFrame(self._content)
        row.pack(fill="x", padx=30, pady=10)
        for i in range(4): row.grid_columnconfigure(i, weight=1)

        for i, (title, desc, action) in enumerate(cards):
            card = ctk.CTkFrame(row, height=160)
            card.grid(row=0, column=i, padx=8, pady=8, sticky="nsew")
            _make_label(card, title, 16, True).pack(pady=(20,8))
            _make_label(card, desc, 12, color="gray", wraplength=160).pack(pady=(0,12), padx=10)
            _make_btn(card, "打开", action, height=32, size=12).pack(pady=(0,15))

        # Quick start
        qf = ctk.CTkFrame(self._content)
        qf.pack(fill="x", padx=30, pady=(20,30))
        _make_label(qf, "快速开始", 16, True).pack(anchor="w", padx=20, pady=(15,8))
        sf = ctk.CTkFrame(qf)
        sf.pack(fill="x", padx=20, pady=(0,15))
        sf.grid_columnconfigure(0, weight=1)
        e = ctk.CTkEntry(sf, placeholder_text="输入股票代码或名称（如 600519 或 茅台）", height=40)
        e.grid(row=0, column=0, padx=(0,8), sticky="ew")
        _make_btn(sf, "开始分析", lambda: self._quick_analyze(e.get()), height=40, size=13).grid(row=0, column=1)

    def _quick_analyze(self, query):
        if not query.strip(): messagebox.showwarning("提示", "请输入股票代码或名称"); return
        self._nav_to("single", 1)

    # --------------------------------------------------------------------
    def _page_single(self):
        _make_label(self._content, "单只股票情绪分析", 20, True).pack(pady=(25,15))

        sf = ctk.CTkFrame(self._content)
        sf.pack(fill="x", padx=30, pady=10)
        sf.grid_columnconfigure(0, weight=1)
        self._ss_search = ctk.CTkEntry(sf, placeholder_text="输入股票代码或名称", height=40)
        self._ss_search.grid(row=0, column=0, padx=(0,8), sticky="ew")
        _make_btn(sf, "搜索", self._search_stock, height=40, size=13).grid(row=0, column=1)

        pf = ctk.CTkFrame(self._content)
        pf.pack(fill="x", padx=30, pady=5)
        _make_label(pf, "回溯天数:", 13).grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self._ss_days = ctk.CTkEntry(pf, width=80); self._ss_days.insert(0, str(DEFAULT_LOOKBACK_DAYS))
        self._ss_days.grid(row=0, column=1, padx=5, pady=5)
        _make_label(pf, "最大新闻数:", 13).grid(row=0, column=2, padx=(25,5), pady=5, sticky="w")
        self._ss_max = ctk.CTkEntry(pf, width=80); self._ss_max.insert(0, "15")
        self._ss_max.grid(row=0, column=3, padx=5, pady=5)

        self._ss_list = ctk.CTkFrame(self._content)
        self._ss_list.pack(fill="x", padx=30, pady=10)
        self._ss_var = tk.StringVar()

        self._ss_btn = _make_btn(self._content, "开始分析",
                                  lambda: self._start_single(), 50, 14, True,
                                  state="disabled")
        self._ss_btn.pack(fill="x", padx=30, pady=15)

    def _search_stock(self):
        q = self._ss_search.get().strip()
        if not q: messagebox.showwarning("提示", "请输入股票代码或名称"); return
        try:
            results = search_stocks(q)
            for w in self._ss_list.winfo_children(): w.destroy()
            if not results:
                _make_label(self._ss_list, "未找到匹配结果", 13, color="gray").pack(pady=15)
                self._ss_btn.configure(state="disabled")
                return
            results = results[:10]
            self._ss_var.set(results[0]["code"])
            for r in results:
                ctk.CTkRadioButton(self._ss_list,
                                    text=f"{r['name']} ({r['code']})",
                                    variable=self._ss_var, value=r["code"],
                                    font=ctk.CTkFont(size=13)).pack(anchor="w", padx=15, pady=2)
            self._ss_btn.configure(state="normal")
        except Exception as e:
            messagebox.showerror("错误", f"搜索失败: {e}")

    def _start_single(self):
        code = self._ss_var.get()
        days = int(self._ss_days.get())
        mx = int(self._ss_max.get())
        info = get_stock_by_code(code)
        name = info["name"] if info else code

        def work():
            self._set_status(f"正在分析 {name}...", 0.3)
            news = get_stock_news(code, days=days, max_news=mx)
            if not news:
                self.root.after(0, lambda: messagebox.showwarning("提示", "未找到相关新闻"))
                self._set_status("就绪")
                return
            self._set_status("正在进行情绪分析...", 0.5)
            analyzer = SentimentAnalyzer()
            sentiment = analyzer.analyze(news)
            self._set_status("正在获取市场数据...", 0.7)
            try: kline = get_kline_data(code, days=days+10)
            except: kline = None
            try: quote = get_real_time_quote(code)
            except: quote = None
            try: market = get_market_index()
            except: market = None
            try: flow = get_fund_flow(code)
            except: flow = None
            try: ann = get_company_announcements(code, days=days)
            except: ann = None
            self._set_status("正在生成报告...", 0.9)
            path = self.reporter.generate_sentiment_report(
                code, name, sentiment, news, kline, quote, market, flow, ann
            )
            self.root.after(0, lambda: self._show_single_result(name, code, sentiment, path))
        self._run_bg(work)

    def _show_single_result(self, name, code, sentiment, path):
        win = ctk.CTkToplevel(self.root)
        win.title(f"分析结果 - {name}")
        win.geometry("550x460")
        win.grab_set()
        score = sentiment["overall_sentiment"]["score"]
        label = sentiment["overall_sentiment"]["label"]
        conf = sentiment["overall_sentiment"]["confidence_index"]
        _make_label(win, f"{name} ({code})", 22, True).pack(pady=20)
        rf = ctk.CTkFrame(win); rf.pack(fill="x", padx=30, pady=10)
        _make_label(rf, f"情绪评分: {score*100:.1f}%", 16, True).pack(anchor="w", padx=15, pady=4)
        _make_label(rf, f"情绪标签:  {label}", 15).pack(anchor="w", padx=15, pady=2)
        _make_label(rf, f"置信度: {conf*100:.1f}%", 14, color="gray").pack(anchor="w", padx=15, pady=2)
        summary = sentiment["overall_sentiment"].get("summary","")
        if summary:
            _make_label(win, summary, 13, wraplength=480).pack(padx=30, pady=(5,0))
        bf = ctk.CTkFrame(win); bf.pack(fill="x", padx=30, pady=20)
        _make_btn(bf, "查看HTML报告", lambda: webbrowser.open(f"file://{path}"), 40, 14).pack(side="left", padx=8, expand=True, fill="x")
        _make_btn(bf, "关闭", win.destroy, 40, 14).pack(side="left", padx=8, expand=True, fill="x")

    # --------------------------------------------------------------------
    def _page_batch(self):
        _make_label(self._content, "批量股票分析", 20, True).pack(pady=(25,15))
        mf = ctk.CTkFrame(self._content)
        mf.pack(fill="x", padx=30, pady=10)
        _make_label(mf, "输入股票代码（逗号分隔）:", 13).pack(anchor="w", padx=15, pady=(10,5))
        self._batch_entry = ctk.CTkEntry(mf, placeholder_text="例如: 600519,000001,600036", height=38)
        self._batch_entry.pack(fill="x", padx=15, pady=5)
        pf = ctk.CTkFrame(mf)
        pf.pack(fill="x", padx=15, pady=10)
        _make_label(pf, "天数:", 13).grid(row=0, column=0, padx=5, sticky="w")
        self._batch_days = ctk.CTkEntry(pf, width=80); self._batch_days.insert(0, str(DEFAULT_LOOKBACK_DAYS))
        self._batch_days.grid(row=0, column=1, padx=5)
        _make_label(pf, "每支股票新闻数:", 13).grid(row=0, column=2, padx=(25,5), sticky="w")
        self._batch_max = ctk.CTkEntry(pf, width=80); self._batch_max.insert(0, "10")
        self._batch_max.grid(row=0, column=3, padx=5)

        _make_btn(self._content, "开始批量分析", lambda: self._start_batch(), 50, 14, True).pack(fill="x", padx=30, pady=15)

    def _start_batch(self):
        raw = self._batch_entry.get().strip()
        if not raw: messagebox.showwarning("提示", "请输入股票代码"); return
        codes = [c.strip() for c in raw.replace("，",",").replace(" ",", ").split(",") if c.strip()]
        stocks = []
        for c in codes:
            info = get_stock_by_code(c)
            if info: stocks.append(info)
        if not stocks: messagebox.showwarning("提示", "未找到有效股票"); return

        days = int(self._batch_days.get())
        mx = int(self._batch_max.get())
        total = len(stocks)

        def work():
            results = []
            news_map = batch_get_news([s["code"] for s in stocks], days=days, max_news=mx)
            for i, s in enumerate(stocks):
                self._set_status(f"正在分析 [{i+1}/{total}] {s['name']}", (i+1)/total)
                n = news_map.get(s["code"], [])
                if n:
                    analyzer = SentimentAnalyzer()
                    sentiment = analyzer.analyze(n)
                    results.append((s, sentiment))
            results.sort(key=lambda x: x[1]["overall_sentiment"]["score"], reverse=True)
            self.root.after(0, lambda: self._show_batch_result(results))

        self._run_bg(work, f"正在分析 {total} 只股票...")

    def _show_batch_result(self, results):
        win = ctk.CTkToplevel(self.root)
        win.title(f"批量分析结果 - {len(results)} 只股票")
        win.geometry("700x550")
        win.grab_set()
        _make_label(win, f"批量分析结果（共 {len(results)} 只股票）", 20, True).pack(pady=20)
        lst = ctk.CTkScrollableFrame(win); lst.pack(fill="both", expand=True, padx=30, pady=10)
        for i, (s, sentiment) in enumerate(results[:30]):
            score = sentiment["overall_sentiment"]["score"]
            label = sentiment["overall_sentiment"]["label"]
            f = ctk.CTkFrame(lst); f.pack(fill="x", pady=3)
            c = _green if label in ("positive","bullish","积极") else (_red if label in ("negative","bearish","消极") else "gray")
            _make_label(f, f"{i+1}.", 14, True, color=c).pack(side="left", padx=8, pady=8)
            _make_label(f, f"{s['name']} ({s['code']})", 14, True).pack(side="left", padx=5, pady=8)
            _make_label(f, f"{score*100:.1f}%", 14, True, color=c).pack(side="right", padx=12, pady=8)
        _make_btn(win, "关闭", win.destroy, 40, 14).pack(padx=30, pady=15, fill="x")

    # --------------------------------------------------------------------
    def _page_backtest(self):
        _make_label(self._content, "策略回测对比", 20, True).pack(pady=(25,15))
        sf = ctk.CTkFrame(self._content)
        sf.pack(fill="x", padx=30, pady=10)
        sf.grid_columnconfigure(0, weight=1)
        self._bt_search = ctk.CTkEntry(sf, placeholder_text="输入股票代码或名称", height=40)
        self._bt_search.grid(row=0, column=0, padx=(0,8), sticky="ew")
        self._bt_lbl = _make_label(sf, "未选择股票", 13, color="gray")
        self._bt_lbl.grid(row=0, column=2, padx=10)
        _make_btn(sf, "搜索", self._search_bt_stock, height=40, size=13).grid(row=0, column=3)

        pf = ctk.CTkFrame(self._content)
        pf.pack(fill="x", padx=30, pady=10)
        _make_label(pf, "本金:", 13).grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self._bt_capital = ctk.CTkEntry(pf, width=100); self._bt_capital.insert(0, "100000")
        self._bt_capital.grid(row=0, column=1, padx=5)
        _make_label(pf, "回测天数:", 13).grid(row=0, column=2, padx=(25,5), sticky="w")
        self._bt_days = ctk.CTkEntry(pf, width=80); self._bt_days.insert(0, "60")
        self._bt_days.grid(row=0, column=3, padx=5)
        self._bt_lbl2 = ctk.CTkLabel(pf, text=""); self._bt_lbl2.grid(row=0, column=4, padx=20)

        self._bt_btn = _make_btn(self._content, "开始回测",
                                  lambda: self._start_bt(), 50, 14, True,
                                  state="disabled")
        self._bt_btn.pack(fill="x", padx=30, pady=15)

    def _search_bt_stock(self):
        q = self._bt_search.get().strip()
        if not q: messagebox.showwarning("提示", "请输入股票代码或名称"); return
        try:
            results = search_stocks(q)
            if not results: messagebox.showwarning("提示", "未找到匹配结果"); return
            self._bt_stock = results[0]
            self._bt_lbl2.configure(text=f"已选择: {self._bt_stock['name']} ({self._bt_stock['code']})", text_color=_accent)
            self._bt_btn.configure(state="normal")
        except Exception as e:
            messagebox.showerror("错误", f"搜索失败: {e}")

    def _start_bt(self):
        if not hasattr(self, "_bt_stock"): return
        s = self._bt_stock
        cap = int(self._bt_capital.get())
        days = int(self._bt_days.get())

        def work():
            self._set_status(f"正在回测 {s['name']}...", 0.5)
            results = compare_strategies(stock_code=s["code"], stock_name=s["name"],
                                          capital=cap, lookback_days=days)
            all_r = list(results.values())
            path = self.reporter.generate_backtest_report(results=all_r,
                                                           stock_name_map={s["code"]: s["name"]})
            self.root.after(0, lambda: self._show_bt_result(results, path))
        self._run_bg(work)

    def _show_bt_result(self, results, path):
        win = ctk.CTkToplevel(self.root)
        win.title("回测结果"); win.geometry("800x600"); win.grab_set()
        _make_label(win, "策略回测对比结果", 20, True).pack(pady=20)
        t = ctk.CTkFrame(win); t.pack(fill="x", padx=30, pady=10)
        cols = ["策略名称", "总收益率", "年化收益率", "最大回撤", "夏普比率", "胜率"]
        for j, h in enumerate(cols):
            _make_label(t, h, 13, True).grid(row=0, column=j, padx=8, pady=8)
        mapping = {"buy_hold":"买入持有策略", "sentiment_only":"纯情绪策略",
                    "sentiment_ma":"情绪+均线策略"}
        for i, (sk, r) in enumerate(results.items(), 1):
            name = mapping.get(sk, sk)
            _make_label(t, name, 12).grid(row=i, column=0, padx=8, pady=4, sticky="w")
            _make_label(t, f"{r.total_return:+.2f}%", 12).grid(row=i, column=1, padx=8, pady=4)
            _make_label(t, f"{r.annual_return:+.2f}%", 12).grid(row=i, column=2, padx=8, pady=4)
            _make_label(t, f"{r.max_drawdown:.2f}%", 12).grid(row=i, column=3, padx=8, pady=4)
            _make_label(t, f"{r.sharpe_ratio:.2f}", 12).grid(row=i, column=4, padx=8, pady=4)
            _make_label(t, f"{r.win_rate:.1f}%", 12).grid(row=i, column=5, padx=8, pady=4)
        bf = ctk.CTkFrame(win); bf.pack(fill="x", padx=30, pady=20)
        _make_btn(bf, "查看HTML报告", lambda: webbrowser.open(f"file://{path}"), 40, 14).pack(side="left", padx=8, expand=True, fill="x")
        _make_btn(bf, "关闭", win.destroy, 40, 14).pack(side="left", padx=8, expand=True, fill="x")

    # --------------------------------------------------------------------
    def _page_reports(self):
        _make_label(self._content, "历史报告", 20, True).pack(pady=(25,15))
        if not REPORT_DIR.exists():
            _make_label(self._content, "未找到报告目录", 13, color="gray").pack(pady=30); return
        reports = sorted(REPORT_DIR.glob("*.html"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not reports:
            _make_label(self._content, "暂无报告，请先进行分析！", 13, color="gray").pack(pady=30); return
        _make_label(self._content, f"共找到 {len(reports)} 份报告", 14).pack(anchor="w", padx=30, pady=(10,5))
        for i, p in enumerate(reports[:50]):
            f = ctk.CTkFrame(self._content); f.pack(fill="x", padx=30, pady=3)
            sz = p.stat().st_size / 1024
            mt = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            _make_label(f, f"{i+1}. {p.stem}", 13, True).pack(side="left", padx=15, pady=8)
            _make_label(f, f"{sz:.0f}KB | {mt}", 11, color="gray").pack(side="left", padx=10, pady=8)
            _make_btn(f, "打开", lambda pp=p: webbrowser.open(f"file://{pp}"), 30, 11).pack(side="right", padx=15, pady=6)
        _make_btn(self._content, "打开报告文件夹", lambda: os.startfile(str(REPORT_DIR)),
                   38, 13).pack(fill="x", padx=30, pady=15)

    # --------------------------------------------------------------------
    def _page_help(self):
        _make_label(self._content, "系统说明", 20, True).pack(pady=(25,15))
        txt = ctk.CTkTextbox(self._content, font=ctk.CTkFont(size=13), height=500)
        txt.pack(fill="both", expand=True, padx=30, pady=10)
        text = """SENTIMENTQUANT v2.0 - 市场情绪分析与量化回测系统

系统功能
  1. 从财经网站获取A股股票新闻
  2. 使用本地 SnowNLP AI 引擎进行情绪分析（无需API密钥）
  3. 生成 Plotly 交互式 HTML 报告（深色主题）
  4. 运行多策略回测并对比性能表现

情绪分析说明
  - 基于NLP的中文情绪评分（0-100%）
  - 多维度分析：6大主题 x 4种信息来源
  - 提供置信度指数衡量结果可靠性
  - 支持关键词分析作为备选方案

回测策略说明
  - 买入持有策略：基准策略，始终持有股票
  - 纯情绪策略：情绪积极时买入，情绪消极时卖出
  - 情绪+均线策略：情绪积极且均线看涨时买入，否则持有现金

快速开始
  1. 点击侧边栏的"单只股票分析"
  2. 输入股票代码（如 600519）并点击搜索
  3. 选择股票并点击"开始分析"
  4. 等待分析完成，然后查看交互式HTML报告

报告保存位置
  所有HTML报告保存在：data/reports/ 目录

技术栈
  GUI框架: CustomTkinter | 数据源: AKShare | NLP引擎: SnowNLP
  可视化: Plotly | 后端: pandas, numpy

注意：回测结果仅供参考，不构成投资建议。
      投资有风险，入市需谨慎，请务必自行研究后再做决策。
"""
        txt.insert("1.0", text); txt.configure(state="disabled")

    def _toggle_theme(self):
        ctk.set_appearance_mode("dark" if self._theme_sw.get() else "light")
        self._theme_sw.configure(text="深色模式" if self._theme_sw.get() else "浅色模式")


def main():
    app = SentimentQuantApp()
    app.run()

if __name__ == "__main__":
    main()
