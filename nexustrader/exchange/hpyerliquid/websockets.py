import msgspec
import asyncio

from typing import Any, Callable, List, Dict
from aiolimiter import AsyncLimiter

from nexustrader.base import WSClient
from nexustrader.core.entity import TaskManager
from nexustrader.exchange.hpyerliquid.constanst import (
    HyperLiquidAccountType,
    HyperLiquidKlineInterval,
)


class HyperLiquidWSClient(WSClient):
    def __init__(
        self,
        account_type: HyperLiquidAccountType,
        handler: Callable[..., Any],
        task_manager: TaskManager,
    ):
        self._account_type = account_type
        url = account_type.ws_url

        super().__init__(
            url,
            handler=handler,
            task_manager=task_manager,
            ping_idle_timeout=5,
            ping_reply_timeout=2,
            specific_ping_msg=msgspec.json.encode({"method": "ping"}),
            auto_ping_strategy="ping_when_idle",
        )

    async def _subscribe(self, msgs: List[Dict[str, str]]):
        msgs = [msg for msg in msgs if msg not in self._subscriptions]
        await self.connect()
        for msg in msgs:
            self._subscriptions.append(msg)
            format_msg = ".".join(msg.values())
            self._log.debug(f"Subscribing to {format_msg}...")
            self._send(
                {
                    "method": "subscribe",
                    "subscription": msg,
                }
            )

    async def _resubscribe(self):
        for msg in self._subscriptions:
            self._send(
                {
                    "method": "subscribe",
                    "subscription": msg,
                }
            )

    async def subscribe_trades(self, symbols: List[str]):
        msgs = [{"type": "trades", "coin": symbol} for symbol in symbols]
        await self._subscribe(msgs)

    async def subscribe_bbo(self, symbols: List[str]):
        msgs = [{"type": "bbo", "coin": symbol} for symbol in symbols]
        await self._subscribe(msgs)

    async def subscribe_l2book(self, symbols: List[str]):
        msgs = [{"type": "l2Book", "coin": symbol} for symbol in symbols]
        await self._subscribe(msgs)

    async def subscribe_candle(
        self, symbols: List[str], interval: HyperLiquidKlineInterval
    ):
        msgs = [
            {"type": "candle", "coin": symbol, "interval": interval.value}
            for symbol in symbols
        ]
        await self._subscribe(msgs)


async def main():
    loop = asyncio.get_event_loop()
    task_manager = TaskManager(
        loop=loop,
    )
    client = HyperLiquidWSClient(
        account_type=HyperLiquidAccountType.MAINNET,
        handler=lambda msg: print(msg),
        task_manager=task_manager,
    )
    await client.subscribe_l2book(symbols=["BTC", "ETH"])
    await task_manager.wait()

if __name__ == "__main__":
    asyncio.run(main())
