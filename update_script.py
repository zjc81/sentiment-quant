#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
更新讲稿：添加PPT翻页标记和材料切换提示
"""
import re

# 读取原讲稿
with open("/Users/aphael/Desktop/其他/副业/Crypto投资小白书/python_world/Python实战/股市舆情AI分析/市场情绪与量化分析系统/视频讲稿_精简总览版.md", "r", encoding="utf-8") as f:
    content = f.read()

# 定义每个时间段的PPT翻页标记
markers = [
    # (原始标题行, 插入的PPT标记)
    ("## 【0:00 - 0:50】开场：直出炸场画面",
     "\n> **[📊 PPT翻页：第1页 封面]**\n> **[📺 此时屏幕展示：dashboard_cinematic.html 全屏录屏（星空粒子+霓虹边框）]**\n"
    ),
    ("## 【0:50 - 1:40】项目能做哪些事？",
     "\n> **[📊 PPT翻页：第2页 项目功能概览]**\n> **[📺 此时PPT展示：四大功能卡片]**\n"
    ),
    ("## 【1:40 - 2:30】整体架构：数据是怎么流的？",
     "\n> **[📊 PPT翻页：第3页 整体架构数据流]**\n> **[📺 此时PPT展示：5步骤数据流示意图]**\n"
    ),
    ("## 【2:30 - 3:20】模块一：情感分析引擎（`sentiment.py`）",
     "\n> **[📊 PPT翻页：第5页 sentiment.py 代码展示]**\n> **[📺 此时PPT展示：左侧SnowNLP代码+右侧六维主题说明]**\n"
    ),
    ("## 【3:20 - 4:10】模块二：回测引擎（`backtest.py`）",
     "\n> **[📊 PPT翻页：第6页 backtest.py 代码展示]**\n> **[📺 此时PPT展示：左侧策略代码+右侧策略说明]**\n"
    ),
    ("## 【4:10 - 5:00】模块三：可视化报告（`report.py`）",
     "\n> **[📊 PPT翻页：第7页 report.py 可视化]**\n> **[📺 此时PPT展示：左侧Plotly代码+右侧报告图表清单]**\n"
    ),
    ("## 【5:00 - 5:50】实战：跑一遍试试？",
     "\n> **[📊 PPT翻页：第8页 实战演示]**\n> **[📺 此时切换：终端录屏 或 PPT第8页的演示流程图]**\n"
    ),
    ("## 【5:50 - 6:30】如何获取全套源码？",
     "\n> **[📊 PPT翻页：第10页 获取源码三步走]**\n> **[📺 此时PPT展示：三步卡片（点赞→关注→私信）]**\n"
    ),
    ("## 【6:30 - 7:10】收尾：项目亮点和结束语",
     "\n> **[📊 PPT翻页：第9页 项目亮点总结]**\n> **[📺 此时PPT展示：4个亮点卡片]**\n"
    ),
    ("## 【7:10 - 8:00】收尾：项目亮点和结束语",
     "\n> **[📊 PPT翻页：第11页 结尾页]**\n> **[📺 此时屏幕展示：dashboard_cinematic.html 全屏特效淡出]**\n"
    ),
]

# 依次插入标记
for header, marker in markers:
    if header in content:
        # 在标题行之后、第一个 > 之前插入
        # 找到标题行位置
        idx = content.find(header)
        if idx != -1:
            # 找到该行结束位置
            line_end = content.find("\n", idx)
            if line_end == -1:
                line_end = len(content)
            # 插入标记
            content = content[:line_end] + marker + content[line_end:]

# 写回文件
with open("/Users/aphael/Desktop/其他/副业/Crypto投资小白书/python_world/Python实战/股市舆情AI分析/市场情绪与量化分析系统/视频讲稿_精简总览版.md", "w", encoding="utf-8") as f:
    f.write(content)

print("✅ 讲稿已更新：添加PPT翻页标记")
print("📊 共添加 10 处PPT翻页提示")
print("📺 共添加 10 处材料切换提示")
