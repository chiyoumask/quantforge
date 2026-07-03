"""多用户账号存储 — 全局账号表 (admin 托管)。

设计:
  - 账号文件: data/user_data/users.json (chmod 0600), 全局唯一, 不按用户隔离
    (账号本身定义"谁是谁", 不能放进某个用户的目录里)。
  - 密码用 PBKDF2-HMAC-SHA256 哈希 (沿用原单密码方案的参数: 200k 迭代, 16B salt)。
  - 角色二态: admin (超管, 可增删用户/设到期) / user (普通用户)。
  - 状态三态: active / suspended (管理员手动暂停) / expired (到期自动失效)。
  - 使用周期: expires_at (ISO 字符串, None=永不过期); 到期后 effective_status 返回 expired。

约束:
  - username 正则 ^[a-zA-Z0-9_-]{2,32}$, 大小写敏感。
  - 不能删除最后一个 admin (避免无人可管)。
  - 密码至少 6 位。

由 services/auth.py (会话) 与 api/users.py (用户管理) 共同消费。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import secrets as _secrets
import threading
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# PBKDF2 参数 (NIST 推荐, 单次校验 ~100ms, 与原单密码方案一致)
_PBKDF2_ITER = 200_000
_SALT_LEN = 16

# username 校验: 字母数字下划线连字符, 2-32 字符
_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_-]{2,32}$")

SCHEMA_VERSION = 1

_lock = threading.Lock()


# ================================================================
# 存储读写
# ================================================================

def _path() -> "Path":
    from app.config import settings
    p = settings.data_dir / "user_data" / "users.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load() -> dict:
    p = _path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            logger.warning("users.json malformed: %s", e)
    return {"schema_version": SCHEMA_VERSION, "users": []}


def _save(data: dict) -> None:
    p = _path()
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass


# ================================================================
# 密码哈希 (PBKDF2-HMAC-SHA256)
# ================================================================

def _hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    """返回 (salt_hex, hash_hex)。salt 为 None 时生成新 salt。"""
    if salt is None:
        salt = os.urandom(_SALT_LEN)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITER)
    return salt.hex(), dk.hex()


def _verify_password(password: str, salt_hex: str, hash_hex: str) -> bool:
    """恒定时间比较, 防时序攻击。"""
    try:
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except ValueError:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITER)
    return _secrets.compare_digest(actual, expected)


# ================================================================
# 时间/状态工具
# ================================================================

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def is_expired(user: dict) -> bool:
    """用户是否已过使用周期。expires_at 为 None 表示永不过期。"""
    exp = user.get("expires_at")
    if not exp:
        return False
    try:
        exp_dt = datetime.fromisoformat(exp)
    except ValueError:
        return False
    if exp_dt.tzinfo is None:
        exp_dt = exp_dt.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) >= exp_dt


def effective_status(user: dict) -> str:
    """实际生效状态: 到期自动归为 expired (优先于 suspended)。"""
    if not user:
        return "expired"
    if is_expired(user):
        return "expired"
    return user.get("status", "active")


def is_active(user: dict) -> bool:
    """用户当前是否可用 (active 且未到期)。"""
    return effective_status(user) == "active"


# ================================================================
# 账号 CRUD
# ================================================================

def _validate_username(username: str) -> str:
    u = (username or "").strip()
    if not _USERNAME_RE.match(u):
        raise ValueError("用户名仅允许字母数字下划线连字符, 2-32 字符")
    return u


def _validate_password(password: str) -> None:
    if not isinstance(password, str) or len(password) < 6:
        raise ValueError("密码至少 6 位")


def list_users() -> list[dict]:
    """返回全部用户 (脱敏, 不含密码字段)。按 username 排序。"""
    d = _load()
    return sorted([_public(u) for u in d.get("users", [])], key=lambda u: u["username"])


def get_user(username: str) -> dict | None:
    """取单个用户完整记录 (含密码 hash, 供校验)。不存在返回 None。"""
    d = _load()
    for u in d.get("users", []):
        if u.get("username") == username:
            return dict(u)
    return None


def user_exists(username: str) -> bool:
    return get_user(username) is not None


def count_admins() -> int:
    d = _load()
    return sum(1 for u in d.get("users", []) if u.get("role") == "admin")


def has_any_user() -> bool:
    d = _load()
    return bool(d.get("users"))


def create_user(
    username: str,
    password: str,
    role: str = "user",
    expires_at: str | None = None,
) -> dict:
    """创建用户。role 必须是 admin/user。expires_at 为 ISO 字符串或 None。
    返回脱敏用户记录。"""
    u = _validate_username(username)
    _validate_password(password)
    if role not in ("admin", "user"):
        raise ValueError("角色必须是 admin 或 user")
    salt_hex, hash_hex = _hash_password(password)
    now = _now_iso()
    record = {
        "username": u,
        "password_hash": hash_hex,
        "password_salt": salt_hex,
        "role": role,
        "status": "active",
        "expires_at": expires_at,
        "created_at": now,
        "updated_at": now,
    }
    with _lock:
        d = _load()
        if any(x.get("username") == u for x in d.get("users", [])):
            raise ValueError(f"用户名已存在: {u}")
        d.setdefault("users", []).append(record)
        _save(d)
    logger.info("user created: %s (role=%s)", u, role)
    return _public(record)


def delete_user(username: str) -> bool:
    """删除用户。禁止删除最后一个 admin (避免无人可管)。"""
    with _lock:
        d = _load()
        users = d.get("users", [])
        target = next((x for x in users if x.get("username") == username), None)
        if target is None:
            return False
        if target.get("role") == "admin":
            admins = [x for x in users if x.get("role") == "admin"]
            if len(admins) <= 1:
                raise ValueError("不能删除最后一个管理员账号")
        d["users"] = [x for x in users if x.get("username") != username]
        _save(d)
    logger.info("user deleted: %s", username)
    # 删除用户后, 该用户的所有会话由 auth 层清理由调用方触发
    return True


def update_user(username: str, **fields) -> dict:
    """更新用户字段 (role/status/expires_at)。不允许改 username/密码。
    status 仅接受 active/suspended/expired。"""
    allowed = {"role", "status", "expires_at"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        raise ValueError("无可更新字段")
    if "role" in updates and updates["role"] not in ("admin", "user"):
        raise ValueError("角色必须是 admin 或 user")
    if "status" in updates and updates["status"] not in ("active", "suspended", "expired"):
        raise ValueError("状态必须是 active/suspended/expired")
    with _lock:
        d = _load()
        users = d.get("users", [])
        target = next((x for x in users if x.get("username") == username), None)
        if target is None:
            raise ValueError(f"用户不存在: {username}")
        # 降级最后一个 admin 的保护
        if (
            target.get("role") == "admin"
            and updates.get("role") == "user"
            and sum(1 for x in users if x.get("role") == "admin") <= 1
        ):
            raise ValueError("不能降级最后一个管理员账号")
        target.update(updates)
        target["updated_at"] = _now_iso()
        _save(d)
    logger.info("user updated: %s -> %s", username, updates)
    return _public(target)


def reset_password(username: str, new_password: str) -> None:
    """管理员重置用户密码。"""
    _validate_password(new_password)
    salt_hex, hash_hex = _hash_password(new_password)
    with _lock:
        d = _load()
        target = next((x for x in d.get("users", []) if x.get("username") == username), None)
        if target is None:
            raise ValueError(f"用户不存在: {username}")
        target["password_hash"] = hash_hex
        target["password_salt"] = salt_hex
        target["updated_at"] = _now_iso()
        _save(d)
    logger.info("user password reset: %s", username)


def change_password(username: str, old_password: str, new_password: str) -> None:
    """用户自己改密码: 校验旧密码。"""
    _validate_password(new_password)
    with _lock:
        d = _load()
        target = next((x for x in d.get("users", []) if x.get("username") == username), None)
        if target is None:
            raise ValueError("用户不存在")
        if not _verify_password(old_password, target.get("password_salt", ""), target.get("password_hash", "")):
            raise ValueError("旧密码错误")
        salt_hex, hash_hex = _hash_password(new_password)
        target["password_hash"] = hash_hex
        target["password_salt"] = salt_hex
        target["updated_at"] = _now_iso()
        _save(d)
    logger.info("user password changed: %s", username)


def verify_password(username: str, password: str) -> bool:
    """校验用户密码。用户不存在或密码错均返回 False。"""
    u = get_user(username)
    if not u:
        return False
    return _verify_password(password, u.get("password_salt", ""), u.get("password_hash", ""))


# ================================================================
# 脱敏
# ================================================================

def _public(user: dict) -> dict:
    """返回不含密码字段的用户记录副本。"""
    out = {k: v for k, v in user.items() if k not in ("password_hash", "password_salt")}
    out["effective_status"] = effective_status(user)
    return out


def public_user(username: str) -> dict | None:
    u = get_user(username)
    return _public(u) if u else None
