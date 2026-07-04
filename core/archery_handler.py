# core/archery_handler.py
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# ---------- Archery 实例数据库配置 ----------
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


def get_current_time():
    """获取当前时间字符串"""
    return datetime.now().strftime("%H:%M:%S")


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


async def run_archery_query(query_sql):
    """
    执行 Archery 查询的占位函数
    未来在这里实现具体的查询逻辑
    """
    return f"【功能待实现】已收到查询请求，SQL内容为: {query_sql}"
