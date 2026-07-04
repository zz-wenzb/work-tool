# server.py
import asyncio
import threading
import socketserver
import http.server
import websockets
import socket
import logging
import os
from core.websocket_handler import handle_client
from core.task_manager import task_manager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('server.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def get_local_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def start_http_server():
    """启动 HTTP 服务器，提供 static 目录中的文件"""

    class CustomHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            # 设置目录为 static 文件夹
            super().__init__(*args, directory="static", **kwargs)

        def do_GET(self):
            """处理 GET 请求，根路径返回 index.html"""
            # 如果请求根路径，返回 index.html
            if self.path == '/' or self.path == '':
                self.path = '/index.html'
            # 如果请求 /static/ 开头的路径，去掉前缀
            elif self.path.startswith('/static/'):
                self.path = self.path[7:]  # 去掉 '/static'
            return super().do_GET()

        def log_message(self, format, *args):
            logger.info(f"HTTP: {format % args}")

    with socketserver.ThreadingTCPServer(("0.0.0.0", 8000), CustomHandler) as httpd:
        logger.info("🌐 网页访问地址: http://localhost:8000")
        logger.info(f"🌐 网页访问地址: http://{get_local_ip()}:8000")
        httpd.serve_forever()


async def cleanup_tasks_periodically():
    """定期清理过期任务"""
    while True:
        try:
            await task_manager.cleanup_expired_tasks(max_duration_minutes=60)
            active_count = await task_manager.get_active_task_count()
            logger.info(f"任务清理完成，当前活跃任务数: {active_count}")
            await asyncio.sleep(30 * 60)
        except Exception as e:
            logger.error(f"任务清理过程中发生错误: {e}")
            await asyncio.sleep(60)


async def main():
    logger.info("🚀 启动服务器...")

    ws_server = await websockets.serve(
        handle_client,
        "0.0.0.0",
        8765,
        ping_interval=20,
        ping_timeout=10,
        close_timeout=10,
    )
    logger.info("💬 WebSocket 服务器运行在 ws://localhost:8765")
    logger.info(f"💬 WebSocket 服务器运行在 ws://{get_local_ip()}:8765")

    http_thread = threading.Thread(target=start_http_server, daemon=True)
    http_thread.start()
    logger.info("🌐 HTTP 服务器已启动")

    cleanup_task = asyncio.create_task(cleanup_tasks_periodically())
    logger.info("🧹 任务清理协程已启动")

    logger.info("✅ 服务器启动完成，等待客户端连接...")
    await ws_server.wait_closed()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n🛑 服务器已关闭")
