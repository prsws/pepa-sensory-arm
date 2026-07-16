"""Embedding generation and cache.

Lifted out of VectorDBManager so that both it and MemoryManager can embed text
without one reaching into the other. Owns the embedding providers, their
long-lived HTTP clients, and the embedding cache.

Cache namespacing:
    Entity state-text and memory queries live in separate LRU namespaces, each
    with its own budget. Sharing one LRU would let memory recall queries and
    entity state-text evict each other -- a fast-path latency change on the 4 GB
    VM, smuggled in under a refactor. Namespacing preserves today's entity
    hit-rate byte-for-byte and defers the shared-vs-split question to P6, whose
    benchmark is the instrument that should answer it.

    Per-entity eviction applies within the entity namespace only; the memory
    namespace is plain LRU.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections import OrderedDict
from typing import Any, Literal

import aiohttp
import homeassistant.helpers.httpx_client
import httpx
from homeassistant.core import HomeAssistant

from .const import (
    CONF_EMBEDDING_KEEP_ALIVE,
    CONF_OPENAI_API_KEY,
    CONF_VECTOR_DB_EMBEDDING_BASE_URL,
    CONF_VECTOR_DB_EMBEDDING_MODEL,
    CONF_VECTOR_DB_EMBEDDING_PROVIDER,
    DEFAULT_EMBEDDING_KEEP_ALIVE,
    DEFAULT_RETRY_BACKOFF_FACTOR,
    DEFAULT_RETRY_INITIAL_DELAY,
    DEFAULT_RETRY_JITTER,
    DEFAULT_RETRY_MAX_ATTEMPTS,
    DEFAULT_RETRY_MAX_DELAY,
    DEFAULT_VECTOR_DB_EMBEDDING_BASE_URL,
    DEFAULT_VECTOR_DB_EMBEDDING_MODEL,
    DEFAULT_VECTOR_DB_EMBEDDING_PROVIDER,
    EMBEDDING_CACHE_MAX_SIZE,
    EMBEDDING_PROVIDER_OLLAMA,
    EMBEDDING_PROVIDER_OPENAI,
    MEMORY_EMBEDDING_CACHE_MAX_SIZE,
)
from .exceptions import ContextInjectionError
from .helpers import render_template_value, retry_async

try:
    import openai

    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

_LOGGER = logging.getLogger(__name__)

CacheNamespace = Literal["entity", "memory"]

# Cache namespaces. Which namespace a call lands in is a property of the caller,
# not of its arguments: VectorDBManager's query embeds and MemoryManager's recall
# queries both pass entity_id=None, so entity_id cannot select the namespace.
CACHE_NS_ENTITY: CacheNamespace = "entity"
CACHE_NS_MEMORY: CacheNamespace = "memory"

# Per-namespace budgets. The entity namespace keeps exactly today's size so its
# hit-rate is unchanged by this refactor.
_NAMESPACE_BUDGETS: dict[str, int] = {
    CACHE_NS_ENTITY: EMBEDDING_CACHE_MAX_SIZE,
    CACHE_NS_MEMORY: MEMORY_EMBEDDING_CACHE_MAX_SIZE,
}


class Embedder:
    """Generates and caches text embeddings for one config entry.

    Held by ChromaClientFactory and reached through it, so that neither manager
    owns the embedding stack and neither has to borrow it from the other.
    """

    def __init__(self, hass: HomeAssistant, config: dict[str, Any]) -> None:
        """Initialize the embedder.

        Args:
            hass: Home Assistant instance.
            config: Configuration dictionary for this entry.
        """
        self.hass = hass
        self.config = config

        self.embedding_model = config.get(
            CONF_VECTOR_DB_EMBEDDING_MODEL, DEFAULT_VECTOR_DB_EMBEDDING_MODEL
        )
        self.embedding_provider = config.get(
            CONF_VECTOR_DB_EMBEDDING_PROVIDER, DEFAULT_VECTOR_DB_EMBEDDING_PROVIDER
        )
        self.embedding_base_url = config.get(
            CONF_VECTOR_DB_EMBEDDING_BASE_URL, DEFAULT_VECTOR_DB_EMBEDDING_BASE_URL
        )
        self.openai_api_key = render_template_value(hass, config.get(CONF_OPENAI_API_KEY, ""))

        # One LRU per namespace, each with its own budget.
        self._caches: dict[str, OrderedDict[str, list[float]]] = {
            CACHE_NS_ENTITY: OrderedDict(),
            CACHE_NS_MEMORY: OrderedDict(),
        }
        # entity_id -> cache_key, so stale state-text embeddings can be evicted
        # when an entity's state changes. Entity namespace only.
        self._entity_cache_keys: dict[str, str] = {}

        # Shared HTTP clients (created lazily, reused across requests).
        self._aiohttp_session: aiohttp.ClientSession | None = None
        self._openai_client: Any | None = None

    async def embed_text(
        self,
        text: str,
        entity_id: str | None = None,
        namespace: CacheNamespace = CACHE_NS_ENTITY,
    ) -> list[float]:
        """Embed text, serving from the namespace's cache when possible.

        Args:
            text: Text to embed.
            entity_id: Enables per-entity cache eviction. When provided, any
                previous cache entry for this entity is removed before inserting
                the new one, preventing stale entries from accumulating as entity
                state changes. Meaningful in the entity namespace only.
            namespace: Which cache namespace this call belongs to. Defaults to
                the entity namespace, preserving VectorDBManager's behavior.

        Returns:
            Embedding vector.

        Raises:
            ContextInjectionError: If embedding fails.
        """
        cache = self._caches[namespace]
        cache_key = hashlib.md5(text.encode()).hexdigest()

        if cache_key in cache:
            cache.move_to_end(cache_key)
            # Update entity->key mapping even on cache hit (idempotent)
            if entity_id is not None:
                self._entity_cache_keys[entity_id] = cache_key
            return cache[cache_key]

        # Evict the previous cache entry for this entity (stale state text)
        if entity_id is not None:
            old_key = self._entity_cache_keys.get(entity_id)
            if old_key is not None and old_key != cache_key:
                cache.pop(old_key, None)
            self._entity_cache_keys[entity_id] = cache_key

        try:
            embedding: list[float]
            if self.embedding_provider == EMBEDDING_PROVIDER_OPENAI:
                embedding = await self._embed_with_openai(text)
            elif self.embedding_provider == EMBEDDING_PROVIDER_OLLAMA:
                embedding = await self._embed_with_ollama(text)
            else:
                raise ContextInjectionError(
                    f"Unknown embedding provider: {self.embedding_provider}"
                )

            cache[cache_key] = embedding
            # Evict oldest entries if over this namespace's budget. Namespaces
            # never evict each other.
            while len(cache) > _NAMESPACE_BUDGETS[namespace]:
                cache.popitem(last=False)
            return embedding

        except Exception as err:
            raise ContextInjectionError(f"Embedding failed: {err}") from err

    def evict_entity(self, entity_id: str) -> None:
        """Drop an entity's cached embedding.

        Called when an entity leaves the index. Entity namespace only -- a
        removed entity has no bearing on cached memory queries.
        """
        old_key = self._entity_cache_keys.pop(entity_id, None)
        if old_key is not None:
            self._caches[CACHE_NS_ENTITY].pop(old_key, None)

    def clear_cache(self, namespace: CacheNamespace | None = None) -> None:
        """Clear one namespace, or all of them.

        Args:
            namespace: The namespace to clear. None clears every namespace, which
                only the owner of the whole embedder should do.
        """
        if namespace is None:
            for cache in self._caches.values():
                cache.clear()
            self._entity_cache_keys.clear()
            return

        self._caches[namespace].clear()
        if namespace == CACHE_NS_ENTITY:
            self._entity_cache_keys.clear()

    def cache_size(self, namespace: CacheNamespace) -> int:
        """Number of entries cached in a namespace."""
        return len(self._caches[namespace])

    async def _embed_with_openai(self, text: str) -> list[float]:
        """Generate embedding using OpenAI API.

        Args:
            text: Text to embed

        Returns:
            Embedding vector
        """
        if not OPENAI_AVAILABLE:
            raise ContextInjectionError(
                "OpenAI library not installed. Install with: pip install openai"
            )

        if not self.openai_api_key:
            raise ContextInjectionError(
                "OpenAI API key not configured. " "Please configure it in Vector DB settings."
            )

        # Reuse OpenAI client across requests
        if self._openai_client is None:
            self._openai_client = openai.AsyncOpenAI(
                api_key=self.openai_api_key,
                base_url=self.embedding_base_url,
                http_client=homeassistant.helpers.httpx_client.get_async_client(hass=self.hass),
            )

        client = self._openai_client

        # Use the new API for embeddings
        async def _request() -> openai.types.CreateEmbeddingResponse:
            return await client.embeddings.create(model=self.embedding_model, input=text)

        response = await retry_async(
            _request,
            max_retries=DEFAULT_RETRY_MAX_ATTEMPTS,
            retryable_exceptions=(httpx.HTTPError,),
            non_retryable_exceptions=(openai.OpenAIError,),
            initial_delay=DEFAULT_RETRY_INITIAL_DELAY,
            backoff_factor=DEFAULT_RETRY_BACKOFF_FACTOR,
            max_delay=DEFAULT_RETRY_MAX_DELAY,
            jitter=DEFAULT_RETRY_JITTER,
        )
        embedding: list[float] = response.data[0].embedding
        return embedding

    async def _ensure_aiohttp_session(self) -> aiohttp.ClientSession:
        """Ensure aiohttp session exists for Ollama requests."""
        if self._aiohttp_session is None or self._aiohttp_session.closed:
            self._aiohttp_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        return self._aiohttp_session

    async def _embed_with_ollama(self, text: str) -> list[float]:
        """Generate embedding using Ollama API.

        Args:
            text: Text to embed

        Returns:
            Embedding vector
        """
        url = f"{self.embedding_base_url.rstrip('/')}/api/embeddings"
        payload = {
            "model": self.embedding_model,
            "prompt": text,
            "keep_alive": self.config.get(CONF_EMBEDDING_KEEP_ALIVE, DEFAULT_EMBEDDING_KEEP_ALIVE),
        }

        async def make_embedding_request() -> list[float]:
            """Make the embedding request to Ollama."""
            try:
                session = await self._ensure_aiohttp_session()
                async with session.post(url, json=payload) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise ContextInjectionError(
                            f"Ollama API error {response.status}: {error_text}"
                        )
                    result = await response.json()
                    embedding: list[float] = result["embedding"]
                    return embedding
            except aiohttp.ClientError as err:
                raise ContextInjectionError(
                    f"Failed to connect to Ollama at {self.embedding_base_url}: {err}"
                ) from err

        embedding: list[float] = await retry_async(
            make_embedding_request,
            max_retries=DEFAULT_RETRY_MAX_ATTEMPTS,
            retryable_exceptions=(aiohttp.ClientError, asyncio.TimeoutError),
            initial_delay=DEFAULT_RETRY_INITIAL_DELAY,
            backoff_factor=DEFAULT_RETRY_BACKOFF_FACTOR,
            max_delay=DEFAULT_RETRY_MAX_DELAY,
            jitter=DEFAULT_RETRY_JITTER,
        )
        return embedding

    async def async_shutdown(self) -> None:
        """Close the shared HTTP clients and drop every cache.

        Owned here, not by either manager: the embedder is shared per config
        entry, so a manager closing these would break the other one's embeds.
        Called by ChromaClientFactory.async_shutdown().
        """
        self.clear_cache()

        if self._aiohttp_session is not None:
            try:
                if not self._aiohttp_session.closed:
                    await self._aiohttp_session.close()
            except Exception:
                pass
            self._aiohttp_session = None

        if self._openai_client is not None:
            try:
                await self._openai_client.close()
            except Exception:
                pass
            self._openai_client = None
