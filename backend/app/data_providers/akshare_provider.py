"""AkShare provider — 免费的 A 股历史/实时/财务数据源。

设计:
  - 实现 MarketDataProvider Protocol 的全部方法:instruments / daily /
    adj_factors / minute / realtime / financial。
  - 作为系统默认的「历史 + 盘后」数据源 (日K/分钟/标的/指数/ETF/财务),
    以及可选实时源(全市场快照, 走东方财富 EM 接口, 免费无 Key)。
  - tickflow 仅作为用户主动选择的「收盘后付费备用」保留, 默认不再使用。

单位/列口径对齐:
  - 日K/分钟K 输出与 TickFlow 历史口径一致 (OHLCV, 成交量单位 = 股)。
  - realtime 输出与 EastMoneyProvider 一致的 15 字段 records, 供 QuoteService
    的 _build_* 零改动复用。
  - 所有 akshare 调用均 try/except 包裹, 单标的失败只 warning 不中断整体。
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Literal

import polars as pl

from app.data_providers.base import AssetType, ProviderCapabilities
from app.data_providers.normalizer import (
    normalize_adj_factors,
    normalize_daily,
    normalize_instruments,
)

logger = logging.getLogger(__name__)

# 历史同步默认节流: 逐股循环, 控制请求频率, 避免被 EM/上游限流。
_DEFAULT_RPM = 80
_DEFAULT_BATCH = 50


def _to_symbol(code: str, asset_type: AssetType = "stock") -> str | None:
    """6 位代码 → 带交易所后缀的 symbol (600519 → 600519.SH)。

    指数/ETF 同样按代码前缀规则加后缀 (与现有 symbol 规范一致)。
    注意: 指数 000xxx(上证) 必须在通用 "00"→SZ 规则之前判定, 否则会被误判为深市。
    """
    c = (code or "").strip()
    if not c or not c.isdigit() or len(c) != 6:
        return None

    # 指数: 000xxx=上证, 399xxx=深证(必须在通用规则前判定)
    if asset_type == "index":
        if c.startswith("000"):
            return f"{c}.SH"
        if c.startswith("399"):
            return f"{c}.SZ"

    if c.startswith(("60", "68", "9")):
        return f"{c}.SH"
    if c.startswith(("00", "30", "20")):
        return f"{c}.SZ"
    if c.startswith(("8", "43", "87", "920")):
        return f"{c}.BJ"

    # ETF: 51/56/58=沪市ETF, 15/16=深市ETF; 其余按交易所前缀兜底
    if asset_type == "etf":
        if c.startswith(("51", "56", "58", "11")):
            return f"{c}.SH"
        if c.startswith(("15", "16", "12")):
            return f"{c}.SZ"

    return f"{c}.SH"


def _em_index_code(symbol: str) -> str:
    """symbol (000001.SH) → 东方财富指数代码 (000001, 不带后缀)。"""
    return symbol.split(".")[0]


def _em_stock_symbol(code: str) -> str:
    """6 位代码 → 东方财富分钟/实时接口用的裸代码 (600519)。"""
    return code.split(".")[0]


class AkshareProvider:
    """AkShare 免费数据源 provider。"""

    name = "akshare"
    capabilities = ProviderCapabilities(
        instruments=True,
        daily=True,
        adj_factor=True,
        minute=True,
        realtime=True,
        financial=True,
    )

    # ── 标的维表 ──────────────────────────────────────────────
    def get_instruments(self, asset_type: AssetType) -> pl.DataFrame:
        try:
            import akshare as ak
        except Exception as e:  # noqa: BLE001
            logger.warning("akshare import failed: %s", e)
            return pl.DataFrame()

        rows: list[dict] = []
        try:
            if asset_type == "index":
                df = ak.stock_zh_index_spot_em()
                for r in pl.from_pandas(df).to_dicts():
                    code = str(r.get("代码") or "").strip()
                    sym = _to_symbol(code, "index")
                    if sym:
                        rows.append({"symbol": sym, "name": r.get("名称"), "code": code})
            elif asset_type == "etf":
                df = ak.fund_etf_spot_em()
                for r in pl.from_pandas(df).to_dicts():
                    code = str(r.get("代码") or "").strip()
                    sym = _to_symbol(code, "etf")
                    if sym:
                        rows.append({"symbol": sym, "name": r.get("名称"), "code": code})
            else:  # stock
                df = ak.stock_info_a_code_name()
                # 返回列: 代码, 名称 (pandas DataFrame)
                for r in pl.from_pandas(df).to_dicts():
                    code = str(r.get("代码") or r.get("code") or "").strip()
                    sym = _to_symbol(code, "stock")
                    if sym:
                        name = r.get("名称") or r.get("name")
                        rows.append({"symbol": sym, "name": name, "code": code})
        except Exception as e:  # noqa: BLE001
            logger.warning("akshare get_instruments(%s) failed: %s", asset_type, e)
            return pl.DataFrame()

        if not rows:
            return pl.DataFrame()
        return normalize_instruments(rows, asset_type=asset_type, source=self.name)

    # ── 日 K ─────────────────────────────────────────────────
    def get_daily(
        self,
        symbols: list[str],
        start_time: datetime | None,
        end_time: datetime | None,
        asset_type: AssetType = "stock",
    ) -> pl.DataFrame:
        if not symbols:
            return pl.DataFrame()
        try:
            import akshare as ak
        except Exception as e:  # noqa: BLE001
            logger.warning("akshare import failed: %s", e)
            return pl.DataFrame()

        start = (start_time or datetime(1990, 1, 1)).strftime("%Y%m%d")
        end = (end_time or datetime.now()).strftime("%Y%m%d")
        interval = 60.0 / _DEFAULT_RPM

        frames: list[pl.DataFrame] = []
        for i, sym in enumerate(symbols):
            code = _em_stock_symbol(sym)
            try:
                if asset_type == "index":
                    raw = ak.stock_zh_index_daily_em(
                        symbol=_em_index_code(sym),
                        start_date=start,
                        end_date=end,
                    )
                else:
                    raw = ak.stock_zh_a_hist(
                        symbol=code,
                        period="daily",
                        start_date=start,
                        end_date=end,
                        adjust="",
                    )
                if raw is None or len(raw) == 0:
                    continue
                # akshare 返回 pandas; 转 polars 后做列映射
                df = pl.from_pandas(raw.reset_index() if hasattr(raw, "reset_index") else raw)
                # 只 rename 实际存在的列(polars rename 对缺失 key 会抛错):
                # 股票/指数日K 列名不同(中文/英文), 缺失 key 必须过滤掉。
                rename_map = {
                    "日期": "date",
                    "时间": "date",
                    "开盘": "open",
                    "收盘": "close",
                    "最高": "high",
                    "最低": "low",
                    "成交量": "volume",
                    "成交额": "amount",
                }
                rename_map = {k: v for k, v in rename_map.items() if k in df.columns}
                df = df.rename(rename_map)
                # akshare 成交量单位为「手」, ×100 转「股」与 TickFlow/eastmoney 口径一致
                if "volume" in df.columns:
                    df = df.with_columns(
                        (pl.col("volume").cast(pl.Float64, strict=False) * 100.0).alias("volume")
                    )
                if "date" in df.columns:
                    df = df.with_columns(pl.col("date").cast(pl.Date, strict=False))
                if "symbol" not in df.columns:
                    df = df.with_columns(pl.lit(sym).alias("symbol"))
                keep = [c for c in ["symbol", "date", "open", "high", "low", "close", "volume", "amount"] if c in df.columns]
                frames.append(df.select(keep))
            except Exception as e:  # noqa: BLE001
                logger.debug("akshare daily %s failed: %s", sym, e)
                continue
            if interval > 0 and i > 0 and i % _DEFAULT_BATCH == 0:
                time.sleep(interval)
        if not frames:
            return pl.DataFrame()
        return pl.concat(frames, how="diagonal_relaxed")

    # ── 复权因子 ─────────────────────────────────────────────
    def get_adj_factors(
        self,
        symbols: list[str],
        start_time: datetime | None,
        end_time: datetime | None,
        asset_type: AssetType = "stock",  # noqa: ARG002
    ) -> pl.DataFrame:
        """复权因子 (ex_factor)。

        akshare 的 stock_zh_a_daily(adjust="qfq"/"hfq") 直接返回「已复权价格」,
        并不单列因子列。因此这里取 未复权(adjust="") 与 前复权(adjust="qfq") 两版收盘价,
        因子 = 前复权收盘 / 未复权收盘 (即累积 qfq 因子)。hfq 同理可再加一次。
        单股 2~3 次请求, 已限速; 失败单股静默跳过。
        """
        if not symbols:
            return pl.DataFrame()
        try:
            import akshare as ak
        except Exception as e:  # noqa: BLE001
            logger.warning("akshare import failed: %s", e)
            return pl.DataFrame()

        start = (start_time or datetime(1990, 1, 1)).strftime("%Y%m%d")
        end = (end_time or datetime.now()).strftime("%Y%m%d")

        frames: list[pl.DataFrame] = []
        for i, sym in enumerate(symbols):
            code = _em_stock_symbol(sym)
            prefix = "sh" if sym.endswith(".SH") else "sz"
            try:
                raw = ak.stock_zh_a_daily(symbol=f"{prefix}{code}", start_date=start, end_date=end, adjust="")
                qfq = ak.stock_zh_a_daily(symbol=f"{prefix}{code}", start_date=start, end_date=end, adjust="qfq")
                if raw is None or qfq is None or len(raw) == 0 or len(qfq) == 0:
                    continue
                raw_df = pl.from_pandas(raw).select(["date", "close"]).rename({"close": "raw_close"})
                qfq_df = pl.from_pandas(qfq).select(["date", "close"]).rename({"close": "qfq_close"})
                merged = raw_df.join(qfq_df, on="date", how="inner")
                merged = merged.filter(pl.col("raw_close").is_not_null() & (pl.col("raw_close") != 0))
                if merged.is_empty():
                    continue
                out = merged.select(
                    pl.lit(sym).alias("symbol"),
                    pl.col("date").cast(pl.Date, strict=False).alias("trade_date"),
                    (pl.col("qfq_close") / pl.col("raw_close")).cast(pl.Float64).alias("ex_factor"),
                )
                frames.append(out)
            except Exception as e:  # noqa: BLE001
                logger.debug("akshare adj_factor %s failed: %s", sym, e)
                continue
            if i > 0 and i % _DEFAULT_BATCH == 0:
                time.sleep(60.0 / _DEFAULT_RPM)
        if not frames:
            return pl.DataFrame()
        df = pl.concat(frames, how="diagonal_relaxed")
        return normalize_adj_factors(df, source=self.name)

    # ── 分钟 K ───────────────────────────────────────────────
    def get_minute(
        self,
        symbols: list[str],
        start_time: datetime | None,
        end_time: datetime | None,
        asset_type: AssetType = "stock",  # noqa: ARG002
        freq: str = "1m",
    ) -> pl.DataFrame:
        if not symbols:
            return pl.DataFrame()
        try:
            import akshare as ak
        except Exception as e:  # noqa: BLE001
            logger.warning("akshare import failed: %s", e)
            return pl.DataFrame()

        period = "5" if freq and freq.startswith("5") else "1"
        start = (start_time or datetime(1990, 1, 1)).strftime("%Y-%m-%d %H:%M:%S")
        end = (end_time or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")

        frames: list[pl.DataFrame] = []
        for i, sym in enumerate(symbols):
            code = _em_stock_symbol(sym)
            try:
                raw = ak.stock_zh_a_hist_min_em(
                    symbol=code,
                    period=period,
                    start_date=start,
                    end_date=end,
                    adjust="",
                )
                if raw is None or len(raw) == 0:
                    continue
                df = pl.from_pandas(raw.reset_index() if hasattr(raw, "reset_index") else raw)
                rename_map = {
                    "时间": "datetime",
                    "开盘": "open",
                    "收盘": "close",
                    "最高": "high",
                    "最低": "low",
                    "成交量": "volume",
                    "成交额": "amount",
                }
                rename_map = {k: v for k, v in rename_map.items() if k in df.columns}
                df = df.rename(rename_map)
                # akshare 成交量单位为「手」, ×100 转「股」与 TickFlow/eastmoney 口径一致
                if "volume" in df.columns:
                    df = df.with_columns(
                        (pl.col("volume").cast(pl.Float64, strict=False) * 100.0).alias("volume")
                    )
                if "datetime" in df.columns:
                    df = df.with_columns(pl.col("datetime").cast(pl.Datetime("us"), strict=False))
                if "symbol" not in df.columns:
                    df = df.with_columns(pl.lit(sym).alias("symbol"))
                keep = [c for c in ["symbol", "datetime", "open", "high", "low", "close", "volume", "amount"] if c in df.columns]
                frames.append(df.select(keep))
            except Exception as e:  # noqa: BLE001
                logger.debug("akshare minute %s failed: %s", sym, e)
                continue
            if i > 0 and i % _DEFAULT_BATCH == 0:
                time.sleep(60.0 / _DEFAULT_RPM)
        if not frames:
            return pl.DataFrame()
        return pl.concat(frames, how="diagonal_relaxed")

    # ── 实时快照 ─────────────────────────────────────────────
    def get_realtime(
        self,
        universes: list[str] | None = None,
        symbols: list[str] | None = None,
    ) -> pl.DataFrame:
        try:
            import akshare as ak
        except Exception as e:  # noqa: BLE001
            logger.warning("akshare import failed: %s", e)
            return pl.DataFrame()

        records: list[dict] = []
        try:
            if universes:
                for u in universes:
                    if u == "CN_Equity_A":
                        df = ak.stock_zh_a_spot_em()
                        records.extend(self._spot_to_records(df, is_index=False))
                    elif u == "CN_Index":
                        df = ak.stock_zh_index_spot_em()
                        records.extend(self._spot_to_records(df, is_index=True))
                    elif u == "CN_ETF":
                        df = ak.fund_etf_spot_em()
                        records.extend(self._spot_to_records(df, is_index=False))
            elif symbols:
                idx = [s for s in symbols if s.startswith(("000", "399")) and s.endswith((".SH", ".SZ"))]
                stk = [s for s in symbols if s not in idx]
                if idx:
                    df = ak.stock_zh_index_spot_em()
                    want = {s.upper() for s in idx}
                    records.extend(r for r in self._spot_to_records(df, is_index=True) if r["symbol"].upper() in want)
                if stk:
                    df = ak.stock_zh_a_spot_em()
                    want = {s.upper() for s in stk}
                    records.extend(r for r in self._spot_to_records(df, is_index=False) if r["symbol"].upper() in want)
        except Exception as e:  # noqa: BLE001
            logger.warning("akshare get_realtime failed: %s", e)
            return pl.DataFrame()
        return pl.DataFrame(records)

    @staticmethod
    def _spot_to_records(df, is_index: bool) -> list[dict]:
        """东方财富 spot DataFrame → 15 字段 records (口径同 EastMoneyProvider)。"""
        out: list[dict] = []
        now_ms = int(time.time() * 1000)
        # akshare 返回 pandas, 先转 polars 再 to_dicts
        for r in pl.from_pandas(df).to_dicts():
            code = str(r.get("代码") or r.get("code") or "").strip()
            sym = _to_symbol(code, "index" if is_index else "stock")
            if not sym:
                continue
            name = r.get("名称") or r.get("name") or ""
            change_pct = _num(r.get("涨跌幅"))
            amplitude = _num(r.get("振幅"))
            if is_index and change_pct is not None:
                change_pct = change_pct / 100.0
            if is_index and amplitude is not None:
                amplitude = amplitude / 100.0
            vol = _num(r.get("成交量"))
            out.append({
                "symbol": sym,
                "name": name,
                "last_price": _num(r.get("最新价")),
                "prev_close": _num(r.get("昨收")),
                "open": _num(r.get("今开")),
                "high": _num(r.get("最高")),
                "low": _num(r.get("最低")),
                "volume": vol * 100.0 if vol is not None else None,
                "amount": _num(r.get("成交额")),
                "change_pct": change_pct,
                "change_amount": _num(r.get("涨跌额")),
                "amplitude": amplitude,
                "turnover_rate": _num(r.get("换手率")),
                "timestamp": now_ms,
                "session": "TRADING",
            })
        return out

    # ── 财务(4 表) ───────────────────────────────────────────
    def get_financial(
        self,
        statement: str,
        symbols: list[str],
        start_year: str | None = None,
        end_year: str | None = None,
    ) -> dict[str, list[dict]]:
        """拉取财务表, 返回 {symbol: [record, ...]}。

        statement ∈ {metrics, income, balance_sheet, cash_flow}。
        akshare 财务接口用 "SH600519"/"SZ000001" 前缀代码。
        """
        try:
            import akshare as ak
        except Exception as e:  # noqa: BLE001
            logger.warning("akshare import failed: %s", e)
            return {}

        sy = start_year or "2021"
        ey = end_year or str(datetime.now().year)

        def _em_symbol(sym: str) -> str:
            code = _em_stock_symbol(sym)
            return f"SH{code}" if sym.endswith(".SH") else f"SZ{code}"

        result: dict[str, list[dict]] = {}
        for sym in symbols:
            try:
                if statement == "metrics":
                    # 指标类 (ROE/毛利率等), 单代码无年份区间
                    raw = ak.stock_financial_analysis_indicator(symbol=_em_stock_symbol(sym))
                elif statement == "income":
                    raw = ak.stock_profit_sheet_by_report_em(symbol=_em_symbol(sym), start_year=sy, end_year=ey)
                elif statement == "balance_sheet":
                    raw = ak.stock_balance_sheet_by_report_em(symbol=_em_symbol(sym), start_year=sy, end_year=ey)
                elif statement == "cash_flow":
                    raw = ak.stock_cash_flow_sheet_by_report_em(symbol=_em_symbol(sym), start_year=sy, end_year=ey)
                else:
                    continue
                if raw is None or len(raw) == 0:
                    continue
                df = pl.from_pandas(raw.reset_index() if hasattr(raw, "reset_index") else raw)
                # 把列名统一为英文 lower snake 便于下游读取
                df = df.rename({c: _slug(c) for c in df.columns})
                recs = df.with_columns(pl.lit(sym).alias("symbol")).to_dicts()
                result[sym] = recs
            except Exception as e:  # noqa: BLE001
                logger.warning("akshare financial %s %s failed: %s", statement, sym, e)
                continue
        return result


def _num(v) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "")
    if not s or s in ("-", "——", "None", "null"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _slug(col: str) -> str:
    """中文列名 → 英文 slug (折中: 保留可读, 下游 financials 页按关键字取数)。"""
    import re
    s = re.sub(r"[^\w]", "_", str(col))
    return s.strip("_").lower()
