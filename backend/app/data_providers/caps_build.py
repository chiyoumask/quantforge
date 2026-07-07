"""把全局 tickflow 档位门控转换为「当前数据源」门控。

默认历史/盘后数据源是 akshare (免费), 视为全能力;tickflow 作为可选付费备用时
仍按真实档位门控。这样同步服务无需大改签名, 只把 `capset.has(Cap.X)` 换成
`active_capabilities(capset).has(Cap.X)` 即可让免费源全开、tickflow 仍受档位约束。
"""
from __future__ import annotations

from app.tickflow.capabilities import Cap, CapabilityLimits, CapabilitySet

# 免费源集合: 这些源不需要任何付费 Key, 视为全能力。
FREE_PROVIDERS = {"akshare", "eastmoney", "sina", "qq"}


def active_capabilities(capset: CapabilitySet | None) -> CapabilitySet:
    """返回适用于「当前数据源」的能力集。

    - 当前日K数据源为免费源 (akshare/eastmoney/sina/qq) → 全能力 (无限流)。
    - 当前为 tickflow → 沿用真实探测到的 capset (按档位门控)。
    """
    from app.services import preferences

    if preferences.get_daily_data_provider() != "tickflow":
        return CapabilitySet({c: CapabilityLimits() for c in Cap})
    return capset or CapabilitySet()
