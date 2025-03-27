import msgspec
import asyncio
import aiosqlite
import sqlite3
import re
from decimal import Decimal
from typing import Dict, Set, Type, List, Optional
from collections import defaultdict
from returns.maybe import maybe
from pathlib import Path

from nexustrader.schema import (
    Order,
    Position,
    ExchangeType,
    InstrumentId,
    Kline,
    BookL1,
    Trade,
    AlgoOrder,
    AccountBalance,
    Balance,
)
from nexustrader.constants import STATUS_TRANSITIONS, AccountType, KlineInterval
from nexustrader.core.entity import TaskManager, RedisClient
from nexustrader.core.log import SpdLog
from nexustrader.core.registry import OrderRegistry
from nexustrader.core.nautilius_core import LiveClock, MessageBus
from nexustrader.constants import StorageBackend


class AsyncCache:
    def __init__(
        self,
        strategy_id: str,
        user_id: str,
        msgbus: MessageBus,
        task_manager: TaskManager,
        registry: OrderRegistry,
        storage_backend: StorageBackend = StorageBackend.SQLITE,
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

        self._log = SpdLog.get_logger(
            name=type(self).__name__, level="DEBUG", flush=True
        )
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

        self._msgbus = msgbus
        self._msgbus.subscribe(topic="kline", handler=self._update_kline_cache)
        self._msgbus.subscribe(topic="bookl1", handler=self._update_bookl1_cache)
        self._msgbus.subscribe(topic="trade", handler=self._update_trade_cache)

        self._storage_initialized = False
        self._registry = registry
        
        self._table_prefix = self.safe_table_name(f"{self.strategy_id}_{self.user_id}")

    ################# # base functions ####################
    
    @staticmethod
    def safe_table_name(name: str) -> str:
        name = re.sub(r'[^a-zA-Z0-9_]', '_', name)
        return name.lower()

    def _encode(self, obj: Order | Position | AlgoOrder) -> bytes:
        return msgspec.json.encode(obj)

    def _decode(
        self, data: bytes, obj_type: Type[Order | Position | AlgoOrder]
    ) -> Order | Position | AlgoOrder:
        return msgspec.json.decode(data, type=obj_type)

    async def _init_storage(self):
        """Initialize the storage backend"""
        if self._storage_backend == StorageBackend.REDIS:
            self._r_async = RedisClient.get_async_client()
            self._r = RedisClient.get_client()
        elif self._storage_backend == StorageBackend.SQLITE:
            db_path = Path(self._db_path)
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self._db_async = await aiosqlite.connect(str(db_path))
            self._db = sqlite3.connect(str(db_path))
            await self._init_sqlite_tables()
        self._storage_initialized = True

    async def _init_sqlite_tables(self):
        """Initialize the SQLite tables"""

        async with self._db_async.cursor() as cursor:
            await cursor.executescript(f"""
                CREATE TABLE IF NOT EXISTS {self._table_prefix}_orders (
                    timestamp INTEGER,
                    uuid TEXT PRIMARY KEY,
                    symbol TEXT,
                    side TEXT, 
                    type TEXT,
                    amount TEXT,
                    price REAL,
                    status TEXT,
                    data BLOB
                );
                
                CREATE INDEX IF NOT EXISTS idx_orders_symbol 
                ON {self._table_prefix}_orders(symbol);
                
                CREATE TABLE IF NOT EXISTS {self._table_prefix}_algo_orders (
                    timestamp INTEGER,
                    uuid TEXT PRIMARY KEY,
                    symbol TEXT,
                    data BLOB
                );
                
                CREATE INDEX IF NOT EXISTS idx_algo_orders_symbol 
                ON {self._table_prefix}_algo_orders(symbol);
                
                CREATE TABLE IF NOT EXISTS {self._table_prefix}_positions (
                    symbol PRIMARY KEY,
                    exchange TEXT,
                    side TEXT,
                    amount TEXT,
                    data BLOB
                );
                
                CREATE TABLE IF NOT EXISTS {self._table_prefix}_open_orders (
                    uuid PRIMARY KEY,
                    exchange TEXT,
                    symbol TEXT
                );
                
                CREATE TABLE IF NOT EXISTS {self._table_prefix}_balances (
                    asset TEXT,
                    account_type TEXT,
                    free TEXT,
                    locked TEXT,
                    PRIMARY KEY (asset, account_type)
                );
                
                CREATE TABLE IF NOT EXISTS {self._table_prefix}_pnl (
                    timestamp INTEGER PRIMARY KEY,
                    pnl REAL,
                    unrealized_pnl REAL
                );
            """)
            await self._db_async.commit()
    
    async def _sync_pnl(self, timestamp: int, pnl: float, unrealized_pnl: float):
        async with self._db_async.cursor() as cursor:
            await cursor.execute(f"INSERT INTO {self._table_prefix}_pnl (timestamp, pnl, unrealized_pnl) VALUES (?, ?, ?)", (timestamp, pnl, unrealized_pnl))
            await self._db_async.commit()

    async def start(self):
        """Start the cache"""
        await self._init_storage()
        self._task_manager.create_task(self._periodic_sync())

    async def _periodic_sync(self):
        """Periodically sync the cache"""
        while True:
            if self._storage_backend == StorageBackend.REDIS:
                await self._sync_to_redis()
            elif self._storage_backend == StorageBackend.SQLITE:
                await self._sync_to_sqlite()
            self._cleanup_expired_data()
            await asyncio.sleep(self._sync_interval)

    async def _sync_to_redis(self):
        """Sync the cache to Redis"""
        self._log.debug("syncing to redis")
        for uuid, order in self._mem_orders.copy().items():
            orders_key = f"strategy:{self.strategy_id}:user_id:{self.user_id}:orders"
            await self._r_async.hset(orders_key, uuid, self._encode(order))

        for uuid, algo_order in self._mem_algo_orders.copy().items():
            algo_orders_key = (
                f"strategy:{self.strategy_id}:user_id:{self.user_id}:algo_orders"
            )
            await self._r_async.hset(algo_orders_key, uuid, self._encode(algo_order))

        for exchange, open_order_uuids in self._mem_open_orders.copy().items():
            open_orders_key = f"strategy:{self.strategy_id}:user_id:{self.user_id}:exchange:{exchange.value}:open_orders"

            await self._r_async.delete(open_orders_key)

            if open_order_uuids:
                await self._r_async.sadd(open_orders_key, *open_order_uuids)

        for symbol, uuids in self._mem_symbol_orders.copy().items():
            instrument_id = InstrumentId.from_str(symbol)
            key = f"strategy:{self.strategy_id}:user_id:{self.user_id}:exchange:{instrument_id.exchange.value}:symbol_orders:{symbol}"
            await self._r_async.delete(key)
            if uuids:
                await self._r_async.sadd(key, *uuids)

        for symbol, uuids in self._mem_symbol_open_orders.copy().items():
            instrument_id = InstrumentId.from_str(symbol)
            key = f"strategy:{self.strategy_id}:user_id:{self.user_id}:exchange:{instrument_id.exchange.value}:symbol_open_orders:{symbol}"
            await self._r_async.delete(key)
            if uuids:
                await self._r_async.sadd(key, *uuids)

        # Add position sync
        for symbol, position in self._mem_positions.copy().items():
            key = f"strategy:{self.strategy_id}:user_id:{self.user_id}:exchange:{position.exchange.value}:symbol_positions:{symbol}"
            await self._r_async.set(key, self._encode(position))
            
        # Add balance sync
        for account_type, balance in self._mem_account_balance.copy().items():
            for asset, amount in balance.balances.items():
                key = f"strategy:{self.strategy_id}:user_id:{self.user_id}:account_type:{account_type.value}:asset_balance:{asset}"
                await self._r_async.set(key, self._encode(amount))

    async def _sync_to_sqlite(self):
        """Sync the cache to SQLite"""
        async with self._db_async.cursor() as cursor:
            await self._sync_orders(cursor)
            await self._sync_algo_orders(cursor)
            await self._sync_positions(cursor)
            await self._sync_open_orders(cursor)
            await self._sync_balances(cursor)
            await self._db_async.commit()
    
    async def sync_orders(self):
        async with self._db_async.cursor() as cursor:
            await self._sync_orders(cursor)
            await self._db_async.commit()
    
    async def sync_algo_orders(self):
        async with self._db_async.cursor() as cursor:
            await self._sync_algo_orders(cursor)
            await self._db_async.commit()

    async def sync_positions(self):
        async with self._db_async.cursor() as cursor:
            await self._sync_positions(cursor)
            await self._db_async.commit()
            
    async def sync_open_orders(self):
        async with self._db_async.cursor() as cursor:
            await self._sync_open_orders(cursor)
            await self._db_async.commit()
            
    async def sync_balances(self):
        async with self._db_async.cursor() as cursor:
            await self._sync_balances(cursor)
            await self._db_async.commit()
            
    async def _sync_orders(self, cursor: aiosqlite.Cursor):
        """Sync orders to SQLite"""
        for uuid, order in self._mem_orders.copy().items():
            await cursor.execute(
                f"INSERT OR REPLACE INTO {self._table_prefix}_orders "
                "(timestamp, uuid, symbol, side, type, amount, price, status, data) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    order.timestamp,
                    uuid,
                    order.symbol,
                    order.side.value,
                    order.type.value,
                    str(order.amount),  # sqlite does not support decimal
                    order.price or order.average,
                    order.status.value,
                    self._encode(order),
                ),
            )

    async def _sync_algo_orders(self, cursor: aiosqlite.Cursor):
        """Sync algorithmic orders to SQLite"""
        for uuid, algo_order in self._mem_algo_orders.copy().items():
            await cursor.execute(
                f"INSERT OR REPLACE INTO {self._table_prefix}_algo_orders "
                "(timestamp, uuid, symbol, data) VALUES (?, ?, ?, ?)",
                (
                    algo_order.timestamp,
                    uuid,
                    algo_order.symbol,
                    self._encode(algo_order),
                ),
            )

    async def _sync_positions(self, cursor: aiosqlite.Cursor):
        """Sync positions to SQLite
        
        1. Delete positions that no longer exist in memory
        2. Insert or update current positions
        """
        # First get all positions from database
        await cursor.execute(f"SELECT symbol FROM {self._table_prefix}_positions")
        db_positions = {row[0] for row in await cursor.fetchall()}
        
        # Delete positions that are in DB but not in memory
        positions_to_delete = db_positions - set(self.get_all_positions().keys())
        if positions_to_delete:
            await cursor.executemany(
                f"DELETE FROM {self._table_prefix}_positions WHERE symbol = ?",
                [(symbol,) for symbol in positions_to_delete]
            )
            self._log.debug(f"Deleted {len(positions_to_delete)} stale positions from database")

        # Insert or update current positions
        for symbol, position in self._mem_positions.copy().items():
            await cursor.execute(
                f"INSERT OR REPLACE INTO {self._table_prefix}_positions "
                "(symbol, exchange, side, amount, data) VALUES (?, ?, ?, ?, ?)",
                (
                    symbol,
                    position.exchange.value,
                    position.side.value if position.side else "FLAT",
                    str(position.amount),
                    self._encode(position),
                ),
            )

    async def _sync_open_orders(self, cursor: aiosqlite.Cursor):
        """Sync open orders to SQLite"""
        await cursor.execute(f"DELETE FROM {self._table_prefix}_open_orders")
        
        for exchange, uuids in self._mem_open_orders.copy().items():
            for uuid in uuids:
                order = self._mem_orders.get(uuid)
                if order:
                    await cursor.execute(
                        f"INSERT INTO {self._table_prefix}_open_orders "
                        "(uuid, exchange, symbol) VALUES (?, ?, ?)",
                        (uuid, exchange.value, order.symbol),
                    )

    async def _sync_balances(self, cursor):
        """Sync account balances to SQLite"""
        for account_type, balance in self._mem_account_balance.copy().items():
            for asset, amount in balance.balances.items():
                await cursor.execute(
                    f"INSERT OR REPLACE INTO {self._table_prefix}_balances "
                    "(asset, account_type, free, locked) VALUES (?, ?, ?, ?)",
                    (
                        asset,
                        account_type.value,
                        str(amount.free),
                        str(amount.locked),
                    ),
                )

    def _cleanup_expired_data(self):
        """Cleanup expired data"""
        current_time = self._clock.timestamp_ms()
        expire_before = current_time - self._expired_time * 1000

        expired_orders = []
        for uuid, order in self._mem_orders.copy().items():
            if order.timestamp < expire_before:
                expired_orders.append(uuid)

                if not order.is_closed:
                    self._log.warn(f"order {uuid} is not closed, but expired")

                self._registry.remove_order(order)

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
        if self._storage_initialized:
            if self._storage_backend == StorageBackend.REDIS:
                await self._sync_to_redis()
                await self._r_async.aclose()
            elif self._storage_backend == StorageBackend.SQLITE:
                await self._sync_to_sqlite()
                await self._db_async.close()
                self._db.close()

    ################ # cache public data  ###################

    def _update_kline_cache(self, kline: Kline):
        key = f"{kline.symbol}-{kline.interval.value}"
        self._kline_cache[key] = kline

    def _update_bookl1_cache(self, bookl1: BookL1):
        self._bookl1_cache[bookl1.symbol] = bookl1

    def _update_trade_cache(self, trade: Trade):
        self._trade_cache[trade.symbol] = trade

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

    def trade(self, symbol: str) -> Optional[Trade]:
        """
        Retrieve a Trade object from the cache by symbol.

        :param symbol: The symbol of the Trade to retrieve.
        :return: The Trade object if found, otherwise None.
        """
        return self._trade_cache.get(symbol, None)

    ################ # cache private data  ###################

    def _check_status_transition(self, order: Order):
        previous_order = self._mem_orders.get(order.uuid)
        if not previous_order:
            return True

        if order.status not in STATUS_TRANSITIONS[previous_order.status]:
            self._log.debug(
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

    def get_all_positions(self, exchange: Optional[ExchangeType] = None) -> Dict[str, Position]:
        positions = {
            symbol: position
            for symbol, position in self._mem_positions.copy().items()
            if ((exchange is None or position.exchange == exchange) and position.is_opened)
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
                

    def _get_all_positions_from_redis(self, exchange_id: ExchangeType) -> Dict[str, Position]:
        positions = {}
        pattern = f"strategy:{self.strategy_id}:user_id:{self.user_id}:exchange:{exchange_id.value}:symbol_positions:*"
        keys = self._r.keys(pattern)
        for key in keys:
            if raw_position := self._r.get(key):
                position = self._decode(raw_position, Position)
                positions[position.symbol] = position
        return positions
    
    def _get_all_positions_from_sqlite(self, exchange_id: ExchangeType) -> Dict[str, Position]:
        positions = {}
        cursor = self._db.cursor()
        cursor.execute(f"SELECT symbol, data FROM {self._table_prefix}_positions WHERE exchange = ?", (exchange_id.value,))
        for row in cursor.fetchall():
            position = self._decode(row[1], Position)
            if position.side:
                positions[position.symbol] = position
        return positions
    
    def _get_balance_from_sqlite(self, account_type: AccountType) -> List[Balance]:
        balances = []
        cursor = self._db.cursor()
        cursor.execute(f"SELECT asset, free, locked FROM {self._table_prefix}_balances WHERE account_type = ?", (account_type.value,))
        for row in cursor.fetchall():
            balances.append(Balance(asset=row[0], free=Decimal(row[1]), locked=Decimal(row[2])))
        return balances
    
    def _get_balance_from_redis(self, account_type: AccountType) -> List[Balance]:
        balances = []
        pattern = f"strategy:{self.strategy_id}:user_id:{self.user_id}:account_type:{account_type.value}:asset_balance:*"
        keys = self._r.keys(pattern)
        for key in keys:
            if raw_balance := self._r.get(key):
                balance: Balance = self._decode(raw_balance, Balance)
                balances.append(balance)
        return balances
    
    #NOTE: this function is not for user to call, it is for internal use
    def _get_all_balances_from_db(self, account_type: AccountType) -> List[Balance]:
        if self._storage_backend == StorageBackend.REDIS:
            return self._get_balance_from_redis(account_type)
        elif self._storage_backend == StorageBackend.SQLITE:
            return self._get_balance_from_sqlite(account_type)
    
    #NOTE: this function is not for user to call, it is for internal use
    def _get_all_positions_from_db(self, exchange_id: ExchangeType) -> Dict[str, Position]:
        if self._storage_backend == StorageBackend.REDIS:
            return self._get_all_positions_from_redis(exchange_id)
        elif self._storage_backend == StorageBackend.SQLITE:
            return self._get_all_positions_from_sqlite(exchange_id)

    def _get_order_from_redis(self, uuid: str) -> Optional[Order | AlgoOrder]:
        # find in memory first
        if uuid.startswith("ALGO-"):
            if order := self._mem_algo_orders.get(uuid):
                return order
            key = f"strategy:{self.strategy_id}:user_id:{self.user_id}:algo_orders"
            obj_type = AlgoOrder
            mem_dict = self._mem_algo_orders
        else:
            if order := self._mem_orders.get(uuid):
                return order
            key = f"strategy:{self.strategy_id}:user_id:{self.user_id}:orders"
            obj_type = Order
            mem_dict = self._mem_orders

        if raw_order := self._r.hget(key, uuid):
            order = self._decode(raw_order, obj_type)
            mem_dict[uuid] = order
            return order
        return None

    def _get_order_from_sqlite(self, uuid: str) -> Optional[Order | AlgoOrder]:
        try:
            # determine the table and object type to query
            if uuid.startswith("ALGO-"):
                table = f"{self._table_prefix}_algo_orders"
                obj_type = AlgoOrder
                mem_dict = self._mem_algo_orders
            else:
                table = f"{self._table_prefix}_orders"
                obj_type = Order
                mem_dict = self._mem_orders

            # find in memory
            if order := mem_dict.get(uuid):
                return order

            # query SQLite
            cursor = self._db.cursor()
            cursor.execute(
                f"""
                SELECT data FROM {table}
                WHERE uuid = ?
                """,
                (uuid,),
            )

            if row := cursor.fetchone():
                order = self._decode(row[0], obj_type)
                mem_dict[uuid] = order  # Cache in memory
                return order

            return None

        except sqlite3.Error as e:
            self._log.error(f"Error getting order from SQLite: {e}")
            return None

    @maybe
    def get_order(self, uuid: str) -> Optional[Order | AlgoOrder]:
        if self._storage_backend == StorageBackend.REDIS:
            return self._get_order_from_redis(uuid)
        elif self._storage_backend == StorageBackend.SQLITE:
            return self._get_order_from_sqlite(uuid)

    def _get_symbol_orders_from_redis(self, instrument_id: InstrumentId) -> Set[str]:
        key = f"strategy:{self.strategy_id}:user_id:{self.user_id}:exchange:{instrument_id.exchange.value}:symbol_orders:{instrument_id.symbol}"
        if redis_orders := self._r.smembers(key):
            return {uuid.decode() for uuid in redis_orders}
        return set()

    def _get_symbol_orders_from_sqlite(self, instrument_id: InstrumentId) -> Set[str]:
        cursor = self._db.cursor()
        cursor.execute(
            f"""
            SELECT uuid FROM {self._table_prefix}_orders WHERE symbol = ?
            """,
            (instrument_id.symbol,),
        )
        return {row[0] for row in cursor.fetchall()}

    def get_symbol_orders(self, symbol: str, in_mem: bool = True) -> Set[str]:
        """Get all orders for a symbol from memory and Redis"""
        memory_orders = self._mem_symbol_orders.get(symbol, set())
        if not in_mem:
            instrument_id = InstrumentId.from_str(symbol)
            if self._storage_backend == StorageBackend.REDIS:
                orders = self._get_symbol_orders_from_redis(instrument_id)
            elif self._storage_backend == StorageBackend.SQLITE:
                orders = self._get_symbol_orders_from_sqlite(instrument_id)
            return memory_orders.union(orders)
        return memory_orders

    def get_open_orders(
        self, symbol: str | None = None, exchange: ExchangeType | None = None
    ) -> Set[str]:
        if symbol is not None:
            return self._mem_symbol_open_orders[symbol]
        elif exchange is not None:
            return self._mem_open_orders[exchange]
        else:
            raise ValueError("Either `symbol` or `exchange` must be specified")
