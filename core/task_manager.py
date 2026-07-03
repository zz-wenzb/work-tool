# core/task_manager.py

import asyncio
import logging
from typing import Dict, Set
from datetime import datetime

# 配置日志
logger = logging.getLogger(__name__)

class TaskManager:
    def __init__(self):
        # 存储所有活跃的任务
        self.active_tasks: Dict[str, asyncio.Task] = {}
        # 存储任务创建时间
        self.task_creation_times: Dict[str, datetime] = {}
        # 任务锁，确保线程安全
        self._lock = asyncio.Lock()
    
    async def add_task(self, task_id: str, coro, *args, **kwargs) -> bool:
        """添加一个新任务"""
        async with self._lock:
            if task_id in self.active_tasks:
                logger.warning(f"任务 {task_id} 已存在，取消旧任务")
                await self._cancel_task(task_id)
            
            task = asyncio.create_task(coro(*args, **kwargs))
            self.active_tasks[task_id] = task
            self.task_creation_times[task_id] = datetime.now()
            
            # 当任务完成时，自动清理
            task.add_done_callback(lambda t: asyncio.create_task(self._cleanup_task(task_id)))
            
            logger.info(f"添加新任务: {task_id}, 当前活跃任务数: {len(self.active_tasks)}")
            return True
    
    async def _cleanup_task(self, task_id: str):
        """清理已完成的任务"""
        async with self._lock:
            if task_id in self.active_tasks:
                task = self.active_tasks[task_id]
                # 检查任务是否异常完成
                if task.exception() is not None:
                    logger.error(f"任务 {task_id} 异常完成: {task.exception()}")
                
                self.active_tasks.pop(task_id, None)
                self.task_creation_times.pop(task_id, None)
                logger.info(f"清理任务: {task_id}, 剩余活跃任务数: {len(self.active_tasks)}")
    
    async def _cancel_task(self, task_id: str):
        """取消指定任务"""
        if task_id in self.active_tasks:
            task = self.active_tasks[task_id]
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass  # 任务被取消是正常行为
                except Exception as e:
                    logger.error(f"任务 {task_id} 取消时发生异常: {e}")
    
    async def cancel_task(self, task_id: str) -> bool:
        """取消并移除任务"""
        async with self._lock:
            if task_id in self.active_tasks:
                await self._cancel_task(task_id)
                self.active_tasks.pop(task_id, None)
                self.task_creation_times.pop(task_id, None)
                logger.info(f"手动取消任务: {task_id}")
                return True
            return False
    
    async def get_task_status(self, task_id: str) -> str:
        """获取任务状态"""
        if task_id in self.active_tasks:
            task = self.active_tasks[task_id]
            if task.done():
                logger.debug(f"任务 {task_id} 状态: completed")
                return "completed"
            elif task.cancelled():
                logger.debug(f"任务 {task_id} 状态: cancelled")
                return "cancelled"
            else:
                logger.debug(f"任务 {task_id} 状态: running")
                return "running"
        logger.debug(f"任务 {task_id} 状态: not_found")
        return "not_found"
    
    async def get_all_task_ids(self) -> Set[str]:
        """获取所有任务ID"""
        async with self._lock:
            task_ids = set(self.active_tasks.keys())
            logger.debug(f"获取所有任务ID: {len(task_ids)} 个任务")
            return task_ids
    
    async def cleanup_expired_tasks(self, max_duration_minutes: int = 60):
        """清理超过指定时间的任务"""
        async with self._lock:
            expired_tasks = []
            current_time = datetime.now()
            for task_id, creation_time in self.task_creation_times.items():
                if (current_time - creation_time).total_seconds() > max_duration_minutes * 60:
                    expired_tasks.append(task_id)
            
            for task_id in expired_tasks:
                logger.warning(f"清理超时任务: {task_id}")
                await self._cancel_task(task_id)
                self.active_tasks.pop(task_id, None)
                self.task_creation_times.pop(task_id, None)
    
    async def get_active_task_count(self) -> int:
        """获取活跃任务数量"""
        async with self._lock:
            count = len(self.active_tasks)
            logger.debug(f"当前活跃任务数量: {count}")
            return count

# 全局任务管理器实例
task_manager = TaskManager()