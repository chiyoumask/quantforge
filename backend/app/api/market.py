"""市场扩展数据 API — 资金流向 / 北向资金 / 龙虎榜 / 融资融券。

按需取数 (非定时同步), 数据来自东方财富 datacenter 公开接口 (免费)。
仿 indices.py 范式: Query 参数 + 返回 dict, 不写 Parquet。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Query, Request

from app.data_providers import eastmoney_datacenter as dc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/market", tags=["market"])


@router.get("/capital-flow/{symbol}")
def capital_flow(symbol: str, request: Request, days: int = Query(default=30, ge=1, le=180)) -> dict:
    """个股资金流向日 K (主力/超大单/大单/中单/小单净流入)。"""
    rows = dc.fetch_capital_flow(symbol, days)
    return {"symbol": symbol, "days": days, "rows": rows}


@router.get("/northbound")
def northbound(days: int = Query(default=30, ge=1, le=180)) -> dict:
    """北向资金日 K (沪股通/深股通/北向合计净买入)。"""
    rows = dc.fetch_northbound(days)
    return {"days": days, "rows": rows}


@router.get("/dragon-tiger")
def dragon_tiger(date: str | None = Query(default=None)) -> dict:
    """龙虎榜明细 (date 缺省取最近交易日)。"""
    rows = dc.fetch_dragon_tiger(date)
    return {"date": date, "rows": rows}


@router.get("/margin")
def margin(days: int = Query(default=30, ge=1, le=180)) -> dict:
    """两市融资融券余额日 K。"""
    rows = dc.fetch_margin(days)
    return {"days": days, "rows": rows}
