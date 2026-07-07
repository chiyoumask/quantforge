"""Provider registry."""
from __future__ import annotations

from app.data_providers.akshare_provider import AkshareProvider
from app.data_providers.eastmoney_provider import EastMoneyProvider
from app.data_providers.qq_provider import QQProvider
from app.data_providers.sina_provider import SinaProvider
from app.data_providers.tickflow_provider import TickFlowProvider

_PROVIDERS = {
    "akshare": AkshareProvider,
    "tickflow": TickFlowProvider,
    "eastmoney": EastMoneyProvider,
    "sina": SinaProvider,
    "qq": QQProvider,
}

# 按标的批量型 provider (不支持 universes 全市场快照, 需 QuoteService 展开为 symbols)
PER_SYMBOL_PROVIDERS = {"sina", "qq"}


def get_provider(name: str = "akshare"):
    provider_cls = _PROVIDERS.get((name or "akshare").lower())
    if provider_cls is None:
        raise ValueError(f"Unsupported data provider: {name}")
    return provider_cls()
