from collections.abc import Callable
from typing import Any

from astock.strategy.base import Strategy


StrategyFactory = Callable[..., Strategy]

_REGISTRY: dict[str, StrategyFactory] = {}


def register_strategy(name: str, factory: StrategyFactory) -> None:
    if name in _REGISTRY:
        raise ValueError(f"策略已注册: {name}")
    _REGISTRY[name] = factory


def list_strategies() -> list[str]:
    return sorted(_REGISTRY)


def get_strategy(name: str, **params: Any) -> Strategy:
    try:
        factory = _REGISTRY[name]
    except KeyError as exc:
        available = ", ".join(list_strategies()) or "无"
        raise ValueError(f"未知策略: {name}; 可用策略: {available}") from exc
    return factory(**params)

