# core/mq_handler.py
"""
MQ (消息队列) 命令处理模块
"""
import json
import logging
import os
import sys
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 导入 MQ 客户端
try:
    from core.mq_client import MQManager
except ImportError as e:
    logger.error(f"导入 MQ 客户端失败: {e}")
    MQManager = None

# ========== MQ 环境配置（直接在这里配置） ==========
MQ_ENV_CONFIG = {
    "dev": {
        "host": "http://192.168.1.79:8082",
        "cookie": "",
        "username": "",
        "password": "",
        "no_login": True
    },
    "test": {
        "host": "http://test-rocketmq.zhongbaozhiyun.com:8080",
        "cookie": "apt.uid=AP-YFGMCGUNNIFB-2-1767687842794-95994121.0.2.6b933aba-006b-4c12-b4b5-a0ddc2adfcf4; NG_TRANSLATE_LANG_KEY=%22zh%22; JSESSIONID=83756A92B4B1BB16DED7BD4A23BE0588",
        "username": "admin",
        "password": "admin123",
        "no_login": False
    },
    "uat": {
        "host": "http://uat-rocketmq.zhongbaozhiyun.com:8080",
        "cookie": "apt.uid=AP-YFGMCGUNNIFB-2-1767687842794-95994121.0.2.6b933aba-006b-4c12-b4b5-a0ddc2adfcf4; JSESSIONID=F830C5AEE5C647F110970B9A0BEE386D; NG_TRANSLATE_LANG_KEY=%22zh%22",
        "username": "admin",
        "password": "admin123",
        "no_login": False
    }
}

# MQ 命令映射
MQ_COMMANDS = {
    "/mq-list": {
        "description": "列出所有 topic (支持模糊搜索)",
        "handler": "handle_mq_list"
    },
    "/mq-exists": {
        "description": "查询某个 topic 是否存在",
        "handler": "handle_mq_exists"
    },
    "/mq-last": {
        "description": "查询某个 topic 最新一条消息的完整消息体",
        "handler": "handle_mq_last"
    },
    "/mq-send": {
        "description": "给 topic 发消息",
        "handler": "handle_mq_send"
    },
    "/mq-recent": {
        "description": "查询某个 topic 最近 N 分钟的所有消息",
        "handler": "handle_mq_recent"
    },
    "/mq-query": {
        "description": "在某个 topic 查询消息（条件查询）",
        "handler": "handle_mq_query"
    },
    "/mq-create": {
        "description": "创建 topic",
        "handler": "handle_mq_create"
    },
    "/mq-delete": {
        "description": "删除 topic",
        "handler": "handle_mq_delete"
    },
}

# 全局 MQ 管理器缓存
_mq_managers = {}


def get_current_time():
    """获取当前时间字符串"""
    return datetime.now().strftime("%H:%M:%S")


def parse_env_from_end(parts, default_env="test"):
    """
    从参数列表末尾提取环境名
    如果最后一个参数是 dev/test/uat，则作为环境名
    否则返回默认环境

    Args:
        parts: 参数列表
        default_env: 默认环境

    Returns:
        (env, remaining_parts): 环境名和剩余参数列表
    """
    if not parts:
        return default_env, parts

    if parts[-1] in ['dev', 'test', 'uat']:
        return parts[-1], parts[:-1]
    return default_env, parts


def get_mq_manager(env: str = "test"):
    """
    获取或创建 MQ 管理器实例

    Args:
        env: 环境名称 (dev, test, uat)

    Returns:
        (MQManager, error_message): 成功返回 (manager, None)，失败返回 (None, error_msg)
    """
    if MQManager is None:
        return None, "MQ 客户端模块未正确导入，请检查 core/mq_client.py"

    # 检查缓存
    cache_key = env
    if cache_key in _mq_managers:
        return _mq_managers[cache_key], None

    # 获取环境配置
    mq_config = MQ_ENV_CONFIG.get(env)
    if not mq_config:
        return None, f"未找到 {env} 环境的配置，请在 MQ_ENV_CONFIG 中添加"

    # 检查必要配置
    if not mq_config.get('host'):
        return None, f"{env} 环境未配置 host 地址"

    try:
        mgr = MQManager(mq_config)

        # 判断是否需要登录
        if mq_config.get('no_login', False):
            logger.info(f"✅ 跳过登录 (环境: {env}, no_login=True)")
            _mq_managers[cache_key] = mgr
            return mgr, None

        # 没有账号密码但有 cookie
        if (not mq_config.get('username') or not mq_config.get('password')) and mq_config.get('cookie'):
            logger.info(f"✅ 使用 cookie 认证 (环境: {env})")
            _mq_managers[cache_key] = mgr
            return mgr, None

        # 有账号密码，执行登录
        if mq_config.get('username') and mq_config.get('password'):
            success = mgr.login()
            if success:
                _mq_managers[cache_key] = mgr
                logger.info(f"✅ MQ 管理器初始化成功 (环境: {env}, host: {mq_config.get('host')})")
                return mgr, None
            else:
                return None, f"登录 {env} 环境失败，请检查账号密码或 cookie"
        else:
            return None, f"{env} 环境未配置账号密码且无有效 cookie，无法认证"

    except Exception as e:
        logger.exception(f"初始化 MQ 管理器失败: {e}")
        return None, f"初始化失败: {e}"


def format_timestamp(timestamp_ms):
    """格式化时间戳（毫秒）"""
    if not timestamp_ms:
        return "N/A"
    try:
        return datetime.fromtimestamp(timestamp_ms / 1000).strftime('%Y-%m-%d %H:%M:%S')
    except:
        return str(timestamp_ms)


def find_field_in_data(data, field_name: str) -> list:
    """在数据中递归查找指定字段的所有值"""
    results = []
    if isinstance(data, dict):
        if field_name in data:
            results.append(data[field_name])
        for value in data.values():
            results.extend(find_field_in_data(value, field_name))
    elif isinstance(data, list):
        for item in data:
            results.extend(find_field_in_data(item, field_name))
    return results


def match_filters(message_body: str, filters: dict) -> bool:
    """判断消息是否匹配过滤条件"""
    try:
        parsed_body = json.loads(message_body)
        for field_name, search_value in filters.items():
            found_values = find_field_in_data(parsed_body, field_name)
            if not found_values:
                return False

            matched = False
            for value in found_values:
                if isinstance(value, str) and isinstance(search_value, str):
                    if search_value.lower() in value.lower():
                        matched = True
                        break
                else:
                    if str(value) == str(search_value):
                        matched = True
                        break

            if not matched:
                return False
        return True
    except json.JSONDecodeError:
        return False


def format_messages_for_display(messages: list, limit: int = 50) -> str:
    """
    格式化消息列表用于显示
    """
    if not messages:
        return "  ⚠️ 没有找到消息"

    display_count = min(len(messages), limit)
    result = f"共 {len(messages)} 条消息"
    if len(messages) > limit:
        result += f" (显示前 {limit} 条)\n\n"
    else:
        result += ":\n\n"

    for idx, msg in enumerate(messages[:limit], 1):
        msg_id = msg.get('msgId', 'N/A')
        store_ts = msg.get('storeTimestamp')
        store_time = format_timestamp(store_ts)
        body = msg.get('messageBody', '')
        topic = msg.get('topic', 'N/A')

        try:
            parsed_body = json.loads(body)
            body_display = json.dumps(parsed_body, ensure_ascii=False)
            if len(body_display) > 200:
                body_display = body_display[:200] + '...'
        except:
            body_display = body[:200] + ('...' if len(body) > 200 else '')

        result += f"[{idx}] 消息ID: {msg_id}\n"
        result += f"    时间: {store_time}\n"
        result += f"    Topic: {topic}\n"
        result += f"    内容: {body_display}\n\n"

    return result


# ============================================================
# 命令处理函数 (统一: env 参数放在最后)
# ============================================================

async def handle_mq_list(websocket, content, cmd):
    """
    /mq-list - 列出所有 topic（支持模糊搜索）
    用法: /mq-list [关键词] [env]
    示例: /mq-list                    # 默认 test 环境，列出所有
    示例: /mq-list cargo              # 默认 test 环境，搜索包含 cargo
    示例: /mq-list cargo test         # test 环境，搜索包含 cargo
    示例: /mq-list test               # ⚠️ 注意: 这样会被当作关键词，不是环境！
    """
    parts = content.split()

    # 从末尾提取 env
    env, remaining = parse_env_from_end(parts[1:], "test")
    keyword = ' '.join(remaining) if remaining else ""

    logger.info(f"[MQ-LIST] env={env}, keyword={keyword}")

    mgr, err = get_mq_manager(env)
    if err:
        await websocket.send(json.dumps({
            "type": "system",
            "content": f"❌ {err}",
            "time": get_current_time()
        }))
        return True

    result = mgr.query_topic_list()
    if result.get('status') != 0:
        await websocket.send(json.dumps({
            "type": "system",
            "content": f"❌ 查询失败: {result.get('errMsg', '未知错误')}",
            "time": get_current_time()
        }))
        return True

    data = result.get('data', {})
    if isinstance(data, list):
        topics = data
    elif isinstance(data, dict):
        topics = data.get('topicList', []) or data.get('topics', []) or []
    else:
        topics = []

    # 按环境过滤（以 env% 开头的 topic）
    filtered_topics = [t for t in topics if t.startswith(f"{env}%")]

    # 按关键词模糊搜索（不区分大小写）
    if keyword:
        keyword_lower = keyword.lower()
        filtered_topics = [t for t in filtered_topics if keyword_lower in t.lower()]

    # 按字母排序
    filtered_topics.sort()

    # 构建回复
    reply = f"📨 Topic 列表 (环境: {env})"
    if keyword:
        reply += f" | 搜索: '{keyword}'"
    reply += f"\n共 {len(filtered_topics)} 个 Topic:\n"

    if filtered_topics:
        max_display = 200
        display_count = len(filtered_topics)
        if display_count > max_display:
            reply += f"(显示前 {max_display} 个，共 {display_count} 个)\n\n"
            filtered_topics = filtered_topics[:max_display]

        for idx, topic in enumerate(filtered_topics, 1):
            reply += f"  {idx}. {topic}\n"
    else:
        reply += "  (无匹配的 Topic)"
        if keyword:
            reply += f"\n\n💡 提示：没有找到包含 '{keyword}' 的 Topic"

    await websocket.send(json.dumps({
        "type": "system",
        "content": reply,
        "time": get_current_time()
    }))
    return True


async def handle_mq_exists(websocket, content, cmd):
    """
    /mq-exists - 查询某个 topic 是否存在
    用法: /mq-exists <topic> [env]
    示例: /mq-exists test%nt_cargo
    示例: /mq-exists test%nt_cargo test
    """
    parts = content.split()
    if len(parts) < 2:
        await websocket.send(json.dumps({
            "type": "system",
            "content": "❌ 用法: /mq-exists <topic> [env]\n示例: /mq-exists test%nt_cargo",
            "time": get_current_time()
        }))
        return True

    # 从末尾提取 env
    env, remaining = parse_env_from_end(parts[1:], "test")
    topic = ' '.join(remaining) if remaining else ""

    if not topic:
        await websocket.send(json.dumps({
            "type": "system",
            "content": "❌ Topic 名称不能为空",
            "time": get_current_time()
        }))
        return True

    logger.info(f"[MQ-EXISTS] topic={topic}, env={env}")

    mgr, err = get_mq_manager(env)
    if err:
        await websocket.send(json.dumps({
            "type": "system",
            "content": f"❌ {err}",
            "time": get_current_time()
        }))
        return True

    result = mgr.query_topic_list()
    if result.get('status') != 0:
        await websocket.send(json.dumps({
            "type": "system",
            "content": f"❌ 查询失败: {result.get('errMsg', '未知错误')}",
            "time": get_current_time()
        }))
        return True

    data = result.get('data', {})
    if isinstance(data, list):
        topics = data
    elif isinstance(data, dict):
        topics = data.get('topicList', []) or data.get('topics', []) or []
    else:
        topics = []

    # 精确匹配
    exists = topic in topics

    reply = f"🔍 查询 Topic: {topic}\n"
    reply += f"  环境: {env}\n"
    reply += f"  存在: {'✅ 是' if exists else '❌ 否'}"

    if not exists and topics:
        similar = [t for t in topics if topic.lower() in t.lower() or t.lower() in topic.lower()]
        similar = [t for t in similar if t != topic]
        if similar:
            reply += f"\n\n  📋 相似的 Topic:\n"
            for s in similar[:5]:
                reply += f"    • {s}\n"

    await websocket.send(json.dumps({
        "type": "system",
        "content": reply,
        "time": get_current_time()
    }))
    return True


# core/mq_handler.py - 在 handle_mq_exists 后面添加

async def handle_mq_last(websocket, content, cmd):
    """
    /mq-last - 查询某个 topic 最新一条消息的完整消息体
    用法: /mq-last <topic> [env]
    示例: /mq-last test%nt_cargo
    示例: /mq-last test%nt_cargo uat
    """
    parts = content.split()
    if len(parts) < 2:
        await websocket.send(json.dumps({
            "type": "system",
            "content": "❌ 用法: /mq-last <topic> [env]\n示例: /mq-last test%nt_cargo",
            "time": get_current_time()
        }))
        return True

    # 从末尾提取 env
    env, remaining = parse_env_from_end(parts[1:], "test")
    topic = ' '.join(remaining) if remaining else ""

    if not topic:
        await websocket.send(json.dumps({
            "type": "system",
            "content": "❌ Topic 名称不能为空",
            "time": get_current_time()
        }))
        return True

    logger.info(f"[MQ-LAST] topic={topic}, env={env}")

    mgr, err = get_mq_manager(env)
    if err:
        await websocket.send(json.dumps({
            "type": "system",
            "content": f"❌ {err}",
            "time": get_current_time()
        }))
        return True

    # 查询最近 60 分钟的消息，获取最新一条
    result = mgr.query_topic_message(topic=topic, m=60, page_size=1)

    if result.get('status') != 0:
        await websocket.send(json.dumps({
            "type": "system",
            "content": f"❌ 查询失败: {result.get('errMsg', '未知错误')}",
            "time": get_current_time()
        }))
        return True

    messages = result.get('data', {}).get('page', {}).get('content', [])

    if not messages:
        await websocket.send(json.dumps({
            "type": "system",
            "content": f"📭 Topic [{topic}] (环境: {env}) 没有找到消息\n\n💡 提示: 可以尝试 /mq-send 发送一条测试消息",
            "time": get_current_time()
        }))
        return True

    # 取最新一条消息（列表默认按时间倒序排列，第一条就是最新的）
    msg = messages[0]
    msg_id = msg.get('msgId', 'N/A')
    store_ts = msg.get('storeTimestamp')
    store_time = format_timestamp(store_ts)
    body = msg.get('messageBody', '')
    topic_name = msg.get('topic', topic)

    # 格式化消息体（尝试美化 JSON）
    try:
        parsed_body = json.loads(body)
        formatted_body = json.dumps(parsed_body, ensure_ascii=False, indent=2)
    except:
        formatted_body = body

    # 构建回复
    reply = f"📨 Topic [{topic_name}] 最新消息 (环境: {env})\n"
    reply += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    reply += f"📌 消息ID: {msg_id}\n"
    reply += f"🕐 时间: {store_time}\n"
    reply += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    reply += f"📄 消息体:\n"
    reply += f"{formatted_body}"

    # 如果消息体太长，截断
    if len(reply) > 15000:
        # 保留前 12000 字符
        reply = reply[:12000] + "\n\n... (消息体过长，已截断)"

    await websocket.send(json.dumps({
        "type": "system",
        "content": reply,
        "time": get_current_time()
    }))
    return True


async def handle_mq_send(websocket, content, cmd):
    """
    /mq-send - 给 topic 发消息
    用法: /mq-send <topic> <message> [env]
    示例: /mq-send test%nt_cargo '{"key":"value"}'
    示例: /mq-send test%nt_cargo '{"shipperName":"货老板"}' test
    提示: 消息内容请用单引号包裹 JSON
    """
    parts = content.split()
    if len(parts) < 3:
        await websocket.send(json.dumps({
            "type": "system",
            "content": "❌ 用法: /mq-send <topic> <message> [env]\n"
                       "示例: /mq-send test%nt_cargo '{\"key\":\"value\"}'\n"
                       "提示: 消息内容请用单引号包裹 JSON",
            "time": get_current_time()
        }))
        return True

    # topic 是第二个参数
    topic = parts[1]

    # 从末尾提取 env（从剩余参数中提取）
    env, remaining = parse_env_from_end(parts[2:], "test")
    # remaining 是消息内容（可能有空格）
    message_body = ' '.join(remaining) if remaining else ""

    if not message_body:
        await websocket.send(json.dumps({
            "type": "system",
            "content": "❌ 消息内容不能为空",
            "time": get_current_time()
        }))
        return True

    logger.info(f"[MQ-SEND] topic={topic}, env={env}, message_length={len(message_body)}")

    mgr, err = get_mq_manager(env)
    if err:
        await websocket.send(json.dumps({
            "type": "system",
            "content": f"❌ {err}",
            "time": get_current_time()
        }))
        return True

    # 验证 JSON 格式
    try:
        json.loads(message_body)
    except json.JSONDecodeError as e:
        await websocket.send(json.dumps({
            "type": "system",
            "content": f"⚠️ JSON 格式错误: {e}\n请重新输入正确的 JSON 格式",
            "time": get_current_time()
        }))
        return True

    result = mgr.send_message(
        topic=topic,
        message_body=message_body,
        tag="",
        key="",
        trace_enabled=False
    )

    if result.get('status') == 0:
        send_data = result.get('data', {})
        msg_id = send_data.get('msgId', 'N/A')
        send_status = send_data.get('sendStatus', 'N/A')
        reply = f"📤 消息发送成功\n"
        reply += f"  Topic: {topic}\n"
        reply += f"  环境: {env}\n"
        reply += f"  消息ID: {msg_id}\n"
        reply += f"  状态: {send_status}\n"
        reply += f"  内容: {message_body[:200]}{'...' if len(message_body) > 200 else ''}"
    else:
        reply = f"❌ 发送失败: {result.get('errMsg', '未知错误')}"

    await websocket.send(json.dumps({
        "type": "system",
        "content": reply,
        "time": get_current_time()
    }))
    return True


async def handle_mq_recent(websocket, content, cmd):
    """
    /mq-recent - 查询某个 topic 最近 N 分钟的所有消息
    用法: /mq-recent <topic> [分钟] [env]
    示例: /mq-recent test%nt_cargo 10
    示例: /mq-recent test%nt_cargo 30 test
    """
    parts = content.split()
    if len(parts) < 2:
        await websocket.send(json.dumps({
            "type": "system",
            "content": "❌ 用法: /mq-recent <topic> [分钟] [env]\n示例: /mq-recent test%nt_cargo 10",
            "time": get_current_time()
        }))
        return True

    # 从末尾提取 env
    env, remaining = parse_env_from_end(parts[1:], "test")

    # 从 remaining 中提取分钟数（最后一个如果是数字）
    minutes = 60
    if remaining:
        # 检查最后一个是否是数字
        if remaining[-1].isdigit():
            minutes = int(remaining[-1])
            remaining = remaining[:-1]
        # 检查第一个是否是数字（如果只有两个参数: topic 和 分钟）
        elif len(remaining) >= 2 and remaining[1].isdigit():
            minutes = int(remaining[1])
            remaining = [remaining[0]]

    topic = ' '.join(remaining) if remaining else ""

    if not topic:
        await websocket.send(json.dumps({
            "type": "system",
            "content": "❌ Topic 名称不能为空",
            "time": get_current_time()
        }))
        return True

    logger.info(f"[MQ-RECENT] topic={topic}, minutes={minutes}, env={env}")

    mgr, err = get_mq_manager(env)
    if err:
        await websocket.send(json.dumps({
            "type": "system",
            "content": f"❌ {err}",
            "time": get_current_time()
        }))
        return True

    result = mgr.query_topic_message(topic=topic, m=minutes, page_size=50)

    if result.get('status') != 0:
        await websocket.send(json.dumps({
            "type": "system",
            "content": f"❌ 查询失败: {result.get('errMsg', '未知错误')}",
            "time": get_current_time()
        }))
        return True

    messages = result.get('data', {}).get('page', {}).get('content', [])

    reply = f"📥 Topic [{topic}] 最近 {minutes} 分钟 (环境: {env})\n"
    reply += format_messages_for_display(messages)

    await websocket.send(json.dumps({
        "type": "system",
        "content": reply,
        "time": get_current_time()
    }))
    return True


async def handle_mq_query(websocket, content, cmd):
    """
    /mq-query - 在某个 topic 查询消息（条件查询）
    用法: /mq-query <topic> <字段=值> [分钟] [env]
    示例: /mq-query test%nt_cargo shipperName=货老板 10
    示例: /mq-query test%nt_cargo cargoName=钢材 30 test
    """
    parts = content.split()
    if len(parts) < 3:
        await websocket.send(json.dumps({
            "type": "system",
            "content": "❌ 用法: /mq-query <topic> <字段=值> [分钟] [env]\n"
                       "示例: /mq-query test%nt_cargo shipperName=货老板 10\n"
                       "示例: /mq-query test%nt_cargo cargoName=钢材 30 test",
            "time": get_current_time()
        }))
        return True

    # 从末尾提取 env
    env, remaining = parse_env_from_end(parts[1:], "test")

    # 从 remaining 中提取分钟数（最后一个如果是数字）
    minutes = 60
    if remaining and remaining[-1].isdigit():
        minutes = int(remaining[-1])
        remaining = remaining[:-1]

    # 从 remaining 中提取条件（包含 = 的参数）
    condition = ""
    condition_idx = -1
    for i in range(len(remaining) - 1, -1, -1):
        if '=' in remaining[i]:
            condition_idx = i
            condition = remaining[i]
            break

    if condition_idx == -1:
        await websocket.send(json.dumps({
            "type": "system",
            "content": "❌ 条件格式错误，请使用 field=value 格式\n示例: shipperName=货老板",
            "time": get_current_time()
        }))
        return True

    # topic 是条件之前的所有内容
    topic = ' '.join(remaining[:condition_idx]) if condition_idx > 0 else remaining[0] if remaining else ""

    # 验证条件格式
    if '=' not in condition:
        await websocket.send(json.dumps({
            "type": "system",
            "content": "❌ 条件格式错误，请使用 field=value 格式\n示例: shipperName=货老板",
            "time": get_current_time()
        }))
        return True

    field, value = condition.split('=', 1)

    if not topic:
        await websocket.send(json.dumps({
            "type": "system",
            "content": "❌ Topic 名称不能为空",
            "time": get_current_time()
        }))
        return True

    logger.info(f"[MQ-QUERY] topic={topic}, field={field}, value={value}, minutes={minutes}, env={env}")

    mgr, err = get_mq_manager(env)
    if err:
        await websocket.send(json.dumps({
            "type": "system",
            "content": f"❌ {err}",
            "time": get_current_time()
        }))
        return True

    result = mgr.query_topic_message(topic=topic, m=minutes, page_size=100)

    if result.get('status') != 0:
        await websocket.send(json.dumps({
            "type": "system",
            "content": f"❌ 查询失败: {result.get('errMsg', '未知错误')}",
            "time": get_current_time()
        }))
        return True

    all_messages = result.get('data', {}).get('page', {}).get('content', [])

    if not all_messages:
        reply = f"🔎 在 Topic [{topic}] 中查询消息\n"
        reply += f"  条件: {field}={value}\n"
        reply += f"  时间范围: 最近 {minutes} 分钟 (环境: {env})\n"
        reply += "  ⚠️ 没有找到消息"
        await websocket.send(json.dumps({
            "type": "system",
            "content": reply,
            "time": get_current_time()
        }))
        return True

    filtered_messages = []
    filters = {field: value}

    for msg in all_messages:
        message_body = msg.get('messageBody')
        if message_body and match_filters(message_body, filters):
            filtered_messages.append(msg)

    if not filtered_messages:
        reply = f"🔎 在 Topic [{topic}] 中查询消息\n"
        reply += f"  条件: {field}={value}\n"
        reply += f"  时间范围: 最近 {minutes} 分钟 (环境: {env})\n"
        reply += f"  共获取 {len(all_messages)} 条消息\n"
        reply += "  ⚠️ 没有匹配到符合条件的消息"
        await websocket.send(json.dumps({
            "type": "system",
            "content": reply,
            "time": get_current_time()
        }))
        return True

    reply = f"🔎 在 Topic [{topic}] 中查询消息\n"
    reply += f"  条件: {field}={value}\n"
    reply += f"  时间范围: 最近 {minutes} 分钟 (环境: {env})\n"
    reply += format_messages_for_display(filtered_messages)

    await websocket.send(json.dumps({
        "type": "system",
        "content": reply,
        "time": get_current_time()
    }))
    return True


async def handle_mq_create(websocket, content, cmd):
    """
    /mq-create - 创建 topic
    用法: /mq-create <topic> [env]
    示例: /mq-create test_my_topic
    示例: /mq-create test_my_topic test
    """
    parts = content.split()
    if len(parts) < 2:
        await websocket.send(json.dumps({
            "type": "system",
            "content": "❌ 用法: /mq-create <topic> [env]\n示例: /mq-create test_my_topic",
            "time": get_current_time()
        }))
        return True

    # 从末尾提取 env
    env, remaining = parse_env_from_end(parts[1:], "test")
    topic = ' '.join(remaining) if remaining else ""

    if not topic:
        await websocket.send(json.dumps({
            "type": "system",
            "content": "❌ Topic 名称不能为空",
            "time": get_current_time()
        }))
        return True

    mgr, err = get_mq_manager(env)
    if err:
        await websocket.send(json.dumps({
            "type": "system",
            "content": f"❌ {err}",
            "time": get_current_time()
        }))
        return True

    result = mgr.create_topic(
        topic=topic,
        message_type="NORMAL",
        write_queue_nums=8,
        read_queue_nums=8,
        perm=7
    )

    if result.get('status') == 0:
        reply = f"✅ Topic '{topic}' 创建成功\n"
        reply += f"  环境: {env}"
    else:
        reply = f"❌ 创建失败: {result.get('errMsg', '未知错误')}"

    await websocket.send(json.dumps({
        "type": "system",
        "content": reply,
        "time": get_current_time()
    }))
    return True


async def handle_mq_delete(websocket, content, cmd):
    """
    /mq-delete - 删除 topic
    用法: /mq-delete <topic> [env]
    示例: /mq-delete test_my_topic
    """
    parts = content.split()
    if len(parts) < 2:
        await websocket.send(json.dumps({
            "type": "system",
            "content": "❌ 用法: /mq-delete <topic> [env]\n示例: /mq-delete test_my_topic",
            "time": get_current_time()
        }))
        return True

    # 从末尾提取 env
    env, remaining = parse_env_from_end(parts[1:], "test")
    topic = ' '.join(remaining) if remaining else ""

    if not topic:
        await websocket.send(json.dumps({
            "type": "system",
            "content": "❌ Topic 名称不能为空",
            "time": get_current_time()
        }))
        return True

    mgr, err = get_mq_manager(env)
    if err:
        await websocket.send(json.dumps({
            "type": "system",
            "content": f"❌ {err}",
            "time": get_current_time()
        }))
        return True

    result = mgr.delete_topic(topic=topic)

    if result.get('status') == 0:
        reply = f"✅ Topic '{topic}' 已删除\n"
        reply += f"  环境: {env}"
    else:
        reply = f"❌ 删除失败: {result.get('errMsg', '未知错误')}"

    await websocket.send(json.dumps({
        "type": "system",
        "content": reply,
        "time": get_current_time()
    }))
    return True


# 命令分发映射
MQ_HANDLERS = {
    "/mq-list": handle_mq_list,
    "/mq-exists": handle_mq_exists,
    "/mq-last": handle_mq_last,
    "/mq-send": handle_mq_send,
    "/mq-recent": handle_mq_recent,
    "/mq-query": handle_mq_query,
    "/mq-create": handle_mq_create,
    "/mq-delete": handle_mq_delete,
}


async def handle_mq_command(websocket, content, cmd):
    """
    MQ 命令入口
    返回 True 表示命令已处理
    """
    handler = MQ_HANDLERS.get(cmd)
    if handler:
        return await handler(websocket, content, cmd)
    return False
