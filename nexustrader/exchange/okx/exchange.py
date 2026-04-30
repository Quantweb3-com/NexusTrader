from typing import Any, Dict
from nexustrader.base import ExchangeManager
import ccxt
import orjson
import msgspec
from nexustrader.constants import InstrumentType
from nexustrader.exchange.okx.schema import OkxMarket, OkxMarketInfo
from nexustrader.schema import Limit, LimitMinMax, MarginMode, Precision


class OkxExchangeManager(ExchangeManager):
    api: ccxt.okx
    market: Dict[str, OkxMarket] # symbol -> okx market
    market_id: Dict[str, str] # symbol -> exchange symbol id

    def __init__(self, config: Dict[str, Any] = None):
        config = config or {}
        config["exchange_id"] = config.get("exchange_id", "okx")
        options = dict(config.get("options") or {})
        options.setdefault("fetchMarkets", ["spot", "future", "swap"])
        config["options"] = options
        super().__init__(config)
        self.passphrase = config.get("password", None)

    def load_markets(self):
        for raw_market in self._fetch_raw_markets():
            try:
                mkt = self._parse_raw_market(raw_market)
                if mkt is None:
                    continue

                if (mkt.spot or mkt.linear or mkt.inverse or mkt.future) and not mkt.option:
                    symbol = self._parse_symbol(mkt, exchange_suffix="OKX")
                    mkt.symbol = symbol
                    self.market[symbol] = mkt
                    self.market_id[mkt.id] = symbol # since okx symbol id is identical, no need to distinguish spot, linear, inverse

            except Exception as e:
                print(f"Error: {e}, {raw_market.get('instId')}, {raw_market}")
                continue

    def _fetch_raw_markets(self) -> list[dict[str, Any]]:
        markets: list[dict[str, Any]] = []
        for inst_type in ("SPOT", "FUTURES", "SWAP"):
            response = self.api.publicGetPublicInstruments({"instType": inst_type})
            markets.extend(response.get("data", []))
        return markets

    def _parse_raw_market(self, raw_market: dict[str, Any]) -> OkxMarket | None:
        inst_id = raw_market.get("instId")
        inst_type = raw_market.get("instType")
        if not inst_id or inst_type not in {"SPOT", "FUTURES", "SWAP"}:
            return None

        base, quote = self._parse_base_quote(raw_market)
        if not base or not quote:
            return None

        is_spot = inst_type == "SPOT"
        is_future = inst_type == "FUTURES"
        is_swap = inst_type == "SWAP"
        ct_type = raw_market.get("ctType")
        settle = raw_market.get("settleCcy") or None
        linear = False if is_spot else ct_type == "linear"
        inverse = False if is_spot else ct_type == "inverse"

        if not is_spot and not (linear or inverse):
            linear = quote in {"USDT", "USDC"} or settle in {"USDT", "USDC"}
            inverse = not linear

        info = msgspec.json.decode(orjson.dumps(raw_market), type=OkxMarketInfo)
        return OkxMarket(
            id=inst_id,
            lowercaseId=inst_id.lower(),
            symbol=self._raw_symbol(base, quote, settle, inst_type, inst_id),
            base=base,
            quote=quote,
            settle=settle,
            baseId=base,
            quoteId=quote,
            settleId=settle,
            type=self._instrument_type(inst_type),
            spot=is_spot,
            margin=False,
            swap=is_swap,
            future=is_future,
            option=False,
            index=None,
            active=raw_market.get("state") == "live",
            contract=not is_spot,
            linear=linear,
            inverse=inverse,
            subType=self._sub_type(linear, inverse),
            taker=0.0005,
            maker=0.0002,
            contractSize=self._to_float(raw_market.get("ctVal")),
            expiry=self._to_int(raw_market.get("expTime")),
            expiryDatetime=None,
            strike=None,
            optionType=None,
            precision=Precision(
                amount=self._to_float(raw_market.get("lotSz")),
                price=self._to_float(raw_market.get("tickSz")),
            ),
            limits=Limit(
                leverage=LimitMinMax(min=1.0, max=self._to_float(raw_market.get("lever"))),
                amount=LimitMinMax(
                    min=self._to_float(raw_market.get("minSz")),
                    max=self._to_float(raw_market.get("maxLmtSz")),
                ),
                price=LimitMinMax(min=self._to_float(raw_market.get("tickSz")), max=None),
                cost=LimitMinMax(min=None, max=self._to_float(raw_market.get("maxLmtAmt"))),
            ),
            marginModes=MarginMode(isolated=None, cross=None),
            created=self._to_int(raw_market.get("listTime")),
            tierBased=None,
            percentage=None,
            info=info,
        )

    def _parse_base_quote(self, raw_market: dict[str, Any]) -> tuple[str | None, str | None]:
        if raw_market.get("instType") == "SPOT":
            return raw_market.get("baseCcy") or None, raw_market.get("quoteCcy") or None

        family = raw_market.get("instFamily")
        if not family:
            inst_id = raw_market.get("instId", "")
            family = inst_id.removesuffix("-SWAP").rsplit("-", 1)[0]
        parts = family.split("-")
        if len(parts) < 2:
            return None, None
        return parts[0], parts[1]

    @staticmethod
    def _instrument_type(inst_type: str) -> InstrumentType:
        if inst_type == "SPOT":
            return InstrumentType.SPOT
        if inst_type == "FUTURES":
            return InstrumentType.FUTURE
        return InstrumentType.SWAP

    @staticmethod
    def _sub_type(linear: bool, inverse: bool) -> InstrumentType | None:
        if linear:
            return InstrumentType.LINEAR
        if inverse:
            return InstrumentType.INVERSE
        return None

    @staticmethod
    def _raw_symbol(
        base: str, quote: str, settle: str | None, inst_type: str, inst_id: str
    ) -> str:
        if inst_type == "SPOT":
            return f"{base}/{quote}"
        if inst_type == "FUTURES":
            return inst_id
        return f"{base}/{quote}:{settle or quote}"

    @staticmethod
    def _to_float(value: Any) -> float | None:
        if value in (None, ""):
            return None
        return float(value)

    @staticmethod
    def _to_int(value: Any) -> int | None:
        if value in (None, ""):
            return None
        return int(value)
