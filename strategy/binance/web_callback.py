from typing import Any

from nexustrader.config import (
    BasicConfig,
    Config,
    PublicConnectorConfig,
    WebConfig,
)
from nexustrader.constants import ExchangeType
from nexustrader.exchange.binance import BinanceAccountType
from nexustrader.strategy import Strategy
from nexustrader.engine import Engine
from nexustrader.web import create_strategy_app


class BinanceWebCallbackStrategy(Strategy):
    """Simple strategy that exposes a FastAPI callback and toggles a flag."""

    web_app = create_strategy_app(title="Binance Web Callback")

    def __init__(self) -> None:
        super().__init__()
        self.signal_enabled = False

    @web_app.post("/toggle")
    async def on_web_cb(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Toggle the signal flag and log the request payload."""
        self.signal_enabled = payload.get("enabled", not self.signal_enabled)
        self.log.info(f"Received web callback payload={payload}")
        return {"enabled": self.signal_enabled}


config = Config(
    strategy_id="binance_web_callback",
    user_id="demo_user",
    strategy=BinanceWebCallbackStrategy(),
    basic_config={
        ExchangeType.BINANCE: BasicConfig(
            testnet=False,
        )
    },
    public_conn_config={
        ExchangeType.BINANCE: [
            PublicConnectorConfig(
                account_type=BinanceAccountType.USD_M_FUTURE,
            )
        ]
    },
    web_config=WebConfig(enabled=True, host="127.0.0.1", port=6666, log_level="error"),
)

engine = Engine(config)

if __name__ == "__main__":
    try:
        engine.start()
    finally:
        engine.dispose()
