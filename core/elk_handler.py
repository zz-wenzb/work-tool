# core/elk_handler.py
"""
ELK 日志查询处理模块
基于 Kibana API 实现日志查询
支持 Cookie 持久化缓存，自动检测过期并重新登录
"""

import json
import logging
import requests
import pickle
import os
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

# ============================================================
# 配置区域
# ============================================================

KIBANA_HOST = "http://devops.zhongbaozhiyun.com"

# Cookie 缓存文件
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "cache")
COOKIE_FILE = os.path.join(CACHE_DIR, "kibana_session.pkl")

# 支持的环境列表
ELK_ENVIRONMENTS = ["dev", "test", "uat", "prod"]

# 环境对应的索引前缀
ENV_INDEX_PREFIX = {
    "prod": ["lorry-prod", "wh-prod"],
    "test": ["lorry-test", "baoqi-test"],
    "uat": ["lorry-uat", "baoqi-uat"],
    "dev": ["lorry-dev", "baoqi-dev"],
}

# ============================================================
# 服务名称映射（完整列表）
# ============================================================

# 用户输入的简称 -> 实际的 k8s app 名称
ELK_SERVICE_MAPPING = {
    # ==================== 网关/路由层 ====================
    "gateway-app": "gateway-app",
    "gateway-platform": "gateway-platform",
    "gateway-shipper": "gateway-shipper",
    "gateway-mp": "gateway-mp",
    "gateway-openapi": "gateway-openapi",
    "gateway-web-energy": "gateway-web-energy",
    "gateway-web": "gateway-web",
    "gateway-sap": "gateway-sap",
    "lorry-msp-gateway": "lorry-msp-gateway",

    # ==================== 认证/授权 ====================
    "auth-server": "auth-server",
    "ums-auth": "ums-auth",
    "lorry-msp-auth": "lorry-msp-auth",

    # ==================== 用户/员工 ====================
    "user-server": "user-server",
    "lorry-msp-user": "lorry-msp-user",
    "lorry-msp-employee": "lorry-msp-employee",
    "report-api-user": "report-api-user",

    # ==================== TMS 运输管理系统 ====================
    "tms-central": "tms-central",
    "tms-vehicle-job": "tms-vehicle-job",
    "tms-contract-job": "tms-contract-job",
    "tms-api-web": "tms-api-web",

    # ==================== OAS 运营管理系统 ====================
    "oas-central": "oas-central",
    "oas-mp-driver": "oas-mp-driver",
    "oas-flow": "oas-flow",
    "oas-revert": "oas-revert",
    "oas-api-web": "oas-api-web",
    "oas-report": "oas-report",
    "oas-mp-order": "oas-mp-order",
    "mq-consumer-oas": "mq-consumer-oas",
    "canal-oas": "canal-oas",

    # ==================== Lorry 货车业务 ====================
    "lorry-xxl-job": "lorry-xxl-job",
    "lorry-msp-data-warehouse-service": "lorry-msp-data-warehouse-service",
    "lorry-msp-order-service": "lorry-msp-order-service",
    "lorry-msp-wechat-robot": "lorry-msp-wechat-robot",
    "lorry-msp-job": "lorry-msp-job",
    "lorry-msp-robot-core": "lorry-msp-robot-core",
    "lorry-msp-file": "lorry-msp-file",
    "lorry-msp-web": "lorry-msp-web",
    "lorry-msp-app-driver": "lorry-msp-app-driver",
    "lorry-msp-message": "lorry-msp-message",
    "lorry-msp-payment": "lorry-msp-payment",
    "lorry-msp-marketing": "lorry-msp-marketing",

    # ==================== 推荐系统 ====================
    "recommend-query": "recommend-query",
    "recommend-service": "recommend-service",
    "recommend-job": "recommend-job",

    # ==================== 货物/货运 ====================
    "cargo-sync": "cargo-sync",
    "cargo-posting": "cargo-posting",

    # ==================== 优惠券 ====================
    "coupon-service": "coupon-service",

    # ==================== 埋点 ====================
    "track-server": "track-server",

    # ==================== 支付/结算 ====================
    "pay-central": "pay-central",
    "payment-account": "payment-account",
    "pay-risk-central": "pay-risk-central",
    "pay-bank-central": "pay-bank-central",
    "payment-transaction-job": "payment-transaction-job",
    "pay-oas-api-web": "pay-oas-api-web",
    "pay-job-ccb": "pay-job-ccb",
    "pos-payment-job": "pos-payment-job",
    "pos-settle-job": "pos-settle-job",
    "pay-oas-api-driver": "pay-oas-api-driver",
    "pay-oas-central": "pay-oas-central",
    "mq-consumer-pay": "mq-consumer-pay",
    "data-center-pay": "data-center-pay",

    # ==================== 能源业务 ====================
    "newenergy-supplier-web": "newenergy-supplier-web",
    "energy-supplier-web": "energy-supplier-web",
    "energy-api-web": "energy-api-web",
    "energy-job-web": "energy-job-web",
    "newenergy-api-web": "newenergy-api-web",
    "gateway-web-energy": "gateway-web-energy",
    "fuel-api-web": "fuel-api-web",

    # ==================== 基础设施 ====================
    "infrastructure-contract": "infrastructure-contract",
    "capacity": "capacity",
    "config-server": "config-server",
    "auth-server": "auth-server",

    # ==================== 文件服务 ====================
    "file-web": "file-web",

    # ==================== 风控/风险 ====================
    "risk": "risk",
    "risk-control": "risk-control",

    # ==================== 司机服务 ====================
    "driver-service": "driver-service",
    "driver-search-service": "driver-search-service",
    "trade-driver-biz": "trade-driver-biz",
    "trade-driver": "trade-driver",

    # ==================== 交易/订单 ====================
    "trade-search-canal": "trade-search-canal",
    "trade-search": "trade-search",
    "trade-biz": "trade-biz",
    "oms-order": "oms-order",

    # ==================== 车道/线路 ====================
    "lane-dot-producer": "lane-dot-producer",
    "lane-dot-consumer": "lane-dot-consumer",
    "lane-track-api": "lane-track-api",

    # ==================== API/开放平台 ====================
    "md-api": "md-api",
    "mu-api": "mu-api",
    "sp-api": "sp-api",
    "openapi-oas-web": "openapi-oas-web",
    "openapi-callback-job": "openapi-callback-job",
    "openapi-callback": "openapi-callback",
    "openapi-api": "openapi-api",
    "openapi-pos-web": "openapi-pos-web",
    "openapi-v2-callback": "openapi-v2-callback",
    "pub-api-config": "pub-api-config",
    "tap-map-api": "tap-map-api",
    "fds-api-feeclouds": "fds-api-feeclouds",
    "css-api-ticket": "css-api-ticket",
    "css-api-web": "css-api-web",
    "msg-api-web": "msg-api-web",
    "debang-api-business": "debang-api-business",
    "finance-api-jilin": "finance-api-jilin",
    "statistics-oas-web": "statistics-oas-web",
    "datareport-api-web": "datareport-api-web",
    "port-tms-web": "port-tms-web",
    "tms-api-web": "tms-api-web",
    "quality-service-web": "quality-service-web",
    "autoins-installment-web": "autoins-installment-web",

    # ==================== MQ 消息队列 ====================
    "mq-consumer-ma": "mq-consumer-ma",
    "mq-consumer-pay": "mq-consumer-pay",
    "mq-consumer-css": "mq-consumer-css",
    "zhongbao-mq-default-producer": "zhongbao-mq-default-producer",

    # ==================== Canal 数据同步 ====================
    "canal-biz": "canal-biz",
    "canal-oas": "canal-oas",
    "erp-canal": "erp-canal",
    "trade-search-canal": "trade-search-canal",

    # ==================== ERP 企业资源计划 ====================
    "erp-doc": "erp-doc",
    "erp-sys": "erp-sys",

    # ==================== 保险 ====================
    "insurance-platform-server": "insurance-platform-server",
    "baoqi-notice-middle": "baoqi-notice-middle",

    # ==================== 中保 ====================
    "zhongbao-customer-web": "zhongbao-customer-web",

    # ==================== 其他 ====================
    "log": "log",
    "obs-engine": "obs-engine",
    "merchant": "merchant",
    "aiprompt-service-web": "aiprompt-service-web",
    "etc-invoice-api": "etc-invoice-api",
    "oils-backend": "oils-backend",
    "tap-logs-consumer": "tap-logs-consumer",
    "robot-service": "robot-service",
}

# 服务名称反向映射（用于搜索）
_SERVICE_ALIAS_MAP = {}
_SERVICE_FULL_NAME_MAP = {}

for alias, full_name in ELK_SERVICE_MAPPING.items():
    _SERVICE_ALIAS_MAP[alias] = full_name
    if full_name not in _SERVICE_FULL_NAME_MAP:
        _SERVICE_FULL_NAME_MAP[full_name] = []
    _SERVICE_FULL_NAME_MAP[full_name].append(alias)

# ============================================================
# 默认配置
# ============================================================

DEFAULT_QUERY_CONFIG = {
    "minutes": 30,
    "env": "test",
    "size": 100,
    "max_results": 500
}

# ============================================================
# Cookie 和认证配置
# ============================================================

HEADERS = {
    "kbn-xsrf": "kibana",
    "Content-Type": "application/json"
}

CREDENTIALS = {
    "username": "elastic",
    "password": "baoqi0411"
}


# ============================================================
# Kibana 认证管理器
# ============================================================

class KibanaAuthManager:
    """
    Kibana 认证管理器
    - 单例模式
    - Cookie 持久化到本地文件
    - 自动检测过期并重新登录
    """
    _instance = None
    _session: Optional[requests.Session] = None
    _last_used: float = 0
    _is_logged_in: bool = False
    _logging_in: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if not hasattr(self, '_initialized') or not self._initialized:
            self._initialized = True
            self._init_session()

    def _init_session(self):
        """初始化或加载缓存的会话"""
        self._session = requests.Session()
        self._session.headers.update(HEADERS)

        os.makedirs(CACHE_DIR, exist_ok=True)

        if os.path.exists(COOKIE_FILE):
            try:
                with open(COOKIE_FILE, "rb") as f:
                    cached_data = pickle.load(f)
                    if cached_data.get('cookies') and cached_data.get('timestamp', 0) > time.time() - 1800:
                        self._session.cookies.update(cached_data['cookies'])
                        self._last_used = time.time()
                        self._is_logged_in = True
                        logger.info("✅ 从缓存加载 Kibana 会话成功")
                        return
                    else:
                        logger.info("⏰ 缓存的 Kibana Cookie 已过期，将重新登录")
                        os.remove(COOKIE_FILE)
            except Exception as e:
                logger.warning(f"加载缓存会话失败: {e}")
                if os.path.exists(COOKIE_FILE):
                    os.remove(COOKIE_FILE)

        self._do_login()

    def _do_login(self) -> bool:
        """执行登录操作并保存 Cookie"""
        logger.info("🔐 正在登录 Kibana...")

        url = f"{KIBANA_HOST}/kibana/internal/security/login"

        payload = {
            "providerType": "basic",
            "providerName": "basic",
            "currentURL": f"{KIBANA_HOST}/kibana/login?msg=LOGGED_OUT",
            "params": CREDENTIALS
        }

        try:
            response = self._session.post(url, json=payload, timeout=10)

            if response.status_code == 200 and self._session.cookies:
                self._last_used = time.time()
                self._is_logged_in = True

                try:
                    os.makedirs(CACHE_DIR, exist_ok=True)
                    cache_data = {
                        'cookies': dict(self._session.cookies),
                        'timestamp': time.time()
                    }
                    with open(COOKIE_FILE, "wb") as f:
                        pickle.dump(cache_data, f)
                    logger.info("✅ Kibana 登录成功，Cookie 已保存到缓存")
                except Exception as e:
                    logger.warning(f"保存 Cookie 缓存失败: {e}")

                return True
            else:
                logger.error(f"❌ Kibana 登录失败: HTTP {response.status_code}")
                self._is_logged_in = False
                return False

        except Exception as e:
            logger.error(f"❌ Kibana 登录异常: {e}")
            self._is_logged_in = False
            return False

    def _test_cookie_valid(self) -> bool:
        """测试当前 cookie 是否有效"""
        if self._session is None:
            return False

        try:
            url = f"{KIBANA_HOST}/kibana/api/status"
            response = self._session.get(url, timeout=5)
            return response.status_code != 401
        except Exception as e:
            logger.warning(f"Cookie 验证异常: {e}")
            return False

    def ensure_login(self) -> bool:
        """确保已登录"""
        if self._is_logged_in and self._session is not None:
            if time.time() - self._last_used > 1500:
                logger.info("⏰ 会话可能已过期，重新验证...")
                self._is_logged_in = False

            if self._is_logged_in:
                if self._test_cookie_valid():
                    self._last_used = time.time()
                    return True
                else:
                    logger.warning("⚠️ Cookie 已过期，需要重新登录")
                    self._is_logged_in = False

        # 防止并发登录
        if self._logging_in:
            time.sleep(1)
            return self._is_logged_in

        self._logging_in = True
        try:
            if self._session is None:
                self._session = requests.Session()
                self._session.headers.update(HEADERS)

            result = self._do_login()
            self._is_logged_in = result
            return result
        finally:
            self._logging_in = False

    def get_session(self) -> requests.Session:
        """获取经过认证的 session"""
        self.ensure_login()
        return self._session

    def refresh_session(self) -> bool:
        """强制刷新 session"""
        self._is_logged_in = False
        if os.path.exists(COOKIE_FILE):
            os.remove(COOKIE_FILE)
        self._session = requests.Session()
        self._session.headers.update(HEADERS)
        return self.ensure_login()


# 全局认证管理器实例
_auth_manager = KibanaAuthManager()


# ============================================================
# 辅助函数
# ============================================================

def get_current_time() -> str:
    return datetime.now().strftime("%H:%M:%S")


def get_service_mapping(service: str) -> str:
    """获取服务映射名称"""
    return _SERVICE_ALIAS_MAP.get(service.lower(), service)


def search_services(keyword: str) -> List[Dict[str, str]]:
    """根据关键字搜索服务"""
    keyword = keyword.lower().strip()
    results = []

    for alias, full_name in ELK_SERVICE_MAPPING.items():
        if keyword in alias.lower() or keyword in full_name.lower():
            results.append({
                "alias": alias,
                "full_name": full_name
            })

    seen = set()
    unique_results = []
    for r in results:
        if r["full_name"] not in seen:
            seen.add(r["full_name"])
            unique_results.append(r)

    return unique_results


def build_index_path(env: str, date_list: List[str]) -> str:
    if env not in ENV_INDEX_PREFIX:
        env = "test"

    prefixes = ENV_INDEX_PREFIX[env]
    all_index_patterns = []

    for p in prefixes:
        for date_str in date_list:
            all_index_patterns.append(f"{p}-*-{date_str}-*")

    index_pattern = ",".join(all_index_patterns)
    return f"/{index_pattern}/_search"


def build_all_env_index_path(date_list: List[str]) -> str:
    """
    构建所有环境的索引路径（用于 traceId 查询）
    包含所有环境的所有索引前缀
    """
    all_prefixes = []
    for prefixes in ENV_INDEX_PREFIX.values():
        all_prefixes.extend(prefixes)

    # 去重
    all_prefixes = list(set(all_prefixes))

    all_index_patterns = []
    for p in all_prefixes:
        for date_str in date_list:
            all_index_patterns.append(f"{p}-*-{date_str}-*")

    index_pattern = ",".join(all_index_patterns)
    return f"/{index_pattern}/_search"


def parse_date_to_utc(date_str: str) -> tuple:
    date_formats = ["%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"]
    parsed_date = None

    for fmt in date_formats:
        try:
            parsed_date = datetime.strptime(date_str, fmt)
            break
        except ValueError:
            continue

    if not parsed_date:
        raise ValueError(f"不支持的日期格式: {date_str}")

    local_start = parsed_date.replace(hour=0, minute=0, second=0)
    local_end = parsed_date.replace(hour=23, minute=59, second=59)

    utc_start = local_start - timedelta(hours=8)
    utc_end = local_end - timedelta(hours=8)

    gte = utc_start.strftime("%Y-%m-%dT%H:%M:%S")
    lte = utc_end.strftime("%Y-%m-%dT%H:%M:%S")

    start_idx_date = utc_start.replace(hour=0, minute=0, second=0, microsecond=0)
    end_idx_date = utc_end.replace(hour=0, minute=0, second=0, microsecond=0)

    date_list = []
    current = start_idx_date
    while current <= end_idx_date:
        date_list.append(current.strftime("%Y.%m.%d"))
        current += timedelta(days=1)

    return gte, lte, date_list


def get_env_from_param(env_param: Optional[str]) -> str:
    if env_param and env_param.lower() in ELK_ENVIRONMENTS:
        return env_param.lower()
    return "test"


def _execute_search_with_retry(
        url: str,
        params: dict,
        payload: dict,
        max_retries: int = 2
) -> requests.Response:
    """
    执行搜索请求，如果遇到 401 自动重新登录并重试
    """
    for attempt in range(max_retries):
        try:
            session = _auth_manager.get_session()

            if attempt > 0:
                logger.info(f"[ELK] 第 {attempt + 1} 次尝试，刷新认证...")
                _auth_manager.refresh_session()
                session = _auth_manager.get_session()

            response = session.post(
                url,
                params=params,
                headers=HEADERS,
                json=payload,
                timeout=30
            )

            if response.status_code == 401:
                logger.warning(f"[ELK] 认证失败 (401)，准备重试... (尝试 {attempt + 1}/{max_retries})")
                _auth_manager._is_logged_in = False
                continue

            return response

        except Exception as e:
            logger.error(f"[ELK] 请求异常: {e}")
            if attempt == max_retries - 1:
                raise
            continue

    response = requests.Response()
    response.status_code = 500
    return response


# ============================================================
# 核心查询函数
# ============================================================

def search_logs(
        service: str,
        keyword: str = "",
        minutes: Optional[int] = None,
        env: str = "test",
        size: int = 100,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        query_date: Optional[str] = None,
        max_results: int = 500,
        all_env: bool = False
) -> List[Dict]:
    """
    搜索日志

    Args:
        all_env: 是否查询所有环境（用于 traceId 查询）
    """
    env = get_env_from_param(env)
    app_name = None
    if not all_env:
        app_name = get_service_mapping(service)

    date_list = []

    if query_date:
        gte, lte, date_list = parse_date_to_utc(query_date)
        logger.info(f"[ELK] 日期查询: {query_date} -> UTC: {gte} ~ {lte}")

    elif start_time and end_time:
        try:
            local_start = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
            local_end = datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")

            utc_start = local_start - timedelta(hours=8)
            utc_end = local_end - timedelta(hours=8)

            gte = utc_start.strftime("%Y-%m-%dT%H:%M:%S")
            lte = utc_end.strftime("%Y-%m-%dT%H:%M:%S")

            start_date = utc_start.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = utc_end.replace(hour=0, minute=0, second=0, microsecond=0)

            current = start_date
            while current <= end_date:
                date_list.append(current.strftime("%Y.%m.%d"))
                current += timedelta(days=1)

        except ValueError as e:
            logger.error(f"[ELK] 时间解析失败: {e}")
            return []
    else:
        minutes = minutes or DEFAULT_QUERY_CONFIG['minutes']
        gte = f"now-{minutes}m"
        lte = "now"
        date_list = [datetime.utcnow().strftime("%Y.%m.%d")]
        logger.info(f"[ELK] 时间查询: 最近 {minutes} 分钟")

    if not date_list:
        date_list = [datetime.utcnow().strftime("%Y.%m.%d")]

    # 构建索引路径
    if all_env:
        es_path = build_all_env_index_path(date_list)
        logger.info(f"[ELK] 索引 (所有环境): {es_path}")
    else:
        es_path = build_index_path(env, date_list)
        logger.info(f"[ELK] 索引: {es_path}")

    filters = [
        {"range": {"@timestamp": {"gte": gte, "lte": lte}}}
    ]

    # 只有非 all_env 模式才添加服务过滤
    if app_name and not all_env:
        filters.append({"term": {"kubernetes.labels.app.keyword": app_name}})

    if keyword:
        filters.append({"match_phrase": {"message": keyword}})

    page_size = min(100, size)
    payload = {
        "size": page_size,
        "query": {
            "bool": {
                "filter": filters
            }
        },
        "sort": [
            {"@timestamp": {"order": "asc"}},
            {"_id": {"order": "asc"}}
        ]
    }

    params = {"path": es_path, "method": "GET"}
    url = f"{KIBANA_HOST}/kibana/api/console/proxy"

    all_logs = []
    search_after = None
    total_fetched = 0

    try:
        while total_fetched < max_results:
            if search_after:
                payload['search_after'] = search_after

            response = _execute_search_with_retry(url, params, payload)

            if response.status_code != 200:
                logger.error(f"[ELK] 请求失败: {response.status_code}")
                break

            data = response.json()
            hits = data.get('hits', {}).get('hits', [])

            if not hits:
                break

            for hit in hits:
                if total_fetched >= max_results:
                    break

                source = hit.get('_source', {})

                timestamp = source.get('@timestamp', '')
                if timestamp:
                    timestamp = timestamp[:19].replace('T', ' ')

                message = source.get('message', '')

                labels = source.get('kubernetes', {}).get('labels', {})
                service_name = labels.get('app', labels.get('run', ''))

                # 提取环境信息（从索引名中获取）
                index_name = hit.get('_index', '')
                env_from_index = "unknown"
                if "lorry-prod" in index_name or "wh-prod" in index_name:
                    env_from_index = "PROD"
                elif "lorry-test" in index_name or "baoqi-test" in index_name:
                    env_from_index = "TEST"
                elif "lorry-uat" in index_name or "baoqi-uat" in index_name:
                    env_from_index = "UAT"
                elif "lorry-dev" in index_name or "baoqi-dev" in index_name:
                    env_from_index = "DEV"

                log_entry = {
                    "timestamp": timestamp,
                    "service": service_name,
                    "message": message,
                    "level": source.get('level', 'INFO'),
                    "host": source.get('host', ''),
                    "env": env_from_index,
                    "index": index_name,
                }
                all_logs.append(log_entry)
                total_fetched += 1

            if len(hits) < page_size:
                break

            last_hit = hits[-1]
            sort_values = last_hit.get('sort', [])
            if sort_values:
                search_after = sort_values
            else:
                break

    except Exception as e:
        logger.error(f"[ELK] 查询异常: {e}")

    logger.info(f"[ELK] 查询完成: 共获取 {len(all_logs)} 条日志")
    return all_logs


# ============================================================
# 格式化输出
# ============================================================

def format_logs_output(logs: List[Dict], limit: int = 50, keyword: str = "", show_env: bool = False) -> str:
    if not logs:
        return "📭 未找到匹配的日志"

    total = len(logs)
    show_count = min(limit, total)

    output_lines = []
    output_lines.append(f"📋 共找到 {total} 条日志，显示前 {show_count} 条：")
    output_lines.append("=" * 70)

    env_icons = {
        "PROD": "🔴",
        "TEST": "🟢",
        "UAT": "🟡",
        "DEV": "🔵",
        "unknown": "⚪"
    }

    for i, log in enumerate(logs[:show_count]):
        timestamp = log.get("timestamp", "")
        level = log.get("level", "INFO")
        service = log.get("service", "")
        message = log.get("message", "")
        env = log.get("env", "unknown")

        if keyword and keyword in message:
            message = message.replace(keyword, f"**{keyword}**")

        if len(message) > 300:
            message = message[:300] + "..."

        level_icon = "ℹ️"
        if "ERROR" in level.upper():
            level_icon = "❌"
        elif "WARN" in level.upper():
            level_icon = "⚠️"
        elif "DEBUG" in level.upper():
            level_icon = "🔍"

        env_icon = env_icons.get(env, "⚪")

        if show_env:
            output_lines.append(f"[{timestamp}] [{env_icon}{env}] [{level_icon}{level}] [{service}] {message}")
        else:
            output_lines.append(f"[{timestamp}] [{level_icon}{level}] [{service}] {message}")

    return "\n".join(output_lines)


def format_services_output(services: List[Dict[str, str]]) -> str:
    """格式化服务列表输出"""
    if not services:
        return "📭 未找到匹配的服务"

    output_lines = []
    output_lines.append(f"📋 找到 {len(services)} 个匹配的服务：")
    output_lines.append("=" * 50)

    for svc in services:
        output_lines.append(f"  {svc['alias']} -> {svc['full_name']}")

    return "\n".join(output_lines)


# ============================================================
# 命令解析
# ============================================================

def parse_elk_command(content: str) -> Dict[str, Any]:
    """解析 ELK 命令参数"""
    parts = content.split()
    if not parts:
        return {'valid': False, 'error': '空命令'}

    cmd = parts[0]
    result = {
        'cmd': cmd,
        'valid': False,
        'error': None,
        'service': None,
        'keyword': None,
        'minutes': DEFAULT_QUERY_CONFIG['minutes'],
        'env': DEFAULT_QUERY_CONFIG['env'],
        'date': None,
        'search_keyword': None,
        'trace_id': None,
    }

    if cmd == '/elk':
        if len(parts) < 3:
            result['error'] = f'用法: {cmd} <服务> <关键字> [分钟] [环境]\n示例: /elk tms error 30 test'
            return result

        result['service'] = parts[1]
        result['keyword'] = parts[2]

        idx = 3
        if idx < len(parts) and parts[idx].isdigit():
            result['minutes'] = int(parts[idx])
            idx += 1

        if idx < len(parts) and parts[idx].lower() in ELK_ENVIRONMENTS:
            result['env'] = parts[idx].lower()
            idx += 1

        result['valid'] = True

    elif cmd == '/elk-date':
        if len(parts) < 4:
            result[
                'error'] = f'用法: {cmd} <服务> <关键字> <日期> [环境]\n示例: /elk-date order timeout 2026-07-24 test'
            return result

        result['service'] = parts[1]
        result['keyword'] = parts[2]
        result['date'] = parts[3]

        idx = 4
        if idx < len(parts) and parts[idx].lower() in ELK_ENVIRONMENTS:
            result['env'] = parts[idx].lower()
            idx += 1

        result['valid'] = True

    elif cmd == '/elk-services':
        if len(parts) < 2:
            result['error'] = f'用法: {cmd} <关键字>\n示例: /elk-services gateway'
            return result

        result['search_keyword'] = parts[1]
        result['valid'] = True

    elif cmd == '/elk-trace':
        # /elk-trace <traceId> [minutes] [env]
        # 默认：30分钟，查所有环境
        if len(parts) < 2:
            result[
                'error'] = f'用法: {cmd} <traceId> [分钟] [环境]\n示例: /elk-trace abc123\n示例: /elk-trace abc123 60 test'
            return result

        result['trace_id'] = parts[1]
        result['keyword'] = parts[1]

        idx = 2
        # 解析分钟数（可选）
        if idx < len(parts) and parts[idx].isdigit():
            result['minutes'] = int(parts[idx])
            idx += 1

        # 解析环境（可选），默认 None 表示查所有环境
        if idx < len(parts) and parts[idx].lower() in ELK_ENVIRONMENTS:
            result['env'] = parts[idx].lower()
        else:
            result['env'] = None  # None 表示查询所有环境

        result['valid'] = True

    else:
        result['error'] = f'未知命令: {cmd}'

    return result


# ============================================================
# WebSocket 命令处理函数
# ============================================================

ELK_COMMANDS = [
    "/elk",
    "/elk-date",
    "/elk-services",
    "/elk-trace",
]

ELK_HELP = """
  /elk <服务> <关键字> [分钟] [环境]
    查询最近 N 分钟的日志
    示例: /elk tms error 30 test

  /elk-date <服务> <关键字> <日期> [环境]
    查询指定日期的日志
    示例: /elk-date order timeout 2026-07-24 test

  /elk-services <关键字>
    搜索匹配的服务名称
    示例: /elk-services gateway

  /elk-trace <traceId> [分钟] [环境]
    根据 traceId 查询日志（默认查询所有环境，30分钟）
    示例: /elk-trace abc123               # 查所有环境，最近30分钟
    示例: /elk-trace abc123 60            # 查所有环境，最近60分钟
    示例: /elk-trace abc123 60 test       # 只查 test 环境，最近60分钟
    示例: /elk-trace abc123 test          # 只查 test 环境，最近30分钟

  环境: prod, test, uat (默认 test)
  服务列表: 使用 /elk-services 搜索查看
"""


async def handle_elk_command(websocket, content: str, cmd: str) -> bool:
    """处理 ELK 相关命令"""
    params = parse_elk_command(content)

    if not params.get('valid'):
        error_msg = params.get('error', '参数错误')
        await websocket.send(json.dumps({
            "type": "error",
            "content": f"❌ {error_msg}",
            "time": get_current_time()
        }))
        return True

    cmd_type = params['cmd']

    if cmd_type == '/elk':
        await handle_elk_search(websocket, params)
    elif cmd_type == '/elk-date':
        await handle_elk_date_search(websocket, params)
    elif cmd_type == '/elk-services':
        await handle_elk_services(websocket, params)
    elif cmd_type == '/elk-trace':
        await handle_elk_trace(websocket, params)
    else:
        await websocket.send(json.dumps({
            "type": "error",
            "content": f"❌ 未知 ELK 命令: {cmd_type}",
            "time": get_current_time()
        }))

    return True


async def handle_elk_search(websocket, params: Dict):
    """处理 /elk 命令"""
    service = params['service']
    keyword = params['keyword']
    minutes = params['minutes']
    env = params['env']

    try:
        await websocket.send(json.dumps({
            "type": "system",
            "content": f"⏳ 正在查询: 服务={service}, 关键字='{keyword}', 最近{minutes}分钟, 环境={env} ...",
            "time": get_current_time()
        }))

        logs = search_logs(
            service=service,
            keyword=keyword,
            minutes=minutes,
            env=env,
            size=100,
            max_results=500
        )

        output = format_logs_output(logs, limit=50, keyword=keyword)

        summary = f"📊 查询结果: 服务={service}, 关键字='{keyword}', 最近{minutes}分钟, 环境={env}\n"

        if len(logs) > 50:
            await websocket.send(json.dumps({
                "type": "system",
                "content": summary + f"共找到 {len(logs)} 条日志，分批显示...",
                "time": get_current_time()
            }))
            for i in range(0, len(logs), 30):
                batch = logs[i:i + 30]
                batch_output = format_logs_output(batch, limit=30, keyword=keyword)
                await websocket.send(json.dumps({
                    "type": "system",
                    "content": batch_output,
                    "time": get_current_time()
                }))
        else:
            await websocket.send(json.dumps({
                "type": "system",
                "content": summary + output,
                "time": get_current_time()
            }))

    except Exception as e:
        logger.error(f"[ELK] 查询失败: {e}")
        await websocket.send(json.dumps({
            "type": "error",
            "content": f"❌ 查询失败: {str(e)}",
            "time": get_current_time()
        }))


async def handle_elk_date_search(websocket, params: Dict):
    """处理 /elk-date 命令"""
    service = params['service']
    keyword = params['keyword']
    date = params['date']
    env = params['env']

    try:
        await websocket.send(json.dumps({
            "type": "system",
            "content": f"⏳ 正在查询: 服务={service}, 关键字='{keyword}', 日期={date}, 环境={env} ...",
            "time": get_current_time()
        }))

        logs = search_logs(
            service=service,
            keyword=keyword,
            query_date=date,
            env=env,
            size=100,
            max_results=500
        )

        output = format_logs_output(logs, limit=50, keyword=keyword)

        summary = f"📊 查询结果: 服务={service}, 关键字='{keyword}', 日期={date}, 环境={env}\n"

        if len(logs) > 50:
            await websocket.send(json.dumps({
                "type": "system",
                "content": summary + f"共找到 {len(logs)} 条日志，分批显示...",
                "time": get_current_time()
            }))
            for i in range(0, len(logs), 30):
                batch = logs[i:i + 30]
                batch_output = format_logs_output(batch, limit=30, keyword=keyword)
                await websocket.send(json.dumps({
                    "type": "system",
                    "content": batch_output,
                    "time": get_current_time()
                }))
        else:
            await websocket.send(json.dumps({
                "type": "system",
                "content": summary + output,
                "time": get_current_time()
            }))

    except ValueError as e:
        await websocket.send(json.dumps({
            "type": "error",
            "content": f"❌ 日期格式错误: {date}，支持格式: YYYY-MM-DD, YYYY/MM/DD, YYYYMMDD",
            "time": get_current_time()
        }))
    except Exception as e:
        logger.error(f"[ELK] 查询失败: {e}")
        await websocket.send(json.dumps({
            "type": "error",
            "content": f"❌ 查询失败: {str(e)}",
            "time": get_current_time()
        }))


async def handle_elk_services(websocket, params: Dict):
    """处理 /elk-services 命令 - 搜索服务"""
    keyword = params['search_keyword']

    try:
        services = search_services(keyword)
        output = format_services_output(services)

        await websocket.send(json.dumps({
            "type": "system",
            "content": f"🔍 服务搜索: '{keyword}'\n\n{output}",
            "time": get_current_time()
        }))

    except Exception as e:
        logger.error(f"[ELK] 服务搜索失败: {e}")
        await websocket.send(json.dumps({
            "type": "error",
            "content": f"❌ 搜索失败: {str(e)}",
            "time": get_current_time()
        }))


async def handle_elk_trace(websocket, params: Dict):
    """处理 /elk-trace 命令 - 根据 traceId 查询日志（默认所有环境，30分钟）"""
    trace_id = params['trace_id']
    minutes = params['minutes']
    env = params.get('env')

    # 判断是否查询所有环境
    all_env = env is None

    try:
        if all_env:
            await websocket.send(json.dumps({
                "type": "system",
                "content": f"⏳ 正在查询 traceId: '{trace_id}'，最近{minutes}分钟，所有环境 ...",
                "time": get_current_time()
            }))
        else:
            await websocket.send(json.dumps({
                "type": "system",
                "content": f"⏳ 正在查询 traceId: '{trace_id}'，最近{minutes}分钟，环境={env} ...",
                "time": get_current_time()
            }))

        # 执行查询
        logs = search_logs(
            service="",
            keyword=trace_id,
            minutes=minutes,
            env=env or "test",
            size=100,
            max_results=1000,
            all_env=all_env
        )

        # 按环境分组统计
        env_stats = {}
        for log in logs:
            env_name = log.get('env', 'unknown')
            env_stats[env_name] = env_stats.get(env_name, 0) + 1

        stats_str = " | ".join([f"{k}: {v}条" for k, v in env_stats.items()]) if env_stats else "无数据"

        output = format_logs_output(logs, limit=50, keyword=trace_id, show_env=True)

        if all_env:
            summary = f"🔍 traceId: '{trace_id}'，最近{minutes}分钟，所有环境\n"
        else:
            summary = f"🔍 traceId: '{trace_id}'，最近{minutes}分钟，环境={env}\n"
        summary += f"📊 分布: {stats_str}\n"

        if len(logs) > 50:
            await websocket.send(json.dumps({
                "type": "system",
                "content": summary + f"共找到 {len(logs)} 条日志，分批显示...",
                "time": get_current_time()
            }))
            for i in range(0, len(logs), 30):
                batch = logs[i:i + 30]
                batch_output = format_logs_output(batch, limit=30, keyword=trace_id, show_env=True)
                await websocket.send(json.dumps({
                    "type": "system",
                    "content": batch_output,
                    "time": get_current_time()
                }))
        else:
            await websocket.send(json.dumps({
                "type": "system",
                "content": summary + output,
                "time": get_current_time()
            }))

    except Exception as e:
        logger.error(f"[ELK] traceId 查询失败: {e}")
        await websocket.send(json.dumps({
            "type": "error",
            "content": f"❌ traceId 查询失败: {str(e)}",
            "time": get_current_time()
        }))
