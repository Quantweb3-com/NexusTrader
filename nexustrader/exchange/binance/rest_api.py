import hmac
import hashlib
import json
import msgspec
import httpx
import aiohttp
import asyncio

from typing import Any, Dict, Union
from urllib.parse import urljoin, urlencode

from nexustrader.base import ApiClient
from nexustrader.exchange.binance.schema import (
    BinanceOrder,
    BinanceListenKey,
    BinanceSpotAccountInfo,
    BinanceFuturesAccountInfo,
    BinanceResponseKline,
    BinanceFuturesModifyOrderResponse,
    BinanceCancelAllOrdersResponse,
    BinanceFundingRateResponse,
    BinancePortfolioMarginBalance,
    BinancePortfolioMarginPositionRisk,
    BinanceIndexResponseKline,
    BinanceBatchOrderResponse,
)
from nexustrader.exchange.binance.constants import (
    BinanceAccountType,
    BinanceRateLimitType,
    BinanceRateLimiter,
    BinanceRateLimiterSync,
)
from nexustrader.exchange.binance.error import BinanceClientError, BinanceServerError
from nexustrader.core.nautilius_core import hmac_signature


class BinanceApiClient(ApiClient):
    _limiter: BinanceRateLimiter
    _limiter_sync: BinanceRateLimiterSync

    def __init__(
        self,
        api_key: str = None,
        secret: str = None,
        testnet: bool = False,
        timeout: int = 10,
        enable_rate_limit: bool = True,
    ):
        super().__init__(
            api_key=api_key,
            secret=secret,
            timeout=timeout,
            enable_rate_limit=enable_rate_limit,
            rate_limiter=BinanceRateLimiter(),
            rate_limiter_sync=BinanceRateLimiterSync(),
        )
        self._headers = {
            "Content-Type": "application/json",
            "User-Agent": "TradingBot/1.0",
        }

        if api_key:
            self._headers["X-MBX-APIKEY"] = api_key

        self._testnet = testnet
        self._msg_encoder = msgspec.json.Encoder()
        self._msg_decoder = msgspec.json.Decoder()
        self._order_decoder = msgspec.json.Decoder(BinanceOrder)
        self._spot_account_decoder = msgspec.json.Decoder(BinanceSpotAccountInfo)
        self._futures_account_decoder = msgspec.json.Decoder(BinanceFuturesAccountInfo)
        self._listen_key_decoder = msgspec.json.Decoder(BinanceListenKey)
        self._kline_response_decoder = msgspec.json.Decoder(list[BinanceResponseKline])
        self._index_kline_response_decoder = msgspec.json.Decoder(
            list[BinanceIndexResponseKline]
        )
        self._futures_modify_order_decoder = msgspec.json.Decoder(
            BinanceFuturesModifyOrderResponse
        )
        self._cancel_all_orders_decoder = msgspec.json.Decoder(
            BinanceCancelAllOrdersResponse
        )
        self._funding_rate_decoder = msgspec.json.Decoder(
            list[BinanceFundingRateResponse]
        )
        self._portfolio_margin_balance_decoder = msgspec.json.Decoder(
            list[BinancePortfolioMarginBalance]
        )
        self._portfolio_margin_position_risk_decoder = msgspec.json.Decoder(
            list[BinancePortfolioMarginPositionRisk]
        )
        self._batch_order_decoder = msgspec.json.Decoder(
            list[BinanceBatchOrderResponse]
        )

    def _generate_signature(self, query: str) -> str:
        signature = hmac.new(
            self._secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        return signature

    def _generate_signature_v2(self, query: str) -> str:
        signature = hmac_signature(self._secret, query)
        return signature

    def _fetch_sync(
        self,
        method: str,
        base_url: str,
        endpoint: str,
        payload: Dict[str, Any] = None,
        signed: bool = False,
        required_timestamp: bool = True,
    ) -> Any:
        self._init_sync_session()

        url = urljoin(base_url, endpoint)
        payload = payload or {}
        if required_timestamp:
            payload["timestamp"] = self._clock.timestamp_ms()
        payload = urlencode(payload)

        if signed:
            signature = self._generate_signature_v2(payload)
            payload += f"&signature={signature}"

        if method == "GET":
            url = f"{url}?{payload}"
            data = None
        else:
            data = payload
        self._log.debug(f"Request: {url}")

        try:
            response = self._sync_session.request(
                method=method,
                url=url,
                headers=self._headers,
                data=data,
            )
            raw = response.content
            self.raise_error(raw, response.status_code, response.headers)
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
        signed: bool = False,
        required_timestamp: bool = True,
    ) -> Any:
        self._init_session()

        url = urljoin(base_url, endpoint)
        payload = payload or {}
        if required_timestamp:
            payload["timestamp"] = self._clock.timestamp_ms()
        payload = urlencode(payload)

        if signed:
            signature = self._generate_signature_v2(payload)
            payload += f"&signature={signature}"
        if method == "GET":
            url = f"{url}?{payload}"
            data = None
        else:
            data = payload
        self._log.debug(f"Request: {url}")

        try:
            response = await self._session.request(
                method=method,
                url=url,
                headers=self._headers,
                data=data,
            )
            raw = await response.read()
            self.raise_error(raw, response.status, response.headers)
            return raw
        except aiohttp.ClientError as e:
            self._log.error(f"Client Error {method} Url: {url} {e}")
            raise
        except asyncio.TimeoutError:
            self._log.error(f"Timeout {method} Url: {url}")
            raise
        except Exception as e:
            self._log.error(f"Error {method} Url: {url} {e}")
            raise

    def raise_error(self, raw: bytes, status: int, headers: Dict[str, Any]):
        if 400 <= status < 500:
            raise BinanceClientError(status, self._msg_decoder.decode(raw), headers)
        elif status >= 500:
            raise BinanceServerError(status, self._msg_decoder.decode(raw), headers)

    def _get_base_url(self, account_type: BinanceAccountType) -> str:
        if account_type == BinanceAccountType.SPOT:
            if self._testnet:
                return BinanceAccountType.SPOT_TESTNET.base_url
            return BinanceAccountType.SPOT.base_url
        elif account_type == BinanceAccountType.MARGIN:
            return BinanceAccountType.MARGIN.base_url
        elif account_type == BinanceAccountType.ISOLATED_MARGIN:
            return BinanceAccountType.ISOLATED_MARGIN.base_url
        elif account_type == BinanceAccountType.USD_M_FUTURE:
            if self._testnet:
                return BinanceAccountType.USD_M_FUTURE_TESTNET.base_url
            return BinanceAccountType.USD_M_FUTURE.base_url
        elif account_type == BinanceAccountType.COIN_M_FUTURE:
            if self._testnet:
                return BinanceAccountType.COIN_M_FUTURE_TESTNET.base_url
            return BinanceAccountType.COIN_M_FUTURE.base_url
        elif account_type == BinanceAccountType.PORTFOLIO_MARGIN:
            return BinanceAccountType.PORTFOLIO_MARGIN.base_url

    async def put_dapi_v1_listen_key(self):
        """
        https://developers.binance.com/docs/derivatives/coin-margined-futures/user-data-streams/Keepalive-User-Data-Stream
        """
        base_url = self._get_base_url(BinanceAccountType.COIN_M_FUTURE)
        end_point = "/dapi/v1/listenKey"
        cost = self._get_rate_limit_cost(1)
        await self._limiter(
            BinanceAccountType.COIN_M_FUTURE, BinanceRateLimitType.REQUEST_WEIGHT
        ).limit(key=BinanceAccountType.COIN_M_FUTURE.value, cost=cost)
        raw = await self._fetch("PUT", base_url, end_point, required_timestamp=False)
        return self._msg_decoder.decode(raw)

    async def post_dapi_v1_listen_key(self):
        """
        https://developers.binance.com/docs/derivatives/coin-margined-futures/user-data-streams/Start-User-Data-Stream
        """
        base_url = self._get_base_url(BinanceAccountType.COIN_M_FUTURE)
        end_point = "/dapi/v1/listenKey"
        cost = self._get_rate_limit_cost(1)
        await self._limiter(
            BinanceAccountType.COIN_M_FUTURE, BinanceRateLimitType.REQUEST_WEIGHT
        ).limit(key=BinanceAccountType.COIN_M_FUTURE.value, cost=cost)
        raw = await self._fetch("POST", base_url, end_point, required_timestamp=False)
        return self._listen_key_decoder.decode(raw)

    async def post_api_v3_user_data_stream(self) -> BinanceListenKey:
        """
        https://developers.binance.com/docs/binance-spot-api-docs/rest-api/user-data-stream-endpoints-deprecated
        """
        base_url = self._get_base_url(BinanceAccountType.SPOT)
        end_point = "/api/v3/userDataStream"
        cost = self._get_rate_limit_cost(2)
        await self._limiter(
            BinanceAccountType.SPOT, BinanceRateLimitType.REQUEST_WEIGHT
        ).limit(key=BinanceAccountType.SPOT.value, cost=cost)
        raw = await self._fetch("POST", base_url, end_point, required_timestamp=False)
        return self._listen_key_decoder.decode(raw)

    async def put_api_v3_user_data_stream(self, listen_key: str):
        """
        https://developers.binance.com/docs/binance-spot-api-docs/user-data-stream
        """
        base_url = self._get_base_url(BinanceAccountType.SPOT)
        end_point = "/api/v3/userDataStream"
        cost = self._get_rate_limit_cost(2)
        await self._limiter(
            BinanceAccountType.SPOT, BinanceRateLimitType.REQUEST_WEIGHT
        ).limit(key=BinanceAccountType.SPOT.value, cost=cost)
        raw = await self._fetch(
            "PUT",
            base_url,
            end_point,
            payload={"listenKey": listen_key},
            required_timestamp=False,
        )
        return self._msg_decoder.decode(raw)

    async def post_sapi_v1_user_data_stream(self) -> BinanceListenKey:
        """
        https://developers.binance.com/docs/margin_trading/trade-data-stream/Start-Margin-User-Data-Stream
        """
        base_url = self._get_base_url(BinanceAccountType.MARGIN)
        end_point = "/sapi/v1/userDataStream"
        cost = self._get_rate_limit_cost(1)
        await self._limiter(
            BinanceAccountType.SPOT, BinanceRateLimitType.REQUEST_WEIGHT
        ).limit(key=BinanceAccountType.SPOT.value, cost=cost)
        raw = await self._fetch("POST", base_url, end_point, required_timestamp=False)
        return self._listen_key_decoder.decode(raw)

    async def put_sapi_v1_user_data_stream(self, listen_key: str):
        """
        https://developers.binance.com/docs/margin_trading/trade-data-stream/Keepalive-Margin-User-Data-Stream
        """
        base_url = self._get_base_url(BinanceAccountType.MARGIN)
        end_point = "/sapi/v1/userDataStream"
        cost = self._get_rate_limit_cost(1)
        await self._limiter(
            BinanceAccountType.SPOT, BinanceRateLimitType.REQUEST_WEIGHT
        ).limit(key=BinanceAccountType.SPOT.value, cost=cost)
        raw = await self._fetch(
            "PUT",
            base_url,
            end_point,
            payload={"listenKey": listen_key},
            required_timestamp=False,
        )
        return self._msg_decoder.decode(raw)

    async def post_sapi_v1_user_data_stream_isolated(
        self, symbol: str
    ) -> BinanceListenKey:
        """
        https://developers.binance.com/docs/margin_trading/trade-data-stream/Start-Isolated-Margin-User-Data-Stream
        """
        base_url = self._get_base_url(BinanceAccountType.ISOLATED_MARGIN)
        end_point = "/sapi/v1/userDataStream/isolated"
        cost = self._get_rate_limit_cost(1)
        await self._limiter(
            BinanceAccountType.SPOT, BinanceRateLimitType.REQUEST_WEIGHT
        ).limit(key=BinanceAccountType.SPOT.value, cost=cost)
        raw = await self._fetch(
            "POST",
            base_url,
            end_point,
            payload={"symbol": symbol},
            required_timestamp=False,
        )
        return self._listen_key_decoder.decode(raw)

    async def put_sapi_v1_user_data_stream_isolated(self, symbol: str, listen_key: str):
        """
        https://developers.binance.com/docs/margin_trading/trade-data-stream/Keepalive-Isolated-Margin-User-Data-Stream
        """
        base_url = self._get_base_url(BinanceAccountType.ISOLATED_MARGIN)
        end_point = "/sapi/v1/userDataStream/isolated"
        cost = self._get_rate_limit_cost(1)
        await self._limiter(
            BinanceAccountType.SPOT, BinanceRateLimitType.REQUEST_WEIGHT
        ).limit(key=BinanceAccountType.SPOT.value, cost=cost)
        raw = await self._fetch(
            "PUT",
            base_url,
            end_point,
            payload={"symbol": symbol, "listenKey": listen_key},
            required_timestamp=False,
        )
        return self._msg_decoder.decode(raw)

    async def post_fapi_v1_listen_key(self) -> BinanceListenKey:
        """
        https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Start-User-Data-Stream
        """
        base_url = self._get_base_url(BinanceAccountType.USD_M_FUTURE)
        end_point = "/fapi/v1/listenKey"
        cost = self._get_rate_limit_cost(1)
        await self._limiter(
            BinanceAccountType.USD_M_FUTURE, BinanceRateLimitType.REQUEST_WEIGHT
        ).limit(key=BinanceAccountType.USD_M_FUTURE.value, cost=cost)
        raw = await self._fetch("POST", base_url, end_point, required_timestamp=False)
        return self._listen_key_decoder.decode(raw)

    async def put_fapi_v1_listen_key(self):
        """
        https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Keepalive-User-Data-Stream
        """
        base_url = self._get_base_url(BinanceAccountType.USD_M_FUTURE)
        end_point = "/fapi/v1/listenKey"
        cost = self._get_rate_limit_cost(1)
        await self._limiter(
            BinanceAccountType.USD_M_FUTURE, BinanceRateLimitType.REQUEST_WEIGHT
        ).limit(key=BinanceAccountType.USD_M_FUTURE.value, cost=cost)
        raw = await self._fetch("PUT", base_url, end_point, required_timestamp=False)
        return self._msg_decoder.decode(raw)

    async def post_papi_v1_listen_key(self) -> BinanceListenKey:
        """
        https://developers.binance.com/docs/derivatives/portfolio-margin/user-data-streams/Start-User-Data-Stream
        """
        base_url = self._get_base_url(BinanceAccountType.PORTFOLIO_MARGIN)
        end_point = "/papi/v1/listenKey"
        cost = self._get_rate_limit_cost(1)
        await self._limiter(
            BinanceAccountType.PORTFOLIO_MARGIN, BinanceRateLimitType.REQUEST_WEIGHT
        ).limit(key=BinanceAccountType.PORTFOLIO_MARGIN.value, cost=cost)
        raw = await self._fetch("POST", base_url, end_point, required_timestamp=False)
        return self._listen_key_decoder.decode(raw)

    async def put_papi_v1_listen_key(self):
        """
        https://developers.binance.com/docs/derivatives/portfolio-margin/user-data-streams/Keepalive-User-Data-Stream
        """
        base_url = self._get_base_url(BinanceAccountType.PORTFOLIO_MARGIN)
        end_point = "/papi/v1/listenKey"
        cost = self._get_rate_limit_cost(1)
        await self._limiter(
            BinanceAccountType.PORTFOLIO_MARGIN, BinanceRateLimitType.REQUEST_WEIGHT
        ).limit(key=BinanceAccountType.PORTFOLIO_MARGIN.value, cost=cost)
        raw = await self._fetch("PUT", base_url, end_point, required_timestamp=False)
        return self._msg_decoder.decode(raw)

    async def post_sapi_v1_margin_order(
        self,
        symbol: str,
        side: str,
        type: str,
        **kwargs,
    ) -> BinanceOrder:
        """
        https://developers.binance.com/docs/margin_trading/trade/Margin-Account-New-Order
        """
        base_url = self._get_base_url(BinanceAccountType.MARGIN)
        end_point = "/sapi/v1/margin/order"
        cost = self._get_rate_limit_cost(6)
        await self._limiter(
            BinanceAccountType.MARGIN, BinanceRateLimitType.REQUEST_WEIGHT
        ).limit(key=BinanceAccountType.MARGIN.value, cost=cost)
        data = {
            "symbol": symbol,
            "side": side,
            "type": type,
            **kwargs,
        }
        raw = await self._fetch("POST", base_url, end_point, payload=data, signed=True)
        return self._order_decoder.decode(raw)

    async def post_api_v3_order(
        self,
        symbol: str,
        side: str,
        type: str,
        **kwargs,
    ) -> BinanceOrder:
        """
        https://developers.binance.com/docs/binance-spot-api-docs/rest-api/public-api-endpoints#new-order-trade
        """
        base_url = self._get_base_url(BinanceAccountType.SPOT)
        end_point = "/api/v3/order"
        cost = self._get_rate_limit_cost(1)
        await self._limiter(
            BinanceAccountType.SPOT, BinanceRateLimitType.REQUEST_WEIGHT
        ).limit(key=BinanceAccountType.SPOT.value, cost=cost)
        data = {
            "symbol": symbol,
            "side": side,
            "type": type,
            **kwargs,
        }
        raw = await self._fetch("POST", base_url, end_point, payload=data, signed=True)
        return self._order_decoder.decode(raw)

    async def post_fapi_v1_order(
        self,
        symbol: str,
        side: str,
        type: str,
        **kwargs,
    ) -> BinanceOrder:
        """
        https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api
        """
        base_url = self._get_base_url(BinanceAccountType.USD_M_FUTURE)
        end_point = "/fapi/v1/order"
        cost = self._get_rate_limit_cost(1)
        await self._limiter(
            BinanceAccountType.USD_M_FUTURE, BinanceRateLimitType.ORDERS
        ).limit(key=BinanceAccountType.USD_M_FUTURE.value, cost=cost)
        data = {
            "symbol": symbol,
            "side": side,
            "type": type,
            **kwargs,
        }
        raw = await self._fetch("POST", base_url, end_point, payload=data, signed=True)
        return self._order_decoder.decode(raw)

    async def post_dapi_v1_order(
        self,
        symbol: str,
        side: str,
        type: str,
        **kwargs,
    ) -> BinanceOrder:
        """
        https://developers.binance.com/docs/derivatives/coin-margined-futures/trade/rest-api
        """
        base_url = self._get_base_url(BinanceAccountType.COIN_M_FUTURE)
        end_point = "/dapi/v1/order"
        cost = self._get_rate_limit_cost(1)
        await self._limiter(
            BinanceAccountType.COIN_M_FUTURE, BinanceRateLimitType.ORDERS
        ).limit(key=BinanceAccountType.COIN_M_FUTURE.value, cost=cost)
        data = {
            "symbol": symbol,
            "side": side,
            "type": type,
            **kwargs,
        }
        raw = await self._fetch("POST", base_url, end_point, payload=data, signed=True)
        return self._order_decoder.decode(raw)

    async def post_papi_v1_um_order(
        self,
        symbol: str,
        side: str,
        type: str,
        **kwargs,
    ) -> BinanceOrder:
        """
        https://developers.binance.com/docs/derivatives/portfolio-margin/trade
        """
        base_url = self._get_base_url(BinanceAccountType.PORTFOLIO_MARGIN)
        end_point = "/papi/v1/um/order"
        cost = self._get_rate_limit_cost(1)
        await self._limiter(
            BinanceAccountType.PORTFOLIO_MARGIN, BinanceRateLimitType.REQUEST_WEIGHT
        ).limit(key=BinanceAccountType.PORTFOLIO_MARGIN.value, cost=cost)
        data = {
            "symbol": symbol,
            "side": side,
            "type": type,
            **kwargs,
        }
        raw = await self._fetch("POST", base_url, end_point, payload=data, signed=True)
        return self._order_decoder.decode(raw)

    async def post_papi_v1_cm_order(
        self,
        symbol: str,
        side: str,
        type: str,
        **kwargs,
    ) -> BinanceOrder:
        """
        https://developers.binance.com/docs/derivatives/portfolio-margin/trade/New-CM-Order
        """
        base_url = self._get_base_url(BinanceAccountType.PORTFOLIO_MARGIN)
        end_point = "/papi/v1/cm/order"
        cost = self._get_rate_limit_cost(1)
        await self._limiter(
            BinanceAccountType.PORTFOLIO_MARGIN, BinanceRateLimitType.REQUEST_WEIGHT
        ).limit(key=BinanceAccountType.PORTFOLIO_MARGIN.value, cost=cost)
        data = {
            "symbol": symbol,
            "side": side,
            "type": type,
            **kwargs,
        }
        raw = await self._fetch("POST", base_url, end_point, payload=data, signed=True)
        return self._order_decoder.decode(raw)

    async def post_papi_v1_margin_order(
        self,
        symbol: str,
        side: str,
        type: str,
        **kwargs,
    ) -> BinanceOrder:
        """
        https://developers.binance.com/docs/derivatives/portfolio-margin/trade/New-Margin-Order
        """
        base_url = self._get_base_url(BinanceAccountType.PORTFOLIO_MARGIN)
        end_point = "/papi/v1/margin/order"
        cost = self._get_rate_limit_cost(1)
        await self._limiter(
            BinanceAccountType.PORTFOLIO_MARGIN, BinanceRateLimitType.REQUEST_WEIGHT
        ).limit(key=BinanceAccountType.PORTFOLIO_MARGIN.value, cost=cost)
        data = {
            "symbol": symbol,
            "side": side,
            "type": type,
            **kwargs,
        }
        raw = await self._fetch("POST", base_url, end_point, payload=data, signed=True)
        return self._order_decoder.decode(raw)

    async def delete_api_v3_order(
        self, symbol: str, order_id: int, **kwargs
    ) -> BinanceOrder:
        """
        https://developers.binance.com/docs/derivatives/portfolio-margin/trade/Cancel-UM-Order
        """
        base_url = self._get_base_url(BinanceAccountType.SPOT)
        end_point = "/api/v3/order"
        cost = self._get_rate_limit_cost(1)
        await self._limiter(
            BinanceAccountType.PORTFOLIO_MARGIN, BinanceRateLimitType.REQUEST_WEIGHT
        ).limit(key=BinanceAccountType.PORTFOLIO_MARGIN.value, cost=cost)
        data = {
            "symbol": symbol,
            "orderId": order_id,
            **kwargs,
        }
        raw = await self._fetch(
            "DELETE", base_url, end_point, payload=data, signed=True
        )
        return self._order_decoder.decode(raw)

    async def delete_sapi_v1_margin_order(
        self, symbol: str, order_id: int, **kwargs
    ) -> BinanceOrder:
        """
        https://developers.binance.com/docs/margin_trading/trade/Margin-Account-Cancel-Order
        """
        base_url = self._get_base_url(BinanceAccountType.MARGIN)
        end_point = "/sapi/v1/margin/order"
        cost = self._get_rate_limit_cost(10)
        await self._limiter(
            BinanceAccountType.MARGIN, BinanceRateLimitType.REQUEST_WEIGHT
        ).limit(key=BinanceAccountType.MARGIN.value, cost=cost)
        data = {
            "symbol": symbol,
            "orderId": order_id,
            **kwargs,
        }
        raw = await self._fetch(
            "DELETE", base_url, end_point, payload=data, signed=True
        )
        return self._order_decoder.decode(raw)

    async def delete_fapi_v1_order(
        self, symbol: str, order_id: int, **kwargs
    ) -> BinanceOrder:
        """
        https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Cancel-Order
        """
        base_url = self._get_base_url(BinanceAccountType.USD_M_FUTURE)
        end_point = "/fapi/v1/order"
        cost = self._get_rate_limit_cost(1)
        await self._limiter(
            BinanceAccountType.USD_M_FUTURE, BinanceRateLimitType.REQUEST_WEIGHT
        ).limit(key=BinanceAccountType.USD_M_FUTURE.value, cost=cost)
        data = {
            "symbol": symbol,
            "orderId": order_id,
            **kwargs,
        }
        raw = await self._fetch(
            "DELETE", base_url, end_point, payload=data, signed=True
        )
        return self._order_decoder.decode(raw)

    async def delete_dapi_v1_order(
        self, symbol: str, order_id: int, **kwargs
    ) -> BinanceOrder:
        """
        https://developers.binance.com/docs/derivatives/coin-margined-futures/trade/rest-api/Cancel-Order
        """
        base_url = self._get_base_url(BinanceAccountType.COIN_M_FUTURE)
        end_point = "/dapi/v1/order"
        cost = self._get_rate_limit_cost(1)
        await self._limiter(
            BinanceAccountType.COIN_M_FUTURE, BinanceRateLimitType.REQUEST_WEIGHT
        ).limit(key=BinanceAccountType.COIN_M_FUTURE.value, cost=cost)
        data = {
            "symbol": symbol,
            "orderId": order_id,
            **kwargs,
        }
        raw = await self._fetch(
            "DELETE", base_url, end_point, payload=data, signed=True
        )
        return self._order_decoder.decode(raw)

    async def delete_papi_v1_um_order(
        self, symbol: str, order_id: int, **kwargs
    ) -> BinanceOrder:
        """
        https://developers.binance.com/docs/derivatives/portfolio-margin/trade/Cancel-UM-Order
        """
        base_url = self._get_base_url(BinanceAccountType.PORTFOLIO_MARGIN)
        end_point = "/papi/v1/um/order"
        cost = self._get_rate_limit_cost(1)
        await self._limiter(
            BinanceAccountType.PORTFOLIO_MARGIN, BinanceRateLimitType.REQUEST_WEIGHT
        ).limit(key=BinanceAccountType.PORTFOLIO_MARGIN.value, cost=cost)
        data = {
            "symbol": symbol,
            "orderId": order_id,
            **kwargs,
        }
        raw = await self._fetch(
            "DELETE", base_url, end_point, payload=data, signed=True
        )
        return self._order_decoder.decode(raw)

    async def delete_papi_v1_cm_order(
        self, symbol: str, order_id: int, **kwargs
    ) -> BinanceOrder:
        """
        https://developers.binance.com/docs/derivatives/portfolio-margin/trade/Cancel-CM-Order
        """
        base_url = self._get_base_url(BinanceAccountType.PORTFOLIO_MARGIN)
        end_point = "/papi/v1/cm/order"
        cost = self._get_rate_limit_cost(1)
        await self._limiter(
            BinanceAccountType.PORTFOLIO_MARGIN, BinanceRateLimitType.REQUEST_WEIGHT
        ).limit(key=BinanceAccountType.PORTFOLIO_MARGIN.value, cost=cost)
        data = {
            "symbol": symbol,
            "orderId": order_id,
            **kwargs,
        }
        raw = await self._fetch(
            "DELETE", base_url, end_point, payload=data, signed=True
        )
        return self._order_decoder.decode(raw)

    async def delete_papi_v1_margin_order(
        self, symbol: str, order_id: int, **kwargs
    ) -> BinanceOrder:
        """
        https://developers.binance.com/docs/derivatives/portfolio-margin/trade/Cancel-Margin-Account-Order
        """
        base_url = self._get_base_url(BinanceAccountType.PORTFOLIO_MARGIN)
        end_point = "/papi/v1/margin/order"
        cost = self._get_rate_limit_cost(2)
        await self._limiter(
            BinanceAccountType.PORTFOLIO_MARGIN, BinanceRateLimitType.REQUEST_WEIGHT
        ).limit(key=BinanceAccountType.PORTFOLIO_MARGIN.value, cost=cost)
        data = {
            "symbol": symbol,
            "orderId": order_id,
            **kwargs,
        }
        raw = await self._fetch(
            "DELETE", base_url, end_point, payload=data, signed=True
        )
        return self._order_decoder.decode(raw)

    async def get_api_v3_account(self) -> BinanceSpotAccountInfo:
        """
        https://developers.binance.com/docs/binance-spot-api-docs/rest-api/account-endpoints#account-information-user_data
        """
        base_url = self._get_base_url(BinanceAccountType.SPOT)
        end_point = "/api/v3/account"
        cost = self._get_rate_limit_cost(20)
        await self._limiter(
            BinanceAccountType.SPOT, BinanceRateLimitType.REQUEST_WEIGHT
        ).limit(key=BinanceAccountType.SPOT.value, cost=cost)
        raw = await self._fetch("GET", base_url, end_point, signed=True)
        return self._spot_account_decoder.decode(raw)

    async def get_fapi_v2_account(self) -> BinanceFuturesAccountInfo:
        """
        https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Account-Information-V2
        """
        base_url = self._get_base_url(BinanceAccountType.USD_M_FUTURE)
        end_point = "/fapi/v2/account"
        cost = self._get_rate_limit_cost(5)
        await self._limiter(
            BinanceAccountType.USD_M_FUTURE, BinanceRateLimitType.REQUEST_WEIGHT
        ).limit(key=BinanceAccountType.USD_M_FUTURE.value, cost=cost)
        raw = await self._fetch("GET", base_url, end_point, signed=True)
        return self._futures_account_decoder.decode(raw)

    async def get_dapi_v1_account(self) -> BinanceFuturesAccountInfo:
        """
        https://developers.binance.com/docs/derivatives/coin-margined-futures/account/rest-api/Account-Information
        """
        base_url = self._get_base_url(BinanceAccountType.COIN_M_FUTURE)
        end_point = "/dapi/v1/account"
        cost = self._get_rate_limit_cost(5)
        await self._limiter(
            BinanceAccountType.COIN_M_FUTURE, BinanceRateLimitType.REQUEST_WEIGHT
        ).limit(key=BinanceAccountType.COIN_M_FUTURE.value, cost=cost)
        raw = await self._fetch("GET", base_url, end_point, signed=True)
        return self._futures_account_decoder.decode(raw)

    async def get_papi_v1_balance(self) -> list[BinancePortfolioMarginBalance]:
        """
        https://developers.binance.com/docs/derivatives/portfolio-margin/account
        """
        base_url = self._get_base_url(BinanceAccountType.PORTFOLIO_MARGIN)
        end_point = "/papi/v1/balance"
        cost = self._get_rate_limit_cost(20)
        await self._limiter(
            BinanceAccountType.PORTFOLIO_MARGIN, BinanceRateLimitType.REQUEST_WEIGHT
        ).limit(key=BinanceAccountType.PORTFOLIO_MARGIN.value, cost=cost)
        raw = await self._fetch("GET", base_url, end_point, signed=True)
        return self._portfolio_margin_balance_decoder.decode(raw)

    async def get_papi_v1_um_position_risk(
        self,
    ) -> list[BinancePortfolioMarginPositionRisk]:
        """
        https://developers.binance.com/docs/derivatives/portfolio-margin/account/Query-UM-Position-Information
        /papi/v1/um/positionRisk
        """
        base_url = self._get_base_url(BinanceAccountType.PORTFOLIO_MARGIN)
        end_point = "/papi/v1/um/positionRisk"
        cost = self._get_rate_limit_cost(5)
        await self._limiter(
            BinanceAccountType.PORTFOLIO_MARGIN, BinanceRateLimitType.REQUEST_WEIGHT
        ).limit(key=BinanceAccountType.PORTFOLIO_MARGIN.value, cost=cost)
        raw = await self._fetch("GET", base_url, end_point, signed=True)
        return self._portfolio_margin_position_risk_decoder.decode(raw)

    async def get_papi_v1_cm_position_risk(
        self,
    ) -> list[BinancePortfolioMarginPositionRisk]:
        """
        https://developers.binance.com/docs/derivatives/portfolio-margin/account/Query-CM-Position-Information
        /papi/v1/cm/positionRisk
        """
        base_url = self._get_base_url(BinanceAccountType.PORTFOLIO_MARGIN)
        end_point = "/papi/v1/cm/positionRisk"
        cost = self._get_rate_limit_cost(1)
        await self._limiter(
            BinanceAccountType.PORTFOLIO_MARGIN, BinanceRateLimitType.REQUEST_WEIGHT
        ).limit(key=BinanceAccountType.PORTFOLIO_MARGIN.value, cost=cost)
        raw = await self._fetch("GET", base_url, end_point, signed=True)
        return self._portfolio_margin_position_risk_decoder.decode(raw)

    def _limit_to_cost(self, limit: int | None) -> int:
        if limit is None:  # default limit is 500
            return self._get_rate_limit_cost(5)

        if limit < 100:
            return self._get_rate_limit_cost(1)
        elif limit < 500:
            return self._get_rate_limit_cost(2)
        elif limit < 1000:
            return self._get_rate_limit_cost(5)
        else:
            return self._get_rate_limit_cost(10)

    def get_fapi_v1_klines(
        self,
        symbol: str,
        interval: str,
        startTime: int = None,
        endTime: int = None,
        limit: int | None = None,
    ):
        """
        https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Kline-Candlestick-Data
        """
        base_url = self._get_base_url(BinanceAccountType.USD_M_FUTURE)
        end_point = "/fapi/v1/klines"
        cost = self._limit_to_cost(limit)
        self._limiter_sync(
            BinanceAccountType.USD_M_FUTURE, BinanceRateLimitType.REQUEST_WEIGHT
        ).limit(key=BinanceAccountType.USD_M_FUTURE.value, cost=cost)

        data = {
            "symbol": symbol,
            "interval": interval,
        }

        if startTime is not None:
            data["startTime"] = startTime
        if endTime is not None:
            data["endTime"] = endTime
        if limit is not None:
            data["limit"] = limit

        raw = self._fetch_sync(
            "GET", base_url, end_point, payload=data, required_timestamp=False
        )
        return self._kline_response_decoder.decode(raw)

    def get_dapi_v1_klines(
        self,
        symbol: str,
        interval: str,
        startTime: int = None,
        endTime: int = None,
        limit: int | None = None,
    ):
        """
        https://developers.binance.com/docs/derivatives/coin-margined-futures/market-data/rest-api/Kline-Candlestick-Data
        """
        base_url = self._get_base_url(BinanceAccountType.COIN_M_FUTURE)
        end_point = "/dapi/v1/klines"

        cost = self._limit_to_cost(limit)

        self._limiter_sync(
            BinanceAccountType.COIN_M_FUTURE, BinanceRateLimitType.REQUEST_WEIGHT
        ).limit(key=BinanceAccountType.COIN_M_FUTURE.value, cost=cost)

        data = {
            "symbol": symbol,
            "interval": interval,
            "startTime": startTime,
            "endTime": endTime,
            "limit": limit,
        }
        data = {k: v for k, v in data.items() if v is not None}
        raw = self._fetch_sync(
            "GET", base_url, end_point, payload=data, required_timestamp=False
        )
        return self._kline_response_decoder.decode(raw)

    def get_fapi_v1_index_price_klines(
        self,
        pair: str,
        interval: str,
        startTime: int = None,
        endTime: int = None,
        limit: int | None = None,
    ):
        base_url = self._get_base_url(BinanceAccountType.USD_M_FUTURE)
        end_point = "/fapi/v1/indexPriceKlines"
        cost = self._limit_to_cost(limit)
        self._limiter_sync(
            BinanceAccountType.USD_M_FUTURE, BinanceRateLimitType.REQUEST_WEIGHT
        ).limit(key=BinanceAccountType.USD_M_FUTURE.value, cost=cost)
        data = {
            "pair": pair,
            "interval": interval,
            "startTime": startTime,
            "endTime": endTime,
            "limit": limit,
        }
        data = {k: v for k, v in data.items() if v is not None}
        raw = self._fetch_sync(
            "GET", base_url, end_point, payload=data, required_timestamp=False
        )
        return self._index_kline_response_decoder.decode(raw)

    def get_dapi_v1_index_price_klines(
        self,
        pair: str,
        interval: str,
        startTime: int = None,
        endTime: int = None,
        limit: int | None = None,
    ):
        base_url = self._get_base_url(BinanceAccountType.COIN_M_FUTURE)
        end_point = "/dapi/v1/indexPriceKlines"
        cost = self._limit_to_cost(limit)
        self._limiter_sync(
            BinanceAccountType.COIN_M_FUTURE, BinanceRateLimitType.REQUEST_WEIGHT
        ).limit(key=BinanceAccountType.COIN_M_FUTURE.value, cost=cost)
        data = {
            "pair": pair,
            "interval": interval,
            "startTime": startTime,
            "endTime": endTime,
            "limit": limit,
        }
        data = {k: v for k, v in data.items() if v is not None}
        raw = self._fetch_sync(
            "GET", base_url, end_point, payload=data, required_timestamp=False
        )
        return self._index_kline_response_decoder.decode(raw)

    def get_api_v3_klines(
        self,
        symbol: str,
        interval: str,
        startTime: int = None,
        endTime: int = None,
        limit: int | None = None,
    ):
        """
        https://developers.binance.com/docs/binance-spot-api-docs/rest-api/market-data-endpoints#klinecandlestick-data

        [
            [
                1499040000000,      // Kline open time
                "0.01634790",       // Open price
                "0.80000000",       // High price
                "0.01575800",       // Low price
                "0.01577100",       // Close price
                "148976.11427815",  // Volume
                1499644799999,      // Kline Close time
                "2434.19055334",    // Quote asset volume
                308,                // Number of trades
                "1756.87402397",    // Taker buy base asset volume
                "28.46694368",      // Taker buy quote asset volume
                "0"                 // Unused field, ignore.
            ]
        ]
        """
        base_url = self._get_base_url(BinanceAccountType.SPOT)
        end_point = "/api/v3/klines"
        data = {
            "symbol": symbol,
            "interval": interval,
        }

        cost = self._get_rate_limit_cost(2)
        self._limiter_sync(
            BinanceAccountType.SPOT, BinanceRateLimitType.REQUEST_WEIGHT
        ).limit(key=BinanceAccountType.SPOT.value, cost=cost)

        if startTime is not None:
            data["startTime"] = startTime
        if endTime is not None:
            data["endTime"] = endTime
        if limit is not None:
            data["limit"] = limit

        raw = self._fetch_sync(
            "GET", base_url, end_point, payload=data, required_timestamp=False
        )
        return self._kline_response_decoder.decode(raw)

    async def put_fapi_v1_order(
        self,
        symbol: str,
        side: str,
        quantity: str,
        price: str,
        orderId: int | None = None,
        origClientOrderId: str = None,
        priceMatch: str | None = None,
    ):
        """
        https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Modify-Order
        """
        base_url = self._get_base_url(BinanceAccountType.USD_M_FUTURE)
        end_point = "/fapi/v1/order"
        cost = self._get_rate_limit_cost(1)
        await self._limiter(
            BinanceAccountType.USD_M_FUTURE, BinanceRateLimitType.ORDERS
        ).limit(key=BinanceAccountType.USD_M_FUTURE.value, cost=cost)
        data = {
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "price": price,
            "orderId": orderId,
            "origClientOrderId": origClientOrderId,
            "priceMatch": priceMatch,
        }
        data = {k: v for k, v in data.items() if v is not None}
        raw = await self._fetch("PUT", base_url, end_point, payload=data, signed=True)
        return self._futures_modify_order_decoder.decode(raw)

    async def put_dapi_v1_order(
        self,
        symbol: str,
        side: str,
        quantity: str,
        price: str,
        orderId: int | None = None,
        origClientOrderId: str = None,
        priceMatch: str | None = None,
    ):
        """
        https://developers.binance.com/docs/derivatives/coin-margined-futures/trade/rest-api/Modify-Order
        """
        base_url = self._get_base_url(BinanceAccountType.COIN_M_FUTURE)
        end_point = "/dapi/v1/order"
        cost = self._get_rate_limit_cost(1)
        await self._limiter(
            BinanceAccountType.COIN_M_FUTURE, BinanceRateLimitType.REQUEST_WEIGHT
        ).limit(key=BinanceAccountType.COIN_M_FUTURE.value, cost=cost)
        data = {
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "price": price,
            "orderId": orderId,
            "origClientOrderId": origClientOrderId,
            "priceMatch": priceMatch,
        }
        data = {k: v for k, v in data.items() if v is not None}
        raw = await self._fetch("PUT", base_url, end_point, payload=data, signed=True)
        return self._futures_modify_order_decoder.decode(raw)

    async def put_papi_v1_cm_order(
        self,
        symbol: str,
        side: str,
        quantity: str,
        price: str,
        orderId: int | None = None,
        origClientOrderId: str = None,
        priceMatch: str | None = None,
    ):
        """
        https://developers.binance.com/docs/derivatives/portfolio-margin/trade/Modify-CM-Order
        """
        base_url = self._get_base_url(BinanceAccountType.PORTFOLIO_MARGIN)
        end_point = "/papi/v1/cm/order"
        cost = self._get_rate_limit_cost(1)
        await self._limiter(
            BinanceAccountType.PORTFOLIO_MARGIN, BinanceRateLimitType.REQUEST_WEIGHT
        ).limit(key=BinanceAccountType.PORTFOLIO_MARGIN.value, cost=cost)
        data = {
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "price": price,
            "orderId": orderId,
            "origClientOrderId": origClientOrderId,
            "priceMatch": priceMatch,
        }
        data = {k: v for k, v in data.items() if v is not None}
        raw = await self._fetch("PUT", base_url, end_point, payload=data, signed=True)
        return self._futures_modify_order_decoder.decode(raw)

    async def put_papi_v1_um_order(
        self,
        symbol: str,
        side: str,
        quantity: str,
        price: str,
        orderId: int | None = None,
        origClientOrderId: str = None,
        priceMatch: str | None = None,
    ):
        """
        https://developers.binance.com/docs/derivatives/portfolio-margin/trade/Modify-UM-Order
        """
        base_url = self._get_base_url(BinanceAccountType.PORTFOLIO_MARGIN)
        end_point = "/papi/v1/um/order"
        cost = self._get_rate_limit_cost(1)
        await self._limiter(
            BinanceAccountType.PORTFOLIO_MARGIN, BinanceRateLimitType.REQUEST_WEIGHT
        ).limit(key=BinanceAccountType.PORTFOLIO_MARGIN.value, cost=cost)
        data = {
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "price": price,
            "orderId": orderId,
            "origClientOrderId": origClientOrderId,
            "priceMatch": priceMatch,
        }
        data = {k: v for k, v in data.items() if v is not None}
        raw = await self._fetch("PUT", base_url, end_point, payload=data, signed=True)
        return self._futures_modify_order_decoder.decode(raw)

    async def delete_fapi_v1_all_open_orders(self, symbol: str):
        """
        DELETE /fapi/v1/allOpenOrders
        https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Cancel-All-Open-Orders
        """
        base_url = self._get_base_url(BinanceAccountType.USD_M_FUTURE)
        end_point = "/fapi/v1/allOpenOrders"
        cost = self._get_rate_limit_cost(1)
        await self._limiter(
            BinanceAccountType.USD_M_FUTURE, BinanceRateLimitType.REQUEST_WEIGHT
        ).limit(key=BinanceAccountType.USD_M_FUTURE.value, cost=cost)
        data = {
            "symbol": symbol,
        }
        raw = await self._fetch(
            "DELETE", base_url, end_point, payload=data, signed=True
        )
        return self._cancel_all_orders_decoder.decode(raw)

    async def delete_dapi_v1_all_open_orders(self, symbol: str):
        """
        DELETE /dapi/v1/allOpenOrders
        https://developers.binance.com/docs/derivatives/coin-margined-futures/trade/rest-api/Cancel-All-Open-Orders
        """
        base_url = self._get_base_url(BinanceAccountType.COIN_M_FUTURE)
        end_point = "/dapi/v1/allOpenOrders"
        cost = self._get_rate_limit_cost(1)
        await self._limiter(
            BinanceAccountType.COIN_M_FUTURE, BinanceRateLimitType.REQUEST_WEIGHT
        ).limit(key=BinanceAccountType.COIN_M_FUTURE.value, cost=cost)
        data = {
            "symbol": symbol,
        }
        raw = await self._fetch(
            "DELETE", base_url, end_point, payload=data, signed=True
        )
        return self._cancel_all_orders_decoder.decode(raw)

    async def delete_papi_v1_um_all_open_orders(self, symbol: str):
        """
        DELETE /papi/v1/um/allOpenOrders
        https://developers.binance.com/docs/derivatives/portfolio-margin/trade/Cancel-All-UM-Open-Orders
        """
        base_url = self._get_base_url(BinanceAccountType.PORTFOLIO_MARGIN)
        end_point = "/papi/v1/um/allOpenOrders"
        cost = self._get_rate_limit_cost(1)
        await self._limiter(
            BinanceAccountType.PORTFOLIO_MARGIN, BinanceRateLimitType.REQUEST_WEIGHT
        ).limit(key=BinanceAccountType.PORTFOLIO_MARGIN.value, cost=cost)
        data = {
            "symbol": symbol,
        }
        raw = await self._fetch(
            "DELETE", base_url, end_point, payload=data, signed=True
        )
        return self._cancel_all_orders_decoder.decode(raw)

    async def delete_papi_v1_cm_all_open_orders(self, symbol: str):
        """
        DELETE /papi/v1/cm/allOpenOrders
        https://developers.binance.com/docs/derivatives/portfolio-margin/trade/Cancel-All-CM-Open-Orders
        """
        base_url = self._get_base_url(BinanceAccountType.PORTFOLIO_MARGIN)
        end_point = "/papi/v1/cm/allOpenOrders"
        cost = self._get_rate_limit_cost(1)
        await self._limiter(
            BinanceAccountType.PORTFOLIO_MARGIN, BinanceRateLimitType.REQUEST_WEIGHT
        ).limit(key=BinanceAccountType.PORTFOLIO_MARGIN.value, cost=cost)
        data = {
            "symbol": symbol,
        }
        raw = await self._fetch(
            "DELETE", base_url, end_point, payload=data, signed=True
        )
        return self._msg_decoder.decode(raw)

    async def delete_papi_v1_margin_all_open_orders(self, symbol: str):
        """
        DELETE /papi/v1/margin/allOpenOrders
        https://developers.binance.com/docs/derivatives/portfolio-margin/trade/Cancel-Margin-Account-All-Open-Orders-on-a-Symbol
        """
        base_url = self._get_base_url(BinanceAccountType.PORTFOLIO_MARGIN)
        end_point = "/papi/v1/margin/allOpenOrders"
        cost = self._get_rate_limit_cost(5)
        await self._limiter(
            BinanceAccountType.PORTFOLIO_MARGIN, BinanceRateLimitType.REQUEST_WEIGHT
        ).limit(key=BinanceAccountType.PORTFOLIO_MARGIN.value, cost=cost)
        data = {
            "symbol": symbol,
        }
        raw = await self._fetch(
            "DELETE", base_url, end_point, payload=data, signed=True
        )
        return self._msg_decoder.decode(raw)

    async def delete_api_v3_open_orders(self, symbol: str):
        """
        DELETE /api/v3/openOrders
        """
        base_url = self._get_base_url(BinanceAccountType.SPOT)
        end_point = "/api/v3/openOrders"
        cost = self._get_rate_limit_cost(1)
        await self._limiter(
            BinanceAccountType.SPOT, BinanceRateLimitType.REQUEST_WEIGHT
        ).limit(key=BinanceAccountType.SPOT.value, cost=cost)
        data = {
            "symbol": symbol,
        }
        raw = await self._fetch(
            "DELETE", base_url, end_point, payload=data, signed=True
        )
        return self._msg_decoder.decode(raw)

    async def get_fapi_v1_funding_rate(
        self,
        symbol: str,
        startTime: int | None = None,
        endTime: int | None = None,
        limit: int | None = None,
    ):
        """
        GET /fapi/v1/fundingRate
        """
        base_url = self._get_base_url(BinanceAccountType.USD_M_FUTURE)
        end_point = "/fapi/v1/fundingRate"
        data = {
            "symbol": symbol,
            "startTime": startTime,
            "endTime": endTime,
            "limit": limit,
        }
        data = {k: v for k, v in data.items() if v is not None}
        raw = await self._fetch("GET", base_url, end_point, payload=data)
        return self._funding_rate_decoder.decode(raw)

    async def get_dapi_v1_funding_rate(
        self,
        symbol: str,
        startTime: int | None = None,
        endTime: int | None = None,
        limit: int | None = None,
    ):
        """
        GET /dapi/v1/fundingRate
        """
        base_url = self._get_base_url(BinanceAccountType.COIN_M_FUTURE)
        end_point = "/dapi/v1/fundingRate"
        data = {
            "symbol": symbol,
            "startTime": startTime,
            "endTime": endTime,
            "limit": limit,
        }
        data = {k: v for k, v in data.items() if v is not None}
        raw = await self._fetch("GET", base_url, end_point, payload=data)
        return self._funding_rate_decoder.decode(raw)

    async def get_fapi_v1_positionSide_dual(self):
        """
        GET /fapi/v1/positionSide/dual
        https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Get-Current-Position-Mode
        """
        base_url = self._get_base_url(BinanceAccountType.USD_M_FUTURE)
        end_point = "/fapi/v1/positionSide/dual"
        cost = self._get_rate_limit_cost(30)
        await self._limiter(
            BinanceAccountType.USD_M_FUTURE, BinanceRateLimitType.REQUEST_WEIGHT
        ).limit(key=BinanceAccountType.USD_M_FUTURE.value, cost=cost)
        raw = await self._fetch("GET", base_url, end_point, signed=True)
        return self._msg_decoder.decode(raw)

    async def get_dapi_v1_positionSide_dual(self):
        """
        GET /dapi/v1/positionSide/dual
        """
        base_url = self._get_base_url(BinanceAccountType.COIN_M_FUTURE)
        end_point = "/dapi/v1/positionSide/dual"
        cost = self._get_rate_limit_cost(30)
        await self._limiter(
            BinanceAccountType.COIN_M_FUTURE, BinanceRateLimitType.REQUEST_WEIGHT
        ).limit(key=BinanceAccountType.COIN_M_FUTURE.value, cost=cost)
        raw = await self._fetch("GET", base_url, end_point, signed=True)
        return self._msg_decoder.decode(raw)

    async def get_papi_v1_um_positionSide_dual(self):
        """
        GET /papi/v1/um/positionSide/dual
        https://developers.binance.com/docs/derivatives/portfolio-margin/account/Get-UM-Current-Position-Mode
        """
        base_url = self._get_base_url(BinanceAccountType.PORTFOLIO_MARGIN)
        end_point = "/papi/v1/um/positionSide/dual"
        cost = self._get_rate_limit_cost(30)
        await self._limiter(
            BinanceAccountType.PORTFOLIO_MARGIN, BinanceRateLimitType.REQUEST_WEIGHT
        ).limit(key=BinanceAccountType.PORTFOLIO_MARGIN.value, cost=cost)
        raw = await self._fetch("GET", base_url, end_point, signed=True)
        return self._msg_decoder.decode(raw)

    async def get_papi_v1_cm_positionSide_dual(self):
        """
        GET /papi/v1/cm/positionSide/dual
        """
        base_url = self._get_base_url(BinanceAccountType.PORTFOLIO_MARGIN)
        end_point = "/papi/v1/cm/positionSide/dual"
        cost = self._get_rate_limit_cost(30)
        await self._limiter(
            BinanceAccountType.PORTFOLIO_MARGIN, BinanceRateLimitType.REQUEST_WEIGHT
        ).limit(key=BinanceAccountType.PORTFOLIO_MARGIN.value, cost=cost)
        raw = await self._fetch("GET", base_url, end_point, signed=True)
        return self._msg_decoder.decode(raw)

    async def post_fapi_v1_batch_orders(
        self,
        batch_orders: list[dict],
    ):
        """
        POST /fapi/v1/batchOrders
        https://developers.binance.com/docs/zh-CN/derivatives/usds-margined-futures/trade/rest-api/Place-Multiple-Orders
        """
        base_url = self._get_base_url(BinanceAccountType.USD_M_FUTURE)
        end_point = "/fapi/v1/batchOrders"
        cost = self._get_rate_limit_cost(5)
        await self._limiter(
            BinanceAccountType.USD_M_FUTURE, BinanceRateLimitType.ORDERS
        ).limit(key=BinanceAccountType.USD_M_FUTURE.value, cost=cost)
        data = {
            "batchOrders": json.dumps(batch_orders),
        }
        raw = await self._fetch("POST", base_url, end_point, payload=data, signed=True)
        return self._batch_order_decoder.decode(raw)

    async def post_dapi_v1_batch_orders(
        self,
        batch_orders: list[dict],
    ):
        """
        POST /dapi/v1/batchOrders
        https://developers.binance.com/docs/zh-CN/derivatives/coin-margined-futures/trade/rest-api/Place-Multiple-Orders
        """
        base_url = self._get_base_url(BinanceAccountType.COIN_M_FUTURE)
        end_point = "/dapi/v1/batchOrders"
        cost = self._get_rate_limit_cost(5)
        await self._limiter(
            BinanceAccountType.COIN_M_FUTURE, BinanceRateLimitType.ORDERS
        ).limit(key=BinanceAccountType.COIN_M_FUTURE.value, cost=cost)
        data = {
            "batchOrders": json.dumps(batch_orders),
        }
        raw = await self._fetch("POST", base_url, end_point, payload=data, signed=True)
        return self._batch_order_decoder.decode(raw)
