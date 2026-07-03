"""告警触发记录存储 — JSONL 追加写 + 滚动清理。

职责:
  - 把每次触发的 AlertEvent 追加写入 data/user_data/alerts.jsonl
  - 提供查询 (按来源/类型过滤、时间倒序、限量)
  - 滚动清理: 保留近 N 天 + 上限 M 条 (取交集)

设计:
  - JSONL 每行一个 JSON 对象,便于增量追加和流式读取
  - 清理策略: 追加后按需 prune (按 ts 删旧),避免文件无限膨胀
  - 读时全量加载到内存过滤 (记录量受上限约束, 5000 条量级无压力)
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

# 保留策略
MAX_DAYS = 7
MAX_RECORDS = 5000
# 每隔多少次写入触发一次清理 (避免每次写都 prune)
PRUNE_EVERY = 20

_lock = threading.Lock()
_write_count = 0


def _path(data_dir: Path, owner: str | None = None) -> Path:
    """告警记录路径。owner 显式指定时按该用户路由 (监控引擎多用户场景);
    否则取当前请求上下文用户。"""
    from app.services import user_context
    p = user_context.user_data_dir_for(data_dir, owner) / "alerts.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def append(data_dir: Path, event: dict, owner: str | None = None) -> None:
    """追加一条触发记录。event 应含 ts(毫秒)、rule_id、source 等字段。
    owner 指定告警归属用户 (监控引擎按规则 owner 路由)。"""
    line = json.dumps(event, ensure_ascii=False)
    with _lock:
        p = _path(data_dir, owner)
        with p.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        global _write_count
        _write_count += 1
        if _write_count >= PRUNE_EVERY:
            _write_count = 0
            _prune_locked(p)


def append_many(data_dir: Path, events: list[dict], owner: str | None = None) -> None:
    """批量追加。owner 显式指定时全部归该用户; 否则按每条事件的 owner 字段分组路由
    (监控引擎 evaluate 产出的事件来自多用户规则, 每条带 owner)。"""
    if not events:
        return
    # 按 owner 分组: owner 参数优先, 否则取 ev["owner"], 都无则走当前上下文 (None)
    groups: dict[str | None, list[dict]] = {}
    if owner is not None:
        groups[owner] = list(events)
    else:
        for ev in events:
            key = ev.get("owner")
            groups.setdefault(key, []).append(ev)
    with _lock:
        global _write_count
        for grp_owner, evs in groups.items():
            p = _path(data_dir, grp_owner)
            with p.open("a", encoding="utf-8") as f:
                for ev in evs:
                    f.write(json.dumps(ev, ensure_ascii=False) + "\n")
            _write_count += len(evs)
            if _write_count >= PRUNE_EVERY:
                _write_count = 0
                _prune_locked(p)


def list_recent(
    data_dir: Path,
    days: int = MAX_DAYS,
    limit: int = MAX_RECORDS,
    source: str | None = None,
    type: str | None = None,
    owner: str | None = None,
) -> list[dict]:
    """读取近 N 天记录,按时间倒序,支持按 source/type 过滤。
    owner 默认取当前上下文用户 (前端只看自己的告警)。"""
    import time
    cutoff = (time.time() - days * 86400) * 1000  # 毫秒
    out: list[dict] = []
    p = _path(data_dir, owner)
    if not p.exists():
        return []
    try:
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except Exception:
                    continue
                if ev.get("ts", 0) < cutoff:
                    continue
                if source and ev.get("source") != source:
                    continue
                if type and ev.get("type") != type:
                    continue
                out.append(ev)
    except Exception as e:
        logger.warning("alert_store read failed: %s", e)
        return []
    # 时间倒序 + 截断
    out.sort(key=lambda x: x.get("ts", 0), reverse=True)
    return out[:limit]


def clear(data_dir: Path, owner: str | None = None) -> int:
    """清空全部记录,返回清除的条数。owner 默认取当前上下文用户。"""
    with _lock:
        p = _path(data_dir, owner)
        if not p.exists():
            return 0
        count = 0
        try:
            with p.open("r", encoding="utf-8") as f:
                count = sum(1 for line in f if line.strip())
        except Exception:
            pass
        p.write_text("", encoding="utf-8")
        return count


def delete_one(data_dir: Path, ts: int) -> bool:
    """删除指定 ts 的单条记录,返回是否删除成功。

    JSONL 无主键, 用 ts(毫秒时间戳) 作为标识。
    若存在多条同 ts, 只删第一条。
    """
    with _lock:
        p = _path(data_dir)
        if not p.exists():
            return False
        kept: list[dict] = []
        deleted = False
        try:
            with p.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ev = json.loads(line)
                    except Exception:
                        continue
                    if not deleted and ev.get("ts") == ts:
                        deleted = True
                        continue
                    kept.append(ev)
        except Exception as e:
            logger.warning("alert_store delete_one read failed: %s", e)
            return False
        if not deleted:
            return False
        try:
            with p.open("w", encoding="utf-8") as f:
                for ev in kept:
                    f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning("alert_store delete_one write failed: %s", e)
            return False
        return True
        return count


def count(data_dir: Path) -> int:
    """返回当前记录总数。"""
    p = _path(data_dir)
    if not p.exists():
        return 0
    try:
        with p.open("r", encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())
    except Exception:
        return 0


def _prune_locked(p: Path) -> None:
    """(调用方需持锁) 保留近 MAX_DAYS 天 + 上限 MAX_RECORDS 条。"""
    import time
    cutoff = (time.time() - MAX_DAYS * 86400) * 1000
    kept: list[dict] = []
    try:
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except Exception:
                    continue
                if ev.get("ts", 0) >= cutoff:
                    kept.append(ev)
    except FileNotFoundError:
        return
    except Exception as e:
        logger.warning("alert_store prune read failed: %s", e)
        return
    # 上限截断 (保留最新的)
    if len(kept) > MAX_RECORDS:
        kept.sort(key=lambda x: x.get("ts", 0))
        kept = kept[-MAX_RECORDS:]
    # 重写文件
    try:
        with p.open("w", encoding="utf-8") as f:
            for ev in kept:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning("alert_store prune write failed: %s", e)
