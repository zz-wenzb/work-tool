# server.py
import asyncio
import threading
import socketserver
import http.server
import websockets
import socket
import logging
from core.websocket_handler import handle_client
from core.task_manager import task_manager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('server.log', encoding='utf-8'),
        logging.StreamHandler()  # 同时输出到控制台
    ]
)
logger = logging.getLogger(__name__)

def get_local_ip():
    try:
        # 连接到一个远程地址以获取本地IP
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"

def start_http_server():
    """启动 HTTP 静态文件服务器，提供 index.html"""
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory="static", **kwargs)

    with socketserver.TCPServer(("0.0.0.0", 8000), Handler) as httpd:
        logger.info("🌐 网页访问地址: http://localhost:8000")
        logger.info(f"🌐 网页访问地址: http://{get_local_ip()}:8000")
        httpd.serve_forever()

async def cleanup_tasks_periodically():
    """定期清理过期任务"""
    while True:
        try:
            # 清理超过60分钟的任务
            await task_manager.cleanup_expired_tasks(max_duration_minutes=60)
            active_count = await task_manager.get_active_task_count()
            logger.info(f"任务清理完成，当前活跃任务数: {active_count}")
            # 每30分钟执行一次清理
            await asyncio.sleep(30 * 60)
        except Exception as e:
            logger.error(f"任务清理过程中发生错误: {e}")
            await asyncio.sleep(60)  # 出错后等待1分钟再重试

async def main():
    logger.info("🚀 启动服务器...")
    # 启动 WebSocket 服务器（监听根路径 /）
    ws_server = await websockets.serve(
        handle_client,
        "0.0.0.0",
        8765,
        ping_interval=20,  # 每20秒发送ping以保持连接
        ping_timeout=10,   # 10秒内未收到pong则认为连接断开
        close_timeout=10,  # 10秒内未关闭则强制关闭
        # 如果你想用路径（如 /ws），取消下一行注释，并同步修改前端
        # path="/ws"
    )
    logger.info("💬 WebSocket 服务器运行在 ws://localhost:8765")
    logger.info(f"💬 WebSocket 服务器运行在 ws://{get_local_ip()}:8765")

    # 在后台线程启动 HTTP 服务器
    http_thread = threading.Thread(target=start_http_server, daemon=True)
    http_thread.start()
    logger.info("🌐 HTTP 服务器已启动")
    
    # 启动定期任务清理协程
    cleanup_task = asyncio.create_task(cleanup_tasks_periodically())
    logger.info("🧹 任务清理协程已启动")

    logger.info("✅ 服务器启动完成，等待客户端连接...")
    # 保持 WebSocket 服务器运行
    await ws_server.wait_closed()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n🛑 服务器已关闭")