"""Context providers for pepa_sensory_arm.

This package provides different strategies for gathering and formatting
context to be injected into LLM prompts.

Available Providers:
    - DirectContextProvider: Directly fetches configured entities
    - VectorDBContextProvider: Semantic entity search using ChromaDB
    - RetrievalContextProvider: Generic retrieval over additional ChromaDB collections
"""

from .base import ContextProvider
from .direct import DirectContextProvider
from .retrieval import RetrievalContextProvider
from .vector_db import VectorDBContextProvider

__all__ = [
    "ContextProvider",
    "DirectContextProvider",
    "RetrievalContextProvider",
    "VectorDBContextProvider",
]
