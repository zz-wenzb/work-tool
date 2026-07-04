# core/websocket_handler.py
import json
import asyncio
import sys
import os
import logging
from datetime import datetime

from core.deploy_manager import run_deploy_task
from core.monitor_manager import run_monitor_task
from core.task_manager import task_manager
from core.token_api import app_start, vue_nt_start, redis_migrate
from core.command_handler import handle_command
from core.archery_handler import ARCHERY_COMMANDS, ARCHERY_INSTANCES

# 配置日志
logger = logging.getLogger(__name__)

# 导入云效 API
try:
    from core.async_cloud_efficiency_api import get_all_apps
except ImportError:
    logger.warning("未找到 async_cloud_efficiency_api，项目列表功能将不可用")
    get_all_apps = None

# 动态添加项目根目录
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from config.monitor_config import MONITOR_CONFIG
except ImportError as e:
    logger.error(f"[ERROR] 无法加载 monitor_config: {e}")
    MONITOR_CONFIG = {}

# --- 全局变量 ---
DYNAMIC_PROJECTS = []
DYNAMIC_DEPLOY_COMMANDS = {}

# --- 监控命令映射 ---
MONITOR_COMMANDS = {}
for key, cfg in MONITOR_CONFIG.items():
    if key.startswith('m') and key[1:].isdigit():
        MONITOR_COMMANDS[f"/{key}"] = cfg

# --- 全局连接客户端 ---
connected_clients = {}


def get_current_time():
    return datetime.now().strftime("%H:%M:%S")


async def init_dynamic_projects():
    """初始化时获取所有项目并生成命令映射"""
    if not get_all_apps:
        return

    logger.info("[初始化] 正在从云效获取全部项目列表...")
    try:
        apps = await get_all_apps()
        if isinstance(apps, list):
            DYNAMIC_PROJECTS.extend(apps)
            next_id = 100

            for app in apps:
                app_name = app.get('name', '')
                app_sn = app.get('sn', '')

                if not app_name:
                    continue

                cmd_key = f"d{next_id}"
                cmd_str = f"/{cmd_key}"

                dynamic_cfg = {
                    "service": app_name,
                    "app_sn": app_sn,
                    "branch": "main",
                    "is_dynamic": True,
                    "source": "yunxiao_api"
                }

                DYNAMIC_DEPLOY_COMMANDS[cmd_str] = dynamic_cfg
                logger.info(f"[动态映射] {cmd_str} -> {app_name} (SN: {app_sn})")
                next_id += 1

            logger.info(
                f"[初始化] 成功加载 {len(DYNAMIC_PROJECTS)} 个项目，生成 {len(DYNAMIC_DEPLOY_COMMANDS)} 个动态命令。")
        else:
            logger.warning("[初始化] 获取到的项目列表格式不正确")
    except Exception as e:
        logger.error(f"[初始化] 获取项目列表失败: {e}", exc_info=True)


# 模块加载时尝试初始化
try:
    loop = asyncio.get_running_loop()
    loop.create_task(init_dynamic_projects())
except RuntimeError:
    pass


async def broadcast(message, exclude=None):
    """广播消息给所有客户端"""
    if not connected_clients:
        return
    clients_snapshot = list(connected_clients.keys())
    disconnected = set()
    for client in clients_snapshot:
        if exclude and client == exclude:
            continue
        try:
            await client.send(message)
        except Exception as e:
            logger.warning(f"[广播错误] 发送消息给客户端失败: {e}")
            disconnected.add(client)
    for client in disconnected:
        if client in connected_clients:
            nickname = connected_clients[client]['nickname']
            connected_clients.pop(client, None)
            logger.info(f"[连接清理] 移除断开的客户端: {nickname}")


async def handle_client(websocket):
    """处理 WebSocket 客户端连接"""
    client_ip = websocket.remote_address[0] if hasattr(websocket, 'remote_address') else 'unknown'
    logger.info(f"[客户端连接] IP={client_ip}")

    if not DYNAMIC_PROJECTS and get_all_apps:
        asyncio.create_task(init_dynamic_projects())

    try:
        async for message in websocket:
            data = json.loads(message)
            msg_type = data.get("type")
            logger.debug(f"[接收消息] IP={client_ip}, 类型={msg_type}")

            if msg_type == "join":
                await handle_join(websocket, data)
            elif msg_type == "chat":
                await handle_chat(websocket, data)
            else:
                await websocket.send(
                    json.dumps({"type": "error", "content": "未知消息类型", "time": get_current_time()}))

    except Exception as e:
        logger.error(f"[WS ERROR] 客户端处理异常:", exc_info=True)
    finally:
        await handle_disconnect(websocket)


async def handle_join(websocket, data):
    """处理加入聊天室"""
    nickname = data.get("nickname", "匿名").strip() or "匿名"
    websocket.nickname = nickname
    connected_clients[websocket] = {
        'nickname': nickname,
        'join_time': get_current_time()
    }

    # 欢迎消息
    await websocket.send(json.dumps({
        "type": "system",
        "content": f"欢迎 {nickname} 加入群聊！",
        "time": get_current_time()
    }))

    # 发送项目列表
    if DYNAMIC_PROJECTS or DYNAMIC_DEPLOY_COMMANDS:
        await websocket.send(json.dumps({
            "type": "project_list",
            "data": DYNAMIC_PROJECTS,
            "dynamic_commands": DYNAMIC_DEPLOY_COMMANDS,
            "time": get_current_time()
        }))

    # 广播加入消息
    join_msg = {
        "type": "system",
        "content": f"【{nickname}】加入了聊天室",
        "time": get_current_time()
    }
    await broadcast(json.dumps(join_msg), exclude=websocket)


async def handle_chat(websocket, data):
    """处理聊天消息"""
    content = data.get("content", "").strip()
    if not content:
        return

    nickname = getattr(websocket, 'nickname', '匿名')

    if content.startswith("/"):
        # 处理命令
        handled = await handle_command(websocket, content, nickname, connected_clients)
        if not handled:
            await websocket.send(json.dumps({
                "type": "error",
                "content": "❌ 未知命令。输入 /help 查看帮助。",
                "time": get_current_time()
            }))
    else:
        # 普通聊天消息
        chat_msg = {
            "type": "chat",
            "nickname": nickname,
            "content": content,
            "time": get_current_time()
        }
        await broadcast(json.dumps(chat_msg))


async def handle_disconnect(websocket):
    """处理客户端断开"""
    client_ip = websocket.remote_address[0] if hasattr(websocket, 'remote_address') else 'unknown'
    if websocket in connected_clients:
        nickname = connected_clients[websocket]['nickname']
        connected_clients.pop(websocket, None)
        logger.info(f"[客户端断开] IP={client_ip}, 用户={nickname}")
        leave_msg = {
            "type": "system",
            "content": f"【{nickname}】离开了聊天室",
            "time": get_current_time()
        }
        await broadcast(json.dumps(leave_msg))
