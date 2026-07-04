# core/command_handler.py
import json
import logging
import uuid
from datetime import datetime

from core.deploy_manager import run_deploy_task
from core.monitor_manager import run_monitor_task
from core.task_manager import task_manager
from core.token_api import app_start, vue_nt_start, redis_migrate
from core.archery_handler import ARCHERY_COMMANDS, handle_archery_query

logger = logging.getLogger(__name__)


def get_current_time():
    """获取当前时间字符串"""
    return datetime.now().strftime("%H:%M:%S")


def get_all_deploy_commands():
    """获取所有部署命令（由外部注入）"""
    from core.websocket_handler import DYNAMIC_DEPLOY_COMMANDS
    return dict(DYNAMIC_DEPLOY_COMMANDS)


def get_monitor_commands():
    """获取监控命令"""
    from core.websocket_handler import MONITOR_COMMANDS
    return MONITOR_COMMANDS


async def handle_command(websocket, content, nickname, connected_clients):
    """
    处理命令消息
    返回 True 表示命令已处理，False 表示需要继续处理
    """
    cmd = content.split()[0]
    all_deploy_cmds = get_all_deploy_commands()
    monitor_cmds = get_monitor_commands()

    # ========== 用户列表 ==========
    if cmd == "/users":
        user_list = [connected_clients[ws]['nickname'] for ws in connected_clients]
        reply_content = "👥 在线用户:\n" + "\n".join(
            f"• {name}" for name in user_list) if user_list else "• 无"
        await websocket.send(
            json.dumps({"type": "system", "content": reply_content, "time": get_current_time()}))
        return True

    # ========== Token 获取 ==========
    if cmd == "/token-app":
        parts = content.split()
        username = parts[1] if len(parts) > 1 else None
        password = parts[2] if len(parts) > 2 else None
        token, refresh_token = app_start(username, password)
        reply_content = f"Authorization:\n{token}\n\nR-Authorization:\n{refresh_token}"
        await websocket.send(
            json.dumps({"type": "system", "content": reply_content, "time": get_current_time()}))
        return True

    if cmd == "/token-vue-nt":
        parts = content.split()
        username = parts[1] if len(parts) > 1 else None
        password = parts[2] if len(parts) > 2 else None
        token, refresh_token = vue_nt_start(username, password)
        reply_content = f"Authorization:\n{token}\n\nR-Authorization:\n{refresh_token}"
        await websocket.send(
            json.dumps({"type": "system", "content": reply_content, "time": get_current_time()}))
        return True

    # ========== 部署命令 ==========
    if cmd in all_deploy_cmds:
        cfg = all_deploy_cmds[cmd]
        task_id = f"deploy_{cmd}_{uuid.uuid4().hex[:8]}"
        logger.info(f"[部署命令] 客户端={nickname}, 命令={cmd}, 任务ID={task_id}, 服务={cfg.get('service')}")
        await task_manager.add_task(task_id, run_deploy_task, cfg, cmd)
        return True

    # ========== 监控命令 ==========
    if cmd in monitor_cmds:
        cfg = monitor_cmds[cmd]
        task_id = f"monitor_{cmd}_{uuid.uuid4().hex[:8]}"
        logger.info(f"[监控命令] 客户端={nickname}, 命令={cmd}, 任务ID={task_id}")
        await task_manager.add_task(task_id, run_monitor_task, cfg, cmd)
        return True

    # ========== Redis 迁移 ==========
    if cmd == "/redis-migrate":
        reply_content = redis_migrate()
        await websocket.send(
            json.dumps({"type": "system", "content": reply_content, "time": get_current_time()}))
        return True

    # ========== Archery 查询 ==========
    if cmd in ARCHERY_COMMANDS:
        await handle_archery_query(websocket, content, cmd)
        return True

    # ========== 帮助 ==========
    if cmd == "/help":
        await handle_help(websocket)
        return True

    # 未知命令
    return False


async def handle_help(websocket):
    """处理 /help 命令"""
    from core.websocket_handler import DYNAMIC_DEPLOY_COMMANDS
    from core.archery_handler import ARCHERY_COMMANDS, ARCHERY_INSTANCES

    help_text = "📋 可用命令:\n"
    help_text += "• /users — 查看在线用户\n"
    help_text += "• /help — 显示此帮助\n"

    # Archery 命令
    help_text += "\n\n🔍 Archery 查询命令:\n"
    for cmd, info in ARCHERY_COMMANDS.items():
        dbs = ", ".join(info['databases'].keys())
        help_text += f"  {cmd} — {info['label']} (数据库: {dbs})\n"
    help_text += "  用法: /<实例> <数据库> <SQL语句>\n"
    help_text += "  示例: /baoqi tms SELECT * FROM users\n"

    # Token 命令
    help_text += "\n\n🔑 获取 Token 命令:\n"
    help_text += "• /token-app [用户名] [密码] — 获取 App 端 Token\n"
    help_text += "• /token-vue-nt [用户名] [密码] — 获取 Vue/NT 端 Token\n"
    help_text += "  (注：用户名和密码可选，若不提供可能使用默认配置或提示错误)"

    # 动态部署命令
    if DYNAMIC_DEPLOY_COMMANDS:
        help_text += f"\n\n🌐 动态项目部署 (共{len(DYNAMIC_DEPLOY_COMMANDS)}个):"
        count = 0
        for c, cfg in DYNAMIC_DEPLOY_COMMANDS.items():
            if count >= 10:
                help_text += f"\n  ... 还有 {len(DYNAMIC_DEPLOY_COMMANDS) - 10} 个项目 (请在左侧面板查看)"
                break
            svc = cfg.get('service', 'Unknown')
            help_text += f"\n  {c} → {svc}"
            count += 1

    help_text += "\n\n💡 提示：点击左侧或右侧面板的命令可直接填入输入框。"

    await websocket.send(
        json.dumps({"type": "system", "content": help_text, "time": get_current_time()}))