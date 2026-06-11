#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SentimentQuant - EXE Build Script
Run: python build.py
"""

import subprocess, sys, shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
PYTHON = Path(r"C:/Users/Think/.workbuddy/binaries/python/envs/sentiment_quant/Scripts/python.exe")
DIST_DIR = PROJECT_ROOT / "dist"
BUILD_DIR = PROJECT_ROOT / "build"

# Clean previous builds
for d in [DIST_DIR, BUILD_DIR]:
    if d.exists():
        shutil.rmtree(d)

# Hidden imports
hidden = [
    "customtkinter","darkdetect","PIL","PIL._tkinter_finder",
    "akshare","lxml","lxml.etree","html5lib","bs4","openpyxl",
    "snownlp","snownlp.sentiment","snownlp.seg","snownlp.tag",
    "plotly","plotly.graph_objects","plotly.io","plotly.express","plotly.validators",
    "pandas","numpy","numpy.core._methods","numpy.lib.format",
    "requests","urllib3","certifi","chardet",
    "tkinter","_tkinter","tkinter.filedialog","tkinter.messagebox",
    "json","datetime","threading","webbrowser","collections","re","io","os","pathlib",
    "colorama","python_dateutil","dateutil","dateutil.tz","tqdm",
]

# Build data list - include project data and all SnowNLP data files
datas = []

# Project data dir
data_dir = PROJECT_ROOT / "data"
if data_dir.exists():
    datas.append(f"{data_dir}{';'}data")

# SnowNLP data files (required at runtime)
snownlp_root = Path(r"C:/Users/Think/.workbuddy/binaries/python/envs/sentiment_quant/Lib/site-packages/snownlp")
if snownlp_root.exists():
    for f in snownlp_root.rglob("*"):
        if f.is_file() and (f.suffix in (".txt", ".marshal") or f.name.endswith(".marshal.3")):
            rel = f.relative_to(snownlp_root.parent)
            target = str(rel.parent).replace("\\", "/")
            datas.append(f"{f}{';'}{target}/")

# Build command
cmd = [
    str(PYTHON), "-m", "PyInstaller",
    "--name=SentimentQuant",
    "--noconfirm",
    "--clean",
    "--noconsole",
    "--onedir",
    str(PROJECT_ROOT / "gui_app.py"),
]

for h in hidden:
    cmd.extend(["--hidden-import", h])

for d in datas:
    cmd.extend(["--add-data", d])

print("Building SentimentQuant.exe...")
print(f"Data files to bundle: {len(datas)} (including {len(datas)-1} snownlp files)")
print()

result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=False)

if result.returncode == 0:
    exe = DIST_DIR / "SentimentQuant.exe"
    print(f"\n[SUCCESS] EXE built: {exe}")
    if exe.exists():
        # Check total dist size
        total_size = sum(f.stat().st_size for f in DIST_DIR.rglob("*") if f.is_file()) / (1024*1024)
        print(f"[INFO] Dist size: {total_size:.1f} MB")
else:
    print(f"\n[FAILED] Exit code: {result.returncode}")
    sys.exit(1)
