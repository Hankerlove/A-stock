from dataclasses import dataclass, field
from typing import Mapping, Protocol

import pandas as pd


MarketData = Mapping[str, pd.DataFrame]


@dataclass(frozen=True)
class StrategySignal:
    trade_date: str
    weights: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    scores: pd.DataFrame = field(default_factory=pd.DataFrame)


class Strategy(Protocol):
    name: str
    description: str

    def generate(self, market: MarketData, trade_date: str) -> StrategySignal:
        """Generate target weights from market data as of trade_date."""
        ...


def empty_signal(trade_date: str) -> StrategySignal:
    return StrategySignal(
        trade_date=trade_date,
        weights=pd.Series(dtype=float, name="weight"),
        scores=pd.DataFrame(),
    )

