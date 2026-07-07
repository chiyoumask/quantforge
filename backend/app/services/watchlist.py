"""自选股服务(§6.1)。

存储:`data/user_data/watchlist.parquet`,字段 symbol + added_at + note。
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import polars as pl

from app.config import settings
from app.tickflow.capabilities import CapabilitySet

logger = logging.getLogger(__name__)


def _path() -> Path:
    from app.services import user_context
    p = user_context.user_data_root() / "watchlist.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def list_symbols() -> list[dict]:
    p = _path()
    if not p.exists():
        return []
    df = pl.read_parquet(p)
    if df.is_empty():
        return []
    return df.to_dicts()


def count() -> int:
    """当前用户自选股数量。"""
    return len(list_symbols())


def add(symbol: str, note: str = "") -> list[dict]:
    p = _path()
    if p.exists():
        df = pl.read_parquet(p)
        # 已存在则先移除，后面重新插入到最前面
        if symbol in df["symbol"].to_list():
            df = df.filter(pl.col("symbol") != symbol)
    else:
        df = pl.DataFrame(schema={"symbol": pl.Utf8, "added_at": pl.Utf8, "note": pl.Utf8})

    new_row = pl.DataFrame({
        "symbol": [symbol],
        "added_at": [datetime.utcnow().isoformat(timespec="seconds")],
        "note": [note],
    })
    out = pl.concat([new_row, df], how="diagonal_relaxed")
    out.write_parquet(p)
    return out.to_dicts()


def remove(symbol: str) -> list[dict]:
    p = _path()
    if not p.exists():
        return []
    df = pl.read_parquet(p)
    df = df.filter(pl.col("symbol") != symbol)
    df.write_parquet(p)
    return df.to_dicts()


def move_to_top(symbol: str) -> list[dict]:
    p = _path()
    if not p.exists():
        return []
    df = pl.read_parquet(p)
    if df.is_empty() or symbol not in df["symbol"].to_list():
        return df.to_dicts()
    target = df.filter(pl.col("symbol") == symbol)
    rest = df.filter(pl.col("symbol") != symbol)
    out = pl.concat([target, rest], how="diagonal_relaxed")
    out.write_parquet(p)
    return out.to_dicts()


def clear() -> int:
    """清空自选列表。返回移除的数量。"""
    p = _path()
    if not p.exists():
        return 0
    df = pl.read_parquet(p)
    count = df.height
    if count > 0:
        pl.DataFrame(schema={"symbol": pl.Utf8, "added_at": pl.Utf8, "note": pl.Utf8}).write_parquet(p)
    return count


def fetch_quotes(symbols: list[str], capset: CapabilitySet | None = None, timeout_s: float = 8.0) -> list[dict]:
    """拉取自选股实时行情。

    走当前实时数据源 provider(get_realtime_data_provider()):
      - eastmoney / akshare / sina / qq 免费源 → 直接拉取,免费用户也能看自选股实时。
      - tickflow(付费备用)→ 走付费 client(按档位)。
    capset 参数保留兼容(供旧调用方传入),但不再用于"提前返回空"的门控。
    """
    from app.services import preferences
    from app.data_providers.registry import get_provider

    if not symbols:
        return []

    provider = preferences.get_realtime_data_provider()
    want = {str(s).upper() for s in symbols}
    try:
        if provider in ("eastmoney", "akshare", "sina", "qq"):
            df = get_provider(provider).get_realtime(symbols=symbols)
            if df.is_empty():
                return []
            return [r for r in df.to_dicts() if str(r.get("symbol") or "").upper() in want]
        # 付费备用源 tickflow: 走付费 client
        from app.tickflow.client import get_paid_realtime_client
        tf = get_paid_realtime_client()
        if tf is None:
            logger.warning("自选股实时行情拉取失败:未配置 TickFlow 付费 API Key (可在设置切换为东方财富/akshare 免费源)")
            return []
        raw = tf.quotes.get(symbols=symbols, as_dataframe=True)
        if raw is None or len(raw) == 0:
            return []
        df = pl.from_pandas(raw)
        rename_map = {
            "last_price": "price",
            "ext.change_pct": "pct",
            "ext.name": "name",
        }
        df = df.rename({k: v for k, v in rename_map.items() if k in df.columns})
        return df.to_dicts()
    except Exception as e:  # noqa: BLE001
        logger.warning("自选股实时行情拉取失败(provider=%s): %s", provider, e)
        return []
