"""Unit tests for Embedder.

Embedding generation and its cache moved here out of VectorDBManager so that
both managers can embed without one reaching into the other. These tests are
ported from test_vector_db_manager.py -- the provider and cache behavior they
cover is unchanged, only its owner is.

The namespace tests are new: they pin AC#8, that entity and memory embeddings
cannot evict each other.
"""

import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from custom_components.pepa_sensory_arm.const import (
    CONF_OPENAI_API_KEY,
    CONF_VECTOR_DB_EMBEDDING_BASE_URL,
    CONF_VECTOR_DB_EMBEDDING_MODEL,
    CONF_VECTOR_DB_EMBEDDING_PROVIDER,
    EMBEDDING_CACHE_MAX_SIZE,
    EMBEDDING_PROVIDER_OLLAMA,
    EMBEDDING_PROVIDER_OPENAI,
)
from custom_components.pepa_sensory_arm.embedder import (
    CACHE_NS_ENTITY,
    CACHE_NS_MEMORY,
    Embedder,
)
from custom_components.pepa_sensory_arm.exceptions import ContextInjectionError


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = MagicMock()
    hass.data = {}
    return hass


@pytest.fixture
def ollama_config():
    """Config selecting the Ollama embedding provider."""
    return {
        CONF_VECTOR_DB_EMBEDDING_PROVIDER: EMBEDDING_PROVIDER_OLLAMA,
        CONF_VECTOR_DB_EMBEDDING_MODEL: "nomic-embed-text",
        CONF_VECTOR_DB_EMBEDDING_BASE_URL: "http://localhost:11434",
    }


@pytest.fixture
def embedder(mock_hass, ollama_config):
    """An embedder with a stubbed generation path."""
    return Embedder(mock_hass, ollama_config)


def _key(text):
    """The cache key for a given text."""
    return hashlib.md5(text.encode()).hexdigest()


# ---- Cache behavior (ported) --------------------------------------------


@pytest.mark.asyncio
async def test_embed_text_uses_cache(embedder):
    """A cached embedding is served without calling a provider."""
    text = "test entity"
    cached = [0.5] * 384
    embedder._caches[CACHE_NS_ENTITY][_key(text)] = cached

    embedder._embed_with_openai = AsyncMock()
    embedder._embed_with_ollama = AsyncMock()

    result = await embedder.embed_text(text)

    assert result == cached
    embedder._embed_with_openai.assert_not_called()
    embedder._embed_with_ollama.assert_not_called()


@pytest.mark.asyncio
async def test_embed_text_cache_miss_generates_new(embedder):
    """A miss calls the provider and caches the result."""
    text = "uncached entity"
    expected = [0.7] * 384
    embedder._embed_with_ollama = AsyncMock(return_value=expected)

    result = await embedder.embed_text(text)

    assert result == expected
    embedder._embed_with_ollama.assert_awaited_once_with(text)
    assert embedder._caches[CACHE_NS_ENTITY][_key(text)] == expected


@pytest.mark.asyncio
async def test_embed_text_entity_id_evicts_stale_cache(embedder):
    """A changed entity's previous embedding is evicted, not left to linger."""
    entity_id = "sensor.temperature"
    old_text = "Entity: Temperature | Current state: 72.1"
    new_text = "Entity: Temperature | Current state: 72.2"
    embedder._embed_with_ollama = AsyncMock(return_value=[0.1] * 384)

    await embedder.embed_text(old_text, entity_id=entity_id)
    await embedder.embed_text(new_text, entity_id=entity_id)

    cache = embedder._caches[CACHE_NS_ENTITY]
    assert _key(old_text) not in cache
    assert _key(new_text) in cache
    assert len(cache) == 1
    assert embedder._entity_cache_keys[entity_id] == _key(new_text)


@pytest.mark.asyncio
async def test_embed_text_without_entity_id_no_eviction(embedder):
    """Without an entity_id there is nothing to evict; entries accumulate."""
    embedder._embed_with_ollama = AsyncMock(return_value=[0.1] * 384)

    await embedder.embed_text("first query")
    await embedder.embed_text("second query")

    assert len(embedder._caches[CACHE_NS_ENTITY]) == 2
    assert len(embedder._entity_cache_keys) == 0


@pytest.mark.asyncio
async def test_evict_entity_drops_cached_embedding(embedder):
    """evict_entity removes the entity's entry and its key mapping."""
    entity_id = "sensor.humidity"
    text = "Entity: Humidity | Current state: 55"
    embedder._embed_with_ollama = AsyncMock(return_value=[0.3] * 384)
    await embedder.embed_text(text, entity_id=entity_id)

    embedder.evict_entity(entity_id)

    assert _key(text) not in embedder._caches[CACHE_NS_ENTITY]
    assert entity_id not in embedder._entity_cache_keys


@pytest.mark.asyncio
async def test_entity_namespace_budget_unchanged(embedder):
    """The entity namespace still evicts at exactly today's budget."""
    embedder._embed_with_ollama = AsyncMock(return_value=[0.1] * 8)

    for i in range(EMBEDDING_CACHE_MAX_SIZE + 5):
        await embedder.embed_text(f"text-{i}")

    assert embedder.cache_size(CACHE_NS_ENTITY) == EMBEDDING_CACHE_MAX_SIZE


# ---- Namespace isolation (AC#8) -----------------------------------------


@pytest.mark.asyncio
async def test_memory_entries_do_not_evict_entity_entries(embedder):
    """Filling the memory namespace leaves entity entries untouched.

    Sharing one LRU would let memory recall queries evict entity state-text --
    a fast-path latency change smuggled in under a refactor.
    """
    embedder._embed_with_ollama = AsyncMock(return_value=[0.1] * 8)
    await embedder.embed_text("entity text", namespace=CACHE_NS_ENTITY)

    for i in range(EMBEDDING_CACHE_MAX_SIZE + 20):
        await embedder.embed_text(f"memory query {i}", namespace=CACHE_NS_MEMORY)

    assert _key("entity text") in embedder._caches[CACHE_NS_ENTITY]
    assert embedder.cache_size(CACHE_NS_ENTITY) == 1


@pytest.mark.asyncio
async def test_entity_entries_do_not_evict_memory_entries(embedder):
    """And the converse: entity churn does not cost memory its cache."""
    embedder._embed_with_ollama = AsyncMock(return_value=[0.1] * 8)
    await embedder.embed_text("memory query", namespace=CACHE_NS_MEMORY)

    for i in range(EMBEDDING_CACHE_MAX_SIZE + 20):
        await embedder.embed_text(f"entity text {i}", namespace=CACHE_NS_ENTITY)

    assert _key("memory query") in embedder._caches[CACHE_NS_MEMORY]
    assert embedder.cache_size(CACHE_NS_MEMORY) == 1


@pytest.mark.asyncio
async def test_same_text_cached_per_namespace(embedder):
    """Identical text in two namespaces occupies two independent entries."""
    embedder._embed_with_ollama = AsyncMock(return_value=[0.1] * 8)

    await embedder.embed_text("shared", namespace=CACHE_NS_ENTITY)
    await embedder.embed_text("shared", namespace=CACHE_NS_MEMORY)

    assert embedder.cache_size(CACHE_NS_ENTITY) == 1
    assert embedder.cache_size(CACHE_NS_MEMORY) == 1


@pytest.mark.asyncio
async def test_clear_cache_clears_only_named_namespace(embedder):
    """Clearing one namespace leaves the other intact.

    This is the ruling that VectorDBManager.async_shutdown() must not evict
    memory's entries.
    """
    embedder._embed_with_ollama = AsyncMock(return_value=[0.1] * 8)
    await embedder.embed_text("entity text", namespace=CACHE_NS_ENTITY)
    await embedder.embed_text("memory query", namespace=CACHE_NS_MEMORY)

    embedder.clear_cache(CACHE_NS_ENTITY)

    assert embedder.cache_size(CACHE_NS_ENTITY) == 0
    assert embedder.cache_size(CACHE_NS_MEMORY) == 1


@pytest.mark.asyncio
async def test_clear_cache_without_namespace_clears_all(embedder):
    """Clearing with no namespace clears everything -- the owner's prerogative."""
    embedder._embed_with_ollama = AsyncMock(return_value=[0.1] * 8)
    await embedder.embed_text("entity text", entity_id="sensor.x", namespace=CACHE_NS_ENTITY)
    await embedder.embed_text("memory query", namespace=CACHE_NS_MEMORY)

    embedder.clear_cache()

    assert embedder.cache_size(CACHE_NS_ENTITY) == 0
    assert embedder.cache_size(CACHE_NS_MEMORY) == 0
    assert len(embedder._entity_cache_keys) == 0


# ---- Provider dispatch (ported) -----------------------------------------


@pytest.mark.asyncio
async def test_embed_text_unknown_provider(mock_hass, ollama_config):
    """An unrecognized provider fails loudly."""
    config = ollama_config.copy()
    config[CONF_VECTOR_DB_EMBEDDING_PROVIDER] = "not_a_provider"
    embedder = Embedder(mock_hass, config)

    with pytest.raises(ContextInjectionError, match="Embedding failed"):
        await embedder.embed_text("some text")


@pytest.mark.asyncio
async def test_embed_with_ollama_success(mock_hass, ollama_config):
    """Ollama returns the embedding from its response body."""
    embedder = Embedder(mock_hass, ollama_config)
    expected = [0.4] * 768

    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={"embedding": expected})
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_response)
    mock_session.closed = False
    embedder._aiohttp_session = mock_session

    async def mock_retry(func, **kwargs):
        return await func()

    with patch(
        "custom_components.pepa_sensory_arm.embedder.retry_async",
        side_effect=mock_retry,
    ):
        result = await embedder._embed_with_ollama("test entity")

    assert result == expected


@pytest.mark.asyncio
async def test_embed_with_ollama_api_error(mock_hass, ollama_config):
    """A non-200 from Ollama surfaces as ContextInjectionError."""
    embedder = Embedder(mock_hass, ollama_config)

    mock_response = MagicMock()
    mock_response.status = 500
    mock_response.text = AsyncMock(return_value="internal error")
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_response)
    mock_session.closed = False
    embedder._aiohttp_session = mock_session

    async def mock_retry(func, **kwargs):
        return await func()

    with patch(
        "custom_components.pepa_sensory_arm.embedder.retry_async",
        side_effect=mock_retry,
    ):
        with pytest.raises(ContextInjectionError, match="Ollama API error 500"):
            await embedder._embed_with_ollama("test entity")


@pytest.mark.asyncio
async def test_embed_with_ollama_timeout(mock_hass, ollama_config):
    """A connection failure names Ollama and its URL."""
    embedder = Embedder(mock_hass, ollama_config)

    mock_session = MagicMock()
    mock_session.post = MagicMock(side_effect=aiohttp.ClientError("timed out"))
    mock_session.closed = False
    embedder._aiohttp_session = mock_session

    async def mock_retry(func, **kwargs):
        return await func()

    with patch(
        "custom_components.pepa_sensory_arm.embedder.retry_async",
        side_effect=mock_retry,
    ):
        with pytest.raises(ContextInjectionError, match="Failed to connect to Ollama"):
            await embedder._embed_with_ollama("test entity")


@pytest.mark.asyncio
async def test_embed_with_openai_success(mock_hass, ollama_config):
    """OpenAI returns the embedding from the first data element."""
    config = ollama_config.copy()
    config[CONF_VECTOR_DB_EMBEDDING_PROVIDER] = EMBEDDING_PROVIDER_OPENAI
    config[CONF_OPENAI_API_KEY] = "sk-test"
    config[CONF_VECTOR_DB_EMBEDDING_MODEL] = "text-embedding-3-small"
    embedder = Embedder(mock_hass, config)
    expected = [0.2] * 1536

    mock_datum = MagicMock()
    mock_datum.embedding = expected
    mock_result = MagicMock()
    mock_result.data = [mock_datum]

    async def mock_retry(func, **kwargs):
        return await func()

    mock_client = MagicMock()
    mock_client.embeddings.create = AsyncMock(return_value=mock_result)

    with (
        patch("custom_components.pepa_sensory_arm.embedder.OPENAI_AVAILABLE", True),
        patch("custom_components.pepa_sensory_arm.embedder.retry_async", side_effect=mock_retry),
    ):
        embedder._openai_client = mock_client
        result = await embedder._embed_with_openai("test entity")

    assert result == expected


@pytest.mark.asyncio
async def test_embed_with_openai_missing_api_key(mock_hass, ollama_config):
    """No API key is a configuration error, named as such."""
    config = ollama_config.copy()
    config[CONF_VECTOR_DB_EMBEDDING_PROVIDER] = EMBEDDING_PROVIDER_OPENAI
    config[CONF_OPENAI_API_KEY] = ""
    embedder = Embedder(mock_hass, config)

    with patch("custom_components.pepa_sensory_arm.embedder.OPENAI_AVAILABLE", True):
        with pytest.raises(ContextInjectionError, match="OpenAI API key not configured"):
            await embedder._embed_with_openai("test entity")


@pytest.mark.asyncio
async def test_embed_with_openai_library_not_available(mock_hass, ollama_config):
    """A missing openai package is reported with the install hint."""
    config = ollama_config.copy()
    config[CONF_VECTOR_DB_EMBEDDING_PROVIDER] = EMBEDDING_PROVIDER_OPENAI
    config[CONF_OPENAI_API_KEY] = "sk-test"
    embedder = Embedder(mock_hass, config)

    with patch("custom_components.pepa_sensory_arm.embedder.OPENAI_AVAILABLE", False):
        with pytest.raises(ContextInjectionError, match="OpenAI library not installed"):
            await embedder._embed_with_openai("test entity")


@pytest.mark.asyncio
async def test_embed_with_openai_api_error(mock_hass, ollama_config):
    """An API failure propagates rather than being swallowed."""
    config = ollama_config.copy()
    config[CONF_VECTOR_DB_EMBEDDING_PROVIDER] = EMBEDDING_PROVIDER_OPENAI
    config[CONF_OPENAI_API_KEY] = "sk-test"
    embedder = Embedder(mock_hass, config)

    async def mock_retry(func, **kwargs):
        return await func()

    mock_client = MagicMock()
    mock_client.embeddings.create = AsyncMock(side_effect=Exception("API is down"))

    with (
        patch("custom_components.pepa_sensory_arm.embedder.OPENAI_AVAILABLE", True),
        patch("custom_components.pepa_sensory_arm.embedder.retry_async", side_effect=mock_retry),
    ):
        embedder._openai_client = mock_client
        with pytest.raises(Exception, match="API is down"):
            await embedder._embed_with_openai("test entity")


@pytest.mark.asyncio
async def test_embed_text_wraps_provider_failure(embedder):
    """Provider failures reach callers as ContextInjectionError."""
    embedder._embed_with_ollama = AsyncMock(side_effect=RuntimeError("boom"))

    with pytest.raises(ContextInjectionError, match="Embedding failed"):
        await embedder.embed_text("some text")


# ---- Shutdown -----------------------------------------------------------


@pytest.mark.asyncio
async def test_shutdown_closes_clients_and_clears_caches(embedder):
    """Shutdown closes the shared HTTP clients and drops every namespace."""
    embedder._embed_with_ollama = AsyncMock(return_value=[0.1] * 8)
    await embedder.embed_text("entity text", namespace=CACHE_NS_ENTITY)
    await embedder.embed_text("memory query", namespace=CACHE_NS_MEMORY)

    mock_session = MagicMock()
    mock_session.closed = False
    mock_session.close = AsyncMock()
    embedder._aiohttp_session = mock_session

    mock_openai = MagicMock()
    mock_openai.close = AsyncMock()
    embedder._openai_client = mock_openai

    await embedder.async_shutdown()

    mock_session.close.assert_awaited_once()
    mock_openai.close.assert_awaited_once()
    assert embedder._aiohttp_session is None
    assert embedder._openai_client is None
    assert embedder.cache_size(CACHE_NS_ENTITY) == 0
    assert embedder.cache_size(CACHE_NS_MEMORY) == 0


@pytest.mark.asyncio
async def test_shutdown_tolerates_close_failures(embedder):
    """A client that refuses to close does not break unload."""
    mock_session = MagicMock()
    mock_session.closed = False
    mock_session.close = AsyncMock(side_effect=RuntimeError("already gone"))
    embedder._aiohttp_session = mock_session

    await embedder.async_shutdown()

    assert embedder._aiohttp_session is None


@pytest.mark.asyncio
async def test_ensure_aiohttp_session_reuses_open_session(embedder):
    """The session is created once and reused across requests."""
    first = await embedder._ensure_aiohttp_session()
    second = await embedder._ensure_aiohttp_session()

    assert first is second
    await first.close()


@pytest.mark.asyncio
async def test_ensure_aiohttp_session_replaces_closed_session(embedder):
    """A closed session is replaced rather than reused."""
    closed = MagicMock()
    closed.closed = True
    embedder._aiohttp_session = closed

    session = await embedder._ensure_aiohttp_session()

    assert session is not closed
    assert isinstance(session, aiohttp.ClientSession)
    await session.close()
