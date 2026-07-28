# core/xxl_job_client.py
import json
import os
import pickle
import requests
from typing import Dict, Optional, List, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# ============================================================
# 配置区域
# ============================================================
XXL_ENV_CONFIG = {
    'dev': {
        'base_url': 'http://192.168.1.22:9561',
        'username': 'admin',
        'password': '123456'
    },
    'test': {
        'base_url': 'http://xxl-job-test.zhongbaozhiyun.com:9012/xxl-job-admin',
        'username': 'zhongbaojob',
        'password': 'zhongbaoJob0411'
    },
    'uat': {
        'base_url': 'http://xxl-job-uat.zhongbaozhiyun.com:9013/xxl-job-admin',
        'username': 'zhongbaojob',
        'password': 'zhongbaoJob0411'
    },
    'prod': {
        'base_url': 'http://prod-xxl-job-lorry.zhongbaozhiyun.com',
        'username': 'zhongbaojob',
        'password': 'zhongbaoJob0411'
    }
}

DEFAULT_XXL_ENV = 'test'
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'cache')
os.makedirs(CACHE_DIR, exist_ok=True)


class XXLJobClient:
    """XXL-JOB 管理端客户端"""

    def __init__(self, env: str = None):
        if env is None:
            env = DEFAULT_XXL_ENV
        if env not in XXL_ENV_CONFIG:
            raise ValueError(f"不支持的环境: {env}，可选: {list(XXL_ENV_CONFIG.keys())}")

        self.env = env
        self.config = XXL_ENV_CONFIG[env]
        self.base_url = self.config['base_url']
        self.username = self.config['username']
        self.password = self.config['password']

        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'X-Requested-With': 'XMLHttpRequest'
        })

        self._cookie_file = os.path.join(CACHE_DIR, f'xxljob_cookies_{env}.pkl')
        self._load_cookies()

    def _load_cookies(self) -> bool:
        """从文件加载 cookies"""
        if not os.path.exists(self._cookie_file):
            return False
        try:
            with open(self._cookie_file, 'rb') as f:
                cookies_dict = pickle.load(f)
                for name, value in cookies_dict.items():
                    self.session.cookies.set(name, value)
            return True
        except Exception as e:
            logger.warning(f"加载 XXL-JOB cookies 失败: {e}")
            return False

    def _save_cookies(self):
        """保存 cookies 到文件"""
        try:
            cookies_dict = {name: value for name, value in self.session.cookies.items()}
            with open(self._cookie_file, 'wb') as f:
                pickle.dump(cookies_dict, f)
        except Exception as e:
            logger.warning(f"保存 XXL-JOB cookies 失败: {e}")

    def _is_session_valid(self) -> bool:
        """验证 session 是否有效"""
        try:
            resp = self.session.post(
                self.base_url + '/jobgroup/pageList',
                data={'start': 0, 'length': 1},
                timeout=5
            )
            if resp.status_code == 200:
                result = resp.json()
                return result.get('code') == 200 or 'data' in result
            return False
        except Exception:
            return False

    def login(self, force: bool = False) -> bool:
        """登录 XXL-JOB 管理端"""
        if not force and self._is_session_valid():
            return True

        try:
            login_url = self.base_url + '/login'
            data = {'userName': self.username, 'password': self.password}
            resp = self.session.post(login_url, data=data, timeout=10)

            if resp.status_code == 200:
                try:
                    result = resp.json()
                    if result.get('code') == 200:
                        self._save_cookies()
                        return True
                except json.JSONDecodeError:
                    if '登录成功' in resp.text or 'xxl-job' in resp.text.lower():
                        self._save_cookies()
                        return True
            elif resp.status_code == 302:
                self._save_cookies()
                return True

            return False
        except requests.RequestException as e:
            logger.error(f"XXL-JOB 登录失败: {e}")
            return False

    def _ensure_login(self):
        """确保已登录"""
        if not self._is_session_valid():
            if not self.login():
                raise Exception("XXL-JOB 登录失败，请检查配置")

    # ==================== 执行器相关 ====================

    def get_executors(self, keywords: List[str] = None) -> List[Dict[str, Any]]:
        """获取执行器列表"""
        self._ensure_login()
        executors = []
        start = 0
        page_size = 50

        while True:
            try:
                resp = self.session.post(
                    self.base_url + '/jobgroup/pageList',
                    data={'appname': '', 'title': '', 'start': start, 'length': page_size},
                    timeout=10
                )
                result = resp.json()
                if result.get('data'):
                    executors.extend(result['data'])
                total = result.get('recordsTotal', 0)
                if start + page_size >= total:
                    break
                start += page_size
            except Exception as e:
                logger.error(f"获取执行器列表失败: {e}")
                break

        if keywords:
            filtered = []
            for executor in executors:
                title = executor.get('title', '')
                for keyword in keywords:
                    if keyword in title:
                        filtered.append(executor)
                        break
            return filtered
        return executors

    def get_executor_by_id(self, executor_id: int) -> Optional[Dict[str, Any]]:
        """根据 ID 获取执行器"""
        executors = self.get_executors()
        for executor in executors:
            if executor.get('id') == executor_id:
                return executor
        return None

    def get_executor_by_title(self, title: str) -> Optional[Dict[str, Any]]:
        """根据标题获取执行器"""
        executors = self.get_executors()
        for executor in executors:
            if executor.get('title') == title:
                return executor
        return None

    # ==================== 任务相关 ====================

    def get_tasks(self,
                  job_group: int = None,
                  job_desc: str = None,
                  executor_handler: str = None,
                  author: str = None,
                  trigger_status: int = -1,
                  page_size: int = 50) -> List[Dict[str, Any]]:
        """获取任务列表"""
        self._ensure_login()

        if job_group is None:
            # 查询所有执行器的任务
            all_tasks = []
            executors = self.get_executors()
            for executor in executors:
                tasks = self._fetch_tasks_by_group(
                    executor['id'], job_desc, executor_handler,
                    author, trigger_status, page_size
                )
                all_tasks.extend(tasks)
            return all_tasks

        return self._fetch_tasks_by_group(
            job_group, job_desc, executor_handler,
            author, trigger_status, page_size
        )

    def _fetch_tasks_by_group(self,
                              job_group: int,
                              job_desc: str = None,
                              executor_handler: str = None,
                              author: str = None,
                              trigger_status: int = -1,
                              page_size: int = 50) -> List[Dict[str, Any]]:
        """获取指定执行器下的任务"""
        tasks = []
        start = 0

        while True:
            try:
                data = {
                    'jobGroup': job_group,
                    'triggerStatus': trigger_status,
                    'jobDesc': job_desc or '',
                    'executorHandler': executor_handler or '',
                    'author': author or '',
                    'start': start,
                    'length': page_size
                }
                resp = self.session.post(
                    self.base_url + '/jobinfo/pageList',
                    data=data,
                    timeout=10
                )
                result = resp.json()
                if result.get('data'):
                    tasks.extend(result['data'])
                total = result.get('recordsTotal', 0)
                if start + page_size >= total:
                    break
                start += page_size
            except Exception as e:
                logger.error(f"获取任务列表失败: {e}")
                break

        return tasks

    # ==================== 任务操作 ====================

    def trigger_task(self,
                     job_id: int,
                     executor_param: str = '',
                     address_list: str = '') -> bool:
        """触发任务执行"""
        self._ensure_login()
        try:
            data = {
                'id': job_id,
                'executorParam': executor_param,
                'addressList': address_list
            }
            resp = self.session.post(
                self.base_url + '/jobinfo/trigger',
                data=data,
                timeout=10
            )
            result = resp.json()
            return result.get('code') == 200
        except Exception as e:
            logger.error(f"触发任务失败: {e}")
            return False

    def trigger_task_by_desc(self,
                             job_desc: str,
                             executor_param: str = '',
                             job_group: int = None) -> bool:
        """根据任务描述触发任务"""
        tasks = self.get_tasks(job_group=job_group, job_desc=job_desc)
        if not tasks:
            return False
        # 精确匹配
        for task in tasks:
            if task.get('jobDesc') == job_desc:
                return self.trigger_task(task['id'], executor_param)
        return False
