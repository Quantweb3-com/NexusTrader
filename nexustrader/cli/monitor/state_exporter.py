import os
import time
import threading
from typing import Dict, Any
from decimal import Decimal
import redis
import msgspec

from nexustrader.core.cache import AsyncCache
from nexustrader.core.nautilius_core import Logger, LiveClock
from nexustrader.core.entity import get_redis_client_if_available


class StrategyStateExporter:
    """Exports strategy state to files for CLI monitoring"""

    def __init__(self, strategy_id: str, user_id: str, cache: AsyncCache):
        self.strategy_id = strategy_id
        self.user_id = user_id
        self.cache = cache
        self.log = Logger(name=type(self).__name__)
        self.clock = LiveClock()

        # Setup Redis connection and strategy tracking
        self.full_id = f"{strategy_id}_{user_id}"
        self.pid = os.getpid()
        self.strategy_key = f"{self.full_id}:{self.pid}"
        self._redis_client = None
        self._init_redis()

        # Export control
        self.running = False
        self.export_thread = None
        self.heartbeat_thread = None

    def start(self):
        """Start state export"""
        if self.running:
            return

        self.log.debug(f"Starting state export for {self.full_id}")

        # Register strategy in Redis running set
        self._register_strategy()

        self.running = True

        # Start export thread
        self.export_thread = threading.Thread(target=self._export_loop, daemon=True)
        self.export_thread.start()

        # Start heartbeat thread (now just updates Redis TTL)
        self.heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop, daemon=True
        )
        self.heartbeat_thread.start()

    def stop(self):
        """Stop state export"""
        if not self.running:
            return

        self.log.debug(f"Stopping state export for {self.full_id}")
        self.running = False

        # Wait for threads to finish
        if self.export_thread and self.export_thread.is_alive():
            self.export_thread.join(timeout=0.1)

        if self.heartbeat_thread and self.heartbeat_thread.is_alive():
            self.heartbeat_thread.join(timeout=0.1)

        # Remove strategy from Redis running set
        self._unregister_strategy()

    def _export_loop(self):
        """Main export loop"""
        while self.running:
            try:
                self._export_state()
                time.sleep(1)  # Export every 1 second
            except Exception as e:
                self.log.error(f"Error in export loop: {e}")
                time.sleep(1)  # Back off on error

    def _register_strategy(self):
        """Register strategy in Redis running set"""
        if not self._redis_client:
            self.log.warning("Redis client not available, cannot register strategy")
            return

        try:
            strategy_info = {
                "strategy_id": self.strategy_id,
                "user_id": self.user_id,
                "pid": self.pid,
                "start_time": self.clock.timestamp(),
                "full_id": self.full_id,
            }

            # Add to running strategies hash
            self._redis_client.hset(
                "nexustrader:running_strategies",
                self.strategy_key,
                msgspec.json.encode(strategy_info),
            )

            self.log.debug(f"Registered strategy {self.strategy_key} in Redis")
        except Exception as e:
            self.log.error(f"Failed to register strategy in Redis: {e}")

    def _unregister_strategy(self):
        """Remove strategy from Redis running set"""
        if not self._redis_client:
            return

        try:
            self._redis_client.hdel("nexustrader:running_strategies", self.strategy_key)
            self.log.debug(f"Unregistered strategy {self.strategy_key} from Redis")
        except Exception as e:
            self.log.error(f"Failed to unregister strategy from Redis: {e}")

    def _heartbeat_loop(self):
        """Background heartbeat loop - maintains Redis strategy info"""
        while self.running:
            try:
                if self._redis_client:
                    # Update strategy info with current timestamp
                    strategy_info = {
                        "strategy_id": self.strategy_id,
                        "user_id": self.user_id,
                        "pid": self.pid,
                        "start_time": self.clock.timestamp(),
                        "full_id": self.full_id,
                        "last_heartbeat": self.clock.timestamp(),
                    }

                    self._redis_client.hset(
                        "nexustrader:running_strategies",
                        self.strategy_key,
                        msgspec.json.encode(strategy_info),
                    )

                time.sleep(30)  # Update every 30 seconds
            except Exception as e:
                self.log.debug(f"Heartbeat failed: {e}")
                time.sleep(5)  # Retry more frequently if failed

    def _export_state(self):
        """Export current strategy state"""
        timestamp = self.clock.timestamp()

        # Export positions
        self._export_positions(timestamp)

        # Export balances
        self._export_balances(timestamp)

        # Export metrics
        self._export_metrics(timestamp)

    def _export_positions(self, timestamp: float):
        """Export positions state"""
        positions_data = {"timestamp": timestamp, "positions": []}

        for symbol, position in self.cache._mem_positions.items():
            positions_data["positions"].append(
                {
                    "symbol": position.symbol,
                    "side": position.side.value if position.side else None,
                    "amount": float(position.amount),
                    "entry_price": position.entry_price,
                }
            )

        self._save_to_redis("positions", positions_data)

    def _export_balances(self, timestamp: float):
        """Export balances state"""
        balances_data = {"timestamp": timestamp, "balances": []}

        for account_type, account_balance in self.cache._mem_account_balance.items():
            for asset, balance in account_balance.balances.items():
                balances_data["balances"].append(
                    {
                        "account_type": account_type.value if account_type else None,
                        "asset": asset,
                        "free": float(balance.free) if balance.free else None,
                        "locked": float(balance.locked) if balance.locked else None,
                        "total": float(balance.total) if balance.total else None,
                    }
                )

        self._save_to_redis("balances", balances_data)

    def _export_metrics(self, timestamp: float):
        """Export performance metrics"""
        metrics_data = {
            "timestamp": timestamp,
            "metrics": {
                "total_orders": len(self.cache._mem_orders),
                "open_orders": len(
                    [
                        o
                        for o in self.cache._mem_orders.values()
                        if o.status and o.status.value in ["NEW", "PARTIALLY_FILLED"]
                    ]
                ),
                "total_positions": len(self.cache._mem_positions),
                "active_positions": len(
                    [
                        p
                        for p in self.cache._mem_positions.values()
                        if p.amount and p.amount > Decimal("0")
                    ]
                ),
            },
        }

        # Calculate total unrealized PnL
        total_unrealized_pnl = sum(
            float(pos.unrealized_pnl) if pos.unrealized_pnl else 0.0
            for pos in self.cache._mem_positions.values()
        )
        metrics_data["metrics"]["total_unrealized_pnl"] = total_unrealized_pnl

        # Calculate total realized PnL
        total_realized_pnl = sum(
            float(pos.realized_pnl) if pos.realized_pnl else 0.0
            for pos in self.cache._mem_positions.values()
        )
        metrics_data["metrics"]["total_realized_pnl"] = total_realized_pnl

        self._save_to_redis("metrics", metrics_data)

    def _init_redis(self):
        """Initialize Redis connection"""
        self._redis_client = get_redis_client_if_available()
        if self._redis_client:
            self.log.debug("Redis connection established")
        else:
            self.log.debug("Redis not available")
            self._redis_client = None

    def _save_to_redis(self, data_type: str, data: Dict[str, Any]):
        """Save data to Redis using msgspec"""
        if not self._redis_client:
            self.log.warning("Redis client not available, skipping save")
            return

        try:
            # Serialize with msgspec
            json_data = msgspec.json.encode(data)
            key = f"strategy:{self.strategy_key}:{data_type}"
            self._redis_client.set(key, json_data, ex=300)  # 5 minute expiry
            self.log.debug(f"Saved {data_type} to Redis key: {key}")
        except (redis.RedisError, redis.ConnectionError) as e:
            self.log.error(f"Redis error saving {data_type}: {e}")
        except msgspec.EncodeError as e:
            self.log.error(f"Serialization error for {data_type}: {e}")
