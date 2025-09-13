import httpx
import msgspec
import eth_account
from eth_account.signers.local import LocalAccount
from eth_account.messages import encode_typed_data
from typing import Dict, Any, List, Literal
from urllib.parse import urljoin
from Crypto.Hash import keccak

from nexustrader.base.api_client import ApiClient
from nexustrader.exchange.hyperliquid.constants import (
    HyperLiquidAccountType,
    HyperLiquidRateLimiter,
    HyperLiquidRateLimiterSync,
    HyperLiquidOrderRequest,
    HyperLiquidOrderCancelRequest,
    HyperLiquidCloidCancelRequest,
)
from nexustrader.exchange.hyperliquid.schema import (
    HyperLiquidOrderResponse,
    HyperLiquidCancelResponse,
    HyperLiquidUserOrder,
    HyperLiquidUserPerpsSummary,
    HyperLiquidKline,
    HyperLiquidTrade,
    HyperLiquidOrderBook,
    HyperLiquidTicker,
    HyperLiquidUserSpotSummary,
)
from nexustrader.exchange.hyperliquid.error import HyperLiquidHttpError
from nexustrader.core.nautilius_core import LiveClock


class HyperLiquidApiClient(ApiClient):
    """REST API client for Hyperliquid exchange"""

    _limiter: HyperLiquidRateLimiter
    _limiter_sync: HyperLiquidRateLimiterSync

    def __init__(
        self,
        clock: LiveClock,
        api_key: str = None,
        secret: str = None,
        timeout: int = 10,
        testnet: bool = False,
        enable_rate_limit: bool = True,
    ):
        super().__init__(
            clock=clock,
            api_key=api_key,
            secret=secret,
            timeout=timeout,
            rate_limiter=HyperLiquidRateLimiter(enable_rate_limit),
            rate_limiter_sync=HyperLiquidRateLimiterSync(enable_rate_limit),
        )

        self._account_type = (
            HyperLiquidAccountType.TESTNET
            if testnet
            else HyperLiquidAccountType.MAINNET
        )
        if secret:
            self._eth_account: LocalAccount = eth_account.Account.from_key(secret)
        self._base_url = self._account_type.rest_url
        self._testnet = testnet
        self._headers = {
            "Content-Type": "application/json",
            # "User-Agent": "NexusTrader/1.0",
        }

        # Decoders for different response types
        self._msg_decoder = msgspec.json.Decoder()
        self._msg_encoder = msgspec.json.Encoder()
        self._order_response_decoder = msgspec.json.Decoder(HyperLiquidOrderResponse)
        self._cancel_response_decoder = msgspec.json.Decoder(HyperLiquidCancelResponse)
        self._user_perps_summary_decoder = msgspec.json.Decoder(
            HyperLiquidUserPerpsSummary
        )
        self._user_spot_summary_decoder = msgspec.json.Decoder(
            HyperLiquidUserSpotSummary
        )

        self._kline_decoder = msgspec.json.Decoder(list[HyperLiquidKline])
        self._trade_decoder = msgspec.json.Decoder(HyperLiquidTrade)
        self._orderbook_decoder = msgspec.json.Decoder(HyperLiquidOrderBook)
        self._ticker_decoder = msgspec.json.Decoder(HyperLiquidTicker)
        self._user_order_decoder = msgspec.json.Decoder(list[HyperLiquidUserOrder])

    def _get_rate_limit_cost(self, length: int, cost: int = 1) -> int:
        """Get rate limit cost for an operation

        Please refer to https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/rate-limits-and-user-limits
        """
        return cost + length // 40

    def _fetch_sync(
        self,
        method: str,
        base_url: str,
        endpoint: str,
        payload: Dict[str, Any],
    ) -> bytes:
        """Synchronous HTTP request"""
        self._init_sync_session()

        url = urljoin(base_url, endpoint)
        data = msgspec.json.encode(payload)

        self._log.debug(f"Request: {method} {url}")

        try:
            response = self._sync_session.request(
                method=method,
                url=url,
                headers=self._headers,
                data=data,
            )
            raw = response.content

            if response.status_code >= 400:
                raise HyperLiquidHttpError(
                    status_code=response.status_code,
                    message=raw.decode() if isinstance(raw, bytes) else str(raw),
                    headers=dict(response.headers),
                )

            return raw
        except httpx.TimeoutException as e:
            self._log.error(f"Timeout {method} {url} {e}")
            raise
        except httpx.ConnectError as e:
            self._log.error(f"Connection Error {method} {url} {e}")
            raise
        except httpx.HTTPStatusError as e:
            self._log.error(f"HTTP Error {method} {url} {e}")
            raise
        except httpx.RequestError as e:
            self._log.error(f"Request Error {method} {url} {e}")
            raise
        except Exception as e:
            self._log.error(f"Error {method} {url} {e}")
            raise

    async def _fetch(
        self,
        method: str,
        base_url: str,
        endpoint: str,
        payload: Dict[str, Any],
    ) -> bytes:
        """Asynchronous HTTP request"""
        self._init_session()

        url = urljoin(base_url, endpoint)
        data = msgspec.json.encode(payload)

        self._log.debug(f"Request: {method} {url}")

        try:
            response = await self._session.request(
                method=method,
                url=url,
                headers=self._headers,
                data=data,
            )
            raw = response.content

            if response.status_code >= 400:
                raise HyperLiquidHttpError(
                    status_code=response.status_code,
                    message=raw.decode() if isinstance(raw, bytes) else str(raw),
                    headers=dict(response.headers),
                )

            return raw
        except httpx.TimeoutException as e:
            self._log.error(f"Timeout {method} {url} {e}")
            raise
        except httpx.ConnectError as e:
            self._log.error(f"Connection Error {method} {url} {e}")
            raise
        except httpx.HTTPStatusError as e:
            self._log.error(f"HTTP Error {method} {url} {e}")
            raise
        except httpx.RequestError as e:
            self._log.error(f"Request Error {method} {url} {e}")
            raise
        except Exception as e:
            self._log.error(f"Error {method} {url} {e}")
            raise

    # Market Data Endpoints
    def get_user_perps_summary(self) -> HyperLiquidUserPerpsSummary:
        """Get user perps summary"""
        endpoint = "/info"
        payload = {"type": "clearinghouseState", "user": self._api_key, "dex": ""}
        self._limiter_sync(endpoint).limit(key=endpoint, cost=2)
        raw = self._fetch_sync("POST", self._base_url, endpoint, payload)
        return self._user_perps_summary_decoder.decode(raw)

    def get_user_spot_summary(self) -> HyperLiquidUserSpotSummary:
        """Get user spot summary"""
        endpoint = "/info"
        payload = {"type": "spotClearinghouseState", "user": self._api_key}
        self._limiter_sync(endpoint).limit(key=endpoint, cost=2)
        raw = self._fetch_sync("POST", self._base_url, endpoint, payload)
        return self._user_spot_summary_decoder.decode(raw)

    def get_klines(
        self, coin: str, interval: str, startTime: int = None, endTime: int = None
    ) -> List[HyperLiquidKline]:
        """
        Get kline/candlestick data
        https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint#candle-snapshot
        """
        endpoint = "/info"
        req = {
            "coin": coin,
            "interval": interval,
        }
        if startTime is not None:
            req["startTime"] = startTime
        if endTime is not None:
            req["endTime"] = endTime
        payload = {"type": "candleSnapshot", "req": req}

        self._limiter_sync(endpoint).limit(key=endpoint, cost=20)
        raw = self._fetch_sync("POST", self._base_url, endpoint, payload)
        return self._kline_decoder.decode(raw)

    def _construct_phantom_agent(
        self, hash: bytes, is_testnet: bool = False
    ) -> Dict[str, Any]:
        return {"source": "b" if is_testnet else "a", "connectionId": hash}

    def _action_hash(
        self, action: Dict[str, Any], nonce: int, vaultAddress: str = None
    ) -> bytes:
        data = msgspec.msgpack.encode(action)
        data += nonce.to_bytes(8, "big")
        if vaultAddress is None:
            data += b"\x00"
        else:
            data += b"\x01"
            data += bytes.fromhex(
                vaultAddress[2:] if vaultAddress.startswith("0x") else vaultAddress
            )
        return keccak.new(digest_bits=256, data=data).digest()

    def _sign_l1_action(
        self, action: Dict[str, Any], nonce: int, vaultAddress: str = None
    ) -> bytes:
        hash = self._action_hash(action, nonce, vaultAddress)
        phantom_agent = self._construct_phantom_agent(hash, is_testnet=self._testnet)
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

    # Trading Endpoints
    async def place_orders(
        self,
        orders: List[HyperLiquidOrderRequest],
        grouping: Literal["na", "normalTpsl", "positionTpsl"] = "na",
    ) -> HyperLiquidOrderResponse:
        nounce = self._clock.timestamp_ms()
        orderAction = {
            "type": "order",
            "orders": orders,
            "grouping": grouping,
        }
        signature = self._sign_l1_action(orderAction, nounce, vaultAddress=None)
        cost = self._get_rate_limit_cost(length=len(orders), cost=1)
        await self._limiter("/exchange").limit(key="orders", cost=cost)
        res = await self._fetch(
            "POST",
            self._base_url,
            "/exchange",
            {
                "action": orderAction,
                "nonce": nounce,
                "signature": signature,
            },
        )
        order = self._order_response_decoder.decode(res)
        return order

    async def cancel_orders(
        self,
        cancels: List[HyperLiquidOrderCancelRequest],
    ):
        nounce = self._clock.timestamp_ms()
        orderAction = {
            "type": "cancel",
            "cancels": cancels,
        }
        signature = self._sign_l1_action(orderAction, nounce, vaultAddress=None)
        cost = self._get_rate_limit_cost(length=len(cancels), cost=1)
        await self._limiter("/exchange").limit(key="cancel", cost=cost)
        res = await self._fetch(
            "POST",
            self._base_url,
            "/exchange",
            {
                "action": orderAction,
                "nonce": nounce,
                "signature": signature,
            },
        )
        return self._cancel_response_decoder.decode(res)

    async def cancel_orders_by_cloid(
        self,
        cancels: List[HyperLiquidCloidCancelRequest],
    ):
        nounce = self._clock.timestamp_ms()
        orderAction = {
            "type": "cancelByCloid",
            "cancels": cancels,
        }
        signature = self._sign_l1_action(orderAction, nounce, vaultAddress=None)
        cost = self._get_rate_limit_cost(length=len(cancels), cost=1)
        await self._limiter("/exchange").limit(key="cancel", cost=cost)
        res = await self._fetch(
            "POST",
            self._base_url,
            "/exchange",
            {
                "action": orderAction,
                "nonce": nounce,
                "signature": signature,
            },
        )
        return self._cancel_response_decoder.decode(res)
