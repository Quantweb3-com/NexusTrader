import asyncpg
import psycopg2
from decimal import Decimal
from typing import Dict, Set, List, Optional

from nexustrader.base.db import StorageBackend
from nexustrader.schema import Order, Position, AlgoOrder, Balance, AccountBalance
from nexustrader.constants import AccountType, ExchangeType, get_postgresql_config


class PostgreSQLBackend(StorageBackend):
    def __init__(
        self, strategy_id: str, user_id: str, table_prefix: str, log, **kwargs
    ):
        super().__init__(strategy_id, user_id, table_prefix, log, **kwargs)
        self._pg_async = None
        self._pg = None

    async def _init_conn(self) -> None:
        pg_config = get_postgresql_config()
        self._pg_async = await asyncpg.create_pool(**pg_config)
        self._pg = psycopg2.connect(**pg_config)

    async def _init_table(self) -> None:
        async with self._pg_async.acquire() as conn:
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.table_prefix}_orders (
                    timestamp BIGINT,
                    uuid TEXT PRIMARY KEY,
                    symbol TEXT,
                    side TEXT, 
                    type TEXT,
                    amount TEXT,
                    price DOUBLE PRECISION,
                    status TEXT,
                    fee TEXT,
                    fee_currency TEXT,
                    data BYTEA
                );
                
                CREATE INDEX IF NOT EXISTS idx_orders_symbol 
                ON {self.table_prefix}_orders(symbol);
                
                CREATE TABLE IF NOT EXISTS {self.table_prefix}_algo_orders (
                    timestamp BIGINT,
                    uuid TEXT PRIMARY KEY,
                    symbol TEXT,
                    data BYTEA
                );
                
                CREATE INDEX IF NOT EXISTS idx_algo_orders_symbol 
                ON {self.table_prefix}_algo_orders(symbol);
                
                CREATE TABLE IF NOT EXISTS {self.table_prefix}_positions (
                    symbol TEXT PRIMARY KEY,
                    exchange TEXT,
                    side TEXT,
                    amount TEXT,
                    data BYTEA
                );
                
                CREATE TABLE IF NOT EXISTS {self.table_prefix}_open_orders (
                    uuid TEXT PRIMARY KEY,
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
                    timestamp BIGINT PRIMARY KEY,
                    pnl DOUBLE PRECISION,
                    unrealized_pnl DOUBLE PRECISION
                );
            """)

    async def close(self) -> None:
        if self._pg_async:
            await self._pg_async.close()
        if self._pg:
            self._pg.close()

    async def sync_orders(self, mem_orders: Dict[str, Order]) -> None:
        async with self._pg_async.acquire() as conn:
            for uuid, order in mem_orders.copy().items():
                await conn.execute(
                    f"INSERT INTO {self.table_prefix}_orders "
                    "(timestamp, uuid, symbol, side, type, amount, price, status, fee, fee_currency, data) "
                    "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11) "
                    "ON CONFLICT (uuid) DO UPDATE SET "
                    "timestamp = EXCLUDED.timestamp, "
                    "symbol = EXCLUDED.symbol, "
                    "side = EXCLUDED.side, "
                    "type = EXCLUDED.type, "
                    "amount = EXCLUDED.amount, "
                    "price = EXCLUDED.price, "
                    "status = EXCLUDED.status, "
                    "fee = EXCLUDED.fee, "
                    "fee_currency = EXCLUDED.fee_currency, "
                    "data = EXCLUDED.data",
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
                )

    async def sync_algo_orders(self, mem_algo_orders: Dict[str, AlgoOrder]) -> None:
        async with self._pg_async.acquire() as conn:
            for uuid, algo_order in mem_algo_orders.copy().items():
                await conn.execute(
                    f"INSERT INTO {self.table_prefix}_algo_orders "
                    "(timestamp, uuid, symbol, data) VALUES ($1, $2, $3, $4) "
                    "ON CONFLICT (uuid) DO UPDATE SET "
                    "timestamp = EXCLUDED.timestamp, "
                    "symbol = EXCLUDED.symbol, "
                    "data = EXCLUDED.data",
                    algo_order.timestamp,
                    uuid,
                    algo_order.symbol,
                    self._encode(algo_order),
                )

    async def sync_positions(self, mem_positions: Dict[str, Position]) -> None:
        async with self._pg_async.acquire() as conn:
            db_positions = await conn.fetch(
                f"SELECT symbol FROM {self.table_prefix}_positions"
            )
            db_position_symbols = {row["symbol"] for row in db_positions}

            positions_to_delete = db_position_symbols - set(mem_positions.keys())
            if positions_to_delete:
                for symbol in positions_to_delete:
                    await conn.execute(
                        f"DELETE FROM {self.table_prefix}_positions WHERE symbol = $1",
                        symbol,
                    )
                self._log.debug(
                    f"Deleted {len(positions_to_delete)} stale positions from database"
                )

            for symbol, position in mem_positions.copy().items():
                await conn.execute(
                    f"INSERT INTO {self.table_prefix}_positions "
                    "(symbol, exchange, side, amount, data) VALUES ($1, $2, $3, $4, $5) "
                    "ON CONFLICT (symbol) DO UPDATE SET "
                    "exchange = EXCLUDED.exchange, "
                    "side = EXCLUDED.side, "
                    "amount = EXCLUDED.amount, "
                    "data = EXCLUDED.data",
                    symbol,
                    position.exchange.value,
                    position.side.value if position.side else "FLAT",
                    str(position.amount),
                    self._encode(position),
                )

    async def sync_open_orders(
        self,
        mem_open_orders: Dict[ExchangeType, Set[str]],
        mem_orders: Dict[str, Order],
    ) -> None:
        async with self._pg_async.acquire() as conn:
            await conn.execute(f"DELETE FROM {self.table_prefix}_open_orders")

            for exchange, uuids in mem_open_orders.copy().items():
                for uuid in uuids.copy():
                    order = mem_orders.get(uuid)
                    if order:
                        await conn.execute(
                            f"INSERT INTO {self.table_prefix}_open_orders "
                            "(uuid, exchange, symbol) VALUES ($1, $2, $3)",
                            uuid,
                            exchange.value,
                            order.symbol,
                        )

    async def sync_balances(
        self, mem_account_balance: Dict[AccountType, AccountBalance]
    ) -> None:
        async with self._pg_async.acquire() as conn:
            for account_type, balance in mem_account_balance.copy().items():
                for asset, amount in balance.balances.items():
                    await conn.execute(
                        f"INSERT INTO {self.table_prefix}_balances "
                        "(asset, account_type, free, locked) VALUES ($1, $2, $3, $4) "
                        "ON CONFLICT (asset, account_type) DO UPDATE SET "
                        "free = EXCLUDED.free, "
                        "locked = EXCLUDED.locked",
                        asset,
                        account_type.value,
                        str(amount.free),
                        str(amount.locked),
                    )

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

            cursor = self._pg.cursor()
            cursor.execute(
                f"SELECT data FROM {table} WHERE uuid = %s",
                (uuid,),
            )

            row = cursor.fetchone()
            cursor.close()

            if row:
                order = self._decode(row[0], obj_type)
                mem_dict[uuid] = order
                return order

            return None

        except Exception as e:
            self._log.error(f"Error getting order from PostgreSQL: {e}")
            return None

    def get_symbol_orders(self, symbol: str) -> Set[str]:
        cursor = self._pg.cursor()
        cursor.execute(
            f"SELECT uuid FROM {self.table_prefix}_orders WHERE symbol = %s",
            (symbol,),
        )
        result = {row[0] for row in cursor.fetchall()}
        cursor.close()
        return result

    def get_all_positions(self, exchange_id: ExchangeType) -> Dict[str, Position]:
        positions = {}
        cursor = self._pg.cursor()
        cursor.execute(
            f"SELECT symbol, data FROM {self.table_prefix}_positions WHERE exchange = %s",
            (exchange_id.value,),
        )
        for row in cursor.fetchall():
            position = self._decode(row[1], Position)
            if position.side:
                positions[position.symbol] = position
        cursor.close()
        return positions

    def get_all_balances(self, account_type: AccountType) -> List[Balance]:
        balances = []
        cursor = self._pg.cursor()
        cursor.execute(
            f"SELECT asset, free, locked FROM {self.table_prefix}_balances WHERE account_type = %s",
            (account_type.value,),
        )
        for row in cursor.fetchall():
            balances.append(
                Balance(asset=row[0], free=Decimal(row[1]), locked=Decimal(row[2]))
            )
        cursor.close()
        return balances
