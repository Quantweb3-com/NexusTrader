#!/usr/bin/env python3

import argparse
import asyncio
import sys
from pathlib import Path
from decimal import Decimal
from typing import List
from datetime import datetime
from dataclasses import dataclass
import pandas as pd
import sqlite3
import aiosqlite
import msgspec
import re

# Add parent directory to path to import NexusTrader modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from nexustrader.schema import Order, OrderSide, OrderStatus, InstrumentId, OrderType
from nexustrader.constants import InstrumentType
from nexustrader.core.log import SpdLog

# Try to import PostgreSQL dependencies
try:
    import psycopg2
    import asyncpg
    from nexustrader.constants import get_postgresql_config
    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False


class MinimalDatabaseBackend:
    """Minimal database backend for PnL analysis to avoid circular imports"""
    
    def __init__(self, db_type: str, strategy_id: str, user_id: str, table_prefix: str = "nexus", db_path: str = None):
        self.db_type = db_type.lower()
        self.strategy_id = strategy_id
        self.user_id = user_id
        self.table_prefix = table_prefix
        self.db_path = db_path
        self._db = None
        self._db_async = None
        # Construct table name like cache.py does
        self._table_prefix = self.safe_table_name(f"{self.strategy_id}_{self.user_id}")
    
    @staticmethod
    def safe_table_name(name: str) -> str:
        name = re.sub(r"[^a-zA-Z0-9_]", "_", name)
        return name.lower()
    
    async def _init_conn(self):
        """Initialize database connections"""
        if self.db_type == 'postgresql':
            if not POSTGRES_AVAILABLE:
                raise ImportError("PostgreSQL dependencies not available")
            
            pg_config = get_postgresql_config()
            self._db_async = await asyncpg.create_pool(**pg_config)
            self._db = psycopg2.connect(**pg_config)
            
        elif self.db_type == 'sqlite':
            db_path = Path(self.db_path or '.keys/cache.db')
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self._db_async = await aiosqlite.connect(str(db_path))
            self._db = sqlite3.connect(str(db_path))
        else:
            raise ValueError(f"Unsupported database type: {self.db_type}")
    
    def _decode(self, data: bytes, obj_type) -> Order:
        """Decode order data from database"""
        return msgspec.json.decode(data, type=obj_type)
    
    async def _execute_query(self, query: str, params: tuple = None):
        """Execute query and return results"""
        cursor = self._db.cursor()
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        result = cursor.fetchall()
        cursor.close()
        return result
    
    async def close(self):
        """Close database connections"""
        if self._db_async:
            if self.db_type == 'postgresql':
                await self._db_async.close()
            else:  # sqlite
                await self._db_async.close()
        
        if self._db:
            self._db.close()


@dataclass
class PositionEntry:
    """Represents a position entry in the FIFO queue"""
    quantity: Decimal
    price: float
    timestamp: int
    fee_in_quote: Decimal


@dataclass
class PnLSnapshot:
    """Represents a PnL snapshot at a point in time"""
    timestamp: int
    realized_pnl: float
    net_position_size: float
    avg_cost: float
    total_fees: float


class FIFOPnLCalculator:
    """FIFO-based PnL calculator for a single symbol supporting long/short positions"""
    
    def __init__(self, symbol: str, maker_fee_rate: float = 0.0001, taker_fee_rate: float = 0.0001):
        self.symbol = symbol
        self.maker_fee_rate = Decimal(str(maker_fee_rate))
        self.taker_fee_rate = Decimal(str(taker_fee_rate))
        self.long_queue: List[PositionEntry] = []   # Long positions
        self.short_queue: List[PositionEntry] = []  # Short positions
        self.realized_pnl = Decimal('0')  # In quote currency
        self.total_fees = Decimal('0')    # In quote currency
        self.pnl_history: List[PnLSnapshot] = []
        
        # Parse symbol to get base/quote currencies and instrument type
        self.base_currency, self.quote_currency, self.instrument_type = self._parse_symbol(symbol)
        
    def _parse_symbol(self, symbol: str):
        """
        Parse symbol according to NexusTrader format:
        BTCUSDT.BINANCE -> base: BTC, quote: USDT (SPOT)
        BTCUSDT-PERP.BINANCE -> base: BTC, quote: USDT (LINEAR)
        BTCUSD.BINANCE -> base: BTC, quote: USD (INVERSE)
        """
        try:
            # Parse using InstrumentId to understand the symbol format
            instrument_id = InstrumentId.from_str(symbol)
            symbol_prefix = symbol.split(".")[0]
            
            if instrument_id.is_spot:
                # For spot: BTCUSDT -> BTC/USDT
                if "USDT" in symbol_prefix:
                    base = symbol_prefix.replace("USDT", "")
                    quote = "USDT"
                elif "BTC" in symbol_prefix and symbol_prefix.endswith("BTC"):
                    base = symbol_prefix.replace("BTC", "")
                    quote = "BTC"
                elif "ETH" in symbol_prefix and symbol_prefix.endswith("ETH"):
                    base = symbol_prefix.replace("ETH", "")
                    quote = "ETH"
                else:
                    # Fallback: assume last 3-4 chars are quote
                    if len(symbol_prefix) > 6:
                        base = symbol_prefix[:-4]
                        quote = symbol_prefix[-4:]
                    else:
                        base = symbol_prefix[:-3]
                        quote = symbol_prefix[-3:]
                        
            elif instrument_id.is_linear:
                # For linear futures: BTCUSDT-PERP -> BTC/USDT
                prefix = symbol_prefix.split("-")[0]
                if "USDT" in prefix:
                    base = prefix.replace("USDT", "")
                    quote = "USDT"
                else:
                    # Default fallback
                    base = prefix[:-4] if len(prefix) > 4 else prefix[:-3]
                    quote = prefix[-4:] if len(prefix) > 4 else prefix[-3:]
                    
            elif instrument_id.is_inverse:
                # For inverse futures: BTCUSD -> BTC/USD
                prefix = symbol_prefix.split("-")[0] if "-" in symbol_prefix else symbol_prefix
                base = prefix.replace("USD", "")
                quote = "USD"
                
            else:
                # Fallback
                base = "UNKNOWN"
                quote = "UNKNOWN"
                
            return base, quote, instrument_id.type
            
        except Exception:
            # Fallback parsing if InstrumentId fails
            symbol_prefix = symbol.split(".")[0].split("-")[0]
            if "USDT" in symbol_prefix:
                return symbol_prefix.replace("USDT", ""), "USDT", InstrumentType.SPOT
            elif "USD" in symbol_prefix:
                return symbol_prefix.replace("USD", ""), "USD", InstrumentType.SPOT
            else:
                return "UNKNOWN", "UNKNOWN", InstrumentType.SPOT
        
    def get_current_position(self):
        """Returns (net_position_size, weighted_avg_cost)"""
        long_qty = sum(entry.quantity for entry in self.long_queue)
        short_qty = sum(entry.quantity for entry in self.short_queue)
        net_position = long_qty - short_qty
        
        if net_position == 0:
            return Decimal('0'), Decimal('0')
        elif net_position > 0:
            # Net long position - calculate weighted average price
            if long_qty > 0:
                total_cost_in_quote = sum(entry.quantity * Decimal(str(entry.price)) for entry in self.long_queue)
                avg_cost = total_cost_in_quote / long_qty
            else:
                avg_cost = Decimal('0')
        else:
            # Net short position - calculate weighted average price
            if short_qty > 0:
                total_cost_in_quote = sum(entry.quantity * Decimal(str(entry.price)) for entry in self.short_queue)
                avg_cost = total_cost_in_quote / short_qty
            else:
                avg_cost = Decimal('0')
            
        return net_position, avg_cost
    
    def _calculate_fee(self, order: Order, fill_price: float, filled_qty: Decimal) -> Decimal:
        """Calculate fee in quote currency"""
        if order.fee is not None and order.fee_currency:
            # If fee is provided in the order
            if order.fee_currency == self.quote_currency:
                return order.fee
            elif order.fee_currency == self.base_currency:
                # Convert base currency fee to quote currency
                return order.fee * Decimal(str(fill_price))
            else:
                # Fee in different currency (like BNB), calculate based on order type
                return self._calculate_fee_by_rate(order, fill_price, filled_qty)
        else:
            # Calculate fee based on order type and rates
            return self._calculate_fee_by_rate(order, fill_price, filled_qty)
    
    def _calculate_fee_by_rate(self, order: Order, fill_price: float, filled_qty: Decimal) -> Decimal:
        """Calculate fee based on maker/taker rates"""
        notional_value = filled_qty * Decimal(str(fill_price))
        
        if order.type == OrderType.LIMIT:
            # Maker order
            return notional_value * self.maker_fee_rate
        else:
            # Taker order (MARKET or others)
            return notional_value * self.taker_fee_rate
    
    def process_order(self, order: Order):
        """Process a filled order and update PnL"""
        if not order.filled or order.filled <= 0:
            return
            
        fill_price = order.average or order.price or 0
        filled_qty = order.filled
        
        # Calculate fee in quote currency
        fee_in_quote = self._calculate_fee(order, fill_price, filled_qty)
        self.total_fees += fee_in_quote
        
        if order.side == OrderSide.BUY:
            self._process_buy_order(filled_qty, fill_price, order.timestamp, fee_in_quote)
        else:  # SELL
            self._process_sell_order(filled_qty, fill_price, order.timestamp, fee_in_quote)
        
        # Record PnL history point
        net_pos, avg_cost = self.get_current_position()
        snapshot = PnLSnapshot(
            timestamp=order.timestamp,
            realized_pnl=float(self.realized_pnl),
            net_position_size=float(net_pos),
            avg_cost=float(avg_cost),
            total_fees=float(self.total_fees)
        )
        self.pnl_history.append(snapshot)
    
    def _process_buy_order(self, quantity: Decimal, price: float, timestamp: int, fee: Decimal):
        """Process a buy order - closes short positions first, then opens long"""
        remaining_qty = quantity
        trade_pnl = Decimal('0')
        
        # First, close short positions using FIFO
        while remaining_qty > 0 and self.short_queue:
            short_entry = self.short_queue[0]
            
            if short_entry.quantity <= remaining_qty:
                # Close entire short position
                # PnL = (short_price - buy_price) * quantity - fees
                price_diff = Decimal(str(short_entry.price)) - Decimal(str(price))
                trade_pnl_in_quote = price_diff * short_entry.quantity
                # Subtract fees (in quote currency)
                trade_pnl += trade_pnl_in_quote - short_entry.fee_in_quote - fee * (short_entry.quantity / quantity)
                
                remaining_qty -= short_entry.quantity
                self.short_queue.pop(0)
            else:
                # Partially close short position
                price_diff = Decimal(str(short_entry.price)) - Decimal(str(price))
                trade_pnl_in_quote = price_diff * remaining_qty
                
                proportional_short_fee = short_entry.fee_in_quote * (remaining_qty / short_entry.quantity)
                proportional_buy_fee = fee * (remaining_qty / quantity)
                
                trade_pnl += trade_pnl_in_quote - proportional_short_fee - proportional_buy_fee
                
                # Update remaining short position
                short_entry.quantity -= remaining_qty
                short_entry.fee_in_quote -= proportional_short_fee
                
                remaining_qty = Decimal('0')
        
        # Add remaining quantity to long position
        if remaining_qty > 0:
            remaining_fee = fee * (remaining_qty / quantity)
            long_entry = PositionEntry(
                quantity=remaining_qty,
                price=price,
                timestamp=timestamp,
                fee_in_quote=remaining_fee
            )
            self.long_queue.append(long_entry)
        
        self.realized_pnl += trade_pnl
    
    def _process_sell_order(self, quantity: Decimal, price: float, timestamp: int, fee: Decimal):
        """Process a sell order - closes long positions first, then opens short"""
        remaining_qty = quantity
        trade_pnl = Decimal('0')
        
        # First, close long positions using FIFO
        while remaining_qty > 0 and self.long_queue:
            long_entry = self.long_queue[0]
            
            if long_entry.quantity <= remaining_qty:
                # Close entire long position
                # PnL = (sell_price - long_price) * quantity - fees
                price_diff = Decimal(str(price)) - Decimal(str(long_entry.price))
                trade_pnl_in_quote = price_diff * long_entry.quantity
                # Subtract fees (in quote currency)
                trade_pnl += trade_pnl_in_quote - long_entry.fee_in_quote - fee * (long_entry.quantity / quantity)
                
                remaining_qty -= long_entry.quantity
                self.long_queue.pop(0)
            else:
                # Partially close long position
                price_diff = Decimal(str(price)) - Decimal(str(long_entry.price))
                trade_pnl_in_quote = price_diff * remaining_qty
                
                proportional_long_fee = long_entry.fee_in_quote * (remaining_qty / long_entry.quantity)
                proportional_sell_fee = fee * (remaining_qty / quantity)
                
                trade_pnl += trade_pnl_in_quote - proportional_long_fee - proportional_sell_fee
                
                # Update remaining long position
                long_entry.quantity -= remaining_qty
                long_entry.fee_in_quote -= proportional_long_fee
                
                remaining_qty = Decimal('0')
        
        # Add remaining quantity to short position
        if remaining_qty > 0:
            remaining_fee = fee * (remaining_qty / quantity)
            short_entry = PositionEntry(
                quantity=remaining_qty,
                price=price,
                timestamp=timestamp,
                fee_in_quote=remaining_fee
            )
            self.short_queue.append(short_entry)
        
        self.realized_pnl += trade_pnl


class PnLAnalyzer:
    """Main PnL analysis class"""
    
    def __init__(self):
        self.log = SpdLog.get_logger("PnLAnalyzer", level="INFO", flush=True)
    
    def _get_db_backend(self, db_type: str, **kwargs):
        """Initialize database backend"""
        return MinimalDatabaseBackend(
            db_type=db_type,
            strategy_id=kwargs.get('strategy_id', 'pnl_analysis'),
            user_id=kwargs.get('user_id', 'analyzer'),
            table_prefix=kwargs.get('table_prefix', 'nexus'),
            db_path=kwargs.get('db_path', '.keys/cache.db')
        )
    
    async def _get_orders_from_db(self, db_backend, db_type: str, symbol: str, start_timestamp: int, 
                                 end_timestamp: int) -> List[Order]:
        """Fetch orders from database"""
        orders = []
        
        try:
            if hasattr(db_backend, '_db') and db_backend._db:
                cursor = db_backend._db.cursor()
                
                query = f"""
                SELECT data FROM {db_backend._table_prefix}_orders 
                WHERE symbol = ? AND timestamp >= ? AND timestamp <= ?
                ORDER BY timestamp ASC
                """
                
                if db_type.lower() == 'postgresql':
                    # PostgreSQL uses %s placeholders
                    query = query.replace('?', '%s')
                    cursor.execute(query, (symbol, start_timestamp, end_timestamp))
                else:
                    # SQLite uses ? placeholders
                    cursor.execute(query, (symbol, start_timestamp, end_timestamp))
                
                rows = cursor.fetchall()
                
                for row in rows:
                    try:
                        order = db_backend._decode(row[0], Order)
                        # Only include filled orders
                        if order.status in [OrderStatus.FILLED, OrderStatus.PARTIALLY_FILLED]:
                            orders.append(order)
                    except Exception as e:
                        self.log.warning(f"Failed to decode order: {e}")
                        continue
                        
                cursor.close()
                
        except Exception as e:
            self.log.error(f"Error fetching orders from database: {e}")
            raise
            
        return orders
    
    async def analyze_symbol_pnl(self, symbol: str, start_date: str = None, end_date: str = None, 
                               db_type: str = None, maker_fee_rate: float = 0.0001, 
                               taker_fee_rate: float = 0.0001, **db_kwargs) -> pd.DataFrame:
        """Analyze PnL for a specific symbol"""
        
        # Initialize database backend
        db_backend = self._get_db_backend(db_type, **db_kwargs)
        await db_backend._init_conn()
        
        # Handle date range - if not provided, use full range
        if start_date is None or end_date is None:
            # Get min/max timestamps from database for this symbol
            orders_table = f"{db_backend._table_prefix}_orders"
            if db_type.lower() == 'postgresql':
                min_max_query = f"SELECT MIN(timestamp) as min_ts, MAX(timestamp) as max_ts FROM {orders_table} WHERE symbol = %s"
            else:
                min_max_query = f"SELECT MIN(timestamp) as min_ts, MAX(timestamp) as max_ts FROM {orders_table} WHERE symbol = ?"
            
            try:
                result = await db_backend._execute_query(min_max_query, (symbol,))
            except Exception as e:
                if "does not exist" in str(e) or "no such table" in str(e):
                    raise ValueError(f"Table '{orders_table}' not found. Check strategy-id and user-id parameters.")
                raise e
            
            if result and result[0][0] is not None:
                min_ts, max_ts = result[0]
                start_timestamp = min_ts if start_date is None else int(datetime.strptime(start_date, '%Y-%m-%d').timestamp() * 1000)
                end_timestamp = max_ts if end_date is None else int(datetime.strptime(end_date, '%Y-%m-%d').timestamp() * 1000)
                
                if start_date is None:
                    start_date = datetime.fromtimestamp(start_timestamp / 1000).strftime('%Y-%m-%d')
                if end_date is None:
                    end_date = datetime.fromtimestamp(end_timestamp / 1000).strftime('%Y-%m-%d')
            else:
                self.log.error(f"No orders found for symbol {symbol}")
                await db_backend.close()
                return pd.DataFrame()
        else:
            # Convert date strings to timestamps
            start_timestamp = int(datetime.strptime(start_date, '%Y-%m-%d').timestamp() * 1000)
            end_timestamp = int(datetime.strptime(end_date, '%Y-%m-%d').timestamp() * 1000)
        
        self.log.info(f"Analyzing PnL for {symbol} from {start_date} to {end_date}")
        self.log.info(f"Maker fee rate: {maker_fee_rate:.4f}%, Taker fee rate: {taker_fee_rate:.4f}%")
        
        try:
            # Fetch orders
            orders = await self._get_orders_from_db(db_backend, db_type, symbol, start_timestamp, end_timestamp)
            self.log.info(f"Found {len(orders)} filled orders for {symbol}")
            
            if not orders:
                self.log.warning(f"No orders found for {symbol} in the specified period")
                return pd.DataFrame()
            
            # Calculate PnL using FIFO
            calculator = FIFOPnLCalculator(symbol, maker_fee_rate, taker_fee_rate)
            
            for order in orders:
                calculator.process_order(order)
            
            # Convert to DataFrame
            if calculator.pnl_history:
                data = []
                for snapshot in calculator.pnl_history:
                    data.append({
                        'timestamp': snapshot.timestamp,
                        'realized_pnl': snapshot.realized_pnl,
                        'net_position_size': snapshot.net_position_size,
                        'avg_cost': snapshot.avg_cost,
                        'total_fees': snapshot.total_fees
                    })
                
                df = pd.DataFrame(data)
                
                # Convert timestamp to datetime
                df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
                df = df.set_index('datetime')
                
                # Add additional metrics
                df['cumulative_pnl'] = df['realized_pnl']
                df['trade_count'] = range(1, len(df) + 1)
                df['pnl_per_trade'] = df['realized_pnl'].diff().fillna(df['realized_pnl'].iloc[0])
                
                # Add position direction
                df['position_direction'] = df['net_position_size'].apply(
                    lambda x: 'LONG' if x > 0 else 'SHORT' if x < 0 else 'FLAT'
                )
                
                self.log.info(f"Symbol: {symbol}")
                self.log.info(f"Instrument type: {calculator.instrument_type}")
                self.log.info(f"Base currency: {calculator.base_currency}")
                self.log.info(f"Quote currency: {calculator.quote_currency}")
                self.log.info(f"Final realized PnL: {calculator.realized_pnl} {calculator.quote_currency}")
                self.log.info(f"Total fees paid: {calculator.total_fees} {calculator.quote_currency}")
                self.log.info(f"Final net position: {df['net_position_size'].iloc[-1]} {calculator.base_currency}")
                
                return df
            else:
                self.log.warning("No PnL history generated")
                return pd.DataFrame()
                
        finally:
            await db_backend.close()


async def main():
    parser = argparse.ArgumentParser(description='Analyze PnL for trading symbols using FIFO method')
    parser.add_argument('--symbol', required=True, 
                       help='Trading symbol (e.g., BTCUSDT.BINANCE, ETHUSDT-PERP.BYBIT)')
    parser.add_argument('--strategy-id', required=True,
                       help='Strategy ID used for database table naming')
    parser.add_argument('--user-id', required=True,
                       help='User ID used for database table naming')
    parser.add_argument('--start', help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', help='End date (YYYY-MM-DD)')
    parser.add_argument('--db', required=True, choices=['sqlite', 'postgresql'], 
                       help='Database type')
    parser.add_argument('--db-path', default='.keys/cache.db', 
                       help='SQLite database path (default: .keys/cache.db)')
    parser.add_argument('--table-prefix', default='nexus', 
                       help='Database table prefix (default: nexus)')
    parser.add_argument('--maker-fee-rate', type=float, default=0.0001,
                       help='Maker fee rate (default: 0.0001 = 0.01%%)')
    parser.add_argument('--taker-fee-rate', type=float, default=0.0001,
                       help='Taker fee rate (default: 0.0001 = 0.01%%)')
    parser.add_argument('--output', help='Output CSV file path')
    
    args = parser.parse_args()
    
    # Initialize analyzer
    analyzer = PnLAnalyzer()
    
    # Database configuration
    db_kwargs = {
        'strategy_id': args.strategy_id,
        'user_id': args.user_id,
        'table_prefix': args.table_prefix
    }
    if args.db == 'sqlite':
        db_kwargs['db_path'] = args.db_path
    
    try:
        # Analyze PnL
        df = await analyzer.analyze_symbol_pnl(
            args.symbol, 
            args.start, 
            args.end, 
            args.db,
            args.maker_fee_rate,
            args.taker_fee_rate,
            **db_kwargs
        )
        
        if not df.empty:
            # Display summary
            print(f"\n=== PnL Analysis for {args.symbol} ===")
            print(f"Period: {args.start} to {args.end}")
            print(f"Total trades: {len(df)}")
            print(f"Final realized PnL: {df['realized_pnl'].iloc[-1]:.8f}")
            print(f"Total fees paid: {df['total_fees'].iloc[-1]:.8f}")
            print(f"Final net position: {df['net_position_size'].iloc[-1]:.8f}")
            print(f"Final position direction: {df['position_direction'].iloc[-1]}")
            
            if len(df) > 1:
                print(f"Best trade PnL: {df['pnl_per_trade'].max():.8f}")
                print(f"Worst trade PnL: {df['pnl_per_trade'].min():.8f}")
                print(f"Average trade PnL: {df['pnl_per_trade'].mean():.8f}")
                print(f"Win rate: {(df['pnl_per_trade'] > 0).mean() * 100:.2f}%")
                
                # Position statistics
                long_trades = (df['position_direction'] == 'LONG').sum()
                short_trades = (df['position_direction'] == 'SHORT').sum()
                flat_trades = (df['position_direction'] == 'FLAT').sum()
                print(f"Long positions: {long_trades}, Short positions: {short_trades}, Flat: {flat_trades}")
            
            # Save to file if specified
            if args.output:
                df.to_csv(args.output)
                print(f"\nTimeseries data saved to: {args.output}")
            else:
                print("\nTimeseries preview:")
                print(df[['realized_pnl', 'net_position_size', 'position_direction', 'pnl_per_trade']].head(10))
                if len(df) > 10:
                    print("...")
                    print(df[['realized_pnl', 'net_position_size', 'position_direction', 'pnl_per_trade']].tail(5))
        else:
            print("No data to analyze")
            
    except Exception as e:
        print(f"Error during analysis: {e}")
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())
