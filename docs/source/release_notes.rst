Release Notes
=============

0.3.6
-----

**Improvements**

- **Lazy credential validation**: Importing ``nexustrader`` no longer crashes with ``FileNotFoundError`` when ``.keys/.secrets.toml`` is missing. A warning is emitted instead, allowing public-only, mock, and backtest workflows to run without any credential file.

- **Multi-source credential resolution**: ``BasicConfig`` now supports three credential sources in priority order:

  1. **Direct pass** (highest priority) — existing behaviour, fully backward-compatible:

  .. code-block:: python

      BasicConfig(api_key="xxx", secret="yyy", testnet=True)

  2. **Settings auto-resolve** via the new ``settings_key`` parameter — reads from ``.keys/.secrets.toml`` or ``NEXUS_`` prefixed environment variables:

  .. code-block:: python

      # Resolves from [BINANCE.DEMO] in .secrets.toml
      # or from NEXUS_BINANCE__DEMO__API_KEY / NEXUS_BINANCE__DEMO__SECRET env vars
      BasicConfig(settings_key="BINANCE.DEMO", testnet=True)

  3. **Plain environment variables** via the new ``from_env()`` classmethod:

  .. code-block:: python

      # Reads BINANCE_API_KEY, BINANCE_SECRET, BINANCE_PASSPHRASE
      BasicConfig.from_env("BINANCE", testnet=True)

      # Custom variable names
      BasicConfig.from_env("X", api_key_var="MY_KEY", secret_var="MY_SECRET")

  All three methods can be combined — directly passed values always take precedence over auto-resolved values.

**Fixed**

- Fixed ``BasicConfig.passphrase`` type annotation from ``str = None`` to ``str | None = None``.

0.3.5
-----

**Breaking Changes**

- **Order identifier renamed — ``oid`` / ``eid``**: The internal order identifier previously exposed as ``order.id`` or ``order.uuid`` is now ``order.oid`` (Order ID). The exchange-assigned identifier is now ``order.eid`` (Exchange ID). Update all strategy and handler code that references these fields:

  .. code-block:: python

      # Before
      self.log.info(f"filled: {order.uuid}")
      self.cancel_order(symbol=symbol, uuid=my_uuid)

      # After
      self.log.info(f"filled: {order.oid}")
      self.cancel_order(symbol=symbol, oid=my_oid)

- **``OrderRegistry`` simplified**: The registry no longer maintains a bidirectional UUID↔ORDER_ID mapping. It now tracks active OIDs with a flat API: ``register_order(oid)``, ``is_registered(oid)``, ``unregister_order(oid)``, ``register_tmp_order(order)``, ``get_tmp_order(oid)``, ``unregister_tmp_order(oid)``. Direct lookup from OID → EID or EID → OID is no longer available through the registry; use ``cache.get_order(oid)`` to access full order objects.

- **``AsyncCache`` constructor**: The ``registry=`` keyword argument has been removed. A ``clock: LiveClock`` argument is now required. If you instantiate ``AsyncCache`` directly (e.g. in tests or custom components), update the call:

  .. code-block:: python

      # Before
      cache = AsyncCache(msgbus=msgbus, registry=registry, ...)

      # After
      from nexustrader.core.nautilius_core import LiveClock
      cache = AsyncCache(msgbus=msgbus, clock=LiveClock(), ...)

**Improvements**

- **Sync/async REST API unification**: Exchange REST API clients now expose a unified interface. Async REST methods are transparently callable in a synchronous context — the ``__getattr__`` wrapper auto-detects async methods and dispatches them via ``run_sync()`` using the running event loop. No manual ``asyncio.run()`` wrappers are needed.
- **Internal ``_order_status_update()``**: A single unified method now covers the full order lifecycle internally, replacing the former ``_order_initialized()`` entry point.

**Fixed**

- Fixed an ``AttributeError`` in ``BaseConnector`` where newly created ``Order`` objects used the removed ``id=`` field instead of ``oid=``, causing order tracking to fail silently.

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
