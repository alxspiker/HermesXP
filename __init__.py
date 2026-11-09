"""Hermes MSN platform plugin.

The loader imports this package and calls register(ctx); the platform
adapter lives in adapter.py.
"""
from .adapter import register

__all__ = ["register"]
