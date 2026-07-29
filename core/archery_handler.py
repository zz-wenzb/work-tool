# core/archery_handler.py
import json
import logging
from datetime import datetime

from core.archery_api import ArcheryAPI, format_query_result, get_session, force_reauthenticate, get_auth_status

logger = logging.getLogger(__name__)

# ---------- Archery 数据库配置 ----------
# 每个数据库直接映射到对应的实例和完整数据库名
ARCHERY_DATABASES = {
    # RDS-baoqi
    'tms': {
        'instance': 'RDS-baoqi',
        'full_name': 'zhongbao-tms'
    },
    # RDS-oas
    'oas': {
        'instance': 'RDS-oas',
        'full_name': 'zhongbao-oas'
    },
    # RDS-lorry
    'lorry': {
        'instance': 'RDS-lorry',
        'full_name': 'zhongbao-lorry'
    },
    'order': {
        'instance': 'RDS-lorry',
        'full_name': 'zhongbao-lorry-order'
    },
    'marketing': {
        'instance': 'RDS-lorry',
        'full_name': 'zhongbao-lorry-marketing'
    },
    'cargo': {
        'instance': 'RDS-lorry',
        'full_name': 'zhongbao-cargo'
    },
    'recommend': {
        'instance': 'RDS-lorry',
        'full_name': 'zhongbao-recommend'
    },
    'payment': {
        'instance': 'RDS-lorry',
        'full_name': 'zhongbao-lorry-payment'
    },
    'user': {
        'instance': 'RDS-lorry',
        'full_name': 'zhongbao-lorry-user'
    }
}

# 生成命令映射: /tms -> 数据库信息
ARCHERY_COMMANDS = {}
for db_id, info in ARCHERY_DATABASES.items():
    cmd = f"/{db_id}"
    ARCHERY_COMMANDS[cmd] = {
        'database_id': db_id,
        'instance': info['instance'],
        'full_name': info['full_name']
    }


def get_current_time():
    """获取当前时间字符串"""
    return datetime.now().strftime("%H:%M:%S")


async def handle_archery_query(websocket, content, cmd):
    """
    处理 Archery 查询命令
    格式: /tms SELECT * FROM table
    """
    # 去掉命令部分
    rest = content[len(cmd):].strip()
    if not rest:
        await websocket.send(json.dumps({
            "type": "system",
            "content": f"❌ 请提供SQL语句\n示例: {cmd} SELECT * FROM users LIMIT 10",
            "time": get_current_time()
        }))
        return

    cmd_info = ARCHERY_COMMANDS.get(cmd)
    if not cmd_info:
        await websocket.send(json.dumps({
            "type": "system",
            "content": f"❌ 未知的数据库: {cmd}",
            "time": get_current_time()
        }))
        return

    sql = rest
    instance_name = cmd_info['instance']
    db_name = cmd_info['full_name']

    try:
        # 执行查询（内部会自动处理鉴权）
        result = await execute_archery_query(instance_name, db_name, sql, limit=100)

        # 使用表格格式
        if result.get("success"):
            formatted = format_query_result(result, max_rows=10)
        else:
            error_msg = result.get('error', '未知错误')
            # 检测是否是鉴权相关的错误
            if 'login' in error_msg.lower() or 'auth' in error_msg.lower():
                formatted = f"🔐 鉴权失败: {error_msg}\n💡 请重试或联系管理员"
            else:
                formatted = f"❌ 查询失败: {error_msg}"

        await websocket.send(json.dumps({
            "type": "system",
            "content": formatted,
            "time": get_current_time()
        }))
    except Exception as e:
        logger.error(f"Archery 查询异常: {e}", exc_info=True)
        await websocket.send(json.dumps({
            "type": "system",
            "content": f"❌ 查询异常: {e}",
            "time": get_current_time()
        }))


async def execute_archery_query(instance_name: str, db_name: str, sql: str, limit: int = 100) -> dict:
    """
    执行 Archery 查询（异步包装）
    """
    try:
        # 确保会话有效
        get_session()

        # 执行查询
        result = ArcheryAPI.execute_sql_query(instance_name, db_name, sql, limit)
        return result
    except Exception as e:
        logger.error(f"执行 Archery 查询失败: {e}")
        return {"success": False, "error": str(e), "data": []}


# ================= 辅助管理函数 =================
async def handle_archery_auth_refresh(websocket):
    """
    手动刷新 Archery 鉴权
    """
    try:
        success = force_reauthenticate()
        status = get_auth_status()

        if success:
            await websocket.send(json.dumps({
                "type": "system",
                "content": f"✅ Archery 鉴权刷新成功\n{json.dumps(status, indent=2, ensure_ascii=False)}",
                "time": get_current_time()
            }))
        else:
            await websocket.send(json.dumps({
                "type": "system",
                "content": f"❌ Archery 鉴权刷新失败，请检查日志",
                "time": get_current_time()
            }))
    except Exception as e:
        logger.error(f"刷新 Archery 鉴权失败: {e}", exc_info=True)
        await websocket.send(json.dumps({
            "type": "system",
            "content": f"❌ 刷新鉴权异常: {e}",
            "time": get_current_time()
        }))


async def handle_archery_auth_status(websocket):
    """
    获取 Archery 鉴权状态
    """
    try:
        status = get_auth_status()
        await websocket.send(json.dumps({
            "type": "system",
            "content": f"🔐 Archery 鉴权状态\n{json.dumps(status, indent=2, ensure_ascii=False)}",
            "time": get_current_time()
        }))
    except Exception as e:
        logger.error(f"获取 Archery 鉴权状态失败: {e}", exc_info=True)
        await websocket.send(json.dumps({
            "type": "system",
            "content": f"❌ 获取鉴权状态异常: {e}",
            "time": get_current_time()
        }))