import hashlib
import hmac
import orjson

from typing import Any, Dict
from urllib.parse import urljoin, urlencode


from nexustrader.core.log import SpdLog
from nexustrader.constants import OrderSide, OrderType
from nexustrader.exchange.binance.error import BinanceClientError, BinanceServerError
from nexustrader.core.nautilius_core import (
    LiveClock,
    HttpClient,
    HttpMethod,
    HttpResponse,
)


class BinanceHttpClient:
    def __init__(
        self,
        api_key: str,
        secret: str,
        testnet: bool = False,
    ):
        self._api_key = api_key
        self._secret = secret
        self._testnet = testnet
        self._clock = LiveClock()
        self._log = SpdLog.get_logger(type(self).__name__, level="INFO", flush=True)

        self._headers = {
            "Content-Type": "application/json",
            "User-Agent": "TradingBot/1.0",
            "X-MBX-APIKEY": api_key,
        }

        self._client = HttpClient()

    def _generate_signature(self, query: str) -> str:
        signature = hmac.new(
            self._secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        return signature

    async def _fetch(
        self,
        method: HttpMethod,
        base_url: str,
        endpoint: str,
        payload: Dict[str, Any] = None,
        signed: bool = False,
    ):
        url = urljoin(base_url, endpoint)
        payload = payload or {}
        payload["timestamp"] = self._clock.timestamp_ms()
        payload = urlencode(payload)

        if signed:
            signature = self._generate_signature(payload)
            payload += f"&signature={signature}"

        url += f"?{payload}"
        self._log.debug(f"Request: {url}")

        response: HttpResponse = await self._client.request(
            method=method,
            url=url,
            headers=self._headers,
        )

        if 400 <= response.status < 500:
            raise BinanceClientError(
                status=response.status,
                message=orjson.loads(response.body) if response.body else None,
                headers=response.headers,
            )
        elif response.status >= 500:
            raise BinanceServerError(
                status=response.status,
                message=orjson.loads(response.body) if response.body else None,
                headers=response.headers,
            )
        return orjson.loads(response.body)

    async def post_fapi_v1_order(
        self,
        symbol: str,
        side: OrderSide,
        type: OrderType,
        **kwargs,
    ):
        if self._testnet:
            base_url = "https://testnet.binancefuture.com"
        else:
            base_url = "https://fapi.binance.com"

        end_point = "/fapi/v1/order"

        payload = {
            "symbol": symbol,
            "side": side.value,
            "type": type.value,
            **kwargs,
        }

        return await self._fetch(
            HttpMethod.POST, base_url, end_point, payload, signed=True
        )

    async def post_papi_v1_um_order(
        self,
        symbol: str,
        side: OrderSide,
        type: OrderType,
        **kwargs,
    ):
        base_url = "https://papi.binance.com"
        end_point = "/papi/v1/um/order"

        payload = {
            "symbol": symbol,
            "side": side.value,
            "type": type.value,
            **kwargs,
        }

        return await self._fetch(
            HttpMethod.POST, base_url, end_point, payload, signed=True
        )
