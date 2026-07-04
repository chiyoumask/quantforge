"""新浪财经实时行情 provider — 免费、按标的批量、备份源。

特点:
  - 按标的查询 (hq.sinajs.cn/list=sh600519,sz000001,...), 每批最多 ~50 只。
  - 全市场需多请求 (5000 只 / 50 = 100 批), 用线程池并发, 较慢 —— 定位为东方财富
    不可达时的备份源, 非主源。
  - 需 Referer: https://finance.sina.com.cn (否则 403)。
  - 输出与东方财富/TickFlow 一致的 15 字段 records, 下游 _build_* 零改动。

单位:
  - 成交量: 新浪返回「股」, 与 TickFlow 日 K 口径一致 (不换算)。
  - 涨跌幅/振幅: 自行计算 (百分数)。股票/指数口径一致 (都是百分数), 但下游
    _build_index_quotes 对指数会 ×100 —— 故指数 change_pct/amplitude 需 ÷100 转小数
    (与东方财富 provider 对齐)。
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

_URL = "http://hq.sinajs.cn/list="
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
_REFERER = "https://finance.sina.com.cn"
_BATCH = 50  # 每批标的数


def _to_sina_code(symbol: str) -> str | None:
    """600519.SH → sh600519; 000001.SZ → sz000001; 指数 000001.SH → s_sh000001。"""
    s = symbol.strip().upper()
    if "." not in s:
        return None
    code, exch = s.split(".", 1)
    if exch == "SH":
        # 指数 (000xxx) 用 s_ 前缀的简版
        if code.startswith("000"):
            return f"s_sh{code}"
        return f"sh{code}"
    if exch == "SZ":
        if code.startswith("399"):
            return f"s_sz{code}"
        return f"sz{code}"
    return None


def _from_sina_code(sc: str) -> str | None:
    """sh600519 → 600519.SH; s_sh000001 → 000001.SH。"""
    is_idx = sc.startswith("s_")
    body = sc[2:] if is_idx else sc  # 去 s_
    if body.startswith("sh"):
        return f"{body[2:]}.SH"
    if body.startswith("sz"):
        return f"{body[2:]}.SZ"
    return None


def _num(v) -> float | None:
    if v is None:
        return None
    try:
        f = float(str(v).strip())
        return f if f != 0 or True else None
    except (ValueError, TypeError):
        return None


def _http_get(url: str, timeout: float = 6.0) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Referer": _REFERER})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("gbk", errors="replace")
    except Exception as e:  # noqa: BLE001
        logger.debug("sina http failed %s: %s", url[:60], e)
        return ""


def _parse_response(text: str, want: set[str] | None = None) -> list[dict]:
    """解析 hq_str_xxx="..."; 行 → 15 字段 records。"""
    out: list[dict] = []
    now_ms = int(time.time() * 1000)
    for m in re.finditer(r'var\s+hq_str_(\w+)="([^"]*)"', text):
        sc = m.group(1)
        symbol = _from_sina_code(sc)
        if not symbol or (want and symbol.upper() not in want):
            continue
        fields = m.group(2).split(",")
        if len(fields) < 10:
            continue
        is_index = sc.startswith("s_")
        try:
            name = fields[0]
            open_ = _num(fields[1])
            prev_close = _num(fields[2])
            last = _num(fields[3])
            high = _num(fields[4])
            low = _num(fields[5])
            if is_index:
                vol = _num(fields[6])   # 指数: [6]=volume
                amount = _num(fields[7])  # [7]=amount
            else:
                vol = _num(fields[8])   # 股票: [8]=volume(股)
                amount = _num(fields[9])  # [9]=amount(元)
        except (IndexError, ValueError):
            continue
        if last is None or prev_close in (None, 0):
            continue
        change_amount = last - prev_close
        change_pct = change_amount / prev_close * 100
        amplitude = ((high - low) / prev_close * 100) if (high is not None and low is not None and prev_close) else None
        if is_index:
            # 指数 ÷100 转小数, 对齐下游 _build_index_quotes ×100 还原
            change_pct = change_pct / 100.0 if change_pct is not None else None
            amplitude = amplitude / 100.0 if amplitude is not None else None
        out.append({
            "symbol": symbol,
            "name": name,
            "last_price": last,
            "prev_close": prev_close,
            "open": open_,
            "high": high,
            "low": low,
            "volume": vol,
            "amount": amount,
            "change_pct": change_pct,
            "change_amount": change_amount,
            "amplitude": amplitude,
            "turnover_rate": None,
            "timestamp": now_ms,
            "session": "TRADING",
        })
    return out


def _fetch_batch(sina_codes: list[str]) -> list[dict]:
    """一批 sina 代码 → records。"""
    if not sina_codes:
        return []
    url = _URL + ",".join(sina_codes)
    text = _http_get(url)
    return _parse_response(text)


class SinaProvider:
    name = "sina"
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
        codes: list[str] = []
        for s in syms:
            c = _to_sina_code(s)
            if c:
                codes.append(c)
        if not codes:
            return pl.DataFrame()
        # 分批并发
        batches = [codes[i:i + _BATCH] for i in range(0, len(codes), _BATCH)]
        records: list[dict] = []
        if len(batches) == 1:
            records.extend(_fetch_batch(batches[0]))
        else:
            with ThreadPoolExecutor(max_workers=min(10, len(batches))) as pool:
                for r in pool.map(_fetch_batch, batches):
                    records.extend(r)
        return pl.DataFrame(records)
