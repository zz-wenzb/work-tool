import aiohttp
import logging
import os
import json
from datetime import datetime, timedelta
from typing import List, Optional, Any, Dict

# 导入本地模型 (确保路径正确)
from models.yunxiao_models import ReleaseWorkflow, AppInfo

# 配置日志
logger = logging.getLogger(__name__)

# --- 基础配置 ---
BASE_URL = "https://openapi-rdc.aliyuncs.com"
TOKEN = "pt-yBeCsFqRbwb3O72TClURkTnr_0d4f4287-afc5-4b45-b175-4a1496468e77"
ORG_ID = "6891a3f25ca26351a77bf9af"
HEADERS = {
    "x-yunxiao-token": TOKEN,
    "Content-Type": "application/json"
}

# --- 缓存配置 ---
CACHE_DIR = "cache"
CACHE_FILE_PATH = os.path.join(CACHE_DIR, "apps_cache.json")
CACHE_EXPIRE_HOURS = 24  # 缓存有效期：24小时 (设为 0 则永久有效，直到手动删除)


def now_str():
    return datetime.now().strftime("%H:%M:%S")


# ==========================================
# 缓存处理逻辑
# ==========================================

async def load_from_cache() -> Optional[List[Any]]:
    """
    尝试从本地文件加载缓存。
    如果文件不存在或已过期，返回 None。
    """
    if not os.path.exists(CACHE_FILE_PATH):
        logger.debug(f"[缓存] 文件不存在: {CACHE_FILE_PATH}")
        return None

    try:
        with open(CACHE_FILE_PATH, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)

        # 检查过期时间
        created_at_str = cache_data.get('created_at')
        if created_at_str and CACHE_EXPIRE_HOURS > 0:
            created_at = datetime.fromisoformat(created_at_str)
            if datetime.now() - created_at > timedelta(hours=CACHE_EXPIRE_HOURS):
                logger.warning(f"[缓存] 缓存已过期 (创建时间: {created_at})，将重新从网络获取。")
                return None

        apps = cache_data.get('data', [])
        logger.info(f"[缓存] ✅ 成功加载 {len(apps)} 个项目 (来源: 本地文件)")
        return apps

    except Exception as e:
        logger.error(f"[缓存] ❌ 读取缓存失败: {e}，将重新从网络获取。")
        return None


async def save_to_cache(apps_list: List[Any]):
    """
    将获取到的数据保存到本地文件。
    """
    try:
        # 确保目录存在
        os.makedirs(CACHE_DIR, exist_ok=True)

        cache_data = {
            "created_at": datetime.now().isoformat(),
            "count": len(apps_list),
            "data": apps_list
        }

        with open(CACHE_FILE_PATH, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)

        logger.info(f"[缓存] 💾 已将 {len(apps_list)} 个项目保存到 {CACHE_FILE_PATH}")
    except Exception as e:
        logger.error(f"[缓存] ❌ 保存缓存失败: {e}")


# ==========================================
# 核心业务逻辑
# ==========================================

async def get_all_apps() -> List[Any]:
    """
    获取当前组织下的所有应用（AppStack）。
    策略：
    1. 优先加载本地缓存。
    2. 若无缓存或缓存过期，则通过 keyset 分页循环从网络获取全量数据。
    3. 网络获取成功后，自动更新缓存文件。
    """

    # 1. 尝试加载缓存
    cached_apps = await load_from_cache()
    if cached_apps is not None:
        return cached_apps

    # 2. 缓存失效，执行网络请求
    logger.info("[网络] 🌐 缓存无效，正在从云效 API 获取最新项目列表...")

    url = f"{BASE_URL}/oapi/v1/appstack/organizations/{ORG_ID}/apps:search"
    all_apps = []
    next_start_id: Optional[str] = None
    page_count = 0

    async with aiohttp.ClientSession() as session:
        while True:
            page_count += 1

            params = {
                "pagination": "keyset",
                "orderBy": "id",
                "perPage": 100,
                "sort": "asc"
            }

            if next_start_id:
                params["nextToken"] = next_start_id

            try:
                logger.debug(f"[网络] 正在获取第 {page_count} 页 (startId={next_start_id or 'None'})...")

                async with session.get(url, headers=HEADERS, params=params) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"[API ERROR] 第 {page_count} 页请求失败 ({response.status}): {error_text}")
                        break

                    result_data = await response.json()
                    logger.info(f"{result_data}")
                    apps_list = result_data.get('data', [])

                    if not apps_list:
                        logger.info(f"[网络] 第 {page_count} 页无数据，结束循环。")
                        break

                    all_apps.extend(apps_list)
                    logger.debug(f"[网络] 第 {page_count} 页获取到 {len(apps_list)} 个项目，累计 {len(all_apps)} 个。")

                    # 检查下一页标识
                    next_start_id = result_data.get('nextToken')

                    if not next_start_id:
                        logger.info(f"[网络] 未检测到 nextStartId，已获取全部数据。")
                        break

            except Exception as e:
                logger.error(f"[API ERROR] 第 {page_count} 页请求异常: {e}", exc_info=True)
                break

    total_count = len(all_apps)
    logger.info(f"[网络] ✅ 分页获取完成。共请求 {page_count} 页，总计 {total_count} 个项目。")

    # 3. 如果成功获取到数据，保存到新缓存
    if total_count > 0:
        await save_to_cache(all_apps)
    else:
        logger.warning("[警告] 网络请求未获取到任何数据，缓存未更新。")

    return all_apps


async def release_workflows_list(appName: str) -> List[ReleaseWorkflow]:
    url = f"{BASE_URL}/oapi/v1/appstack/organizations/{ORG_ID}/apps/{appName}/releaseWorkflows"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=HEADERS) as response:
                if response.status != 200:
                    logger.error(f"[API ERROR] 获取 {appName} 工作流失败: {await response.text()}")
                    return []
                workflows_data = await response.json()
                if not isinstance(workflows_data, list):
                    logger.warning(f"[API WARNING] {appName} 工作流返回格式非列表: {type(workflows_data)}")
                    return []
                return [ReleaseWorkflow(**wf) for wf in workflows_data]
        except Exception as e:
            logger.error(f"[API ERROR] 获取 {appName} 工作流异常: {e}")
            return []


async def release_workflows_list_test(appName: str, process: str):
    """查找包含特定关键词的工作流"""
    workflows = await release_workflows_list(appName)
    for workflow in workflows:
        if workflow.name and process in workflow.name:
            return workflow
    return None


async def release_workflow_execution_list(appName: str, releaseWorkflowSn: str, releaseStageSn: str):
    """获取工作流执行记录"""
    url = f"{BASE_URL}/oapi/v1/appstack/organizations/{ORG_ID}/apps/{appName}/releaseWorkflows/{releaseWorkflowSn}/releaseStages/{releaseStageSn}/executions"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=HEADERS) as response:
                if response.status != 200:
                    logger.error(f"[API ERROR] 获取 {appName} 工作流执行记录失败: {await response.text()}")
                    return None
                execution = await response.json()
                if not execution.get('data'):
                    logger.error(f"[API ERROR] {appName} 无执行记录")
                    return None
                return execution['data']
        except Exception as e:
            logger.error(f"[API ERROR] 获取 {appName} 工作流执行记录异常: {e}")
            return None


async def get_test_workflow(appName: str) -> Optional[ReleaseWorkflow]:
    """专门获取名为'测试流程'的工作流"""
    workflows = await release_workflows_list(appName)
    for wf in workflows:
        if wf.name == "测试流程":
            return wf
    return None


async def execute_pipeline_run(appName: str, gitlab_name: str, branch: str, workflow_sn: str, stage_sn: str) -> int:
    """执行流水线"""
    url = f"{BASE_URL}/oapi/v1/appstack/organizations/{ORG_ID}/apps/{appName}/releaseWorkflows/{workflow_sn}/releaseStages/{stage_sn}:execute"
    data = {"params": {"FLOW_INST_RUNNING_COMMENT": "", "branchRepoInfo": "[]"}}
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, headers=HEADERS, json=data) as response:
                response.raise_for_status()
                result = await response.json()
                if 'pipelineRunId' not in result:
                    logger.error(f"[API ERROR] 执行流水线成功但未返回 pipelineRunId: {result}")
                    raise ValueError("Missing pipelineRunId in response")
                return result['pipelineRunId']
        except Exception as e:
            logger.error(f"[API ERROR] 执行流水线异常: {e}")
            raise


async def get_pipeline_run_status(appName: str, workflow_sn: str, stage_sn: str, execution_number: str) -> str:
    """获取流水线运行状态"""
    url = f"{BASE_URL}/oapi/v1/appstack/organizations/{ORG_ID}/apps/{appName}/releaseWorkflows/{workflow_sn}/releaseStages/{stage_sn}/executions/{execution_number}:getPipelineRun"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=HEADERS) as response:
                response.raise_for_status()
                result = await response.json()
                pipeline_info = result.get("pipelineRun", {})
                return pipeline_info.get("status", "UNKNOWN")
        except Exception as e:
            logger.error(f"[API ERROR] 获取流水线状态异常: {e}")
            raise