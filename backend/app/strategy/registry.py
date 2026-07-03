"""按用户懒加载的策略引擎注册表。

设计:
  - app.state.strategy_engine 指向本注册表 (鸭子类型委托), 所有现有调用点
    (list_strategies/get/has/run/run_all/reload/load_errors) 无需改动,
    自动委托到 current_username() 对应的 StrategyEngine 实例。
  - 每个用户一个引擎 = builtin(全局共享) + 该用户 custom/ai 目录。
  - 首次访问懒构建; 该用户增删策略后调 invalidate(username) 重建。
  - 后台/监控引擎等无请求上下文的场景用 for_user(owner) 显式取指定用户的引擎,
    以便 strategy 型监控规则在规则 owner 的策略集合内解析 strategy_id。

为什么不加载所有用户的策略到一个引擎:
  - 策略 id 可能跨用户重名 (两人各写一个 custom_x), 单引擎会冲突覆盖。
  - 每用户独立引擎天然隔离, 用户只看到 builtin + 自己的策略。
"""
from __future__ import annotations

import logging
import threading
from datetime import date
from pathlib import Path
from typing import Any, Callable

import polars as pl

from app.strategy.engine import StrategyEngine

logger = logging.getLogger(__name__)


class StrategyEngineRegistry:
    """策略引擎注册表 — 按用户懒加载, 鸭子类型委托到当前用户引擎。"""

    def __init__(
        self,
        enriched_loader: Callable[[date], pl.DataFrame],
        enriched_history_loader: Callable[[date, int], pl.DataFrame] | None = None,
        builtin_dir: Path | None = None,
    ) -> None:
        self._enriched_loader = enriched_loader
        self._enriched_history_loader = enriched_history_loader
        self._builtin_dir = builtin_dir or (
            Path(__file__).resolve().parent / "builtin"
        )
        self._engines: dict[str, StrategyEngine] = {}
        self._lock = threading.Lock()

    # ================================================================
    # 用户 → 引擎目录解析
    # ================================================================

    def _dirs_for(self, username: str) -> list[Path]:
        """某用户的策略搜索目录: builtin(共享) + 该用户 custom/ai。"""
        from app.services import user_context
        root = user_context.user_data_root(username)
        return [
            self._builtin_dir,
            root / "strategies" / "custom",
            root / "strategies" / "ai",
        ]

    def _current_user(self) -> str:
        from app.services import user_context
        return user_context.current_username() or "admin"

    def for_user(self, username: str | None = None) -> StrategyEngine:
        """取指定用户的引擎 (无则构建并缓存)。username 为 None 时取当前上下文用户。"""
        u = username or self._current_user()
        with self._lock:
            eng = self._engines.get(u)
            if eng is None:
                eng = StrategyEngine(
                    enriched_loader=self._enriched_loader,
                    enriched_history_loader=self._enriched_history_loader,
                    strategy_dirs=self._dirs_for(u),
                )
                self._engines[u] = eng
                logger.info("strategy engine built for user %s: %d strategies", u, len(eng.list_strategies()))
            return eng

    def invalidate(self, username: str | None = None) -> None:
        """丢弃某用户的缓存引擎 (增删策略后下次 get 重建)。username 为 None 时取当前用户。"""
        u = username or self._current_user()
        with self._lock:
            self._engines.pop(u, None)

    # ================================================================
    # 鸭子类型委托 — 让 app.state.strategy_engine 直接指向本注册表
    # ================================================================

    def _current(self) -> StrategyEngine:
        return self.for_user(self._current_user())

    def list_strategies(self) -> list[dict]:
        return self._current().list_strategies()

    def get(self, strategy_id: str):
        return self._current().get(strategy_id)

    def has(self, strategy_id: str) -> bool:
        return self._current().has(strategy_id)

    def run(self, strategy_id: str, *args: Any, **kwargs: Any):
        return self._current().run(strategy_id, *args, **kwargs)

    def run_all(self, as_of: date, *args: Any, **kwargs: Any):
        return self._current().run_all(as_of, *args, **kwargs)

    def reload(self) -> None:
        """重载当前用户的引擎 (保存/删除策略后调用)。"""
        self._current().reload()

    @property
    def load_errors(self) -> list[dict]:
        return self._current().load_errors
