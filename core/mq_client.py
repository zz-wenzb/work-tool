import logging
from typing import Optional, Dict, Any, List, Generator
import time
import requests
import re
import json

logger = logging.getLogger(__name__)


class MQManager:
    def __init__(self, mq_config: Dict[str, Any]):
        self.host = mq_config.get('host')
        self.cookie = mq_config.get('cookie')
        self.username = mq_config.get('username')
        self.password = mq_config.get('password')

    def _get_xsrf_token(self) -> Optional[str]:
        """
        从 cookie 中提取 XSRF-TOKEN
        
        Returns:
            XSRF-TOKEN 值，如果不存在则返回 None
        """
        if not self.cookie:
            return None

        match = re.search(r'XSRF-TOKEN=([^;]+)', self.cookie)
        if match:
            return match.group(1)
        return None

    def login(self):
        """
        登录并仅更新 JSESSIONID
        如果未配置 username/password，则跳过登录（使用已有 cookie）
        """
        # 检查是否配置了账号密码
        if not self.username or not self.password:
            logger.warning("⚠️ 未配置 MQ 账号密码，跳过登录步骤（使用已有 cookie）")
            logger.warning("⚠️ 如果接口返回 403，请检查 cookie 是否过期，或在配置文件中添加 username/password")
            return True

        url = f"{self.host}/login/login.do"
        params = {
            "password": self.password,
            "username": self.username
        }

        headers = {
            'content-type': 'application/json;charset=UTF-8',
        }

        try:
            response = requests.post(url, params=params, headers=headers)

            if response.status_code == 200:
                # 获取响应头中的 Set-Cookie
                set_cookie = response.headers.get('Set-Cookie')
                print(set_cookie)

                if set_cookie:
                    # 使用正则提取新的 JSESSIONID
                    match = re.search(r'JSESSIONID=([^;]+)', set_cookie)
                    if match:
                        new_session_id = match.group(1)

                        # --- 核心替换逻辑 ---

                        # 1. 如果 self.cookie 为空，直接赋值
                        if not self.cookie:
                            self.cookie = f"JSESSIONID={new_session_id}"
                        else:
                            # 2. 如果已有 cookie，使用正则替换旧的 JSESSIONID
                            # 这样可以保留 apt.uid 等其他字段
                            if "JSESSIONID=" in self.cookie:
                                self.cookie = re.sub(
                                    r'JSESSIONID=[^;]+',
                                    f'JSESSIONID={new_session_id}',
                                    self.cookie
                                )
                            else:
                                # 如果没有 JSESSIONID，则追加
                                self.cookie += f"; JSESSIONID={new_session_id}"

                        # --- 替换结束 ---

                        print("✅ 登录成功，JSESSIONID 已更新")
                        print(self.cookie)
                        return True

                print("⚠️ 响应中未包含 Set-Cookie")
                return False

            else:
                print(f"❌ 登录失败，状态码: {response.status_code}")
                return False

        except Exception as e:
            print(f"❌ 登录发生异常: {e}")
            return False

    # core/mq_client.py

    def query_topic_message(self, topic: str, m: int = 15, page_size: int = 20, fetch_all: bool = False) -> dict:
        """
        查询topic消息列表

        Args:
            topic: Topic名称
            m: 查询最近多少分钟的消息
            page_size: 每页大小，默认20
            fetch_all: 是否获取所有分页（默认False，只取第一页）

        Returns:
            响应数据字典
        """
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
            response = requests.post(url, headers=headers, json=payload)

            if response.status_code != 200:
                logger.error(f"查询失败: {response.status_code}")
                return {'status': -1, 'errMsg': f'HTTP {response.status_code}'}

            first_page = response.json()

            # 如果只取第一页，或第一页失败，直接返回
            if not fetch_all or first_page.get('status') != 0:
                return first_page

            # ========== 以下只有 fetch_all=True 时才执行 ==========
            # 获取分页信息
            page_info = first_page.get('data', {}).get('page', {})
            total_pages = page_info.get('totalPages', 1)
            all_content = page_info.get('content', [])

            logger.info(f"获取全量数据: 共 {total_pages} 页")

            # 循环获取剩余页面
            for page_num in range(2, total_pages + 1):
                payload['pageNum'] = page_num
                response = requests.post(url, headers=headers, json=payload)

                if response.status_code == 200:
                    page_data = response.json()
                    if page_data.get('status') == 0:
                        content = page_data.get('data', {}).get('page', {}).get('content', [])
                        all_content.extend(content)
                        if page_num % 10 == 0:
                            logger.info(f"已获取 {page_num}/{total_pages} 页")
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
        """
        查询所有Topic列表（基础API）
        
        Returns:
            响应数据字典
        """
        url = f"{self.host}/topic/list.query"
        headers = {
            'Cookie': self.cookie,
            'content-type': 'application/json;charset=UTF-8',
        }

        # 添加 XSRF-TOKEN
        xsrf_token = self._get_xsrf_token()
        if xsrf_token:
            headers['X-XSRF-TOKEN'] = xsrf_token

        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"查询Topic列表失败: {response.status_code}, {response.text}")
            return {'status': -1, 'errMsg': f'HTTP {response.status_code}'}

    def query_cluster_info(self) -> dict:
        """
        查询集群信息，获取集群名称和 broker 列表
        
        Returns:
            响应数据字典，包含 clusterInfo 和 brokerServer 信息
        """
        url = f"{self.host}/cluster/list.query"
        headers = {
            'Cookie': self.cookie,
            'Content-Type': 'application/json;charset=UTF-8',
        }

        # 添加 XSRF-TOKEN
        xsrf_token = self._get_xsrf_token()
        if xsrf_token:
            headers['X-XSRF-TOKEN'] = xsrf_token

        try:
            response = requests.get(url, headers=headers)

            if response.status_code == 200:
                result = response.json()
                if result.get('status') == 0:
                    logger.info("✅ 查询集群信息成功")
                return result
            else:
                logger.error(f"❌ 查询集群信息失败: HTTP {response.status_code}")
                return {'status': -1, 'errMsg': f'HTTP {response.status_code}'}
        except Exception as e:
            logger.exception(f"❌ 查询集群信息异常: {e}")
            return {'status': -1, 'errMsg': str(e)}

    def get_message_detail(self, msg_id: str, topic: str) -> Optional[str]:
        """
        根据 msgId 和 topic 获取消息详情
        注意：根据最新响应，结构是 data -> messageView -> messageBody
        """
        detail_url = f"{self.host}/message/viewMessage.query"
        params = {
            "msgId": msg_id,
            "topic": topic
        }
        headers = {
            'Cookie': self.cookie
        }

        # 添加 XSRF-TOKEN
        xsrf_token = self._get_xsrf_token()
        if xsrf_token:
            headers['X-XSRF-TOKEN'] = xsrf_token

        try:
            response = requests.get(detail_url, headers=headers, params=params)
            response_data = response.json()

            if response_data.get('status') == 0:
                # ✅ 关键修改点：路径改为 ['data']['messageView']['messageBody']
                return response_data.get('data', {}).get('messageView', {}).get('messageBody')
            else:
                logger.error(f"详情接口错误: {response_data.get('errMsg')}")
                return None
        except Exception as e:
            logger.exception(f"获取详情异常: {e}")
            return None

    def create_topic(self, topic: str, cluster_name_list: list = None, broker_name_list: list = None,
                     message_type: str = "NORMAL", write_queue_nums: int = 8,
                     read_queue_nums: int = 8, perm: int = 7, auto_fetch_cluster: bool = True) -> dict:
        """
        创建 Topic
        
        Args:
            topic: Topic名称
            cluster_name_list: 集群名称列表，默认自动获取
            broker_name_list: Broker名称列表，默认自动获取
            message_type: 消息类型，默认 NORMAL
            write_queue_nums: 写队列数，默认8
            read_queue_nums: 读队列数，默认8
            perm: 权限，2=只读，4=只写，6=读写，7=继承，默认7
            auto_fetch_cluster: 是否自动获取集群和broker信息，默认True
            
        Returns:
            响应数据字典，格式: {'status': 0, 'data': {...}} 或 {'status': -1, 'errMsg': '...'}
        """
        # 自动获取集群和 broker 信息
        if auto_fetch_cluster and (not cluster_name_list or not broker_name_list):
            cluster_result = self.query_cluster_info()
            if cluster_result.get('status') == 0:
                data = cluster_result.get('data', {})
                cluster_info = data.get('clusterInfo', {})

                # 提取集群名称列表
                if not cluster_name_list:
                    cluster_addr_table = cluster_info.get('clusterAddrTable', {})
                    cluster_name_list = list(cluster_addr_table.keys()) if cluster_addr_table else ["DefaultCluster"]

                # 提取 broker 名称列表
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

        # 添加 XSRF-TOKEN
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
            response = requests.post(url, headers=headers, json=payload)

            if response.status_code == 200:
                result = response.json()
                if result.get('status') == 0:
                    logger.info(f"✅ Topic '{topic}' 创建成功")
                else:
                    logger.warning(f"⚠️ Topic '{topic}' 创建失败: {result.get('errMsg')}")
                return result
            else:
                logger.error(f"❌ 创建 Topic 失败: HTTP {response.status_code}")
                return {'status': -1, 'errMsg': f'HTTP {response.status_code}'}
        except Exception as e:
            logger.exception(f"❌ 创建 Topic 异常: {e}")
            return {'status': -1, 'errMsg': str(e)}

    def delete_topic(self, topic: str) -> dict:
        """
        删除 Topic
        
        Args:
            topic: Topic名称
            
        Returns:
            响应数据字典，格式: {'status': 0, 'data': {...}} 或 {'status': -1, 'errMsg': '...'}
        """
        url = f"{self.host}/topic/deleteTopic.do"
        headers = {
            'Cookie': self.cookie,
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        }

        # 添加 XSRF-TOKEN
        xsrf_token = self._get_xsrf_token()
        if xsrf_token:
            headers['X-XSRF-TOKEN'] = xsrf_token

        payload = {
            "topic": topic
        }

        try:
            response = requests.post(url, headers=headers, data=payload)

            if response.status_code == 200:
                result = response.json()
                if result.get('status') == 0:
                    logger.info(f"✅ Topic '{topic}' 删除成功")
                else:
                    logger.warning(f"⚠️ Topic '{topic}' 删除失败: {result.get('errMsg')}")
                return result
            else:
                logger.error(f"❌ 删除 Topic 失败: HTTP {response.status_code}")
                return {'status': -1, 'errMsg': f'HTTP {response.status_code}'}
        except Exception as e:
            logger.exception(f"❌ 删除 Topic 异常: {e}")
            return {'status': -1, 'errMsg': str(e)}

    def send_message(self, topic: str, message_body: str, tag: str = "", key: str = "",
                     trace_enabled: bool = False) -> dict:
        """
        发送消息到指定 Topic
        
        Args:
            topic: Topic名称，如 "dev%nt_cargo"
            message_body: 消息体内容（JSON字符串）
            tag: 消息标签，默认为空
            key: 消息键，默认为空
            trace_enabled: 是否启用追踪，默认False
            
        Returns:
            响应数据字典，格式: {'status': 0, 'data': {...}} 或 {'status': -1, 'errMsg': '...'}
            data包含: sendStatus, msgId, messageQueue, queueOffset, transactionId等
        """
        url = f"{self.host}/topic/sendTopicMessage.do"
        headers = {
            'Cookie': self.cookie,
            'Content-Type': 'application/json;charset=UTF-8',
        }

        # 添加 XSRF-TOKEN
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
            response = requests.post(url, headers=headers, json=payload)

            if response.status_code == 200:
                result = response.json()
                if result.get('status') == 0:
                    send_data = result.get('data', {})
                    msg_id = send_data.get('msgId', 'N/A')
                    send_status = send_data.get('sendStatus', 'N/A')
                    logger.info(f"✅ 消息发送成功 - msgId: {msg_id}, status: {send_status}")
                else:
                    logger.warning(f"⚠️ 消息发送失败: {result.get('errMsg')}")
                return result
            else:
                logger.error(f"❌ 发送消息失败: HTTP {response.status_code}")
                return {'status': -1, 'errMsg': f'HTTP {response.status_code}'}
        except Exception as e:
            logger.exception(f"❌ 发送消息异常: {e}")
            return {'status': -1, 'errMsg': str(e)}
