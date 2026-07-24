# core/gitlab_fetcher.py
"""
GitLab 提交记录获取模块
"""

import logging
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Any, Set, Optional

from config.gitlab_config import (
    GITLAB_URL,
    GITLAB_TOKEN,
    DAYS,
    BRANCH_ACTIVE_DAYS,
    MAX_BRANCHES_PER_PROJECT
)

logger = logging.getLogger(__name__)


class GitLabCommitFetcher:
    """GitLab 提交记录获取器"""

    def __init__(self, gitlab_url: str = None, private_token: str = None):
        """
        初始化 GitLab 连接

        Args:
            gitlab_url: GitLab 实例 URL
            private_token: GitLab 个人访问令牌
        """
        self.gitlab_url = (gitlab_url or GITLAB_URL).rstrip('/')
        self.token = private_token or GITLAB_TOKEN
        self.headers = {
            'PRIVATE-TOKEN': self.token,
            'Content-Type': 'application/json'
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def get_user_info(self) -> Optional[Dict[str, Any]]:
        """获取当前用户信息"""
        try:
            url = f"{self.gitlab_url}/api/v4/user"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"获取用户信息失败: {e}")
            return None

    def get_projects(self, per_page: int = 100) -> List[Dict[str, Any]]:
        """
        获取当前用户有权限的所有项目
        """
        all_projects = []
        page = 1

        try:
            while True:
                url = f"{self.gitlab_url}/api/v4/projects"
                params = {
                    'membership': True,
                    'per_page': per_page,
                    'page': page,
                    'order_by': 'updated_at',
                    'sort': 'desc'
                }

                response = self.session.get(url, params=params, timeout=30)
                response.raise_for_status()

                projects = response.json()
                if not projects:
                    break

                all_projects.extend(projects)
                page += 1

            logger.info(f"获取到 {len(all_projects)} 个项目")
            return all_projects
        except Exception as e:
            logger.error(f"获取项目列表失败: {e}")
            return []

    def get_recent_branches(self, project_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """
        获取项目最近更新的分支
        """
        url = f"{self.gitlab_url}/api/v4/projects/{project_id}/repository/branches"
        params = {
            'per_page': min(limit, 100),
            'page': 1,
            'sort': 'updated_desc'
        }

        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            branches = response.json()

            if len(branches) > limit:
                branches = branches[:limit]

            return branches
        except Exception as e:
            logger.warning(f"获取项目 {project_id} 分支列表失败: {e}")
            return []

    def get_user_commits_on_branch(
        self,
        project_id: int,
        username: str,
        branch: str,
        since: datetime
    ) -> List[Dict[str, Any]]:
        """
        获取项目中特定分支上特定用户的提交记录
        """
        url = f"{self.gitlab_url}/api/v4/projects/{project_id}/repository/commits"
        params = {
            'author': username,
            'since': since.isoformat(),
            'per_page': 100,
            'ref_name': branch
        }

        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception:
            return []

    def format_commit_info(self, commit: Dict[str, Any], project_name: str, branch: str) -> str:
        """
        格式化提交信息
        """
        commit_date = commit.get('created_at', '')
        commit_msg = commit.get('message', '').split('\n')[0]
        commit_id = commit.get('short_id', commit.get('id', ''))[:8]

        return f"[{project_name}] [{branch}] {commit_date} | {commit_id} | {commit_msg}"

    def fetch_commits(self, days: int = None) -> tuple:
        """
        获取当前用户最近 N 天的提交记录

        Args:
            days: 查询天数，默认使用配置

        Returns:
            (commits_text, commit_count, username)
        """
        days = days or DAYS

        # 获取用户信息
        user_info = self.get_user_info()
        if not user_info:
            return "获取用户信息失败，请检查 GitLab Token 是否有效", 0, ""

        username = user_info.get('username')
        user_name = user_info.get('name', username)

        logger.info(f"正在获取用户 {user_name} ({username}) 的提交记录...")

        # 获取所有有权限的项目
        projects = self.get_projects()
        logger.info(f"找到 {len(projects)} 个有权限的项目")

        # 计算 N 天前的时间
        n_days_ago = datetime.now() - timedelta(days=days)

        all_commits = []
        commit_set = set()

        for project in projects:
            project_id = project.get('id')
            project_name = project.get('name_with_namespace', project.get('name', str(project_id)))

            logger.debug(f"检查项目: {project_name}")

            # 获取最近更新的分支
            recent_branches = self.get_recent_branches(project_id, MAX_BRANCHES_PER_PROJECT)

            if not recent_branches:
                continue

            project_commit_count = 0

            for branch_info in recent_branches:
                branch_name = branch_info.get('name')

                # 检查分支最后提交时间
                commit = branch_info.get('commit', {})
                committed_date = commit.get('committed_date', '')
                if committed_date:
                    try:
                        commit_time = datetime.fromisoformat(committed_date.replace('Z', '+00:00'))
                        branch_active_since = datetime.now() - timedelta(days=BRANCH_ACTIVE_DAYS)
                        if commit_time < branch_active_since:
                            continue
                    except (ValueError, TypeError):
                        pass

                commits = self.get_user_commits_on_branch(
                    project_id, username, branch_name, n_days_ago
                )

                if commits:
                    for c in commits:
                        commit_id = c.get('id', '')
                        if commit_id not in commit_set:
                            commit_set.add(commit_id)
                            formatted = self.format_commit_info(c, project_name, branch_name)
                            all_commits.append(formatted)
                            project_commit_count += 1

            if project_commit_count > 0:
                logger.debug(f"项目 {project_name} 找到 {project_commit_count} 条提交")

        # 按时间排序（从新到旧）
        all_commits.sort(reverse=True)

        logger.info(f"总共找到 {len(all_commits)} 条提交记录")

        if all_commits:
            return "\n".join(all_commits), len(all_commits), username
        else:
            return f"最近 {days} 天内没有找到任何提交记录", 0, username


def fetch_commits(days: int = None) -> tuple:
    """
    便捷函数：获取提交记录

    Returns:
        (commits_text, commit_count, username)
    """
    fetcher = GitLabCommitFetcher()
    return fetcher.fetch_commits(days)