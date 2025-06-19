import aiosqlite
import sqlite3
from pathlib import Path
from typing import Dict, Set, List, Optional

from nexustrader.base.db import StorageBackend
from nexustrader.schema import Order, Position, AlgoOrder, Balance, AccountBalance
from nexustrader.constants import AccountType, ExchangeType


class SQLiteBackend(StorageBackend):
    def __init__(
        self,
        strategy_id: str,
        user_id: str,
        table_prefix: str,
        log,
        db_path: str = ".keys/cache.db",
        **kwargs,
    ):
        super().__init__(strategy_id, user_id, table_prefix, log, **kwargs)
        self.db_path = db_path
        self._db_async = None
        self._db = None

    async def _init_conn(self) -> None:
        db_path = Path(self.db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_async = await aiosqlite.connect(str(db_path))
        self._db = sqlite3.connect(str(db_path))

    async def _init_table(self) -> None:
        async with self._db_async.cursor() as cursor:
            await cursor.executescript(f"""
                CREATE TABLE IF NOT EXISTS {self.table_prefix}_orders (
                    timestamp INTEGER,
                    uuid TEXT PRIMARY KEY,
                    symbol TEXT,
                    side TEXT, 
                    type TEXT,
                    amount TEXT,
                    price REAL,
                    status TEXT,
                    fee TEXT,
                    fee_currency TEXT,
                    data BLOB
                );
                
                CREATE INDEX IF NOT EXISTS idx_orders_symbol 
                ON {self.table_prefix}_orders(symbol);
                
                CREATE TABLE IF NOT EXISTS {self.table_prefix}_algo_orders (
                    timestamp INTEGER,
                    uuid TEXT PRIMARY KEY,
                    symbol TEXT,
                    data BLOB
                );
                
                CREATE INDEX IF NOT EXISTS idx_algo_orders_symbol 
                ON {self.table_prefix}_algo_orders(symbol);
                
                CREATE TABLE IF NOT EXISTS {self.table_prefix}_positions (
                    symbol PRIMARY KEY,
                    exchange TEXT,
                    side TEXT,
                    amount TEXT,
                    data BLOB
                );
                
                CREATE TABLE IF NOT EXISTS {self.table_prefix}_open_orders (
                    uuid PRIMARY KEY,
                    exchange TEXT,
                    symbol TEXT
                );
                
                CREATE TABLE IF NOT EXISTS {self.table_prefix}_balances (
                    asset TEXT,
                    account_type TEXT,
                    free TEXT,
                    locked TEXT,
                    PRIMARY KEY (asset, account_type)
                );
                
                CREATE TABLE IF NOT EXISTS {self.table_prefix}_pnl (
                    timestamp INTEGER PRIMARY KEY,
                    pnl REAL,
                    unrealized_pnl REAL
                );
            """)
            await self._db_async.commit()

    async def close(self) -> None:
        if self._db_async:
            await self._db_async.close()
        if self._db:
            self._db.close()

    async def sync_orders(self, mem_orders: Dict[str, Order]) -> None:
        async with self._db_async.cursor() as cursor:
            for uuid, order in mem_orders.copy().items():
                await cursor.execute(
                    f"INSERT OR REPLACE INTO {self.table_prefix}_orders "
                    "(timestamp, uuid, symbol, side, type, amount, price, status, fee, fee_currency, data) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        order.timestamp,
                        uuid,
                        order.symbol,
                        order.side.value,
                        order.type.value,
                        str(order.amount),
                        order.price or order.average,
                        order.status.value,
                        str(order.fee) if order.fee is not None else None,
                        order.fee_currency,
                        self._encode(order),
                    ),
                )
            await self._db_async.commit()

    async def sync_algo_orders(self, mem_algo_orders: Dict[str, AlgoOrder]) -> None:
        async with self._db_async.cursor() as cursor:
            for uuid, algo_order in mem_algo_orders.copy().items():
                await cursor.execute(
                    f"INSERT OR REPLACE INTO {self.table_prefix}_algo_orders "
                    "(timestamp, uuid, symbol, data) VALUES (?, ?, ?, ?)",
                    (
                        algo_order.timestamp,
                        uuid,
                        algo_order.symbol,
                        self._encode(algo_order),
                    ),
                )
            await self._db_async.commit()

    async def sync_positions(self, mem_positions: Dict[str, Position]) -> None:
        async with self._db_async.cursor() as cursor:
            await cursor.execute(f"SELECT symbol FROM {self.table_prefix}_positions")
            db_positions = {row[0] for row in await cursor.fetchall()}

            positions_to_delete = db_positions - set(mem_positions.keys())
            if positions_to_delete:
                await cursor.executemany(
                    f"DELETE FROM {self.table_prefix}_positions WHERE symbol = ?",
                    [(symbol,) for symbol in positions_to_delete],
                )
                self._log.debug(
                    f"Deleted {len(positions_to_delete)} stale positions from database"
                )

            for symbol, position in mem_positions.copy().items():
                await cursor.execute(
                    f"INSERT OR REPLACE INTO {self.table_prefix}_positions "
                    "(symbol, exchange, side, amount, data) VALUES (?, ?, ?, ?, ?)",
                    (
                        symbol,
                        position.exchange.value,
                        position.side.value if position.side else "FLAT",
                        str(position.amount),
                        self._encode(position),
                    ),
                )
            await self._db_async.commit()

    async def sync_open_orders(
        self,
        mem_open_orders: Dict[ExchangeType, Set[str]],
        mem_orders: Dict[str, Order],
    ) -> None:
        async with self._db_async.cursor() as cursor:
            await cursor.execute(f"DELETE FROM {self.table_prefix}_open_orders")

            for exchange, uuids in mem_open_orders.copy().items():
                for uuid in uuids.copy():
                    order = mem_orders.get(uuid)
                    if order:
                        await cursor.execute(
                            f"INSERT INTO {self.table_prefix}_open_orders "
                            "(uuid, exchange, symbol) VALUES (?, ?, ?)",
                            (uuid, exchange.value, order.symbol),
                        )
            await self._db_async.commit()

    async def sync_balances(
        self, mem_account_balance: Dict[AccountType, AccountBalance]
    ) -> None:
        async with self._db_async.cursor() as cursor:
            for account_type, balance in mem_account_balance.copy().items():
                for asset, amount in balance.balances.items():
                    await cursor.execute(
                        f"INSERT OR REPLACE INTO {self.table_prefix}_balances "
                        "(asset, account_type, free, locked) VALUES (?, ?, ?, ?)",
                        (
                            asset,
                            account_type.value,
                            str(amount.free),
                            str(amount.locked),
                        ),
                    )
            await self._db_async.commit()

    def get_order(
        self,
        uuid: str,
        mem_orders: Dict[str, Order],
        mem_algo_orders: Dict[str, AlgoOrder],
    ) -> Optional[Order | AlgoOrder]:
        try:
            if uuid.startswith("ALGO-"):
                table = f"{self.table_prefix}_algo_orders"
                obj_type = AlgoOrder
                mem_dict = mem_algo_orders
            else:
                table = f"{self.table_prefix}_orders"
                obj_type = Order
                mem_dict = mem_orders

            if order := mem_dict.get(uuid):
                return order

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
                mem_dict[uuid] = order
                return order

            return None

        except sqlite3.Error as e:
            self._log.error(f"Error getting order from SQLite: {e}")
            return None

    def get_symbol_orders(self, symbol: str) -> Set[str]:
        cursor = self._db.cursor()
        cursor.execute(
            f"""
            SELECT uuid FROM {self.table_prefix}_orders WHERE symbol = ?
            """,
            (symbol,),
        )
        return {row[0] for row in cursor.fetchall()}

    def get_all_positions(self, exchange_id: ExchangeType) -> Dict[str, Position]:
        positions = {}
        cursor = self._db.cursor()
        cursor.execute(
            f"SELECT symbol, data FROM {self.table_prefix}_positions WHERE exchange = ?",
            (exchange_id.value,),
        )
        for row in cursor.fetchall():
            position = self._decode(row[1], Position)
            if position.side:
                positions[position.symbol] = position
        return positions

    def get_all_balances(self, account_type: AccountType) -> List[Balance]:
        from decimal import Decimal

        balances = []
        cursor = self._db.cursor()
        cursor.execute(
            f"SELECT asset, free, locked FROM {self.table_prefix}_balances WHERE account_type = ?",
            (account_type.value,),
        )
        for row in cursor.fetchall():
            balances.append(
                Balance(asset=row[0], free=Decimal(row[1]), locked=Decimal(row[2]))
            )
        return balances
