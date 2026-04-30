import base64
import hashlib
import hmac
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable

import aiohttp


class TraderId(str):
    pass


class UUID4:
    def __init__(self, value: str | uuid.UUID | None = None):
        self._uuid = uuid.UUID(str(value)) if value is not None else uuid.uuid4()

    @property
    def value(self) -> str:
        return str(self._uuid)

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return f"UUID4('{self.value}')"

    def __hash__(self) -> int:
        return hash(self._uuid)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, UUID4):
            return self._uuid == other._uuid
        if isinstance(other, uuid.UUID):
            return self._uuid == other
        if isinstance(other, str):
            return self.value == other
        return False


class LiveClock:
    def timestamp_ns(self) -> int:
        return time.time_ns()

    def timestamp_us(self) -> int:
        return time.time_ns() // 1_000

    def timestamp_ms(self) -> int:
        return time.time_ns() // 1_000_000

    def timestamp(self) -> float:
        return time.time()

    def utc_now(self) -> datetime:
        return datetime.now(timezone.utc)


@dataclass(frozen=True)
class TimeEvent:
    name: str
    event_id: UUID4
    ts_event: int
    ts_init: int


class MessageBus:
    def __init__(self, trader_id: TraderId | str, clock: LiveClock):
        self.trader_id = TraderId(str(trader_id))
        self.clock = clock
        self._topic_handlers: dict[str, list[Callable[[Any], Any]]] = {}
        self._endpoint_handlers: dict[str, list[Callable[[Any], Any]]] = {}

    def subscribe(
        self,
        topic: str | None = None,
        handler: Callable[[Any], Any] | None = None,
        endpoint: str | None = None,
        **_: Any,
    ) -> None:
        key = topic or endpoint
        if key is None or handler is None:
            raise ValueError("Both topic/endpoint and handler are required")
        handlers = (
            self._endpoint_handlers.setdefault(key, [])
            if endpoint and not topic
            else self._topic_handlers.setdefault(key, [])
        )
        handlers.append(handler)

    def register(self, endpoint: str, handler: Callable[[Any], Any], **_: Any) -> None:
        self._endpoint_handlers.setdefault(endpoint, []).append(handler)

    def deregister(
        self, endpoint: str, handler: Callable[[Any], Any] | None = None, **_: Any
    ) -> None:
        if endpoint not in self._endpoint_handlers:
            return
        if handler is None:
            self._endpoint_handlers.pop(endpoint, None)
            return
        self._endpoint_handlers[endpoint] = [
            item for item in self._endpoint_handlers[endpoint] if item != handler
        ]

    def publish(self, topic: str, msg: Any, **_: Any) -> None:
        for handler in list(self._topic_handlers.get(topic, [])):
            handler(msg)

    def send(self, endpoint: str, msg: Any, **_: Any) -> None:
        for handler in list(self._endpoint_handlers.get(endpoint, [])):
            handler(msg)
        for handler in list(self._topic_handlers.get(endpoint, [])):
            handler(msg)


class HttpMethod(str, Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: bytes
    headers: dict[str, str]


class HttpClient:
    async def request(
        self,
        method: HttpMethod | str,
        url: str,
        headers: dict[str, str] | None = None,
        body: bytes | str | None = None,
        **_: Any,
    ) -> HttpResponse:
        async with aiohttp.ClientSession() as session:
            async with session.request(
                method=str(method.value if isinstance(method, HttpMethod) else method),
                url=url,
                headers=headers,
                data=body,
            ) as response:
                return HttpResponse(
                    status=response.status,
                    body=await response.read(),
                    headers=dict(response.headers),
                )


class WebSocketClientError(RuntimeError):
    pass


@dataclass(frozen=True)
class WebSocketConfig:
    url: str
    handler: Callable[[bytes], Any]
    heartbeat: float | None = None
    headers: list[tuple[str, str]] | dict[str, str] | None = None
    ping_handler: Callable[[bytes], Any] | None = None


class WebSocketClient:
    @classmethod
    async def connect(cls, *_: Any, **__: Any):
        raise WebSocketClientError(
            "WebSocketClient compatibility shim is not implemented; use WSClient."
        )


def hmac_signature(secret: str, query: str) -> str:
    return hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()


def rsa_signature(private_key: str, payload: str) -> str:
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
    except ImportError as exc:
        raise RuntimeError("cryptography is required for rsa_signature") from exc

    key = serialization.load_pem_private_key(private_key.encode(), password=None)
    signature = key.sign(payload.encode(), padding.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(signature).decode()


def ed25519_signature(private_key: str, payload: str) -> str:
    try:
        from cryptography.hazmat.primitives import serialization
    except ImportError as exc:
        raise RuntimeError("cryptography is required for ed25519_signature") from exc

    key = serialization.load_pem_private_key(private_key.encode(), password=None)
    signature = key.sign(payload.encode())
    return base64.b64encode(signature).decode()
