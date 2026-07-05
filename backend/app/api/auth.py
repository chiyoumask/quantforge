"""访问认证 API (多用户)。

端点:
  GET  /api/auth/status        — 是否已初始化、当前会话是否有效 + 当前用户名/角色
  POST /api/auth/setup         — 首次创建超管账号(仅限本机/内网, 防公网抢占)
  POST /api/auth/login         — 登录(用户名+密码 → 会话 token, 含限流)
  POST /api/auth/logout        — 注销当前会话
  POST /api/auth/change-password — 用户自己改密码(需已登录)

安全:
  - setup 端点只接受本机/内网请求(request.client.host), 公网请求 403。
    否则黑客可比用户更早扫到域名, 抢先建超管, 反客为主。
  - login 限流: 同一来源 IP 连续失败 5 次, 锁 5 分钟(内存计数)。
  - 会话 token 通过 HttpOnly cookie 下发, 前端无需手动管理。
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from threading import Lock

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.services import auth, user_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

COOKIE_NAME = "tf_session"
_COOKIE_MAX_AGE = 30 * 24 * 3600  # 与 SESSION_TTL 一致

# 限流: { ip: (fail_count, lock_until_ts) }
_fail_counter: dict[str, tuple[int, float]] = defaultdict(lambda: (0, 0.0))
_fail_lock = Lock()
_MAX_FAILS = 5
_LOCK_SECONDS = 300


def _is_local_network(host: str | None) -> bool:
    """是否本机或内网请求。

    反向代理(Nginx)场景下 request.client.host 是代理本身(127.0.0.1),
    需信任 X-Forwarded-For 的最左(原始客户端)。本项目部署若经反代,
    请在反代配置正确的 X-Forwarded-For(标准做法)。
    """
    if not host:
        return False
    if host in ("127.0.0.1", "::1", "localhost"):
        return True
    # 内网网段: 10.x / 172.16-31.x / 192.168.x
    if host.startswith("10.") or host.startswith("192.168."):
        return True
    if host.startswith("172."):
        try:
            second = int(host.split(".")[1])
            if 16 <= second <= 31:
                return True
        except (IndexError, ValueError):
            pass
    return False


def _client_ip(request: Request) -> str:
    """取真实客户端 IP(信任反代 X-Forwarded-For)。"""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check_login_rate_limit(ip: str) -> None:
    """登录失败限流检查, 触发则抛 429。"""
    with _fail_lock:
        count, until = _fail_counter.get(ip, (0, 0.0))
        now = time.time()
        if until > now:
            wait = int(until - now)
            raise HTTPException(
                status_code=429,
                detail=f"登录失败次数过多, 请 {wait} 秒后重试",
            )


def _record_login_fail(ip: str) -> None:
    """记录一次登录失败, 达阈值则锁定。"""
    with _fail_lock:
        count, until = _fail_counter.get(ip, (0, 0.0))
        count += 1
        if count >= _MAX_FAILS:
            until = time.time() + _LOCK_SECONDS
            logger.warning("auth login locked for %s after %d fails", ip, count)
        _fail_counter[ip] = (count, until)


def _clear_login_fails(ip: str) -> None:
    """登录成功后清除该 IP 的失败计数。"""
    with _fail_lock:
        _fail_counter.pop(ip, None)


def _set_session_cookie(response: Response, token: str) -> None:
    """统一会话 cookie 下发。"""
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=_COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        path="/",
        secure=False,  # 自托管可能无 HTTPS, 不强制 secure(建议反代加 HTTPS)
    )


# ================================================================
# 端点
# ================================================================

class SetupIn(BaseModel):
    username: str = Field(min_length=2, max_length=32)
    password: str = Field(min_length=6, max_length=128)


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=128)


class ChangePasswordIn(BaseModel):
    old_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=6, max_length=128)


@router.get("/status")
def auth_status(request: Request) -> dict:
    """认证状态: 是否已初始化 + 当前请求是否已登录 + 用户名/角色 + 自选股配额。"""
    token = request.cookies.get(COOKIE_NAME)
    user = auth.get_user_from_session(token) if token else None
    wl_limit = None
    ext_pages = False
    if user:
        from app.services import user_store
        wl_limit = user_store.get_effective_quota(user, "watchlist_limit")
        ext_pages = user_store.get_effective_feature(user, "ext_pages")
    return {
        "configured": auth.is_configured(),
        "authenticated": user is not None,
        "username": user.get("username") if user else None,
        "role": user.get("role") if user else None,
        "watchlist_limit": wl_limit,   # None=不限 (管理员)
        "ext_pages": ext_pages,        # 是否开放扩展页面 (/analysis/*)
    }


@router.post("/setup")
def setup_account(req: SetupIn, request: Request) -> dict:
    """首次创建超管账号。仅限本机/内网请求(防公网抢占)。

    若已存在任何用户, 返回 409(后续用户由管理员在用户管理页创建)。
    """
    client_ip = _client_ip(request)
    if not _is_local_network(client_ip):
        logger.warning("setup rejected from non-local ip: %s", client_ip)
        raise HTTPException(
            status_code=403,
            detail="首次创建账号仅允许本机或内网访问,请通过 SSH/本地浏览器操作",
        )

    if user_store.has_any_user():
        raise HTTPException(status_code=409, detail="账号已初始化,如需新增用户请登录后使用用户管理功能")

    user = user_store.create_user(req.username, req.password, role="admin", expires_at=None)
    logger.info("admin account set up from %s: %s", client_ip, req.username)
    return {"ok": True, "configured": True, "username": user["username"], "role": "admin"}


@router.post("/login")
def login(req: LoginIn, request: Request, response: Response) -> dict:
    """登录: 用户名+密码 → 会话 token(写 HttpOnly cookie)。含失败限流。"""
    ip = _client_ip(request)
    _check_login_rate_limit(ip)

    if not auth.is_configured():
        raise HTTPException(status_code=409, detail="尚未初始化账号,请先创建超管账号")

    token = auth.verify_and_create_session(req.username, req.password)
    if not token:
        # 细化提示: 用户不可用 (到期/暂停) 与密码错区分
        user = user_store.get_user(req.username)
        if user and not user_store.is_active(user):
            status = user_store.effective_status(user)
            _record_login_fail(ip)
            detail = "账号已暂停" if status == "suspended" else "账号已过期,请联系管理员"
            raise HTTPException(status_code=403, detail=detail, headers={"X-Account-Status": status})
        _record_login_fail(ip)
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    _clear_login_fails(ip)
    _set_session_cookie(response, token)
    user = user_store.public_user(req.username)
    return {
        "ok": True,
        "authenticated": True,
        "username": user["username"] if user else req.username,
        "role": user["role"] if user else None,
    }


@router.post("/logout")
def logout(request: Request, response: Response) -> dict:
    """注销当前会话。"""
    token = request.cookies.get(COOKIE_NAME)
    if token:
        auth.revoke_session(token)
    response.delete_cookie(key=COOKIE_NAME, path="/")
    return {"ok": True}


@router.post("/change-password")
def change_password(req: ChangePasswordIn, request: Request) -> dict:
    """修改密码: 需验证旧密码, 成功后该用户所有会话失效(含当前, 需重新登录)。"""
    token = request.cookies.get(COOKIE_NAME)
    user = auth.get_user_from_session(token) if token else None
    if not user:
        raise HTTPException(status_code=401, detail="请先登录")

    try:
        auth.change_password(user["username"], req.old_password, req.new_password)
    except ValueError as e:
        ip = _client_ip(request)
        _record_login_fail(ip)
        raise HTTPException(status_code=401, detail=str(e)) from None
    return {"ok": True, "message": "密码已修改, 请重新登录"}
