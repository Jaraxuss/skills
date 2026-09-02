from __future__ import annotations

from typing import Any


class StructuredError(ValueError):
    """A stable machine-readable failure for agent-facing commands."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.retryable = retryable

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": False,
            "error_code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "details": self.details,
        }
