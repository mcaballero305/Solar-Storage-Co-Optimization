"""
microgrid

Python front-end for AMPL-based microgrid MILP sweeps and Excel post-processing.
"""

from importlib.metadata import PackageNotFoundError, version

# Package version (falls back gracefully when running from source)
try:
    __version__ = version("microgrid")
except PackageNotFoundError:  # e.g. when not installed via pip yet
    __version__ = "0.0.0"

# Convenience re-exports so you can do:
#   from microgrid import model_helpers
# instead of microgrid.core.model_helpers
from .core import model_helpers, excel_utils, logging_utils, pv_sizing_limits  # noqa: F401

__all__ = [
    "model_helpers",
    "excel_utils",
    "logging_utils",
    "pv_sizing_limits",
    "__version__",
]
