from datetime import timedelta
import httpx
import msgspec
from typing import Dict, Any, List
from urllib.parse import urlencode, urljoin

from throttled import Throttled, rate_limiter

from nexustrader.base.api_client import ApiClient
from nexustrader.core.nautilius_core import LiveClock, Logger
from nexustrader.exchange.hyperliquid.constants import HyperLiquidAccountType
from nexustrader.exchange.hyperliquid.exchange import HyperLiquidExchangeManager
from nexustrader.exchange.hyperliquid.schema import (
    HyperLiquidActiveAssetData,
    HyperLiquidOrderResponse,
    HyperLiquidCancelResponse,
    HyperLiquidSpotMeta,
    HyperLiquidUserOrder,
    HyperLiquidUserPerpsSummary,
    HyperLiquidMeta,
    HyperLiquidKline,
    HyperLiquidTrade,
    HyperLiquidOrderBook,
    HyperLiquidTicker,
    HyperLiquidUserSpotSummary,
)
from nexustrader.exchange.hyperliquid.error import HyperLiquidHttpError


class HyperLiquidRateLimiter:
    """Rate limiter for Hyperliquid API"""

    def __init__(self, enable_rate_limit: bool = True):
        self._throttled: [str, Throttled] = {
            "/exchange": Throttled(
                quota=rate_limiter.per_duration(timedelta(seconds=60), limit=1200),
                timeout=10 if enable_rate_limit else -1,
            ),
        }

    def __call__(self, endpoint: str) -> Throttled:
        return self._throttled[endpoint]


class HyperLiquidRateLimiterSync:
    """Synchronous rate limiter for Hyperliquid API"""

    def __init__(self, enable_rate_limit: bool = True):
        self._throttled: [str, Throttled] = {
            "/info": Throttled(
                quota=rate_limiter.per_duration(timedelta(seconds=60), limit=1200),
                timeout=10 if enable_rate_limit else -1,
            ),
        }

    def __call__(self, endpoint: str) -> Throttled:
        return self._throttled[endpoint]


class HyperLiquidApiClient(ApiClient):
    """REST API client for Hyperliquid exchange"""

    _limiter: HyperLiquidRateLimiter
    _limiter_sync: HyperLiquidRateLimiterSync

    def __init__(
        self,
        api_key: str = None,
        secret: str = None,
        exchange: HyperLiquidExchangeManager = None,
        timeout: int = 10,
        testnet: bool = False,
        enable_rate_limit: bool = True,
    ):
        super().__init__(
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
        self._base_url = self._account_type.rest_url
        self._log = Logger(name=type(self).__name__)
        self._clock = LiveClock()
        self._exchange = exchange

        self._headers = {
            "Content-Type": "application/json",
            # "User-Agent": "NexusTrader/1.0",
        }

        # Decoders for different response types
        self._msg_decoder = msgspec.json.Decoder()
        self._msg_encoder = msgspec.json.Encoder()
        self._order_response_decoder = msgspec.json.Decoder(HyperLiquidOrderResponse)
        self._cancel_response_decoder = msgspec.json.Decoder(HyperLiquidCancelResponse)
        self._user_perps_summary_decoder = msgspec.json.Decoder(HyperLiquidUserPerpsSummary)
        self._user_spot_summary_decoder = msgspec.json.Decoder(HyperLiquidUserSpotSummary)
        self._user_active_assets_decoder = msgspec.json.Decoder(HyperLiquidActiveAssetData)
        self._meta_decoder = msgspec.json.Decoder(HyperLiquidMeta)
        self._kline_decoder = msgspec.json.Decoder(list[HyperLiquidKline])
        self._trade_decoder = msgspec.json.Decoder(HyperLiquidTrade)
        self._orderbook_decoder = msgspec.json.Decoder(HyperLiquidOrderBook)
        self._ticker_decoder = msgspec.json.Decoder(HyperLiquidTicker)
        self._user_order_decoder = msgspec.json.Decoder(list[HyperLiquidUserOrder])
        self._spot_meta_decoder = msgspec.json.Decoder(HyperLiquidSpotMeta)

    def _get_rate_limit_cost(self, cost: int = 1) -> int:
        """Get rate limit cost for an operation"""
        return cost

    def _fetch_sync(
        self,
        method: str,
        base_url: str,
        endpoint: str,
        payload: Dict[str, Any] = None,
        signed: bool = False,
    ) -> bytes:
        """Synchronous HTTP request"""
        self._init_sync_session()

        url = urljoin(base_url, endpoint)
        payload = payload or {}

        if method == "GET":
            if payload:
                url = f"{url}?{urlencode(payload)}"
            data = None
        else:
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
        payload: Dict[str, Any] = None,
    ) -> bytes:
        """Asynchronous HTTP request"""
        self._init_session()

        url = urljoin(base_url, endpoint)
        payload = payload or {}

        if method == "GET":
            if payload:
                url = f"{url}?{urlencode(payload)}"
            data = None
        else:
            data = msgspec.json.encode(payload)

        self._log.debug(f"Request: {method} {url}")

        try:
            response = await self._session.request(
                method=method,
                url=url,
                headers=self._headers,
                data=data,
            )
            raw = await response.read()

            if response.status >= 400:
                raise HyperLiquidHttpError(
                    status_code=response.status,
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

    def get_meta(self) -> HyperLiquidMeta:
        """Get market metadata"""
        endpoint = "/info"
        payload = {"type": "meta"}

        cost = self._get_rate_limit_cost(1)
        self._limiter_sync("public").limit(key=endpoint, cost=cost)
        raw = self._fetch_sync("POST", self._base_url, endpoint, payload, signed=False)
        return self._meta_decoder.decode(raw)

    def get_spot_meta(self) -> HyperLiquidSpotMeta:
        """Get spot market metadata"""
        endpoint = "/info"
        payload = {"type": "spotMeta"}

        cost = self._get_rate_limit_cost(1)
        self._limiter_sync(endpoint).limit(key=endpoint, cost=cost)
        raw = self._fetch_sync("POST", self._base_url, endpoint, payload, signed=False)
        return self._spot_meta_decoder.decode(raw)

    def get_user_perps_summary(self, user: str) -> HyperLiquidUserPerpsSummary:
        """Get user perps summary"""
        endpoint = "/info"
        payload = {"type": "clearinghouseState", "user": user}

        cost = self._get_rate_limit_cost(1)
        self._limiter_sync(endpoint).limit(key=endpoint, cost=cost)
        raw = self._fetch_sync("POST", self._base_url, endpoint, payload, signed=False)
        return self._user_perps_summary_decoder.decode(raw)

    def get_user_spot_summary(self, user: str) -> HyperLiquidUserPerpsSummary:
        """Get user spot summary"""
        endpoint = "/info"
        payload = {"type": "spotClearinghouseState", "user": user}

        cost = self._get_rate_limit_cost(1)
        self._limiter_sync(endpoint).limit(key=endpoint, cost=cost)
        raw = self._fetch_sync("POST", self._base_url, endpoint, payload, signed=False)
        return self._user_spot_summary_decoder.decode(raw)

    def get_user_active_assets(self, user: str, coin: str) -> List[Dict[str, Any]]:
        """Get user fills"""
        endpoint = "/info"
        payload = {"type": "activeAssetData", "user": user, "coin": coin}

        cost = self._get_rate_limit_cost(1)
        self._limiter_sync(endpoint).limit(key=endpoint, cost=cost)
        raw = self._fetch_sync("POST", self._base_url, endpoint, payload, signed=False)
        return self._user_active_assets_decoder.decode(raw)

    
    def get_open_orders(self, user: str, dex: str = "") -> List[Dict[str, Any]]:
        """Get open orders for a user"""
        endpoint = "/info"
        payload = {"type": "openOrders", "user": user, "dex": dex}

        cost = self._get_rate_limit_cost(1)
        self._limiter_sync(endpoint).limit(key=endpoint, cost=cost)
        raw = self._fetch_sync("POST", self._base_url, endpoint, payload, signed=False)
        return self._user_order_decoder.decode(raw)

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

        cost = self._get_rate_limit_cost(1)
        self._limiter_sync(endpoint).limit(key=endpoint, cost=cost)
        raw = self._fetch_sync("POST", self._base_url, endpoint, payload, signed=False)
        return self._kline_decoder.decode(raw)

    def get_trades(self, coin: str, limit: int = 100) -> List[HyperLiquidTrade]:
        """Get recent trades"""
        endpoint = "/info"
        payload = {"type": "recentTrades", "coin": coin, "limit": limit}

        cost = self._get_rate_limit_cost(1)
        self._limiter_sync("public").limit(key=endpoint, cost=cost)
        raw = self._fetch_sync("POST", self._base_url, endpoint, payload, signed=False)
        return self._msg_decoder.decode(raw)

    def get_orderbook(self, coin: str) -> HyperLiquidOrderBook:
        """Get order book"""
        endpoint = "/info"
        payload = {"type": "orderBook", "coin": coin}

        cost = self._get_rate_limit_cost(1)
        self._limiter_sync("public").limit(key=endpoint, cost=cost)
        raw = self._fetch_sync("POST", self._base_url, endpoint, payload, signed=False)
        return self._orderbook_decoder.decode(raw)

    # Trading Endpoints

    async def place_order(
        self,
        user: str,
        asset: int,
        is_buy: bool,
        sz: str,
        limit_px: str,
        reduce_only: bool = False,
        order_type: str = "Limit",
    ) -> HyperLiquidOrderResponse:
        """
        Place an order

        request body:
        {
            "action": {
                "type": "order",
                "orders": [
                    {
                        "a": 4,
                        "b": true,
                        "p": "1000",
                        "s": "0.5",
                        "r": false,
                        "t": {
                            "limit": {
                                "tif": "Gtc"
                            }
                        }
                    }
                ],
                "grouping": "na"
            },
            "nonce": 1753107403341,
            "signature": {
                "r": "0x77b9d39dedf4e351047cab8d6ba4b73d3315d77c27701304bcd11d6e83a3a48a",
                "s": "0x59ece0c1e9c554eb479a19bccfedc04c4316c30c2a043082105a759374ad2c7c",
                "v": 27
            },
            "vaultAddress": null,
            "expiresAfter": null
        }

        """
        endpoint = "/exchange"

        action = {
            "type": "order",
            "orders": [
                {
                    "a": asset,  # asset id or symbol
                    "b": is_buy,  # buy (True) or sell (False)
                    "p": limit_px,  # price as string
                    "s": sz,  # size as string
                    "r": reduce_only,  # reduce only
                    "t": {
                        order_type.lower(): {
                            "tif": "Gtc"  # Time in force, hardcoded as Gtc for now
                        }
                    },
                }
            ],
            "grouping": "na",
        }

        nonce = self._clock.timestamp_ms()
        signature = self._exchange.api.sign_l1_action(action, nonce)
        payload = {
            "action": action,
            "nonce": nonce,
            "signature": signature,
            "vaultAddress": None,
            "expiresAfter": None,
        }
        cost = self._get_rate_limit_cost(1)
        self._limiter(endpoint).limit(key=endpoint, cost=cost)
        raw = await self._fetch("POST", self._base_url, endpoint, payload)
        return self._order_response_decoder.decode(raw)

    async def cancel_order(self, asset: int, oid: int) -> HyperLiquidCancelResponse:
        """Cancel an order"""
        endpoint = "/exchange"

        action = {
            "type": "cancel",
            "cancels": [
                {
                    "a": asset,
                    "o": oid,
                }
            ],
        }
        nonce = self._clock.timestamp_ms()
        signature = self._exchange.api.sign_l1_action(action, nonce)
        payload = {
            "action": action,
            "nonce": nonce,
            "signature": signature,
        }

        cost = self._get_rate_limit_cost(1)
        self._limiter(endpoint).limit(key=endpoint, cost=cost)
        raw = await self._fetch("POST", self._base_url, endpoint, payload)
        return self._cancel_response_decoder.decode(raw)

    async def cancel_all_orders(
        self, user: str, coin: str
    ) -> HyperLiquidCancelResponse:
        """Cancel all orders for a coin"""
        pass

    async def close_position(
        self, user: str, coin: str, sz: str
    ) -> HyperLiquidOrderResponse:
        """Close a position"""
        pass


if __name__ == "__main__":
    pass
