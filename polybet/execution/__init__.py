"""Execution: turn an approved order into a fill (paper or live)."""

from .base import Executor
from .paper import PaperExecutor

__all__ = ["Executor", "PaperExecutor"]
