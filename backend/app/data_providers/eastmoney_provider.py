"""东方财富 push2 实时行情 provider — 免费、无 Key、全市场快照。

设计:
  - 实现 MarketDataProvider Protocol 的 get_realtime, 输出与 TickFlow 等价的
    15 字段 records (symbol/name/last_price/prev_close/open/high/low/volume/amount/
    change_pct/change_amount/amplitude/turnover_rate/timestamp/session),
    使 QuoteService 的 _build_daily/_build_quote_extra/_build_index_quotes 零改动复用。
  - 全市场: clist 一次拉取全 A 股 (~5000 只), 替代 TickFlow get_by_universes。
  - 指数: clist 指数分类, 或按 secid 取核心指数。

单位对齐 (关键, 匹配 TickFlow 既有口径, 避免下游 _build_* 二次缩放出错):
  - 成交量 f5 单位为「手」, ×100 → 股 (与 TickFlow 日 K 口径一致)。
  - 涨跌幅/振幅: 股票 f3/f7 已是百分数 (与 TickFlow 股票 ext 一致, _build_daily 原样用);
    指数则 ÷100 转小数 (匹配 TickFlow 指数口径, 因 _build_index_quotes 会 ×100 还原)。
  - 停牌/盘前 EastMoney 返回 "-" 字符串, 统一转 None。
"""
from __future__ import annotations

import json
import logging
import time
import urllib.parse
import urllib.request
from datetime import datetime

import polars as pl

from app.data_providers.base import AssetType, ProviderCapabilities

logger = logging.getLogger(__name__)

_CLIST_URL = "http://push2.eastmoney.com/api/qt/clist/get"
# 全 A 股: 沪市主板(m:1+t:2) + 沪市科创板(m:1+t:23) + 深市主板(m:0+t:6) + 深市创业板(m:0+t:80)
_STOCK_FS = "m:1+t:2,m:1+t:23,m:0+t:6,m:0+t:80"
# 指数: 沪指(m:1+s:2) + 深指(m:0+s:2)
_INDEX_FS = "m:1+s:2,m:0+s:2"
# clist 字段: 代码/名称/最新/涨跌幅/涨跌额/量/额/振幅/换手/高/低/开/昨收
_CLIST_FIELDS = "f12,f14,f2,f3,f4,f5,f6,f7,f8,f15,f16,f17,f18"
# UA 防被识别为爬虫
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


def _to_symbol(code: str) -> str | None:
    """EastMoney 裸代码 → 带交易所后缀的 symbol (如 600519 → 600519.SH)。"""
    c = (code or "").strip()
    if not c or not c.isdigit() or len(c) != 6:
        return None
    # 沪市: 60/68/9 开头 (含科创板 68); 深市: 00/30/20; 北交所: 8/43/87/920
    if c.startswith(("60", "68", "9")):
        return f"{c}.SH"
    if c.startswith(("00", "30", "20")):
        return f"{c}.SZ"
    if c.startswith(("8", "43", "87", "920")):
        return f"{c}.BJ"
    return None


def _is_index_symbol(symbol: str) -> bool:
    """是否指数代码 (沪 000xxx / 深 399xxx)。"""
    s = symbol.strip().upper()
    code = s.split(".")[0] if "." in s else s
    if s.endswith(".SH") and code.startswith("000"):
        return True
    if s.endswith(".SZ") and code.startswith("399"):
        return True
    return False


def _num(v) -> float | None:
    """EastMoney 字段转 float; '-'/'None'/非数字 → None。"""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s or s in ("-", "——", "None", "null"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _http_get(url: str, timeout: float = 8.0) -> dict:
    """简单 GET + JSON 解析 (urllib, 零新依赖)。"""
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Referer": "https://quote.eastmoney.com/"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    try:
        return json.loads(body)
    except json.JSONDecode as e:
        logger.warning("eastmoney non-json response: %s", e)
        return {}


def _symbol_from_row(code: str, market, is_index: bool) -> str | None:
    """根据 f12(代码) + f13(市场: 1=SH, 0=SZ) 构造 symbol。

    f13 是 EastMoney 明确的市场标记, 比代码前缀更可靠 (尤其指数: 000001 属上证指数,
    若按股票前缀规则会被误判为 000001.SZ 平安银行)。
    """
    if not code or not code.isdigit() or len(code) != 6:
        return None
    if market == 1:
        return f"{code}.SH"
    if market == 0:
        return f"{code}.SZ"
    # f13 缺失时按代码前缀兜底
    if code.startswith(("60", "68", "9", "000", "880")):  # SH: 主板/科创板/B股/上证指数
        return f"{code}.SH"
    if code.startswith(("00", "30", "20", "399")):  # SZ: 主板/创业板/B股/深证指数
        return f"{code}.SZ"
    if code.startswith(("8", "43", "87", "920")):  # 北交所
        return f"{code}.BJ"
    return None


def _fetch_clist(fs: str, is_index: bool) -> list[dict]:
    """拉取 clist 分类全量, 返回 15 字段 record 列表。"""
    params = urllib.parse.urlencode({
        "pn": 1, "pz": 20000, "po": 1, "np": 1,
        "fltt": 2, "invt": 2, "fid": "f12",
        "fs": fs, "fields": _CLIST_FIELDS + ",f13",
    })
    url = f"{_CLIST_URL}?{params}"
    data = _http_get(url)
    rows = (data.get("data") or {}).get("diff") or []
    out: list[dict] = []
    now_ms = int(time.time() * 1000)
    for r in rows:
        code = str(r.get("f12") or "").strip()
        symbol = _symbol_from_row(code, r.get("f13"), is_index)
        if not symbol:
            continue
        name = r.get("f14") or ""
        change_pct = _num(r.get("f3"))
        amplitude = _num(r.get("f7"))
        if is_index:
            # 指数: ÷100 转小数, 匹配 TickFlow 指数口径 (下游 _build_index_quotes 会 ×100 还原)
            if change_pct is not None:
                change_pct = change_pct / 100.0
            if amplitude is not None:
                amplitude = amplitude / 100.0
        vol = _num(r.get("f5"))
        out.append({
            "symbol": symbol,
            "name": name,
            "last_price": _num(r.get("f2")),
            "prev_close": _num(r.get("f18")),
            "open": _num(r.get("f17")),
            "high": _num(r.get("f15")),
            "low": _num(r.get("f16")),
            "volume": vol * 100.0 if vol is not None else None,  # 手 → 股
            "amount": _num(r.get("f6")),
            "change_pct": change_pct,
            "change_amount": _num(r.get("f4")),
            "amplitude": amplitude,
            "turnover_rate": _num(r.get("f8")),
            "timestamp": now_ms,
            "session": "TRADING",
        })
    return out


class EastMoneyProvider:
    """东方财富 push2 实时行情 provider。"""

    name = "eastmoney"
    capabilities = ProviderCapabilities(
        instruments=False,
        daily=False,
        adj_factor=False,
        minute=False,
        realtime=True,
        financial=False,
    )

    def get_instruments(self, asset_type: AssetType) -> pl.DataFrame:  # noqa: ARG002
        return pl.DataFrame()

    def get_daily(self, *args, **kwargs) -> pl.DataFrame:  # noqa: ARG002
        return pl.DataFrame()

    def get_adj_factors(self, *args, **kwargs) -> pl.DataFrame:  # noqa: ARG002
        return pl.DataFrame()

    def get_minute(self, *args, **kwargs) -> pl.DataFrame:  # noqa: ARG002
        return pl.DataFrame()

    def get_realtime(
        self,
        universes: list[str] | None = None,
        symbols: list[str] | None = None,
    ) -> pl.DataFrame:
        """拉取实时行情, 返回 15 字段 records 的 DataFrame。

        - universes 含 CN_Equity_A → 全 A 股 clist; CN_Index → 指数 clist。
        - symbols → 按代码分类: 指数走指数 clist 过滤, 股票走股票 clist 过滤 (一次全量再 filter)。
        """
        records: list[dict] = []
        try:
            if universes:
                for u in universes:
                    if u == "CN_Equity_A":
                        records.extend(_fetch_clist(_STOCK_FS, is_index=False))
                    elif u == "CN_Index":
                        records.extend(_fetch_clist(_INDEX_FS, is_index=True))
                    elif u == "CN_ETF":
                        # ETF 暂用股票 clist 口径 (字段相同); 后续可独立分类
                        records.extend(_fetch_clist(_STOCK_FS, is_index=False))
            elif symbols:
                idx = [s for s in symbols if _is_index_symbol(s)]
                stk = [s for s in symbols if not _is_index_symbol(s)]
                if idx:
                    rows = _fetch_clist(_INDEX_FS, is_index=True)
                    want = set(s.upper() for s in idx)
                    records.extend(r for r in rows if r["symbol"].upper() in want)
                if stk:
                    rows = _fetch_clist(_STOCK_FS, is_index=False)
                    want = set(s.upper() for s in stk)
                    records.extend(r for r in rows if r["symbol"].upper() in want)
        except Exception as e:  # noqa: BLE001
            logger.warning("eastmoney get_realtime failed: %s", e)
            return pl.DataFrame()
        return pl.DataFrame(records)
