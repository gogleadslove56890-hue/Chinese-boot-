from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class RiskPolicy:
    amount: float = 1.0
    minimum_confidence: int = 70
    maximum_trades: int = 3
    cooldown_seconds: int = 300
    daily_loss_limit: float = 0.0
    maximum_amount: float = 100.0


class RiskManager:
    def __init__(self, policy: RiskPolicy | None = None) -> None:
        self.policy = policy or RiskPolicy()
        self.trades = 0
        self.loss = 0.0
        self.last_trade_at: datetime | None = None
        self.emergency_stopped = False

    def check_trade(self, confidence: int, amount: float, now: datetime | None = None) -> tuple[bool, str]:
        if self.emergency_stopped:
            return False, "Emergency stop is active."
        if amount <= 0 or amount > self.policy.maximum_amount:
            return False, "Trade amount exceeds the configured limit."
        if confidence < self.policy.minimum_confidence:
            return False, "Signal confidence is below the configured minimum."
        if self.trades >= self.policy.maximum_trades:
            return False, "Maximum trades per session reached."
        if self.loss >= self.policy.daily_loss_limit > 0:
            return False, "Daily loss limit reached."
        current = now or datetime.now(timezone.utc)
        if self.last_trade_at is not None:
            elapsed = (current - self.last_trade_at).total_seconds()
            if elapsed < self.policy.cooldown_seconds:
                return False, "Trade cooldown is active."
        return True, "Trade passed risk checks."

    def record_trade(self, now: datetime | None = None) -> None:
        self.trades += 1
        self.last_trade_at = now or datetime.now(timezone.utc)

    def record_loss(self, amount: float) -> None:
        self.loss += max(0.0, amount)

    def emergency_stop(self) -> None:
        self.emergency_stopped = True

    def reset_emergency_stop(self) -> None:
        self.emergency_stopped = False
