"""
市场情绪与量化分析系统 - 配置文件
"""
import os
from pathlib import Path

# ===== 项目根目录 =====
PROJECT_ROOT = Path(__file__).parent

# ===== 数据目录 =====
DATA_DIR = PROJECT_ROOT / "data"
NEWS_CACHE_DIR = DATA_DIR / "news_cache"
SENTIMENT_CACHE_DIR = DATA_DIR / "sentiment_cache"
REPORT_DIR = DATA_DIR / "reports"
STOCK_LIST_CACHE = DATA_DIR / "stock_list_cache"

# 自动创建目录
for d in [DATA_DIR, NEWS_CACHE_DIR, SENTIMENT_CACHE_DIR, REPORT_DIR, STOCK_LIST_CACHE]:
    d.mkdir(parents=True, exist_ok=True)

# ===== 缓存设置 =====
CACHE_VALID_DAYS = 1          # 缓存有效期（天）
DEFAULT_LOOKBACK_DAYS = 7     # 默认回溯天数
MAX_NEWS_PER_STOCK = 20       # 每只股票最大新闻数
NEWS_PER_DAY = 5              # 每天最多保留的新闻数

# ===== 网络请求设置 =====
REQUEST_TIMEOUT = 30          # 请求超时（秒）
MAX_RETRIES = 3               # 最大重试次数
RETRY_BACKOFF = 2.0           # 退避因子

# ===== 回测设置 =====
DEFAULT_START_CAPITAL = 100000   # 初始资金
DEFAULT_COMMISSION = 0.0003      # 佣金费率（万三）
DEFAULT_SLIPPAGE = 0.001         # 滑点

# ===== 情感分析配置 =====
# 正面关键词
POSITIVE_KEYWORDS = [
    '利好', '增长', '突破', '创新高', '获得', '中标', '战略合作',
    '涨停', '大涨', '盈利', '扭亏', '超预期', '增持', '回购',
    '分红', '送转', '签约', '投产', '获批', '放量', '领涨',
    '龙头', '白马', '绩优', '朝阳', '景气', '反转'
]

# 负面关键词
NEGATIVE_KEYWORDS = [
    '下滑', '亏损', '违规', '处罚', '风险', '下跌', '减持',
    '跌停', '暴跌', '利空', '炸板', 'st', '退市', '立案',
    '调查', '警示', '冻结', '质押', '担保', '商誉', '减值',
    '预警', '预亏', 'st', '戴帽', '立案', '调查', '召回'
]
