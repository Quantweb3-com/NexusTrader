import base64
import hashlib
import hmac
import os
import asyncio
import argparse
from typing import Any, Dict, TypeVar
from urllib.parse import urlencode, urljoin
from error import KucoinError
import threading
import msgspec
from curl_cffi import requests
from nautilus_trader.common.component import LiveClock
from nexustrader.core.nautilius_core import hmac_signature

from nexustrader.base import ApiClient, RetryManager
from nexustrader.exchange.kucoin.constants import KucoinAccountType, KucoinRateLimiter
from nexustrader.exchange.kucoin.schema import (
    KucoinSpotGetAccountsResponse,
    KucoinSpotGetAccountDetailResponse,
    KucoinFuturesGetAccountResponse,
    KucoinSpotKlineResponse,
    KucoinSpotAddOrderRequest,
    KucoinSpotAddOrderResponse,
    KucoinSpotBatchAddOrdersResponse,
    KucoinSpotCancelOrderByClientResponse,
    KucoinSpotCancelAllBySymbolResponse,
    KucoinSpotModifyOrderResponse,
    KucoinFuturesKlineResponse,
    KucoinFuturesPositionModeResponse,
    KucoinFuturesGetPositionsResponse,
)


# For Signature: Refer to https://www.kucoin.com/docs-new/authentication
# For Api Rate Limits: Refer to https://www.kucoin.com/docs-new/rate-limit
# You should define spot api / futures trading api in KucoinApiClient
# for example:
# Spot market data api:
    # https://www.kucoin.com/docs-new/rest/spot-trading/market-data/get-klines
    # /api/v1/market/candles
    # you should define it as: def get_api_v1_market_candles(self, symbol: str, ...)
# Futures market data api:
    # https://www.kucoin.com/docs-new/rest/futures-trading/market-data/get-klines
    # /api/v1/kline/query
    # you should define it as: def get_api_v1_kline_query(self, symbol: str, ...)

# since their base url is different for spot and futures trading,
# you could implement a _get_base_url method in the KucoinApiClient class
# def _get_base_url(self, account_type: KucoinAccountType) -> str:
# you could refer `../binance/rest_api.py` for an example of how to implement it.

# implements KucoinApiClient(ApiClient)
class KucoinApiClient(ApiClient):
    _limiter: KucoinRateLimiter

    def __init__(
        self,
        clock: LiveClock,
        api_key: str | None = None,
        secret: str | None = None,
        timeout: int = 10,
        max_retries: int = 0,
        delay_initial_ms: int = 100,
        delay_max_ms: int = 800,
        backoff_factor: int = 2,
        enable_rate_limit: bool = True,
    ):
        super().__init__(
            clock=clock,
            api_key=api_key,
            secret=secret,
            timeout=timeout,
            rate_limiter=KucoinRateLimiter(enable_rate_limit),
            retry_manager=RetryManager(
                max_retries=max_retries,
                delay_initial_ms=delay_initial_ms,
                delay_max_ms=delay_max_ms,
                backoff_factor=backoff_factor,
                exc_types=(KucoinError, KucoinError),
                retry_check=lambda e: e.code in [-1000, -1001],
            ),
        )
        self._headers = {
            "Content-Type": "application/json",
            "User-Agent": "TradingBot/1.0",
        }

        if api_key:
            self._headers["X-MBX-APIKEY"] = api_key
            
        self._msg_encoder = msgspec.json.Encoder()
        self._msg_decoder = msgspec.json.Decoder(type=dict)
        self._dec_spot_get_accounts = msgspec.json.Decoder(type=KucoinSpotGetAccountsResponse)
        self._dec_spot_get_account_detail = msgspec.json.Decoder(type=KucoinSpotGetAccountDetailResponse)
        self._dec_futures_get_account = msgspec.json.Decoder(type=KucoinFuturesGetAccountResponse)
        self._dec_spot_kline = msgspec.json.Decoder(type=KucoinSpotKlineResponse)
        self._dec_spot_add_order = msgspec.json.Decoder(type=KucoinSpotAddOrderResponse)
        self._dec_spot_batch_add_orders = msgspec.json.Decoder(type=KucoinSpotBatchAddOrdersResponse)
        self._dec_spot_cancel_order_by_client = msgspec.json.Decoder(type=KucoinSpotCancelOrderByClientResponse)
        self._dec_spot_cancel_all_by_symbol = msgspec.json.Decoder(type=KucoinSpotCancelAllBySymbolResponse)
        self._dec_spot_modify_order = msgspec.json.Decoder(type=KucoinSpotModifyOrderResponse)
        self._dec_futures_kline = msgspec.json.Decoder(type=KucoinFuturesKlineResponse)
        self._dec_futures_position_mode = msgspec.json.Decoder(type=KucoinFuturesPositionModeResponse)
        self._dec_futures_get_positions = msgspec.json.Decoder(type=KucoinFuturesGetPositionsResponse)

    def _generate_signature_v2(
        self,
        timestamp: str,
        method: str,
        path: str,
        query: str | None = None,
        body: str | None = None,
    ) -> str:
        """
        Generate KuCoin signature using core `hmac_signature` for hashing,
        and return base64-encoded digest as required by KuCoin.
        sign_str = timestamp + method + path + query + body
        """
        if not self._secret:
            raise RuntimeError("KuCoin signature requires API secret")

        normalized_query = (query or "").lstrip("?")
        payload = body or ""
        sign_str = f"{timestamp}{method.upper()}{path}{normalized_query}{payload}"

        hex_digest = hmac_signature(self._secret, sign_str)
        return base64.b64encode(bytes.fromhex(hex_digest)).decode("utf-8")

    def _get_headers(
        self,
        method: str,
        request_path: str,
        payload_json: str | None = None,
    ) -> dict[str, str]:

        if not self._api_key or not self._secret:
            raise RuntimeError("KuCoin signed request requires API key and secret")

        timestamp = str(self._clock.timestamp_ms())

        path, _, query = request_path.partition("?")
        signature = self._generate_signature_v2(
            timestamp=timestamp,
            method=method,
            path=path,
            query=query,
            body=payload_json,
        )

        headers = dict(self._headers)
        headers.update(
            {
                "KC-API-KEY": self._api_key,
                "KC-API-SIGN": signature,
                "KC-API-TIMESTAMP": timestamp,
                "KC-API-KEY-VERSION": getattr(self, "_key_version", "2"),
            }
        )

        passphrase = getattr(self, "_passphrase", None)
        if passphrase:
            headers["KC-API-PASSPHRASE"] = base64.b64encode(
                    hmac.new(
                        self._secret.encode("utf-8"),
                        passphrase.encode("utf-8"),
                        hashlib.sha256,
                    ).digest()
                ).decode()

        partner = getattr(self, "_partner", None)
        if partner:
            headers.setdefault("KC-API-PARTNER", partner)

        return headers

    async def _fetch(
        self,
        method: str,
        base_url: str,
        endpoint: str,
        payload: Dict[str, Any] | None = None,
        signed: bool = False,
    ) -> Any:
        
        # Rate limiting occurs per endpoint using throttled limiter in each method
    
        return await self._retry_manager.run(
            name=f"{method} {endpoint}",
            func=self._fetch_async,
            method=method,
            base_url=base_url,
            endpoint=endpoint,
            payload=payload,
            signed=signed,
        )

    async def _fetch_async(
        self,
        method: str,
        base_url: str,
        endpoint: str,
        payload: Dict[str, Any] | None = None,
        signed: bool = False,
    ) -> Any:
        self._init_session(base_url)

        request_path = endpoint
        headers = self._headers

        payload = payload or {}

        encoder = self._msg_encoder

        if method == "GET":
            payload_json = urlencode(payload) if payload else ""
        else:
            payload_json = encoder.encode(payload).decode("utf-8")

        if method == "GET":
            if payload_json:
                request_path += f"?{payload_json}"
            payload_json = None

        if signed and self._api_key:
            headers = self._get_headers(
                method=method,
                request_path=request_path,
                payload_json=payload_json,
            )

        try:
            self._log.debug(
                f"{method} {request_path} Headers: {headers} payload: {payload_json}"
            )

            response = await self._session.request(
                method=method, url=base_url+request_path, headers=headers, data=payload_json
            )
            raw = response.content

            return self._decode_response(response, raw)
        except requests.exceptions.Timeout as e:
            self._log.error(f"Timeout {method} {request_path} {e}")
            raise
        except requests.exceptions.ConnectionError as e:
            self._log.error(f"Connection Error {method} {request_path} {e}")
            raise
        except requests.exceptions.HTTPError as e:
            self._log.error(f"HTTP Error {method} {request_path} {e}")
            raise
        except requests.exceptions.RequestException as e:
            self._log.error(f"Request Error {method} {request_path} {e}")
            raise
        except Exception as e:
            self._log.error(f"Error {method} {request_path} {e}")
            raise

    def _decode_response(self, response, raw: bytes) -> Any:

        if response.status_code >= 400:

            error_message = self._msg_decoder.decode(raw)
            code = error_message.get("code", response.status_code)
            message = error_message.get("msg", f"HTTP Error {response.status_code}")

            raise KucoinError(
                code=code,
                message=message,
            )

        return raw

    def _fetch_sync(
        self,
        method: str,
        base_url: str,
        endpoint: str,
        payload: Dict[str, Any] | None = None,
        signed: bool = False,
    ) -> Any:
        self._init_sync_session(base_url)

        request_path = endpoint
        headers = self._headers

        payload = payload or {}

        encoder = self._msg_encoder

        if method == "GET":
            payload_json = urlencode(payload) if payload else ""
        else:
            payload_json = encoder.encode(payload).decode("utf-8")

        if method == "GET":
            if payload_json:
                request_path += f"?{payload_json}"
            payload_json = None

        if signed and self._api_key:
            headers = self._get_headers(
                method=method,
                request_path=request_path,
                payload_json=payload_json,
            )

        try:
            self._log.debug(
                f"{method} {request_path} Headers: {headers} payload: {payload_json}"
            )

            response = self._sync_session.request(
                method=method, url=base_url+request_path, headers=headers, data=payload_json
            )
            raw = response.content

            return self._decode_response(response, raw)
        except requests.exceptions.Timeout as e:
            self._log.error(f"Timeout {method} {request_path} {e}")
            raise
        except requests.exceptions.ConnectionError as e:
            self._log.error(f"Connection Error {method} {request_path} {e}")
            raise
        except requests.exceptions.HTTPError as e:
            self._log.error(f"HTTP Error {method} {request_path} {e}")
            raise
        except requests.exceptions.RequestException as e:
            self._log.error(f"Request Error {method} {request_path} {e}")
            raise
        except Exception as e:
            self._log.error(f"Error {method} {request_path} {e}")
            raise

    async def fetch_ws_url(self, *, futures: bool, private: bool) -> str:
        account = KucoinAccountType.FUTURES if futures else KucoinAccountType.SPOT
        base_url = self._get_base_url(account)

        if private and (not self._api_key or not self._secret):
            raise RuntimeError("Private WS token fetch requires API key and secret")

        endpoint = "/api/v1/bullet-private" if private else "/api/v1/bullet-public"
        cost = self._get_rate_limit_cost(1)
        await self._limiter(endpoint).limit(key=endpoint, cost=cost)
        raw = await self._fetch(
            "POST",
            base_url,
            endpoint,
            payload={},
            signed=private,
        )

        dec = msgspec.json.Decoder(type=dict)
        data = dec.decode(raw).get("data", {})
        token = data.get("token")
        servers = data.get("instanceServers") or []
        if not token or not servers:
            raise RuntimeError("Failed to fetch KuCoin WS token or servers")
        url = servers[0].get("endpoint")
        if not url:
            raise RuntimeError("Invalid WS server endpoint from KuCoin response")
        connect_id = str(self._clock.timestamp_ms())
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}token={token}&connectId={connect_id}"

    def _get_base_url(self, account_type: KucoinAccountType) -> str:
        if account_type == KucoinAccountType.SPOT:
            return KucoinAccountType.SPOT.base_url
        else :
            return KucoinAccountType.FUTURES.base_url

    async def get_api_v1_accounts(
        self,
        currency: str | None = None,
        type: str | None = None,
    ) -> KucoinSpotGetAccountsResponse:
        """
        https://www.kucoin.com/docs-new/rest/account-info/account-funding/get-account-list-spot
        """
        base_url = self._get_base_url(KucoinAccountType.SPOT)
        end_point = "/api/v1/accounts"

        data = {
            "currency": currency,
            "type": type,
        }
        data = {k: v for k, v in data.items() if v is not None}

        cost = self._get_rate_limit_cost(1)
        await self._limiter(end_point).limit(key=end_point, cost=cost)
        raw = await self._fetch(
            "GET",
            base_url,
            end_point,
            payload=data,
            signed=True,
        )
        return self._dec_spot_get_accounts.decode(raw)

    def get_api_v1_accounts_sync(
        self,
        currency: str | None = None,
        type: str | None = None,
    ) -> KucoinSpotGetAccountsResponse:
        """
        Sync: https://www.kucoin.com/docs-new/rest/account-info/account-funding/get-account-list-spot
        """
        base_url = self._get_base_url(KucoinAccountType.SPOT)
        end_point = "/api/v1/accounts"

        data = {
            "currency": currency,
            "type": type,
        }
        data = {k: v for k, v in data.items() if v is not None}

        raw = self._fetch_sync(
            "GET",
            base_url,
            end_point,
            payload=data,
            signed=True,
        )
        return self._dec_spot_get_accounts.decode(raw)

    async def get_api_v1_accounts_detail(
        self,
        accountId: str,
    ) -> KucoinSpotGetAccountDetailResponse:
        """
        https://www.kucoin.com/docs-new/rest/account-info/account-funding/get-account-detail-spot
        """
        base_url = self._get_base_url(KucoinAccountType.SPOT)
        end_point = f"/api/v1/accounts/{accountId}"

        cost = self._get_rate_limit_cost(1)
        await self._limiter(end_point).limit(key=end_point, cost=cost)
        raw = await self._fetch(
            "GET",
            base_url,
            end_point,
            payload={},
            signed=True,
        )
        return self._dec_spot_get_account_detail.decode(raw)

    async def get_fapi_v1_account(
        self,
        currency: str | None = None,
    ) -> KucoinFuturesGetAccountResponse:
        """
        https://www.kucoin.com/docs-new/rest/account-info/account-funding/get-account-futures
        """
        base_url = self._get_base_url(KucoinAccountType.FUTURES)
        end_point = "/api/v1/account-overview"

        data = {
            "currency": currency,
        }
        # 去掉 None 字段
        data = {k: v for k, v in data.items() if v is not None}

        cost = self._get_rate_limit_cost(1)
        await self._limiter(end_point).limit(key=end_point, cost=cost)
        raw = await self._fetch(
            "GET",
            base_url,
            end_point,
            payload=data,
            signed=True,
        )
        return self._dec_futures_get_account.decode(raw)

    def get_fapi_v1_account_sync(
        self,
        currency: str | None = None,
    ) -> KucoinFuturesGetAccountResponse:
        """
        Sync: https://www.kucoin.com/docs-new/rest/account-info/account-funding/get-account-futures
        """
        base_url = self._get_base_url(KucoinAccountType.FUTURES)
        end_point = "/api/v1/account-overview"

        data = {
            "currency": currency,
        }
        data = {k: v for k, v in data.items() if v is not None}

        raw = self._fetch_sync(
            "GET",
            base_url,
            end_point,
            payload=data,
            signed=True,
        )
        return self._dec_futures_get_account.decode(raw)

    async def get_api_v1_market_candles(
        self,
        symbol: str,
        type: str,
        startAt: int | None = None,
        endAt: int | None = None,
    ) -> KucoinSpotKlineResponse:
        """
        https://www.kucoin.com/docs-new/rest/spot-trading/market-data/get-klines
        """
        base_url = self._get_base_url(KucoinAccountType.SPOT)
        end_point = "/api/v1/market/candles"

        data = {
            "symbol": symbol,
            "type": type,
            "startAt": startAt,
            "endAt": endAt,
        }
        data = {k: v for k, v in data.items() if v is not None}

        cost = self._get_rate_limit_cost(1)
        await self._limiter(end_point).limit(key=end_point, cost=cost)
        raw = await self._fetch(
            "GET",
            base_url,
            end_point,
            payload=data,
            signed=False,
        )
        return self._dec_spot_kline.decode(raw)

    async def post_api_v1_order(
        self,
        symbol: str,
        type: str,
        side: str,
        clientOid: str | None = None,
        stp: str | None = None,
        tradeType: str | None = None,
        tags: str | None = None,
        remark: str | None = None,
        price: str | None = None,
        size: str | None = None,
        funds: str | None = None,
        timeInForce: str | None = None,
        cancelAfter: int | None = None,
        postOnly: bool | None = None,
        hidden: bool | None = None,
        iceberg: bool | None = None,
        visibleSize: str | None = None,
        allowMaxTimeWindow: int | None = None,
    ) -> KucoinSpotAddOrderResponse:
        """
        https://www.kucoin.com/docs-new/rest/spot-trading/orders/add-order
        """
        base_url = self._get_base_url(KucoinAccountType.SPOT)
        end_point = "/api/v1/hf/orders"

        data = {
            "symbol": symbol,
            "type": type,
            "side": side,
            "clientOid": clientOid,
            "stp": stp,
            "tradeType": tradeType,
            "tags": tags,
            "remark": remark,
            "price": price,
            "size": size,
            "funds": funds,
            "timeInForce": timeInForce,
            "cancelAfter": cancelAfter,
            "postOnly": postOnly,
            "hidden": hidden,
            "iceberg": iceberg,
            "visibleSize": visibleSize,
            "allowMaxTimeWindow": allowMaxTimeWindow,
        }

        data = {k: v for k, v in data.items() if v is not None}

        cost = self._get_rate_limit_cost(1)
        await self._limiter(end_point).limit(key=end_point, cost=cost)
        raw = await self._fetch(
            "POST",
            base_url,
            end_point,
            payload=data,
            signed=True,
        )
        return self._dec_spot_add_order.decode(raw)
    
    async def post_api_v1_orders(
        self,
        orders: list[dict[str, Any]],
    ) -> KucoinSpotBatchAddOrdersResponse:
        """
        https://www.kucoin.com/docs-new/rest/spot-trading/orders/batch-add-orders
        """
        base_url = self._get_base_url(KucoinAccountType.SPOT)
        end_point = "/api/v1/hf/orders/multi"

        payload = {"orderList": orders}

        cost = self._get_rate_limit_cost(len(orders))
        await self._limiter(end_point).limit(key=end_point, cost=cost)
        raw = await self._fetch(
            "POST",
            base_url,
            end_point,
            payload=payload,
            signed=True,
        )
        return self._dec_spot_batch_add_orders.decode(raw)
    
    async def delete_api_v1_order_by_clientoid(
        self,
        clientOid: str,
        symbol: str,
    ) -> KucoinSpotCancelOrderByClientResponse:
        """
        https://www.kucoin.com/docs-new/rest/spot-trading/orders/cancel-order-by-clientoid
        """
        base_url = self._get_base_url(KucoinAccountType.SPOT)
        end_point = "/api/v1/hf/orders/client-order"

        data = {
            "clientOid": clientOid,
            "symbol": symbol,
        }

        cost = self._get_rate_limit_cost(1)
        await self._limiter(end_point).limit(key=end_point, cost=cost)
        raw = await self._fetch(
            "DELETE",
            base_url,
            end_point,
            payload=data,
            signed=True,
        )
        return self._dec_spot_cancel_order_by_client.decode(raw)

    async def delete_api_v1_orders_by_symbol(
        self,
        symbol: str,
    ) -> KucoinSpotCancelAllBySymbolResponse:
        """
        https://www.kucoin.com/docs-new/rest/spot-trading/orders/cancel-all-by-symbol
        """
        base_url = self._get_base_url(KucoinAccountType.SPOT)
        end_point = "/api/v1/hf/orders"

        data = {
            "symbol": symbol,
        }
        # 去掉 None 字段
        data = {k: v for k, v in data.items() if v is not None}

        cost = self._get_rate_limit_cost(1)
        await self._limiter(end_point).limit(key=end_point, cost=cost)
        raw = await self._fetch(
            "DELETE",
            base_url,
            end_point,
            payload=data,
            signed=True,
        )
        return self._dec_spot_cancel_all_by_symbol.decode(raw)
    
    async def post_api_v1_order_modify(
        self,
        symbol: str,
        orderId: str | None = None,
        clientOid: str | None = None,
        newPrice: str | None = None,
        newSize: str | None = None,
    ) -> KucoinSpotModifyOrderResponse:
        """
        https://www.kucoin.com/docs-new/rest/spot-trading/orders/modify-order
        """
        base_url = self._get_base_url(KucoinAccountType.SPOT)
        end_point = "/api/v1/hf/orders/alter"

        data = {
            "symbol": symbol,
            "orderId": orderId,
            "clientOid": clientOid,
            "newPrice": newPrice,
            "newSize": newSize,
        }

        # 去掉为 None 的字段
        data = {k: v for k, v in data.items() if v is not None}

        cost = self._get_rate_limit_cost(1)
        await self._limiter(end_point).limit(key=end_point, cost=cost)
        raw = await self._fetch(
            "POST",
            base_url,
            end_point,
            payload=data,
            signed=True,
        )
        return self._dec_spot_modify_order.decode(raw)

    async def get_fapi_v1_kline_query(
        self,
        symbol: str,
        granularity: int,
        from_: int | None = None,
        to: int | None = None ,
    ) -> KucoinFuturesKlineResponse:
        """
        https://www.kucoin.com/docs-new/rest/futures-trading/market-data/get-klines
        """
        base_url = self._get_base_url(KucoinAccountType.FUTURES)
        end_point = "/api/v1/kline/query"

        data = {
            "symbol": symbol,
            "granularity": granularity,
            "from": from_,
            "to": to,
        }
        data = {k: v for k, v in data.items() if v is not None}

        cost = self._get_rate_limit_cost(1)
        await self._limiter(end_point).limit(key=end_point, cost=cost)
        raw = await self._fetch(
            "GET",
            base_url,
            end_point,
            payload=data,
            signed=False,
        )
        return self._dec_futures_kline.decode(raw)
    
    async def get_api_v1_position_mode(self) -> KucoinFuturesPositionModeResponse:
        """
        https://www.kucoin.com/docs-new/rest/futures-trading/positions/get-position-mode
        """
        base_url = self._get_base_url(KucoinAccountType.FUTURES)
        end_point = "/api/v1/position/mode"

        cost = self._get_rate_limit_cost(1)
        await self._limiter(end_point).limit(key=end_point, cost=cost)
        raw = await self._fetch(
            "GET",
            base_url,
            end_point,
            payload={},
            signed=True,
        )
        resp = self._dec_futures_position_mode.decode(raw)

        # 只允许 one-way 模式
        if resp.data.positionMode != 1:
            raise KucoinError(
                code=-1,
                message=f"Only one-way position mode (1) is allowed, current: {resp.data.positionMode}",
            )

        return resp

    def get_api_v1_position_mode_sync(self) -> KucoinFuturesPositionModeResponse:
        """
        Sync: https://www.kucoin.com/docs-new/rest/futures-trading/positions/get-position-mode
        """
        base_url = self._get_base_url(KucoinAccountType.FUTURES)
        end_point = "/api/v1/position/mode"

        raw = self._fetch_sync(
            "GET",
            base_url,
            end_point,
            payload={},
            signed=True,
        )
        resp = self._dec_futures_position_mode.decode(raw)
        if resp.data.positionMode != 1:
            raise KucoinError(
                code=-1,
                message=f"Only one-way position mode (1) is allowed, current: {resp.data.positionMode}",
            )
        return resp
    
    async def get_api_v1_positions(
        self,
        currency: str | None = None,
    ) -> KucoinFuturesGetPositionsResponse:
        """
        https://www.kucoin.com/docs-new/rest/futures-trading/positions/get-position-list
        """
        base_url = self._get_base_url(KucoinAccountType.FUTURES)
        end_point = "/api/v1/positions"

        data = {
            "currency": currency,
        }
        # 去掉 None 字段
        data = {k: v for k, v in data.items() if v is not None}

        cost = self._get_rate_limit_cost(1)
        await self._limiter(end_point).limit(key=end_point, cost=cost)
        raw = await self._fetch(
            "GET",
            base_url,
            end_point,
            payload=data,
            signed=True,
        )
        return self._dec_futures_get_positions.decode(raw)

    def get_api_v1_positions_sync(
        self,
        currency: str | None = None,
    ) -> KucoinFuturesGetPositionsResponse:
        """
        Sync: https://www.kucoin.com/docs-new/rest/futures-trading/positions/get-position-list
        """
        base_url = self._get_base_url(KucoinAccountType.FUTURES)
        end_point = "/api/v1/positions"

        data = {
            "currency": currency,
        }
        data = {k: v for k, v in data.items() if v is not None}

        raw = self._fetch_sync(
            "GET",
            base_url,
            end_point,
            payload=data,
            signed=True,
        )
        return self._dec_futures_get_positions.decode(raw)

    async def post_fapi_v1_order(
        self,
        symbol: str,
        side: str,
        type: str,
        clientOid: str | None = None,
        leverage: int | None = None,
        timeInForce: str | None = None,
        price: str | None = None,
        size: str | None = None,
        qty: str | None = None,
        valueQty: str | None = None,
        reduceOnly: bool | None = None,
        remark: str | None = None,
        stop: str | None = None,
        stopPrice: str | None = None,
        stopPriceType: str | None = None,
        closeOrder: bool | None = None,
        forceHold: bool | None = None,
        stp: str | None = None,
        marginMode: str | None = None,
        postOnly: bool | None = None,
        hidden: bool | None = None,
        iceberg: bool | None = None,
        visibleSize: str | None = None,
        positionSide: str | None = None,
    ) -> Dict[str, Any]:
        """
        Futures: Add order
        Doc: https://www.kucoin.com/docs-new/rest/futures-trading/orders/add-order
        Endpoint: POST /api/v1/orders (futures base URL)
        """
        base_url = self._get_base_url(KucoinAccountType.FUTURES)
        end_point = "/api/v1/orders"

        data = {
            "symbol": symbol,
            "side": side,
            "type": type,
            "clientOid": clientOid,
            "leverage": leverage,
            "timeInForce": timeInForce,
            "price": price,
            "size": size,
            "qty": qty,
            "valueQty": valueQty,
            "reduceOnly": reduceOnly,
            "remark": remark,
            "stop": stop,
            "stopPrice": stopPrice,
            "stopPriceType": stopPriceType,
            "closeOrder": closeOrder,
            "forceHold": forceHold,
            "stp": stp,
            "marginMode": marginMode,
            "postOnly": postOnly,
            "hidden": hidden,
            "iceberg": iceberg,
            "visibleSize": visibleSize,
            "positionSide": positionSide,
        }
        # remove None values
        data = {k: v for k, v in data.items() if v is not None}

        cost = self._get_rate_limit_cost(1)
        await self._limiter(end_point).limit(key=end_point, cost=cost)
        raw = await self._fetch(
            "POST",
            base_url,
            end_point,
            payload=data,
            signed=True,
        )
        return self._msg_decoder.decode(raw)

    async def delete_fapi_v1_orders(
        self,
        symbol: str
    ) -> Dict[str, Any]:
        """
        Futures: Cancel all orders (optionally by symbol)
        Doc: https://www.kucoin.com/docs-new/rest/futures-trading/orders/cancel-all-orders
        Endpoint: DELETE /api/v1/orders (futures base URL)
        """
        base_url = self._get_base_url(KucoinAccountType.FUTURES)
        end_point = "/api/v1/orders"

        data = {
            "symbol": symbol,
        }

        cost = self._get_rate_limit_cost(1)
        await self._limiter(end_point).limit(key=end_point, cost=cost)
        raw = await self._fetch(
            "DELETE",
            base_url,
            end_point,
            payload=data,
            signed=True,
        )
        return self._msg_decoder.decode(raw)

    async def delete_fapi_v1_order_by_orderid(
        self,
        orderId: str,
    ) -> Dict[str, Any]:
        """
        Futures: Cancel order by orderId
        Doc: https://www.kucoin.com/docs-new/rest/futures-trading/orders/cancel-order-by-orderld
        Endpoint: DELETE /api/v1/orders/{orderId}
        """
        base_url = self._get_base_url(KucoinAccountType.FUTURES)
        end_point = f"/api/v1/orders/{orderId}"

        cost = self._get_rate_limit_cost(1)
        await self._limiter(end_point).limit(key=end_point, cost=cost)
        raw = await self._fetch(
            "DELETE",
            base_url,
            end_point,
            payload={},
            signed=True,
        )
        return self._msg_decoder.decode(raw)

    async def delete_fapi_v1_order_by_clientoid(
        self,
        clientOid: str,
        symbol: str 
    ) -> Dict[str, Any]:
        """
        Futures: Cancel order by clientOid
        Doc: https://www.kucoin.com/docs-new/rest/futures-trading/orders/cancel-order-by-clientoid
        Endpoint: DELETE /api/v1/orders/client-order
        """
        base_url = self._get_base_url(KucoinAccountType.FUTURES)
        end_point = "/api/v1/orders/client-order"

        data = {
            "clientOid": clientOid,
            "symbol": symbol,
        }

        cost = self._get_rate_limit_cost(1)
        await self._limiter(end_point).limit(key=end_point, cost=cost)
        raw = await self._fetch(
            "DELETE",
            base_url,
            end_point,
            payload=data,
            signed=True,
        )
        return self._msg_decoder.decode(raw)

    async def delete_api_v1_orders_cancel_all(self) -> Dict[str, Any]:
        """
        Spot: Cancel all open orders across all symbols
        Doc: https://www.kucoin.com/docs-new/rest/spot-trading/orders/cancel-all-orders
        Endpoint: DELETE /api/v1/hf/orders/cancelAll
        """
        base_url = self._get_base_url(KucoinAccountType.SPOT)
        end_point = "/api/v1/hf/orders/cancelAll"

        cost = self._get_rate_limit_cost(1)
        await self._limiter(end_point).limit(key=end_point, cost=cost)
        raw = await self._fetch(
            "DELETE",
            base_url,
            end_point,
            payload={},
            signed=True,
        )
        return self._msg_decoder.decode(raw)

    async def post_api_v2_accounts_inner_transfer(
        self,
        currency: str,
        amount: str,
        clientOid: str | None = None,
        fromType: str = "main",
        toType: str = "trade",
    ) -> Dict[str, Any]:
        base_url = self._get_base_url(KucoinAccountType.SPOT)
        end_point = "/api/v2/accounts/inner-transfer"

        if clientOid is None:
            clientOid = f"inner-{self._clock.timestamp_ms()}"

        data = {
            "clientOid": clientOid,
            "currency": currency,
            "from": fromType,
            "to": toType,
            "amount": amount,
        }

        raw = await self._fetch(
            "POST",
            base_url,
            end_point,
            payload=data,
            signed=True,
        )
        return self._msg_decoder.decode(raw)


# Simple runner to test get_api_v1_accounts using CLI args
async def _main(args: argparse.Namespace):
    api_key = args.api_key
    secret = args.secret
    passphrase = args.passphrase
    currency = args.currency
    typ = args.type

    clock = LiveClock()
    client = KucoinApiClient(clock=clock, api_key=api_key, secret=secret)
    if passphrase:
        setattr(client, "_passphrase", passphrase)

    try:
        resp = await client.get_api_v1_accounts(currency=currency, type=typ)
        print("code:", getattr(resp, "code", None))
        if hasattr(resp, "data"):
            print("accounts:", len(resp.data))
            for acc in resp.data[:3]:
                print(acc.id, acc.currency, acc.type, acc.balance, acc.available, acc.holds)
        else:
            print(resp)
    except Exception as e:
        print("Error:", e)

    # Hardcoded test for futures kline
    try:
        symbol = "XBTUSDTM"
        granularity = 60  # 1-minute klines
        now_ms = clock.timestamp_ms()
        from_ms = now_ms - 60 * 60 * 1000  # past 1 hour
        to_ms = now_ms

        print("\nTesting futures kline (symbol=XBTUSDTM, granularity=60)...")
        kline_resp = await client.get_fapi_v1_kline_query(
            symbol=symbol,
            granularity=granularity,
            from_=from_ms,
            to=to_ms,
        )
        print("code:", getattr(kline_resp, "code", None))
        if hasattr(kline_resp, "data"):
            print("klines:", len(kline_resp.data))
            for row in kline_resp.data[:3]:
                # Print first three rows for a quick peek
                print(row)
        else:
            print(kline_resp)
    except Exception as e:
        print("Futures kline error:", e)

    # Inner transfer: move 10 from main -> trade
    # try:
    #     cur = currency or "USDT"
    #     print(f"\nTransferring 10 {cur} from main -> trade...")
    #     transfer_resp = await client.post_api_v2_accounts_inner_transfer(
    #         currency=cur,
    #         amount="10",
    #         fromType="main",
    #         toType="trade",
    #     )
    #     # KuCoin returns dict with code/data for v2 endpoints
    #     print("transfer code:", transfer_resp.get("code"))
    #     print("transfer data:", transfer_resp.get("data") or transfer_resp)
    # except Exception as e:
    #     print("Inner transfer error:", e)

    # Hardcoded test for spot candles (klines)
    try:
        symbol_spot_kline = "BTC-USDT"
        type_frame = "1min"  # KuCoin spot uses strings like 1min, 5min, 1hour
        now_sec = clock.timestamp_ms() // 1000
        start_sec = now_sec - 60 * 60  # past 1 hour (seconds)
        end_sec = now_sec

        print("\nTesting spot candles (symbol=BTC-USDT, type=1min)...")
        spot_kline_resp = await client.get_api_v1_market_candles(
            symbol=symbol_spot_kline,
            type=type_frame,
            startAt=start_sec,
            endAt=end_sec,
        )
        print("code:", getattr(spot_kline_resp, "code", None))
        if hasattr(spot_kline_resp, "data"):
            print("klines:", len(spot_kline_resp.data))
            for row in spot_kline_resp.data[:3]:
                print(row)
        else:
            print(spot_kline_resp)
    except Exception as e:
        print("Spot candles error:", e)

    
    try:
        symbol_spot = "BTC-USDT"
        client_oid = f"spot-test-{clock.timestamp_ms()}"

        # print("\nTesting spot trade: place limit order then cancel...")
        # add_resp = await client.post_api_v1_order(
        #     symbol=symbol_spot,
        #     type="limit",
        #     side="buy",
        #     clientOid=client_oid,
        #     tradeType="TRADE",
        #     price="1000",  # far from market to avoid fill
        #     size="0.0001",
        #     timeInForce="GTC",
        #     postOnly=True,
        #     remark="Test",
        # )
        # print("place code:", getattr(add_resp, "code", None))
        # if hasattr(add_resp, "data"):
        #     print("placed:", add_resp.data)
        # else:
        #     print(add_resp)

        cancel_resp = await client.delete_api_v1_order_by_clientoid(
            clientOid=client_oid,
            symbol=symbol_spot,
        )
        print("cancel code:", getattr(cancel_resp, "code", None))
        if hasattr(cancel_resp, "data"):
            print("cancel data:", cancel_resp.data)
        else:
            print(cancel_resp)
    except Exception as e:
        print("Spot trade error:", e)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test KuCoin spot get accounts")
    parser.add_argument("--api-key", required=True, help="KuCoin API key")
    parser.add_argument("--secret", required=True, help="KuCoin API secret")
    parser.add_argument("--passphrase", required=False, help="KuCoin API passphrase")
    parser.add_argument("--currency", required=False, help="Filter by currency, e.g., USDT")
    parser.add_argument("--type", required=False, help="Account type filter, e.g., trade, main")
    args = parser.parse_args()
    asyncio.run(_main(args))