#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
打包脚本 - 将GUI应用程序打包成Windows可执行文件
使用PyInstaller创建独立exe文件
"""

import subprocess
import sys
import os
from pathlib import Path

def install_pyinstaller():
    """安装PyInstaller"""
    print("正在安装 PyInstaller...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

def build_exe():
    """打包成exe文件"""
    project_root = Path(__file__).parent
    
    # PyInstaller 命令参数
    cmd = [
        "pyinstaller",
        "--name=SentimentQuant",  # 输出文件名
        "--onefile",  # 打包成单个exe文件
        "--windowed",  # 不显示控制台窗口
        "--icon=NONE",  # 暂不设置图标
        "--add-data", f"{project_root}/data;data",  # 包含数据目录
        "--hidden-import", "customtkinter",
        "--hidden-import", "akshare",
        "--hidden-import", "snownlp",
        "--hidden-import", "plotly",
        "--hidden-import", "pandas",
        "--hidden-import", "numpy",
        str(project_root / "gui_app.py"),
    ]
    
    print("开始打包...")
    print(f"命令: {' '.join(cmd)}")
    
    try:
        subprocess.check_call(cmd, cwd=project_root)
        print("\n" + "="*50)
        print("打包成功！")
        print(f"exe文件位置: {project_root}/dist/SentimentQuant.exe")
        print("="*50)
    except subprocess.CalledProcessError as e:
        print(f"\n打包失败: {e}")
        return False
    
    return True

def main():
    """主函数"""
    print("="*50)
    print("市场情绪分析系统 - 打包工具")
    print("="*50)
    print()
    
    # 检查PyInstaller
    try:
        import PyInstaller
    except ImportError:
        print("未检测到 PyInstaller，正在安装...")
        install_pyinstaller()
    
    # 开始打包
    if build_exe():
        print("\n打包完成！")
        print("提示: 首次运行exe可能需要允许防火墙访问")
    
if __name__ == "__main__":
    main()
