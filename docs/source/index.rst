Welcome to NexusTrader's documentation!
=========================================
.. |python-versions| image:: https://img.shields.io/badge/python-3.11%20|%203.12-blue
   :alt: Python Versions

.. |docs| image:: https://img.shields.io/badge/docs-passing-brightgreen
   :alt: Documentation Status

.. |version| image:: https://img.shields.io/pypi/v/nexustrader?&color=blue
   :alt: Version


|python-versions| |docs| |version|

Introduction
-----------------

NexusTrader is an open-source trading framework focused on **execution reliability**
for live systems. It is built for strategies that need to remain correct under
delayed acknowledgements, retries, reconnects, and exchange-side uncertainty.

For AI-native workflows, the `NexusTrader MCP <https://github.com/Quantweb3-com/NexusTrader-mcp>`_
layer can expose trading capabilities through the Model Context Protocol, making
it easier to connect the framework to Codex, Claude Code, Cursor, OpenClaw, and
other MCP-compatible tools.

Why NexusTrader
-----------------

- **Deterministic order execution**: WebSocket order paths are tracked until ACK,
  and ACK timeout can trigger REST confirmation before the system decides the
  request failed.
- **Idempotent order submission**: ``client_oid`` and ``idempotency_key`` help
  suppress duplicate creates and make retries safer.
- **Reconnect reconciliation**: After a private WebSocket reconnect, NexusTrader
  can resync balances, positions, and open orders, then emit a reconciliation diff
  to the strategy layer.
- **Observable execution state**: Failed orders carry a reason, lifecycle events
  are published, and pending ACK state is tracked explicitly.
- **MCP-friendly AI integration**: The NexusTrader MCP layer helps expose trading
  workflows to MCP-compatible assistants such as Codex, Claude Code, Cursor, and
  OpenClaw without requiring a separate adapter for each IDE or agent tool.

Reliability And Performance
-----------------------------

- **Enhanced Event Loop Performance**:
  NexusTrader leverages `uvloop <https://github.com/MagicStack/uvloop>`_, a high-performance event loop, delivering speeds up to 2-4 times faster than Python's default asyncio loop.
- **High-Performance WebSocket Framework**:
  Built with `picows <https://github.com/tarasko/picows>`_, a Cython-based WebSocket library that matches the speed of C++'s Boost.Beast, significantly outperforming Python alternatives like websockets and aiohttp.
- **Optimized Data Serialization**:
  Utilizing `msgspec` for serialization and deserialization, NexusTrader achieves unmatched efficiency, surpassing tools like ``orjson``, ``ujson``, and ``json``. All data classes are implemented with ``msgspec.Struct`` for maximum performance.
- **Scalable Order Management**:
  Orders are handled efficiently using ``asyncio.Queue``, ensuring seamless processing even at high volumes.
- **Reliable Private WS Recovery**:
  After a private WebSocket reconnect, NexusTrader can automatically resync balances, positions, and open orders, emit reconciliation diffs to strategies, and confirm uncertain WS order state through REST when ACKs are delayed.
- **Lightweight Core Runtime**:
  Core infrastructure such as the MessageBus, Clock, and logging stack now runs on lightweight pure-Python components plus ``nexuslog``, avoiding heavy Rust build requirements while keeping live-trading behavior predictable.

Architecture
----------------------------

The core of NexusTrader sits between your strategy and the exchange APIs. Public
connectors provide market data, private connectors manage account state, the EMS
submits requests, and the OMS tracks order state through the full execution path.

.. image:: ./_static/arch.png
   :alt: Data Flow Diagram
   :align: center

Key Capabilities
--------------

- **Multi-exchange integration**: Binance, Bybit, OKX, Bitget, HyperLiquid, and
  Bybit TradFi (MT5).
- **Low-latency data and order paths**: Built around asyncio, ``picows``, and
  ``msgspec`` for efficient live operation.
- **Resilient order handling**: Pending ACK tracking, REST fallback, and
  reconnect reconciliation are built into the framework.
- **Scalable strategy workflows**: Suitable for multi-symbol, event-driven, timer,
  and signal-driven strategies.
- **TradFi support**: Bybit TradFi extends the framework into Forex, Gold,
  Indices, and Stocks through MetaTrader 5 on Windows.

Contact
-------

.. |twitter| image:: https://img.shields.io/badge/X-000000?&logo=x&logoColor=white
   :target: https://x.com/quantweb3_ai

.. |discord| image:: https://img.shields.io/badge/Discord-5865F2?&logo=discord&logoColor=white
   :target: https://discord.gg/BR8VGRrXFr

.. |telegram| image:: https://img.shields.io/badge/Telegram-2CA5E0?&logo=telegram&logoColor=white
   :target: https://t.me/+6e2MtXxoibM2Yzlk

|twitter| Stay updated with our latest news, features, and announcements.

|discord| Join our community to discuss ideas, get support, and connect with other users.

|telegram| Receive instant updates and engage in real-time discussions.

Contents
----------

.. toctree::
   :maxdepth: 2

   installation
   quickstart/index
   concepts/index
   exchange/index
   api/index
   release_notes
