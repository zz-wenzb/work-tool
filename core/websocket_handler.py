# core/websocket_handler.py

import json
import asyncio
from datetime import datetime
import traceback
import sys
import os
import logging
import uuid

# 配置日志
logger = logging.getLogger(__name__)

# 导入本地模块
from core.deploy_manager import run_deploy_task
from core.monitor_manager import run_monitor_task
from core.task_manager import task_manager
from core.token_api import app_start, vue_nt_start, redis_migrate

# 【新增】导入云效 API
try:
    from core.async_cloud_efficiency_api import get_all_apps
except ImportError:
    logger.warning("未找到 async_cloud_efficiency_api，项目列表功能将不可用")
    get_all_apps = None

# https://help.aliyun.com/zh/yunxiao/developer-reference/createpipelinerun?spm=a2c4g.11186623.help-menu-150040.d_5_0_8_3_0.76275ce7nUFLQV

# 动态添加项目根目录
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from config.monitor_config import MONITOR_CONFIG
except ImportError as e:
    logger.error(f"[ERROR] 无法加载 monitor_config: {e}")
    MONITOR_CONFIG = {}

# --- 全局变量：动态项目列表 ---
DYNAMIC_PROJECTS = []
DYNAMIC_DEPLOY_COMMANDS = {}  # 存储动态生成的命令映射 { "/d1": {config...}, ... }

# 【新增】Archery 实例数据库配置
ARCHERY_INSTANCES = [
    {
        'id': 'baoqi',
        'label': 'RDS-baoqi',
        'databases': [
            {'id': 'tms', 'full': 'zhongbao-tms'}
        ]
    },
    {
        'id': 'oas',
        'label': 'RDS-oas',
        'databases': [
            {'id': 'oas', 'full': 'zhongbao-oas'}
        ]
    },
    {
        'id': 'lorry',
        'label': 'RDS-lorry',
        'databases': [
            {'id': 'lorry', 'full': 'zhongbao-lorry'},
            {'id': 'lorry-order', 'full': 'zhongbao-lorry-order'},
            {'id': 'lorry-marketing', 'full': 'zhongbao-lorry-marketing'},
            {'id': 'cargo', 'full': 'zhongbao-cargo'}
        ]
    }
]

# 生成命令映射: /baoqi -> 实例信息
ARCHERY_COMMANDS = {}
for inst in ARCHERY_INSTANCES:
    cmd = f"/{inst['id']}"
    ARCHERY_COMMANDS[cmd] = {
        'instance_id': inst['id'],
        'label': inst['label'],
        'databases': {db['id']: db['full'] for db in inst['databases']}
    }


# 【新增】处理 Archery 查询命令 (简化版)
async def handle_archery_query(websocket, content, cmd):
    """
    处理 Archery 查询命令
    格式: /baoqi tms SELECT * FROM table
    或: /baoqi SELECT * FROM table (如果只有一个数据库则自动使用)
    """
    # 去掉命令部分
    rest = content[len(cmd):].strip()
    if not rest:
        await websocket.send(json.dumps({
            "type": "system",
            "content": f"❌ 请提供数据库和SQL语句\n示例: {cmd} tms SELECT * FROM users",
            "time": get_current_time()
        }))
        return

    cmd_info = ARCHERY_COMMANDS.get(cmd)
    if not cmd_info:
        await websocket.send(json.dumps({
            "type": "system",
            "content": f"❌ 未知的实例: {cmd}",
            "time": get_current_time()
        }))
        return

    # 解析参数: 第一个词可能是数据库名，也可能是SQL
    parts = rest.split(maxsplit=1)
    if len(parts) < 2:
        await websocket.send(json.dumps({
            "type": "system",
            "content": f"❌ 请同时提供数据库名和SQL语句\n示例: {cmd} tms SELECT * FROM users",
            "time": get_current_time()
        }))
        return

    first_part = parts[0]
    sql = parts[1]

    # 检查第一个参数是否是数据库名
    if first_part in cmd_info['databases']:
        database_short = first_part
        database_full = cmd_info['databases'][database_short]
    else:
        # 如果只有一个数据库，且第一个参数不是数据库名，则把第一个参数当作SQL的一部分
        db_list = list(cmd_info['databases'].keys())
        if len(db_list) == 1:
            database_short = db_list[0]
            database_full = cmd_info['databases'][database_short]
            # 把第一个参数拼回SQL
            sql = f"{first_part} {sql}"
        else:
            valid_dbs = ", ".join(db_list)
            await websocket.send(json.dumps({
                "type": "system",
                "content": f"❌ 请指定数据库名 ({valid_dbs})\n示例: {cmd} tms SELECT * FROM users",
                "time": get_current_time()
            }))
            return

    # 【占位】这里调用实际的 Archery 查询逻辑
    # result = await run_archery_query(cmd_info['instance_id'], database_full, sql)

    reply_content = (
        f"🔍 Archery 查询请求已收到\n"
        f"实例: {cmd_info['label']}\n"
        f"数据库: {database_full}\n"
        f"SQL: {sql}\n"
        f"\n【功能待实现】查询结果将在这里显示"
    )

    await websocket.send(json.dumps({
        "type": "system",
        "content": reply_content,
        "time": get_current_time()
    }))



async def init_dynamic_projects():
    """初始化时获取所有项目并生成命令映射"""
    if not get_all_apps:
        return

    logger.info("[初始化] 正在从云效获取全部项目列表...")
    try:
        apps = await get_all_apps()
        if isinstance(apps, list):
            DYNAMIC_PROJECTS.extend(apps)

            # 为每个项目自动生成一个部署命令 (如果配置中没有硬编码覆盖)
            next_id = 100  # 动态项目从 /d100 开始，避免冲突

            for app in apps:
                app_name = app.get('name', '')
                app_sn = app.get('sn', '')

                if not app_name:
                    continue

                # 检查是否已经在静态配置中存在 (通过服务名匹配等逻辑可在此扩展)
                # 这里简单起见，直接为所有云效项目生成动态命令
                cmd_key = f"d{next_id}"
                cmd_str = f"/{cmd_key}"

                # 构造一个临时的配置对象
                # 注意：run_deploy_task 需要特定的 cfg 结构，这里假设它需要 'service', 'branch' 等
                # 你需要根据实际的 run_deploy_task 需求调整这里的字典结构
                dynamic_cfg = {
                    "service": app_name,
                    "app_sn": app_sn,  # 传递 sn 给部署任务使用
                    "branch": "main",  # 默认分支，或者从其他地方获取
                    "is_dynamic": True,  # 标记是动态生成的
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


# 在模块加载时尝试启动初始化任务 (确保事件循环存在)
try:
    loop = asyncio.get_running_loop()
    loop.create_task(init_dynamic_projects())
except RuntimeError:
    # 如果还没有事件循环（例如直接导入脚本），需要在主程序启动时调用 init_dynamic_projects
    pass


# 合并静态和动态命令用于处理逻辑
def get_all_deploy_commands():
    merged = dict(DYNAMIC_DEPLOY_COMMANDS)
    return merged


MONITOR_COMMANDS = {}
for key, cfg in MONITOR_CONFIG.items():
    if key.startswith('m') and key[1:].isdigit():
        MONITOR_COMMANDS[f"/{key}"] = cfg

# 全局连接客户端字典
connected_clients = {}


def get_current_time():
    return datetime.now().strftime("%H:%M:%S")


async def handle_client(websocket):
    client_ip = websocket.remote_address[0] if hasattr(websocket, 'remote_address') else 'unknown'
    logger.info(f"[客户端连接] IP={client_ip}")

    # 连接成功后，如果是第一个用户，可以再次触发刷新（可选）
    if not DYNAMIC_PROJECTS and get_all_apps:
        asyncio.create_task(init_dynamic_projects())

    try:
        async for message in websocket:
            data = json.loads(message)
            msg_type = data.get("type")
            logger.debug(f"[接收消息] IP={client_ip}, 类型={msg_type}")

            if msg_type == "join":
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

                # 【修改后】发送最新的项目列表给前端
                # 直接发送完整的 DYNAMIC_DEPLOY_COMMANDS 字典，保留所有字段 (service, branch, app_sn 等)
                if DYNAMIC_PROJECTS or DYNAMIC_DEPLOY_COMMANDS:
                    await websocket.send(json.dumps({
                        "type": "project_list",
                        "data": DYNAMIC_PROJECTS,
                        "dynamic_commands": DYNAMIC_DEPLOY_COMMANDS,  # <-- 直接发送完整对象
                        "time": get_current_time()
                    }))

                # 广播加入消息
                join_msg = {
                    "type": "system",
                    "content": f"【{nickname}】加入了聊天室",
                    "time": get_current_time()
                }
                await broadcast(json.dumps(join_msg), exclude=websocket)

            elif msg_type == "chat":
                content = data.get("content", "").strip()
                if not content:
                    continue

                nickname = getattr(websocket, 'nickname', '匿名')

                if content.startswith("/"):
                    cmd = content.split()[0]

                    # 合并命令查找表
                    all_deploy_cmds = get_all_deploy_commands()

                    if cmd == "/users":
                        user_list = [connected_clients[ws]['nickname'] for ws in connected_clients]
                        reply_content = "👥 在线用户:\n" + "\n".join(
                            f"• {name}" for name in user_list) if user_list else "• 无"
                        await websocket.send(
                            json.dumps({"type": "system", "content": reply_content, "time": get_current_time()}))

                    elif cmd == "/token-app":
                        parts = content.split()
                        username = parts[1] if len(parts) > 1 else None
                        password = parts[2] if len(parts) > 2 else None
                        token, refresh_token = app_start(username, password)
                        reply_content = f"Authorization:\n{token}\n\nR-Authorization:\n{refresh_token}"
                        await websocket.send(
                            json.dumps({"type": "system", "content": reply_content, "time": get_current_time()}))

                    elif cmd == "/token-vue-nt":
                        parts = content.split()
                        username = parts[1] if len(parts) > 1 else None
                        password = parts[2] if len(parts) > 2 else None
                        token, refresh_token = vue_nt_start(username, password)
                        reply_content = f"Authorization:\n{token}\n\nR-Authorization:\n{refresh_token}"
                        await websocket.send(
                            json.dumps({"type": "system", "content": reply_content, "time": get_current_time()}))

                    elif cmd in all_deploy_cmds:
                        cfg = all_deploy_cmds[cmd]
                        task_id = f"deploy_{cmd}_{uuid.uuid4().hex[:8]}"
                        logger.info(
                            f"[部署命令] 客户端={nickname}, 命令={cmd}, 任务ID={task_id}, 服务={cfg.get('service')}")
                        await task_manager.add_task(task_id, run_deploy_task, cfg, cmd)

                    elif cmd in MONITOR_COMMANDS:
                        cfg = MONITOR_COMMANDS[cmd]
                        task_id = f"monitor_{cmd}_{uuid.uuid4().hex[:8]}"
                        logger.info(f"[监控命令] 客户端={nickname}, 命令={cmd}, 任务ID={task_id}")
                        await task_manager.add_task(task_id, run_monitor_task, cfg, cmd)

                    elif cmd == "/redis-migrate":
                        reply_content = redis_migrate()
                        await websocket.send(
                            json.dumps({"type": "system", "content": reply_content, "time": get_current_time()}))


                    # 【新增】处理 Archery 查询命令
                    elif cmd in ARCHERY_COMMANDS:
                        await handle_archery_query(websocket, content, cmd)
                    elif cmd == "/help":

                        help_text = "📋 可用命令:\n"

                        help_text += "• /users — 查看在线用户\n"

                        help_text += "• /help — 显示此帮助\n"
                        # 【新增】在帮助信息中添加 Archery 命令
                        help_text += "\n\n🔍 Archery 查询命令:\n"
                        for cmd, info in ARCHERY_COMMANDS.items():
                            dbs = ", ".join(info['databases'].keys())
                            help_text += f"  {cmd} — {info['label']} (数据库: {dbs})\n"
                        help_text += "  用法: /<实例> <数据库> <SQL语句>\n"
                        help_text += "  示例: /baoqi tms SELECT * FROM users\n"

                        # 【新增】Token 获取命令介绍

                        help_text += "\n\n🔑 获取 Token 命令:\n"

                        help_text += "• /token-app [用户名] [密码] — 获取 App 端 Token\n"

                        help_text += "• /token-vue-nt [用户名] [密码] — 获取 Vue/NT 端 Token\n"

                        help_text += "  (注：用户名和密码可选，若不提供可能使用默认配置或提示错误)"

                        # 动态部署命令

                        if DYNAMIC_DEPLOY_COMMANDS:

                            help_text += f"\n\n🌐 动态项目部署 (共{len(DYNAMIC_DEPLOY_COMMANDS)}个):"

                            # 只显示前 10 个，避免消息太长

                            count = 0

                            for c, cfg in DYNAMIC_DEPLOY_COMMANDS.items():

                                if count >= 10:
                                    help_text += f"\n  ... 还有 {len(DYNAMIC_DEPLOY_COMMANDS) - 10} 个项目 (请在左侧面板查看)"

                                    break

                                svc = cfg.get('service', 'Unknown')

                                help_text += f"\n  {c} → {svc}"

                                count += 1

                        # 监控命令 (如果需要也可以取消注释)

                        # if MONITOR_COMMANDS:

                        #     help_text += "\n\n📊 监控发版命令:"

                        #     for c, cfg in MONITOR_COMMANDS.items():

                        #         svc = cfg.get('service', 'Unknown')

                        #         help_text += f"\n  {c} → {svc}"

                        help_text += "\n\n💡 提示：点击左侧或右侧面板的命令可直接填入输入框。"

                        await websocket.send(

                            json.dumps({"type": "system", "content": help_text, "time": get_current_time()}))


                    else:
                        await websocket.send(json.dumps({"type": "error", "content": "❌ 未知命令。输入 /help 查看帮助。",
                                                         "time": get_current_time()}))
                else:
                    chat_msg = {"type": "chat", "nickname": nickname, "content": content, "time": get_current_time()}
                    await broadcast(json.dumps(chat_msg))

            else:
                await websocket.send(
                    json.dumps({"type": "error", "content": "未知消息类型", "time": get_current_time()}))

    except Exception as e:
        logger.error(f"[WS ERROR] 客户端处理异常:", exc_info=True)
    finally:
        client_ip = websocket.remote_address[0] if hasattr(websocket, 'remote_address') else 'unknown'
        if websocket in connected_clients:
            nickname = connected_clients[websocket]['nickname']
            connected_clients.pop(websocket, None)
            logger.info(f"[客户端断开] IP={client_ip}, 用户={nickname}")
            leave_msg = {"type": "system", "content": f"【{nickname}】离开了聊天室", "time": get_current_time()}
            await broadcast(json.dumps(leave_msg))


# 在文件顶部的导入区域，可以预留一个位置
# from core.archery_api import run_archery_query # 未来实现时再导入

# 【新增】定义一个占位函数
async def run_archery_query(query_sql):
    """
    执行 Archery 查询的占位函数
    未来在这里实现具体的查询逻辑
    """
    # 这里只是一个框架，返回一个提示信息
    return f"【功能待实现】已收到查询请求，SQL内容为: {query_sql}"


async def broadcast(message, exclude=None):
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
