import base64
import hashlib
import hmac
from typing import Any, Dict, TypeVar
from urllib.parse import urlencode, urljoin
from error import KucoinError
import threading
import msgspec
from curl_cffi import requests

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
        api_key: str = None,
        secret: str = None,
        timeout: int = 10,
        max_retries: int = 0,
        delay_initial_ms: int = 100,
        delay_max_ms: int = 800,
        backoff_factor: int = 2,
        enable_rate_limit: bool = True,
    ):
        super().__init__(
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

    def _generate_signature(
        self,
        timestamp: str,
        method: str,
        path: str,
        query: str | None = None,
        body: str | None = None,
    ) -> str:
        if not self._secret:
            raise RuntimeError("KuCoin signature requires API secret")

        normalized_query = (query or "").lstrip("?")
        payload = body or ""
        sign_str = f"{timestamp}{method.upper()}{path}{normalized_query}{payload}"

        digest = hmac.new(
            self._secret.encode("utf-8"),
            sign_str.encode("utf-8"),
            hashlib.sha256,
        ).digest()

        return base64.b64encode(digest).decode("utf-8")

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
        signature = self._generate_signature(
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
            key_version = headers["KC-API-KEY-VERSION"]
            if key_version == "2":
                hashed = base64.b64encode(
                    hmac.new(
                        self._secret.encode("utf-8"),
                        passphrase.encode("utf-8"),
                        hashlib.sha256,
                    ).digest()
                ).decode("utf-8")
                headers["KC-API-PASSPHRASE"] = hashed
            else:
                headers["KC-API-PASSPHRASE"] = passphrase

        partner = getattr(self, "_partner", None)
        if partner:
            headers.setdefault("KC-API-PARTNER", partner)

        return headers

    async def _fetch(
        self,
        method: str,
        base_url: str,
        endpoint: str,
        payload: Dict[str, Any] | msgspec.Struct | None = None,
        signed: bool = False,
        *,
        response_type: str | None = None,
    ) -> Any:
        
        scope = "SPOT" if "api.kucoin.com" in base_url else "FUTURES"
        self._limiter._acquire_rate_limit(scope, method)
    
        return await self._retry_manager.run(
            name=f"{method} {endpoint}",
            func=self._fetch_async,
            method=method,
            base_url=base_url,
            endpoint=endpoint,
            payload=payload,
            signed=signed,
            response_type=response_type,
        )

    async def _fetch_async(
        self,
        method: str,
        base_url: str,
        endpoint: str,
        payload: Dict[str, Any] | msgspec.Struct | None = None,
        signed: bool = False,
        response_type: str | None = None,
    ) -> Any:
        self._init_session(self._base_url)

        request_path = endpoint
        headers = self._headers

        payload = payload or {}

        encoder = self._msg_encoder

        if method == "GET":
            # GET 请求：payload 用于构造 query string
            if isinstance(payload, msgspec.Struct):
                payload_dict = msgspec.asdict(payload)
            else:
                payload_dict = payload

            payload_json = urlencode(payload_dict) if payload_dict else ""
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
                method=method, url=base_url+endpoint, headers=headers, data=payload_json
            )
            raw = response.content

            return self._decode_response(response, raw, response_type)
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

    def _decode_response(self, response, raw: bytes, response_type: str | None) -> Any:

        if response.status_code >= 400:

            error_message = self._msg_decoder.decode(raw)
            code = error_message.get("code", response.status_code)
            message = error_message.get("msg", f"HTTP Error {response.status_code}")

            raise KucoinError(
                code=code,
                message=message,
            )

        if response_type == "spot_get_accounts":
            return self._dec_spot_get_accounts.decode(raw)
        if response_type == "spot_get_account_detail":
            return self._dec_spot_get_account_detail.decode(raw)
        if response_type == "futures_get_account":
            return self._dec_futures_get_account.decode(raw)
        if response_type == "spot_kline":
            return self._dec_spot_kline.decode(raw)
        if response_type == "spot_add_order":
            return self._dec_spot_add_order.decode(raw)
        if response_type == "spot_batch_add_orders":
            return self._dec_spot_batch_add_orders.decode(raw)
        if response_type == "spot_cancel_order_by_client":
            return self._dec_spot_cancel_order_by_client.decode(raw)
        if response_type == "spot_cancel_all_by_symbol":
            return self._dec_spot_cancel_all_by_symbol.decode(raw)
        if response_type == "spot_modify_order":
            return self._dec_spot_modify_order.decode(raw)
        if response_type == "futures_kline":
            return self._dec_futures_kline.decode(raw)
        if response_type == "futures_position_mode":
            return self._dec_futures_position_mode.decode(raw)
        if response_type == "futures_get_positions":
            return self._dec_futures_get_positions.decode(raw)

        return raw

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
        # 去掉 None 字段
        data = {k: v for k, v in data.items() if v is not None}

        raw = await self._fetch(
            "GET",
            base_url,
            end_point,
            payload=data,
            signed=True,
            response_type="spot_get_accounts",
        )
        return raw     

    async def get_api_v1_accounts_detail(
        self,
        accountId: str,
    ) -> KucoinSpotGetAccountDetailResponse:
        """
        https://www.kucoin.com/docs-new/rest/account-info/account-funding/get-account-detail-spot
        """
        base_url = self._get_base_url(KucoinAccountType.SPOT)
        end_point = f"/api/v1/accounts/{accountId}"

        raw = await self._fetch(
            "GET",
            base_url,
            end_point,
            payload={},
            signed=True,
            response_type="spot_get_account_detail",
        )
        return raw

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

        raw = await self._fetch(
            "GET",
            base_url,
            end_point,
            payload=data,
            signed=True,
            response_type="futures_get_account",
        )
        return raw

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
        # 去掉 None 字段
        data = {k: v for k, v in data.items() if v is not None}

        raw = await self._fetch(
            "GET",
            base_url,
            end_point,
            payload=data,
            signed=False,
            response_type="spot_kline",
        )
        return raw

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

        # 去掉为 None 的字段，避免发送多余参数
        data = {k: v for k, v in data.items() if v is not None}

        raw = await self._fetch(
            "POST",
            base_url,
            end_point,
            payload=data,
            signed=True,
            response_type="spot_add_order",
        )
        return raw
    
    async def post_api_v1_orders(
        self,
        orders: list[KucoinSpotAddOrderRequest],
    ) -> KucoinSpotBatchAddOrdersResponse:
        """
        https://www.kucoin.com/docs-new/rest/spot-trading/orders/batch-add-orders
        """
        base_url = self._get_base_url(KucoinAccountType.SPOT)
        end_point = "/api/v1/hf/orders/multi"

        order_list: list[dict[str, Any]] = []
        for o in orders:
            d = msgspec.asdict(o)
            d = {k: v for k, v in d.items() if v is not None}
            order_list.append(d)

        payload = {"orderList": order_list}

        raw = await self._fetch(
            "POST",
            base_url,
            end_point,
            payload=payload,
            signed=True,
            response_type="spot_batch_add_orders",
        )
        return raw
    
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

        raw = await self._fetch(
            "DELETE",
            base_url,
            end_point,
            payload=data,
            signed=True,
            response_type="spot_cancel_order_by_client",
        )
        return raw

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

        raw = await self._fetch(
            "DELETE",
            base_url,
            end_point,
            payload=data,
            signed=True,
            response_type="spot_cancel_all_by_symbol",
        )
        return raw
    
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
            "type": type,
            "orderId": orderId,
            "clientOid": clientOid,
            "newPrice": newPrice,
            "newSize": newSize,
        }

        # 去掉为 None 的字段
        data = {k: v for k, v in data.items() if v is not None}

        raw = await self._fetch(
            "POST",
            base_url,
            end_point,
            payload=data,
            signed=True,
            response_type="spot_modify_order",
        )
        return raw   

    async def get_api_v1_kline_query(
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
        # 去掉 None 字段（这里理论上都必填）
        data = {k: v for k, v in data.items() if v is not None}

        raw = await self._fetch(
            "GET",
            base_url,
            end_point,
            payload=data,
            signed=False,
            response_type="futures_kline",
        )
        return raw
    
    async def get_api_v1_position_mode(self) -> KucoinFuturesPositionModeResponse:
        """
        https://www.kucoin.com/docs-new/rest/futures-trading/positions/get-position-mode
        """
        base_url = self._get_base_url(KucoinAccountType.FUTURES)
        end_point = "/api/v1/position/mode"

        raw = await self._fetch(
            "GET",
            base_url,
            end_point,
            payload={},
            signed=True,
            response_type="futures_position_mode",
        )

        # 只允许 one-way 模式
        if raw.data.positionMode != 1:
            raise KucoinError(
                code=-1,
                message=f"Only one-way position mode (1) is allowed, current: {raw.data.positionMode}",
            )

        return raw
    
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

        raw = await self._fetch(
            "GET",
            base_url,
            end_point,
            payload=data,
            signed=True,
            response_type="futures_get_positions",
        )
        return raw