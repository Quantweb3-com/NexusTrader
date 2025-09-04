import msgspec
import base64
import httpx
from typing import Any, Dict
from urllib.parse import urlencode
from nexustrader.base import ApiClient, RetryManager
from nexustrader.exchange.bitget.constants import (
    BitgetRateLimiter,
    BitgetRateLimiterSync,
)

from nexustrader.exchange.bitget.schema import BitgetAccountAssetResponse
from nexustrader.exchange.bitget.error import BitgetError
from nexustrader.core.nautilius_core import (
    hmac_signature,
    LiveClock,
)
from nexustrader.exchange.bitget.schema import (
    BitgetOrderHistoryResponse,
    BitgetOpenOrdersResponse,
    BitgetPositionListResponse,
    BitgetOrderCancelResponse,
    BitgetOrderPlaceResponse,
    BitgetOrderModifyResponse,
    BitgetBaseResponse,
    BitgetKlineResponse,
    BitgetIndexPriceKlineResponse,
    BitgetGeneralResponse,
    BitgetTickerResponse,
    BitgetV3PositionResponse,
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
        max_retries: int = 0,
        delay_initial_ms: int = 100,
        delay_max_ms: int = 800,
        backoff_factor: int = 2,
    ):
        super().__init__(
            clock=clock,
            api_key=api_key,
            secret=secret,
            timeout=timeout,
            rate_limiter=BitgetRateLimiter(enable_rate_limit),
            rate_limiter_sync=BitgetRateLimiterSync(enable_rate_limit),
            retry_manager=RetryManager(
                max_retries=max_retries,
                delay_initial_ms=delay_initial_ms,
                delay_max_ms=delay_max_ms,
                backoff_factor=backoff_factor,
                exc_types=(BitgetError,),
                retry_check=lambda e: e.code in [40200],
            ),
        )

        self._base_url = "https://api.bitget.com"
        self._passphrase = passphrase
        self._testnet = testnet

        self._headers = {
            "Content-Type": "application/json",
            "locale": "en-US",
        }

        if self._testnet:
            self._headers["PAPTRADING"] = "1"

        if api_key:
            self._headers["ACCESS-KEY"] = api_key

        self._msg_decoder = msgspec.json.Decoder()
        self._msg_encoder = msgspec.json.Encoder()
        self._general_response_decoder = msgspec.json.Decoder(BitgetGeneralResponse)
        self._cancel_order_decoder = msgspec.json.Decoder(BitgetOrderCancelResponse)
        self._order_response_decoder = msgspec.json.Decoder(BitgetOrderPlaceResponse)
        self._position_list_decoder = msgspec.json.Decoder(BitgetPositionListResponse)
        self._open_orders_response_decoder = msgspec.json.Decoder(
            BitgetOpenOrdersResponse
        )
        self._order_history_response_decoder = msgspec.json.Decoder(
            BitgetOrderHistoryResponse
        )
        self._wallet_balance_response_decoder = msgspec.json.Decoder(
            BitgetAccountAssetResponse
        )
        self._order_modify_response_decoder = msgspec.json.Decoder(
            BitgetOrderModifyResponse
        )
        self._cancel_all_orders_decoder = msgspec.json.Decoder(BitgetBaseResponse)
        self._kline_response_decoder = msgspec.json.Decoder(BitgetKlineResponse)
        self._index_kline_response_decoder = msgspec.json.Decoder(
            BitgetIndexPriceKlineResponse
        )
        self._ticker_response_decoder = msgspec.json.Decoder(BitgetTickerResponse)
        self._v3_position_response_decoder = msgspec.json.Decoder(
            BitgetV3PositionResponse
        )

    def _generate_signature(self, message: str) -> str:
        hex_digest = hmac_signature(self._secret, message)
        digest = bytes.fromhex(hex_digest)
        return base64.b64encode(digest).decode()

    def _get_signature(
        self,
        ts: int,
        method: str,
        request_path: str,
        payload_json: str | None = None,
    ) -> str:
        body = payload_json or ""
        sign_str = f"{ts}{method}{request_path}{body}"
        signature = self._generate_signature(sign_str)
        return signature

    def _get_headers(
        self,
        method: str,
        request_path: str,
        payload_json: str | None = None,
    ):
        ts = self._clock.timestamp_ms()
        signature = self._get_signature(
            ts=ts,
            method=method,
            request_path=request_path,
            payload_json=payload_json,
        )
        return {
            **self._headers,
            "ACCESS-KEY": self._api_key,
            "ACCESS-SIGN": signature,
            "ACCESS-TIMESTAMP": str(ts),
            "ACCESS-PASSPHRASE": self._passphrase,
        }

    async def _fetch(
        self,
        method: str,
        endpoint: str,
        payload: Dict[str, Any] = None,
        signed: bool = False,
    ) -> Any:
        return await self._retry_manager.run(
            name=f"{method} {endpoint}",
            func=self._fetch_async,
            method=method,
            endpoint=endpoint,
            payload=payload,
            signed=signed,
        )

    async def _fetch_async(
        self,
        method: str,
        endpoint: str,
        payload: Dict[str, Any] = None,
        signed: bool = False,
    ) -> Any:
        self._init_session(self._base_url)

        request_path = endpoint
        headers = self._headers

        payload = payload or {}

        payload_json = (
            urlencode(payload)
            if method == "GET"
            else self._msg_encoder.encode(payload).decode("utf-8")
        )

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
                method=method, url=request_path, headers=headers, data=payload_json
            )
            raw = response.content

            if response.status_code >= 400:
                error_message = self._msg_decoder.decode(raw)
                code = error_message.get("code", response.status_code)
                message = error_message.get("msg", f"HTTP Error {response.status_code}")

                raise BitgetError(
                    code=code,
                    message=message,
                )
            return raw
        except httpx.TimeoutException as e:
            self._log.error(f"Timeout {method} {request_path} {e}")
            raise
        except httpx.ConnectError as e:
            self._log.error(f"Connection Error {method} {request_path} {e}")
            raise
        except httpx.HTTPStatusError as e:
            self._log.error(f"HTTP Error {method} {request_path} {e}")
            raise
        except httpx.RequestError as e:
            self._log.error(f"Request Error {method} {request_path} {e}")
            raise
        except Exception as e:
            self._log.error(f"Error {method} {request_path} {e}")
            raise

    def _fetch_sync(
        self,
        method: str,
        endpoint: str,
        payload: Dict[str, Any] = None,
        signed: bool = False,
    ) -> Any:
        self._init_sync_session(self._base_url)

        request_path = endpoint
        headers = self._headers

        payload = payload or {}

        payload_json = (
            urlencode(payload)
            if method == "GET"
            else self._msg_encoder.encode(payload).decode("utf-8")
        )

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
                method=method, url=request_path, headers=headers, data=payload_json
            )
            raw = response.content

            if response.status_code >= 400:
                error_message = self._msg_decoder.decode(raw)
                code = error_message.get("code", response.status_code)
                message = error_message.get("msg", f"HTTP Error {response.status_code}")

                raise BitgetError(
                    code=code,
                    message=message,
                )
            return raw
        except httpx.TimeoutException as e:
            self._log.error(f"Timeout {method} {request_path} {e}")
            raise
        except httpx.ConnectError as e:
            self._log.error(f"Connection Error {method} {request_path} {e}")
            raise
        except httpx.HTTPStatusError as e:
            self._log.error(f"HTTP Error {method} {request_path} {e}")
            raise
        except httpx.RequestError as e:
            self._log.error(f"Request Error {method} {request_path} {e}")
            raise
        except Exception as e:
            self._log.error(f"Error {method} {request_path} {e}")
            raise

    async def post_api_v3_trade_place_order(
        self,
        category: str,
        symbol: str,
        qty: str,
        side: str,
        orderType: str,
        timeInForce: str,
        **kwargs,
    ):
        endpoint = "/api/v3/trade/place-order"

        payload = {
            "category": category,
            "symbol": symbol,
            "qty": qty,
            "side": side,
            "orderType": orderType,
            "timeInForce": timeInForce,
            **kwargs,
        }
        payload = {k: v for k, v in payload.items() if v is not None}

        await self._limiter(endpoint).limit(key=endpoint, cost=1)
        raw = await self._fetch(
            method="POST",
            endpoint=endpoint,
            payload=payload,
            signed=True,
        )

        return self._order_response_decoder.decode(raw)

    async def post_api_v3_trade_cancel_order(
        self,
        orderId: str,
        clientOid: str | None = None,
    ):
        endpoint = "/api/v3/trade/cancel-order"

        payload = {
            "orderId": orderId,
            "clientOid": clientOid,
        }
        payload = {k: v for k, v in payload.items() if v is not None}

        await self._limiter(endpoint).limit(key=endpoint, cost=1)
        raw = await self._fetch(
            method="POST",
            endpoint=endpoint,
            payload=payload,
            signed=True,
        )

        return self._cancel_order_decoder.decode(raw)

    async def post_api_v2_mix_order_place_order(
        self,
        symbol: str,
        productType: str,
        marginMode: str,
        marginCoin: str,
        size: str,
        side: str,
        orderType: str,
        price: str | None = None,
        force: str | None = None,
        **kwargs,
    ):
        """
        Create Order

        https://www.bitget.com/api-doc/contract/trade/Place-Order

        force: ioc | fok | gtc | post_only
        """
        endpoint = "/api/v2/mix/order/place-order"

        payload = {
            "symbol": symbol,
            "productType": productType,
            "side": side,
            "orderType": orderType,
            "size": size,
            "price": price,
            "marginCoin": marginCoin,
            "marginMode": marginMode,
            "force": force,
            **kwargs,
        }
        payload = {k: v for k, v in payload.items() if v is not None}

        await self._limiter(endpoint).limit(key=endpoint, cost=1)

        raw = await self._fetch(
            method="POST",
            endpoint=endpoint,
            payload=payload,
            signed=True,
        )

        return self._order_response_decoder.decode(raw)

    async def post_api_v2_mix_order_cancel_order(
        self,
        symbol: str,
        productType: str,
        orderId: str,
        marginCoin: str | None = None,
        clientOid: str | None = None,
    ):
        """
        Bitget API:
        https://www.bitget.com/api-doc/contract/trade/Cancel-Order
        """
        endpoint = "/api/v2/mix/order/cancel-order"

        payload = {
            "symbol": symbol,
            "productType": productType,
            "orderId": orderId,
            "marginCoin": marginCoin,
            "clientOid": clientOid,
        }

        payload = {k: v for k, v in payload.items() if v is not None}
        await self._limiter(endpoint).limit(key=endpoint, cost=1)
        raw = await self._fetch("POST", endpoint, payload, signed=True)
        return self._cancel_order_decoder.decode(raw)

    async def post_api_v2_spot_trade_place_order(
        self,
        symbol: str,
        side: str,
        orderType: str,
        force: str,
        size: str,
        price: str | None = None,
        **kwargs,
    ):
        """
        https://www.bitget.com/api-doc/spot/trade/Place-Order
        POST /api/v2/spot/trade/place-order

        force: ioc | fok | gtc | post_only
        """
        endpoint = "/api/v2/spot/trade/place-order"

        payload = {
            "symbol": symbol,
            "side": side,
            "orderType": orderType,
            "force": force,
            "size": size,
            "price": price,
            **kwargs,
        }
        payload = {k: v for k, v in payload.items() if v is not None}
        await self._limiter(endpoint).limit(key=endpoint, cost=1)

        raw = await self._fetch("POST", endpoint, payload, signed=True)

        return self._order_response_decoder.decode(raw)

    async def post_api_v2_spot_trade_cancel_order(
        self,
        symbol: str,
        orderId: str,
        tpslType: str | None = None,  # default normal | tpsl
        clientOid: str | None = None,
    ):
        """
        https://www.bitget.com/api-doc/spot/trade/Cancel-Order

        POST /api/v2/spot/trade/cancel-order
        """
        endpoint = "/api/v2/spot/trade/cancel-order"

        payload = {
            "symbol": symbol,
            "orderId": orderId,
            "tpslType": tpslType,
            "clientOid": clientOid,
        }
        payload = {k: v for k, v in payload.items() if v is not None}

        await self._limiter(endpoint).limit(key=endpoint, cost=1)

        raw = await self._fetch("POST", endpoint, payload, signed=True)

        return self._cancel_order_decoder.decode(raw)

    def get_api_v2_mix_position_all_position(
        self,
        productType: str,
        marginCoin: str | None = None,
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
        payload = {k: v for k, v in payload.items() if v is not None}

        self._limiter_sync(endpoint).limit(key=endpoint, cost=1)

        raw = self._fetch_sync("GET", endpoint, payload, signed=True)

        return self._position_list_decoder.decode(raw)

    def get_api_v3_market_tickers(
        self,
        category: str,
        symbol: str | None = None,
    ):
        endpoint = "/api/v3/market/tickers"
        payload = {
            "category": category,
            "symbol": symbol,
        }
        self._limiter_sync(endpoint).limit(key=endpoint, cost=1)
        payload = {k: v for k, v in payload.items() if v is not None}
        raw = self._fetch_sync("GET", endpoint, payload, signed=False)
        return self._ticker_response_decoder.decode(raw)

    async def post_api_v3_trade_cancel_symbol_order(
        self,
        category: str,
        symbol: str,
    ):
        endpoint = "/api/v3/trade/cancel-symbol-order"

        payload = {
            "category": category,
            "symbol": symbol,
        }
        await self._limiter(endpoint).limit(key=endpoint, cost=1)
        payload = {k: v for k, v in payload.items() if v is not None}
        raw = await self._fetch("POST", endpoint, payload, signed=True)
        return self._msg_decoder.decode(raw)

    def get_api_v3_position_current_position(
        self,
        category: str,
        symbol: str | None = None,
        posSide: str | None = None,
    ):
        """
        Query real-time position data by symbol, side, or category.

        GET /api/v3/position/current-position
        https://www.bitget.com/api-doc/contract/position/Get-Position-Info

        Args:
            category: Product type (USDT-FUTURES, COIN-FUTURES, USDC-FUTURES)
            symbol: Symbol name (e.g. BTCUSDT). If not provided, returns all positions in category
            posSide: Position side (long/short). If provided, only returns position for this side
        """
        endpoint = "/api/v3/position/current-position"

        payload = {
            "category": category,
            "symbol": symbol,
            "posSide": posSide,
        }
        payload = {k: v for k, v in payload.items() if v is not None}

        self._limiter_sync(endpoint).limit(key=endpoint, cost=1)
        raw = self._fetch_sync("GET", endpoint, payload, signed=True)
        return self._v3_position_response_decoder.decode(raw)


# async def main():
#     from nexustrader.constants import settings

#     API_KEY = settings.BITGET.DEMO1.API_KEY
#     SECRET = settings.BITGET.DEMO1.SECRET
#     PASSPHRASE = settings.BITGET.DEMO1.PASSPHRASE

#     log_guard, _, clock = setup_nautilus_core(
#         trader_id="TESTER-001",
#         level_stdout="DEBUG",
#     )

#     client = BitgetApiClient(
#         clock=clock,
#         api_key=API_KEY,
#         secret=SECRET,
#         passphrase=PASSPHRASE,
#         testnet=True,
#         enable_rate_limit=True,
#     )
#     try:
#         res = await client.post_api_v2_mix_order_place_order(
#             symbol="BTCUSDT",
#             side="sell",
#             orderType="market",
#             size="0.01",
#             force="gtc",
#             productType="USDT-FUTURES",
#             marginMode="crossed",
#             marginCoin="USDT",
#             # price="113637.94",
#         )

#         # print(res)
#         # res = await client.post_api_v2_spot_trade_cancel_order(
#         #     symbol="ETHUSDT",
#         #     # productType="USDT-FUTURES",
#         #     orderId="1335439525711675392",
#         # )
#         # print(res)
#     finally:
#         await client.close_session()


# if __name__ == "__main__":
#     asyncio.run(main())
