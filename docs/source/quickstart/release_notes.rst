Release Notes
=============

0.3.32
------

**Fixed: fast-closing create ACKs are reconciled through REST**

Binance, Bitget, Bybit, OKX, and HyperLiquid now schedule short REST order
lookup after successful REST or WebSocket create ACKs for ``MARKET`` and
``IOC`` / ``FOK`` orders. If the private order stream misses a fast terminal
event, the real ``FILLED`` / ``CANCELED`` / ``EXPIRED`` state is written back
instead of leaving the order stuck in ``PENDING`` or ``ACCEPTED`` until cache
expiry.

**Fixed: cache order status updates now have a public API**

``AsyncCache.update_order_status()`` is now the public wrapper for validated
order status cache writes, so OMS code no longer needs to call the private
``_order_status_update()`` method directly.

**Fixed: batch create ACKs use the same terminal reconciliation**

Binance, Bybit, OKX, and HyperLiquid batch create success paths now reuse the
same post-ACK reconciliation helper for fast-closing orders.

0.3.31
------

**Fixed: Binance cancel ACK terminal states are applied immediately**

Binance WebSocket cancel ACKs now apply returned terminal states such as
``CANCELED`` or ``FILLED`` immediately instead of always writing
``CANCELING`` and waiting for a private order-stream event.

**Fixed: cancel success paths use short REST reconciliation across exchanges**

Binance, Bitget, Bybit, OKX, and HyperLiquid now schedule a short delayed REST
order lookup after successful cancel ACKs that leave the order in
``CANCELING``. If the private order stream misses the terminal event, the real
``FILLED`` / ``CANCELED`` / ``EXPIRED`` state is written back quickly.

**Fixed: Binance user-data stream expiry is recovered explicitly**

Binance ``listenKeyExpired`` events now trigger user-data stream recovery and
resync, and private connector health includes latest order/account update
timestamps.

0.3.30
------

**Fixed: Bybit server-time sync uses curl_cffi response attributes**

Bybit signed REST request preparation now reads ``response.content`` and
``response.status_code`` from ``curl_cffi`` responses, preventing repeated
``'Response' object has no attribute 'read'`` warnings. Failed time-sync
attempts now use a short 5 second retry backoff instead of retrying on every
signed request.

**Fixed: cancel ``Unknown order`` / not-found errors trigger REST reconciliation**

Binance, Bitget, Bybit, OKX, and HyperLiquid WebSocket cancel not-found style
errors now immediately trigger REST order lookup. Closed REST states are written
back and resolve the cancel ACK wait, reducing the chance that a maker fill
remains unpaired until a long strategy timeout fires.

0.3.29
------

**Fixed: OKX import dependency is declared**

``orjson`` is now included in the base dependencies because the OKX exchange
module imports it during the ``nexustrader.engine`` import chain. This prevents
fresh installs from failing with a missing dependency that downstream broad
exception handlers could misreport as ``nexustrader not available``.

0.3.28
------

**Fixed: Linux/macOS base installs no longer require MetaTrader5**

``MetaTrader5`` is now available only through the Windows-only ``tradfi`` extra,
so base installs on Linux/macOS do not attempt to install the Windows-only MT5
wheel. ``requirements.txt`` and Docker installation paths were also synchronized
with the current production dependency set.

0.3.27
------

**Fixed: Bybit TradFi position cache now stays synchronized with MT5**

Bybit TradFi uses a local MetaTrader 5 terminal process instead of a private
exchange WebSocket. NexusTrader now refreshes MT5 ``positions_get()`` into the
strategy cache after connector startup, on a background polling loop, after
immediate market fills, and after pending-order close events.

This makes position reads reliable during live MT5 trading:

.. code-block:: python

   position = self.cache.get_position("XAUUSD_s.BYBIT_TRADFI")

**Fixed: stale Bybit TradFi positions are cleared**

When MT5 returns an empty positions list, stale ``BYBIT_TRADFI`` positions are
removed from the cache. When MT5 returns ``None``, NexusTrader treats that as a
read failure and keeps the existing cache state to avoid falsely flattening
positions during transient terminal/API errors.

**Documentation: standard symbols and side semantics**

The Bybit TradFi and cache docs now clarify that strategy APIs and cache lookups
must use NexusTrader symbols, not raw MT5 broker symbols:

.. code-block:: python

   # Correct
   self.cache.get_position("XAUUSD_s.BYBIT_TRADFI")

   # Wrong
   self.cache.get_position("XAUUSD.s")

``Position.side`` uses ``PositionSide.LONG`` / ``PositionSide.SHORT`` /
``PositionSide.FLAT``. Order direction remains ``OrderSide.BUY`` /
``OrderSide.SELL`` across Bybit TradFi and all other exchanges.

**Fixed: OKX market loading accepts integer ``instIdCode`` values**

OKX can return numeric ``instIdCode`` values from the public instruments
endpoint. NexusTrader now accepts both string and integer values when decoding
OKX market metadata, so startup keeps the ``BTCUSDT-PERP.OKX`` to
``BTC-USDT-SWAP`` mapping required by public subscriptions and WebSocket order
operations.

**Verification**

.. code-block:: powershell

   uv run ruff check
   uv run pytest

0.3.26
------

**Fixed: ``on_start()`` can access the engine event loop**

``Engine.start()`` now sets the engine loop as the current thread event loop
before calling the user ``on_start()`` hook. Existing strategy code can use
``asyncio.get_event_loop()`` in ``on_start()`` and schedule tasks without
accessing the private ``engine._loop`` attribute.

**Fixed: ``Strategy.set_timer()`` compatibility restored**

The old public ``set_timer(callback, interval, ...)`` API has been restored as
a deprecated wrapper around ``schedule(..., trigger="interval")``. It now emits
``DeprecationWarning`` and maps ``interval``, ``name``, ``start_time``, and
``stop_time`` to the scheduler instead of failing with ``AttributeError``.

**Verification**

Regression coverage was added for both compatibility fixes:

.. code-block:: powershell

   uv run pytest test\core\test_engine_start_loop.py test\core\test_strategy_timer_compat.py -q

0.3.25
------

**Fixed: credential TOML file is no longer required at import/startup**

Importing ``nexustrader.constants`` no longer raises ``FileNotFoundError`` when
``.keys/.secrets.toml`` is missing. The runtime now emits a warning instead,
so public-only market-data workflows, mock setups, tests, and direct-credential
configurations are not blocked by the absence of a TOML secrets file.

**Fixed: multiple credential sources are supported again**

``BasicConfig`` now accepts the supported credential sources without forcing
users into one file format:

- direct constructor values: ``BasicConfig(api_key="...", secret="...")``
- Dynaconf lookup: ``BasicConfig(settings_key="BYBIT.DEMO")``
- plain environment variables: ``BasicConfig.from_env("BYBIT")``

Dynaconf lookup supports both ``.keys/.secrets.toml`` and ``NEXUS_`` prefixed
nested environment variables such as ``NEXUS_BYBIT__DEMO__API_KEY``. Plain
environment lookup reads variables like ``BYBIT_API_KEY``, ``BYBIT_SECRET``,
and ``BYBIT_PASSPHRASE``.

**Operational note**

Private trading still requires valid API credentials. This patch only changes
when and where credential validation happens: startup/import is permissive, and
private connector initialization or exchange requests remain responsible for
failing when required credentials are actually missing.

**Verification**

The hotfix was checked by importing ``nexustrader.constants`` without
``.keys/.secrets.toml``, resolving credentials through both
``BasicConfig.from_env()`` and ``BasicConfig(settings_key=...)``, then running
``ruff check`` and ``py_compile`` on the changed config modules.

0.3.24
------

**New: local compatibility layer for core runtime primitives**

NexusTrader now includes lightweight in-repo replacements for the core
nautilus-style primitives used by the runtime and tests, including
``MessageBus``, ``LiveClock``, ``TraderId``, ``UUID4``, signature helpers, and
minimal HTTP/WebSocket shims. Strategies and tests no longer need to import
these primitives directly from ``nautilus-trader``.

**New: websocket health reporting**

Public and private websocket clients now expose operational health through
``get_health()``. The health payload includes connection state, subscription
count, last message timestamp and age, message count, reconnect count, and
disconnect timestamps.

**New: direct Binance kline websocket subscriptions**

Binance kline subscriptions now support direct combined-stream websocket
clients with stream chunking, heartbeat handling, receive timeouts, reconnect
backoff, and dedicated health reporting for the direct kline stream.

**Changed: dependency and platform profile simplified**

Project metadata now targets Python ``>=3.11,<3.13``, skips ``uvloop`` on
Windows, and uses a smaller dependency set centered on the currently supported
runtime path. ``Engine`` selects ``WindowsSelectorEventLoopPolicy`` on Windows
so ``aiohttp`` / ``aiodns`` can run reliably without ``uvloop``.

**Changed: exchange and documentation surface narrowed**

The active documented exchange paths are now Binance, Bybit, and OKX. Legacy
or unused factory modules, CLI/web app modules, persistence backends, Bybit
TradFi, Bitget, and HyperLiquid implementation/docs were removed or excluded
from the main documentation surface. Sphinx API, concept, exchange,
installation, and quickstart docs were refreshed to match the current runtime.

**Fixed: Bybit startup timestamp failures**

Bybit market loading now disables ccxt's private currency prefetch by default,
enables time-difference adjustment, and uses a 10 second receive window. This
prevents startup from failing on private coin-info timestamp checks when local
system time drifts outside Bybit's default receive window.

**Fixed: Bybit signed REST timestamp drift**

The Bybit REST client now uses a 10 second receive window and syncs a cached
Bybit server-time offset before signed requests. Public Bybit subscription
examples now configure public connectors only, avoiding
``/v5/account/wallet-balance`` initialization for market-data-only demos.

**Fixed: OKX market loading sandbox parsing failures**

OKX markets are now loaded from raw public instrument endpoints. Malformed
instruments are skipped without aborting engine startup.

**Testing**

Focused coverage was added or updated for websocket health tracking, local
message bus behavior, OKX raw market loading, and Bybit exchange/REST timestamp
configuration. The focused Bybit checks were verified with:

.. code-block:: powershell

   uv run pytest test\exchange\test_bybit_exchange_config.py test\exchange\test_bybit_rest_api.py -q

0.3.23
------

**Fixed: ``cancel_all_orders()`` skipped already-marked orders on Bitget / HyperLiquid / OKX EMS**

``Strategy.cancel_all_orders()`` marks all currently open OIDs with cancel intent
before the request is handed to EMS. The Bitget / HyperLiquid / OKX EMS
overrides then called ``get_open_orders()`` without ``include_canceling=True``,
so they could immediately observe an empty set and never send the real
per-order cancel requests. Those paths now fetch the full open-order set and
fan out the cancel requests correctly.

**Fixed: OKX ``cancel_all_orders()`` was a no-op**

``OkxOrderManagementSystem.cancel_all_orders()`` now submits batched REST
requests through ``/api/v5/trade/cancel-batch-orders`` instead of doing
nothing. Requests are chunked to 20 orders per batch, successful entries are
marked ``CANCELING``, and rejected entries are surfaced as ``CANCEL_FAILED``
with the exchange error message preserved per order.

**Fixed: amend-order success paths no longer violate the order state machine**

Binance / Bybit / OKX previously wrote ``OrderStatus.PENDING`` after a
successful modify request. For an order already in ``ACCEPTED`` or
``PARTIALLY_FILLED`` state, this creates an invalid transition such as
``ACCEPTED -> PENDING`` that is rejected by ``STATUS_TRANSITIONS``, causing the
cache update to be dropped silently. The amend paths now reuse the cached live
status so valid no-op transitions like ``ACCEPTED -> ACCEPTED`` and
``PARTIALLY_FILLED -> PARTIALLY_FILLED`` are accepted.

**Fixed: amend-order cache writes no longer erase known fill state**

Bybit / OKX amend success handlers were creating partial ``Order`` snapshots
that reset fields such as ``amount``, ``filled``, ``remaining``, ``side``,
``type``, and ``time_in_force`` when only price or size was amended. This was
especially dangerous for partially filled orders because the local cache could
lose the known execution state immediately after a successful amend. These
handlers now preserve the cached execution metadata and only overwrite fields
that genuinely changed; Binance also preserves the effective amount on
price-only amend requests.

0.3.22
------

**Changed: logging backend replaced — ``nexuslog`` → ``loguru``**

The ``nexuslog`` Rust-backed logging package has been replaced with
`loguru <https://github.com/Delgan/loguru>`_ — a pure-Python logger with
zero build requirements (no C++ or Rust toolchain needed on any platform).

The ``Logger`` shim interface (``self.log.info()``, ``self.log.debug()``, etc.)
is **fully backward-compatible**.  No strategy code changes are required.

**Changed: time-based log rotation**

``setup_nautilus_core()`` / ``setup_nexus_core()`` now supports automatic
daily log rotation when a ``filename`` is provided:

.. code-block:: python

   from nexustrader.config import Config, LogConfig

   config = Config(
       ...,
       log_config=LogConfig(
           filename="logs/nexus.log",   # enables rotation
       ),
   )

Rotation defaults:

- **When**: midnight (``rotation_when="midnight"``)
- **Retention**: 30 days (``rotation_backup_count=30``)
- **Encoding**: UTF-8
- **Mode**: async non-blocking (``enqueue=True``)

All defaults can be overridden by passing the corresponding kwargs
directly to ``setup_nautilus_core()``.

**Changed: ``TRACE`` level now fully supported**

loguru natively supports ``TRACE`` (level 5).  ``logger.trace()`` calls are
emitted at true TRACE severity — no longer remapped to DEBUG.

0.3.20
------

**Improved: Bybit TradFi tick polling interval reduced to 10 ms**

The default ``TICK_POLL_INTERVAL`` for ``BybitTradeFiPublicConnector`` has been
reduced from **100 ms to 10 ms**.  Because each ``symbol_info_tick()`` call to
the MT5 terminal completes in roughly 15–60 µs over the local named-pipe IPC,
the 100 ms default was far more conservative than necessary.  At 10 ms the
average bid/ask detection latency drops from ~50 ms to ~5 ms with negligible
additional CPU load (~0.6 % per polling symbol).

**New: ``tick_poll_interval`` configurable via ``PublicConnectorConfig``**

Users can now override the MT5 tick polling rate at configuration time without
subclassing or patching the connector:

.. code-block:: python

   # Default (10 ms)
   PublicConnectorConfig(account_type=BybitTradeFiAccountType.DEMO)

   # Custom (20 ms)
   PublicConnectorConfig(account_type=BybitTradeFiAccountType.DEMO, tick_poll_interval=0.02)

   # Aggressive (5 ms)
   PublicConnectorConfig(account_type=BybitTradeFiAccountType.DEMO, tick_poll_interval=0.005)

The field is ``None`` by default, in which case the connector's built-in
default (0.01 s) is used.  Other exchanges ignore this field entirely.

**New: ``price_type`` parameter for Bybit TradFi limit orders**

``create_order()`` and ``create_order_ws()`` now accept a ``price_type``
keyword argument for limit orders on Bybit TradFi.  When supplied, the OMS
calls ``symbol_info_tick()`` at the moment the order is actually dispatched to
MT5, replacing the price the strategy computed from a potentially stale
``on_bookl1`` event:

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - ``price_type``
     - Price sent to MT5
   * - *(not set)*
     - The ``price`` value supplied by the strategy (unchanged behaviour)
   * - ``"bid"``
     - Latest best bid, re-fetched at submission time
   * - ``"ask"``
     - Latest best ask, re-fetched at submission time
   * - ``"opponent"``
     - Best ask for a buy order, best bid for a sell order

.. code-block:: python

   # Cross the spread — aggressive limit, price fetched fresh at dispatch
   self.create_order(
       symbol="EURUSD.BYBIT_TRADFI",
       side=OrderSide.BUY,
       type=OrderType.LIMIT,
       amount=Decimal("0.1"),
       price_type="opponent",
   )

This parameter is **only effective for Bybit TradFi (MT5) limit orders**.
Passing it to any other exchange connector has no effect.

0.3.19
------

**Fixed: Bybit WebSocket ping timeout misaligned with official recommendation**

Both ``BybitWSClient`` and ``BybitWSApiClient`` used ``ping_idle_timeout=5``
and ``ping_reply_timeout=2``.  Bybit's official documentation recommends
sending a heartbeat every **20 seconds**; the 5-second interval was
unnecessarily aggressive and the 2-second reply window was too tight for
normal network jitter between the client and Bybit servers.

**Fix**: Updated both constructors to ``ping_idle_timeout=20`` /
``ping_reply_timeout=5``.

**Fixed: OKX WebSocket ping timeout misaligned with official recommendation**

Both ``OkxWSClient`` and ``OkxWSApiClient`` used ``ping_idle_timeout=5``
and ``ping_reply_timeout=2``.  OKX closes the connection if no message is
exchanged within **30 seconds**; the 5-second idle timeout was overly
aggressive and the 2-second reply window was too tight for typical latency
between a cloud host and OKX servers.

**Fix**: Updated both constructors to ``ping_idle_timeout=30`` /
``ping_reply_timeout=5``, aligning with Bitget and HyperLiquid which already
used these values.

0.3.18
------

**Fixed: Bybit WS API pong never recognized → infinite reconnect loop**

``BybitWSApiClient.user_api_pong_callback`` decoded pong frames using
``BybitWsApiGeneralMsg``, which has required fields ``retCode`` and ``retMsg``.
The actual Bybit API WS pong response is ``{"op": "pong", "connId": "xxx"}``
and does not carry those fields, so ``msgspec.json.decode`` raised
``DecodeError`` on every pong, the callback returned ``False``, picows
triggered a 2-second timeout, disconnected, and reconnected 1 second later —
an infinite reconnect loop.

**Fix 1**: ``user_api_pong_callback`` now decodes with ``BybitWsMessageGeneral``
(all fields optional; ``is_pong`` checks both ``op == "pong"`` and
``ret_msg == "pong"``), matching the approach already used by
``user_pong_callback`` for the public WS.

**Fix 2**: ``BybitWSApiClient.__init__`` now passes
``auto_ping_strategy="ping_periodically"``, consistent with ``BybitWSClient``.
Previously the omission defaulted to ``"ping_when_idle"``, causing
behavioural inconsistency between the public and private WS clients.

**Fixed: OKX WebSocket clients missing ``auto_ping_strategy``**

Both ``OkxWSClient`` and ``OkxWSApiClient`` were constructed without an
explicit ``auto_ping_strategy``, defaulting picows to ``"ping_when_idle"``.
This is inconsistent with the ``"ping_periodically"`` strategy used by every
other exchange's WS clients and can cause connection drops during low-traffic
periods.

**Fix**: Added ``auto_ping_strategy="ping_periodically"`` to both OKX WS
client constructors.

0.3.17
------

**Fixed: WebSocket reconnect loop missing ``await`` on ``disconnect()``**

In ``WSClient._connection_handler()``, the call to ``self.disconnect()`` inside
the reconnect loop was not ``await``-ed.  Since ``disconnect()`` is an
``async def``, the bare call produced a coroutine object that was silently
discarded, generating ``RuntimeWarning: coroutine 'WSClient.disconnect' was
never awaited`` on every reconnect cycle.  The stale transport was never torn
down, causing resource leaks and potential duplicate connections.

**Fix**: Added ``await`` to the ``self.disconnect()`` call in the reconnect
branch of ``_connection_handler()``.

**Fixed: ``Engine.dispose()`` deadlock when called from a signal handler**

When user code registered a ``signal.signal()`` handler that called
``engine.dispose()`` while ``engine.start()`` was blocking on
``loop.run_until_complete(self._start())``, ``dispose()`` would attempt another
``loop.run_until_complete()`` on the already-running event loop, raising
``RuntimeError: This event loop is already running``.

**Fix**: ``dispose()`` now checks ``self._loop.is_running()`` first.  If the
loop is active, it schedules ``task_manager._shutdown_event.set()`` via
``loop.call_soon_threadsafe()`` and returns immediately.  This allows
``_start()`` → ``task_manager.wait()`` to unblock naturally, and ``start()``'s
``finally`` block performs the actual disposal after the loop has stopped.

For users who override signal handling, the recommended pattern is::

    def _signal_handler(self, signum, frame):
        self.engine.dispose()   # now safe — returns immediately when loop is running

    engine.start()              # blocks until shutdown_event is set
    # dispose() runs in start()'s finally block after the loop stops

0.3.16
------

**Fixed: WebSocket disconnect not properly awaited**

``WSClient.disconnect()`` was a synchronous method.  Callers that held the
result of ``disconnect()`` without ``await`` would silently drop the coroutine,
leaving the underlying transport open and the associated asyncio tasks running
until the event loop was forcibly closed.

**Symptom**: After ``engine.dispose()``, stray ``Task was destroyed but it is
pending`` warnings appeared in the log.  On some runs the process hung for
several seconds after the strategy finished.

**Fix**: ``WSClient.disconnect()`` is now ``async``.  It saves a local
reference to the transport before clearing ``self._transport``, calls
``transport.disconnect()``, then ``await asyncio.wait_for(transport.wait_disconnected(), timeout=3.0)``
to confirm the connection is fully closed before firing the ``on_disconnected``
hook.  A 3-second timeout prevents indefinite blocking on a stuck transport.

All call sites updated accordingly:

- ``PublicConnector.disconnect()`` — ``await self._ws_client.disconnect()``
  (previously the call was commented out as "not needed").
- ``PrivateConnector.disconnect()`` — ``await self._oms._ws_client.disconnect()``.
- ``OkxPublicConnector.disconnect()`` — ``await self._business_ws_client.disconnect()``.
- ``bybit_tradfi._NullWsClientStub.disconnect()`` — promoted to ``async def``
  to satisfy the awaitable contract.

**Fixed: engine shutdown leaves pending tasks uncollected**

``Engine._close_event_loop()`` cancelled all remaining asyncio tasks but never
awaited them, so their ``CancelledError`` handlers never ran and the event loop
could not close cleanly.

**Fix**: After cancelling every task, the engine now calls
``loop.run_until_complete(asyncio.gather(*pending_tasks, return_exceptions=True))``
to drain them before ``loop.close()``.  The post-disconnect sleep was also
increased from 0.2 s to 0.5 s to give the WS transports time to finish their
handshake before the task sweep begins.

**Fixed: Binance historical kline fetch called outside async context**

``BinancePublicConnector._get_index_price_klines()`` and
``_get_historical_klines()`` assigned the raw coroutine returned by the REST
client to ``klines_response`` without running it, resulting in a
``coroutine was never awaited`` warning and an empty response.

**Fix**: Both calls are now wrapped with ``self._run_sync()``, consistent with
every other exchange (OKX, Bybit, Bitget) that already used ``_run_sync`` for
the same pattern.

0.3.15
------

**Fixed: reconnect resync deadlock (event-loop freeze)**

After a private WebSocket disconnected and reconnected, the post-reconnect
resync task called the synchronous ``_init_account_balance()`` /
``_init_position()`` helpers.  These helpers internally use
``asyncio.run_coroutine_threadsafe(coro, loop).result()``.  When called from
a coroutine that is *already running inside the event loop* (the resync is
launched via ``create_task``), ``.result()`` blocks the event-loop thread
while waiting for a future that can only be resolved by that same loop —
a classic deadlock.

**Symptom**: The ``resynced`` event never appeared after a reconnect, and
the entire event loop froze — no market data, no order callbacks, nothing.

**Fix**: A new ``_async_resync_init()`` helper in the base OMS offloads both
sync inits to a thread-pool executor via ``asyncio.run_in_executor()``.  The
executor thread blocks on ``.result()`` while the event loop remains free to
drive the submitted REST coroutines.  Applied to OKX, Binance, Bybit, Bitget,
and HyperLiquid.

**Fixed: spurious ``on_accepted_order`` callbacks after reconnect**

After reconnect, ``_resync_after_reconnect()`` fetches all current open orders
via REST and passes them to ``order_status_update()``.  Because the
``ACCEPTED → ACCEPTED`` state transition is deliberately allowed (to support
modify-order flows), every already-open order triggered a fresh
``on_accepted_order`` callback — even though nothing had changed.

**Symptom**: ``cnt_accepted`` was higher than ``cnt_submitted`` in tests.  In
production strategies, any logic placed in ``on_accepted_order`` (hedging,
position tracking, risk checks) would be re-executed for every open order
after every reconnect.

**Fix**: ``order_status_update()`` gains an optional ``silent=True`` parameter.
When set, the local cache is updated but no strategy callbacks are dispatched.
``_resync_after_reconnect()`` in OKX, Binance, and Bybit now compares the
fetched status against the cached status and passes ``silent=True`` when they
are identical.  Status transitions that represent a genuine change
(``PENDING → ACCEPTED``, ``ACCEPTED → FILLED``, etc.) continue to fire the
corresponding callbacks as before.

0.3.14
------

**New: order-create idempotency controls**

``CreateOrderSubmit`` now includes an optional ``idempotency_key`` and
``Strategy.create_order()`` / ``create_order_ws()`` accept both
``client_oid`` and ``idempotency_key``.  ``AsyncCache`` keeps a canonical
OID per idempotency key, so repeated strategy signals can safely reuse the
same logical order instead of generating duplicate submissions.

**New: explicit WebSocket ACK error types**

Added ``WsRequestNotSentError``, ``WsAckTimeoutError``, and
``WsAckRejectedError`` to distinguish between three failure modes:

- the request never left because the WS API socket was down,
- the request was sent but the exchange never acknowledged it in time,
- the exchange explicitly rejected the WS order/cancel request.

**New: ``WsOrderResultType`` structured result enum**

A new ``WsOrderResultType`` enum (``REQUEST_NOT_SENT``, ``ACK_REJECTED``,
``ACK_TIMEOUT``, ``ACK_TIMEOUT_CONFIRMED``) is now returned by
``create_order_ws()`` and ``cancel_order_ws()`` and is also published via
the new ``on_ws_order_request_result()`` strategy callback, giving
strategies a structured way to inspect WS ACK outcomes without catching
exceptions.

**New: ``on_ws_order_request_result()`` strategy callback**

A new overrideable ``Strategy`` method fires whenever a background WS
order or cancel task produces a structured ACK outcome::

    def on_ws_order_request_result(self, result: dict):
        # result keys: oid, symbol, exchange, result_type, reason, timestamp
        if result["result_type"] == WsOrderResultType.ACK_TIMEOUT:
            self.log.warning(f"WS ACK timeout for {result['oid']}: {result['reason']}")

This replaces the need to catch ``WsAckTimeoutError`` / ``WsAckRejectedError``
inside background tasks manually.

**Changed: WS ACK handling is now consistent across exchanges**

OKX, Binance, Bybit, Bitget, and HyperLiquid now register a pending ACK
future for each WS order or cancel request, reject all pending waiters when
the WS API disconnects, wait up to 5 seconds for an ACK, and then attempt a
REST confirmation before raising an ACK-timeout error.  This closes the gap
between "request sent" and "exchange state known" during transient WS issues.

**Changed: Bitget and HyperLiquid gain WS fallback parity**

``create_order_ws()`` and ``cancel_order_ws()`` on Bitget and HyperLiquid now
support the same ``ws_fallback=True`` behavior already available on OKX,
Binance, and Bybit.  If the WS send fails immediately, the OMS can retry via
REST instead of failing the order path outright.

**Changed: duplicate create submissions are rejected earlier**

Base EMS now suppresses repeated create requests when the order OID is
already inflight, already registered, or already present in cache.  The
HyperLiquid EMS applies the same protection after converting the strategy OID
into the exchange ``cloid`` representation.

**New: Bitget and HyperLiquid open-order REST recovery**

Bitget now provides the REST wrappers needed to query pending UTA, futures,
and spot orders, while HyperLiquid now exposes ``get_open_orders()`` from the
authenticated REST client.  Both OMS implementations now use these helpers in
``fetch_order()``, ``fetch_open_orders()``, and reconnect resync flows.

**Fixed: pending ACK waiters no longer hang on disconnect**

When a WS API connection drops mid-request, any coroutines still awaiting an
ACK are now failed immediately with ``WsRequestNotSentError`` instead of being
left pending in memory.

**Changed: ``fetch_order()`` gains a ``force_refresh`` parameter**

``Strategy.fetch_order()`` and all exchange OMS ``fetch_order()``
implementations now accept ``force_refresh=True`` to skip the local cache
and query the exchange REST API directly.  This is used internally by
ACK-timeout recovery paths and can be called from strategy code when
authoritative exchange state is required::

    order = self.fetch_order(symbol, oid, force_refresh=True)

**Fixed: duplicate-submit and ACK-recovery regressions are covered by tests**

Three new regression suites were added:

- ``test/test_order_idempotency.py`` covers canonical OID reuse and duplicate
  create suppression in strategy and EMS paths.
- ``test/test_ws_ack.py`` covers not-sent requests, ACK timeout with REST
  confirmation, explicit rejection, disconnect cleanup, and fallback behavior.
- ``test/test_ack_and_reconcile.py`` covers reconnect reconciliation logic,
  pending ACK rejection on disconnect, and REST-confirmation after timeout
  across multiple exchanges.

0.3.13
------

**New: WebSocket lifecycle hooks**

``WSClient`` now exposes ``set_lifecycle_hooks(on_connected, on_disconnected,
on_reconnected)``.  Hooks are fired automatically on each connection state
change and can be sync or async callables.  The OMS registers hooks at startup
and publishes ``private_ws_status`` and ``private_ws_resync_diff`` events to
the message bus so strategies can react via the new ``on_private_ws_status()``
and ``on_private_ws_resync_diff()`` callbacks.

**New: automatic reconnect order reconciliation**

After a private WebSocket reconnects, the OMS re-fetches balances, positions,
and open orders, then emits a diff summary containing positions opened/closed
and orders added/removed.  OKX, Binance, and Bybit each have exchange-specific
``_resync_after_reconnect()`` overrides with a configurable grace window
(``set_reconnect_reconcile_grace_ms()``) that prevents false order closures
from delayed snapshots.

**New: ``ws_fallback`` parameter on WS order methods**

``create_order_ws()`` and ``cancel_order_ws()`` across OKX, Binance, and Bybit
now accept a ``ws_fallback=True`` keyword argument.  When the WebSocket send
fails due to a ``ConnectionError`` the call automatically retries via REST
(default) or marks the order as ``FAILED`` / ``CANCEL_FAILED`` immediately
when ``ws_fallback=False``.

**New: ``fetch_order``, ``fetch_open_orders``, ``fetch_recent_trades``**

New OMS methods for querying live order state via REST, also exposed directly
on ``Strategy``::

    order = self.fetch_order(symbol, oid)
    open_orders = self.fetch_open_orders(symbol)
    recent = self.fetch_recent_trades(symbol, limit=50)

**New: OKX ``get_api_v5_trade_orders_pending``**

New REST endpoint wrapper for retrieving pending open orders used internally
by the OKX reconnect reconciliation.

**New: Binance fetch-order REST wrappers**

Added ``get_api_v3_order``, ``get_fapi_v1_order``, ``get_dapi_v1_order``,
``get_api_v3_open_orders``, ``get_fapi_v1_open_orders``, and
``get_dapi_v1_open_orders`` to the Binance REST client.

**Fixed: inactive symbol warnings across all exchanges**

``load_markets()`` in OKX, Binance, Bybit, and Bitget now skips instruments
where ``active=False`` before attempting to parse them (OKX additionally
skips ``info.state='preopen'``).  This eliminates the repeated
``Symbol Format Error: Expected float, got null`` warnings that appeared for
delisted or pre-launch instruments whose precision fields are all ``null``.

**Fixed: Bitget WS API silent order drop**

``BitgetWSApiClient._submit()`` and ``_uta_submit()`` now call
``_send_or_raise()`` instead of ``_send()``, so a disconnected socket raises
``ConnectionError`` rather than silently dropping the order request.  This
matches the same fix already applied to OKX, Binance, and Bybit in the same
release.

**Fixed: test ``nautilus_trader`` import**

``test/base/__init__.py``, ``test/base/conftest.py``, and
``test/core/conftest.py`` now import ``TraderId`` from
``nexustrader.core.nautilius_core`` instead of the removed
``nautilus_trader`` package, so all test suites collect correctly on Windows.

**Changed: ``WSClient._send()`` return value**

``_send()`` now returns ``bool`` (``True`` on success, ``False`` when not
connected) and a new ``_send_or_raise()`` helper raises ``ConnectionError``
when the socket is unavailable, used internally by the WS API clients.

**Changed: ``uv.toml`` link-mode**

Added ``link-mode = "copy"`` to suppress hardlink warnings when the uv cache
and the project ``.venv`` are on different drives.

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
