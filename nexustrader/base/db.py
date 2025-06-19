import asyncio
from abc import ABC, abstractmethod
from typing import Dict, Set, List, Optional, Type

from nexustrader.schema import Order, Position, AlgoOrder, Balance, AccountBalance
from nexustrader.constants import AccountType, ExchangeType


class StorageBackend(ABC):
    def __init__(
        self, strategy_id: str, user_id: str, table_prefix: str, log, **kwargs
    ):
        self.strategy_id = strategy_id
        self.user_id = user_id
        self.table_prefix = table_prefix
        self._log = log
        self._storage_initialized = False

    @abstractmethod
    async def _init_conn(self) -> None:
        pass

    @abstractmethod
    async def _init_table(self) -> None:
        pass

    @abstractmethod
    async def close(self) -> None:
        pass

    @abstractmethod
    async def sync_orders(self, mem_orders: Dict[str, Order]) -> None:
        pass

    @abstractmethod
    async def sync_algo_orders(self, mem_algo_orders: Dict[str, AlgoOrder]) -> None:
        pass

    @abstractmethod
    async def sync_positions(self, mem_positions: Dict[str, Position]) -> None:
        pass

    @abstractmethod
    async def sync_open_orders(
        self,
        mem_open_orders: Dict[ExchangeType, Set[str]],
        mem_orders: Dict[str, Order],
    ) -> None:
        pass

    @abstractmethod
    async def sync_balances(
        self, mem_account_balance: Dict[AccountType, AccountBalance]
    ) -> None:
        pass

    @abstractmethod
    def get_order(
        self,
        uuid: str,
        mem_orders: Dict[str, Order],
        mem_algo_orders: Dict[str, AlgoOrder],
    ) -> Optional[Order | AlgoOrder]:
        pass

    @abstractmethod
    def get_symbol_orders(self, symbol: str) -> Set[str]:
        pass

    @abstractmethod
    def get_all_positions(self, exchange_id: ExchangeType) -> Dict[str, Position]:
        pass

    @abstractmethod
    def get_all_balances(self, account_type: AccountType) -> List[Balance]:
        pass

    async def _periodic_sync(
        self,
        mem_orders: Dict[str, Order],
        mem_algo_orders: Dict[str, AlgoOrder],
        mem_positions: Dict[str, Position],
        mem_open_orders: Dict[ExchangeType, Set[str]],
        mem_account_balance: Dict[AccountType, AccountBalance],
        sync_interval: int,
    ) -> None:
        while True:
            await self.sync_orders(mem_orders)
            await self.sync_algo_orders(mem_algo_orders)
            await self.sync_positions(mem_positions)
            await self.sync_open_orders(mem_open_orders, mem_orders)
            await self.sync_balances(mem_account_balance)
            await asyncio.sleep(sync_interval)

    async def start(self) -> None:
        await self._init_conn()
        await self._init_table()
        self._storage_initialized = True

    def _encode(self, obj: Order | Position | AlgoOrder | Balance) -> bytes:
        import msgspec

        return msgspec.json.encode(obj)

    def _decode(
        self, data: bytes, obj_type: Type[Order | Position | AlgoOrder | Balance]
    ) -> Order | Position | AlgoOrder | Balance:
        import msgspec

        return msgspec.json.decode(data, type=obj_type)
