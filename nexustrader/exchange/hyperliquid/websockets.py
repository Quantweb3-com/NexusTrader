import msgspec

from typing import Any, Callable, List, Dict

from nexustrader.base import WSClient
from nexustrader.core.entity import TaskManager
from nexustrader.core.nautilius_core import LiveClock
from nexustrader.exchange.hyperliquid.constants import (
    HyperLiquidAccountType,
    HyperLiquidKlineInterval,
)


class HyperLiquidWSClient(WSClient):
    def __init__(
        self,
        account_type: HyperLiquidAccountType,
        handler: Callable[..., Any],
        task_manager: TaskManager,
        clock: LiveClock,
        api_key: str | None = None,  # in HyperLiquid, api_key is the wallet address
        custom_url: str | None = None,
    ):
        self._account_type = account_type

        if custom_url:
            url = custom_url
        else:
            url = account_type.ws_url

        self._api_key = api_key

        super().__init__(
            url=url,
            handler=handler,
            task_manager=task_manager,
            clock=clock,
            ping_idle_timeout=30,
            ping_reply_timeout=5,
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

    async def subscribe_order_updates(self):
        msg = {
            "type": "orderUpdates",
            "user": self._api_key,
        }
        await self._subscribe([msg])

    async def subscribe_user_events(self):
        msg = {
            "type": "userEvents",
            "user": self._api_key,
        }
        await self._subscribe([msg])

    async def subscribe_user_fills(self):
        msg = {
            "type": "userFills",
            "user": self._api_key,
        }
        await self._subscribe([msg])

    async def subscribe_user_fundings(self):
        msg = {
            "type": "userFundings",
            "user": self._api_key,
        }
        await self._subscribe([msg])

    async def subscribe_user_non_funding_ledger_updates(self):
        msg = {
            "type": "userNonFundingLedgerUpdates",
            "user": self._api_key,
        }
        await self._subscribe([msg])

    async def subscribe_web_data2(self):
        msg = {
            "type": "webData2",
            "user": self._api_key,
        }
        await self._subscribe([msg])

    async def subscribe_notification(self):
        msg = {
            "type": "notification",
            "user": self._api_key,
        }
        await self._subscribe([msg])
