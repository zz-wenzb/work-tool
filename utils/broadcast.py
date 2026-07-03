# utils/broadcast.py

import json
import asyncio
import logging

# 导入websocket_handler以访问连接字典
from core import websocket_handler

# 配置日志
logger = logging.getLogger(__name__)


async def broadcast(message: dict):
    if isinstance(message, dict):
        message = json.dumps(message, ensure_ascii=False)
    
    client_count = len(websocket_handler.connected_clients)
    logger.debug(f"[广播消息] 目标客户端数: {client_count}")
    
    # 使用websocket_handler中的connected_clients字典
    if websocket_handler.connected_clients:
        results = await asyncio.gather(
            *[ws.send(message) for ws in websocket_handler.connected_clients.keys()],
            return_exceptions=True
        )
        
        # 检查是否有发送失败的情况
        failed_count = sum(1 for r in results if isinstance(r, Exception))
        if failed_count > 0:
            logger.warning(f"[广播消息] 发送失败: {failed_count}/{client_count} 客户端")
        else:
            logger.debug(f"[广播消息] 发送成功: {client_count} 客户端")
    else:
        logger.debug("[广播消息] 无连接客户端")


async def broadcast_message(msg_type: str, content: str):
    from datetime import datetime
    message = {
        "type": msg_type,
        "content": content,
        "time": datetime.now().strftime("%H:%M:%S")
    }
    await broadcast(message)