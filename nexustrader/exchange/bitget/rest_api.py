import msgspec
from typing import Any, Dict
from urllib.parse import urljoin, urlencode
import hmac
import hashlib
import base64
import time
import json
import aiohttp
import httpx
from nexustrader.base import ApiClient
from nexustrader.exchange.bitget.constants import (
    BitgetAccountType,
    BitgetRateLimiter,
    BitgetRateLimiterSync,
)

from nexustrader.exchange.bitget.schema import BitgetAccountAssetResponse
# from nexustrader.exchange.bitget.error import BitgetClientError, BitgetServerError
from nexustrader.core.nautilius_core import hmac_signature, LiveClock
from nexustrader.exchange.bitget.schema import (
    BitgetOrderHistoryResponse,
    BitgetOpenOrdersResponse,
    BitgetPositionListResponse,
    BitgetOrderCancelResponse,
    BitgetOrderPlaceResponse,
    BitgetAccountAssetResponse,
    BitgetOrderModifyResponse,
    BitgetResponse,
    BitgetBaseResponse,
    BitgetKlineResponse,
    BitgetIndexPriceKlineItem, 
    BitgetIndexPriceKlineResponse
)


class BitgetApiClient(ApiClient):
    _limiter: BitgetRateLimiter
    _limiter_sync: BitgetRateLimiterSync

    def __init__(
        self,
        clock: LiveClock,
        api_key: str | None = None,
        secret: str | None = None,
        passphrase: str | None = None,
        testnet: bool = False,
        timeout: int = 10,
        enable_rate_limit: bool = True,
    ):
        super().__init__(
            clock=clock,
            api_key=api_key,
            secret=secret,
            timeout=timeout,
            rate_limiter=BitgetRateLimiter(),
            rate_limiter_sync=BitgetRateLimiterSync(),
        )

        self._base_url = "https://api.bitget.com"
        self._passphrase = passphrase
        self._testnet = testnet

        self._headers = {
            "Content-Type": "application/json",
            "User-Agent": "NexusTrader/1.0",
        }

        if self._testnet:
            self._headers["PAPTRADING"] = "1"


        if api_key:
            self._headers["ACCESS-KEY"] = api_key

        self._recv_window = "5000"

        self._msg_decoder = msgspec.json.Decoder()
        self._msg_encoder = msgspec.json.Encoder()
        self._cancel_order_decoder = msgspec.json.Decoder(BitgetOrderCancelResponse)
        # 响应结构解码器（你后面可以继续添加对应的 schema）
        # self._market_response_decoder = msgspec.json.Decoder(BitgetMarketResponse)
        self._order_response_decoder = msgspec.json.Decoder(BitgetOrderPlaceResponse)
        # self._balance_response_decoder = msgspec.json.Decoder(BitgetBalanceResponse)
        self._position_list_decoder = msgspec.json.Decoder(BitgetPositionListResponse)
        self._open_orders_response_decoder = msgspec.json.Decoder(BitgetOpenOrdersResponse)
        self._order_history_response_decoder = msgspec.json.Decoder(BitgetOrderHistoryResponse)
        self._wallet_balance_response_decoder = msgspec.json.Decoder(BitgetAccountAssetResponse)
        self._order_modify_response_decoder = msgspec.json.Decoder(BitgetOrderModifyResponse)
        self._cancel_all_orders_decoder = msgspec.json.Decoder(BitgetBaseResponse)
        self._kline_response_decoder = msgspec.json.Decoder(BitgetKlineResponse)
        self._index_kline_response_decoder = msgspec.json.Decoder(BitgetIndexPriceKlineResponse)


    def _generate_signature(
        secret_key: str,
        timestamp: str,
        method: str,
        request_path: str,
        query_string: str = "",
        body: str = "",
    ) -> str:
        method = method.upper()
        
        if query_string:
            request_path = f"{request_path}?{query_string}"

        message = f"{timestamp}{method}{request_path}{body}"

        digest = hmac.new(
            secret_key.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256
        ).digest()

        signature = base64.b64encode(digest).decode()
        return signature

    def _fetch_sync(
        self,
        method: str,
        base_url: str,
        endpoint: str,
        payload: Dict[str, Any] = None,
        signed: bool = False,
    ) -> Any:
        self._init_sync_session()

        url = urljoin(base_url, endpoint)
        payload = payload or {}

        query = urlencode(payload) if method.upper() == "GET" else ""
        body = "" if method.upper() == "GET" else self._msg_encoder.encode(payload).decode("utf-8")

        timestamp = str(self._clock.timestamp_ms())

        headers = self._headers.copy()
        headers.update({
            "Content-Type": "application/json",
            "locale": "en-US",
        })

        if signed:
            signature = self._generate_signature(
                secret_key=self._secret,
                timestamp=timestamp,
                method=method,
                request_path=endpoint,
                query_string=query,
                body=body,
            )
            headers.update({
                "ACCESS-KEY": self._api_key,
                "ACCESS-SIGN": signature,
                "ACCESS-TIMESTAMP": timestamp,
                "ACCESS-PASSPHRASE": self._passphrase,
            })

        if query:
            url += f"?{query}"

        self._log.debug(f"Request: {method} {url} body={body}")

        try:
            response = self._sync_session.request(
                method=method,
                url=url,
                headers=headers,
                content=body if method.upper() != "GET" else None,
            )
            raw = response.content
            self.raise_error(raw, response.status_code, response.headers)
            return raw
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


    async def _fetch(
        self,
        method: str,
        base_url: str,
        endpoint: str,
        payload: Dict[str, Any] = None,
        signed: bool = False,
    ) -> Any:
        self._init_session()

        url = urljoin(base_url, endpoint)
        payload = payload or {}

        query = urlencode(payload) if method.upper() == "GET" else ""
        body = "" if method.upper() == "GET" else self._msg_encoder.encode(payload).decode("utf-8")

        timestamp = str(self._clock.timestamp_ms())

        headers = self._headers.copy()
        headers.update({
            "Content-Type": "application/json",
            "locale": "en-US",
        })

        if signed:
            signature = self._generate_signature(
                secret_key=self._secret,
                timestamp=timestamp,
                method=method,
                request_path=endpoint,
                query_string=query,
                body=body,
            )
            headers.update({
                "ACCESS-KEY": self._api_key,
                "ACCESS-SIGN": signature,
                "ACCESS-TIMESTAMP": timestamp,
                "ACCESS-PASSPHRASE": self._passphrase,
            })

        if query:
            url += f"?{query}"

        self._log.debug(f"Request: {method} {url} body={body}")

        try:
            response = await self._session.request(
                method=method,
                url=url,
                headers=headers,
                content=body if method.upper() != "GET" else None,  # content= 替代 data=
            )
            raw = response.content
            self.raise_error(raw, response.status_code, response.headers)
            return raw
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


    def raise_error(self, raw: bytes, status: int, headers: Dict[str, Any]):
        body = self._msg_decoder.decode(raw) if raw else None
        if 400 <= status < 500:
            raise BitgetClientError(status, body, headers)
        elif status >= 500:
            raise BitgetServerError(status, body, headers)



    def _get_base_url(self, account_type: BitgetAccountType) -> str:
        if account_type == BitgetAccountType.LIVE:
            return "https://api.bitget.com"
        elif account_type == BitgetAccountType.DEMO:
            return "https://api.bitget.com"  
        elif account_type in {
            BitgetAccountType.SPOT_MOCK,
            BitgetAccountType.LINEAR_MOCK,
            BitgetAccountType.INVERSE_MOCK,
        }:
            return "https://api.bitget.com"  

        raise ValueError(f"Unsupported BitgetAccountType: {account_type}")

    async def post_v2_mix_order_place(
        self,
        symbol: str,
        productType: str,
        side: str,
        orderType: str,
        size: str,
        price: str | None = None,
        marginCoin: str | None = None,
        clientOid: str | None = None,
        **kwargs,
    ):
        """
        Create Order

        https://www.bitget.com/api-doc/contract/trade/Place-Order
        """
        endpoint = "/api/v2/mix/order/placeOrder"

        payload = {
            "symbol": symbol,
            "productType": productType,
            "side": side,
            "orderType": orderType,
            "size": size,
            "price": price,
            "marginCoin": marginCoin,
            "clientOid": clientOid,
            **kwargs,
        }
        body_dict = {k: v for k, v in payload.items() if v is not None}

        cost = self._get_rate_limit_cost(2)
        await self._limiter("trade").limit(key=endpoint, cost=cost)

        raw = await self._fetch(method="POST",base_url=self._base_url,endpoint=endpoint,payload=body_dict,signed=True,   )

        return self._order_response_decoder.decode(raw)


    async def post_v2_mix_order_cancel(
        self,
        symbol: str,
        product_type: str,
        order_id: str | None = None,
        client_oid: str | None = None,
        margin_coin: str | None = None,
    ):
        """
        Bitget API:
        https://bitgetlimited.github.io/apidoc/en/mix/#cancel-order
        """
        endpoint = "/api/v2/mix/order/cancel-order"

        payload = {
            "symbol": symbol,
            "productType": product_type,
            "orderId": order_id,
            "clientOid": client_oid,
            "marginCoin": margin_coin,
        }

        payload = {k: v for k, v in payload.items() if v is not None}

        cost = self._get_rate_limit_cost(1)
        await self._limiter("trade").limit(key=endpoint, cost=cost)

        raw = await self._fetch("POST", self._base_url, endpoint, payload, signed=True)

        return self._cancel_order_decoder.decode(raw)


    async def get_v2_all_position(
        self,
        productType: str,
        marginCoin: str,
    ) -> BitgetPositionListResponse:
        """
        GET /api/v2/mix/position/all-position
        https://www.bitget.com/api-doc/contract/position/get-all-position
        """
        endpoint = "/api/v2/mix/position/all-position"

        payload = {
            "productType": productType,
            "marginCoin": marginCoin,
        }

        cost = self._get_rate_limit_cost(1)
        await self._limiter("position").limit(key=endpoint, cost=cost)

        raw = await self._fetch("GET", self._base_url, endpoint, payload, signed=True)

        return self._position_list_decoder.decode(raw)

    
    async def get_v2_mix_order_current(
        self,
        symbol: str,
        productType: str,
        **kwargs,
    ) -> BitgetOpenOrdersResponse:
        """
        https://www.bitget.com/api-doc/contract/trade/Get-Orders-Pending
        """
        endpoint = "/api/v2/mix/order/current"
        payload = {
            "symbol": symbol,
            "productType": productType,
            **kwargs,
        }
        cost = self._get_rate_limit_cost(cost=1)
        await self._limiter("trade").limit(key=endpoint, cost=cost)
        payload = {k: v for k, v in payload.items() if v is not None}
        raw = await self._fetch("GET", self._base_url, endpoint, payload, signed=True)
        return self._open_orders_response_decoder.decode(raw)

    async def get_v2_mix_order_history(
        self,
        productType: str,
        symbol: str | None = None,
        startTime: int | None = None,
        endTime: int | None = None,
        limit: int | None = None,
        idLessThan: str | None = None,
    ) -> BitgetOrderHistoryResponse:
        """
        https://www.bitget.com/api-doc/contract/trade/Get-Orders-History
        """
        endpoint = "/api/v2/mix/order/orders-history"
        payload = {
            "productType": productType,
            "symbol": symbol,
            "startTime": startTime,
            "endTime": endTime,
            "limit": limit,
            "idLessThan": idLessThan,
        }
        # 过滤掉为 None 的字段
        payload = {k: v for k, v in payload.items() if v is not None}

        raw = await self._fetch("GET", self._base_url, endpoint, payload, signed=True)
        return self._order_history_response_decoder.decode(raw)

    async def get_v2_spot_account_assets(
        self,
        coin: str | None = None,
        asset_type: str = "hold_only",
        **kwargs,
    ) -> BitgetAccountAssetResponse:
        """
        https://www.bitget.com/api-doc/spot/account/Get-Account-Assets
        """
        endpoint = "/api/v2/spot/account/assets"

        payload = {
            "coin": coin,
            "assetType": asset_type,
            **kwargs,
        }

        cost = self._get_rate_limit_cost(1)
        await self._limiter("account").limit(key=endpoint, cost=cost)

        raw = await self._fetch("GET", self._base_url, endpoint, payload, signed=True)

        return self._wallet_balance_response_decoder.decode(raw)

    async def post_v2_mix_order_modify(
        self,
        *,
        symbol: str,
        productType: str,
        newClientOid: str,
        orderId: str | None = None,
        clientOid: str | None = None,
        newSize: str | None = None,
        newPrice: str | None = None,
        presetTakeProfitPrice: str | None = None,
        presetStopLossPrice: str | None = None,
    ) -> BitgetOrderModifyResponse:
        """
        https://www.bitget.com/api-doc/contract/trade/Modify-Order
        POST /api/v2/mix/order/modify-order
        Modify Order | Bitget API :contentReference[oaicite:2]{index=2}
        """
        endpoint = "/api/v2/mix/order/modify-order"
        payload: dict[str, Any] = {
            "symbol": symbol,
            "productType": productType,
            "newClientOid": newClientOid,
        }
        if orderId is not None:
            payload["orderId"] = orderId
        elif clientOid is not None:
            payload["clientOid"] = clientOid
        else:
            raise ValueError("orderId or clientOid must be provided")

        if newSize is not None:
            payload["newSize"] = newSize
        if newPrice is not None:
            payload["newPrice"] = newPrice
        if presetTakeProfitPrice is not None:
            payload["presetTakeProfitPrice"] = presetTakeProfitPrice
        if presetStopLossPrice is not None:
            payload["presetStopLossPrice"] = presetStopLossPrice

        # 10 times/sec per UID :contentReference[oaicite:3]{index=3}
        await self._limiter("trade").limit(key=endpoint, cost=1)

        raw = await self._fetch(method="POST",base_url=self._base_url,endpoint=endpoint,payload=payload,signed=True)
        resp = msgspec.json.Decoder(BitgetResponse).decode(raw)
        return resp.data

    async def post_v2_mix_order_cancel_all(
        self,
        productType: str,
        symbol: str | None = None,
        marginCoin: str | None = None,
    ):
        """
        https://www.bitget.com/api-doc/contract/trade/Cancel-All-Orders
        """
        endpoint = "/api/v2/mix/order/cancel-all"
        payload = {
            "productType": productType,
            "symbol": symbol,
            "marginCoin": marginCoin,
        }
        cost = self._get_rate_limit_cost(cost=2)
        await self._limiter("trade").limit(key=endpoint, cost=cost)

        payload = {k: v for k, v in payload.items() if v is not None}
        raw = await self._fetch("POST", self._base_url, endpoint, payload, signed=True)
        return self._msg_decoder.decode(raw)

    async def get_v2_mix_market_kline(
        self,
        symbol: str,
        product_type: str,
        granularity: str,
        start_time: str | None = None,
        end_time: str | None = None,
        kline_type: str | None = None,
        limit: int | None = None,
    ):
        """
        Get Candlestick (Kline) Data from Bitget
        https://www.bitget.com/api-doc/contract/market/Get-Candle-Data
        """
        endpoint = "/api/v2/mix/market/candles"
        payload = {
            "symbol": symbol,
            "productType": product_type,
            "granularity": granularity,
            "startTime": start_time,
            "endTime": end_time,
            "kLineType": kline_type,
            "limit": str(limit) if limit is not None else None,
        }
        cost = self._get_rate_limit_cost(cost=1)
        self._limiter_sync("public").limit(key=endpoint, cost=cost)
        payload = {k: v for k, v in payload.items() if v is not None}
        raw = self._fetch_sync("GET", self._base_url, endpoint, payload, signed=False)
        return self._kline_response_decoder.decode(raw)

    def get_v2_mix_market_index_price_kline(
        self,
        productType: str,
        symbol: str,
        granularity: str,
        startTime: str | None = None,
        endTime: str | None = None,
        limit: str | None = None,
    ) -> BitgetIndexPriceKlineResponse:
        """
        https://www.bitget.com/api-doc/contract/market/Get-History-Index-Candle-Data
        """
        endpoint = "/api/v2/mix/market/history-index-candles"
        payload = {
            "productType": productType,
            "symbol": symbol,
            "granularity": granularity,
            "startTime": startTime,
            "endTime": endTime,
            "limit": limit,
        }
        payload = {k: v for k, v in payload.items() if v is not None}

        cost = self._get_rate_limit_cost(1)
        self._limiter_sync("public").limit(key=endpoint, cost=cost)

        raw = self._fetch_sync("GET", self._base_url, endpoint, payload, signed=False)

        decoded = msgspec.json.decode(raw)
        items = [
            BitgetIndexPriceKlineItem(
                timestamp=i[0],
                open_price=i[1],
                high_price=i[2],
                low_price=i[3],
                close_price=i[4],
                base_volume=i[5],
                quote_volume=i[6],
            )
            for i in decoded["data"]
        ]
        return BitgetIndexPriceKlineResponse(
            code=decoded["code"],
            msg=decoded["msg"],
            requestTime=decoded["requestTime"],
            data=items
        )
