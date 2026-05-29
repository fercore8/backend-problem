"""Data: market ingestion (live + synthetic) and persistence."""

from .sample import generate_scenario
from .repository import Repository

__all__ = ["generate_scenario", "Repository"]
