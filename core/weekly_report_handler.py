# core/weekly_report_handler.py
"""
周报命令处理模块
"""

import json
import logging
from datetime import datetime
from typing import Optional

from core.weekly_report import generate_weekly_report, generate_weekly_report_async

logger = logging.getLogger(__name__)


def get_current_time() -> str:
    """获取当前时间字符串"""
    return datetime.now().strftime("%H:%M:%S")


# ============================================================
# 命令定义
# ============================================================

WEEKLY_REPORT_COMMANDS = ["/report", "/周报", "/weekly"]

WEEKLY_REPORT_HELP_SHORT = """
  /report [天数]    生成周报
  示例: /report              # 生成最近7天的周报
  示例: /report 5            # 生成最近5天的周报
"""


async def handle_weekly_report_command(websocket, content: str, cmd: str) -> bool:
    """
    处理周报生成命令
    """
    parts = content.split()

    # 解析天数参数
    days = 7
    if len(parts) >= 2:
        try:
            days = int(parts[1])
            if days < 1:
                days = 1
            if days > 30:
                days = 30
        except ValueError:
            pass

    # 发送生成中提示
    await websocket.send(json.dumps({
        "type": "system",
        "content": f"⏳ 正在生成周报（最近 {days} 天），请稍候...",
        "time": get_current_time()
    }))

    try:
        # 生成周报
        report = generate_weekly_report(days)

        # 发送结果
        await websocket.send(json.dumps({
            "type": "system",
            "content": report,
            "time": get_current_time()
        }))

    except Exception as e:
        logger.error(f"生成周报失败: {e}")
        await websocket.send(json.dumps({
            "type": "error",
            "content": f"❌ 生成周报失败: {str(e)}",
            "time": get_current_time()
        }))

    return True
