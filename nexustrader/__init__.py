from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("tradebot")
except PackageNotFoundError:
    __version__ = "unknown"
