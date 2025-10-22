import asyncpg
import psycopg2
from decimal import Decimal
from typing import Dict, Set, List, Optional, Any

from nexustrader.backends.db import StorageBackend
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
                    oid TEXT PRIMARY KEY,
                    eid TEXT,
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
                    oid TEXT PRIMARY KEY,
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
                    oid TEXT PRIMARY KEY,
                    eid TEXT,
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
                
                CREATE TABLE IF NOT EXISTS {self.table_prefix}_params (
                    key TEXT PRIMARY KEY,
                    value BYTEA,
                    timestamp BIGINT DEFAULT (EXTRACT(EPOCH FROM NOW()) * 1000)::BIGINT
                );
            """)

    async def close(self) -> None:
        if self._pg_async:
            await self._pg_async.close()
        if self._pg:
            self._pg.close()

    async def sync_orders(self, mem_orders: Dict[str, Order]) -> None:
        async with self._pg_async.acquire() as conn:
            for oid, order in mem_orders.copy().items():
                await conn.execute(
                    f"INSERT INTO {self.table_prefix}_orders "
                    "(timestamp, oid, eid, symbol, side, type, amount, price, status, fee, fee_currency, data) "
                    "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12) "
                    "ON CONFLICT (oid) DO UPDATE SET "
                    "timestamp = EXCLUDED.timestamp, "
                    "eid = EXCLUDED.eid, "
                    "symbol = EXCLUDED.symbol, "
                    "side = EXCLUDED.side, "
                    "type = EXCLUDED.type, "
                    "amount = EXCLUDED.amount, "
                    "price = EXCLUDED.price, "
                    "status = EXCLUDED.status, "
                    "fee = EXCLUDED.fee, "
                    "fee_currency = EXCLUDED.fee_currency, "
                    "data = EXCLUDED.data",
                    int(order.timestamp),
                    str(order.oid),
                    str(order.eid),
                    str(order.symbol),
                    str(order.side.value) if order.side is not None else None,
                    str(order.type.value) if order.type is not None else None,
                    str(order.amount),
                    float(order.price or order.average)
                    if (order.price or order.average)
                    else None,
                    str(order.status.value),
                    str(order.fee) if order.fee is not None else None,
                    order.fee_currency,
                    self._encode(order),
                )

    async def sync_algo_orders(self, mem_algo_orders: Dict[str, AlgoOrder]) -> None:
        async with self._pg_async.acquire() as conn:
            for oid, algo_order in mem_algo_orders.copy().items():
                await conn.execute(
                    f"INSERT INTO {self.table_prefix}_algo_orders "
                    "(timestamp, oid, symbol, data) VALUES ($1, $2, $3, $4) "
                    "ON CONFLICT (oid) DO UPDATE SET "
                    "timestamp = EXCLUDED.timestamp, "
                    "symbol = EXCLUDED.symbol, "
                    "data = EXCLUDED.data",
                    int(algo_order.timestamp),
                    str(oid),
                    str(algo_order.symbol),
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
                        str(symbol),
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
                    str(symbol),
                    str(position.exchange.value),
                    str(position.side.value) if position.side else "FLAT",
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

            for exchange, oids in mem_open_orders.copy().items():
                for oid in oids.copy():
                    order = mem_orders.get(oid)
                    if order:
                        await conn.execute(
                            f"INSERT INTO {self.table_prefix}_open_orders "
                            "(oid, eid, exchange, symbol) VALUES ($1, $2, $3, $4)",
                            str(oid),
                            str(order.eid),
                            str(exchange.value),
                            str(order.symbol),
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
                        str(asset),
                        str(account_type.value),
                        str(amount.free),
                        str(amount.locked),
                    )

    def get_order(
        self,
        oid: str,
        mem_orders: Dict[str, Order],
        mem_algo_orders: Dict[str, AlgoOrder],
    ) -> Optional[Order | AlgoOrder]:
        if order := mem_orders.get(oid):
            return order
        if algo_order := mem_algo_orders.get(oid):
            return algo_order

        try:
            cursor = self._pg.cursor()
            with cursor:
                # Try regular orders first
                cursor.execute(
                    f"SELECT data FROM {self.table_prefix}_orders WHERE oid = %s",
                    (oid,),
                )
                row = cursor.fetchone()
                if row:
                    order = self._decode(row[0], Order)
                    mem_orders[oid] = order
                    return order
                # Try algo orders
                cursor.execute(
                    f"SELECT data FROM {self.table_prefix}_algo_orders WHERE oid = %s",
                    (oid,),
                )
                row = cursor.fetchone()
                if row:
                    algo_order = self._decode(row[0], AlgoOrder)
                    mem_algo_orders[oid] = algo_order
                    return algo_order
                return None
        except psycopg2.DatabaseError as error:
            self._log.error(f"Error getting order from PostgreSQL: {error}")
            return None

    def get_symbol_orders(self, symbol: str) -> Set[str]:
        cursor = self._pg.cursor()
        with cursor:
            cursor.execute(
                f"SELECT oid FROM {self.table_prefix}_orders WHERE symbol = %s",
                (symbol,),
            )
            result = {row[0] for row in cursor.fetchall()}
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

    async def sync_params(self, mem_params: Dict[str, Any]) -> None:
        import msgspec

        async with self._pg_async.acquire() as conn:
            for key, value in mem_params.copy().items():
                try:
                    serialized_value = self._encode_param(value)
                    await conn.execute(
                        f"INSERT INTO {self.table_prefix}_params "
                        "(key, value) VALUES ($1, $2) "
                        "ON CONFLICT (key) DO UPDATE SET "
                        "value = EXCLUDED.value, "
                        "timestamp = DEFAULT",
                        str(key),
                        serialized_value,
                    )
                except msgspec.EncodeError as e:
                    self._log.error(f"Error serializing parameter {key}: {e}")
                except Exception as e:
                    self._log.error(f"Error storing parameter {key}: {e}")

    def get_param(self, key: str, default: Any = None) -> Any:
        import msgspec

        try:
            cursor = self._pg.cursor()
            cursor.execute(
                f"SELECT value FROM {self.table_prefix}_params WHERE key = %s", (key,)
            )
            row = cursor.fetchone()
            cursor.close()

            if row:
                try:
                    return self._decode_param(row[0])
                except msgspec.DecodeError as e:
                    self._log.error(f"Error deserializing parameter {key}: {e}")
                    return default
            return default
        except Exception as e:
            self._log.error(f"Error getting parameter {key}: {e}")
            return default

    def get_all_params(self) -> Dict[str, Any]:
        import msgspec

        params = {}
        try:
            cursor = self._pg.cursor()
            cursor.execute(f"SELECT key, value FROM {self.table_prefix}_params")
            for row in cursor.fetchall():
                try:
                    params[row[0]] = self._decode_param(row[1])
                except msgspec.DecodeError as e:
                    self._log.error(f"Error deserializing parameter {row[0]}: {e}")
            cursor.close()
        except Exception as e:
            self._log.error(f"Error getting all parameters: {e}")
        return params
