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


def make_record(
    content,
    *,
    memory_id="mem_1",
    category="fact",
    source="behavioral",
    trust=0.5,
    importance=0.5,
    **metadata,
):
    """Build a MemoryRecord for tests, with the interim backend's extras.

    Consumers now receive MemoryRecords rather than the interim backend's dicts,
    so tests construct the contract's type. importance stays in metadata, where
    the contract puts it -- it is salience, not epistemic weight.
    """
    from custom_components.pepa_sensory_arm.memory_interface import MemoryRecord

    meta = {"importance": importance}
    meta.update(metadata)
    return MemoryRecord(
        id=memory_id,
        content=content,
        category=category,
        source=source,
        created_at=1000.0,
        updated_at=1000.0,
        trust=trust,
        metadata=meta,
    )
