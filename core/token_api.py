#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import redis
import sys
import base64
import json
import logging

# ================== 日志配置 ==================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# ================== 配置区 ==================
# 测试环境 API 地址
APP_TEST_ENV_URL = "https://test-oas.baoqi68.com/app-v1/ums-auth"
VUE_NT_TEST_ENV_URL = "https://test-tms.baoqi68.com/api-v1/tms-auth"

# 开发环境 Redis（目标）
DEV_REDIS_HOST = "192.168.1.20"
DEV_REDIS_PORT = 6379
DEV_REDIS_PASSWORD = "123456"
DEV_REDIS_DB = 1

# 测试环境 Redis（源）
TEST_REDIS_HOST = "test-redis.zhongbaozhiyun.com"
TEST_REDIS_PORT = 6379
TEST_REDIS_PASSWORD = "baoqi0411"
TEST_REDIS_DB = 0

# 登录账号
APP_USERNAME = "18525509251"
APP_PASSWORD = "Wzb199410191012"

VUE_NT_USERNAME = "wenzhibin"
VUE_NT_PASSWORD = "Wzb199410191012"

REDIS_MIGRATE_KEYS = [
    "example:key1",
    "example:key2",
]


# ===========================================


def get_captcha(url):
    """获取验证码（测试环境返回明文 code）"""
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data["data"]["uuid"], data["data"]["code"]
    except Exception as e:
        logger.error(f"获取验证码失败: {e}")
        raise


def login(login_url, username, password, uuid, code):
    """使用验证码登录并获取 token"""
    payload = {
        "userName": username,
        "password": password,
        "uuid": uuid,
        "code": code
    }
    try:
        resp = requests.post(login_url, json=payload, timeout=10)
        resp.raise_for_status()
        result = resp.json()
        token = result.get("data", {}).get("accessToken")
        refresh_token = result.get("data", {}).get("refreshToken")
        if not token or not refresh_token:
            raise RuntimeError(f"❌ 登录成功但未返回 token，响应: {result}")
        return token, refresh_token
    except Exception as e:
        logger.error(f"登录失败: {e}")
        raise


def migrate_redis_session(source_key, dest_key=None):
    """
    从测试环境 Redis 迁移一个 key 到开发环境 Redis，保留原始 value 和 TTL。
    适用于迁移 tms:auth:token:xxx 等会话数据。
    """
    if dest_key is None:
        dest_key = source_key

    src_r = redis.Redis(
        host=TEST_REDIS_HOST,
        port=TEST_REDIS_PORT,
        password=TEST_REDIS_PASSWORD,
        db=TEST_REDIS_DB,
        decode_responses=False,
        socket_connect_timeout=5,
        socket_timeout=5
    )

    dst_r = redis.Redis(
        host=DEV_REDIS_HOST,
        port=DEV_REDIS_PORT,
        password=DEV_REDIS_PASSWORD,
        db=DEV_REDIS_DB,
        decode_responses=False,
        socket_connect_timeout=5,
        socket_timeout=5
    )

    if not src_r.exists(source_key):
        logger.warning(f"警告：测试环境 Redis 中 key 不存在 → {source_key}")
        return False

    value = src_r.get(source_key)
    ttl = src_r.ttl(source_key)

    if ttl == -2:
        logger.warning(f"警告：key 已过期 → {source_key}")
        return False

    if ttl == -1:
        dst_r.set(dest_key, value)
    else:
        dst_r.setex(dest_key, ttl, value)

    logger.info(f"✅ 成功迁移 Redis key: {source_key} → {dest_key} (TTL={ttl}s)")
    return True


def parse_jwt_payload(token: str) -> dict:
    """
    解析 JWT token 的 payload 部分（不验证签名，仅用于读取用户信息）
    """
    try:
        parts = token.split('.')
        if len(parts) != 3:
            raise ValueError("Invalid JWT format")

        payload_b64 = parts[1]
        padding = '=' * (4 - (len(payload_b64) % 4))
        payload_b64_padded = payload_b64 + padding

        payload_json = base64.urlsafe_b64decode(payload_b64_padded)
        payload = json.loads(payload_json)
        return payload
    except Exception as e:
        raise ValueError(f"Failed to parse JWT token: {e}")


def app_start(username=None, password=None):
    username = username or APP_USERNAME
    password = password or APP_PASSWORD
    logger.info(f"1\ufe0f\u20e3 正在获取验证码... (用户: {username})")
    captcha_url = f"{APP_TEST_ENV_URL}/captcha"
    uuid, code = get_captcha(captcha_url)
    logger.info(f"   uuid: {uuid}\n   code: {code}")

    logger.info("2\ufe0f\u20e3 正在登录获取 token...")
    login_url = f"{APP_TEST_ENV_URL}/login/app/driver"
    token, refresh_token = login(login_url, username, password, uuid, code)
    logger.info(f"   R-Authorization: {refresh_token}")
    logger.info(f"   Authorization:  {token}")

    user_info = parse_jwt_payload(token)
    # sys_user:up-2:183712:1:SfiboMc2yPM-RYkLXwH72-Bearer
    session_key = f"sys_user:{user_info['p']}-{user_info['i']}:{user_info['u']}:{user_info['s']}:{refresh_token}"
    logger.info(f"3\ufe0f\u20e3 正在迁移用户会话数据: {session_key}")
    migrate_redis_session(session_key)

    logger.info(f"   - 你的 accessToken 已存入开发 Redis（key={session_key}）")
    return token, refresh_token


def vue_nt_start(username=None, password=None):
    username = username or VUE_NT_USERNAME
    password = password or VUE_NT_PASSWORD
    logger.info(f"1\ufe0f\u20e3 正在获取验证码... (用户: {username})")
    captcha_url = f"{VUE_NT_TEST_ENV_URL}/captcha"
    uuid, code = get_captcha(captcha_url)
    logger.info(f"   uuid: {uuid}\n   code: {code}")

    logger.info("2\ufe0f\u20e3 正在登录获取 token...")
    login_url = f"{VUE_NT_TEST_ENV_URL}/login"
    token, refresh_token = login(login_url, username, password, uuid, code)
    logger.info(f"   R-Authorization: {refresh_token}")
    logger.info(f"   Authorization:  {token}")

    user_info = parse_jwt_payload(token)
    session_key = f"sys_user:{user_info['p']}-{user_info['i']}:{user_info['u']}:{refresh_token}"
    logger.info(f"3\ufe0f\u20e3 正在迁移用户会话数据: {session_key}")
    migrate_redis_session(session_key)

    logger.info(f"   - 你的 accessToken 已存入开发 Redis（key={session_key}）")
    return token, refresh_token


def redis_migrate():
    logger.info("🚀 开始执行 Redis 迁移任务...")
    
    src_r = redis.Redis(
        host=TEST_REDIS_HOST,
        port=TEST_REDIS_PORT,
        password=TEST_REDIS_PASSWORD,
        db=TEST_REDIS_DB,
        decode_responses=False,
        socket_connect_timeout=5,
        socket_timeout=5
    )
    
    dst_r = redis.Redis(
        host=DEV_REDIS_HOST,
        port=DEV_REDIS_PORT,
        password=DEV_REDIS_PASSWORD,
        db=DEV_REDIS_DB,
        decode_responses=False,
        socket_connect_timeout=5,
        socket_timeout=5
    )
    
    success_keys = []
    skipped_keys = []
    failed_keys = []
    not_found_keys = []
    not_string_keys = []
    
    for key in REDIS_MIGRATE_KEYS:
        try:
            key_type = src_r.type(key)
            if isinstance(key_type, bytes):
                key_type = key_type.decode("utf-8")
            
            if key_type == "none":
                not_found_keys.append(key)
                logger.warning(f"key 不存在: {key}")
                continue
            
            if key_type != "string":
                not_string_keys.append(key)
                logger.warning(f"key 类型不是 string: {key} (类型: {key_type})")
                continue
            
            if dst_r.exists(key):
                skipped_keys.append(key)
                logger.info(f"目标已存在，跳过: {key}")
                continue
            
            value = src_r.get(key)
            ttl = src_r.ttl(key)
            
            if ttl > 0:
                dst_r.setex(key, ttl, value)
            elif ttl == -1:
                dst_r.set(key, value)
            else:
                skipped_keys.append(key)
                logger.info(f"key 已过期，跳过: {key}")
                continue
            
            success_keys.append(key)
            logger.info(f"✅ 迁移成功: {key} (TTL={ttl}s)")
            
        except Exception as e:
            failed_keys.append((key, str(e)))
            logger.error(f"迁移失败: {key}, 错误: {e}")
    
    src_r.close()
    dst_r.close()
    
    lines = [
        "✅ Redis 迁移任务完成",
        f"📊 统计:",
        f"  • 总计: {len(REDIS_MIGRATE_KEYS)}",
        f"  • 成功: {len(success_keys)}",
        f"  • 跳过(已存在): {len(skipped_keys)}",
        f"  • 不存在: {len(not_found_keys)}",
        f"  • 类型不匹配: {len(not_string_keys)}",
        f"  • 失败: {len(failed_keys)}",
    ]
    
    if failed_keys:
        lines.append("❌ 失败详情:")
        for key, err in failed_keys[:10]:
            lines.append(f"  • {key}: {err}")
    
    return "\n".join(lines)

