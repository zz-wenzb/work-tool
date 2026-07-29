# core/archery_api.py
import requests
import pickle
import os
import logging
import time
from datetime import datetime
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# ================= 配置 =================
BASE_URL = "http://archery.zhongbaozhiyun.com:9123"
LOGIN_URL = f"{BASE_URL}/authenticate/"
QUERY_URL = f"{BASE_URL}/query/"
INSTANCE_LIST_URL = f"{BASE_URL}/group/user_all_instances/"
INSTANCE_RESOURCE_URL = f"{BASE_URL}/instance/instance_resource/"

LOGIN_DATA = {
    "username": "wenzhibin",
    "password": "Zbzy#2025"
}

COOKIE_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "cache", "archery_session.pkl")


# ================= 会话管理 =================
class ArcherySessionManager:
    _instance = None
    _session: Optional[requests.Session] = None
    _last_used: float = 0
    _is_valid: bool = False  # 会话有效标志

    def __new__(cls):
        if not cls._instance:
            cls._instance = super().__new__(cls)
            cls._instance._init_session()
        return cls._instance

    def _init_session(self):
        """初始化或加载缓存的会话"""
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest"
        })

        # 尝试加载缓存的 Cookie
        if os.path.exists(COOKIE_FILE):
            try:
                with open(COOKIE_FILE, "rb") as f:
                    cached_session = pickle.load(f)
                    if cached_session.cookies.get("csrftoken"):
                        # 复制 cookies 和必要的 headers
                        self._session.cookies.update(cached_session.cookies)
                        if 'X-CSRFToken' in cached_session.headers:
                            self._session.headers['X-CSRFToken'] = cached_session.headers['X-CSRFToken']
                        self._last_used = time.time()
                        # 验证会话是否真的有效
                        if self._validate_session():
                            self._is_valid = True
                            logger.info("✅ 从缓存加载 Archery 会话成功")
                            return
                        else:
                            logger.warning("⚠️ 缓存的会话无效，将重新登录")
            except Exception as e:
                logger.warning(f"加载缓存会话失败: {e}")
                if os.path.exists(COOKIE_FILE):
                    os.remove(COOKIE_FILE)

        # 执行登录
        self._login()

    def _validate_session(self) -> bool:
        """验证当前会话是否有效"""
        try:
            # 尝试访问首页，检查是否被重定向到登录页
            response = self._session.get(BASE_URL, timeout=5, allow_redirects=False)

            # 如果返回 302 重定向到登录页，说明会话无效
            if response.status_code == 302:
                location = response.headers.get('Location', '')
                if 'login' in location.lower():
                    logger.warning("会话已过期（重定向到登录页）")
                    return False

            # 如果返回 HTML 登录页
            content_type = response.headers.get('Content-Type', '')
            if 'text/html' in content_type and 'Login' in response.text:
                logger.warning("会话已过期（返回登录页）")
                return False

            return True
        except Exception as e:
            logger.warning(f"验证会话失败: {e}")
            return False

    def _login(self):
        """登录 Archery"""
        logger.info("正在登录 Archery...")
        try:
            # 创建新的 Session 实例（清除旧状态）
            self._session = requests.Session()
            self._session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest"
            })

            # 步骤1: 获取初始 CSRF Token
            logger.debug("获取初始 CSRF Token...")
            init_response = self._session.get(BASE_URL, timeout=10)
            initial_csrf = self._session.cookies.get("csrftoken", "")
            logger.debug(f"初始 CSRF Token: {initial_csrf[:20] if initial_csrf else 'None'}...")

            # 步骤2: 登录
            login_headers = {
                "X-CSRFToken": initial_csrf,
                "Referer": BASE_URL,
                "Content-Type": "application/x-www-form-urlencoded"
            }

            login_response = self._session.post(
                LOGIN_URL,
                data=LOGIN_DATA,
                headers=login_headers,
                timeout=10
            )

            if login_response.status_code == 200:
                # 验证登录是否成功（检查返回的是 JSON 还是 HTML）
                content_type = login_response.headers.get('Content-Type', '')
                if 'text/html' in content_type and 'Login' in login_response.text:
                    raise Exception("登录失败：返回登录页面，请检查用户名密码")

                # 获取新的 CSRF Token
                new_csrf = self._session.cookies.get("csrftoken", "")
                if new_csrf:
                    self._session.headers["X-CSRFToken"] = new_csrf
                    self._session.headers["Content-Type"] = "application/x-www-form-urlencoded"
                    self._session.headers["Referer"] = BASE_URL

                    self._last_used = time.time()
                    self._is_valid = True

                    # 保存会话到缓存
                    os.makedirs(os.path.dirname(COOKIE_FILE), exist_ok=True)
                    with open(COOKIE_FILE, "wb") as f:
                        pickle.dump(self._session, f)

                    logger.info("✅ Archery 登录成功")
                else:
                    raise Exception("登录后未获取到 CSRF Token")
            else:
                raise Exception(f"登录失败，状态码: {login_response.status_code}")

        except Exception as e:
            logger.error(f"Archery 登录失败: {e}")
            self._is_valid = False
            raise

    def refresh_session(self):
        """强制刷新会话（重新鉴权）"""
        logger.info("🔄 强制刷新 Archery 会话（重新鉴权）...")

        # 删除旧的缓存文件
        if os.path.exists(COOKIE_FILE):
            try:
                os.remove(COOKIE_FILE)
                logger.info("已删除旧会话缓存")
            except Exception as e:
                logger.warning(f"删除缓存文件失败: {e}")

        # 重置会话状态
        self._session = None
        self._is_valid = False
        self._last_used = 0

        # 重新登录
        self._login()

    def get_session(self) -> requests.Session:
        """获取会话，如果过期则自动重新鉴权"""
        # 检查是否需要刷新
        need_refresh = False

        # 1. 检查时间过期
        if time.time() - self._last_used > 1500:  # 25分钟
            logger.info("⏰ 会话时间已过期")
            need_refresh = True

        # 2. 检查会话是否有效
        if not need_refresh and not self._is_valid:
            logger.info("🔍 会话标记为无效")
            need_refresh = True

        # 3. 如果会话存在但可能无效，进行验证
        if not need_refresh and self._session:
            try:
                if not self._validate_session():
                    logger.warning("⚠️ 会话验证失败，需要重新鉴权")
                    need_refresh = True
            except Exception as e:
                logger.warning(f"会话验证异常: {e}")
                need_refresh = True

        # 如果需要刷新，执行重新鉴权
        if need_refresh:
            self.refresh_session()

        # 确保 CSRF Token 存在
        csrf_token = self._session.cookies.get("csrftoken")
        if csrf_token:
            self._session.headers["X-CSRFToken"] = csrf_token
            self._session.headers["Content-Type"] = "application/x-www-form-urlencoded"
            self._session.headers["Referer"] = BASE_URL
        else:
            logger.warning("⚠️ 未找到 CSRF Token，执行重新鉴权...")
            self.refresh_session()

        self._last_used = time.time()
        return self._session


# ================= 全局会话实例 =================
session_manager = ArcherySessionManager()


def get_session() -> requests.Session:
    """获取 Archery 会话"""
    return session_manager.get_session()


def force_reauthenticate():
    """
    强制重新鉴权（外部调用接口）
    用于手动重置会话
    """
    logger.info("🔐 执行强制重新鉴权...")
    session_manager.refresh_session()
    logger.info("✅ 重新鉴权完成")
    return session_manager._is_valid


def get_auth_status() -> dict:
    """
    获取当前鉴权状态
    """
    return {
        "is_valid": session_manager._is_valid,
        "last_used": datetime.fromtimestamp(session_manager._last_used).strftime(
            "%Y-%m-%d %H:%M:%S") if session_manager._last_used > 0 else "Never",
        "has_session": session_manager._session is not None,
        "has_csrf": bool(session_manager._session.cookies.get("csrftoken")) if session_manager._session else False
    }


# ================= Archery API 接口 =================
class ArcheryAPI:
    @staticmethod
    def execute_sql_query(instance_name: str, db_name: str, sql_content: str, limit_num: int = 100) -> Dict[str, Any]:
        """
        执行 SQL 查询，自动检测会话过期并重新鉴权
        """
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # 获取会话（会自动验证和刷新）
                session = get_session()

                # 确保请求头完整
                csrf_token = session.cookies.get("csrftoken")
                if csrf_token:
                    session.headers["X-CSRFToken"] = csrf_token
                    session.headers["Content-Type"] = "application/x-www-form-urlencoded"
                    session.headers["Referer"] = BASE_URL
                else:
                    # 如果没有 CSRF，强制重新鉴权
                    logger.warning("缺少 CSRF Token，强制重新鉴权")
                    session_manager.refresh_session()
                    session = get_session()
                    continue

                data = {
                    "instance_name": instance_name,
                    "db_name": db_name,
                    "schema_name": "",
                    "tb_name": "",
                    "sql_content": sql_content,
                    "limit_num": limit_num
                }

                response = session.post(QUERY_URL, data=data, timeout=30)

                # 检测会话过期
                content_type = response.headers.get('Content-Type', '')
                if 'text/html' in content_type or response.text.strip().startswith('<!DOCTYPE'):
                    logger.warning(f"⚠️ 返回 HTML 页面（会话过期），尝试重新鉴权 (尝试 {attempt + 1}/{max_retries})")
                    session_manager.refresh_session()
                    continue

                # 检测 403 权限问题
                if response.status_code == 403:
                    logger.warning(f"⚠️ 收到 403，会话可能过期，重新鉴权 (尝试 {attempt + 1}/{max_retries})")
                    session_manager.refresh_session()
                    continue

                # 解析响应
                return ArcheryParser.parse_sql_query(response)

            except requests.exceptions.Timeout:
                logger.error(f"请求超时 (尝试 {attempt + 1}/{max_retries})")
                if attempt == max_retries - 1:
                    return {"success": False, "error": "请求超时", "data": []}

            except Exception as e:
                logger.error(f"执行 SQL 查询失败 (尝试 {attempt + 1}): {e}")
                if attempt == max_retries - 1:
                    return {"success": False, "error": str(e), "data": []}

        return {"success": False, "error": "查询失败，已重试多次", "data": []}

    @staticmethod
    def get_user_instances(tag_code: str = "can_read") -> Dict[str, Any]:
        """获取用户有权限的实例列表"""
        max_retries = 2
        for attempt in range(max_retries):
            try:
                session = get_session()
                params = {"tag_codes[]": tag_code}
                response = session.get(INSTANCE_LIST_URL, params=params, timeout=30)

                # 检测会话过期
                content_type = response.headers.get('Content-Type', '')
                if 'text/html' in content_type or response.text.strip().startswith('<!DOCTYPE'):
                    logger.warning(f"⚠️ 返回 HTML 页面（会话过期），尝试重新鉴权")
                    session_manager.refresh_session()
                    continue

                if response.status_code == 403:
                    logger.warning("⚠️ 收到 403，会话可能过期，重新鉴权")
                    session_manager.refresh_session()
                    continue

                return ArcheryParser.parse_instances(response)
            except Exception as e:
                logger.error(f"获取实例列表失败 (尝试 {attempt + 1}): {e}")
                if attempt == max_retries - 1:
                    return {"success": False, "error": str(e), "data": []}
        return {"success": False, "error": "获取实例列表失败", "data": []}

    @staticmethod
    def get_instance_databases(instance_name: str) -> Dict[str, Any]:
        """获取实例下的数据库列表"""
        max_retries = 2
        for attempt in range(max_retries):
            try:
                session = get_session()
                params = {
                    "instance_name": instance_name,
                    "resource_type": "database"
                }
                response = session.get(INSTANCE_RESOURCE_URL, params=params, timeout=30)

                # 检测会话过期
                content_type = response.headers.get('Content-Type', '')
                if 'text/html' in content_type or response.text.strip().startswith('<!DOCTYPE'):
                    logger.warning(f"⚠️ 返回 HTML 页面（会话过期），尝试重新鉴权")
                    session_manager.refresh_session()
                    continue

                if response.status_code == 403:
                    logger.warning("⚠️ 收到 403，会话可能过期，重新鉴权")
                    session_manager.refresh_session()
                    continue

                return ArcheryParser.parse_instance_databases(response)
            except Exception as e:
                logger.error(f"获取数据库列表失败 (尝试 {attempt + 1}): {e}")
                if attempt == max_retries - 1:
                    return {"success": False, "error": str(e), "data": []}
        return {"success": False, "error": "获取数据库列表失败", "data": []}


# ================= 解析器 =================
class ArcheryParser:
    @staticmethod
    def parse_sql_query(response: requests.Response) -> Dict[str, Any]:
        """解析 SQL 查询结果"""
        logger.info(f"响应状态码: {response.status_code}")
        logger.info(f"响应头: {dict(response.headers)}")

        # 打印前500字符的原始响应用于调试
        raw_response = response.text[:500]
        logger.info(f"原始响应: {raw_response}")

        if response.status_code != 200:
            error_msg = f"HTTP {response.status_code}"
            if response.status_code == 403:
                error_msg = "会话已过期，请重新登录"
            elif response.status_code == 500:
                error_msg = "服务器内部错误，请检查 SQL 语句"
            # 检查是否是 HTML 响应
            if response.text and response.text.strip().startswith('<!DOCTYPE'):
                error_msg = "返回了HTML页面，可能会话已过期或需要重新登录"
            return {"success": False, "error": error_msg, "data": []}

        try:
            json_res = response.json()
            if json_res.get("status") == 0:
                query_data = json_res.get("data", {})
                columns = query_data.get("column_list", [])
                rows = query_data.get("rows", [])
                result_list = [dict(zip(columns, row)) for row in rows]
                return {
                    "success": True,
                    "query_time": query_data.get("query_time"),
                    "affected_rows": query_data.get("affected_rows"),
                    "data": result_list,
                    "columns": columns,
                    "row_count": len(result_list)
                }
            else:
                err_msg = json_res.get("msg") or json_res.get("data", {}).get("error", "未知错误")
                return {"success": False, "error": err_msg, "data": []}
        except Exception as e:
            logger.error(f"解析 SQL 结果失败: {e}")
            logger.error(f"响应内容: {response.text[:1000]}")
            return {"success": False, "error": f"解析失败: {e}", "data": []}

    @staticmethod
    def parse_instances(response: requests.Response) -> Dict[str, Any]:
        """解析实例列表"""
        if response.status_code != 200:
            return {"success": False, "error": f"HTTP {response.status_code}", "data": []}

        try:
            json_res = response.json()
            if json_res.get("status") == 0:
                return {"success": True, "data": json_res.get("data", [])}
            else:
                return {"success": False, "error": json_res.get("msg", "未知错误"), "data": []}
        except Exception as e:
            logger.error(f"解析实例列表失败: {e}")
            return {"success": False, "error": f"解析失败: {e}", "data": []}

    @staticmethod
    def parse_instance_databases(response: requests.Response) -> Dict[str, Any]:
        """解析实例下的数据库列表"""
        if response.status_code != 200:
            return {"success": False, "error": f"HTTP {response.status_code}", "data": []}

        try:
            json_res = response.json()
            if json_res.get("status") == 0:
                data = json_res.get("data", [])
                if data and isinstance(data[0], str):
                    return {"success": True, "data": data}
                elif data and isinstance(data[0], dict):
                    db_names = [db.get("db_name") or db.get("name") for db in data if
                                db.get("db_name") or db.get("name")]
                    return {"success": True, "data": db_names}
                else:
                    return {"success": True, "data": data}
            else:
                return {"success": False, "error": json_res.get("msg", "未知错误"), "data": []}
        except Exception as e:
            logger.error(f"解析数据库列表失败: {e}")
            return {"success": False, "error": f"解析失败: {e}", "data": []}


# ================= 格式化工具 =================
def format_query_result(result: Dict[str, Any], max_rows: int = 10) -> str:
    """
    格式化查询结果为表格格式（显示所有列，自动换行）
    """
    if not result.get("success"):
        return f"❌ 查询失败: {result.get('error', '未知错误')}"

    data = result.get("data", [])
    columns = result.get("columns", [])
    row_count = result.get("row_count", 0)
    query_time = result.get("query_time", 0)

    if row_count == 0:
        return "✅ 查询成功，返回 0 行数据"

    display_data = data[:max_rows]

    if not columns or not display_data:
        return "✅ 查询成功，但数据为空"

    output = []
    output.append(f"✅ 查询成功！耗时: {query_time}s，共返回 {row_count} 行")
    output.append("")

    # 计算每列最大宽度（限制最大宽度避免表格过宽）
    col_widths = {}
    for col in columns:
        # 列名宽度，限制最大 20 字符
        col_widths[col] = min(len(str(col)), 20)

    for row in display_data:
        if isinstance(row, dict):
            for col in columns:
                val = str(row.get(col, ""))
                # 截断过长的值，限制最大 30 字符
                if len(val) > 30:
                    val = val[:27] + "..."
                col_widths[col] = max(col_widths[col], len(val))

    # 构建表头
    header_parts = []
    sep_parts = []
    for col in columns:
        width = col_widths[col]
        header_parts.append(str(col).ljust(width))
        sep_parts.append("-" * width)

    output.append(" | ".join(header_parts))
    output.append("-|-".join(sep_parts))

    # 数据行
    for row in display_data:
        if isinstance(row, dict):
            row_parts = []
            for col in columns:
                val = str(row.get(col, ""))
                if len(val) > 30:
                    val = val[:27] + "..."
                row_parts.append(val.ljust(col_widths[col]))
            output.append(" | ".join(row_parts))
        else:
            output.append(str(row))

    if row_count > max_rows:
        output.append(f"\n... 共 {row_count} 行，仅显示前 {max_rows} 行")
        output.append("💡 提示：可添加 LIMIT 控制返回行数")

    return "\n".join(output)


# ================= 测试函数 =================
def test_connection():
    """测试 Archery 连接"""
    try:
        session = get_session()
        csrf = session.cookies.get("csrftoken")
        if csrf:
            logger.info(f"✅ Archery 连接成功，CSRF Token: {csrf[:20]}...")
            return True
        else:
            logger.error("❌ 未获取到 CSRF Token")
            return False
    except Exception as e:
        logger.error(f"❌ Archery 连接失败: {e}")
        return False


# 模块加载时测试连接
if __name__ != "__main__":
    try:
        test_connection()
    except Exception as e:
        logger.warning(f"Archery 初始化连接测试失败: {e}")