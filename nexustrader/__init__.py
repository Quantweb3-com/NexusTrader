from importlib.metadata import version, PackageNotFoundError


try:
    __version__ = version("nexustrader")
except PackageNotFoundError:
    __version__ = "unknown"
