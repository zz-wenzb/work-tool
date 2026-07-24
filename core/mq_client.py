# core/mq_client.py
import logging
import pickle
import os
import time
from typing import Optional, Dict, Any, List, Generator
import requests
import re
import json

logger = logging.getLogger(__name__)

# Cookie 缓存配置
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "cache")
MQ_COOKIE_FILE = os.path.join(CACHE_DIR, "mq_session.pkl")
# Cookie 过期时间（秒），RocketMQ 默认 session 有效期约 30 分钟
COOKIE_EXPIRE_SECONDS = 1500  # 25分钟，提前刷新


class MQManager:
    def __init__(self, mq_config: Dict[str, Any]):
        self.host = mq_config.get('host')
        self.username = mq_config.get('username')
        self.password = mq_config.get('password')
        self.no_login = mq_config.get('no_login', False)

        # 从缓存或配置加载 cookie
        self.cookie = self._load_cookie() or mq_config.get('cookie', '')
        self._last_used = time.time()
        self._is_logged_in = False

        # 如果有 cookie，验证是否有效
        if self.cookie:
            self._is_logged_in = self._test_cookie_valid()
            if not self._is_logged_in:
                logger.warning("⚠️ 缓存的 MQ Cookie 已过期，将重新登录")
                self.cookie = ""

        # 如果 no_login 为 True，跳过登录
        if self.no_login:
            self._is_logged_in = True
            logger.info(f"✅ MQ 跳过登录 (no_login=True, host={self.host})")
            return

        # 如果没有有效 cookie，尝试登录
        if not self._is_logged_in and self.username and self.password:
            self.login()

    def _load_cookie(self) -> Optional[str]:
        """从缓存加载 cookie"""
        if not os.path.exists(MQ_COOKIE_FILE):
            return None

        try:
            with open(MQ_COOKIE_FILE, "rb") as f:
                cached_data = pickle.load(f)

            if not isinstance(cached_data, dict):
                logger.warning("MQ 缓存数据格式异常")
                return None

            # 检查是否过期
            timestamp = cached_data.get('timestamp', 0)
            if time.time() - timestamp > COOKIE_EXPIRE_SECONDS:
                logger.info("⏰ 缓存的 MQ Cookie 已过期")
                os.remove(MQ_COOKIE_FILE)
                return None

            cookie = cached_data.get('cookie', '')
            if cookie:
                logger.info("✅ 从缓存加载 MQ Cookie 成功")
                return cookie
            else:
                return None

        except (pickle.UnpicklingError, EOFError, AttributeError) as e:
            logger.warning(f"加载 MQ 缓存失败 (数据损坏): {e}")
            if os.path.exists(MQ_COOKIE_FILE):
                os.remove(MQ_COOKIE_FILE)
            return None
        except Exception as e:
            logger.warning(f"加载 MQ 缓存失败: {e}")
            return None

    def _save_cookie(self, cookie: str):
        """保存 cookie 到缓存"""
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            cache_data = {
                'cookie': cookie,
                'timestamp': time.time(),
                'host': self.host,
                'username': self.username
            }
            with open(MQ_COOKIE_FILE, "wb") as f:
                pickle.dump(cache_data, f)
            logger.info("✅ MQ Cookie 已保存到缓存")
        except Exception as e:
            logger.warning(f"保存 MQ Cookie 缓存失败: {e}")

    def _test_cookie_valid(self) -> bool:
        """测试当前 cookie 是否有效"""
        if not self.cookie:
            return False

        try:
            url = f"{self.host}/topic/list.query"
            headers = {
                'Cookie': self.cookie,
                'content-type': 'application/json;charset=UTF-8',
            }

            xsrf_token = self._get_xsrf_token()
            if xsrf_token:
                headers['X-XSRF-TOKEN'] = xsrf_token

            response = requests.get(url, headers=headers, timeout=5)

            # 200 表示有效，403 表示过期
            if response.status_code == 200:
                # 尝试解析 JSON
                try:
                    result = response.json()
                    # 检查业务状态码
                    if result.get('status') == 0 or result.get('status') == 200:
                        return True
                    elif result.get('status') == -1 and '403' in str(result.get('errMsg', '')):
                        return False
                    else:
                        # 其他错误可能是权限问题，但 cookie 可能有效
                        return True
                except (json.JSONDecodeError, ValueError):
                    # 响应不是 JSON，可能是登录页，说明 cookie 无效
                    logger.warning("MQ Cookie 验证: 响应不是 JSON，cookie 可能无效")
                    return False
            elif response.status_code == 403:
                return False
            else:
                # 其他状态码可能是网络问题，保守处理
                return True

        except requests.exceptions.RequestException as e:
            logger.warning(f"MQ Cookie 验证请求异常: {e}")
            return True
        except Exception as e:
            logger.warning(f"MQ Cookie 验证异常: {e}")
            return True

    def _get_xsrf_token(self) -> Optional[str]:
        """从 cookie 中提取 XSRF-TOKEN"""
        if not self.cookie:
            return None

        match = re.search(r'XSRF-TOKEN=([^;]+)', self.cookie)
        if match:
            return match.group(1)
        return None

    def login(self) -> bool:
        """
        登录并更新 Cookie
        如果未配置 username/password，则跳过登录（使用已有 cookie）
        """
        # 如果 no_login 为 True，跳过登录
        if self.no_login:
            self._is_logged_in = True
            logger.info("✅ MQ 跳过登录 (no_login=True)")
            return True

        # 如果已经有有效 cookie，直接返回
        if self.cookie and self._test_cookie_valid():
            self._is_logged_in = True
            return True

        # 检查是否配置了账号密码
        if not self.username or not self.password:
            logger.warning("⚠️ 未配置 MQ 账号密码，且无有效 cookie")
            self._is_logged_in = False
            return False

        url = f"{self.host}/login/login.do"
        params = {
            "password": self.password,
            "username": self.username
        }

        headers = {
            'content-type': 'application/json;charset=UTF-8',
        }

        try:
            response = requests.post(url, params=params, headers=headers, timeout=10)

            if response.status_code == 200:
                # 获取响应头中的 Set-Cookie
                set_cookie = response.headers.get('Set-Cookie')

                if set_cookie:
                    # 提取 JSESSIONID
                    match = re.search(r'JSESSIONID=([^;]+)', set_cookie)
                    if match:
                        new_session_id = match.group(1)

                        # 更新 cookie
                        xsrf_token = self._get_xsrf_token()
                        if not self.cookie:
                            # 如果没有 cookie，直接构建
                            if xsrf_token:
                                self.cookie = f"JSESSIONID={new_session_id}; XSRF-TOKEN={xsrf_token}"
                            else:
                                self.cookie = f"JSESSIONID={new_session_id}"
                        else:
                            # 已有 cookie，替换 JSESSIONID
                            if "JSESSIONID=" in self.cookie:
                                self.cookie = re.sub(
                                    r'JSESSIONID=[^;]+',
                                    f'JSESSIONID={new_session_id}',
                                    self.cookie
                                )
                            else:
                                self.cookie += f"; JSESSIONID={new_session_id}"

                        self._last_used = time.time()
                        self._is_logged_in = True

                        # 保存到缓存
                        self._save_cookie(self.cookie)

                        logger.info("✅ MQ 登录成功，JSESSIONID 已更新并缓存")
                        return True
                    else:
                        logger.warning("⚠️ 响应中未包含 JSESSIONID")
                        return False
                else:
                    logger.warning("⚠️ 响应中未包含 Set-Cookie")
                    return False
            else:
                logger.error(f"❌ MQ 登录失败，状态码: {response.status_code}")
                self._is_logged_in = False
                return False

        except Exception as e:
            logger.error(f"❌ MQ 登录发生异常: {e}")
            self._is_logged_in = False
            return False

    def _ensure_valid_cookie(self) -> bool:
        """确保 cookie 有效，如果无效则重新登录"""
        # 如果 no_login 为 True，跳过验证
        if self.no_login:
            return True

        # 检查是否超过25分钟未使用
        if time.time() - self._last_used > COOKIE_EXPIRE_SECONDS:
            logger.info("⏰ MQ 会话可能已过期，重新验证...")
            self._is_logged_in = False

        # 如果标记为已登录且 cookie 存在，验证是否真正有效
        if self._is_logged_in and self.cookie:
            # 先快速验证
            if self._test_cookie_valid():
                self._last_used = time.time()
                return True
            else:
                logger.warning("⚠️ MQ Cookie 已过期，需要重新登录")
                self._is_logged_in = False

        # 尝试重新登录
        if self.username and self.password:
            result = self.login()
            if result:
                return True

        # 如果登录失败，返回 False
        logger.warning("⚠️ MQ 无法获取有效 Cookie")
        return False

    def _safe_request(self, method: str, url: str, **kwargs) -> Optional[dict]:
        """
        安全的请求方法，处理非 JSON 响应
        """
        try:
            response = requests.request(method, url, **kwargs)

            # 检查状态码
            if response.status_code == 403:
                logger.warning("⚠️ 收到 403，尝试重新登录...")
                if self.login():
                    # 重新发起请求
                    response = requests.request(method, url, **kwargs)
                else:
                    return {'status': -1, 'errMsg': '认证失败，请重新登录'}

            if response.status_code != 200:
                logger.error(f"请求失败: {response.status_code}")
                return {'status': -1, 'errMsg': f'HTTP {response.status_code}'}

            # 尝试解析 JSON
            try:
                return response.json()
            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"响应不是 JSON 格式: {e}")
                logger.debug(f"响应内容: {response.text[:200]}")
                return {'status': -1, 'errMsg': '服务器返回非 JSON 响应，请检查服务状态'}

        except requests.exceptions.RequestException as e:
            logger.error(f"请求异常: {e}")
            return {'status': -1, 'errMsg': str(e)}
        except Exception as e:
            logger.error(f"请求发生异常: {e}")
            return {'status': -1, 'errMsg': str(e)}

    def query_topic_message(self, topic: str, m: int = 15, page_size: int = 20, fetch_all: bool = False) -> dict:
        """查询topic消息列表"""
        if not self._ensure_valid_cookie():
            return {'status': -1, 'errMsg': '认证失败，请检查账号密码或网络连接'}

        url = f"{self.host}/message/queryMessagePageByTopic.query"
        headers = {
            'Cookie': self.cookie,
            'content-type': 'application/json;charset=UTF-8',
        }

        xsrf_token = self._get_xsrf_token()
        if xsrf_token:
            headers['X-XSRF-TOKEN'] = xsrf_token

        end = int(time.time() * 1000)
        start = end - (m * 60 * 1000)

        payload = {
            "topic": topic,
            "begin": start,
            "end": end,
            "pageNum": 1,
            "pageSize": page_size,
            "taskId": ""
        }

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)

            if response.status_code == 403:
                logger.warning("⚠️ 收到 403，尝试重新登录...")
                if self.login():
                    response = requests.post(url, headers=headers, json=payload, timeout=30)
                else:
                    return {'status': -1, 'errMsg': '认证失败，请重新登录'}

            if response.status_code != 200:
                logger.error(f"查询失败: {response.status_code}")
                return {'status': -1, 'errMsg': f'HTTP {response.status_code}'}

            # 尝试解析 JSON
            try:
                first_page = response.json()
            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"响应不是 JSON 格式: {e}")
                return {'status': -1, 'errMsg': '服务器返回非 JSON 响应'}

            # 如果只取第一页，或第一页失败，直接返回
            if not fetch_all or first_page.get('status') != 0:
                return first_page

            # 获取分页信息
            page_info = first_page.get('data', {}).get('page', {})
            total_pages = page_info.get('totalPages', 1)
            all_content = page_info.get('content', [])

            logger.info(f"获取全量数据: 共 {total_pages} 页")

            # 循环获取剩余页面
            for page_num in range(2, total_pages + 1):
                payload['pageNum'] = page_num
                response = requests.post(url, headers=headers, json=payload, timeout=30)

                if response.status_code == 200:
                    try:
                        page_data = response.json()
                        if page_data.get('status') == 0:
                            content = page_data.get('data', {}).get('page', {}).get('content', [])
                            all_content.extend(content)
                            if page_num % 10 == 0:
                                logger.info(f"已获取 {page_num}/{total_pages} 页")
                    except (json.JSONDecodeError, ValueError):
                        logger.warning(f"第 {page_num} 页响应不是 JSON")
                else:
                    logger.warning(f"第 {page_num} 页获取失败")

            # 合并数据
            first_page['data']['page']['content'] = all_content
            first_page['data']['page']['totalElements'] = len(all_content)

            logger.info(f"✅ 共获取 {len(all_content)} 条消息")
            return first_page

        except Exception as e:
            logger.exception(f"查询异常: {e}")
            return {'status': -1, 'errMsg': str(e)}

    def query_topic_list(self) -> dict:
        """查询所有Topic列表"""
        if not self._ensure_valid_cookie():
            return {'status': -1, 'errMsg': '认证失败，请检查账号密码或网络连接'}

        url = f"{self.host}/topic/list.query"
        headers = {
            'Cookie': self.cookie,
            'content-type': 'application/json;charset=UTF-8',
        }

        xsrf_token = self._get_xsrf_token()
        if xsrf_token:
            headers['X-XSRF-TOKEN'] = xsrf_token

        try:
            response = requests.get(url, headers=headers, timeout=10)

            if response.status_code == 403:
                logger.warning("⚠️ 收到 403，尝试重新登录...")
                if self.login():
                    response = requests.get(url, headers=headers, timeout=10)
                else:
                    return {'status': -1, 'errMsg': '认证失败，请重新登录'}

            if response.status_code != 200:
                logger.error(f"查询Topic列表失败: {response.status_code}")
                return {'status': -1, 'errMsg': f'HTTP {response.status_code}'}

            # 尝试解析 JSON
            try:
                return response.json()
            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"响应不是 JSON 格式: {e}")
                logger.debug(f"响应内容: {response.text[:200]}")
                return {'status': -1, 'errMsg': '服务器返回非 JSON 响应，请检查 Cookie 是否有效'}

        except Exception as e:
            logger.exception(f"查询Topic列表异常: {e}")
            return {'status': -1, 'errMsg': str(e)}

    def query_cluster_info(self) -> dict:
        """查询集群信息"""
        if not self._ensure_valid_cookie():
            return {'status': -1, 'errMsg': '认证失败，请检查账号密码或网络连接'}

        url = f"{self.host}/cluster/list.query"
        headers = {
            'Cookie': self.cookie,
            'Content-Type': 'application/json;charset=UTF-8',
        }

        xsrf_token = self._get_xsrf_token()
        if xsrf_token:
            headers['X-XSRF-TOKEN'] = xsrf_token

        try:
            response = requests.get(url, headers=headers, timeout=10)

            if response.status_code == 403:
                logger.warning("⚠️ 收到 403，尝试重新登录...")
                if self.login():
                    response = requests.get(url, headers=headers, timeout=10)
                else:
                    return {'status': -1, 'errMsg': '认证失败，请重新登录'}

            if response.status_code != 200:
                logger.error(f"❌ 查询集群信息失败: HTTP {response.status_code}")
                return {'status': -1, 'errMsg': f'HTTP {response.status_code}'}

            try:
                result = response.json()
                if result.get('status') == 0:
                    logger.info("✅ 查询集群信息成功")
                return result
            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"响应不是 JSON 格式: {e}")
                return {'status': -1, 'errMsg': '服务器返回非 JSON 响应'}

        except Exception as e:
            logger.exception(f"❌ 查询集群信息异常: {e}")
            return {'status': -1, 'errMsg': str(e)}

    def get_message_detail(self, msg_id: str, topic: str) -> Optional[str]:
        """根据 msgId 和 topic 获取消息详情"""
        if not self._ensure_valid_cookie():
            return None

        detail_url = f"{self.host}/message/viewMessage.query"
        params = {
            "msgId": msg_id,
            "topic": topic
        }
        headers = {
            'Cookie': self.cookie
        }

        xsrf_token = self._get_xsrf_token()
        if xsrf_token:
            headers['X-XSRF-TOKEN'] = xsrf_token

        try:
            response = requests.get(detail_url, headers=headers, params=params, timeout=10)

            if response.status_code == 403:
                logger.warning("⚠️ 收到 403，尝试重新登录...")
                if self.login():
                    response = requests.get(detail_url, headers=headers, params=params, timeout=10)
                else:
                    return None

            if response.status_code != 200:
                logger.error(f"获取详情失败: {response.status_code}")
                return None

            try:
                response_data = response.json()
                if response_data.get('status') == 0:
                    return response_data.get('data', {}).get('messageView', {}).get('messageBody')
                else:
                    logger.error(f"详情接口错误: {response_data.get('errMsg')}")
                    return None
            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"响应不是 JSON 格式: {e}")
                return None

        except Exception as e:
            logger.exception(f"获取详情异常: {e}")
            return None

    def create_topic(self, topic: str, cluster_name_list: list = None, broker_name_list: list = None,
                     message_type: str = "NORMAL", write_queue_nums: int = 8,
                     read_queue_nums: int = 8, perm: int = 7, auto_fetch_cluster: bool = True) -> dict:
        """创建 Topic"""
        if not self._ensure_valid_cookie():
            return {'status': -1, 'errMsg': '认证失败，请检查账号密码或网络连接'}

        # 自动获取集群和 broker 信息
        if auto_fetch_cluster and (not cluster_name_list or not broker_name_list):
            cluster_result = self.query_cluster_info()
            if cluster_result.get('status') == 0:
                data = cluster_result.get('data', {})
                cluster_info = data.get('clusterInfo', {})

                if not cluster_name_list:
                    cluster_addr_table = cluster_info.get('clusterAddrTable', {})
                    cluster_name_list = list(cluster_addr_table.keys()) if cluster_addr_table else ["DefaultCluster"]

                if not broker_name_list:
                    broker_addr_table = cluster_info.get('brokerAddrTable', {})
                    broker_name_list = list(broker_addr_table.keys()) if broker_addr_table else []

                logger.info(f"自动获取到集群: {cluster_name_list}, Broker: {broker_name_list}")
            else:
                logger.warning("无法自动获取集群信息，使用默认值")
                if not cluster_name_list:
                    cluster_name_list = ["DefaultCluster"]
                if not broker_name_list:
                    broker_name_list = []

        url = f"{self.host}/topic/createOrUpdate.do"
        headers = {
            'Cookie': self.cookie,
            'Content-Type': 'application/json',
        }

        xsrf_token = self._get_xsrf_token()
        if xsrf_token:
            headers['X-XSRF-TOKEN'] = xsrf_token

        payload = {
            "clusterNameList": cluster_name_list or ["DefaultCluster"],
            "brokerNameList": broker_name_list or [],
            "topicName": topic,
            "messageType": message_type,
            "writeQueueNums": write_queue_nums,
            "readQueueNums": read_queue_nums,
            "perm": perm
        }

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)

            if response.status_code == 403:
                logger.warning("⚠️ 收到 403，尝试重新登录...")
                if self.login():
                    response = requests.post(url, headers=headers, json=payload, timeout=30)
                else:
                    return {'status': -1, 'errMsg': '认证失败，请重新登录'}

            if response.status_code != 200:
                logger.error(f"❌ 创建 Topic 失败: HTTP {response.status_code}")
                return {'status': -1, 'errMsg': f'HTTP {response.status_code}'}

            try:
                result = response.json()
                if result.get('status') == 0:
                    logger.info(f"✅ Topic '{topic}' 创建成功")
                else:
                    logger.warning(f"⚠️ Topic '{topic}' 创建失败: {result.get('errMsg')}")
                return result
            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"响应不是 JSON 格式: {e}")
                return {'status': -1, 'errMsg': '服务器返回非 JSON 响应'}

        except Exception as e:
            logger.exception(f"❌ 创建 Topic 异常: {e}")
            return {'status': -1, 'errMsg': str(e)}

    def delete_topic(self, topic: str) -> dict:
        """删除 Topic"""
        if not self._ensure_valid_cookie():
            return {'status': -1, 'errMsg': '认证失败，请检查账号密码或网络连接'}

        url = f"{self.host}/topic/deleteTopic.do"
        headers = {
            'Cookie': self.cookie,
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        }

        xsrf_token = self._get_xsrf_token()
        if xsrf_token:
            headers['X-XSRF-TOKEN'] = xsrf_token

        payload = {
            "topic": topic
        }

        try:
            response = requests.post(url, headers=headers, data=payload, timeout=30)

            if response.status_code == 403:
                logger.warning("⚠️ 收到 403，尝试重新登录...")
                if self.login():
                    response = requests.post(url, headers=headers, data=payload, timeout=30)
                else:
                    return {'status': -1, 'errMsg': '认证失败，请重新登录'}

            if response.status_code != 200:
                logger.error(f"❌ 删除 Topic 失败: HTTP {response.status_code}")
                return {'status': -1, 'errMsg': f'HTTP {response.status_code}'}

            try:
                result = response.json()
                if result.get('status') == 0:
                    logger.info(f"✅ Topic '{topic}' 删除成功")
                else:
                    logger.warning(f"⚠️ Topic '{topic}' 删除失败: {result.get('errMsg')}")
                return result
            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"响应不是 JSON 格式: {e}")
                return {'status': -1, 'errMsg': '服务器返回非 JSON 响应'}

        except Exception as e:
            logger.exception(f"❌ 删除 Topic 异常: {e}")
            return {'status': -1, 'errMsg': str(e)}

    def send_message(self, topic: str, message_body: str, tag: str = "", key: str = "",
                     trace_enabled: bool = False) -> dict:
        """发送消息到指定 Topic"""
        if not self._ensure_valid_cookie():
            return {'status': -1, 'errMsg': '认证失败，请检查账号密码或网络连接'}

        url = f"{self.host}/topic/sendTopicMessage.do"
        headers = {
            'Cookie': self.cookie,
            'Content-Type': 'application/json;charset=UTF-8',
        }

        xsrf_token = self._get_xsrf_token()
        if xsrf_token:
            headers['X-XSRF-TOKEN'] = xsrf_token

        payload = {
            "topic": topic,
            "tag": tag,
            "key": key,
            "messageBody": message_body,
            "traceEnabled": trace_enabled
        }

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)

            if response.status_code == 403:
                logger.warning("⚠️ 收到 403，尝试重新登录...")
                if self.login():
                    response = requests.post(url, headers=headers, json=payload, timeout=30)
                else:
                    return {'status': -1, 'errMsg': '认证失败，请重新登录'}

            if response.status_code != 200:
                logger.error(f"❌ 发送消息失败: HTTP {response.status_code}")
                return {'status': -1, 'errMsg': f'HTTP {response.status_code}'}

            try:
                result = response.json()
                if result.get('status') == 0:
                    send_data = result.get('data', {})
                    msg_id = send_data.get('msgId', 'N/A')
                    send_status = send_data.get('sendStatus', 'N/A')
                    logger.info(f"✅ 消息发送成功 - msgId: {msg_id}, status: {send_status}")
                else:
                    logger.warning(f"⚠️ 消息发送失败: {result.get('errMsg')}")
                return result
            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"响应不是 JSON 格式: {e}")
                return {'status': -1, 'errMsg': '服务器返回非 JSON 响应'}

        except Exception as e:
            logger.exception(f"❌ 发送消息异常: {e}")
            return {'status': -1, 'errMsg': str(e)}
