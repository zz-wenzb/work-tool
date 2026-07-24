# core/weekly_report.py
"""
AI 周报生成模块
"""

import json
import logging
import uuid
import time
import requests
from datetime import datetime, timedelta
from typing import Optional

from config.gitlab_config import QIANWEN_COOKIE
from core.gitlab_fetcher import fetch_commits

logger = logging.getLogger(__name__)


def call_qianwen_api(prompt: str, timeout: int = 120) -> str:
    """
    调用通义千问 API 生成周报

    Args:
        prompt: 提示词
        timeout: 超时时间（秒）

    Returns:
        AI 生成的内容
    """
    session_id = str(uuid.uuid4()).replace('-', '')
    device_id = str(uuid.uuid4())
    req_id = str(uuid.uuid4()).replace('-', '')
    timestamp = str(int(time.time() * 1000))

    url = f"https://chat2.qianwen.com/api/v2/chat?biz_id=ai_qwen&chat_client=h5&device=pc&fr=pc&pr=qwen&ut={device_id}&la=zh-CN&tz=Asia/Shanghai&ve=2.4.1&nonce={req_id[:12]}&timestamp={timestamp}"

    headers = {
        'accept': 'application/json, text/event-stream, text/plain, */*',
        'content-type': 'application/json',
        'origin': 'https://www.qianwen.com',
        'referer': f'https://www.qianwen.com/chat/{session_id}',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'x-platform': 'pc_tongyi',
        'cookie': QIANWEN_COOKIE,
    }

    payload = {
        "req_id": req_id,
        "model": "Qwen",
        "scene": "chat",
        "session_id": session_id,
        "sub_scene": "chat",
        "temporary": False,
        "messages": [{"content": prompt, "mime_type": "text/plain"}],
        "from": "default",
        "topic_id": str(uuid.uuid4()).replace('-', ''),
        "parent_req_id": "0",
        "scene_param": "first_turn",
        "chat_client": "h5",
        "client_tm": timestamp,
        "protocol_version": "v2",
        "biz_id": "ai_qwen"
    }

    try:
        response = requests.post(url, headers=headers, json=payload, stream=True, timeout=timeout)

        if response.status_code != 200:
            logger.error(f"通义千问 API 请求失败: {response.status_code}")
            return ""

        full_text = ""
        last_content = ""

        for line in response.iter_lines(decode_unicode=True):
            if not line:
                continue

            if line.startswith('data:'):
                data_str = line[5:].strip()
                if data_str == '[DONE]':
                    break

                try:
                    data = json.loads(data_str)
                    if 'data' in data and 'messages' in data['data']:
                        messages = data['data']['messages']
                        for msg in messages:
                            if isinstance(msg, dict):
                                if msg.get('mime_type') == 'multi_load/iframe':
                                    content = msg.get('content', '')
                                    if content and isinstance(content, str) and content != last_content:
                                        full_text = content
                                        last_content = content
                except json.JSONDecodeError:
                    pass

        return full_text

    except requests.exceptions.Timeout:
        logger.error("通义千问 API 请求超时")
        return ""
    except Exception as e:
        logger.error(f"通义千问 API 请求异常: {e}")
        return ""


def generate_weekly_report(days: int = 7) -> str:
    """
    生成周报

    Args:
        days: 查询天数，默认7天

    Returns:
        生成的周报文本
    """
    # 1. 获取 GitLab 提交记录
    logger.info("正在获取 GitLab 提交记录...")
    commits_text, commit_count, username = fetch_commits(days)

    if commit_count == 0:
        return f"📭 最近 {days} 天内没有找到任何提交记录，无法生成周报。\n\n{commits_text}"

    logger.info(f"获取到 {commit_count} 条提交记录")

    # 2. 计算日期范围
    today = datetime.now()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    date_range = f"{week_start.strftime('%Y.%m.%d')} - {week_end.strftime('%Y.%m.%d')}"

    # 3. 构建提示词
    prompt = f"""你是一个专业的周报生成助手。请根据以下本周GitLab提交记录，帮我生成一份工作周报。

【提交记录】
{commits_text}

【周报格式】
本周工作周报（{date_range}）

【本周完成】
1. <20-40字概括>
2. <20-40字概括>
3. <20-40字概括>
4. <20-40字概括>

【下周计划】
1. <20-40字概括>
2. <20-40字概括>
3. <20-40字概括>

【分析要求】
1. 仔细阅读每条提交记录，提取关键信息
2. 将相似的工作合并归类：
   - 包含 "Merge" 或 "合并" → 代码合并工作
   - 包含 "fix"、"bug"、"修复" → 问题修复
   - 包含 "feature"、"新增"、"添加" → 功能开发
   - 包含 "优化"、"refactor" → 性能/代码优化
3. 按照重要性排序，突出核心成果
4. 如果有多个项目，需要综合表述
5. 下周计划要基于本周的未完成工作或后续迭代方向
6. 如果提交记录少于3条，请说明"本周提交记录较少"
7. 每条工作项必须控制在20-40字之间，简洁有力

现在开始生成周报："""

    # 4. 调用 AI 生成周报
    logger.info("正在调用 AI 生成周报...")
    report = call_qianwen_api(prompt)

    if not report:
        return "❌ AI 生成周报失败，请检查通义千问 Cookie 是否有效"

    # 5. 格式化输出
    return f"""
📊 **周报生成完成**

👤 用户: {username}
📅 周期: {date_range}
📝 提交记录数: {commit_count} 条

{'=' * 60}
{report}
{'=' * 60}
"""


async def generate_weekly_report_async(days: int = 7) -> str:
    """
    异步生成周报（用于 WebSocket）
    """
    return generate_weekly_report(days)
