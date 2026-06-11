"""
缓存管理模块 - JSON文件缓存 + LRU内存缓存
"""
import os
import json
import hashlib
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional, Dict, Callable


class FileCache:
    """
    文件缓存 - 在磁盘上缓存数据以减少重复请求
    """

    def __init__(self, cache_dir: Path, valid_days: int = 1):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.valid_days = valid_days

    def _get_path(self, key: str) -> Path:
        """根据key生成缓存文件路径"""
        # 使用hash生成安全的文件名
        hashed = hashlib.md5(key.encode()).hexdigest()
        return self.cache_dir / f"{hashed}.json"

    def get(self, key: str) -> Optional[Any]:
        """获取缓存"""
        path = self._get_path(key)
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            cache_time = datetime.fromisoformat(data["_cached_at"])
            if (datetime.now() - cache_time).days <= self.valid_days:
                return data["_value"]
        except Exception:
            pass
        return None

    def set(self, key: str, value: Any):
        """设置缓存"""
        path = self._get_path(key)
        try:
            data = {
                "_cached_at": datetime.now().isoformat(),
                "_key": key,
                "_value": value,
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"  缓存写入失败: {e}")

    def get_or_set(self, key: str, fetch_func: Callable[[], Any]) -> Any:
        """获取缓存，如果没有则调用fetch_func获取并缓存"""
        cached = self.get(key)
        if cached is not None:
            return cached
        value = fetch_func()
        self.set(key, value)
        return value

    def clear_expired(self):
        """清除过期缓存"""
        now = datetime.now()
        for f in self.cache_dir.glob("*.json"):
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                cache_time = datetime.fromisoformat(data["_cached_at"])
                if (now - cache_time).days > self.valid_days:
                    f.unlink()
            except Exception:
                f.unlink()

    def clear_all(self):
        """清除所有缓存"""
        for f in self.cache_dir.glob("*.json"):
            try:
                f.unlink()
            except Exception:
                pass


class MemoryCache:
    """
    内存缓存 - LRU策略，用于加速频繁访问的数据
    """

    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self._cache: Dict[str, Any] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            return self._cache.get(key)

    def set(self, key: str, value: Any):
        with self._lock:
            if len(self._cache) >= self.max_size:
                # 简单策略：清除一半
                keys_to_remove = list(self._cache.keys())[:self.max_size // 2]
                for k in keys_to_remove:
                    del self._cache[k]
            self._cache[key] = value

    def get_or_set(self, key: str, fetch_func: Callable[[], Any]) -> Any:
        cached = self.get(key)
        if cached is not None:
            return cached
        value = fetch_func()
        self.set(key, value)
        return value

    def clear(self):
        with self._lock:
            self._cache.clear()
