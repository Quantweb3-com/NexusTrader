from typing import Dict, Set, List, Optional

from nexustrader.base.db import StorageBackend
from nexustrader.schema import (
    Order,
    Position,
    AlgoOrder,
    Balance,
    AccountBalance,
    InstrumentId,
)
from nexustrader.constants import AccountType, ExchangeType
from nexustrader.core.entity import RedisClient


class RedisBackend(StorageBackend):
    def __init__(
        self, strategy_id: str, user_id: str, table_prefix: str, log, **kwargs
    ):
        super().__init__(strategy_id, user_id, table_prefix, log, **kwargs)
        self._r_async = None
        self._r = None

    async def _init_conn(self) -> None:
        self._r_async = RedisClient.get_async_client()
        self._r = RedisClient.get_client()

    async def _init_table(self) -> None:
        pass

    async def close(self) -> None:
        if self._r_async:
            await self._r_async.aclose()

    async def sync_orders(self, mem_orders: Dict[str, Order]) -> None:
        orders_key = f"strategy:{self.strategy_id}:user_id:{self.user_id}:orders"
        for uuid, order in mem_orders.copy().items():
            await self._r_async.hset(orders_key, uuid, self._encode(order))

    async def sync_algo_orders(self, mem_algo_orders: Dict[str, AlgoOrder]) -> None:
        algo_orders_key = (
            f"strategy:{self.strategy_id}:user_id:{self.user_id}:algo_orders"
        )
        for uuid, algo_order in mem_algo_orders.copy().items():
            await self._r_async.hset(algo_orders_key, uuid, self._encode(algo_order))

    async def sync_positions(self, mem_positions: Dict[str, Position]) -> None:
        for symbol, position in mem_positions.copy().items():
            key = f"strategy:{self.strategy_id}:user_id:{self.user_id}:exchange:{position.exchange.value}:symbol_positions:{symbol}"
            await self._r_async.set(key, self._encode(position))

    async def sync_open_orders(
        self,
        mem_open_orders: Dict[ExchangeType, Set[str]],
        mem_orders: Dict[str, Order],
    ) -> None:
        for exchange, open_order_uuids in mem_open_orders.copy().items():
            open_orders_key = f"strategy:{self.strategy_id}:user_id:{self.user_id}:exchange:{exchange.value}:open_orders"

            await self._r_async.delete(open_orders_key)

            if open_order_uuids:
                await self._r_async.sadd(open_orders_key, *open_order_uuids)

        for symbol, uuids in self._get_symbol_orders_mapping(mem_orders).items():
            instrument_id = InstrumentId.from_str(symbol)
            key = f"strategy:{self.strategy_id}:user_id:{self.user_id}:exchange:{instrument_id.exchange.value}:symbol_orders:{symbol}"
            await self._r_async.delete(key)
            if uuids:
                await self._r_async.sadd(key, *uuids)

        for symbol, uuids in self._get_symbol_open_orders_mapping(
            mem_open_orders, mem_orders
        ).items():
            instrument_id = InstrumentId.from_str(symbol)
            key = f"strategy:{self.strategy_id}:user_id:{self.user_id}:exchange:{instrument_id.exchange.value}:symbol_open_orders:{symbol}"
            await self._r_async.delete(key)
            if uuids:
                await self._r_async.sadd(key, *uuids)

    async def sync_balances(
        self, mem_account_balance: Dict[AccountType, AccountBalance]
    ) -> None:
        for account_type, balance in mem_account_balance.copy().items():
            for asset, amount in balance.balances.items():
                key = f"strategy:{self.strategy_id}:user_id:{self.user_id}:account_type:{account_type.value}:asset_balance:{asset}"
                await self._r_async.set(key, self._encode(amount))

    def get_order(
        self,
        uuid: str,
        mem_orders: Dict[str, Order],
        mem_algo_orders: Dict[str, AlgoOrder],
    ) -> Optional[Order | AlgoOrder]:
        if uuid.startswith("ALGO-"):
            if order := mem_algo_orders.get(uuid):
                return order
            key = f"strategy:{self.strategy_id}:user_id:{self.user_id}:algo_orders"
            obj_type = AlgoOrder
            mem_dict = mem_algo_orders
        else:
            if order := mem_orders.get(uuid):
                return order
            key = f"strategy:{self.strategy_id}:user_id:{self.user_id}:orders"
            obj_type = Order
            mem_dict = mem_orders

        if raw_order := self._r.hget(key, uuid):
            order = self._decode(raw_order, obj_type)
            mem_dict[uuid] = order
            return order
        return None

    def get_symbol_orders(self, symbol: str) -> Set[str]:
        instrument_id = InstrumentId.from_str(symbol)
        key = f"strategy:{self.strategy_id}:user_id:{self.user_id}:exchange:{instrument_id.exchange.value}:symbol_orders:{instrument_id.symbol}"
        if redis_orders := self._r.smembers(key):
            return {uuid.decode() for uuid in redis_orders}
        return set()

    def get_all_positions(self, exchange_id: ExchangeType) -> Dict[str, Position]:
        positions = {}
        pattern = f"strategy:{self.strategy_id}:user_id:{self.user_id}:exchange:{exchange_id.value}:symbol_positions:*"
        keys = self._r.keys(pattern)
        for key in keys:
            if raw_position := self._r.get(key):
                position = self._decode(raw_position, Position)
                positions[position.symbol] = position
        return positions

    def get_all_balances(self, account_type: AccountType) -> List[Balance]:
        balances = []
        pattern = f"strategy:{self.strategy_id}:user_id:{self.user_id}:account_type:{account_type.value}:asset_balance:*"
        keys = self._r.keys(pattern)
        for key in keys:
            if raw_balance := self._r.get(key):
                balance: Balance = self._decode(raw_balance, Balance)
                balances.append(balance)
        return balances

    def _get_symbol_orders_mapping(
        self, mem_orders: Dict[str, Order]
    ) -> Dict[str, Set[str]]:
        symbol_orders = {}
        for uuid, order in mem_orders.items():
            if order.symbol not in symbol_orders:
                symbol_orders[order.symbol] = set()
            symbol_orders[order.symbol].add(uuid)
        return symbol_orders

    def _get_symbol_open_orders_mapping(
        self,
        mem_open_orders: Dict[ExchangeType, Set[str]],
        mem_orders: Dict[str, Order],
    ) -> Dict[str, Set[str]]:
        symbol_open_orders = {}
        for exchange, uuids in mem_open_orders.items():
            for uuid in uuids:
                order = mem_orders.get(uuid)
                if order:
                    if order.symbol not in symbol_open_orders:
                        symbol_open_orders[order.symbol] = set()
                    symbol_open_orders[order.symbol].add(uuid)
        return symbol_open_orders
