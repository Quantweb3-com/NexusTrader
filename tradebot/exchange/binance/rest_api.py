import time
import hmac
import orjson
import hashlib

import asyncio
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional
from urllib.parse import urljoin, urlencode
from tradebot.entity import Order

from tradebot.base import RestApi2, RestApi
from tradebot.exchange.binance.constants import BASE_URLS, ENDPOINTS
from tradebot.exchange.binance.constants import BinanceAccountType, EndpointsType


class BinanceRestApi(RestApi):
    def __init__(
        self,
        account_type: BinanceAccountType,
        api_key: str = None,
        secret: str = None,
        **kwargs,
    ):
        self._api_key = api_key
        self._secret = secret
        self._account_type = account_type
        self._base_url = BASE_URLS[account_type]
        super().__init__(**kwargs)

    def _get_headers(self) -> Dict[str, str]:
        # headers = {
        #     "Accept": "application/json",
        #     "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/56.0.2924.87 Safari/537.36",
        # }
        headers = {}
        if self._api_key:
            headers["X-MBX-APIKEY"] = self._api_key
        return headers

    def _generate_signature(self, query: str) -> str:
        signature = hmac.new(
            self._secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        return signature

    async def _fetch(
        self,
        method: str,
        endpoint: str,
        params: Dict[str, Any] = {},
        data: Dict[str, Any] = {},
        signed: bool = False,
    ) -> Any:
        url = urljoin(self._base_url, endpoint)

        data["timestamp"] = time.time_ns() // 1_000_000
        query = "&".join([f"{k}={v}" for k, v in data.items()])
        headers = self._get_headers()

        if signed:
            signature = self._generate_signature(query)
            params["signature"] = signature

        return await self.request(
            method, url, params=params, data=data, headers=headers
        )

    async def start_user_data_stream(self) -> Dict[str, Any]:
        if self._api_key is None:
            raise ValueError("API key is required to start user data stream")
        endpoint = self._generate_endpoint(EndpointsType.USER_DATA_STREAM)
        return await self._fetch("POST", endpoint)

    async def keep_alive_user_data_stream(self, listen_key: str) -> Dict[str, Any]:
        if self._api_key is None:
            raise ValueError("API key is required to keep alive user data stream")
        endpoint = self._generate_endpoint(EndpointsType.USER_DATA_STREAM)
        return await self._fetch("PUT", endpoint, params={"listenKey": listen_key})

    async def new_order(self, symbol: str, side: str, type: str, **kwargs):
        """
        SPOT: https://developers.binance.com/docs/binance-spot-api-docs/rest-api#new-order-trade /api/v3/order
        MARGIN: https://developers.binance.com/docs/margin_trading/trade/Margin-Account-New-Order /sapi/v1/margin/order
        USDM: https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api /fapi/v1/order
        COINM: https://developers.binance.com/docs/derivatives/coin-margined-futures/trade /dapi/v1/order
        PORTFOLIO > USDM: https://developers.binance.com/docs/derivatives/portfolio-margin/trade /papi/v1/um/order
                  > COINM: https://developers.binance.com/docs/derivatives/portfolio-margin/trade/New-CM-Order /papi/v1/cm/order
                  > MARGIN: https://developers.binance.com/docs/derivatives/portfolio-margin/trade/New-Margin-Order /papi/v1/margin/order
        """
        endpoint = self._generate_endpoint(EndpointsType.TRADING)
        endpoint = f"{endpoint}/order"
        params = {"symbol": symbol, "side": side, "type": type, **kwargs}
        return await self._fetch("POST", endpoint, data=params, signed=True)

    def _generate_endpoint(self, endpoint_type: EndpointsType) -> str:
        return ENDPOINTS[endpoint_type][self._account_type]


class BinanceApiClient(RestApi2):
    def __init__(
        self,
        api_key: str = None,
        secret: str = None,
        testnet: bool = False,
        **kwargs,
    ):
        self._api_key = api_key
        self._secret = secret
        self._testnet = testnet
        super().__init__(**kwargs)

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/56.0.2924.87 Safari/537.36",
        }
        if self._api_key:
            headers["X-MBX-APIKEY"] = self._api_key
        return headers

    def _generate_signature(self, query: str) -> str:
        signature = hmac.new(
            self._secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        return signature

    async def _fetch(
        self,
        method: str,
        base_url: str,
        endpoint: str,
        params: Dict[str, Any] = None,
        data: Dict[str, Any] = None,
        signed: bool = False,
    ) -> Any:
        url = urljoin(base_url, endpoint)
        data = data or {}
        data["timestamp"] = time.time_ns() // 1_000_000
        query = urlencode(data)
        headers = self._get_headers()

        if signed:
            signature = self._generate_signature(query)
            query += f"&signature={signature}"
            
        if method in ["GET", "DELETE"]:
            params = params or {}
            params.update(data)
            data = None
        else:
            data = query.encode()
            # data = orjson.dumps(query)

        return await self.request(
            method, url, params=params, data=query, headers=headers
        )

    async def put_dapi_v1_listen_key(self):
        """
        https://developers.binance.com/docs/derivatives/coin-margined-futures/user-data-streams/Keepalive-User-Data-Stream
        """
        base_url = (
            BinanceAccountType.COIN_M_FUTURE.base_url
            if not self._testnet
            else BinanceAccountType.COIN_M_FUTURE_TESTNET.base_url
        )
        end_point = "/dapi/v1/listenKey"
        return await self._fetch("PUT", base_url, end_point)

    async def post_dapi_v1_listen_key(self):
        """
        https://developers.binance.com/docs/derivatives/coin-margined-futures/user-data-streams/Start-User-Data-Stream
        """
        base_url = (
            BinanceAccountType.COIN_M_FUTURE.base_url
            if not self._testnet
            else BinanceAccountType.COIN_M_FUTURE_TESTNET.base_url
        )
        end_point = "/dapi/v1/listenKey"
        return await self._fetch("POST", base_url, end_point)

    async def post_api_v3_user_data_stream(self):
        """
        https://developers.binance.com/docs/binance-spot-api-docs/user-data-stream#create-a-listenkey-user_stream
        """
        base_url = (
            BinanceAccountType.SPOT.base_url
            if not self._testnet
            else BinanceAccountType.SPOT_TESTNET.base_url
        )
        end_point = "/api/v3/userDataStream"
        return await self._fetch("POST", base_url, end_point)

    async def put_api_v3_user_data_stream(self, listen_key: str):
        """
        https://developers.binance.com/docs/binance-spot-api-docs/user-data-stream
        """
        base_url = (
            BinanceAccountType.SPOT.base_url
            if not self._testnet
            else BinanceAccountType.SPOT_TESTNET.base_url
        )
        end_point = "/api/v3/userDataStream"
        return await self._fetch(
            "PUT", base_url, end_point, data={"listenKey": listen_key}
        )

    async def post_sapi_v1_user_data_stream(self):
        """
        https://developers.binance.com/docs/margin_trading/trade-data-stream/Start-Margin-User-Data-Stream
        """
        base_url = BinanceAccountType.MARGIN.base_url
        end_point = "/sapi/v1/userDataStream"
        return await self._fetch("POST", base_url, end_point)

    async def put_sapi_v1_user_data_stream(self, listen_key: str):
        """
        https://developers.binance.com/docs/margin_trading/trade-data-stream/Keepalive-Margin-User-Data-Stream
        """
        base_url = BinanceAccountType.MARGIN.base_url
        end_point = "/sapi/v1/userDataStream"
        return await self._fetch(
            "PUT", base_url, end_point, data={"listenKey": listen_key}
        )

    async def post_sapi_v1_user_data_stream_isolated(self, symbol: str):
        """
        https://developers.binance.com/docs/margin_trading/trade-data-stream/Start-Isolated-Margin-User-Data-Stream
        """
        base_url = BinanceAccountType.ISOLATED_MARGIN.base_url
        end_point = "/sapi/v1/userDataStream/isolated"
        return await self._fetch("POST", base_url, end_point, data={"symbol": symbol})

    async def put_sapi_v1_user_data_stream_isolated(self, symbol: str, listen_key: str):
        """
        https://developers.binance.com/docs/margin_trading/trade-data-stream/Keepalive-Isolated-Margin-User-Data-Stream
        """
        base_url = BinanceAccountType.ISOLATED_MARGIN.base_url
        end_point = "/sapi/v1/userDataStream/isolated"
        return await self._fetch(
            "PUT", base_url, end_point, data={"symbol": symbol, "listenKey": listen_key}
        )

    async def post_fapi_v1_listen_key(self):
        """
        https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Start-User-Data-Stream
        """
        base_url = (
            BinanceAccountType.USD_M_FUTURE.base_url
            if not self._testnet
            else BinanceAccountType.USD_M_FUTURE_TESTNET.base_url
        )
        end_point = "/fapi/v1/listenKey"
        return await self._fetch("POST", base_url, end_point)

    async def put_fapi_v1_listen_key(self):
        """
        https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-streams/Keepalive-User-Data-Stream
        """
        base_url = (
            BinanceAccountType.USD_M_FUTURE.base_url
            if not self._testnet
            else BinanceAccountType.USD_M_FUTURE_TESTNET.base_url
        )
        end_point = "/fapi/v1/listenKey"
        return await self._fetch("PUT", base_url, end_point)
    
    async def post_papi_v1_listen_key(self):
        """
        https://developers.binance.com/docs/derivatives/portfolio-margin/user-data-streams/Start-User-Data-Stream
        """
        base_url = BinanceAccountType.PORTFOLIO_MARGIN.base_url
        end_point = "/papi/v1/listenKey"
        return await self._fetch("POST", base_url, end_point)
    
    async def put_papi_v1_listen_key(self):
        """
        https://developers.binance.com/docs/derivatives/portfolio-margin/user-data-streams/Keepalive-User-Data-Stream
        """
        base_url = BinanceAccountType.PORTFOLIO_MARGIN.base_url
        end_point = "/papi/v1/listenKey"
        return await self._fetch("PUT", base_url, end_point)
    
    async def post_sapi_v1_margin_order(
        self,
        symbol: str,
        side: Literal["BUY", "SELL"],
        type: Literal["LIMIT", "MARKET"],
        **kwargs,
    ):
        """
        https://developers.binance.com/docs/margin_trading/trade/Margin-Account-New-Order
        """
        base_url = BinanceAccountType.MARGIN.base_url
        end_point = "/sapi/v1/margin/order"
        data = {
            "symbol": symbol,
            "side": side,
            "type": type,
            **kwargs,
        }
        return await self._fetch("POST", base_url, end_point, data=data, signed=True)

    async def post_api_v3_order(
        self,
        symbol: str,
        side: Literal["BUY", "SELL"],
        type: Literal["LIMIT", "MARKET"],
        **kwargs,
    ):
        """
        https://developers.binance.com/docs/binance-spot-api-docs/rest-api/public-api-endpoints#new-order-trade
        """
        base_url = (
            BinanceAccountType.SPOT.base_url
            if not self._testnet
            else BinanceAccountType.SPOT_TESTNET.base_url
        )
        end_point = "/api/v3/order"
        data = {
            "symbol": symbol,
            "side": side,
            "type": type,
            **kwargs,
        }
        return await self._fetch("POST", base_url, end_point, data=data, signed=True)
    
    async def post_fapi_v1_order(
        self,
        symbol: str,
        side: Literal["BUY", "SELL"],
        type: Literal["LIMIT", "MARKET"],
        **kwargs,
    ):
        """
        https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api
        """
        base_url = BinanceAccountType.USD_M_FUTURE.base_url if not self._testnet else BinanceAccountType.USD_M_FUTURE_TESTNET.base_url
        end_point = "/fapi/v1/order"
        data = {
            "symbol": symbol,
            "side": side,
            "type": type,
            **kwargs,
        }
        return await self._fetch("POST", base_url, end_point, data=data, signed=True)
    
    async def post_dapi_v1_order(
        self,
        symbol: str,
        side: Literal["BUY", "SELL"],
        type: Literal["LIMIT", "MARKET"],
        **kwargs,
    ):
        """
        https://developers.binance.com/docs/derivatives/coin-margined-futures/trade
        """
        base_url = BinanceAccountType.COIN_M_FUTURE.base_url if not self._testnet else BinanceAccountType.COIN_M_FUTURE_TESTNET.base_url
        end_point = "/dapi/v1/order"
        data = {
            "symbol": symbol,
            "side": side,
            "type": type,
            **kwargs,
        }
        return await self._fetch("POST", base_url, end_point, data=data, signed=True)
    
    async def post_papi_v1_um_order(
        self,
        symbol: str,
        side: Literal["BUY", "SELL"],
        type: Literal["LIMIT", "MARKET"],
        **kwargs,
    ):
        """
        https://developers.binance.com/docs/derivatives/portfolio-margin/trade
        """
        base_url = BinanceAccountType.PORTFOLIO_MARGIN.base_url
        end_point = "/papi/v1/um/order"
        
        data = {
            "symbol": symbol,
            "side": side,
            "type": type,
            **kwargs,
        }
        return await self._fetch("POST", base_url, end_point, data=data, signed=True)
    
    async def post_papi_v1_cm_order(
        self,
        symbol: str,
        side: Literal["BUY", "SELL"],
        type: Literal["LIMIT", "MARKET"],
        **kwargs,
    ):
        """
        https://developers.binance.com/docs/derivatives/portfolio-margin/trade/New-CM-Order
        """
        base_url = BinanceAccountType.PORTFOLIO_MARGIN.base_url
        end_point = "/papi/v1/cm/order"
        
        data = {
            "symbol": symbol,
            "side": side,
            "type": type,
            **kwargs,
        }
        return await self._fetch("POST", base_url, end_point, data=data, signed=True)
    
    async def post_papi_v1_margin_order(
        self,
        symbol: str,
        side: Literal["BUY", "SELL"],
        type: Literal["LIMIT", "MARKET"],
        **kwargs,
    ):
        """
        https://developers.binance.com/docs/derivatives/portfolio-margin/trade/New-Margin-Order
        """
        base_url = BinanceAccountType.PORTFOLIO_MARGIN.base_url
        end_point = "/papi/v1/margin/order"
        
        data = {
            "symbol": symbol,
            "side": side,
            "type": type,
            **kwargs,
        }
        return await self._fetch("POST", base_url, end_point, data=data, signed=True)
    
    
