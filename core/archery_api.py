# core/archery_api.py
import requests
import pickle
import os
import logging
import time
from datetime import datetime, timedelta
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
                    # 检查是否过期（超过30分钟认为过期）
                    if cached_session.cookies.get("csrftoken"):
                        self._session.cookies.update(cached_session.cookies)
                        self._session.headers.update(cached_session.headers)
                        self._last_used = time.time()
                        logger.info("✅ 从缓存加载 Archery 会话成功")
                        return
            except Exception as e:
                logger.warning(f"加载缓存会话失败: {e}")
                if os.path.exists(COOKIE_FILE):
                    os.remove(COOKIE_FILE)

        # 执行登录
        self._login()

    def _login(self):
        """登录 Archery"""
        logger.info("正在登录 Archery...")
        try:
            # 获取初始 CSRF
            self._session.get(BASE_URL)
            initial_csrf = self._session.cookies.get("csrftoken", "")

            login_headers = {
                "X-CSRFToken": initial_csrf,
                "Referer": BASE_URL,
                "Content-Type": "application/x-www-form-urlencoded"
            }

            response = self._session.post(LOGIN_URL, data=LOGIN_DATA, headers=login_headers)

            if response.status_code == 200:
                logger.info("✅ Archery 登录成功")
                self._last_used = time.time()
                # 保存会话到缓存
                os.makedirs(os.path.dirname(COOKIE_FILE), exist_ok=True)
                with open(COOKIE_FILE, "wb") as f:
                    pickle.dump(self._session, f)
            else:
                raise Exception(f"登录失败，状态码: {response.status_code}, 响应: {response.text[:200]}")
        except Exception as e:
            logger.error(f"Archery 登录失败: {e}")
            raise

    def get_session(self) -> requests.Session:
        """获取会话，如果过期则重新登录"""
        # 检查会话是否过期（超过25分钟）
        if time.time() - self._last_used > 1500:  # 25分钟
            logger.info("⏰ 会话可能已过期，尝试刷新...")
            self.refresh_session()

        # 确保有 CSRF Token
        csrf_token = self._session.cookies.get("csrftoken")
        if csrf_token:
            self._session.headers.update({
                "X-CSRFToken": csrf_token,
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": BASE_URL
            })
        else:
            logger.warning("⚠️ 未找到 CSRF Token，重新登录...")
            self.refresh_session()

        self._last_used = time.time()
        return self._session

    def refresh_session(self):
        """刷新会话"""
        logger.info("🔄 刷新 Archery 会话...")
        if os.path.exists(COOKIE_FILE):
            os.remove(COOKIE_FILE)
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest"
        })
        self._login()


# ================= 全局会话实例 =================
session_manager = ArcherySessionManager()


def get_session() -> requests.Session:
    """获取 Archery 会话"""
    return session_manager.get_session()


# ================= Archery API 接口 =================
class ArcheryAPI:
    @staticmethod
    def execute_sql_query(instance_name: str, db_name: str, sql_content: str, limit_num: int = 100) -> Dict[str, Any]:
        """
        执行 SQL 查询，自动处理会话过期
        """
        max_retries = 2
        for attempt in range(max_retries):
            try:
                session = get_session()

                # 确保 CSRF Token 在请求头中
                csrf_token = session.cookies.get("csrftoken")
                if csrf_token:
                    session.headers["X-CSRFToken"] = csrf_token

                data = {
                    "instance_name": instance_name,
                    "db_name": db_name,
                    "schema_name": "",
                    "tb_name": "",
                    "sql_content": sql_content,
                    "limit_num": limit_num
                }

                response = session.post(QUERY_URL, data=data)

                # 如果返回 403，说明会话失效，尝试刷新
                if response.status_code == 403:
                    logger.warning(f"⚠️ 收到 403，尝试刷新会话 (尝试 {attempt + 1}/{max_retries})")
                    session_manager.refresh_session()
                    continue

                return ArcheryParser.parse_sql_query(response)
            except Exception as e:
                logger.error(f"执行 SQL 查询失败 (尝试 {attempt + 1}): {e}")
                if attempt == max_retries - 1:
                    return {"success": False, "error": str(e), "data": []}

        return {"success": False, "error": "查询失败，请重试", "data": []}

    @staticmethod
    def get_user_instances(tag_code: str = "can_read") -> Dict[str, Any]:
        """获取用户有权限的实例列表"""
        try:
            session = get_session()
            params = {"tag_codes[]": tag_code}
            response = session.get(INSTANCE_LIST_URL, params=params)
            return ArcheryParser.parse_instances(response)
        except Exception as e:
            logger.error(f"获取实例列表失败: {e}")
            return {"success": False, "error": str(e), "data": []}

    @staticmethod
    def get_instance_databases(instance_name: str) -> Dict[str, Any]:
        """获取实例下的数据库列表"""
        try:
            session = get_session()
            params = {
                "instance_name": instance_name,
                "resource_type": "database"
            }
            response = session.get(INSTANCE_RESOURCE_URL, params=params)
            return ArcheryParser.parse_instance_databases(response)
        except Exception as e:
            logger.error(f"获取数据库列表失败: {e}")
            return {"success": False, "error": str(e), "data": []}


# ================= 解析器 =================
class ArcheryParser:
    @staticmethod
    def parse_sql_query(response: requests.Response) -> Dict[str, Any]:
        """解析 SQL 查询结果"""
        if response.status_code != 200:
            error_msg = f"HTTP {response.status_code}"
            if response.status_code == 403:
                error_msg = "会话已过期，请重新登录"
            elif response.status_code == 500:
                error_msg = "服务器内部错误，请检查 SQL 语句"
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
            return {"success": False, "error": f"解析失败: {e}", "data": []}


# ================= 格式化工具 =================
# core/archery_api.py - 替换 format_query_result 函数
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
