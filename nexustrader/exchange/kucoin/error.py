from __future__ import annotations

from typing import Any

class KucoinError(Exception):

    def __init__(self, code: str | int, message: str, payload: dict[str, Any] | None = None):
        self.code = str(code)
        self.message = message
        self.payload = payload or {}
        super().__init__(f"[{self.code}] {self.message}")
