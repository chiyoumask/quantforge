"""腾讯财经实时行情 provider — 免费、按标的批量、备份源。

特点:
  - 按标的查询 (qt.gtimg.cn/q=sh600519,sz000001,...), 每批最多 ~50 只。
  - 全市场需多请求并发, 较慢 —— 定位为东方财富不可达时的备份源。
  - 无防盗链, 无需 Referer。
  - 输出与其它 provider 一致的 15 字段 records。

字段映射 (v_xxx="a~b~c~..." split by "~", 基于 qt.gtimg.cn 公开格式):
  [1]=name [2]=code [3]=last [4]=prev_close [5]=open [6]=volume(手) [7]=amount(元)
  [9]=high [10]=low  (涨跌幅/额 自行从 last/prev_close 计算, 不依赖腾讯计算字段)
  注: 腾讯字段位 occasionally 调整, last/prev_close([3]/[4]) 最稳定; high/low 位若
  偏移以 VPS 实测为准。成交量单位「手」×100 → 股 (对齐 TickFlow 日 K)。
"""
from __future__ import annotations

import logging
import re
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import polars as pl

from app.data_providers.base import AssetType, ProviderCapabilities

logger = logging.getLogger(__name__)

_URL = "http://qt.gtimg.cn/q="
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
_BATCH = 50


def _to_qq_code(symbol: str) -> str | None:
    """600519.SH → sh600519; 000001.SZ → sz000001 (指数同前缀)。"""
    s = symbol.strip().upper()
    if "." not in s:
        return None
    code, exch = s.split(".", 1)
    if exch == "SH":
        return f"sh{code}"
    if exch == "SZ":
        return f"sz{code}"
    return None


def _from_qq_code(qc: str) -> str | None:
    if qc.startswith("sh"):
        return f"{qc[2:]}.SH"
    if qc.startswith("sz"):
        return f"{qc[2:]}.SZ"
    return None


def _num(v) -> float | None:
    try:
        return float(str(v).strip())
    except (ValueError, TypeError):
        return None


def _http_get(url: str, timeout: float = 6.0) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("gbk", errors="replace")
    except Exception as e:  # noqa: BLE001
        logger.debug("qq http failed %s: %s", url[:60], e)
        return ""


def _is_index(symbol: str) -> bool:
    code = symbol.split(".")[0]
    return (symbol.endswith(".SH") and code.startswith("000")) or \
           (symbol.endswith(".SZ") and code.startswith("399"))


def _parse_response(text: str, want: set[str] | None = None) -> list[dict]:
    out: list[dict] = []
    now_ms = int(time.time() * 1000)
    for m in re.finditer(r'v_(\w+)="([^"]*)"', text):
        qc = m.group(1)
        symbol = _from_qq_code(qc)
        if not symbol or (want and symbol.upper() not in want):
            continue
        f = m.group(2).split("~")
        if len(f) < 11:
            continue
        try:
            name = f[1]
            last = _num(f[3])
            prev_close = _num(f[4])
            open_ = _num(f[5])
            vol = _num(f[6])
            amount = _num(f[7])
            high = _num(f[9])
            low = _num(f[10])
        except (IndexError, ValueError):
            continue
        if last is None or prev_close in (None, 0):
            continue
        change_amount = last - prev_close
        change_pct = change_amount / prev_close * 100
        amplitude = ((high - low) / prev_close * 100) if (high is not None and low is not None) else None
        is_index = _is_index(symbol)
        if is_index:
            # 指数 ÷100 转小数, 对齐下游 _build_index_quotes ×100 还原
            change_pct = change_pct / 100.0
            amplitude = amplitude / 100.0 if amplitude is not None else None
        out.append({
            "symbol": symbol,
            "name": name,
            "last_price": last,
            "prev_close": prev_close,
            "open": open_,
            "high": high,
            "low": low,
            "volume": vol * 100.0 if vol is not None else None,  # 手 → 股
            "amount": amount,
            "change_pct": change_pct,
            "change_amount": change_amount,
            "amplitude": amplitude,
            "turnover_rate": None,
            "timestamp": now_ms,
            "session": "TRADING",
        })
    return out


def _fetch_batch(qq_codes: list[str]) -> list[dict]:
    if not qq_codes:
        return []
    url = _URL + ",".join(qq_codes)
    return _parse_response(_http_get(url))


class QQProvider:
    name = "qq"
    capabilities = ProviderCapabilities(realtime=True)

    def get_instruments(self, asset_type: AssetType) -> pl.DataFrame:  # noqa: ARG002
        return pl.DataFrame()

    def get_daily(self, *a, **k) -> pl.DataFrame:  # noqa: ARG002
        return pl.DataFrame()

    def get_adj_factors(self, *a, **k) -> pl.DataFrame:  # noqa: ARG002
        return pl.DataFrame()

    def get_minute(self, *a, **k) -> pl.DataFrame:  # noqa: ARG002
        return pl.DataFrame()

    def get_realtime(
        self,
        universes: list[str] | None = None,
        symbols: list[str] | None = None,
    ) -> pl.DataFrame:
        """按标的批量+并发拉取。universes 模式由 QuoteService 预展开为 symbols 传入。"""
        syms = symbols or []
        if not syms:
            return pl.DataFrame()
        codes = [c for c in (_to_qq_code(s) for s in syms) if c]
        if not codes:
            return pl.DataFrame()
        batches = [codes[i:i + _BATCH] for i in range(0, len(codes), _BATCH)]
        records: list[dict] = []
        if len(batches) == 1:
            records.extend(_fetch_batch(batches[0]))
        else:
            with ThreadPoolExecutor(max_workers=min(10, len(batches))) as pool:
                for r in pool.map(_fetch_batch, batches):
                    records.extend(r)
        return pl.DataFrame(records)
