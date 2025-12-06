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


# ACCOUNT 
# Get Account List (Spot)
# https://www.kucoin.com/docs-new/rest/account-info/account-funding/get-account-list-spot

# Get Account Detail (Spot)
# https://www.kucoin.com/docs-new/rest/account-info/account-funding/get-account-detail-spot


# Get Account Futures (Futures)
# https://www.kucoin.com/docs-new/rest/account-info/account-funding/get-account-futures

# SPOT

# Get Klines
# https://www.kucoin.com/docs-new/rest/spot-trading/market-data/get-klines

# Add Orders
# https://www.kucoin.com/docs-new/rest/spot-trading/orders/add-order

# Batch Add Orders
# https://www.kucoin.com/docs-new/rest/spot-trading/orders/batch-add-orders

# Cancel Order by ClientOid
# https://www.kucoin.com/docs-new/rest/spot-trading/orders/cancel-order-by-clientoid

# cancel all orders by symbol
# https://www.kucoin.com/docs-new/rest/spot-trading/orders/cancel-all-orders-by-symbol

# Modify Order
# https://www.kucoin.com/docs-new/rest/spot-trading/orders/modify-order


# FUTURES

# Get Klines
# https://www.kucoin.com/docs-new/rest/futures-trading/market-data/get-klines

# The ORDER endpoints for futures trading are the same for spot trading

# Get Position Mode
# https://www.kucoin.com/docs-new/rest/futures-trading/positions/get-position-mode # only allowed one-way mode

# Get Position List
# https://www.kucoin.com/docs-new/rest/futures-trading/positions/get-position-list