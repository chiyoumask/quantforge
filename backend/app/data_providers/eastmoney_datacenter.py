"""东方财富 datacenter 扩展数据 — 资金流向 / 北向资金 / 龙虎榜 / 融资融券。

全部走东财公开接口 (免费、无 Key、境内可达), 用 stdlib urllib (与 eastmoney_provider 一致)。
按需取数 (非定时同步), 简单内存 TTL 缓存 (threading.Lock + ts, 仿 data.py 模式)。

⚠️ 字段码 (f51/f52…/RPT 列名) 基于东财公开 API 文档实现, 偶有调整;
   实现把字段映射集中为常量, 便于 VPS 实测后微调。
"""
from __future__ import annotations

import json
import logging
import threading
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

logger = logging.getLogger(__name__)

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
_REFERER = "https://quote.eastmoney.com/"

# TTL 缓存 (秒) — 这些数据日级更新, 缓存久一点无妨
_TTL_SHORT = 60        # 龙虎榜 (按日)
_TTL_DAILY = 300       # 资金流向/北向/融资融券 (日 K 级)

_lock = threading.Lock()
_cache: dict[str, tuple[float, object]] = {}


def _http_get(url: str, timeout: float = 8.0) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Referer": _REFERER})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        return json.loads(body)
    except Exception as e:  # noqa: BLE001
        logger.warning("eastmoney datacenter 请求失败 %s: %s", url[:80], e)
        return {}


def _num(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _secid(symbol: str) -> str | None:
    """600519.SH → 1.600519; 000001.SZ → 0.000001 (1=沪, 0=深)。"""
    s = symbol.strip().upper()
    if "." not in s:
        return None
    code, exch = s.split(".", 1)
    if exch == "SH":
        return f"1.{code}"
    if exch == "SZ":
        return f"0.{code}"
    return None


def _cached_fetch(key: str, ttl: int, fn):
    """简单 TTL 缓存包裹。"""
    with _lock:
        item = _cache.get(key)
        if item and (time.time() - item[0]) < ttl:
            return item[1]
    val = fn()
    with _lock:
        _cache[key] = (time.time(), val)
    return val


# ================================================================
# 1. 个股资金流向 (日 K)
# ================================================================

def fetch_capital_flow(symbol: str, days: int = 30) -> list[dict]:
    """个股资金流向日 K: 主力/超大单/大单/中单/小单净流入额 (元)。

    返回 [{date, main, super_large, large, medium, small}], 日期升序。
    """
    days = max(1, min(days, 180))
    secid = _secid(symbol)
    if not secid:
        return []
    key = f"capflow:{secid}:{days}"
    return _cached_fetch(key, _TTL_DAILY, lambda: _fetch_capital_flow_impl(secid, days))


def _fetch_capital_flow_impl(secid: str, days: int) -> list[dict]:
    # fields2 顺序: f51=日期 f52=主力净流入 f53=小单净流入 f54=中单净流入 f55=大单净流入 f56=超大单净流入
    params = urllib.parse.urlencode({
        "secid": secid, "klt": 101, "lmt": days,
        "fields1": "f1,f2,f3,f7",
        "fields2": "f51,f52,f53,f54,f55,f56",
    })
    url = f"http://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get?{params}"
    data = _http_get(url)
    klines = (data.get("data") or {}).get("klines") or []
    out: list[dict] = []
    for line in klines:
        f = line.split(",")
        if len(f) < 6:
            continue
        out.append({
            "date": f[0],
            "main": _num(f[1]),           # 主力净流入
            "small": _num(f[2]),          # 小单净流入
            "medium": _num(f[3]),         # 中单净流入
            "large": _num(f[4]),          # 大单净流入
            "super_large": _num(f[5]),    # 超大单净流入
        })
    return out


# ================================================================
# 2. 北向资金 (日 K)
# ================================================================

def fetch_northbound(days: int = 30) -> list[dict]:
    """北向资金日 K: 沪股通/深股通/北向合计净买入额 (元)。

    返回 [{date, hgt, sgt, total}], 日期升序。
    """
    days = max(1, min(days, 180))
    key = f"northbound:{days}"
    return _cached_fetch(key, _TTL_DAILY, lambda: _fetch_northbound_impl(days))


def _fetch_northbound_impl(days: int) -> list[dict]:
    # fields2: f51=日期 f52=沪股通净买入 f53=深股通净买入 f54=北向合计净买入
    params = urllib.parse.urlencode({
        "klt": 101, "lmt": days,
        "fields1": "f1,f2,f3,f4",
        "fields2": "f51,f52,f53,f54",
    })
    url = f"http://push2his.eastmoney.com/api/qt/kamt.kline/get?{params}"
    data = _http_get(url)
    klines = (data.get("data") or {}).get("klines") or []
    out: list[dict] = []
    for line in klines:
        f = line.split(",")
        if len(f) < 4:
            continue
        out.append({
            "date": f[0],
            "hgt": _num(f[1]),     # 沪股通净买入
            "sgt": _num(f[2]),     # 深股通净买入
            "total": _num(f[3]),   # 北向合计
        })
    return out


# ================================================================
# 3. 龙虎榜
# ================================================================

def fetch_dragon_tiger(trade_date: str | None = None) -> list[dict]:
    """龙虎榜明细 (指定交易日)。

    返回 [{code, name, date, reason, buy_amount, sell_amount, net_amount}]。
    trade_date 缺省取最近交易日 (今天或前一交易日)。
    """
    if not trade_date:
        trade_date = _latest_trade_date()
    key = f"dragontiger:{trade_date}"
    return _cached_fetch(key, _TTL_SHORT, lambda: _fetch_dragon_tiger_impl(trade_date))


def _fetch_dragon_tiger_impl(trade_date: str) -> list[dict]:
    params = urllib.parse.urlencode({
        "reportName": "RPT_DAILYBILLBOARD_DETAILS",
        "pageSize": 100, "pageNumber": 1,
        "sortColumns": "NET_AMOUNT", "sortTypes": "-1",
        "filter": f"(TRADE_DATE='{trade_date}')",
    })
    url = f"https://datacenter-web.eastmoney.com/api/data/v1/get?{params}"
    data = _http_get(url)
    rows = (data.get("result") or {}).get("data") or []
    out: list[dict] = []
    for r in rows:
        out.append({
            "code": r.get("SECURITY_CODE") or r.get("SECUCODE", ""),
            "name": r.get("SECURITY_NAME_ABBR") or r.get("SECURITY_NAME", ""),
            "date": (r.get("TRADE_DATE") or "")[:10],
            "reason": r.get("EXPLAIN") or "",
            "buy_amount": _num(r.get("BUY_AMOUNT")),
            "sell_amount": _num(r.get("SELL_AMOUNT")),
            "net_amount": _num(r.get("NET_AMOUNT")),
        })
    return out


# ================================================================
# 4. 融资融券 (两市余额)
# ================================================================

def fetch_margin(days: int = 30) -> list[dict]:
    """两市融资融券余额日 K。

    返回 [{date, rzye, rqye, total}], 日期升序。rzye=融资余额, rqye=融券余额。
    """
    days = max(1, min(days, 180))
    key = f"margin:{days}"
    return _cached_fetch(key, _TTL_DAILY, lambda: _fetch_margin_impl(days))


def _fetch_margin_impl(days: int) -> list[dict]:
    params = urllib.parse.urlencode({
        "reportName": "RPTA_WEB_RZRQ_BALANCE",
        "pageSize": min(days, 200), "pageNumber": 1,
        "sortColumns": "TRADE_DATE", "sortTypes": "-1",
    })
    url = f"https://datacenter-web.eastmoney.com/api/data/v1/get?{params}"
    data = _http_get(url)
    rows = (data.get("result") or {}).get("data") or []
    out: list[dict] = []
    for r in rows:
        out.append({
            "date": (r.get("TRADE_DATE") or "")[:10],
            "rzye": _num(r.get("RZYE")),     # 融资余额
            "rqye": _num(r.get("RQYE")),     # 融券余额
            "total": _num(r.get("RZRQYE")),  # 融资融券余额
        })
    out.reverse()  # API 默认降序, 反转为升序
    return out


# ================================================================
# 工具
# ================================================================

def _latest_trade_date() -> str:
    """最近交易日 (今天非交易日则回退)。简单兜底: 周末回退到周五。"""
    today = date.today()
    while today.weekday() >= 5:  # 5=周六 6=周日
        today = today - timedelta(days=1)
    return today.isoformat()


def invalidate_cache() -> None:
    """清空扩展数据缓存 (数据清理/手动刷新时调用)。"""
    with _lock:
        _cache.clear()
