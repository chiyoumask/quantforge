"""凭据本地存储 — 拆分为全局与 per-user 两类。

拆分原因 (Issue: 之前全局共享 secrets.json, 导致管理员 AI/TickFlow Key 泄露给
普通用户, 且普通用户改配置会反向影响管理员):

  - 全局 (data/user_data/secrets.json, chmod 0600): TickFlow 凭据 (tickflow_api_key /
    tickflow_base_url)。这些用于拉取「全实例共享」的行情数据 (K线/标的/实时),
    由超管托管, 普通用户不可见不可改。
  - per-user (data/user_data/{username}/secrets.json): AI 配置 (ai_api_key /
    ai_base_url / ai_model / ai_provider / ai_codex_command / ai_user_agent)。
    每个用户自行配置, 互不可见。AI 生成在请求上下文中按当前用户读取。

优先级: secrets.json(对应作用域) > .env > 空。
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


# ================================================================
# 路径
# ================================================================

def _global_path() -> Path:
    """全局凭据 (TickFlow Key 等, 超管托管)。"""
    from app.config import settings
    p = settings.data_dir / "user_data" / "secrets.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _user_path() -> Path:
    """per-user 凭据 (AI 配置, 每用户独立)。"""
    from app.services import user_context
    p = user_context.user_data_root() / "secrets.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


# ================================================================
# 通用读写
# ================================================================

def _load(p: Path) -> dict:
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            logger.warning("secrets file malformed (%s): %s", p, e)
    return {}


def _save(p: Path, data: dict) -> None:
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass


def _clear(p: Path, keys: tuple[str, ...]) -> dict:
    if not p.exists():
        return {}
    if not keys:
        p.unlink()
        return {}
    data = _load(p)
    for k in keys:
        data.pop(k, None)
    _save(p, data)
    return data


# ================================================================
# 全局 (TickFlow 凭据)
# ================================================================

def load_global() -> dict:
    return _load(_global_path())


def save_global(updates: dict) -> dict:
    """合并写入全局凭据 (TickFlow Key 等)。返回新内容。"""
    current = load_global()
    current.update({k: v for k, v in updates.items() if v is not None})
    _save(_global_path(), current)
    return current


def clear_global(*keys: str) -> dict:
    return _clear(_global_path(), keys)


def get_tickflow_key() -> str:
    """取当前 TickFlow Key: 全局 secrets.json 优先, 否则 .env。"""
    val = load_global().get("tickflow_api_key")
    if val:
        return val
    from app.config import settings
    return settings.tickflow_api_key or ""


def get_tickflow_base_url() -> str | None:
    """取用户自定义 TickFlow 付费端点 (None=用 SDK 默认)。"""
    return load_global().get("tickflow_base_url") or None


# ================================================================
# per-user (AI 配置)
# ================================================================

def load_user() -> dict:
    """读取当前用户的 AI 配置。"""
    return _load(_user_path())


def save_user(updates: dict) -> dict:
    """合并写入当前用户的 AI 配置。返回新内容。"""
    current = load_user()
    current.update({k: v for k, v in updates.items() if v is not None})
    _save(_user_path(), current)
    return current


def clear_user(*keys: str) -> dict:
    return _clear(_user_path(), keys)


def get_ai_key() -> str:
    """取当前用户的 AI Key: per-user secrets.json 优先, 否则 .env。"""
    val = load_user().get("ai_api_key")
    if val:
        return val
    from app.config import settings
    return settings.ai_api_key or ""


def get_ai_config(key: str, default: str = "") -> str:
    """取当前用户的 AI 配置项: per-user secrets.json 优先, 否则 config 默认。"""
    val = load_user().get(key)
    if val:
        return val
    from app.config import settings
    return getattr(settings, key, default) or default


# ================================================================
# 兼容旧调用 (tickflow client 等读 tickflow_base_url 用 load())
# ================================================================

def load() -> dict:
    """旧接口: 返回全局凭据。TickFlow 相关用此; AI 相关请改用 load_user()。"""
    return load_global()


def save(updates: dict) -> dict:
    """旧接口: 写入全局凭据 (TickFlow 相关)。AI 相关请改用 save_user()。"""
    return save_global(updates)


def clear(*keys: str) -> dict:
    """旧接口: 清全局凭据。"""
    return clear_global(*keys)


def mask(key: str, prefix: int = 4, suffix: int = 4) -> str:
    """脱敏显示。"""
    if not key:
        return ""
    if len(key) <= prefix + suffix:
        return "•" * len(key)
    return f"{key[:prefix]}{'•' * 6}{key[-suffix:]}"
