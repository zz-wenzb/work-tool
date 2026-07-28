# core/xxl_job_handler.py
import json
import logging
from datetime import datetime
from typing import List

from core.xxl_job_client import XXLJobClient, DEFAULT_XXL_ENV, XXL_ENV_CONFIG

logger = logging.getLogger(__name__)


def get_current_time():
    return datetime.now().strftime("%H:%M:%S")


# ============================================================
# 命令映射
# ============================================================
XXL_COMMANDS = {
    '/xxl-executors': '查询执行器列表',
    '/xxl-tasks': '获取任务列表',
    '/xxl-trigger': '触发任务执行',
}

XXL_HELP = """
  • /xxl-executors [关键词] [env]
    查询执行器列表，支持按标题关键词筛选
    示例: /xxl-executors                 # test 环境，所有执行器
    示例: /xxl-executors 区域化          # 筛选标题包含"区域化"
    示例: /xxl-executors 微信 uat        # uat 环境，筛选"微信"

  • /xxl-tasks <执行器ID或标题> [关键词] [env]
    获取指定执行器下的任务列表
    示例: /xxl-tasks 1                  # 执行器ID=1
    示例: /xxl-tasks 区域化服务          # 按标题查找执行器
    示例: /xxl-tasks 1 优惠券           # 筛选任务描述包含"优惠券"
    示例: /xxl-tasks 1 优惠券 uat       # uat 环境

  • /xxl-trigger <任务ID或描述> [参数] [env]
    触发任务执行
    示例: /xxl-trigger 123              # 触发任务ID=123
    示例: /xxl-trigger 数据同步任务      # 按描述触发
    示例: /xxl-trigger 123 "{\"key\":\"value\"}"  # 带参数触发
    示例: /xxl-trigger 123 参数 uat     # uat 环境
"""


def parse_env_from_args(args: List[str]) -> tuple:
    """
    从参数列表中解析环境
    返回: (剩余参数, 环境)
    """
    env = DEFAULT_XXL_ENV
    remaining = list(args)

    # 从后往前查找环境参数
    if remaining and remaining[-1] in XXL_ENV_CONFIG:
        env = remaining.pop()
    return remaining, env


async def handle_xxl_command(websocket, content: str, cmd: str) -> bool:
    """处理 XXL-JOB 命令"""
    parts = content.split()
    if not parts:
        return False

    cmd = parts[0]
    args = parts[1:] if len(parts) > 1 else []

    if cmd == '/xxl-executors':
        return await handle_xxl_executors(websocket, args)
    elif cmd == '/xxl-tasks':
        return await handle_xxl_tasks(websocket, args)
    elif cmd == '/xxl-trigger':
        return await handle_xxl_trigger(websocket, args)
    else:
        return False


async def handle_xxl_executors(websocket, args: List[str]):
    """处理 /xxl-executors 命令"""
    # 解析参数
    keywords = []
    env = DEFAULT_XXL_ENV

    for arg in args:
        if arg in XXL_ENV_CONFIG:
            env = arg
        else:
            keywords.append(arg)

    try:
        client = XXLJobClient(env=env)
        if not client.login():
            await websocket.send(json.dumps({
                "type": "system",
                "content": f"❌ [{env}] XXL-JOB 登录失败，请检查配置",
                "time": get_current_time()
            }))
            return True

        executors = client.get_executors(keywords=keywords if keywords else None)

        if not executors:
            await websocket.send(json.dumps({
                "type": "system",
                "content": f"📋 [{env}] 未找到匹配的执行器" + (f" (关键词: {', '.join(keywords)})" if keywords else ""),
                "time": get_current_time()
            }))
            return True

        lines = [f"📊 [{env}] 执行器列表 (共 {len(executors)} 个)"]
        lines.append("=" * 50)
        for i, ex in enumerate(executors, 1):
            ex_id = ex.get('id', 'N/A')
            title = ex.get('title', 'N/A')
            appname = ex.get('appname', 'N/A')
            address_list = ex.get('addressList', 'N/A')
            lines.append(f"{i:2}. ID: {ex_id} | {title}")
            lines.append(f"   AppName: {appname}")
            lines.append(f"   地址: {address_list}")
            if ex.get('registryList'):
                registry = ', '.join(ex.get('registryList', []))
                lines.append(f"   注册: {registry}")
            lines.append("-" * 50)

        await websocket.send(json.dumps({
            "type": "system",
            "content": "\n".join(lines),
            "time": get_current_time()
        }))

    except Exception as e:
        logger.error(f"XXL-JOB 查询执行器失败: {e}", exc_info=True)
        await websocket.send(json.dumps({
            "type": "system",
            "content": f"❌ 查询执行器失败: {str(e)}",
            "time": get_current_time()
        }))

    return True


async def handle_xxl_tasks(websocket, args: List[str]):
    """处理 /xxl-tasks 命令"""
    if not args:
        await websocket.send(json.dumps({
            "type": "system",
            "content": "❌ 用法: /xxl-tasks <执行器ID或标题> [关键词] [env]",
            "time": get_current_time()
        }))
        return True

    # 解析参数
    env = DEFAULT_XXL_ENV
    keywords = []
    executor_input = args[0]
    remaining = args[1:]

    # 从后往前解析环境
    if remaining and remaining[-1] in XXL_ENV_CONFIG:
        env = remaining.pop()

    # 剩余的都是关键词
    keywords = remaining

    try:
        client = XXLJobClient(env=env)
        if not client.login():
            await websocket.send(json.dumps({
                "type": "system",
                "content": f"❌ [{env}] XXL-JOB 登录失败",
                "time": get_current_time()
            }))
            return True

        # 确定 job_group
        job_group = None
        executor_title = None

        # 尝试解析为数字 ID
        if executor_input.isdigit():
            job_group = int(executor_input)
        else:
            # 按标题查找
            executor = client.get_executor_by_title(executor_input)
            if executor:
                job_group = executor['id']
                executor_title = executor.get('title')
            else:
                await websocket.send(json.dumps({
                    "type": "system",
                    "content": f"❌ 未找到执行器: {executor_input}",
                    "time": get_current_time()
                }))
                return True

        # 获取任务列表
        tasks = client.get_tasks(job_group=job_group, trigger_status=-1)

        # 关键词筛选
        if keywords:
            filtered = []
            for task in tasks:
                desc = task.get('jobDesc', '')
                for kw in keywords:
                    if kw in desc:
                        filtered.append(task)
                        break
            tasks = filtered

        if not tasks:
            await websocket.send(json.dumps({
                "type": "system",
                "content": f"📋 [{env}] 执行器 '{executor_title or job_group}' 下没有任务"
                           + (f" (关键词: {', '.join(keywords)})" if keywords else ""),
                "time": get_current_time()
            }))
            return True

        lines = [f"📋 [{env}] 任务列表: {executor_title or f'ID:{job_group}'} (共 {len(tasks)} 个)"]
        lines.append("=" * 50)
        for i, task in enumerate(tasks, 1):
            status = "✅ 运行中" if task.get('triggerStatus') == 1 else "⏸️ 已暂停"
            lines.append(f"{i:2}. ID: {task.get('id'):6} | {task.get('jobDesc', 'N/A')[:30]}")
            lines.append(f"   状态: {status} | Cron: {task.get('scheduleConf', 'N/A')}")
            lines.append(f"   Handler: {task.get('executorHandler', 'N/A')} | 作者: {task.get('author', 'N/A')}")
            if task.get('executorParam'):
                lines.append(f"   参数: {task.get('executorParam')}")
            lines.append("-" * 50)

        await websocket.send(json.dumps({
            "type": "system",
            "content": "\n".join(lines),
            "time": get_current_time()
        }))

    except Exception as e:
        logger.error(f"XXL-JOB 查询任务失败: {e}", exc_info=True)
        await websocket.send(json.dumps({
            "type": "system",
            "content": f"❌ 查询任务失败: {str(e)}",
            "time": get_current_time()
        }))

    return True


async def handle_xxl_trigger(websocket, args: List[str]):
    """处理 /xxl-trigger 命令"""
    if not args:
        await websocket.send(json.dumps({
            "type": "system",
            "content": "❌ 用法: /xxl-trigger <任务ID或描述> [参数] [env]",
            "time": get_current_time()
        }))
        return True

    # 解析参数
    env = DEFAULT_XXL_ENV
    executor_param = ''
    target = args[0]
    remaining = args[1:]

    # 从后往前解析环境
    if remaining and remaining[-1] in XXL_ENV_CONFIG:
        env = remaining.pop()

    # 剩余的是参数（如果存在）
    if remaining:
        executor_param = ' '.join(remaining)

    try:
        client = XXLJobClient(env=env)
        if not client.login():
            await websocket.send(json.dumps({
                "type": "system",
                "content": f"❌ [{env}] XXL-JOB 登录失败",
                "time": get_current_time()
            }))
            return True

        success = False
        if target.isdigit():
            # 按 ID 触发
            success = client.trigger_task(int(target), executor_param)
            desc = f"任务ID: {target}"
        else:
            # 按描述触发
            success = client.trigger_task_by_desc(target, executor_param)
            desc = f"任务描述: {target}"

        if success:
            await websocket.send(json.dumps({
                "type": "system",
                "content": f"✅ [{env}] 触发成功: {desc}" + (f" (参数: {executor_param})" if executor_param else ""),
                "time": get_current_time()
            }))
        else:
            await websocket.send(json.dumps({
                "type": "system",
                "content": f"❌ [{env}] 触发失败: {desc}，请检查任务是否存在",
                "time": get_current_time()
            }))

    except Exception as e:
        logger.error(f"XXL-JOB 触发任务失败: {e}", exc_info=True)
        await websocket.send(json.dumps({
            "type": "system",
            "content": f"❌ 触发任务失败: {str(e)}",
            "time": get_current_time()
        }))

    return True
