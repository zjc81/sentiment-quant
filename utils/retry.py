"""
智能重试机制 - 支持指数退避、多接口备选、超时控制
"""
import time
import random
import functools
from typing import Callable, Any, List, Optional


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    backoff_factor: float = 2.0,
    max_delay: float = 30.0,
    exceptions: tuple = (Exception,),
    on_retry: Optional[Callable[[int, Exception], None]] = None,
):
    """
    带指数退避的重试装饰器

    Args:
        max_retries: 最大重试次数
        base_delay: 初始等待时间（秒）
        backoff_factor: 退避因子（每次重试等待时间乘以此值）
        max_delay: 最大等待时间
        exceptions: 需要重试的异常类型
        on_retry: 每次重试前的回调函数
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        delay = min(base_delay * (backoff_factor ** attempt), max_delay)
                        # 添加随机抖动，避免同时重试
                        jitter = random.uniform(0, delay * 0.1)
                        sleep_time = delay + jitter
                        if on_retry:
                            on_retry(attempt + 1, e, sleep_time)
                        time.sleep(sleep_time)
                    else:
                        raise
            raise last_exception  # type: ignore
        return wrapper
    return decorator


def fetch_with_fallback(
    fallbacks: List[Callable[[], Any]],
    max_retries_per_source: int = 2,
    on_switch: Optional[Callable[[int, str], None]] = None,
) -> Any:
    """
    多接口备选获取数据

    Args:
        fallbacks: 备选数据获取函数列表（按优先级排列）
        max_retries_per_source: 每个来源最大重试次数
        on_switch: 切换数据源时的回调

    Returns:
        任意类型: 获取到的数据

    Raises:
        RuntimeError: 所有数据源都失败时
    """
    last_error = None
    for idx, fetcher in enumerate(fallbacks):
        for attempt in range(max_retries_per_source):
            try:
                return fetcher()
            except Exception as e:
                last_error = e
                if attempt < max_retries_per_source - 1:
                    time.sleep(1.0 * (2 ** attempt))
                continue
        if idx < len(fallbacks) - 1 and on_switch:
            source_name = getattr(fetcher, "__name__", f"source_{idx}")
            on_switch(idx + 1, source_name)

    raise RuntimeError(
        f"所有数据源均获取失败，最后错误: {last_error}"
    )


def safe_request(
    url: str,
    timeout: int = 30,
    max_retries: int = 3,
    **kwargs,
) -> Any:
    """
    安全的HTTP请求封装 - 带重试和超时

    Args:
        url: 请求URL
        timeout: 超时时间（秒）
        max_retries: 最大重试次数
        **kwargs: 传递给requests的其他参数

    Returns:
        requests.Response: HTTP响应
    """
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    session = requests.Session()
    retry_strategy = Retry(
        total=max_retries,
        backoff_factor=1.0,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    response = session.get(url, timeout=timeout, **kwargs)
    response.raise_for_status()
    return response
