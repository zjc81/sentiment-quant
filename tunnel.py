#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
公网隧道管理器 - 让你的手机随时随地访问本地 Flask 服务
使用 localhost.run / serveo.net 免费隧道（无需注册、无需安装）
"""

import subprocess
import threading
import re
import time
import sys
import os


class TunnelManager:
    """管理公网隧道连接"""

    def __init__(self, local_port=5000):
        self.local_port = local_port
        self.proc = None
        self.public_url = None
        self._running = False
        self._url_found = threading.Event()

    def _try_localhost_run(self) -> str | None:
        """尝试 localhost.run 隧道（首选）"""
        try:
            cmd = [
                "ssh",
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
                "-o", "ServerAliveInterval=30",
                "-o", "ServerAliveCountMax=3",
                "-o", "ConnectTimeout=10",
                "-R", f"80:localhost:{self.local_port}",
                "nokey@localhost.run",
            ]

            self.proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            url_pattern = re.compile(r"https://([a-zA-Z0-9-]+\.lhr\.life)")

            # 读取输出寻找URL，最多等待15秒
            start = time.time()
            for line in iter(self.proc.stdout.readline, ""):
                match = url_pattern.search(line)
                if match:
                    return match.group(0)
                if time.time() - start > 15:
                    break

            return None
        except (FileNotFoundError, Exception):
            return None

    def _try_serveo(self) -> str | None:
        """备用: serveo.net 隧道"""
        try:
            cmd = [
                "ssh",
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
                "-o", "ServerAliveInterval=30",
                "-o", "ConnectTimeout=10",
                "-R", f"80:localhost:{self.local_port}",
                "serveo.net",
            ]

            # 先结束之前的进程
            if self.proc:
                self.proc.kill()

            self.proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            url_pattern = re.compile(r"https://([a-zA-Z0-9]+)")

            start = time.time()
            for line in iter(self.proc.stdout.readline, ""):
                match = url_pattern.search(line)
                if match and ("serveo" in match.group(0) or match.group(1).isalnum()):
                    return match.group(0)
                if time.time() - start > 15:
                    break

            return None
        except (FileNotFoundError, Exception):
            return None

    def start(self) -> str:
        """启动隧道，返回公网 URL"""
        print("\n" + "=" * 60)
        print("  创建公网隧道...")
        print("=" * 60)

        # 尝试 localhost.run
        print("  [1/2] 尝试 localhost.run...")
        url = self._try_localhost_run()

        if url:
            self.public_url = url
            self._url_found.set()
            return url

        # 备用: serveo.net
        print("  [2/2] 尝试 serveo.net...")
        url = self._try_serveo()

        if url:
            self.public_url = url
            self._url_found.set()
            return url

        raise RuntimeError("无法创建公网隧道，请检查网络连接后重试")

    def stop(self):
        """关闭隧道"""
        if self.proc:
            self.proc.kill()
            self.proc = None
        self.public_url = None

    def is_running(self):
        """检查隧道是否活跃"""
        if not self.proc:
            return False
        return self.proc.poll() is None


def start_public_tunnel(port=5000) -> str:
    """
    启动公网隧道并返回 URL

    使用:
        from tunnel import start_public_tunnel
        public_url = start_public_tunnel(5000)
        print(f"公网地址: {public_url}")
    """
    manager = TunnelManager(port)
    url = manager.start()
    return url


def main():
    """独立运行：测试隧道"""
    print("TunnelManager 测试")
    try:
        url = start_public_tunnel(5000)
        print(f"\n  公网地址: {url}")
        print(f"  在手机上打开此地址即可访问！")
        print(f"  按 Ctrl+C 退出")
        while True:
            time.sleep(1)
    except RuntimeError as e:
        print(f"\n  [错误] {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n  已退出")


if __name__ == "__main__":
    main()
