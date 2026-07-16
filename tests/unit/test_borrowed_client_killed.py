"""The borrowed-client bug is dead. These tests are the headstone.

The bug (Design Ledger §5): MemoryManager parasitized VectorDBManager's ChromaDB
client, so switching the entity-context Context Mode to Direct silently killed
memory vector search, Chroma sync, and dedup. Nothing told the user. Memory just
quietly stopped remembering semantically.

Two things are pinned here:

1. **Behavior** -- memory's vector capability is independent of Context Mode.
2. **Structure** -- no first-party module reaches for the pieces the bug was made
   of. The structural checks are source scans rather than import checks on
   purpose: the worst offender found during recon (agent/core.py) fetched the
   manager out of hass.data typed as `Any`, so it never imported MemoryManager at
   all and no import-level check would have seen it.
"""

import pathlib
import re

import pytest

from custom_components.pepa_sensory_arm.const import (
    CONF_CONTEXT_MODE,
    CONF_MEMORY_COLLECTION_NAME,
    CONF_MEMORY_MAX_MEMORIES,
    CONTEXT_MODE_DIRECT,
    CONTEXT_MODE_VECTOR_DB,
    DEFAULT_MEMORY_COLLECTION_NAME,
)
from custom_components.pepa_sensory_arm.memory_manager import MemoryManager

COMPONENT_DIR = pathlib.Path("custom_components/pepa_sensory_arm")

# __init__.py constructs the managers, so it legitimately names them. Tests are
# exempt for the obvious reason.
SANCTIONED_FILES = {"__init__.py"}


def _first_party_sources():
    """Every first-party module except the sanctioned ones."""
    for path in COMPONENT_DIR.rglob("*.py"):
        if path.name in SANCTIONED_FILES:
            continue
        if "__pycache__" in path.parts:
            continue
        yield path


# ---- Behavior: Context Mode no longer touches memory --------------------


@pytest.mark.parametrize("context_mode", [CONTEXT_MODE_DIRECT, CONTEXT_MODE_VECTOR_DB, None])
async def test_memory_vector_search_works_regardless_of_context_mode(
    mock_hass, mock_store, mock_chroma_factory, context_mode
):
    """Memory can search semantically whatever Context Mode says.

    This is the bug's acceptance test. Before the fix, CONTEXT_MODE_DIRECT meant
    VectorDBManager was never constructed, so MemoryManager was handed None and
    silently dropped to store-only.
    """
    config = {
        CONF_MEMORY_MAX_MEMORIES: 100,
        CONF_MEMORY_COLLECTION_NAME: DEFAULT_MEMORY_COLLECTION_NAME,
        CONF_CONTEXT_MODE: context_mode,
    }

    manager = MemoryManager(hass=mock_hass, chroma_factory=mock_chroma_factory, config=config)
    await manager.async_initialize()
    try:
        assert manager._chromadb_available is True
        assert manager.capabilities.vector_recall is True
    finally:
        await manager.async_shutdown()


@pytest.mark.parametrize("context_mode", [CONTEXT_MODE_DIRECT, CONTEXT_MODE_VECTOR_DB, None])
async def test_capabilities_do_not_vary_with_context_mode(
    mock_hass, mock_store, mock_chroma_factory, context_mode
):
    """Flipping Context Mode does not alter declared capabilities."""
    config = {
        CONF_MEMORY_COLLECTION_NAME: DEFAULT_MEMORY_COLLECTION_NAME,
        CONF_CONTEXT_MODE: context_mode,
    }

    manager = MemoryManager(hass=mock_hass, chroma_factory=mock_chroma_factory, config=config)
    await manager.async_initialize()
    try:
        caps = manager.capabilities
    finally:
        await manager.async_shutdown()

    assert caps.vector_recall is True
    assert caps.supersession is False
    assert caps.trust_dynamics is False
    assert caps.durable_fast_track is True
    assert caps.provenance_enforced is False


async def test_memory_embeds_through_the_factory(mock_hass, mock_store, mock_chroma_factory):
    """Memory's embeddings come from the factory, in the memory namespace."""
    config = {CONF_MEMORY_COLLECTION_NAME: DEFAULT_MEMORY_COLLECTION_NAME}
    manager = MemoryManager(hass=mock_hass, chroma_factory=mock_chroma_factory, config=config)
    await manager.async_initialize()
    try:
        await manager.recall("cafe a las siete")
    finally:
        await manager.async_shutdown()

    assert mock_chroma_factory.embed_text.await_count >= 1
    for call in mock_chroma_factory.embed_text.await_args_list:
        assert call.kwargs.get("namespace") == "memory", (
            "memory must embed in its own cache namespace, or it will evict "
            "entity state-text on the fast path"
        )


async def test_no_factory_means_store_only_not_a_crash(mock_hass, mock_store):
    """No ChromaDB at all degrades to store-only, declared honestly."""
    config = {CONF_MEMORY_COLLECTION_NAME: DEFAULT_MEMORY_COLLECTION_NAME}
    manager = MemoryManager(hass=mock_hass, chroma_factory=None, config=config)
    await manager.async_initialize()
    try:
        assert manager._chromadb_available is False
        assert manager.capabilities.vector_recall is False
    finally:
        await manager.async_shutdown()


# ---- Structure: neither borrowed channel can come back ------------------


def test_memory_manager_never_reaches_into_vector_db_manager():
    """AC#4: zero `vector_db_manager._<attr>` reaches anywhere.

    An object-level scan, not a symbol-level one -- the reach was through two
    different attributes (`_embed_text` and `_client`), and naming them
    individually is how the sixth one got missed during recon.
    """
    offenders = []
    pattern = re.compile(r"vector_db_manager\._\w+")
    for path in _first_party_sources():
        for i, line in enumerate(path.read_text().splitlines(), 1):
            if pattern.search(line):
                offenders.append(f"{path}:{i}: {line.strip()}")

    assert not offenders, "borrowed-object reach reintroduced:\n" + "\n".join(offenders)


# AC#6's two source scans (no first-party import of MemoryManager; no read of
# the legacy "memory_manager" hass.data key) land with commit 5, which is what
# migrates the consumers. They would be red here, and a red test in a green
# commit teaches everyone to ignore red tests.
