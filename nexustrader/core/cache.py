import msgspec
import asyncio
import re
from typing import Dict, Set, Type, List, Optional
from collections import defaultdict
from returns.maybe import maybe
from pathlib import Path

from nexustrader.schema import (
    Order,
    Position,
    ExchangeType,
    Kline,
    BookL1,
    Trade,
    AlgoOrder,
    AccountBalance,
    Balance,
    FundingRate,
    IndexPrice,
    MarkPrice,
    BookL2,
)
from nexustrader.constants import STATUS_TRANSITIONS, AccountType, KlineInterval
from nexustrader.core.entity import TaskManager
from nexustrader.core.nautilius_core import LiveClock, MessageBus, Logger
from nexustrader.constants import StorageType
from nexustrader.backends import SQLiteBackend, PostgreSQLBackend


class AsyncCache:
    def __init__(
        self,
        strategy_id: str,
        user_id: str,
        msgbus: MessageBus,
        task_manager: TaskManager,
        storage_backend: StorageType = StorageType.SQLITE,
        db_path: str = ".keys/cache.db",
        sync_interval: int = 60,  # seconds
        expired_time: int = 3600,  # seconds
    ):
        parent_dir = Path(db_path).parent
        if not parent_dir.exists():
            parent_dir.mkdir(parents=True, exist_ok=True)

        self.strategy_id = strategy_id
        self.user_id = user_id
        self._storage_backend = storage_backend
        self._db_path = db_path

        self._log = Logger(name=type(self).__name__)
        self._clock = LiveClock()

        # in-memory save
        self._mem_closed_orders: Dict[str, bool] = {}  # uuid -> bool
        self._mem_orders: Dict[str, Order] = {}  # uuid -> Order
        self._mem_algo_orders: Dict[str, AlgoOrder] = {}  # uuid -> AlgoOrder
        self._mem_open_orders: Dict[ExchangeType, Set[str]] = defaultdict(
            set
        )  # exchange_id -> set(uuid)
        self._mem_symbol_open_orders: Dict[str, Set[str]] = defaultdict(
            set
        )  # symbol -> set(uuid)
        self._mem_symbol_orders: Dict[str, Set[str]] = defaultdict(
            set
        )  # symbol -> set(uuid)
        self._mem_positions: Dict[str, Position] = {}  # symbol -> Position
        self._mem_account_balance: Dict[AccountType, AccountBalance] = defaultdict(
            AccountBalance
        )

        # set params
        self._sync_interval = sync_interval  # sync interval
        self._expired_time = expired_time  # expire time
        self._task_manager = task_manager

        self._kline_cache: Dict[str, Kline] = {}
        self._bookl1_cache: Dict[str, BookL1] = {}
        self._trade_cache: Dict[str, Trade] = {}
        self._bookl2_cache: Dict[str, BookL2] = {}
        self._funding_rate_cache: Dict[str, FundingRate] = {}
        self._index_price_cache: Dict[str, IndexPrice] = {}
        self._mark_price_cache: Dict[str, MarkPrice] = {}

        self._msgbus = msgbus
        self._msgbus.subscribe(topic="kline", handler=self._update_kline_cache)
        self._msgbus.subscribe(topic="bookl1", handler=self._update_bookl1_cache)
        self._msgbus.subscribe(topic="trade", handler=self._update_trade_cache)
        self._msgbus.subscribe(topic="bookl2", handler=self._update_bookl2_cache)
        self._msgbus.subscribe(
            topic="funding_rate", handler=self._update_funding_rate_cache
        )
        self._msgbus.subscribe(
            topic="index_price", handler=self._update_index_price_cache
        )
        self._msgbus.subscribe(
            topic="mark_price", handler=self._update_mark_price_cache
        )

        self._storage_initialized = False
        self._table_prefix = self.safe_table_name(f"{self.strategy_id}_{self.user_id}")
        self._backend = None

    ################# # base functions ####################

    @staticmethod
    def safe_table_name(name: str) -> str:
        name = re.sub(r"[^a-zA-Z0-9_]", "_", name)
        return name.lower()

    def _encode(self, obj: Order | Position | AlgoOrder) -> bytes:
        return msgspec.json.encode(obj)

    def _decode(
        self, data: bytes, obj_type: Type[Order | Position | AlgoOrder]
    ) -> Order | Position | AlgoOrder:
        return msgspec.json.decode(data, type=obj_type)

    async def _init_storage(self):
        """Initialize the storage backend"""
        if self._storage_backend == StorageType.SQLITE:
            self._backend = SQLiteBackend(
                strategy_id=self.strategy_id,
                user_id=self.user_id,
                table_prefix=self._table_prefix,
                log=self._log,
                db_path=self._db_path,
            )
        elif self._storage_backend == StorageType.POSTGRESQL:
            self._backend = PostgreSQLBackend(
                strategy_id=self.strategy_id,
                user_id=self.user_id,
                table_prefix=self._table_prefix,
                log=self._log,
            )

        await self._backend.start()
        self._storage_initialized = True

    async def start(self):
        """Start the cache"""
        await self._init_storage()
        self._task_manager.create_task(self._periodic_sync())

    async def _periodic_sync(self):
        """Periodically sync the cache"""
        while True:
            await self._backend.sync_orders(self._mem_orders)
            await self._backend.sync_algo_orders(self._mem_algo_orders)
            await self._backend.sync_positions(self._mem_positions)
            await self._backend.sync_open_orders(
                self._mem_open_orders, self._mem_orders
            )
            await self._backend.sync_balances(self._mem_account_balance)
            self._cleanup_expired_data()
            await asyncio.sleep(self._sync_interval)

    async def sync_orders(self):
        await self._backend.sync_orders(self._mem_orders)

    async def sync_algo_orders(self):
        await self._backend.sync_algo_orders(self._mem_algo_orders)

    async def sync_positions(self):
        await self._backend.sync_positions(self._mem_positions)

    async def sync_open_orders(self):
        await self._backend.sync_open_orders(self._mem_open_orders, self._mem_orders)

    async def sync_balances(self):
        await self._backend.sync_balances(self._mem_account_balance)

    def _cleanup_expired_data(self):
        """Cleanup expired data"""
        current_time = self._clock.timestamp_ms()
        expire_before = current_time - self._expired_time * 1000

        expired_orders = []
        for uuid, order in self._mem_orders.copy().items():
            if order.timestamp < expire_before:
                expired_orders.append(uuid)

                if not order.is_closed:
                    self._log.warning(f"order {uuid} is not closed, but expired")

        for uuid in expired_orders:
            del self._mem_orders[uuid]
            self._mem_closed_orders.pop(uuid, None)
            self._log.debug(f"removing order {uuid} from memory")
            for symbol, order_set in self._mem_symbol_orders.copy().items():
                self._log.debug(f"removing order {uuid} from symbol {symbol}")
                order_set.discard(uuid)

        expired_algo_orders = [
            uuid
            for uuid, algo_order in self._mem_algo_orders.copy().items()
            if algo_order.timestamp < expire_before
        ]
        for uuid in expired_algo_orders:
            del self._mem_algo_orders[uuid]
            self._log.debug(f"removing algo order {uuid} from memory")

    async def close(self):
        """关闭缓存"""
        if self._storage_initialized and self._backend:
            await self._backend.sync_orders(self._mem_orders)
            await self._backend.sync_algo_orders(self._mem_algo_orders)
            await self._backend.sync_positions(self._mem_positions)
            await self._backend.sync_open_orders(
                self._mem_open_orders, self._mem_orders
            )
            await self._backend.sync_balances(self._mem_account_balance)
            await self._backend.close()

    ################ # cache public data  ###################

    def _update_kline_cache(self, kline: Kline):
        key = f"{kline.symbol}-{kline.interval.value}"
        self._kline_cache[key] = kline

    def _update_bookl1_cache(self, bookl1: BookL1):
        self._bookl1_cache[bookl1.symbol] = bookl1

    def _update_trade_cache(self, trade: Trade):
        self._trade_cache[trade.symbol] = trade

    def _update_bookl2_cache(self, bookl2: BookL2):
        self._bookl2_cache[bookl2.symbol] = bookl2

    def _update_funding_rate_cache(self, funding_rate: FundingRate):
        self._funding_rate_cache[funding_rate.symbol] = funding_rate

    def _update_index_price_cache(self, index_price: IndexPrice):
        self._index_price_cache[index_price.symbol] = index_price

    def _update_mark_price_cache(self, mark_price: MarkPrice):
        self._mark_price_cache[mark_price.symbol] = mark_price

    def kline(self, symbol: str, interval: KlineInterval) -> Optional[Kline]:
        """
        Retrieve a Kline object from the cache by symbol.

        :param symbol: The symbol of the Kline to retrieve.
        :return: The Kline object if found, otherwise None.
        """
        key = f"{symbol}-{interval.value}"
        return self._kline_cache.get(key, None)

    def bookl1(self, symbol: str) -> Optional[BookL1]:
        """
        Retrieve a BookL1 object from the cache by symbol.

        :param symbol: The symbol of the BookL1 to retrieve.
        :return: The BookL1 object if found, otherwise None.
        """
        return self._bookl1_cache.get(symbol, None)

    def bookl2(self, symbol: str) -> Optional[BookL2]:
        """
        Retrieve a BookL2 object from the cache by symbol.
        """
        return self._bookl2_cache.get(symbol, None)

    def trade(self, symbol: str) -> Optional[Trade]:
        """
        Retrieve a Trade object from the cache by symbol.

        :param symbol: The symbol of the Trade to retrieve.
        :return: The Trade object if found, otherwise None.
        """
        return self._trade_cache.get(symbol, None)

    def funding_rate(self, symbol: str) -> Optional[FundingRate]:
        """
        Retrieve a FundingRate object from the cache by symbol.
        """
        return self._funding_rate_cache.get(symbol, None)

    def index_price(self, symbol: str) -> Optional[IndexPrice]:
        """
        Retrieve an IndexPrice object from the cache by symbol.
        """
        return self._index_price_cache.get(symbol, None)

    def mark_price(self, symbol: str) -> Optional[MarkPrice]:
        """
        Retrieve a MarkPrice object from the cache by symbol.
        """
        return self._mark_price_cache.get(symbol, None)

    ################ # cache private data  ###################

    def _check_status_transition(self, order: Order):
        previous_order = self._mem_orders.get(order.uuid)
        if not previous_order:
            return True

        if order.status not in STATUS_TRANSITIONS[previous_order.status]:
            self._log.warning(
                f"Order id: {order.uuid} Invalid status transition: {previous_order.status} -> {order.status}"
            )
            return False

        return True

    def _apply_position(self, position: Position):
        if position.is_closed:
            self._mem_positions.pop(position.symbol, None)
        else:
            self._mem_positions[position.symbol] = position

    def _apply_balance(self, account_type: AccountType, balances: List[Balance]):
        self._mem_account_balance[account_type]._apply(balances)

    def get_balance(self, account_type: AccountType) -> AccountBalance:
        return self._mem_account_balance[account_type]

    @maybe
    def get_position(self, symbol: str) -> Optional[Position]:
        if position := self._mem_positions.get(symbol, None):
            return position

    def get_all_positions(
        self, exchange: Optional[ExchangeType] = None
    ) -> Dict[str, Position]:
        positions = {
            symbol: position
            for symbol, position in self._mem_positions.copy().items()
            if (
                (exchange is None or position.exchange == exchange)
                and position.is_opened
            )
        }
        return positions

    def _order_initialized(self, order: Order | AlgoOrder):
        if isinstance(order, AlgoOrder):
            self._mem_algo_orders[order.uuid] = order
        else:
            if not self._check_status_transition(order):
                return
            self._mem_orders[order.uuid] = order
            self._mem_open_orders[order.exchange].add(order.uuid)
            self._mem_symbol_orders[order.symbol].add(order.uuid)
            self._mem_symbol_open_orders[order.symbol].add(order.uuid)

    def _order_status_update(self, order: Order | AlgoOrder):
        if isinstance(order, AlgoOrder):
            self._mem_algo_orders[order.uuid] = order
        else:
            if not self._check_status_transition(order):
                return
            self._mem_orders[order.uuid] = order
            if order.is_closed:
                self._mem_open_orders[order.exchange].discard(order.uuid)
                self._mem_symbol_open_orders[order.symbol].discard(order.uuid)

    # NOTE: this function is not for user to call, it is for internal use
    def _get_all_balances_from_db(self, account_type: AccountType) -> List[Balance]:
        return self._backend.get_all_balances(account_type)

    # NOTE: this function is not for user to call, it is for internal use
    def _get_all_positions_from_db(
        self, exchange_id: ExchangeType
    ) -> Dict[str, Position]:
        return self._backend.get_all_positions(exchange_id)

    @maybe
    def get_order(self, uuid: str) -> Optional[Order | AlgoOrder]:
        return self._backend.get_order(uuid, self._mem_orders, self._mem_algo_orders)

    def get_symbol_orders(self, symbol: str, in_mem: bool = True) -> Set[str]:
        """Get all orders for a symbol from memory and storage"""
        memory_orders = self._mem_symbol_orders.get(symbol, set())
        if not in_mem:
            storage_orders = self._backend.get_symbol_orders(symbol)
            return memory_orders.union(storage_orders)
        return memory_orders

    def get_open_orders(
        self, symbol: str | None = None, exchange: ExchangeType | None = None
    ) -> Set[str]:
        if symbol is not None:
            return self._mem_symbol_open_orders[symbol].copy()
        elif exchange is not None:
            return self._mem_open_orders[exchange].copy()
        else:
            raise ValueError("Either `symbol` or `exchange` must be specified")
