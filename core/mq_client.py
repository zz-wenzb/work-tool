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

        # 使用 Session 自动管理 cookie
        self._session = requests.Session()
        self._csrf_token = None
        self._last_used = time.time()
        self._is_logged_in = False

        # 从缓存加载 cookie
        self.cookie = self._load_cookie() or mq_config.get('cookie', '')
        if self.cookie:
            self._session.headers.update({'Cookie': self.cookie})

        # 如果 no_login 为 True，通过 csrf-token 接口初始化会话
        if self.no_login:
            if not self.cookie or not self._csrf_token:
                self._init_session()
            self._is_logged_in = True
            logger.info(f"✅ MQ 跳过登录 (no_login=True, host={self.host})")
            return

        # 如果有 cookie，验证是否有效
        if self.cookie:
            self._is_logged_in = self._test_cookie_valid()
            if not self._is_logged_in:
                logger.warning("⚠️ 缓存的 MQ Cookie 已过期，将重新登录")
                self.cookie = ""
            else:
                self._fetch_csrf_token()

        # 如果没有有效 cookie，尝试登录
        if not self._is_logged_in and self.username and self.password:
            self.login()

    def _init_session(self) -> bool:
        """初始化会话：访问 csrf-token 接口获取 JSESSIONID 和 CSRF Token"""
        try:
            url = f"{self.host}/rocketmq-dashboard/csrf-token"
            response = self._session.get(url, timeout=10)

            if response.status_code != 200:
                logger.error(f"初始化会话失败: HTTP {response.status_code}")
                return False

            result = response.json()
            if result.get('status') != 0:
                logger.error(f"初始化会话失败: {result.get('errMsg')}")
                return False

            token = result.get('data', {}).get('token')
            if not token:
                logger.error("CSRF Token 为空")
                return False

            self._csrf_token = token
            self._session.headers.update({'X-XSRF-TOKEN': token})

            # 从 session 中提取 cookie 并缓存
            cookie_parts = []
            for key, value in self._session.cookies.items():
                cookie_parts.append(f"{key}={value}")
            self.cookie = '; '.join(cookie_parts)
            self._save_cookie(self.cookie)

            logger.info(f"✅ 会话初始化成功，CSRF Token: {token[:8]}...")
            return True

        except Exception as e:
            logger.error(f"初始化会话失败: {e}")
            return False

    def _fetch_csrf_token(self) -> Optional[str]:
        """获取 CSRF Token"""
        try:
            url = f"{self.host}/rocketmq-dashboard/csrf-token"
            response = self._session.get(url, timeout=10)

            if response.status_code == 200:
                result = response.json()
                if result.get('status') == 0:
                    token = result.get('data', {}).get('token')
                    if token:
                        self._csrf_token = token
                        self._session.headers.update({'X-XSRF-TOKEN': token})
                        logger.info(f"✅ 获取 CSRF Token 成功: {token[:8]}...")
                        return token
            return None
        except Exception as e:
            logger.warning(f"获取 CSRF Token 失败: {e}")
            return None

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
                self._session.headers.update({'Cookie': cookie})
                return cookie
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
            url = f"{self.host}/ops/homePage.query"
            headers = {
                'content-type': 'application/json;charset=UTF-8',
            }
            if self._csrf_token:
                headers['X-XSRF-TOKEN'] = self._csrf_token

            response = self._session.get(url, headers=headers, timeout=5)

            if response.status_code == 200:
                try:
                    result = response.json()
                    if result.get('status') == 0 or result.get('status') == 200:
                        return True
                except (json.JSONDecodeError, ValueError):
                    return False
            elif response.status_code == 403:
                return False
            return True

        except requests.exceptions.RequestException as e:
            logger.warning(f"MQ Cookie 验证请求异常: {e}")
            return True
        except Exception as e:
            logger.warning(f"MQ Cookie 验证异常: {e}")
            return True

    def _get_xsrf_token(self) -> Optional[str]:
        """获取 XSRF-TOKEN"""
        if self._csrf_token:
            return self._csrf_token

        if not self.cookie:
            return None
        match = re.search(r'XSRF-TOKEN=([^;]+)', self.cookie)
        if match:
            return match.group(1)
        return None

    def login(self) -> bool:
        """登录并更新 Cookie"""
        if self.no_login:
            self._is_logged_in = True
            logger.info("✅ MQ 跳过登录 (no_login=True)")
            return True

        if self.cookie and self._test_cookie_valid():
            self._is_logged_in = True
            self._fetch_csrf_token()
            return True

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
                set_cookie = response.headers.get('Set-Cookie')
                if set_cookie:
                    match = re.search(r'JSESSIONID=([^;]+)', set_cookie)
                    if match:
                        new_session_id = match.group(1)
                        xsrf_token = self._get_xsrf_token()
                        if not self.cookie:
                            if xsrf_token:
                                self.cookie = f"JSESSIONID={new_session_id}; XSRF-TOKEN={xsrf_token}"
                            else:
                                self.cookie = f"JSESSIONID={new_session_id}"
                        else:
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
                        self._session.headers.update({'Cookie': self.cookie})
                        self._save_cookie(self.cookie)
                        self._fetch_csrf_token()
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
        """确保 cookie 有效，如果无效则重新初始化"""
        if self.no_login:
            # 检查 session 是否有效
            if self.cookie and self._csrf_token:
                # 快速验证
                try:
                    url = f"{self.host}/ops/homePage.query"
                    response = self._session.get(url, timeout=3)
                    if response.status_code == 200:
                        self._last_used = time.time()
                        return True
                except:
                    pass

            # 无效则重新初始化
            logger.warning("⚠️ 会话无效，重新初始化...")
            return self._init_session()

        # 有账号密码的逻辑
        if time.time() - self._last_used > COOKIE_EXPIRE_SECONDS:
            logger.info("⏰ MQ 会话可能已过期，重新验证...")
            self._is_logged_in = False

        if self._is_logged_in and self.cookie:
            if self._test_cookie_valid():
                self._last_used = time.time()
                return True
            else:
                logger.warning("⚠️ MQ Cookie 已过期，需要重新登录")
                self._is_logged_in = False

        if self.username and self.password:
            result = self.login()
            if result:
                return True

        logger.warning("⚠️ MQ 无法获取有效 Cookie")
        return False

    def query_topic_message(self, topic: str, m: int = 15, page_size: int = 20, fetch_all: bool = False) -> dict:
        """查询topic消息列表"""
        if not self._ensure_valid_cookie():
            return {'status': -1, 'errMsg': '认证失败，请检查账号密码或网络连接'}

        url = f"{self.host}/message/queryMessagePageByTopic.query"
        headers = {
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
            response = self._session.post(url, headers=headers, json=payload, timeout=30)

            if response.status_code == 403:
                logger.warning("⚠️ 收到 403，尝试重新初始化...")
                if self._init_session():
                    xsrf_token = self._get_xsrf_token()
                    if xsrf_token:
                        headers['X-XSRF-TOKEN'] = xsrf_token
                    response = self._session.post(url, headers=headers, json=payload, timeout=30)
                else:
                    return {'status': -1, 'errMsg': '认证失败，请重新登录'}

            if response.status_code != 200:
                logger.error(f"查询失败: {response.status_code}")
                return {'status': -1, 'errMsg': f'HTTP {response.status_code}'}

            try:
                first_page = response.json()
            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"响应不是 JSON 格式: {e}")
                return {'status': -1, 'errMsg': '服务器返回非 JSON 响应'}

            if not fetch_all or first_page.get('status') != 0:
                return first_page

            page_info = first_page.get('data', {}).get('page', {})
            total_pages = page_info.get('totalPages', 1)
            all_content = page_info.get('content', [])

            logger.info(f"获取全量数据: 共 {total_pages} 页")

            for page_num in range(2, total_pages + 1):
                payload['pageNum'] = page_num
                response = self._session.post(url, headers=headers, json=payload, timeout=30)

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
            'content-type': 'application/json;charset=UTF-8',
        }

        xsrf_token = self._get_xsrf_token()
        if xsrf_token:
            headers['X-XSRF-TOKEN'] = xsrf_token

        try:
            response = self._session.get(url, headers=headers, timeout=10)

            if response.status_code == 403:
                logger.warning("⚠️ 收到 403，尝试重新初始化...")
                if self._init_session():
                    xsrf_token = self._get_xsrf_token()
                    if xsrf_token:
                        headers['X-XSRF-TOKEN'] = xsrf_token
                    response = self._session.get(url, headers=headers, timeout=10)
                else:
                    return {'status': -1, 'errMsg': '认证失败，请重新登录'}

            if response.status_code != 200:
                logger.error(f"查询Topic列表失败: {response.status_code}")
                return {'status': -1, 'errMsg': f'HTTP {response.status_code}'}

            try:
                return response.json()
            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"响应不是 JSON 格式: {e}")
                return {'status': -1, 'errMsg': '服务器返回非 JSON 响应'}

        except Exception as e:
            logger.exception(f"查询Topic列表异常: {e}")
            return {'status': -1, 'errMsg': str(e)}

    def query_cluster_info(self) -> dict:
        """查询集群信息"""
        if not self._ensure_valid_cookie():
            return {'status': -1, 'errMsg': '认证失败，请检查账号密码或网络连接'}

        url = f"{self.host}/cluster/list.query"
        headers = {
            'Content-Type': 'application/json;charset=UTF-8',
        }

        xsrf_token = self._get_xsrf_token()
        if xsrf_token:
            headers['X-XSRF-TOKEN'] = xsrf_token

        try:
            response = self._session.get(url, headers=headers, timeout=10)

            if response.status_code == 403:
                logger.warning("⚠️ 收到 403，尝试重新初始化...")
                if self._init_session():
                    xsrf_token = self._get_xsrf_token()
                    if xsrf_token:
                        headers['X-XSRF-TOKEN'] = xsrf_token
                    response = self._session.get(url, headers=headers, timeout=10)
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
        headers = {}

        xsrf_token = self._get_xsrf_token()
        if xsrf_token:
            headers['X-XSRF-TOKEN'] = xsrf_token

        try:
            response = self._session.get(detail_url, headers=headers, params=params, timeout=10)

            if response.status_code == 403:
                logger.warning("⚠️ 收到 403，尝试重新初始化...")
                if self._init_session():
                    xsrf_token = self._get_xsrf_token()
                    if xsrf_token:
                        headers['X-XSRF-TOKEN'] = xsrf_token
                    response = self._session.get(detail_url, headers=headers, params=params, timeout=10)
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
            response = self._session.post(url, headers=headers, json=payload, timeout=30)

            if response.status_code == 403:
                logger.warning("⚠️ 收到 403，尝试重新初始化...")
                if self._init_session():
                    xsrf_token = self._get_xsrf_token()
                    if xsrf_token:
                        headers['X-XSRF-TOKEN'] = xsrf_token
                    response = self._session.post(url, headers=headers, json=payload, timeout=30)
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
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        }

        xsrf_token = self._get_xsrf_token()
        if xsrf_token:
            headers['X-XSRF-TOKEN'] = xsrf_token

        payload = {
            "topic": topic
        }

        try:
            response = self._session.post(url, headers=headers, data=payload, timeout=30)

            if response.status_code == 403:
                logger.warning("⚠️ 收到 403，尝试重新初始化...")
                if self._init_session():
                    xsrf_token = self._get_xsrf_token()
                    if xsrf_token:
                        headers['X-XSRF-TOKEN'] = xsrf_token
                    response = self._session.post(url, headers=headers, data=payload, timeout=30)
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
            return {'status': -1, 'errMsg': '无法获取有效 Cookie'}

        url = f"{self.host}/topic/sendTopicMessage.do"
        headers = {
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
            response = self._session.post(url, headers=headers, json=payload, timeout=30)

            if response.status_code == 403:
                logger.warning("⚠️ 收到 403，尝试重新初始化...")
                if self._init_session():
                    xsrf_token = self._get_xsrf_token()
                    if xsrf_token:
                        headers['X-XSRF-TOKEN'] = xsrf_token
                    response = self._session.post(url, headers=headers, json=payload, timeout=30)
                    if response.status_code == 200:
                        logger.info("✅ 重新初始化后发送成功")
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