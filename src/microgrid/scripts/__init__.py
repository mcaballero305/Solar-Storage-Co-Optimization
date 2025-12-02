"""
CLI entrypoints for the microgrid package.

These modules are hooked up to console scripts in pyproject.toml:
- run_single_loop: single-run CLI (one PV/BESS configuration).
- run_sweep:       sweep-run CLI (one sweep CSV).
- parallel_sweep:  launcher for multiple sweep files.
"""

from . import run_single_loop, run_sweep, parallel_sweep  # noqa: F401

__all__ = [
    "run_single_loop",
    "run_sweep",
    "parallel_sweep",
]
