# core/password_handler.py
"""
密码查询处理模块
支持搜索和显示各种服务的账号密码信息
"""

import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

from config.password_config import PASSWORD_DATA

logger = logging.getLogger(__name__)


def get_current_time() -> str:
    """获取当前时间字符串"""
    return datetime.now().strftime("%H:%M:%S")


def search_passwords(keyword: str, env: Optional[str] = None) -> List[Dict[str, str]]:
    """
    搜索密码信息

    Args:
        keyword: 搜索关键字（支持环境、类型、地址、用户名、备注等）
        env: 环境过滤（DEV, Test, UAT, PROD, Global）

    Returns:
        匹配的密码信息列表
    """
    keyword_lower = keyword.lower().strip()
    results = []

    for item in PASSWORD_DATA:
        # item 格式: (环境, 类型, 地址, 端口, 用户名, 密码, 备注)
        env_name, service_type, address, port, username, password, remark = item

        # 环境过滤
        if env and env_name.upper() != env.upper():
            continue

        # 搜索匹配
        search_text = f"{env_name} {service_type} {address} {username} {remark}".lower()
        if keyword_lower in search_text:
            results.append({
                "env": env_name,
                "type": service_type,
                "address": address,
                "port": str(port) if port else "",
                "username": username if username else "无",
                "password": password if password else "无",
                "remark": remark if remark else ""
            })

    return results


def format_password_result(results: List[Dict[str, str]], keyword: str) -> str:
    """
    格式化密码查询结果
    """
    if not results:
        return f"🔍 未找到与 '{keyword}' 匹配的密码信息"

    output_lines = []
    output_lines.append(f"🔍 找到 {len(results)} 条匹配结果：")
    output_lines.append("=" * 70)

    for idx, item in enumerate(results, 1):
        env = item.get("env", "")
        service_type = item.get("type", "")
        address = item.get("address", "")
        port = item.get("port", "")
        username = item.get("username", "")
        password = item.get("password", "")
        remark = item.get("remark", "")

        # 构建地址显示
        addr_display = address
        if port and port not in ["无", "80", "443"]:
            addr_display = f"{address}:{port}"

        # 环境标签颜色
        env_tags = {
            "DEV": "🔵",
            "Test": "🟢",
            "UAT": "🟡",
            "PROD": "🔴",
            "Global": "🟣"
        }
        env_icon = env_tags.get(env, "📌")

        output_lines.append(f"[{idx}] {env_icon} [{env}] {service_type}")
        output_lines.append(f"    📍 地址: {addr_display}")

        # 如果有完整URL（备注中包含http），额外显示
        if remark and ("http://" in remark or "https://" in remark):
            output_lines.append(f"    🔗 访问: {remark}")

        output_lines.append(f"    👤 账号: {username}")
        output_lines.append(f"    🔑 密码: {password}")
        if remark and "http://" not in remark and "https://" not in remark:
            output_lines.append(f"    📝 备注: {remark}")
        output_lines.append("    " + "-" * 50)

    return "\n".join(output_lines)


# ============================================================
# 命令处理
# ============================================================

PASSWORD_COMMANDS = ["/pwd", "/password", "/密码"]

PASSWORD_HELP = """
  /pwd <关键字> [环境]
    查询密码信息
    示例: /pwd kibana              # 搜索所有包含 kibana 的信息
    示例: /pwd mysql               # 搜索所有 MySQL
    示例: /pwd redis DEV           # 搜索 DEV 环境的 Redis
    示例: /pwd 192.168             # 搜索 IP 地址
    示例: /pwd wenzhibin           # 搜索用户名

  支持的环境: DEV, Test, UAT, PROD, Global
  支持搜索: 环境、类型、地址、用户名、备注
"""


async def handle_password_command(websocket, content: str, cmd: str) -> bool:
    """
    处理密码查询命令
    """
    parts = content.split()

    # 解析参数
    if len(parts) < 2:
        await websocket.send(json.dumps({
            "type": "system",
            "content": f"❌ 用法: {cmd} <关键字> [环境]\n示例: {cmd} kibana\n示例: {cmd} mysql DEV",
            "time": get_current_time()
        }))
        return True

    # 提取关键字和环境
    keyword = parts[1]
    env = None

    if len(parts) >= 3:
        env_candidate = parts[2].upper()
        if env_candidate in ["DEV", "TEST", "UAT", "PROD", "GLOBAL"]:
            env = env_candidate

    logger.info(f"[PASSWORD] keyword={keyword}, env={env}")

    # 搜索
    results = search_passwords(keyword, env)

    # 格式化输出
    output = format_password_result(results, keyword)

    await websocket.send(json.dumps({
        "type": "system",
        "content": output,
        "time": get_current_time()
    }))

    return True


# 密码命令帮助信息（用于 /help）
PASSWORD_HELP_SHORT = """
  /pwd <关键字> [环境]   查询密码信息
  示例: /pwd kibana      /pwd mysql DEV
"""
