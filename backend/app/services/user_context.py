"""请求级用户身份上下文 — 多用户数据隔离的核心。

设计:
  - 用 contextvars.ContextVar 存当前请求的 username, 由 auth 中间件在每个请求入口设置。
  - 所有按用户隔离的存储服务 (preferences/watchlist/monitor_rules/...) 通过
    user_data_root() 取得自己专属的目录基准, 实现透明的 per-user 路径。
  - 行情数据 (kline_*/instruments_*/financials/...) 不经过此处, 保持全局共享。
  - 后台任务 (调度器/行情轮询) 无请求上下文; 需访问用户态数据时用 for_user() 显式切换,
    或由监控引擎按规则 owner 路由 (见 strategy/monitor.py)。
"""
from __future__ import annotations

import contextlib
import contextvars
import re
from pathlib import Path

# 当前请求的用户名。None 表示无请求上下文 (后台任务)。
_current_user: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_user", default=None
)

# username 必须与 user_store 的校验一致, 防止路径穿越 (.. / / 等)。
_SAFE_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_-]{2,32}$")


def set_current_user(username: str | None) -> None:
    """设置当前请求的用户名 (由 auth 中间件调用)。"""
    _current_user.set(username)


def current_username() -> str | None:
    """取当前用户名。无请求上下文时返回 None。"""
    return _current_user.get()


def require_username() -> str:
    """取当前用户名, 无则抛 RuntimeError (应在已登录请求路径上调用)。"""
    u = _current_user.get()
    if not u:
        raise RuntimeError("当前无用户上下文 (后台任务未通过 for_user 切换)")
    return u


def _safe_dir_name(username: str) -> str:
    """校验 username 并返回可安全拼接的目录名 (防路径穿越)。"""
    if not _SAFE_USERNAME_RE.match(username):
        raise ValueError(f"非法用户名, 拒绝拼接路径: {username!r}")
    return username


def user_data_root(username: str | None = None) -> Path:
    """返回某用户的用户态数据根目录。

    默认取当前上下文用户; 显式传 username 供后台任务/监控引擎按 owner 路由。
    不会自动创建 (由各存储服务的 _path()/_dir() mkdir)。
    """
    from app.config import settings

    u = username if username is not None else _current_user.get()
    if not u:
        # 无上下文 (后台任务误调用): 兜底到 admin, 避免崩溃; 正常路径不应走到这里。
        u = "admin"
    return settings.data_dir / "user_data" / _safe_dir_name(u)


def user_data_dir_for(data_dir: Path, owner: str | None = None) -> Path:
    """基于显式 data_dir 解析用户目录 (供接收 data_dir 参数的存储服务用)。

    与 user_data_root() 等价, 但用调用方传入的 data_dir 而非全局 settings.data_dir,
    便于 monitor_rules/custom_signals/alert_store 等保持 (data_dir, ...) 签名。
    """
    u = owner if owner is not None else _current_user.get()
    if not u:
        u = "admin"
    return data_dir / "user_data" / _safe_dir_name(u)


@contextlib.contextmanager
def for_user(username: str):
    """临时切换用户上下文 (供后台任务显式指定操作目标用户)。

    用法:
        with user_context.for_user("alice"):
            preferences.save({...})   # 写入 alice 的 preferences.json
    """
    token = _current_user.set(username)
    try:
        yield
    finally:
        _current_user.reset(token)
