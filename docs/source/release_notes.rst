Release Notes
=============

0.3.4
-----

**Changed**

- **Simplified Cache API**: ``cache.get_position()`` and ``cache.get_order()`` now return ``Optional[T]`` directly instead of a ``Maybe`` monad. Replace ``.value_or(None)`` with a direct ``None`` check, and ``.bind_optional(lambda o: o.field).value_or(False)`` with ``o.field if o else False``.
- **ZeroMQ is now an optional dependency**: The ``zmq`` package is no longer installed by default. Users who rely on ``ZeroMQSignalConfig`` must install the extras: ``pip install nexustrader[signal]``.
- **Windows: signal handler warning suppressed**: The unsupported ``asyncio`` signal handler on Windows no longer emits a ``UserWarning``; it is now silently logged at DEBUG level.

**Removed**

- **``returns`` library removed**: Replaced with standard ``Optional[T]`` return types — no external dependency needed.
- **Dead production dependencies removed**: ``streamz``, ``pathlib`` (Python stdlib), ``bcrypt``, ``cython``, and ``certifi`` had zero usage and have been removed, reducing the install footprint.
- **``pyinstrument`` moved to dev-only**: The profiling tool is no longer pulled in for regular users.

0.3.3
-----

**New Features & Improvements**

- **Batched WebSocket subscriptions**: Both initial subscriptions and reconnection resubscriptions now process symbols in batches of 50 with a short delay between batches, enabling reliable support for thousands of symbols without overloading the connection.
- **Binance Spot: migrated to signature-based user data stream**: Replaced the deprecated ``listenKey`` mechanism with the new ``userDataStream.subscribe.signature`` WebSocket API for Binance Spot accounts (effective since 2026-02-20). Futures, Margin, and Portfolio Margin accounts continue to use the existing ``listenKey`` flow.
- **OKX: ``instIdCode`` support for WebSocket order operations**: Adapted to OKX's upcoming parameter migration from ``instId`` to ``instIdCode`` in WebSocket order and cancel-order requests (Phase 1: 2026-03-26, Phase 2: 2026-03-31). The system uses ``instIdCode`` when available and falls back to ``instId`` for backward compatibility.
- **Inflight order tracking**: Orders that have been submitted to the exchange but not yet acknowledged are now tracked per symbol via ``cache.get_inflight_orders()`` and ``cache.wait_for_inflight_orders()``. This prevents race conditions when rapidly submitting and cancelling orders.
- **Synchronous cancel-intent marking**: ``cancel_order``, ``cancel_order_ws``, and ``cancel_all_orders`` now mark cancel intent synchronously at the Strategy layer, eliminating a window where the local order state could conflict with incoming exchange updates.
- **Order ``reason`` field**: The ``Order`` struct now carries an optional ``reason`` field to capture human-readable failure context (e.g. exchange error messages) for ``FAILED`` and ``CANCEL_FAILED`` orders.
- **OMS null-OID guard**: ``order_status_update`` gracefully skips orders with ``oid=None`` (e.g. exchange-initiated liquidations), preventing ``KeyError`` crashes.
- **RetryManager utility**: A generic retry helper with exponential backoff and jitter is now available at ``nexustrader.base.retry.RetryManager`` for resilient asynchronous operations.

0.3.1
-----

**New Features & Improvements**

- **Windows support**: NexusTrader now runs natively on Windows. On Windows, ``uvloop`` is automatically skipped and the standard ``asyncio`` event loop is used instead.
