import requests
import json

# 企微群机器人 Webhook
webhook = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=d0e04be1-e801-4273-91c2-6fa605fe2335"


class WeComNotifier:
    def __init__(self):
        self.webhook_url = webhook

    def _send_markdown(self, content: str):
        headers = {'Content-Type': 'application/json'}
        payload = {"msgtype": "markdown", "markdown": {"content": content}}
        try:
            resp = requests.post(self.webhook_url, headers=headers, data=json.dumps(payload))
            result = resp.json()
            if result.get("errcode") != 0:
                print(f"⚠️ 企微消息发送失败: {result}")
            else:
                print("✅ 企微消息发送成功")
        except Exception as e:
            print(f"⚠️ 企微消息请求异常: {e}")

    def notify_deploy_success(self, service_name: str, env: str = "prod", deploy_time: str = ""):
        content = f"""## 🚀 应用部署成功
> **应用名称**：`{service_name}`  
> **部署环境**：`{env}`  
> **完成时间**：{deploy_time or "刚刚"}  

"""
        self._send_markdown(content)

    def notify_deploy_failed(self, service_name: str, reason: str = "部署失败"):
        content = f"""## ❌ 应用部署失败
> **应用名称**：`{service_name}`  
> **失败原因**：{reason}  

"""
        self._send_markdown(content)

    def notify_check_failed(self, service_name: str, reason: str):
        content = f"""## ⚠️ 部署状态检查异常
> **应用名称**：`{service_name}`  
> **异常说明**：{reason}  

"""
        self._send_markdown(content)

    def notify_timeout(self, service_name: str):
        content = f"""## ⏳ 部署超时提醒
> **应用名称**：`{service_name}`  

"""
        self._send_markdown(content)

    def notify_no_workflow(self, service_name: str):
        content = f"""## ❗ 配置缺失警告
> **应用名称**：`{service_name}`  

"""
        self._send_markdown(content)