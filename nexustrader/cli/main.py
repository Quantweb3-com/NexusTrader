import click
import sys
import msgspec

from nexustrader.cli.app import run_monitor
from nexustrader.core.entity import get_redis_client_if_available


@click.group()
def cli():
    """NexusTrader CLI tools for monitoring and management"""
    pass


@cli.command()
def monitor():
    """Start the interactive CLI monitor for running strategies"""
    try:
        run_monitor()
    except KeyboardInterrupt:
        click.echo("\nMonitor stopped.")
    except Exception as e:
        click.echo(f"Error starting monitor: {e}", err=True)
        sys.exit(1)


def _get_redis_client():
    """Get Redis client"""
    return get_redis_client_if_available()


@cli.command()
def status():
    """Show status of running strategies"""
    redis_client = _get_redis_client()
    if not redis_client:
        click.echo("Redis not available.", err=True)
        return

    try:
        # Get all running strategies from Redis hash
        running_strategies = redis_client.hgetall("nexustrader:running_strategies")

        if not running_strategies:
            click.echo("No strategies running.")
            return

        strategies = {}
        for strategy_key, strategy_data in running_strategies.items():
            if isinstance(strategy_key, bytes):
                strategy_key = strategy_key.decode("utf-8")
            if isinstance(strategy_data, bytes):
                strategy_data = strategy_data.decode("utf-8")

            try:
                strategy_info = msgspec.json.decode(strategy_data)
                full_id = strategy_info.get("full_id", strategy_key)
                pid = strategy_info.get("pid", "unknown")
                strategies[f"{full_id}:{pid}"] = strategy_info
            except msgspec.DecodeError:
                continue

        click.echo(f"Found {len(strategies)} running strategies:")
        click.echo()

        for strategy_id, strategy in strategies.items():
            status_color = "green"
            click.echo(f"  • {strategy_id} - ", nl=False)
            click.secho("running", fg=status_color)
            click.echo(f"    PID: {strategy.get('pid', 'N/A')}")
            click.echo(f"    Last heartbeat: {strategy.get('last_heartbeat', 'N/A')}")

            # Check if Redis data exists
            try:
                key = f"strategy:{strategy_id}:metrics"
                if redis_client.exists(key):
                    click.echo("    Redis data: ✓")
                else:
                    click.echo("    Redis data: ✗")
            except Exception:
                click.echo("    Redis data: ✗")

    except Exception as e:
        click.echo(f"Error getting status: {e}", err=True)


@cli.command()
def cleanup():
    """Clean up orphaned Redis strategy data"""
    redis_client = _get_redis_client()
    if not redis_client:
        click.echo("Redis not available.", err=True)
        return

    try:
        # Get all strategy data keys
        strategy_keys = redis_client.keys("strategy:*")

        if not strategy_keys:
            click.echo("No strategy data found.")
            return

        # Get running strategies
        running_strategies = redis_client.hgetall("nexustrader:running_strategies")
        running_strategy_ids = set()

        for strategy_data in running_strategies.values():
            if isinstance(strategy_data, bytes):
                strategy_data = strategy_data.decode("utf-8")
            try:
                strategy_info = msgspec.json.decode(strategy_data)
                full_id = strategy_info.get("full_id")
                if full_id:
                    running_strategy_ids.add(full_id)
            except msgspec.DecodeError:
                continue

        cleaned = 0
        for key in strategy_keys:
            if isinstance(key, bytes):
                key = key.decode("utf-8")

            # Extract strategy ID from key (format: strategy:strategy_id:data_type)
            parts = key.split(":")
            if len(parts) >= 2:
                strategy_id = parts[1]
                if strategy_id not in running_strategy_ids:
                    click.echo(f"Cleaning up Redis data for {strategy_id}...")
                    redis_client.delete(key)
                    cleaned += 1

        if cleaned > 0:
            click.echo(f"Cleaned up {cleaned} orphaned strategy data keys.")
        else:
            click.echo("No cleanup needed.")

    except Exception as e:
        click.echo(f"Error during cleanup: {e}", err=True)


@cli.command()
@click.argument("strategy_id")
def logs(strategy_id):
    """Show logs for a specific strategy"""
    redis_client = _get_redis_client()
    if not redis_client:
        click.echo("Redis not available.", err=True)
        return

    try:
        # Check if strategy exists in running strategies
        running_strategies = redis_client.hgetall("nexustrader:running_strategies")
        strategy_found = False

        for strategy_data in running_strategies.values():
            if isinstance(strategy_data, bytes):
                strategy_data = strategy_data.decode("utf-8")
            try:
                strategy_info = msgspec.json.decode(strategy_data)
                if strategy_info.get("full_id") == strategy_id:
                    strategy_found = True
                    break
            except msgspec.DecodeError:
                continue

        if not strategy_found:
            click.echo(f"Strategy {strategy_id} not found or not running.", err=True)
            return

        # Try to show recent metrics from Redis
        metrics_key = f"strategy:{strategy_id}:metrics"
        metrics_data = redis_client.get(metrics_key)

        if metrics_data:
            try:
                if isinstance(metrics_data, bytes):
                    metrics_data = metrics_data.decode("utf-8")
                data = msgspec.json.decode(metrics_data)
                click.echo(f"Strategy: {strategy_id}")
                click.echo(f"Last updated: {data.get('timestamp', 'N/A')}")
                click.echo("Metrics:")
                for key, value in data.get("metrics", {}).items():
                    click.echo(f"  {key}: {value}")
            except Exception as e:
                click.echo(f"Error reading metrics: {e}", err=True)
        else:
            click.echo(f"No metrics data found for {strategy_id}", err=True)

    except Exception as e:
        click.echo(f"Error getting strategy logs: {e}", err=True)


def main():
    """Main entry point for nexustrader-cli command"""
    cli()


if __name__ == "__main__":
    main()
