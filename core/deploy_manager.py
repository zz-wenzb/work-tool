# core/deploy_manager.py

import time
import asyncio
import logging
from core.async_cloud_efficiency_api import (
    get_test_workflow,
    execute_pipeline_run,
    get_pipeline_run_status
)
from utils.broadcast import broadcast
from datetime import datetime

# 配置日志
logger = logging.getLogger(__name__)

def now_str():
    return datetime.now().strftime("%H:%M:%S")

async def poll_pipeline_status(service_name: str, workflow_sn: str, stage_sn: str, pipeline_run_id: int) -> bool:
    logger.info(f"开始轮询流水线状态: 服务={service_name}, 工作流={workflow_sn}, 阶段={stage_sn}, 运行ID={pipeline_run_id}")
    max_retries = 30
    retry = 0
    while retry < max_retries:
        try:
            status = await get_pipeline_run_status(service_name, workflow_sn, stage_sn, str(pipeline_run_id))
            logger.debug(f"轮询第 {retry+1} 次: 状态={status}")
            if status == "SUCCESS":
                logger.info(f"流水线执行成功: 服务={service_name}, 运行ID={pipeline_run_id}")
                return True
            elif status in ("FAILED", "CANCELLED", "STOPPED"):
                logger.warning(f"流水线执行失败: 服务={service_name}, 状态={status}, 运行ID={pipeline_run_id}")
                return False
            await asyncio.sleep(20)
            retry += 1
        except Exception as e:
            logger.warning(f"[轮询异常] 服务={service_name}, 运行ID={pipeline_run_id}, 错误={e}")
            await asyncio.sleep(5)
            retry += 1
    logger.warning(f"轮询超时: 服务={service_name}, 运行ID={pipeline_run_id}, 尝试次数={max_retries}")
    return False

async def run_deploy_task(deploy_info: dict, command_str: str):
    service_name = deploy_info['service']
    logger.info(f"开始执行部署任务: 服务={service_name}, 命令={command_str}")
    await broadcast({
        "type": "system",
        "content": f"🚀 正在部署服务 [{service_name}]（命令: {command_str}），请稍等...",
        "time": now_str()
    })

    try:
        logger.info(f"获取测试工作流: 服务={service_name}")
        workflow = await get_test_workflow(service_name)
        if not workflow or not workflow.releaseStages:
            logger.warning(f"未找到有效的发布流程或阶段: 服务={service_name}")
            await broadcast({
                "type": "system",
                "content": "未找到有效的发布流程或阶段",
                "time": now_str()
            })
            return
        else:
            logger.info(f"获取工作流成功: 服务={service_name}, 工作流={workflow.sn}")

        pipeline_run_id = await execute_pipeline_run(
            service_name,
            '',
            '',
            workflow.sn,
            workflow.releaseStages[0].sn
        )
        logger.info(f"流水线执行已启动: 服务={service_name}, 运行ID={pipeline_run_id}")

        logger.info(f"开始轮询流水线状态: 服务={service_name}, 运行ID={pipeline_run_id}")
        success = await poll_pipeline_status(
            service_name,
            workflow.sn,
            workflow.releaseStages[0].sn,
            pipeline_run_id
        )
        logger.info(f"流水线执行完成: 服务={service_name}, 成功={success}")

        msg = f"✅ 服务 [{service_name}] 部署成功！" if success else f"❌ 服务 [{service_name}] 部署失败！请检查日志。"
        await broadcast({
            "type": "system",
            "content": msg,
            "time": now_str()
        })

    except Exception as e:
        error_msg = f"💥 部署 [{service_name}] 时发生异常: {str(e)}"
        logger.error(f"[ERROR] {error_msg}")
        await broadcast({
            "type": "system",
            "content": error_msg,
            "time": now_str()
        })