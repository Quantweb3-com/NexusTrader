import hmac
import hashlib
import msgspec

from typing import Any, Dict
from urllib.parse import urljoin, urlencode
from curl_cffi import requests

from nexustrader.base import ApiClient, RetryManager


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