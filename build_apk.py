#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
SentimentQuant APK 构建工具
将 Flask Web 应用打包成 Android APK
=============================================================================

构建方式:
    方式一（推荐）: PWA - 添加到主屏幕
        手机浏览器打开网址 → 菜单 → "添加到主屏幕" → 像原生App一样使用

    方式二: TWA (Trusted Web Activity)
        使用 bubblewrap 将 PWA 打包成真正的 APK

    方式三: WebView 封装
        使用 Android Studio 创建 WebView 项目封装

本脚本生成方式二所需的所有文件。
=============================================================================
"""

import os, json, shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
OUTPUT_DIR = PROJECT_ROOT / "apk_build"
STATIC_DIR = PROJECT_ROOT / "static"
TEMPLATES_DIR = PROJECT_ROOT / "templates"

# ============================================================================
# 步骤1: 生成 TWA 所需文件
# ============================================================================

def build_twa_files(host="127.0.0.1", port=5000):
    """生成 Trusted Web Activity 包装文件"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[INFO] 生成 TWA 文件到: {OUTPUT_DIR}")

    # 生成 assetlinks.json
    assetlinks = [{
        "relation": ["delegate_permission/common.handle_all_urls"],
        "target": {
            "namespace": "android_app",
            "package_name": "com.sentimentquant.app",
            "sha256_cert_fingerprints": ["YOUR_SHA256_HERE"]
        }
    }]

    with open(OUTPUT_DIR / "assetlinks.json", "w") as f:
        json.dump(assetlinks, f, indent=2, ensure_ascii=False)
    print(f"  [OK] assetlinks.json")

    # 生成 strings.xml
    strings_xml = '''<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string name="app_name">市场情绪量化</string>
    <string name="asset_statements">
        [{
            "include": "https://sentimentquant.example.com/.well-known/assetlinks.json"
        }]
    </string>
</resources>'''
    with open(OUTPUT_DIR / "strings.xml", "w", encoding="utf-8") as f:
        f.write(strings_xml)
    print(f"  [OK] strings.xml")

    # 生成 twa-manifest.json
    twa_manifest = {
        "packageId": "com.sentimentquant.app",
        "host": host,
        "name": "市场情绪量化系统",
        "launcherName": "SentimentQuant",
        "display": "standalone",
        "themeColor": "#0f0f1a",
        "navigationColor": "#0f0f1a",
        "backgroundColor": "#0f0f1a",
        "startUrl": "/",
        "iconUrl": "https://sentimentquant.example.com/static/icon-512.png",
        "maskableIconUrl": "https://sentimentquant.example.com/static/icon-192.png",
        "splashScreenFadeOutDuration": 300,
        "signingKey": {
            "path": "./android.keystore",
            "alias": "sentimentquant"
        }
    }
    with open(OUTPUT_DIR / "twa-manifest.json", "w", encoding="utf-8") as f:
        json.dump(twa_manifest, f, indent=2, ensure_ascii=False)
    print(f"  [OK] twa-manifest.json")


def build_direct_apk_explanation():
    """生成直接APK构建说明"""
    guide = """# SentimentQuant APK 构建指南

## 方式一: PWA 添加到主屏幕（推荐，无需构建APK）

1. 启动服务器: 双击 `启动手机服务.bat`
2. 手机连接同一 WiFi
3. 手机浏览器打开: `http://电脑IP:5000`
4. 浏览器菜单 → "添加到主屏幕" (Chrome) 或 "添加到桌面" (Safari)
5. 桌面出现图标,点击即可像原生App一样使用

优点: 无需构建APK,实时更新,支持所有功能

---

## 方式二: Bubblewrap (TWA) 构建真 APK

### 安装 bubblewrap:
```bash
npm install -g @bubblewrap/cli
```

### 初始化项目:
```bash
bubblewrap init --manifest "https://YOUR_SERVER/static/manifest.json"
```

### 构建 APK:
```bash
bubblewrap build
```

生成的 APK 在项目 app-release 目录下。

---

## 方式三: Android Studio WebView 封装

1. 创建新 Android 项目
2. 在 MainActivity.java 中添加 WebView:
```java
WebView webView = findViewById(R.id.webview);
webView.getSettings().setJavaScriptEnabled(true);
webView.loadUrl("http://YOUR_SERVER_IP:5000");
```

3. 在 AndroidManifest.xml 添加 Internet 权限:
```xml
<uses-permission android:name="android.permission.INTERNET"/>
```

4. Build → Generate Signed APK

---

## 部署到公网 (让手机在外网也能访问)

### 使用 ngrok (免费):
```bash
# 安装 ngrok, 然后:
ngrok http 5000
# 使用生成的 https://xxx.ngrok.io 地址
```

### 使用 CloudStudio 部署:
项目已支持 `cloudstudio-deploy`,可以部署到云端。
"""

    with open(OUTPUT_DIR / "APK构建指南.md", "w", encoding="utf-8") as f:
        f.write(guide)
    print(f"  [OK] APK构建指南.md")


# ============================================================================
# 主流程
# ============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("  SentimentQuant APK Builder")
    print("=" * 60)
    print()

    build_direct_apk_explanation()
    build_twa_files()

    print()
    print("=" * 60)
    print("  构建文件已生成到: apk_build/")
    print()
    print("  推荐使用方式一 (PWA 添加到主屏幕):")
    print("    1. 双击 `启动手机服务.bat` 启动服务器")
    print("    2. 手机浏览器打开 http://电脑IP:5000")
    print("    3. 添加到主屏幕即可像 App 一样使用!")
    print("=" * 60)
