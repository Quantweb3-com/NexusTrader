import msgspec
import eth_account
from eth_account.signers.local import LocalAccount
from eth_account.messages import encode_typed_data
from Crypto.Hash import keccak
from typing import Any, Callable, List, Dict, Literal

from nexustrader.base import WSClient
from nexustrader.core.entity import TaskManager
from nexustrader.core.nautilius_core import LiveClock
from nexustrader.exchange.hyperliquid.constants import (
    HyperLiquidAccountType,
    HyperLiquidKlineInterval,
    HyperLiquidRateLimiter,
    HyperLiquidOrderRequest,
    HyperLiquidOrderCancelRequest,
    HyperLiquidCloidCancelRequest,
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

    async def _unsubscribe(self, msgs: List[Dict[str, str]]):
        msgs = [msg for msg in msgs if msg in self._subscriptions]
        await self.connect()
        for msg in msgs:
            self._subscriptions.remove(msg)
            format_msg = ".".join(msg.values())
            self._log.debug(f"Unsubscribing from {format_msg}...")
            self._send(
                {
                    "method": "unsubscribe",
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

    async def unsubscribe_trades(self, symbols: List[str]):
        msgs = [{"type": "trades", "coin": symbol} for symbol in symbols]
        await self._unsubscribe(msgs)

    async def subscribe_bbo(self, symbols: List[str]):
        msgs = [{"type": "bbo", "coin": symbol} for symbol in symbols]
        await self._subscribe(msgs)

    async def unsubscribe_bbo(self, symbols: List[str]):
        msgs = [{"type": "bbo", "coin": symbol} for symbol in symbols]
        await self._unsubscribe(msgs)

    async def subscribe_l2book(self, symbols: List[str]):
        msgs = [{"type": "l2Book", "coin": symbol} for symbol in symbols]
        await self._subscribe(msgs)

    async def unsubscribe_l2book(self, symbols: List[str]):
        msgs = [{"type": "l2Book", "coin": symbol} for symbol in symbols]
        await self._unsubscribe(msgs)

    async def subscribe_candle(
        self, symbols: List[str], interval: HyperLiquidKlineInterval
    ):
        msgs = [
            {"type": "candle", "coin": symbol, "interval": interval.value}
            for symbol in symbols
        ]
        await self._subscribe(msgs)

    async def unsubscribe_candle(
        self, symbols: List[str], interval: HyperLiquidKlineInterval
    ):
        msgs = [
            {"type": "candle", "coin": symbol, "interval": interval.value}
            for symbol in symbols
        ]
        await self._unsubscribe(msgs)

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


class HyperLiquidWSApiClient(WSClient):
    """WebSocket API client for HyperLiquid order operations"""

    def __init__(
        self,
        account_type: HyperLiquidAccountType,
        api_key: str,
        secret: str,
        handler: Callable[..., Any],
        task_manager: TaskManager,
        clock: LiveClock,
        enable_rate_limit: bool = True,
    ):
        self._api_key = api_key
        self._secret = secret
        self._account_type = account_type
        self._testnet = account_type.is_testnet

        if secret:
            self._eth_account: LocalAccount = eth_account.Account.from_key(secret)

        url = account_type.ws_url
        self._limiter = HyperLiquidRateLimiter(enable_rate_limit=enable_rate_limit)

        # UUID to integer mapping for HyperLiquid API
        self._oid_to_id: Dict[str, int] = {}
        self._id_to_oid: Dict[int, str] = {}
        self._next_id = 1

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

    def _resubscribe(self):
        pass

    def _get_rate_limit_cost(self, length: int, cost: int = 1) -> int:
        """Get rate limit cost for an operation

        Please refer to https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/rate-limits-and-user-limits
        """
        return cost + length // 40

    def _oid_to_int(self, oid_str: str) -> int:
        """Convert oid to integer for HyperLiquid API compatibility"""
        if oid_str not in self._oid_to_id:
            self._oid_to_id[oid_str] = self._next_id
            self._id_to_oid[self._next_id] = oid_str
            self._next_id += 1
        return self._oid_to_id[oid_str]

    def _int_to_oid(self, id_int: int) -> str:
        """Convert integer back to oid"""
        return self._id_to_oid.get(id_int, str(id_int))

    def _construct_phantom_agent(self, hash_bytes: bytes) -> Dict[str, Any]:
        """Construct phantom agent for signature"""
        return {"source": "b" if self._testnet else "a", "connectionId": hash_bytes}

    def _action_hash(
        self, action: Dict[str, Any], nonce: int, vault_address: str = None
    ) -> bytes:
        """Generate action hash for signature"""
        data = msgspec.msgpack.encode(action)
        data += nonce.to_bytes(8, "big")
        if vault_address is None:
            data += b"\x00"
        else:
            data += b"\x01"
            data += bytes.fromhex(
                vault_address[2:] if vault_address.startswith("0x") else vault_address
            )
        return keccak.new(digest_bits=256, data=data).digest()

    def _sign_l1_action(
        self, action: Dict[str, Any], nonce: int, vault_address: str = None
    ) -> Dict[str, Any]:
        """Sign L1 action for authentication"""
        hash_bytes = self._action_hash(action, nonce, vault_address)
        phantom_agent = self._construct_phantom_agent(hash_bytes)
        encoded_data = encode_typed_data(
            full_message={
                "domain": {
                    "chainId": 1337,
                    "name": "Exchange",
                    "verifyingContract": "0x0000000000000000000000000000000000000000",
                    "version": "1",
                },
                "types": {
                    "Agent": [
                        {"name": "source", "type": "string"},
                        {"name": "connectionId", "type": "bytes32"},
                    ],
                    "EIP712Domain": [
                        {"name": "name", "type": "string"},
                        {"name": "version", "type": "string"},
                        {"name": "chainId", "type": "uint256"},
                        {"name": "verifyingContract", "type": "address"},
                    ],
                },
                "primaryType": "Agent",
                "message": phantom_agent,
            }
        )
        signed = self._eth_account.sign_message(encoded_data)
        return {
            "r": f"{signed.r:#x}",
            "s": f"{signed.s:#x}",
            "v": signed.v,
        }

    def _submit(
        self,
        oid: str,
        request_type: Literal["info", "action"],
        payload: Dict[str, Any],
    ):
        """Submit request to HyperLiquid WebSocket API"""
        message_id = self._oid_to_int(oid)
        message = {
            "method": "post",
            "id": message_id,
            "request": {"type": request_type, "payload": payload},
        }
        self._send(message)

    async def place_order(
        self,
        id: str,
        orders: List[HyperLiquidOrderRequest],
        grouping: Literal["na", "normalTpsl", "positionTpsl"] = "na",
    ):
        """Place orders via WebSocket"""
        nonce = self._clock.timestamp_ms()
        order_action = {
            "type": "order",
            "orders": orders,
            "grouping": grouping,
        }
        signature = self._sign_l1_action(order_action, nonce, vault_address=None)

        payload = {
            "action": order_action,
            "nonce": nonce,
            "signature": signature,
        }
        cost = self._get_rate_limit_cost(length=len(orders), cost=1)
        await self._limiter("/exchange").limit(key="order", cost=cost)
        self._submit(oid=id, request_type="action", payload=payload)

    async def cancel_order(
        self,
        id: str,
        cancels: List[HyperLiquidOrderCancelRequest],
    ):
        """Cancel orders via WebSocket"""
        nonce = self._clock.timestamp_ms()
        cancel_action = {
            "type": "cancel",
            "cancels": cancels,
        }
        signature = self._sign_l1_action(cancel_action, nonce, vault_address=None)

        payload = {
            "action": cancel_action,
            "nonce": nonce,
            "signature": signature,
        }
        cost = self._get_rate_limit_cost(length=len(cancels), cost=1)
        await self._limiter("/exchange").limit(key="cancel", cost=cost)
        self._submit(oid=id, request_type="action", payload=payload)

    async def cancel_orders_by_cloid(
        self,
        id: str,
        cancels: List[HyperLiquidCloidCancelRequest],
    ):
        nounce = self._clock.timestamp_ms()
        orderAction = {
            "type": "cancelByCloid",
            "cancels": cancels,
        }
        signature = self._sign_l1_action(orderAction, nounce, vault_address=None)
        payload = {
            "action": orderAction,
            "nonce": nounce,
            "signature": signature,
        }
        cost = self._get_rate_limit_cost(length=len(cancels), cost=1)
        await self._limiter("/exchange").limit(key="cancel", cost=cost)
        self._submit(oid=id, request_type="action", payload=payload)


# import asyncio  # noqa


# async def main():
#     from nexustrader.constants import settings
#     from nexustrader.exchange.hyperliquid.constants import oid_to_cloid_hex
#     from nexustrader.core.entity import TaskManager, OidGen
#     from nexustrader.core.nautilius_core import LiveClock, setup_nautilus_core

#     HYPER_API_KEY = settings.HYPER.TESTNET.API_KEY
#     HYPER_SECRET = settings.HYPER.TESTNET.SECRET

#     log_guard, _, clock = setup_nautilus_core(  # noqa
#         trader_id="hyper-test",
#         level_stdout="DEBUG",
#     )

#     oidgen = OidGen(clock)

#     task_manager = TaskManager(
#         loop=asyncio.get_event_loop(),
#     )

#     ws_api_client = HyperLiquidWSApiClient(
#         account_type=HyperLiquidAccountType.TESTNET,
#         api_key=HYPER_API_KEY,
#         secret=HYPER_SECRET,
#         handler=lambda msg: print(msg),
#         task_manager=task_manager,
#         clock=LiveClock(),
#         enable_rate_limit=True,
#     )
# oid = oid_to_cloid_hex(oidgen.oid)
# await ws_api_client.connect()
# await ws_api_client.place_order(
#     id=oid,
#     orders=[
#         {
#             "a": 4,
#             "b": True,
#             "p": "4500",
#             "s": "0.003",
#             "r": False,
#             "t": {
#                 "limit": {
#                     "tif": "Gtc"
#                 }
#             },
#             "c": oid,
#         }
#     ]
# )
# await ws_api_client.cancel_order(
#     id=UUID4().value, cancels=[{"a": 4, "o": 38086199157}]
# )
# await ws_api_client.cancel_orders_by_cloid(
#     id="0x0000000000000000f3f0b3863b5d5b86",
#     cancels=[{"asset": 4, "cloid": "0x0000000000000000f3f0b3863b5d5b86"}],
# )
# await task_manager.wait()


# place order success
# {
#     "channel": "post",
#     "data": {
#         "id": 1,
#         "response": {
#             "type": "action",
#             "payload": {
#                 "status": "ok",
#                 "response": {"type": "cancel", "data": {"statuses": ["success"]}},
#             },
#         },
#     },
# }
# # cancel order success
# {
#     "channel": "post",
#     "data": {
#         "id": 1,
#         "response": {
#             "type": "action",
#             "payload": {
#                 "status": "ok",
#                 "response": {
#                     "type": "order",
#                     "data": {
#                         "statuses": [
#                             {"error": "Order must have minimum value of $10. asset=4"}
#                         ]
#                     },
#                 },
#             },
#         },
#     },
# }
# # place order failed
# {
#     "channel": "post",
#     "data": {
#         "id": 1,
#         "response": {
#             "type": "action",
#             "payload": {
#                 "status": "ok",
#                 "response": {
#                     "type": "order",
#                     "data": {
#                         "statuses": [
#                             {"error": "Order must have minimum value of $10. asset=4"}
#                         ]
#                     },
#                 },
#             },
#         },
#     },
# }
# # place order success, you only need to get oid
# {
#     "channel": "post",
#     "data": {
#         "id": 1,
#         "response": {
#             "type": "action",
#             "payload": {
#                 "status": "ok",
#                 "response": {
#                     "type": "order",
#                     "data": {
#                         "statuses": [
#                             {
#                                 "filled": {
#                                     "totalSz": "0.003",
#                                     "avgPx": "4432.9",
#                                     "oid": 38086199157,
#                                 }
#                             }
#                         ]
#                     },
#                 },
#             },
#         },
#     },
# }
# # cancel order failed
# {
#     "channel": "post",
#     "data": {
#         "id": 1,
#         "response": {
#             "type": "action",
#             "payload": {
#                 "status": "ok",
#                 "response": {
#                     "type": "cancel",
#                     "data": {
#                         "statuses": [
#                             {
#                                 "error": "Order was never placed, already canceled, or filled. asset=4"
#                             }
#                         ]
#                     },
#                 },
#             },
#         },
#     },
# }


# if __name__ == "__main__":
#     asyncio.run(main())
