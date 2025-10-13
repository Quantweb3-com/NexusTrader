from typing import Callable, List, Dict
from typing import Any
from urllib.parse import urlencode
from nexustrader.base import WSClient
from nexustrader.exchange.binance.constants import (
    BinanceAccountType,
    BinanceKlineInterval,
    BinanceRateLimiter,
    BinanceRateLimitType,
)
from nexustrader.core.entity import TaskManager
from nexustrader.core.nautilius_core import hmac_signature, LiveClock


class BinanceWSClient(WSClient):
    def __init__(
        self,
        account_type: BinanceAccountType,
        handler: Callable[..., Any],
        task_manager: TaskManager,
        clock: LiveClock,
        ws_suffix: str = "/ws",
        custom_url: str | None = None,
    ):
        self._account_type = account_type
        url = account_type.ws_url

        if ws_suffix not in ["/ws", "/stream"]:
            raise ValueError(f"Invalid ws_suffix: {ws_suffix}")

        url += ws_suffix

        if custom_url is not None:
            url = custom_url

        super().__init__(
            url,
            handler=handler,
            task_manager=task_manager,
            clock=clock,
            enable_auto_ping=False,
        )

    def _send_payload(
        self, params: List[str], method: str = "SUBSCRIBE", chunk_size: int = 50
    ):
        # Split params into chunks of 100 if length exceeds 100
        params_chunks = [
            params[i : i + chunk_size] for i in range(0, len(params), chunk_size)
        ]

        for chunk in params_chunks:
            payload = {
                "method": method,
                "params": chunk,
                "id": self._clock.timestamp_ms(),
            }
            self._send(payload)

    async def _subscribe(self, params: List[str]):
        params = [param for param in params if param not in self._subscriptions]

        if not params:
            return

        for param in params:
            self._subscriptions.append(param)
            self._log.debug(f"Subscribing to {param}...")

        await self.connect()
        self._send_payload(params, method="SUBSCRIBE")

    async def _unsubscribe(self, params: List[str]):
        params = [param for param in params if param in self._subscriptions]

        if not params:
            return

        for param in params:
            self._subscriptions.remove(param)
            self._log.debug(f"Unsubscribing from {param}...")

        await self.connect()
        self._send_payload(params, method="UNSUBSCRIBE")

    async def subscribe_agg_trade(self, symbols: List[str]):
        if (
            self._account_type.is_isolated_margin_or_margin
            or self._account_type.is_portfolio_margin
        ):
            raise ValueError(
                "Not Supported for `Margin Account` or `Portfolio Margin Account`"
            )
        params = [f"{symbol.lower()}@aggTrade" for symbol in symbols]
        await self._subscribe(params)

    async def subscribe_trade(self, symbols: List[str]):
        if (
            self._account_type.is_isolated_margin_or_margin
            or self._account_type.is_portfolio_margin
        ):
            raise ValueError(
                "Not Supported for `Margin Account` or `Portfolio Margin Account`"
            )
        params = [f"{symbol.lower()}@trade" for symbol in symbols]
        await self._subscribe(params)

    async def subscribe_book_ticker(self, symbols: List[str]):
        if (
            self._account_type.is_isolated_margin_or_margin
            or self._account_type.is_portfolio_margin
        ):
            raise ValueError(
                "Not Supported for `Margin Account` or `Portfolio Margin Account`"
            )
        params = [f"{symbol.lower()}@bookTicker" for symbol in symbols]
        await self._subscribe(params)

    async def subscribe_partial_book_depth(self, symbols: List[str], level: int):
        if level not in (5, 10, 20):
            raise ValueError("Level must be 5, 10, or 20")
        params = [f"{symbol.lower()}@depth{level}@100ms" for symbol in symbols]
        await self._subscribe(params)

    async def subscribe_mark_price(self, symbols: List[str]):
        if not self._account_type.is_future:
            raise ValueError("Only Supported for `Future Account`")
        params = [f"{symbol.lower()}@markPrice@1s" for symbol in symbols]
        await self._subscribe(params)

    async def subscribe_user_data_stream(self, listen_key: str):
        await self._subscribe([listen_key])

    async def subscribe_kline(
        self,
        symbols: List[str],
        interval: BinanceKlineInterval,
    ):
        if (
            self._account_type.is_isolated_margin_or_margin
            or self._account_type.is_portfolio_margin
        ):
            raise ValueError(
                "Not Supported for `Margin Account` or `Portfolio Margin Account`"
            )
        params = [f"{symbol.lower()}@kline_{interval.value}" for symbol in symbols]
        await self._subscribe(params)

    async def unsubscribe_agg_trade(self, symbols: List[str]):
        if (
            self._account_type.is_isolated_margin_or_margin
            or self._account_type.is_portfolio_margin
        ):
            raise ValueError(
                "Not Supported for `Margin Account` or `Portfolio Margin Account`"
            )
        params = [f"{symbol.lower()}@aggTrade" for symbol in symbols]
        await self._unsubscribe(params)

    async def unsubscribe_trade(self, symbols: List[str]):
        if (
            self._account_type.is_isolated_margin_or_margin
            or self._account_type.is_portfolio_margin
        ):
            raise ValueError(
                "Not Supported for `Margin Account` or `Portfolio Margin Account`"
            )
        params = [f"{symbol.lower()}@trade" for symbol in symbols]
        await self._unsubscribe(params)

    async def unsubscribe_book_ticker(self, symbols: List[str]):
        if (
            self._account_type.is_isolated_margin_or_margin
            or self._account_type.is_portfolio_margin
        ):
            raise ValueError(
                "Not Supported for `Margin Account` or `Portfolio Margin Account`"
            )
        params = [f"{symbol.lower()}@bookTicker" for symbol in symbols]
        await self._unsubscribe(params)

    async def unsubscribe_partial_book_depth(self, symbols: List[str], level: int):
        if level not in (5, 10, 20):
            raise ValueError("Level must be 5, 10, or 20")
        params = [f"{symbol.lower()}@depth{level}@100ms" for symbol in symbols]
        await self._unsubscribe(params)

    async def unsubscribe_mark_price(self, symbols: List[str]):
        if not self._account_type.is_future:
            raise ValueError("Only Supported for `Future Account`")
        params = [f"{symbol.lower()}@markPrice@1s" for symbol in symbols]
        await self._unsubscribe(params)

    async def unsubscribe_user_data_stream(self, listen_key: str):
        await self._unsubscribe([listen_key])

    async def unsubscribe_kline(
        self,
        symbols: List[str],
        interval: BinanceKlineInterval,
    ):
        if (
            self._account_type.is_isolated_margin_or_margin
            or self._account_type.is_portfolio_margin
        ):
            raise ValueError(
                "Not Supported for `Margin Account` or `Portfolio Margin Account`"
            )
        params = [f"{symbol.lower()}@kline_{interval.value}" for symbol in symbols]
        await self._unsubscribe(params)

    async def _resubscribe(self):
        self._send_payload(self._subscriptions)


class BinanceWSApiClient(WSClient):
    def __init__(
        self,
        account_type: BinanceAccountType,
        api_key: str,
        secret: str,
        handler: Callable[..., Any],
        task_manager: TaskManager,
        clock: LiveClock,
        enable_rate_limit: bool,
    ):
        self._account_type = account_type
        self._api_key = api_key
        self._secret = secret
        self._limiter = BinanceRateLimiter(enable_rate_limit)

        url = account_type.ws_order_url

        if not url:
            raise ValueError(f"WebSocket URL not supported for {account_type}")

        super().__init__(
            url=url,
            handler=handler,
            task_manager=task_manager,
            clock=clock,
            enable_auto_ping=False,
        )

    def _generate_signature_v2(self, query: str) -> str:
        signature = hmac_signature(self._secret, query)
        return signature

    def _send_payload(
        self,
        id: str,
        method: str,
        params: Dict[str, Any],
        required_ts: bool = True,
        auth: bool = True,
    ):
        if required_ts:
            params["timestamp"] = self._clock.timestamp_ms()

        if auth:
            params["apiKey"] = self._api_key
            query = urlencode(sorted(params.items()))
            signature = self._generate_signature_v2(query)
            params["signature"] = signature

        payload = {
            "method": method,
            "id": id,
            "params": params,
        }
        self._send(payload)

    async def spot_new_order(
        self, oid: str, symbol: str, side: str, type: str, quantity: str, **kwargs: Any
    ):
        params = {
            "symbol": symbol,
            "side": side,
            "type": type,
            "quantity": quantity,
            **kwargs,
        }
        await self._limiter(
            account_type=BinanceAccountType.SPOT,
            rate_limit_type=BinanceRateLimitType.ORDERS,
        ).limit(
            key="spot.order.place",
            cost=1,
        )
        self._send_payload(id=f"n{oid}", method="order.place", params=params)

    async def spot_cancel_order(
        self, oid: str, symbol: str, origClientOrderId: int, **kwargs: Any
    ):
        params = {
            "symbol": symbol,
            "origClientOrderId": origClientOrderId,
            **kwargs,
        }
        await self._limiter(
            account_type=BinanceAccountType.SPOT,
            rate_limit_type=BinanceRateLimitType.REQUEST_WEIGHT,
        ).limit(
            key="spot.order.cancel",
            cost=1,
        )
        self._send_payload(id=f"c{oid}", method="order.cancel", params=params)

    async def usdm_new_order(
        self, oid: str, symbol: str, side: str, type: str, quantity: str, **kwargs: Any
    ):
        params = {
            "symbol": symbol,
            "side": side,
            "type": type,
            "quantity": quantity,
            **kwargs,
        }
        await self._limiter(
            account_type=BinanceAccountType.USD_M_FUTURE,
            rate_limit_type=BinanceRateLimitType.ORDERS,
        ).limit(
            key="usdm.order.place",
            cost=1,
        )
        self._send_payload(id=f"n{oid}", method="order.place", params=params)

    async def usdm_cancel_order(
        self, oid: str, symbol: str, origClientOrderId: int, **kwargs: Any
    ):
        params = {
            "symbol": symbol,
            "origClientOrderId": origClientOrderId,
            **kwargs,
        }
        await self._limiter(
            account_type=BinanceAccountType.USD_M_FUTURE,
            rate_limit_type=BinanceRateLimitType.REQUEST_WEIGHT,
        ).limit(
            key="usdm.order.cancel",
            cost=1,
        )
        self._send_payload(id=f"c{oid}", method="order.cancel", params=params)

    async def coinm_new_order(
        self, oid: str, symbol: str, side: str, type: str, quantity: str, **kwargs: Any
    ):
        params = {
            "symbol": symbol,
            "side": side,
            "type": type,
            "quantity": quantity,
            **kwargs,
        }
        await self._limiter(
            account_type=BinanceAccountType.COIN_M_FUTURE,
            rate_limit_type=BinanceRateLimitType.ORDERS,
        ).limit(
            key="coinm.order.place",
            cost=1,
        )
        self._send_payload(id=f"n{oid}", method="order.place", params=params)

    async def coinm_cancel_order(
        self, oid: str, symbol: str, origClientOrderId: int, **kwargs: Any
    ):
        params = {
            "symbol": symbol,
            "origClientOrderId": origClientOrderId,
            **kwargs,
        }
        await self._limiter(
            account_type=BinanceAccountType.COIN_M_FUTURE,
            rate_limit_type=BinanceRateLimitType.REQUEST_WEIGHT,
        ).limit(
            key="coinm.order.cancel",
            cost=1,
        )
        self._send_payload(id=f"c{oid}", method="order.cancel", params=params)

    async def _resubscribe(self):
        pass


import asyncio  # noqa


async def main():
    from nexustrader.constants import settings
    from nexustrader.core.entity import TaskManager
    from nexustrader.core.nautilius_core import LiveClock, setup_nautilus_core, UUID4

    # API_KEY = settings.BINANCE.SPOT.TESTNET.API_KEY
    # SECRET = settings.BINANCE.SPOT.TESTNET.SECRET

    API_KEY = settings.BINANCE.FUTURE.TESTNET_1.API_KEY
    SECRET = settings.BINANCE.FUTURE.TESTNET_1.SECRET

    log_guard = setup_nautilus_core(  # noqa
        trader_id="bnc-test",
        level_stdout="DEBUG",
    )

    task_manager = TaskManager(
        loop=asyncio.get_event_loop(),
    )

    ws_api_client = BinanceWSApiClient(
        account_type=BinanceAccountType.USD_M_FUTURE_TESTNET,
        api_key=API_KEY,
        secret=SECRET,
        handler=lambda msg: print(msg),
        task_manager=task_manager,
        clock=LiveClock(),
        enable_rate_limit=True,
    )

    await ws_api_client.connect()

    await ws_api_client.usdm_new_order(
        id=UUID4().value,
        symbol="BTCUSDT",
        side="BUY",
        type="LIMIT",
        quantity="0.003",
        price="120000",
        # timeInForce="GTC",
    )

    # await ws_api_client.usdm_cancel_order(
    #     id="aa510a1f-7240-4368-8cc0-ba577483a734",
    #     symbol="BTCUSDT",
    #     orderId=5594834544,  # Replace with a valid order ID
    # )

    # await ws_api_client.spot_new_order(
    #     id=UUID4().value,
    #     symbol="BTCUSDT",
    #     side="BUY",
    #     type="LIMIT",
    #     quantity="0.001",
    #     price="80000",
    #     timeInForce="GTC",
    # )
    # await ws_api_client.spot_cancel_open_orders(
    #     id="20dbbfdb-fc47-4abf-bb0f-bc0cd117c29a",
    #     symbol="BTCUSDT",
    # )

    await task_manager.wait()


if __name__ == "__main__":
    asyncio.run(main())
