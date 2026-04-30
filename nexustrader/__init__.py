import os
import sys
from importlib.metadata import version, PackageNotFoundError


_DLL_DIRECTORY_HANDLES = []


def _add_conda_dll_directory_on_windows():
    if os.name != "nt" or not hasattr(os, "add_dll_directory"):
        return

    candidates = [os.environ.get("CONDA_PREFIX"), sys.prefix]
    for prefix in candidates:
        if not prefix:
            continue

        dll_dir = os.path.join(prefix, "Library", "bin")
        if not os.path.isdir(dll_dir):
            continue

        try:
            _DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(dll_dir))
        except OSError:
            continue


_add_conda_dll_directory_on_windows()

try:
    __version__ = version("tradebot")
except PackageNotFoundError:
    __version__ = "unknown"
