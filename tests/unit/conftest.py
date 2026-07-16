"""Shared fixtures for unit tests."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_store():
    """Create a mock Store instance."""
    with patch("custom_components.pepa_sensory_arm.memory_manager.Store") as mock:
        store = MagicMock()
        store.async_load = AsyncMock(return_value=None)
        store.async_save = AsyncMock()
        mock.return_value = store
        yield store


@pytest.fixture
def mock_chroma_factory():
    """Create a mock ChromaClientFactory.

    This fixture used to be `mock_vector_db_manager`, mocking `_embed_text` and
    `_client` onto a VectorDBManager stand-in -- the borrowed-client shape
    itself, reproduced in the tests. Memory now gets its client and its
    embeddings from the factory and never touches VectorDBManager.
    """
    factory = MagicMock()
    factory.embed_text = AsyncMock(return_value=[0.1] * 384)
    factory.evict_entity = MagicMock()
    factory.clear_cache = MagicMock()
    factory.available = True

    collection = MagicMock()
    collection.query = MagicMock(
        return_value={
            "ids": [[]],
            "distances": [[]],
            "documents": [[]],
            "metadatas": [[]],
        }
    )
    collection.upsert = MagicMock()
    collection.delete = MagicMock()

    client = MagicMock()
    client.get_or_create_collection = MagicMock(return_value=collection)
    factory.get_client = AsyncMock(return_value=client)

    return factory
