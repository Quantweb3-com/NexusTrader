from enum import Enum

from nexustrader.constants import AccountType


class BitgetAccountType(AccountType):
    LIVE = 0
    DEMO = 1
    SPOT_MOCK = 2
    LINEAR_MOCK = 3
    INVERSE_MOCK = 4

    @property
    def exchange_id(self):
        return "bitget"

    @property
    def testnet(self):
        return self == self.DEMO

    @property
    def stream_url(self):
        if self.testnet:
            return "wss://ws.bitget.com/v2/ws"
        else:
            return "wss://ws.bitget.com/v2/ws"

    @property
    def is_mock(self):
        return self in (self.SPOT_MOCK, self.LINEAR_MOCK, self.INVERSE_MOCK)

    @property
    def is_linear_mock(self):
        return self == self.LINEAR_MOCK

    @property
    def is_inverse_mock(self):
        return self == self.INVERSE_MOCK

    @property
    def is_spot_mock(self):
        return self == self.SPOT_MOCK


class BitgetInstType(Enum):
    SPOT = "SPOT"
    USDT_FUTURES = "USDT-FUTURES"
    COIN_FUTURES = "COIN-FUTURES"
    USDC_FUTURES = "USDC-FUTURES"
    SUSDT_FUTURES = "SUSD-FUTURES"
    SUSDC_FUTURES = "SUSDC-FUTURES"
    SCOIN_FUTURES = "SCOIN-FUTURES"


class BitgetKlineInterval(Enum):
    MINUTE_1 = "candle1m"
    MINUTE_5 = "candle5m"
    MINUTE_15 = "candle15m"
    MINUTE_30 = "candle30m"
    HOUR_1 = "candle1H"
    HOUR_4 = "candle4H"
    HOUR_6 = "candle6Hutc"
    HOUR_12 = "candle12Hutc"
    DAY_1 = "candle1Dutc"
