"""多用户会话管理 — token ↔ username 绑定。

设计:
  - 账号存储 (users.json) 与密码哈希职责在 services/user_store.py; 本模块只管会话。
  - 会话 token 用 secrets.token_urlsafe, 内存 + 文件双存 (data/user_data/sessions.json),
    支持多进程/重启不丢失, 沿用原单密码方案的恢复模式。
  - 会话绑定 username; is_valid_session 同时校验用户仍 active 且未到期
    (到期/暂停后在线会话立即失效, 下次请求即被中间件拦截)。

安全要点:
  - 设首个 admin 仍限本机/内网 (见 auth router), 防公网抢占。
  - 登录限流: 错5次锁5分钟 (见 auth router 内存计数)。
"""
from __future__ import annotations

import json
import logging
import os
import secrets as _secrets
import threading
import time
from pathlib import Path

from app.services import user_store

logger = logging.getLogger(__name__)

_TOKEN_BYTES = 32

# 会话有效期: 30 天 (自托管, 长一点减少重登频率)
SESSION_TTL = 30 * 24 * 3600

_lock = threading.Lock()
# 内存中的有效会话: { token: { username, expire } }。进程重启后从磁盘恢复。
_sessions: dict[str, dict] = {}


def _path() -> Path:
    from app.config import settings
    p = settings.data_dir / "user_data" / "sessions.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load_sessions_file() -> dict:
    p = _path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            logger.warning("sessions.json malformed: %s", e)
    return {}


def _save_sessions_locked() -> None:
    """把当前内存会话写回 sessions.json (需持锁调用)。"""
    p = _path()
    p.write_text(
        json.dumps(
            {t: s for t, s in _sessions.items()},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass


# ================================================================
# 配置状态
# ================================================================

def is_configured() -> bool:
    """是否已初始化 (至少存在一个 admin 账号)。"""
    return user_store.count_admins() > 0


def bootstrap_from_env() -> bool:
    """首次初始化: 若环境变量 ADMIN_USERNAME/ADMIN_PASSWORD 已配置且尚无用户, 则创建首个 admin。

    公网服务器部署场景: 避免每次都要 SSH 端口转发才能设首个账号。
    兼容: 若仅设了旧版 AUTH_PASSWORD, 用它作 admin 密码 (用户名取 ADMIN_USERNAME 或默认 admin)。
    一旦设置成功, 后续重启不再覆盖 (改密码/用户管理走 UI)。

    Returns:
        True 表示本次用环境变量初始化了账号; False 表示无需初始化。
    """
    from app.config import settings

    username = (settings.admin_username or "admin").strip()
    password = (settings.admin_password or settings.auth_password or "").strip()
    if not password:
        return False
    if user_store.has_any_user():
        return False
    try:
        user_store.create_user(username, password, role="admin", expires_at=None)
        logger.info("admin account bootstrapped from env (one-time): %s", username)
        return True
    except ValueError as e:
        logger.warning("admin bootstrap skipped: %s", e)
        return False


# ================================================================
# 会话生命周期
# ================================================================

def verify_and_create_session(username: str, password: str) -> str | None:
    """验证用户名+密码, 成功则创建会话并返回 token。

    拒绝条件: 用户不存在 / 密码错 / 状态非 active / 已到期。
    """
    user = user_store.get_user(username)
    if not user:
        return None
    if not user_store.verify_password(username, password):
        return None
    if not user_store.is_active(user):
        # 到期或暂停: 拒绝登录
        return None
    token = _secrets.token_urlsafe(_TOKEN_BYTES)
    expire = time.time() + SESSION_TTL
    with _lock:
        _sessions[token] = {"username": username, "expire": expire}
        _save_sessions_locked()
    return token


def revoke_session(token: str) -> None:
    """注销会话(登出)。"""
    with _lock:
        _sessions.pop(token, None)
        _save_sessions_locked()


def revoke_all_for_user(username: str) -> int:
    """注销某用户的所有会话 (改密码/暂停/删除/到期时调用)。返回清除条数。"""
    n = 0
    with _lock:
        for token in [t for t, s in _sessions.items() if s.get("username") == username]:
            _sessions.pop(token, None)
            n += 1
        if n:
            _save_sessions_locked()
    return n


def get_user_from_session(token: str) -> dict | None:
    """取会话对应的用户记录 (脱敏)。无效返回 None。"""
    if not token:
        return None
    with _lock:
        s = _sessions.get(token)
        if s is None:
            return None
        if time.time() > s.get("expire", 0):
            _sessions.pop(token, None)
            _save_sessions_locked()
            return None
    # 实时校验用户仍可用 (到期/暂停/删除后立即失效)
    user = user_store.get_user(s["username"])
    if not user or not user_store.is_active(user):
        with _lock:
            _sessions.pop(token, None)
            _save_sessions_locked()
        return None
    return user_store._public(user)


def is_valid_session(token: str) -> bool:
    """检查会话是否有效(存在 + 未过期 + 用户仍 active 且未到期)。"""
    return get_user_from_session(token) is not None


def session_username(token: str) -> str | None:
    """快捷取会话用户名 (不校验 active, 供中间件做轻量判断前先取身份)。
    完整校验仍由 get_user_from_session / is_valid_session 负责。"""
    if not token:
        return None
    with _lock:
        s = _sessions.get(token)
        if s is None:
            return None
        if time.time() > s.get("expire", 0):
            _sessions.pop(token, None)
            _save_sessions_locked()
            return None
        return s.get("username")


def _restore_sessions() -> None:
    """启动时从 sessions.json 恢复未过期会话(支持进程重启不丢登录态)。"""
    with _lock:
        data = _load_sessions_file()
        now = time.time()
        if isinstance(data, dict):
            for token, s in data.items():
                if not isinstance(s, dict):
                    continue
                expire = s.get("expire")
                if isinstance(expire, (int, float)) and expire > now:
                    _sessions[token] = {"username": s.get("username"), "expire": expire}
        if len(_sessions) != len(data if isinstance(data, dict) else {}):
            _save_sessions_locked()


# 兼容旧调用: change_password 由 user_store 实现, 此处转发并清理会话
def change_password(username: str, old_password: str, new_password: str) -> None:
    """用户自己改密码。成功后该用户所有会话失效 (强制重新登录)。"""
    user_store.change_password(username, old_password, new_password)
    revoke_all_for_user(username)


def set_password(password: str) -> None:
    """兼容旧接口: 仅在单用户迁移期用于初始化 admin 密码。已弃用, 请用 user_store.create_user。"""  # noqa: D401
    raise NotImplementedError("set_password 已移除, 请用 user_store.create_user / change_password")


# 模块加载时恢复会话
try:
    _restore_sessions()
except Exception as e:  # noqa: BLE001
    logger.warning("restore sessions failed: %s", e)
