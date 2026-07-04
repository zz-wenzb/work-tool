# core/archery_handler.py
import json
import logging
from datetime import datetime

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
            "content": f"❌ 请提供SQL语句\n示例: {cmd} SELECT * FROM users",
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
    database_full = cmd_info['full_name']
    instance = cmd_info['instance']

    # 【占位】这里调用实际的 Archery 查询逻辑
    # result = await run_archery_query(instance, database_full, sql)

    reply_content = (
        f"🔍 Archery 查询请求已收到\n"
        f"实例: {instance}\n"
        f"数据库: {database_full}\n"
        f"SQL: {sql}\n"
        f"\n【功能待实现】查询结果将在这里显示"
    )

    await websocket.send(json.dumps({
        "type": "system",
        "content": reply_content,
        "time": get_current_time()
    }))


async def run_archery_query(instance, database, sql):
    """
    执行 Archery 查询的占位函数
    未来在这里实现具体的查询逻辑
    """
    return f"【功能待实现】实例: {instance}, 数据库: {database}, SQL: {sql}"
