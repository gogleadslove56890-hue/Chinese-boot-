from __future__ import annotations

from typing import Any


class ExecutionProvider:
    """Authorized execution boundary; no implementation means no trading."""

    name = "No authorized Olymp Trade execution integration"
    available = False

    async def execute(self, order: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError(
            "Auto execution disabled: authorized Olymp Trade trading access is required."
        )
