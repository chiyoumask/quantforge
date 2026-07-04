"""用户管理 API (仅超管)。

端点:
  GET    /api/users                — 列出全部用户 (脱敏)
  POST   /api/users                — 创建用户
  DELETE /api/users/{username}     — 删除用户
  PUT    /api/users/{username}     — 改角色/状态/到期
  POST   /api/users/{username}/reset-password — 重置密码

全部端点要求当前会话 role=admin, 否则 403。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.services import auth, user_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/users", tags=["users"])


def _require_admin(request: Request) -> dict:
    """校验当前会话为 admin, 否则 403。返回用户记录。"""
    user = getattr(request.state, "current_user", None)
    if not user or user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可访问用户管理")
    return user


def _parse_expires(v: str | None) -> str | None:
    """校验 ISO 时间字符串, 空串/None → None (永不过期)。"""
    if not v or not v.strip():
        return None
    from datetime import datetime
    try:
        datetime.fromisoformat(v)
    except ValueError:
        raise HTTPException(status_code=400, detail="expires_at 需为合法 ISO 时间字符串") from None
    return v


# ================================================================
# 模型
# ================================================================

class CreateUserIn(BaseModel):
    username: str = Field(min_length=2, max_length=32)
    password: str = Field(min_length=6, max_length=128)
    role: str = Field(default="user")  # admin | vip | user
    expires_at: str | None = Field(default=None)


class UpdateUserIn(BaseModel):
    role: str | None = None          # admin | vip | user
    status: str | None = None        # active | suspended | expired
    expires_at: str | None = None    # None=永不过期; 传空串清空
    watchlist_limit: int | None | str = None  # 逐用户自选股上限覆盖; None=不动; 数字=设值; "default"=回退角色默认


class ResetPasswordIn(BaseModel):
    new_password: str = Field(min_length=6, max_length=128)


# ================================================================
# 端点
# ================================================================

@router.get("")
def list_users(request: Request) -> list[dict]:
    """列出全部用户 (脱敏, 不含密码)。"""
    _require_admin(request)
    return user_store.list_users()


@router.post("", status_code=201)
def create_user(req: CreateUserIn, request: Request) -> dict:
    """创建用户。"""
    _require_admin(request)
    try:
        return user_store.create_user(
            req.username, req.password, role=req.role, expires_at=_parse_expires(req.expires_at)
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None


@router.delete("/{username}")
def delete_user(username: str, request: Request) -> dict:
    """删除用户。禁止删最后一个 admin。删后清除其会话。"""
    _require_admin(request)
    try:
        deleted = user_store.delete_user(username)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    if not deleted:
        raise HTTPException(status_code=404, detail=f"用户不存在: {username}")
    auth.revoke_all_for_user(username)
    return {"ok": True}


@router.put("/{username}")
def update_user(username: str, req: UpdateUserIn, request: Request) -> dict:
    """更新用户: 角色/状态/到期/自选股配额。状态改 suspended 或到期后, 在线会话立即失效。"""
    _require_admin(request)
    updates: dict = {}
    if req.role is not None:
        updates["role"] = req.role
    if req.status is not None:
        updates["status"] = req.status
    if req.expires_at is not None:
        # 空串表示清空到期 (永不过期)
        updates["expires_at"] = _parse_expires(req.expires_at) if req.expires_at.strip() else None
    if req.watchlist_limit is not None:
        # "default" → 回退角色默认 (清除逐用户覆盖); 数字 → 设定覆盖; 留空 None 不动
        wl = str(req.watchlist_limit).strip() if isinstance(req.watchlist_limit, str) else req.watchlist_limit
        if wl == "default" or wl == "":
            updates["quotas"] = {"watchlist_limit": None}   # 清除覆盖
        elif isinstance(wl, (int, str)) and str(wl).lstrip("-").isdigit():
            n = int(wl)
            if n < 0:
                raise HTTPException(status_code=400, detail="自选股上限不能为负数")
            updates["quotas"] = {"watchlist_limit": n if n > 0 else None}
    if not updates:
        raise HTTPException(status_code=400, detail="无可更新字段")
    try:
        result = user_store.update_user(username, **updates)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    # 不主动清除会话: 让中间件在下一次请求时按 effective_status 自然拒绝
    # (返回 403 ACCOUNT_EXPIRED, 比静默 401 更明确)。角色变更也无需 revoke ——
    # role 每次 get_user_from_session 都从 user_store 实时读取, 自动生效。
    return result


@router.post("/{username}/reset-password")
def reset_password(username: str, req: ResetPasswordIn, request: Request) -> dict:
    """管理员重置某用户密码。重置后该用户需重新登录。"""
    _require_admin(request)
    if not user_store.user_exists(username):
        raise HTTPException(status_code=404, detail=f"用户不存在: {username}")
    try:
        user_store.reset_password(username, req.new_password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    auth.revoke_all_for_user(username)
    return {"ok": True, "message": f"已重置 {username} 的密码"}
