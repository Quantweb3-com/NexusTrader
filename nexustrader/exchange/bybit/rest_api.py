import hmac
import hashlib
import httpx
import aiohttp
import asyncio
import msgspec
from typing import Any, Dict, List
from urllib.parse import urljoin, urlencode
from decimal import Decimal
from nexustrader.base import ApiClient
from nexustrader.exchange.bybit.constants import (
    BybitBaseUrl,
    BybitRateLimiter,
    BybitRateLimiterSync,
)
from nexustrader.exchange.bybit.error import BybitError
from nexustrader.core.nautilius_core import hmac_signature
from nexustrader.exchange.bybit.schema import (
    BybitResponse,
    BybitOrderResponse,
    BybitPositionResponse,
    BybitOrderHistoryResponse,
    BybitOpenOrdersResponse,
    BybitWalletBalanceResponse,
    BybitKlineResponse,
    BybitIndexKlineResponse,
    BybitBatchOrderResponse,
)


class BybitApiClient(ApiClient):
    _limiter: BybitRateLimiter
    _limiter_sync: BybitRateLimiterSync

    def __init__(
        self,
        api_key: str = None,
        secret: str = None,
        timeout: int = 10,
        testnet: bool = False,
        enable_rate_limit: bool = True,
    ):
        """
        ### Testnet:
        `https://api-testnet.bybit.com`

        ### Mainnet:
        (both endpoints are available):
        `https://api.bybit.com`
        `https://api.bytick.com`

        ### Important:
        Netherland users: use `https://api.bybit.nl` for mainnet
        Hong Kong users: use `https://api.byhkbit.com` for mainnet
        Turkey users: use `https://api.bybit-tr.com` for mainnet
        Kazakhstan users: use `https://api.bybit.kz` for mainnet
        """

        super().__init__(
            api_key=api_key,
            secret=secret,
            timeout=timeout,
            enable_rate_limit=enable_rate_limit,
            rate_limiter=BybitRateLimiter(),
            rate_limiter_sync=BybitRateLimiterSync(),
        )
        self._recv_window = 5000

        if testnet:
            self._base_url = BybitBaseUrl.TESTNET.base_url
        else:
            self._base_url = BybitBaseUrl.MAINNET_1.base_url

        self._headers = {
            "Content-Type": "application/json",
            "User-Agent": "TradingBot/1.0",
        }

        if api_key:
            self._headers["X-BAPI-API-KEY"] = api_key

        self._msg_decoder = msgspec.json.Decoder()
        self._msg_encoder = msgspec.json.Encoder()
        self._response_decoder = msgspec.json.Decoder(BybitResponse)
        self._order_response_decoder = msgspec.json.Decoder(BybitOrderResponse)
        self._position_response_decoder = msgspec.json.Decoder(BybitPositionResponse)
        self._order_history_response_decoder = msgspec.json.Decoder(
            BybitOrderHistoryResponse
        )
        self._open_orders_response_decoder = msgspec.json.Decoder(
            BybitOpenOrdersResponse
        )
        self._wallet_balance_response_decoder = msgspec.json.Decoder(
            BybitWalletBalanceResponse
        )
        self._kline_response_decoder = msgspec.json.Decoder(BybitKlineResponse)
        self._index_kline_response_decoder = msgspec.json.Decoder(
            BybitIndexKlineResponse
        )
        self._batch_order_response_decoder = msgspec.json.Decoder(
            BybitBatchOrderResponse
        )

    def _generate_signature(self, payload: str) -> List[str]:
        timestamp = str(self._clock.timestamp_ms())

        param = str(timestamp) + self._api_key + str(self._recv_window) + payload
        hash = hmac.new(
            bytes(self._secret, "utf-8"), param.encode("utf-8"), hashlib.sha256
        )
        signature = hash.hexdigest()
        return [signature, timestamp]

    def _generate_signature_v2(self, payload: str) -> List[str]:
        timestamp = str(self._clock.timestamp_ms())
        param = f"{timestamp}{self._api_key}{self._recv_window}{payload}"
        signature = hmac_signature(self._secret, param)  # return hex digest string
        return [signature, timestamp]

    async def _fetch(
        self,
        method: str,
        base_url: str,
        endpoint: str,
        payload: Dict[str, Any] = None,
        signed: bool = False,
    ):
        self._init_session()

        url = urljoin(base_url, endpoint)
        payload = payload or {}

        payload_str = (
            urlencode(payload)
            if method == "GET"
            else self._msg_encoder.encode(payload).decode("utf-8")
        )

        headers = self._headers
        if signed:
            signature, timestamp = self._generate_signature_v2(payload_str)
            headers = {
                **headers,
                "X-BAPI-TIMESTAMP": timestamp,
                "X-BAPI-SIGN": signature,
                "X-BAPI-RECV-WINDOW": str(self._recv_window),
            }

        if method == "GET":
            url += f"?{payload_str}"
            payload_str = None

        try:
            self._log.debug(f"Request: {url} {payload_str}")
            response = await self._session.request(
                method=method,
                url=url,
                headers=headers,
                data=payload_str,
            )
            raw = await response.read()
            if response.status >= 400:
                raise BybitError(
                    code=response.status,
                    message=self._msg_decoder.decode(raw) if raw else None,
                )
            bybit_response: BybitResponse = self._response_decoder.decode(raw)
            if bybit_response.retCode == 0:
                return raw
            else:
                raise BybitError(
                    code=bybit_response.retCode,
                    message=bybit_response.retMsg,
                )
        except aiohttp.ClientError as e:
            self._log.error(f"Client Error {method} Url: {url} {e}")
            raise
        except asyncio.TimeoutError:
            self._log.error(f"Timeout {method} Url: {url}")
            raise
        except Exception as e:
            self._log.error(f"Error {method} Url: {url} {e}")
            raise

    def _fetch_sync(
        self,
        method: str,
        base_url: str,
        endpoint: str,
        payload: Dict[str, Any] = None,
        signed: bool = False,
    ):
        self._init_sync_session()

        url = urljoin(base_url, endpoint)
        payload = payload or {}

        payload_str = (
            urlencode(payload)
            if method == "GET"
            else self._msg_encoder.encode(payload).decode("utf-8")
        )

        headers = self._headers
        if signed:
            signature, timestamp = self._generate_signature_v2(payload_str)
            headers = {
                **headers,
                "X-BAPI-TIMESTAMP": timestamp,
                "X-BAPI-SIGN": signature,
                "X-BAPI-RECV-WINDOW": str(self._recv_window),
            }

        if method == "GET":
            url += f"?{payload_str}"
            payload_str = None

        try:
            self._log.debug(f"Request: {url} {payload_str}")
            response = self._sync_session.request(
                method=method,
                url=url,
                headers=headers,
                data=payload_str,
            )
            raw = response.content
            if response.status_code >= 400:
                raise BybitError(
                    code=response.status_code,
                    message=self._msg_decoder.decode(raw) if raw else None,
                )
            bybit_response: BybitResponse = self._response_decoder.decode(raw)
            if bybit_response.retCode == 0:
                return raw
            else:
                raise BybitError(
                    code=bybit_response.retCode,
                    message=bybit_response.retMsg,
                )
        except httpx.TimeoutException as e:
            self._log.error(f"Timeout {method} Url: {url} - {e}")
            raise
        except httpx.ConnectError as e:
            self._log.error(f"Connection Error {method} Url: {url} - {e}")
            raise
        except httpx.HTTPStatusError as e:
            self._log.error(f"HTTP Error {method} Url: {url} - {e}")
            raise
        except httpx.RequestError as e:
            self._log.error(f"Request Error {method} Url: {url} - {e}")
            raise
        except Exception as e:
            self._log.error(f"Error {method} Url: {url} - {e}")
            raise

    async def post_v5_order_create(
        self,
        category: str,
        symbol: str,
        side: str,
        order_type: str,
        qty: Decimal,
        **kwargs,
    ) -> BybitOrderResponse:
        """
        https://bybit-exchange.github.io/docs/v5/order/create-order
        """
        endpoint = "/v5/order/create"
        payload = {
            "category": category,
            "symbol": symbol,
            "side": side,
            "orderType": order_type,
            "qty": str(qty),
            **kwargs,
        }
        if category == "spot":
            cost = 1
        else:
            cost = 2
        cost = self._get_rate_limit_cost(cost=cost)
        await self._limiter("trade").limit(key=endpoint, cost=cost)
        raw = await self._fetch("POST", self._base_url, endpoint, payload, signed=True)
        return self._order_response_decoder.decode(raw)

    async def post_v5_order_cancel(
        self, category: str, symbol: str, **kwargs
    ) -> BybitOrderResponse:
        """
        https://bybit-exchange.github.io/docs/v5/order/cancel-order
        """
        endpoint = "/v5/order/cancel"
        payload = {
            "category": category,
            "symbol": symbol,
            **kwargs,
        }
        if category == "spot":
            cost = 1
        else:
            cost = 2
        cost = self._get_rate_limit_cost(cost=cost)
        await self._limiter("trade").limit(key=endpoint, cost=cost)
        raw = await self._fetch("POST", self._base_url, endpoint, payload, signed=True)
        return self._order_response_decoder.decode(raw)

    async def get_v5_position_list(
        self, category: str, **kwargs
    ) -> BybitPositionResponse:
        endpoint = "/v5/position/list"
        payload = {
            "category": category,
            **kwargs,
        }
        cost = self._get_rate_limit_cost(cost=1)
        await self._limiter("position").limit(key=endpoint, cost=cost)
        payload = {k: v for k, v in payload.items() if v is not None}
        raw = await self._fetch("GET", self._base_url, endpoint, payload, signed=True)
        return self._position_response_decoder.decode(raw)

    async def get_v5_order_realtime(self, category: str, **kwargs):
        """
        https://bybit-exchange.github.io/docs/v5/order/open-order
        """
        endpoint = "/v5/order/realtime"
        payload = {
            "category": category,
            **kwargs,
        }
        raw = await self._fetch("GET", self._base_url, endpoint, payload, signed=True)
        return self._open_orders_response_decoder.decode(raw)

    async def get_v5_order_history(self, category: str, **kwargs):
        """
        https://bybit-exchange.github.io/docs/v5/order/order-list
        """
        endpoint = "/v5/order/history"
        payload = {
            "category": category,
            **kwargs,
        }
        raw = await self._fetch("GET", self._base_url, endpoint, payload, signed=True)
        return self._order_history_response_decoder.decode(raw)

    async def get_v5_account_wallet_balance(
        self, account_type: str, **kwargs
    ) -> BybitWalletBalanceResponse:
        endpoint = "/v5/account/wallet-balance"
        payload = {
            "accountType": account_type,
            **kwargs,
        }
        cost = self._get_rate_limit_cost(cost=1)
        await self._limiter("account").limit(key=endpoint, cost=cost)
        raw = await self._fetch("GET", self._base_url, endpoint, payload, signed=True)
        return self._wallet_balance_response_decoder.decode(raw)

    async def post_v5_order_amend(
        self,
        category: str,
        symbol: str,
        orderId: str | None = None,
        orderLinkId: str | None = None,
        orderIv: str | None = None,
        triggerPrice: str | None = None,
        qty: str | None = None,
        price: str | None = None,
        tpslMode: str | None = None,
        takeProfit: str | None = None,
        stopLoss: str | None = None,
        tpTriggerBy: str | None = None,
        slTriggerBy: str | None = None,
        triggerBy: str | None = None,
        tpLimitPrice: str | None = None,
        slLimitPrice: str | None = None,
    ):
        """
        https://bybit-exchange.github.io/docs/v5/order/amend-order
        """
        endpoint = "/v5/order/amend"
        payload = {
            "category": category,
            "symbol": symbol,
            "orderId": orderId,
            "orderLinkId": orderLinkId,
            "orderIv": orderIv,
            "triggerPrice": triggerPrice,
            "qty": qty,
            "price": price,
            "tpslMode": tpslMode,
            "takeProfit": takeProfit,
            "stopLoss": stopLoss,
            "tpTriggerBy": tpTriggerBy,
            "slTriggerBy": slTriggerBy,
            "triggerBy": triggerBy,
            "tpLimitPrice": tpLimitPrice,
            "slLimitPrice": slLimitPrice,
        }
        cost = self._get_rate_limit_cost(cost=2)
        await self._limiter("trade").limit(key=endpoint, cost=cost)
        payload = {k: v for k, v in payload.items() if v is not None}
        raw = await self._fetch("POST", self._base_url, endpoint, payload, signed=True)
        return self._order_response_decoder.decode(raw)

    async def post_v5_order_cancel_all(
        self,
        category: str,
        symbol: str | None = None,
        baseCoin: str | None = None,
        settleCoin: str | None = None,
        orderFilter: str | None = None,
        stopOrderType: str | None = None,
    ):
        endpoint = "/v5/order/cancel-all"
        payload = {
            "category": category,
            "symbol": symbol,
            "baseCoin": baseCoin,
            "settleCoin": settleCoin,
            "orderFilter": orderFilter,
            "stopOrderType": stopOrderType,
        }
        if category == "spot":
            cost = 1
        else:
            cost = 2
        cost = self._get_rate_limit_cost(cost=cost)
        await self._limiter("trade").limit(key=endpoint, cost=cost)
        payload = {k: v for k, v in payload.items() if v is not None}
        raw = await self._fetch("POST", self._base_url, endpoint, payload, signed=True)
        return self._msg_decoder.decode(raw)

    def get_v5_market_kline(
        self,
        category: str,
        symbol: str,
        interval: str,
        start: int | None = None,
        end: int | None = None,
        limit: int | None = None,
    ):
        endpoint = "/v5/market/kline"
        payload = {
            "category": category,
            "symbol": symbol,
            "interval": interval,
            "start": start,
            "end": end,
            "limit": limit,
        }
        cost = self._get_rate_limit_cost(cost=1)
        self._limiter_sync("public").limit(key=endpoint, cost=cost)
        payload = {k: v for k, v in payload.items() if v is not None}
        raw = self._fetch_sync("GET", self._base_url, endpoint, payload, signed=False)
        return self._kline_response_decoder.decode(raw)

    def get_v5_market_index_price_kline(
        self,
        category: str,
        symbol: str,
        interval: str,
        start: int | None = None,
        end: int | None = None,
        limit: int | None = None,
    ):
        endpoint = "/v5/market/index-price-kline"
        payload = {
            "category": category,
            "symbol": symbol,
            "interval": interval,
            "start": start,
            "end": end,
            "limit": limit,
        }
        cost = self._get_rate_limit_cost(cost=1)
        self._limiter_sync("public").limit(key=endpoint, cost=cost)
        payload = {k: v for k, v in payload.items() if v is not None}
        raw = self._fetch_sync("GET", self._base_url, endpoint, payload, signed=False)
        return self._index_kline_response_decoder.decode(raw)

    async def post_v5_order_create_batch(
        self,
        category: str,
        request: List[Dict[str, Any]],
    ) -> BybitBatchOrderResponse:
        """
        Place multiple orders in a single request
        https://bybit-exchange.github.io/docs/v5/order/batch-place

        Maximum orders per request:
        - Option: 20 orders
        - Inverse: 20 orders
        - Linear: 20 orders
        - Spot: 10 orders
        """
        endpoint = "/v5/order/create-batch"
        payload = {
            "category": category,
            "request": request,
        }

        # Rate limit cost based on category
        if category == "spot":
            cost = 1
        else:
            cost = 2
        cost = self._get_rate_limit_cost(cost=cost)
        await self._limiter("trade").limit(key=endpoint, cost=cost)

        raw = await self._fetch("POST", self._base_url, endpoint, payload, signed=True)
        return self._batch_order_response_decoder.decode(raw)
