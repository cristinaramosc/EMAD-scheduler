"""Compatibility shim to expose the package `backend.scheduler_engine` as
`scheduler_engine` so legacy imports continue to work during tests.
"""
import importlib
import sys

# Import the real package under backend.scheduler_engine
real_pkg = importlib.import_module("backend.scheduler_engine")

# Insert into sys.modules under the legacy name
sys.modules["scheduler_engine"] = real_pkg

# Re-export attributes
from backend.scheduler_engine import *  # noqa: F401,F403
