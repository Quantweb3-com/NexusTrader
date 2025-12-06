"""KuCoin REST API error helpers."""

from __future__ import annotations

from typing import Any

import msgspec


class KucoinError(Exception):
    """Base class for KuCoin client errors."""

    def __init__(self, code: str | int, message: str, payload: dict[str, Any] | None = None):
        self.code = str(code)
        self.message = message
        self.payload = payload or {}
        super().__init__(f"[{self.code}] {self.message}")


class KucoinRequestError(KucoinError):
    """Raised when the KuCoin REST API returns an error response."""


_decoder = msgspec.json.Decoder(dict)


def parse_error(payload: bytes | None, status_code: int | None = None) -> KucoinRequestError:
    """Convert a raw HTTP response payload into a :class:`KucoinRequestError`."""

    if not payload:
        code = str(status_code or "unknown")
        return KucoinRequestError(code=code, message="Empty response payload")

    try:
        data = _decoder.decode(payload)
    except msgspec.DecodeError:
        text = payload.decode("utf-8", errors="ignore")
        code = str(status_code or "unknown")
        return KucoinRequestError(code=code, message=text or "Unable to decode KuCoin error")

    code = data.get("code", "unknown")
    message = data.get("msg") or data.get("message") or "Unknown KuCoin error"
    return KucoinRequestError(code=code, message=message, payload=data)


def retry_check(error: KucoinRequestError) -> bool:
    """Return True when an error is transient and should be retried."""

    code = getattr(error, "code", "")
    if not code:
        return False

    code_str = str(code)
    return code_str.startswith("429") or code_str.startswith("500") or code_str.startswith("503")


__all__ = ["KucoinError", "KucoinRequestError", "parse_error", "retry_check"]
