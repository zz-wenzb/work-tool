# core/elk_handler.py
"""
ELK 日志查询处理模块
基于 Kibana API 实现日志查询
"""

import json
import logging
import requests
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

# ============================================================
# 配置区域
# ============================================================

KIBANA_HOST = "http://devops.zhongbaozhiyun.com"

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
    # 核心服务
    "tms": "tms-central",
    "oas": "oas-central",
    "lorry": "lorry-msp-gateway",
    "order": "lorry-msp-order-service",
    "marketing": "lorry-msp-marketing",
    "cargo": "cargo-sync",
    "gateway": "gateway-app",
    "auth": "ums-auth",
    "user": "lorry-msp-user",
    "payment": "lorry-msp-payment",
    "file": "lorry-msp-file",
    "message": "lorry-msp-message",
    "recommend": "recommend-query",
    "trade": "trade-search",
    "coupon": "coupon-service",
    "driver": "lorry-msp-app-driver",
    "employee": "lorry-msp-employee",
    "number": "lorry-msp-number-generator",

    # 网关相关
    "gateway-app": "gateway-app",
    "gateway-openapi": "gateway-openapi",
    "gateway-shipper": "gateway-shipper",
    "gateway-web": "gateway-web",
    "gateway-web-energy": "gateway-web-energy",
    "gateway-platform": "gateway-platform",
    "gateway-mp": "gateway-mp",
    "gateway-sap": "gateway-sap",

    # 网货相关
    "cargo-sync": "cargo-sync",
    "cargo-posting": "cargo-posting",

    # 推荐相关
    "recommend-job": "recommend-job",
    "recommend-query": "recommend-query",
    "recommend-service": "recommend-service",

    # OAS 相关
    "oas-central": "oas-central",
    "oas-revert": "oas-revert",
    "oas-flow": "oas-flow",
    "oas-report": "oas-report",
    "oas-settle-job": "oas-settle-job",
    "oas-api-web": "oas-api-web",
    "oas-api-rescue": "oas-api-rescue",
    "oas-mp-order": "oas-mp-order",
    "oas-mp-driver": "oas-mp-driver",
    "oas-mp-agent": "oas-mp-agent",
    "oas-thirdpayment-job": "oas-thirdpayment-job",
    "oas-deppon-track-push": "oas-deppon-track-push",

    # TMS 相关
    "tms-central": "tms-central",
    "tms-api-web": "tms-api-web",
    "tms-vehicle-job": "tms-vehicle-job",
    "tms-auth": "tms-auth",

    # MQ 相关
    "mq-consumer-oas": "mq-consumer-oas",
    "zhongbao-mq-default-producer-nengtou": "zhongbao-mq-default-producer-nengtou",

    # 其他服务
    "pub-api-config": "pub-api-config",
    "infrastructure-contract": "infrastructure-contract",
    "oils-backend": "oils-backend",
    "auth-server": "auth-server",
    "risk-control": "risk-control",
    "pos-payment-job": "pos-payment-job",
    "pay-central": "pay-central",
    "user-server": "user-server",
    "energy-api-web": "energy-api-web",
    "erp-doc": "erp-doc",
    "upgrade-record": "upgrade-record",
    "autoins-installment-web": "autoins-installment-web",
    "erp-sys": "erp-sys",
    "port-tms-web": "port-tms-web",
    "xxl-job": "xxl-job",
    "lane-track-api": "lane-track-api",
    "energy-supplier-web": "energy-supplier-web",
    "baoqi-notice-middle": "baoqi-notice-middle",
    "pay-risk-central": "pay-risk-central",
    "energy-job-web": "energy-job-web",
    "openapi-oas-web": "openapi-oas-web",
    "lane-dot-consumer": "lane-dot-consumer",
    "trade-driver-biz": "trade-driver-biz",
    "crm-api-web": "crm-api-web",
    "openapi-callback-job": "openapi-callback-job",
    "pos-settle-job": "pos-settle-job",
    "sap-api-web": "sap-api-web",
    "trade-waybill-shipper-posting": "trade-waybill-shipper-posting",
    "mts-manage": "mts-manage",
    "etc-api-web": "etc-api-web",
    "newenergy-api-web": "newenergy-api-web",
    "openapi-pos-web": "openapi-pos-web",
    "openapi-oas": "openapi-oas",
    "css-api-ticket": "css-api-ticket",
    "openapi-dv": "openapi-dv",
    "newenergy-supplier-web": "newenergy-supplier-web",
    "lane-dot-producer": "lane-dot-producer",
    "fuel-api-web": "fuel-api-web",
    "capacity-api-web": "capacity-api-web",
    "fds-invoice-api": "fds-invoice-api",
    "report-api-user": "report-api-user",
    "finance-api-nanjing": "finance-api-nanjing",
    "pay-job-ccb": "pay-job-ccb",
    "pay-api-web": "pay-api-web",
    "pmts-api-web": "pmts-api-web",
    "zhongbao-customer-web": "zhongbao-customer-web",
    "pay-job-ceb": "pay-job-ceb",
    "wms-server": "wms-server",
    "erp-integration-central": "erp-integration-central",
    "domain-order": "domain-order",
    "openapi-developer": "openapi-developer",
    "pay-job-jilin": "pay-job-jilin",
    "pay-oas-api-web": "pay-oas-api-web",
    "openapi-gateway": "openapi-gateway",
    "openapi-callback": "openapi-callback",
    "mts-shipper": "mts-shipper",
    "app-dv-api": "app-dv-api",
    "datareport-api-web": "datareport-api-web",
    "finance-api-jilin": "finance-api-jilin",
    "mu-api": "mu-api",
    "openapi-v2-callback": "openapi-v2-callback",
    "ums-api-web": "ums-api-web",
    "jiaotou-tms-server": "jiaotou-tms-server",
    "openapi-auth-web": "openapi-auth-web",
    "pay-oas-api-driver": "pay-oas-api-driver",
    "jiaotou-tms-carrier": "jiaotou-tms-carrier",
    "obs-engine": "obs-engine",
    "report-credit-stats": "report-credit-stats",
    "openapi-v2-sink-zhongbao": "openapi-v2-sink-zhongbao",
    "lane-track-handle-history": "lane-track-handle-history",
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

# 初始 Cookie（从你提供的脚本中提取）
COOKIES = {
    "sid": "Fe26.2**da33316f7e1ea4d79e21eec4e6a6f6f727052df41879cead2423b557da8f59df*SDKyquwRhqWhajhq6iSNWw*gxtQIsvOqS-GYBPwZoY9DtkIYon-1IUmxxxiqIScB0ugjzAUSZ9XenpCQ_DVIvOytcE_VgUdE-aec9LLo-7R8P_jPzQxsDXrcMVzeNxr88lOa7znulASm3RYeaMp2eou8ERNipBtZL2n-Zc2W2uz4DVOYzMMTWy-TtRs1zCgryUDOMlvlkavMfuBLJDn3FokGi3-tPlCUrc7SY7u010vnOxBOMqzHwlCM4c2qA4Qrs3QEyPHnbImuf8HD6iFY3U6**253439102b47e89232325b8d8d218c30b91a15a571a89664e3906f7aca7c9210*9gOsb7Ok5S48o9AfKx9VfDKzy_yD1V2VDQy2mvx57v8",
    "apt.uid": "AP-YFGMCGUNNIFB-2-1767687842794-95994121.0.2.6b933aba-006b-4c12-b4b5-a0ddc2adfcf4"
}

HEADERS = {
    "kbn-xsrf": "kibana",
    "Content-Type": "application/json"
}

CREDENTIALS = {
    "username": "elastic",
    "password": "baoqi0411"
}


# ============================================================
# 认证管理器（核心优化）
# ============================================================

class KibanaAuthManager:
    """
    Kibana 认证管理器
    - 单例模式
    - 懒加载登录
    - 自动检测 cookie 过期并重新登录
    - 线程安全
    """
    _instance = None
    _session = None
    _is_logged_in = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self._login_lock = False  # 简单的锁，防止并发登录

    def _do_login(self) -> bool:
        """
        执行登录操作
        """
        logger.info("[ELK] 正在登录 Kibana...")

        session = requests.Session()
        url = f"{KIBANA_HOST}/kibana/internal/security/login"

        payload = {
            "providerType": "basic",
            "providerName": "basic",
            "currentURL": f"{KIBANA_HOST}/kibana/login?msg=LOGGED_OUT",
            "params": CREDENTIALS
        }

        try:
            response = session.post(url, json=payload, headers=HEADERS, timeout=10)

            if response.status_code == 200 and session.cookies:
                # 更新全局 COOKIES
                for key, value in session.cookies.items():
                    COOKIES[key] = value

                # 更新 session
                if self._session is None:
                    self._session = requests.Session()
                else:
                    self._session.cookies.clear()
                self._session.cookies.update(COOKIES)

                self._is_logged_in = True
                logger.info("[ELK] ✅ 登录成功，Cookie 已保存")
                return True
            else:
                logger.error(f"[ELK] ❌ 登录失败: HTTP {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"[ELK] ❌ 登录异常: {e}")
            return False

    def ensure_login(self) -> bool:
        """
        确保已登录，如果未登录或 session 无效则登录
        """
        # 如果已经登录且 session 存在，直接返回
        if self._is_logged_in and self._session is not None:
            return True

        # 防止并发登录
        if self._login_lock:
            # 等待一小段时间后重试
            import time
            time.sleep(1)
            return self._is_logged_in

        self._login_lock = True
        try:
            # 如果 session 不存在，创建新的
            if self._session is None:
                self._session = requests.Session()
                # 先用已有的 cookie 初始化
                self._session.cookies.update(COOKIES)

            # 测试当前 cookie 是否有效
            if self._test_cookie_valid():
                self._is_logged_in = True
                return True

            # Cookie 无效，重新登录
            logger.info("[ELK] Cookie 已过期，正在重新登录...")
            result = self._do_login()
            self._is_logged_in = result
            return result

        finally:
            self._login_lock = False

    def _test_cookie_valid(self) -> bool:
        """
        测试当前 cookie 是否有效
        发送一个简单请求验证
        """
        if self._session is None:
            return False

        try:
            # 尝试获取 Kibana 状态，验证 cookie 是否有效
            url = f"{KIBANA_HOST}/kibana/api/status"
            response = self._session.get(url, timeout=5)

            # 如果是 200 或 302，说明 cookie 有效
            # 如果是 401，说明 cookie 过期
            return response.status_code != 401

        except Exception as e:
            logger.warning(f"[ELK] Cookie 验证异常: {e}")
            return False

    def get_session(self) -> requests.Session:
        """
        获取经过认证的 session
        如果未登录，自动登录
        """
        self.ensure_login()
        return self._session

    def refresh_session(self) -> bool:
        """
        强制刷新 session（重新登录）
        """
        self._is_logged_in = False
        self._session = None
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
            # 获取认证 session（会自动登录）
            session = _auth_manager.get_session()

            # 如果是重试，强制刷新 session
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

            # 如果是 401，触发重试
            if response.status_code == 401:
                logger.warning(f"[ELK] 认证失败 (401)，准备重试... (尝试 {attempt + 1}/{max_retries})")
                # 标记 session 无效，下次会重新登录
                _auth_manager._is_logged_in = False
                continue

            return response

        except Exception as e:
            logger.error(f"[ELK] 请求异常: {e}")
            if attempt == max_retries - 1:
                raise
            continue

    # 所有重试都失败，返回一个空的错误响应
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
        max_results: int = 500
) -> List[Dict]:
    """搜索日志"""
    env = get_env_from_param(env)
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

    es_path = build_index_path(env, date_list)
    logger.info(f"[ELK] 索引: {es_path}")

    filters = [
        {"range": {"@timestamp": {"gte": gte, "lte": lte}}}
    ]

    if app_name:
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

            # 使用带重试的请求函数
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

                log_entry = {
                    "timestamp": timestamp,
                    "service": service_name,
                    "message": message,
                    "level": source.get('level', 'INFO'),
                    "host": source.get('host', ''),
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

def format_logs_output(logs: List[Dict], limit: int = 50, keyword: str = "") -> str:
    if not logs:
        return "📭 未找到匹配的日志"

    total = len(logs)
    show_count = min(limit, total)

    output_lines = []
    output_lines.append(f"📋 共找到 {total} 条日志，显示前 {show_count} 条：")
    output_lines.append("=" * 70)

    for i, log in enumerate(logs[:show_count]):
        timestamp = log.get("timestamp", "")
        level = log.get("level", "INFO")
        service = log.get("service", "")
        message = log.get("message", "")

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