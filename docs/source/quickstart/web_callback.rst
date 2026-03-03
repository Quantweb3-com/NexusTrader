Web Callbacks
==============

NexusTrader includes an optional embedded **FastAPI** web server that lets you expose HTTP
endpoints inside your strategy. This is useful for receiving external signals (e.g., from a
TradingView webhook or a custom dashboard) without running a separate process.

Enabling the Web Server
-----------------------

Set ``web_config`` in your :class:`~nexustrader.config.Config`:

.. code-block:: python

    from nexustrader.config import Config, WebConfig

    config = Config(
        ...
        web_config=WebConfig(
            enabled=True,
            host="127.0.0.1",
            port=6666,
            log_level="error",
        ),
    )

WebConfig Parameters
--------------------

.. list-table::
   :header-rows: 1
   :widths: 20 15 65

   * - Field
     - Type
     - Description
   * - ``enabled``
     - ``bool``
     - Enable the embedded web server (default: ``False``)
   * - ``host``
     - ``str``
     - Bind address (default: ``"0.0.0.0"``)
   * - ``port``
     - ``int``
     - Listening port (default: ``8000``)
   * - ``log_level``
     - ``str``
     - Uvicorn log level: ``"debug"``, ``"info"``, ``"warning"``, ``"error"``

Defining Endpoints in the Strategy
------------------------------------

Use the ``create_strategy_app`` helper to attach a FastAPI app to your strategy class, then
decorate methods with standard FastAPI decorators. The method receives ``self`` (the strategy
instance) so it can read and modify strategy state directly.

.. code-block:: python

    from typing import Any
    from nexustrader.strategy import Strategy
    from nexustrader.web import create_strategy_app

    class MyStrategy(Strategy):
        web_app = create_strategy_app(title="My Strategy")

        def __init__(self):
            super().__init__()
            self.signal_enabled = False

        @web_app.post("/toggle")
        async def on_toggle(self, payload: dict[str, Any]) -> dict[str, Any]:
            self.signal_enabled = payload.get("enabled", not self.signal_enabled)
            self.log.info(f"signal_enabled={self.signal_enabled}")
            return {"enabled": self.signal_enabled}

Calling the endpoint:

.. code-block:: bash

    curl -X POST http://127.0.0.1:6666/toggle \
         -H "Content-Type: application/json" \
         -d '{"enabled": true}'

Full Example
------------

.. code-block:: python

    from typing import Any

    from nexustrader.config import Config, PublicConnectorConfig, BasicConfig, WebConfig
    from nexustrader.constants import ExchangeType
    from nexustrader.exchange.binance import BinanceAccountType
    from nexustrader.strategy import Strategy
    from nexustrader.engine import Engine
    from nexustrader.web import create_strategy_app


    class BinanceWebCallbackStrategy(Strategy):
        """Exposes a /toggle endpoint to enable or disable the trading signal."""

        web_app = create_strategy_app(title="Binance Web Callback")

        def __init__(self) -> None:
            super().__init__()
            self.signal_enabled = False

        @web_app.post("/toggle")
        async def on_web_cb(self, payload: dict[str, Any]) -> dict[str, Any]:
            self.signal_enabled = payload.get("enabled", not self.signal_enabled)
            self.log.info(f"Received web callback payload={payload}")
            return {"enabled": self.signal_enabled}


    config = Config(
        strategy_id="binance_web_callback",
        user_id="demo_user",
        strategy=BinanceWebCallbackStrategy(),
        basic_config={
            ExchangeType.BINANCE: BasicConfig(testnet=False)
        },
        public_conn_config={
            ExchangeType.BINANCE: [
                PublicConnectorConfig(
                    account_type=BinanceAccountType.USD_M_FUTURE
                )
            ]
        },
        web_config=WebConfig(
            enabled=True,
            host="127.0.0.1",
            port=6666,
            log_level="error",
        ),
    )

    engine = Engine(config)

    if __name__ == "__main__":
        try:
            engine.start()
        finally:
            engine.dispose()

Interactive API Docs
--------------------

When the server is running, FastAPI automatically generates interactive documentation at:

- ``http://<host>:<port>/docs`` — Swagger UI
- ``http://<host>:<port>/redoc`` — ReDoc

.. note::

   The web server runs in a background thread so it does **not** block the main event loop.
   Endpoint handlers are ``async`` and run inside the server's own event loop; avoid
   directly awaiting coroutines from the main trading loop inside them.
