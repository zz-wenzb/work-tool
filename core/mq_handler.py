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
        "host": "http://192.168.1.79:8082",  # 修复：去掉重复的 http://
        "cookie": "",  # 可选，有 cookie 可跳过登录
        "username": "",  # dev 环境不需要用户名密码
        "password": "",
        "no_login": True  # 标记此环境不需要登录
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
        "description": "列出所有 topic",
        "handler": "handle_mq_list"
    },
    "/mq-exists": {
        "description": "查询某个 topic 是否存在",
        "handler": "handle_mq_exists"
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
        # 1. 如果配置了 no_login=True，跳过登录
        # 2. 如果没有配置 username 或 password，且有 cookie，跳过登录
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


async def handle_mq_list(websocket, content, cmd):
    """
    /mq-list - 列出所有 topic
    用法: /mq-list [env]
    示例: /mq-list test
    """
    parts = content.split()
    env = parts[1] if len(parts) > 1 else "test"

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

    reply = f"📨 Topic 列表 (环境: {env})\n"
    reply += f"共 {len(filtered_topics)} 个 Topic:\n"
    if filtered_topics:
        for idx, topic in enumerate(filtered_topics, 1):
            reply += f"  {idx}. {topic}\n"
    else:
        reply += "  (无)\n"

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

    # 默认值
    env = "test"
    topic = ""

    # 解析参数：
    # 如果只有2个参数: /mq-exists test%nt_cargo → topic=test%nt_cargo, env=test
    # 如果有3个参数: /mq-exists test%nt_cargo test → topic=test%nt_cargo, env=test
    # 如果有3个参数但第二个是环境名: /mq-exists test test%nt_cargo → 这种情况需要特殊处理

    if len(parts) == 2:
        # 只有 topic，没有指定环境
        topic = parts[1]
        env = "test"
    elif len(parts) == 3:
        # 判断哪个是环境，哪个是 topic
        # 如果第二个参数是 dev/test/uat，则第二个是环境，第三个是 topic
        if parts[1] in ['dev', 'test', 'uat']:
            env = parts[1]
            topic = parts[2]
        # 如果第三个参数是 dev/test/uat，则第三个是环境，第二个是 topic
        elif parts[2] in ['dev', 'test', 'uat']:
            env = parts[2]
            topic = parts[1]
        else:
            # 都不是环境，把第二个和第三个合并作为 topic
            topic = ' '.join(parts[1:])
            env = "test"
    else:
        # 多于3个参数，从后往前找环境
        env = "test"
        # 检查最后一个是否是环境
        if parts[-1] in ['dev', 'test', 'uat']:
            env = parts[-1]
            topic = ' '.join(parts[1:-1])
        else:
            topic = ' '.join(parts[1:])

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
        # 显示相似的 topic
        similar = [t for t in topics if topic.lower() in t.lower() or t.lower() in topic.lower()]
        # 排除完全匹配的
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


async def handle_mq_send(websocket, content, cmd):
    """
    /mq-send - 给 topic 发消息
    用法: /mq-send <topic> <message> [env]
    示例: /mq-send test%nt_cargo '{"key":"value"}'
    示例: /mq-send test%nt_cargo '{"shipperName":"货老板"}' test
    提示: 消息内容请用单引号包裹 JSON
    """
    # 先分割，但保留消息内容中的空格
    parts = content.split(maxsplit=2)
    if len(parts) < 3:
        await websocket.send(json.dumps({
            "type": "system",
            "content": "❌ 用法: /mq-send <topic> <message> [env]\n"
                       "示例: /mq-send test%nt_cargo '{\"key\":\"value\"}'\n"
                       "提示: 消息内容请用单引号包裹 JSON",
            "time": get_current_time()
        }))
        return True

    # topic 是第二部分
    topic = parts[1]
    msg_and_env = parts[2]

    # 默认环境
    env = "test"
    message_body = msg_and_env

    # 检查最后一个词是否是环境
    words = msg_and_env.rsplit(maxsplit=1)
    if len(words) == 2 and words[1] in ['dev', 'test', 'uat']:
        env = words[1]
        message_body = words[0]

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
    用法: /mq-recent <topic> [minutes] [env]
    示例: /mq-recent test%nt_cargo 10
    示例: /mq-recent test%nt_cargo 30 test
    """
    parts = content.split()
    if len(parts) < 2:
        await websocket.send(json.dumps({
            "type": "system",
            "content": "❌ 用法: /mq-recent <topic> [minutes] [env]\n示例: /mq-recent test%nt_cargo 10",
            "time": get_current_time()
        }))
        return True

    # 默认值
    env = "test"
    minutes = 60

    # 从后往前解析
    i = len(parts) - 1

    # 1. 检查最后一个是否是环境
    if i >= 1 and parts[i] in ['dev', 'test', 'uat']:
        env = parts[i]
        i -= 1

    # 2. 检查当前是否是数字（分钟数）
    if i >= 1 and parts[i].isdigit():
        minutes = int(parts[i])
        i -= 1

    # 3. 剩余部分都是 topic
    if i >= 1:
        topic = ' '.join(parts[1:i + 1])
    else:
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

    reply = f"📥 Topic [{topic}] 最近 {minutes} 分钟\n"
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
    用法: /mq-query <topic> <field=value> [minutes] [env]
    示例: /mq-query test%nt_cargo shipperName=货老板 10
    示例: /mq-query test%nt_cargo cargoName=钢材 30 test
    """
    parts = content.split()
    if len(parts) < 3:
        await websocket.send(json.dumps({
            "type": "system",
            "content": "❌ 用法: /mq-query <topic> <field=value> [minutes] [env]\n"
                       "示例: /mq-query test%nt_cargo shipperName=货老板 10\n"
                       "示例: /mq-query test%nt_cargo cargoName=钢材 30 test",
            "time": get_current_time()
        }))
        return True

    # 从后往前解析参数
    # 默认值
    env = "test"
    minutes = 60
    condition = ""
    topic_parts = []

    i = len(parts) - 1

    # 1. 检查最后一个参数是否是环境
    if i >= 1 and parts[i] in ['dev', 'test', 'uat']:
        env = parts[i]
        i -= 1

    # 2. 检查当前参数是否是数字（分钟数）
    if i >= 1 and parts[i].isdigit():
        minutes = int(parts[i])
        i -= 1

    # 3. 现在 parts[i] 应该是条件（field=value）
    # 条件可能包含 =，所以从后往前找包含 = 的参数
    condition_idx = -1
    for j in range(i, 0, -1):
        if '=' in parts[j]:
            condition_idx = j
            condition = parts[j]
            break

    if condition_idx == -1:
        await websocket.send(json.dumps({
            "type": "system",
            "content": "❌ 条件格式错误，请使用 field=value 格式\n示例: shipperName=货老板",
            "time": get_current_time()
        }))
        return True

    # 4. 条件之前的参数都是 topic 的一部分
    if condition_idx > 1:
        topic = ' '.join(parts[1:condition_idx])
    else:
        topic = parts[1]

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

    # 记录解析结果（调试用）
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
        reply += f"  时间范围: 最近 {minutes} 分钟\n"
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
        reply += f"  时间范围: 最近 {minutes} 分钟\n"
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
    reply += f"  时间范围: 最近 {minutes} 分钟\n"
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
    """
    parts = content.split()
    if len(parts) < 2:
        await websocket.send(json.dumps({
            "type": "system",
            "content": "❌ 用法: /mq-create <topic> [env]\n示例: /mq-create test_my_topic",
            "time": get_current_time()
        }))
        return True

    topic = parts[1]
    env = parts[2] if len(parts) > 2 else "test"

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

    topic = parts[1]
    env = parts[2] if len(parts) > 2 else "test"

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
