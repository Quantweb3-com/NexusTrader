Release Notes
=============

0.3.12
------

**Added: ``pandas`` dependency**

``pandas>=3.0.1`` is now a required dependency of NexusTrader.

**Changed: ``MetaTrader5`` is now optional**

The ``MetaTrader5`` package is declared under ``[project.optional-dependencies]``
(``tradfi`` group, Windows only) instead of a hard dependency.  Installing
NexusTrader on Linux or macOS no longer fails because of a platform-incompatible
package.

**Fixed: non-Windows platform error handling**

``_check_platform()`` in ``_mt5_bridge.py`` now raises ``SystemExit`` instead of
``RuntimeError`` when not running on Windows.  The error message is clearer and
the process exits cleanly without printing a traceback.

**Fixed: ``ImportError`` on non-Windows during MT5 init**

``BybitTradeFiPrivateConnector.connect()`` now catches ``ImportError`` from the
``mt5_initialize`` executor call and converts it into a ``SystemExit`` with an
actionable message, avoiding a confusing raw ``ImportError`` traceback.

**Fixed: premature ``disconnect()`` crash**

A new ``_mt5_connected`` boolean flag on ``BybitTradeFiPrivateConnector`` prevents
``disconnect()`` from attempting an MT5 shutdown when the connection was never
successfully established, avoiding a crash during engine teardown after a failed
``connect()``.

**Fixed: synchronous OMS initialisation in constructor**

``BybitTradeFiOrderManagementSystem.__init__`` no longer calls the synchronous
``_init_account_balance()`` and ``_init_position()`` methods at construction time.
These are now deferred to the async variants invoked inside
``BybitTradeFiPrivateConnector.connect()``, keeping the constructor free of
blocking I/O.

**Changed: demo strategy platform tips**

All Bybit TradFi demo strategies (``demo_market_data.py``, ``demo_multi_symbol.py``,
``demo_trading.py``, ``xau_arb_market_data.py``) now include a top-of-file comment
informing users that MetaTrader 5 requires Windows.

0.3.11
------

**New: Bybit TradFi — Traditional Financial Markets via MetaTrader 5**

NexusTrader now supports traditional financial markets (Forex, Gold, Indices,
Stocks) through the Bybit TradFi brokerage, which uses a MetaTrader 5 terminal
as the execution backend.

Key additions:

- ``BybitTradeFiPublicConnector`` — polling-based market data (BookL1, Trade,
  Kline, historical klines) via the MT5 Python API. No WebSocket required.
- ``BybitTradeFiPrivateConnector`` — terminal initialisation, login, broker
  connectivity check, market loading, and order lifecycle management.
- ``BybitTradeFiOrderManagementSystem`` — market orders, limit/pending orders,
  cancel, and polling-based status updates mapped to standard NexusTrader
  order states.
- ``ExchangeType.BYBIT_TRADFI`` and ``BybitTradeFiAccountType`` (``DEMO`` / ``LIVE``).
- Symbol naming: internal dots in MT5 names are replaced with underscores
  (``XAUUSD.s`` → ``XAUUSD_s.BYBIT_TRADFI``, ``TSLA.s`` → ``TSLA_s.BYBIT_TRADFI``).
- Demo strategies in ``strategy/bybit_tradfi/``.

**Fixed: stdout log buffering**

``setup_nautilus_core`` now defaults ``batch_size=1`` for ``nexuslog`` so that
log messages appear immediately instead of being buffered until 32 entries
accumulate. Previously this caused complete silence while waiting for blocking
operations such as ``mt5.initialize()``.

**Fixed: ``request_klines`` deadlock**

Synchronous data-request helpers (``request_klines``, ``request_ticker``,
``request_all_tickers``) now submit work directly to the ``ThreadPoolExecutor``
instead of going through ``task_manager.run_sync()``, which blocked the event
loop thread while waiting for a coroutine scheduled on that same loop.

**Fixed: Kline over-emission**

Kline polling previously emitted the current unconfirmed bar on every poll
cycle (every 0.5 s). It now only emits on bar open, on close-price change
within the bar, and on bar close.

0.3.10
------

**Performance: WebSocket startup ~4-5 s (was ~12 s)**

Private-connector startup was dominated by fixed ``asyncio.sleep(5)`` calls
used as a safety margin after sending WebSocket auth payloads. Each exchange
had at least two sequential sleeps (WS API client + private WS client),
totalling ~10-12 seconds of idle waiting before the engine was ready.

Two complementary optimisations eliminate almost all of that overhead:

1. **Event-driven auth completion** — ``asyncio.sleep(5)`` is replaced by an
   ``asyncio.Event`` that fires as soon as the exchange acknowledges the auth
   request. A 5-second timeout is kept as a safety fallback. Each exchange OMS
   now detects the auth/login response and calls ``notify_auth_success()`` on
   the corresponding WS client.

2. **Parallel WS connection** — Bybit, OKX, and Bitget private connectors now
   connect and authenticate both the WS API client and the private WS client
   concurrently via ``asyncio.gather()``. Binance non-spot accounts similarly
   parallelise the WS API connection and the REST listen-key request.

Affected exchanges: Binance, Bybit, OKX, Bitget.

0.3.9
-----

**Fixed: Binance startup crash on position mode check**

The four REST API calls in Binance ``_position_mode_check`` were not wrapped
with ``_run_sync()`` after the sync-to-async API client migration in v0.3.5.
This caused a ``'coroutine' object is not subscriptable`` error on startup for
Binance linear, inverse, and portfolio margin accounts.

0.3.8
-----

**Fixed: ``Order.reason`` now populated on failure**

All exchange OMS implementations (Binance, Bybit, OKX, Bitget, HyperLiquid)
now set the ``Order.reason`` field when creating ``FAILED`` or ``CANCEL_FAILED``
orders. Previously the error message was only logged and then discarded —
strategies receiving ``on_failed_order`` / ``on_cancel_failed_order`` callbacks
always saw ``order.reason = None``.

The field is populated from the exchange error response across all failure paths:
REST exceptions, WebSocket API errors, and batch order individual failures.

.. code-block:: python

    def on_failed_order(self, order: Order):
        self.log.error(f"Order {order.oid} failed: {order.reason}")

    def on_cancel_failed_order(self, order: Order):
        self.log.error(f"Cancel {order.oid} failed: {order.reason}")

0.3.7
-----

**Performance: ~70 ms cold import (was several seconds)**

The ``nautilus-trader`` dependency has been removed. It was the dominant source of
slow startup because of its Rust/Cython initialisation overhead. All functionality
is now provided by pure-Python code and the lightweight ``nexuslog`` package.

**What changed**

- ``nautilus-trader`` is no longer installed. A Rust toolchain or ``build-essential``
  is no longer required on any platform.
- ``nexuslog`` (``>=0.4.0``) is the new logging backend.
- All previously Rust-backed components are now pure Python:

  - ``MessageBus`` — pub/sub and point-to-point endpoint routing.
  - ``LiveClock`` — wall-clock time, asyncio-based repeating timers.
  - ``TimeEvent`` — timer event dataclass (``ts_event``, ``ts_init`` in nanoseconds).
  - ``hmac_signature``, ``rsa_signature``, ``ed25519_signature`` — crypto signing helpers.
  - ``TraderId``, ``UUID4`` — identifier utilities.

- ``LogColor`` in ``nexustrader.constants`` is now a plain Python ``Enum`` with the
  same attribute names (``NORMAL``, ``GREEN``, ``BLUE``, ``MAGENTA``, ``CYAN``,
  ``YELLOW``, ``RED``).

**Migration — zero changes required for most users**

Existing strategy code is fully compatible:

- ``self.log.info(msg, color=LogColor.BLUE)`` continues to work unchanged.
- ``from nexustrader.constants import LogColor`` continues to work unchanged.
- ``LogConfig`` and all ``Engine`` / ``Config`` APIs are unchanged.

The only internal breaking change is that ``setup_nautilus_core()`` now returns
``(msgbus, clock)`` instead of the former three-tuple ``(log_guard, msgbus, clock)``.
This affects only code that calls ``setup_nautilus_core`` directly (not typical
strategy code).

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
