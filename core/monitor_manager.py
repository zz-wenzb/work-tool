import time
import asyncio
import logging
from core.async_cloud_efficiency_api import (
    release_workflows_list_test,
    release_workflow_execution_list
)
from utils.broadcast import broadcast
from datetime import datetime
from core.we_com_notify import WeComNotifier

# 配置日志
logger = logging.getLogger(__name__)


def now_str():
    return datetime.now().strftime("%H:%M:%S")



async def run_monitor_task(monitor_info: dict, command_str: str):
    service_name = monitor_info['service']
    logger.info(f"开始执行监控任务: 服务={service_name}, 命令={command_str}, 过程={monitor_info['process']}")
    await broadcast({
        "type": "system",
        "content": f"🚀 正在监控服务 [{service_name}]（命令: {command_str}），请稍等...",
        "time": now_str()
    })

    # notifier = WeComNotifier()
    max_retries = 30  # 最多等待 30 分钟 (30 * 20s)
    retry_count = 0
    logger.info(f"获取工作流: 服务={service_name}, 过程={monitor_info['process']}")
    workflow = await release_workflows_list_test(service_name, monitor_info['process'])
    if workflow is None or workflow.sn is None or workflow.releaseStages[0].sn is None:
        logger.warning(f"未找到有效的工作流配置: 服务={service_name}, 过程={monitor_info['process']}")
        # notifier.notify_no_workflow(service_name)
        await broadcast({
            "type": "system",
            "content": f"❗ 配置缺失警告 服务 [{service_name}] ",
            "time": now_str()
        })
        return
    else:
        logger.info(f"获取工作流成功: 服务={service_name}, 工作流={workflow.sn}, 阶段={workflow.releaseStages[0].sn}")

    logger.info(f"开始轮询监控: 服务={service_name}, 最大重试次数={max_retries}")
    while retry_count < max_retries:
        try:
            logger.debug(f"轮询第 {retry_count+1} 次: 服务={service_name}")
            data = await release_workflow_execution_list(
                service_name,
                workflow.sn,
                workflow.releaseStages[0].sn
            )
            logger.debug(f"获取执行数据: {data}")
            # {'number': '10', 'state': 'RUNNING', 'triggerMode': 'MANUAL', 'startTime': None, 'endTime': None}
            current_date = datetime.now().strftime('%Y-%m-%d')
            raw_start_time = data.get('startTime', '')
            if data['state'] in ['RUNNING']:
                logger.info(f"   → {service_name} 状态: {data['state']} (继续等待...)")
            elif raw_start_time[:10] != current_date:
                logger.info(f"   → {service_name} 今天未部署: {raw_start_time[:10]} != {current_date}")
                # notifier.notify_check_failed(service_name, "")
                await broadcast({
                    "type": "system",
                    "content": f"⚠️ 今天未部署 服务 [{service_name}]",
                    "time": now_str()
                })
                return
            elif data['state'] in ['SUCCESS']:
                logger.info(f"   → {service_name} 部署成功")
                # raw_end_time = data.get('endTime', '')
                # deploy_time = parse_iso_to_local(raw_end_time)
                # notifier.notify_deploy_success(service_name, "prod", deploy_time)
                await broadcast({
                    "type": "system",
                    "content": f"🚀  应用部署成功 服务 [{service_name}]",
                    "time": now_str()
                })
                return
            elif data['state'] in ['FAIL', 'FAILED']:
                logger.warning(f"   → {service_name} 部署失败")
                # notifier.notify_deploy_failed(service_name, "流水线执行失败")
                await broadcast({
                    "type": "system",
                    "content": f"❌ 应用部署失败 服务 [{service_name}]",
                    "time": now_str()
                })
                return
            else:
                logger.info(f"   → {service_name} 状态: {data['state']} (继续等待...)")

            await asyncio.sleep(20)
            retry_count += 1

        except Exception as e:
            logger.error(f"[轮询异常] 服务={service_name}, 错误={e}")
            await asyncio.sleep(20)
            retry_count += 1

    logger.warning(f"监控任务超时: 服务={service_name}, 尝试次数={max_retries}")
    # 超时处理
    # notifier.notify_timeout(service_name)
    await broadcast({
        "type": "system",
        "content": f"⏳ 部署超时提醒 服务 [{service_name}]",
        "time": now_str()
    })