"""
Pure Python implementations to replace nautilus-trader dependencies.

Provides:
  - MessageBus: simple pub/sub + endpoint routing
  - LiveClock: wall-clock time + asyncio-based timers
  - TimeEvent: timer event dataclass
  - TraderId: string subclass identifier
  - UUID4: uuid4 wrapper
  - hmac_signature / rsa_signature / ed25519_signature: crypto helpers
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac as _hmac
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable


# ---------------------------------------------------------------------------
# Identifiers
# ---------------------------------------------------------------------------


class TraderId(str):
    """Simple string subclass used as a trader identifier."""


class UUID4:
    """UUID4 wrapper that exposes a `.value` string attribute."""

    __slots__ = ("value",)

    def __init__(self):
        self.value: str = str(uuid.uuid4())

    def __repr__(self) -> str:
        return f"UUID4('{self.value}')"

    def __hash__(self):
        return hash(self.value)

    def __eq__(self, other):
        if isinstance(other, UUID4):
            return self.value == other.value
        return NotImplemented


# ---------------------------------------------------------------------------
# TimeEvent
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class TimeEvent:
    """Emitted by LiveClock when a named timer fires.

    Attributes
    ----------
    name : str
        Timer name.
    ts_event : int
        Scheduled fire time in nanoseconds (UTC epoch).
    ts_init : int
        Actual call time in nanoseconds (UTC epoch).
    """

    name: str
    ts_event: int
    ts_init: int


# ---------------------------------------------------------------------------
# LiveClock
# ---------------------------------------------------------------------------


def _now_ns() -> int:
    return time.time_ns()


def _now_ms() -> int:
    return int(time.time() * 1_000)


class LiveClock:
    """Wall-clock that also manages asyncio-based repeating timers."""

    def __init__(self):
        self._timers: dict[str, asyncio.Task] = {}
        self._next_time_ns: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Time accessors
    # ------------------------------------------------------------------

    def timestamp(self) -> float:
        """Current UNIX time in seconds (float)."""
        return time.time()

    def timestamp_ms(self) -> int:
        """Current UNIX time in milliseconds (int)."""
        return _now_ms()

    def timestamp_ns(self) -> int:
        """Current UNIX time in nanoseconds (int)."""
        return _now_ns()

    def utc_now(self) -> datetime:
        """Current UTC datetime."""
        return datetime.now(tz=timezone.utc)

    # ------------------------------------------------------------------
    # Timer management
    # ------------------------------------------------------------------

    def set_timer(
        self,
        name: str,
        interval: timedelta,
        start_time: datetime,
        stop_time: datetime | None,
        callback: Callable[[TimeEvent], None],
    ) -> None:
        """Register a repeating timer.

        The timer first fires at *start_time*, then every *interval* after
        that.  The synchronous *callback* is called with a :class:`TimeEvent`
        on each fire.

        Parameters
        ----------
        name:
            Unique timer name (used to cancel later).
        interval:
            Repeat interval.
        start_time:
            UTC datetime of first fire.
        stop_time:
            Optional UTC datetime after which the timer stops (inclusive
            boundary: the last fire is the last one *before* stop_time).
        callback:
            Synchronous callable receiving a single :class:`TimeEvent`.
        """
        # Cancel existing timer with the same name, if any.
        self.cancel_timer(name)

        interval_ns = int(interval.total_seconds() * 1_000_000_000)

        async def _run():
            # Calculate initial delay
            now_utc = datetime.now(tz=timezone.utc)
            delay = (start_time - now_utc).total_seconds()
            if delay > 0:
                await asyncio.sleep(delay)

            # Compute first ts_event in nanoseconds
            ts_event = int(start_time.timestamp() * 1_000_000_000)

            while True:
                # Update next expected time
                self._next_time_ns[name] = ts_event

                ts_init = _now_ns()
                event = TimeEvent(name=name, ts_event=ts_event, ts_init=ts_init)
                try:
                    callback(event)
                except Exception:
                    import traceback

                    traceback.print_exc()

                ts_event += interval_ns

                # Check stop_time
                if stop_time is not None:
                    stop_ns = int(stop_time.timestamp() * 1_000_000_000)
                    if ts_event > stop_ns:
                        break

                # Sleep until next fire
                sleep_ns = ts_event - _now_ns()
                if sleep_ns > 0:
                    await asyncio.sleep(sleep_ns / 1_000_000_000)

            # Clean up
            self._next_time_ns.pop(name, None)
            self._timers.pop(name, None)

        loop = asyncio.get_event_loop()
        task = loop.create_task(_run(), name=f"timer_{name}")
        self._timers[name] = task

    def cancel_timer(self, name: str) -> None:
        """Cancel a named timer if it exists."""
        task = self._timers.pop(name, None)
        if task is not None and not task.done():
            task.cancel()
        self._next_time_ns.pop(name, None)

    def next_time_ns(self, name: str) -> int:
        """Return the next scheduled fire time (nanoseconds) for *name*."""
        return self._next_time_ns.get(name, 0)


# ---------------------------------------------------------------------------
# MessageBus
# ---------------------------------------------------------------------------


class MessageBus:
    """Minimal in-process pub/sub + endpoint routing bus.

    Two communication patterns are supported:

    * **Topic (fan-out)**: ``subscribe`` / ``publish`` – one-to-many.
    * **Endpoint (point-to-point)**: ``register`` / ``send`` – one-to-one.
    """

    def __init__(self, trader_id: TraderId, clock: LiveClock):
        self._trader_id = trader_id
        self._clock = clock
        self._subscriptions: dict[str, list[Callable]] = {}
        self._endpoints: dict[str, Callable] = {}

    # ------------------------------------------------------------------
    # Pub / sub
    # ------------------------------------------------------------------

    def subscribe(self, topic: str, handler: Callable[[Any], None]) -> None:
        """Subscribe *handler* to *topic*."""
        self._subscriptions.setdefault(topic, [])
        if handler not in self._subscriptions[topic]:
            self._subscriptions[topic].append(handler)

    def unsubscribe(self, topic: str, handler: Callable[[Any], None]) -> None:
        """Remove *handler* from *topic*."""
        handlers = self._subscriptions.get(topic)
        if handlers and handler in handlers:
            handlers.remove(handler)

    def publish(self, topic: str, msg: Any) -> None:
        """Publish *msg* to all handlers subscribed to *topic*."""
        for handler in list(self._subscriptions.get(topic, [])):
            handler(msg)

    # ------------------------------------------------------------------
    # Endpoint (point-to-point)
    # ------------------------------------------------------------------

    def register(self, endpoint: str, handler: Callable[[Any], None]) -> None:
        """Register *handler* for point-to-point *endpoint*."""
        self._endpoints[endpoint] = handler

    def send(self, endpoint: str, msg: Any) -> None:
        """Send *msg* to the handler registered for *endpoint*."""
        handler = self._endpoints.get(endpoint)
        if handler is not None:
            handler(msg)


# ---------------------------------------------------------------------------
# Cryptographic helpers
# ---------------------------------------------------------------------------


def hmac_signature(key: str, msg: str) -> str:
    """Return HMAC-SHA256 hex digest of *msg* signed with *key*."""
    return _hmac.new(
        key.encode("utf-8"),
        msg.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def rsa_signature(key: str, msg: str) -> str:
    """Return base-64–encoded PKCS#1 v1.5 RSA-SHA256 signature.

    *key* should be a PEM-encoded RSA private key string.
    """
    from Crypto.Hash import SHA256
    from Crypto.PublicKey import RSA
    from Crypto.Signature import pkcs1_15
    import base64

    rsa_key = RSA.import_key(key)
    h = SHA256.new(msg.encode("utf-8"))
    sig = pkcs1_15.new(rsa_key).sign(h)
    return base64.b64encode(sig).decode("ascii")


def ed25519_signature(key: str, msg: str) -> str:
    """Return base-64–encoded Ed25519 signature.

    *key* should be a base-64–encoded 32-byte Ed25519 private key seed.
    """
    import base64

    from Crypto.PublicKey import OKP
    from Crypto.Signature import eddsa

    private_key_bytes = base64.b64decode(key)
    key_obj = OKP.import_key(seed=private_key_bytes, curve_name="Ed25519")
    signer = eddsa.new(key_obj, "rfc8032")
    sig = signer.sign(msg.encode("utf-8"))
    return base64.b64encode(sig).decode("ascii")
