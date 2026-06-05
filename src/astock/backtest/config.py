from dataclasses import dataclass, field


@dataclass(frozen=True)
class ExecutionConfig:
    commission_rate: float = 0.0003
    stamp_duty_rate: float = 0.0005
    slippage_rate: float = 0.0005
    min_commission: float = 5.0
    lot_size: int = 100
    enforce_suspend: bool = True
    enforce_limit: bool = True
    limit_buffer_pct: float = 0.01

    def __post_init__(self) -> None:
        for name in ["commission_rate", "stamp_duty_rate", "slippage_rate", "min_commission"]:
            if getattr(self, name) < 0:
                raise ValueError(f"{name} 不能为负数")
        if self.lot_size < 1:
            raise ValueError("lot_size 必须大于等于 1")


@dataclass(frozen=True)
class BacktestConfig:
    start_date: str
    end_date: str
    initial_cash: float = 1_000_000.0
    rebalance_frequency: str = "monthly"
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)

    def __post_init__(self) -> None:
        if self.start_date > self.end_date:
            raise ValueError("start_date 不能晚于 end_date")
        if self.initial_cash <= 0:
            raise ValueError("initial_cash 必须大于 0")
        allowed = {"daily", "weekly", "monthly"}
        if self.rebalance_frequency not in allowed:
            raise ValueError(f"rebalance_frequency 必须是: {', '.join(sorted(allowed))}")

