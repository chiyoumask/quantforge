"""一次性数据迁移 — 单用户 → 多用户。

启动时在 auth bootstrap 之前运行 (幂等: 已迁移则跳过)。

迁移内容:
  1. 旧 auth.json (单密码) → users.json (admin 账号, 复用旧 hash) + sessions.json (新格式)。
     迁后 auth.json 重命名为 auth.json.legacy.bak (不删, 留底)。
  2. 顶层 user_data 用户态文件 → user_data/admin/ (per-user 隔离)。
     全局文件 (secrets.json / users.json / sessions.json) 保留在顶层不动。
  3. data/strategies/{custom,ai}/ → user_data/admin/strategies/{custom,ai}/
  4. data/backtest_results/ → user_data/admin/backtest_results/

安全: 仅在源存在且目标不存在时移动; 任一目标已存在即视为已迁移, 跳过该项。
"""
from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

# 顶层 user_data 中需要迁入 admin 目录的文件/目录 (全局文件除外)
# preferences.json 保持全局 (系统级配置, 不按用户隔离), 故不在此列。
_USER_DATA_MIGRANTS = [
    "watchlist.parquet",
    "alerts.jsonl",
    "ai_reports.json",
    "ai_stock_reports.json",
    "ai_market_recaps.json",
    "strategy_cache.json",
    "monitor_rules",
    "custom_signals",
    "strategy_overrides",
]

# 保留在顶层 user_data 的全局文件 (不迁移)
_GLOBAL_FILES = {"secrets.json", "users.json", "sessions.json", "auth.json", "auth.json.legacy.bak"}


def _user_data_dir() -> Path:
    from app.config import settings
    p = settings.data_dir / "user_data"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _admin_dir() -> Path:
    p = _user_data_dir() / "admin"
    p.mkdir(parents=True, exist_ok=True)
    return p


# ================================================================
# 1. auth.json → users.json + sessions.json
# ================================================================

def migrate_legacy_auth() -> bool:
    """旧单密码 auth.json → 多用户 users.json。

    Returns: True 表示本次执行了迁移。
    """
    from app.config import settings
    from app.services import user_store

    users_path = _user_data_dir() / "users.json"
    if users_path.exists():
        return False  # 已是多用户模式

    auth_path = _user_data_dir() / "auth.json"
    if not auth_path.exists():
        return False

    try:
        legacy = json.loads(auth_path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        logger.warning("legacy auth.json unreadable, skip migration: %s", e)
        return False

    if not legacy.get("password_hash"):
        logger.info("legacy auth.json has no password, skip migration")
        return False

    username = (settings.admin_username or "admin").strip()
    # 直接复用旧 hash (无明文, 不重新哈希)
    record = {
        "username": username,
        "password_hash": legacy["password_hash"],
        "password_salt": legacy.get("password_salt", ""),
        "role": "admin",
        "status": "active",
        "expires_at": None,
        "created_at": str(legacy.get("updated_at", "")),
        "updated_at": str(legacy.get("updated_at", "")),
    }
    users_data = {"schema_version": user_store.SCHEMA_VERSION, "users": [record]}
    users_path.write_text(json.dumps(users_data, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        import os
        os.chmod(users_path, 0o600)
    except OSError:
        pass

    # 迁移会话: 旧格式 {token: expire_ts} → 新格式 {token: {username, expire}}
    old_sessions = legacy.get("sessions") or {}
    if isinstance(old_sessions, dict) and old_sessions:
        new_sessions = {
            t: {"username": username, "expire": exp}
            for t, exp in old_sessions.items()
            if isinstance(exp, (int, float))
        }
        sessions_path = _user_data_dir() / "sessions.json"
        sessions_path.write_text(
            json.dumps(new_sessions, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        try:
            import os
            os.chmod(sessions_path, 0o600)
        except OSError:
            pass

    # 旧文件留底 (不删, 避免误判; 用户可手动清理)
    bak = auth_path.with_name("auth.json.legacy.bak")
    try:
        shutil.move(str(auth_path), str(bak))
    except Exception as e:  # noqa: BLE001
        logger.warning("rename legacy auth.json to .bak failed (非致命): %s", e)

    logger.info("migrated legacy auth.json → users.json (admin=%s)", username)
    return True


# ================================================================
# 2-4. 用户态文件 → user_data/admin/
# ================================================================

def _safe_move(src: Path, dst: Path) -> None:
    """源存在且目标不存在时移动; 否则跳过。"""
    if not src.exists():
        return
    if dst.exists():
        return  # 目标已存在, 视为已迁移, 跳过
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.move(str(src), str(dst))
        logger.info("migrated %s → %s", src.name, dst)
    except Exception as e:  # noqa: BLE001
        logger.warning("migrate %s failed (非致命, 可手动搬迁): %s", src, e)


def migrate_legacy_user_data() -> bool:
    """顶层 user_data 用户态文件 + data/strategies + data/backtest_results → admin 目录。

    幂等: admin 目录已存在相关文件则跳过对应项。secrets.json 等全局文件保留顶层。
    """
    from app.config import settings

    admin = _admin_dir()
    moved_any = False

    # user_data 顶层用户态文件/目录
    ud = _user_data_dir()
    for name in _USER_DATA_MIGRANTS:
        src = ud / name
        if src.exists():
            _safe_move(src, admin / name)
            moved_any = True

    # data/strategies/{custom,ai} → admin/strategies/{custom,ai}
    for sub in ("custom", "ai"):
        src = settings.data_dir / "strategies" / sub
        if src.exists():
            _safe_move(src, admin / "strategies" / sub)
            moved_any = True

    # data/backtest_results → admin/backtest_results
    bt_src = settings.data_dir / "backtest_results"
    if bt_src.exists() and any(bt_src.iterdir()):
        # 整目录搬迁: 目标不存在时移, 已存在则逐项移
        dst = admin / "backtest_results"
        if not dst.exists():
            _safe_move(bt_src, dst)
            moved_any = True
        else:
            for f in list(bt_src.iterdir()):
                _safe_move(f, dst / f.name)
                moved_any = True

    if moved_any:
        logger.info("migrated legacy user_data → %s", admin)
    return moved_any


def migrate_split_secrets() -> bool:
    """拆分旧全局 secrets.json: AI 字段迁到 admin 的 per-user 文件, TickFlow 凭据留全局。

    之前 AI 配置 (ai_*) 存在全局 secrets.json, 与 TickFlow Key 混在一起, 导致多用户
    下管理员 AI Key 泄露给普通用户。迁移: 把 ai_* 字段搬到 data/user_data/admin/secrets.json,
    全局只保留 tickflow_api_key / tickflow_base_url。幂等。
    """
    import json
    global_path = _user_data_dir() / "secrets.json"
    if not global_path.exists():
        return False
    try:
        data = json.loads(global_path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        logger.warning("secrets.json unreadable, skip split: %s", e)
        return False

    ai_keys = {
        "ai_api_key", "ai_base_url", "ai_model", "ai_provider",
        "ai_codex_command", "ai_user_agent",
    }
    ai_fields = {k: data[k] for k in ai_keys if k in data}
    if not ai_fields:
        return False  # 无 AI 字段, 无需拆分

    # 写入 admin 的 per-user secrets.json (合并, 不覆盖已有)
    admin_secrets = _admin_dir() / "secrets.json"
    existing = {}
    if admin_secrets.exists():
        try:
            existing = json.loads(admin_secrets.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            existing = {}
    # 只补缺失的字段 (不覆盖 admin 可能已自行改过的)
    for k, v in ai_fields.items():
        existing.setdefault(k, v)
    admin_secrets.parent.mkdir(parents=True, exist_ok=True)
    admin_secrets.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        import os
        os.chmod(admin_secrets, 0o600)
    except OSError:
        pass

    # 从全局 secrets.json 移除 AI 字段
    for k in ai_keys:
        data.pop(k, None)
    global_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("migrated AI secrets → admin per-user (global keeps tickflow only)")
    return True


def run_all() -> None:
    """启动时调用: 执行全部迁移 (幂等)。"""
    try:
        migrate_legacy_auth()
    except Exception as e:  # noqa: BLE001
        logger.warning("legacy auth migration failed: %s", e)
    try:
        migrate_legacy_user_data()
    except Exception as e:  # noqa: BLE001
        logger.warning("legacy user_data migration failed: %s", e)
    try:
        migrate_split_secrets()
    except Exception as e:  # noqa: BLE001
        logger.warning("secrets split migration failed: %s", e)
