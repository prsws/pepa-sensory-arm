"""Shared ChromaDB client and embedding helpers for vector-backed context providers.

This module holds the ChromaDB client initialization and query-embedding code
shared by VectorDBContextProvider and RetrievalContextProvider. The functions
were extracted verbatim from VectorDBContextProvider — pure code motion, no
behavior changes.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections import OrderedDict
from typing import TYPE_CHECKING, Any

import aiohttp
import homeassistant.helpers.httpx_client
import httpx
from homeassistant.core import HomeAssistant

from ..const import (
    CONF_OPENAI_API_KEY,
    CONF_VECTOR_DB_EMBEDDING_BASE_URL,
    CONF_VECTOR_DB_EMBEDDING_MODEL,
    CONF_VECTOR_DB_EMBEDDING_PROVIDER,
    CONF_VECTOR_DB_HOST,
    CONF_VECTOR_DB_PORT,
    DEFAULT_RETRY_BACKOFF_FACTOR,
    DEFAULT_RETRY_INITIAL_DELAY,
    DEFAULT_RETRY_JITTER,
    DEFAULT_RETRY_MAX_ATTEMPTS,
    DEFAULT_RETRY_MAX_DELAY,
    DEFAULT_VECTOR_DB_EMBEDDING_BASE_URL,
    DEFAULT_VECTOR_DB_EMBEDDING_MODEL,
    DEFAULT_VECTOR_DB_EMBEDDING_PROVIDER,
    DEFAULT_VECTOR_DB_HOST,
    DEFAULT_VECTOR_DB_PORT,
    EMBEDDING_PROVIDER_OLLAMA,
    EMBEDDING_PROVIDER_OPENAI,
)
from ..exceptions import ContextInjectionError, EmbeddingTimeoutError
from ..helpers import render_template_value, retry_async

if TYPE_CHECKING:
    from chromadb.api import ClientAPI

# Maximum number of embedding vectors to cache (each ~3-12KB)
EMBEDDING_CACHE_MAX_SIZE = 1000

# Conditional imports for ChromaDB
try:
    import chromadb

    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False

# Conditional imports for OpenAI embeddings
try:
    import openai

    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

_LOGGER = logging.getLogger(__name__)


class VectorClientMixin:
    """Mixin providing a ChromaDB client and query embedding for context providers.

    Expects the consuming class to set ``self.hass`` (HomeAssistant) before
    ``_init_vector_common`` is called.
    """

    hass: HomeAssistant

    def _init_vector_common(self, hass: HomeAssistant, config: dict[str, Any]) -> None:
        """Initialize shared ChromaDB/embedding configuration and state."""
        self.host = config.get(CONF_VECTOR_DB_HOST, DEFAULT_VECTOR_DB_HOST)
        self.port = config.get(CONF_VECTOR_DB_PORT, DEFAULT_VECTOR_DB_PORT)
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

        self._client: ClientAPI | None = None
        self._embedding_cache: OrderedDict[str, list[float]] = OrderedDict()

        # Shared HTTP clients (created lazily, reused across requests)
        self._aiohttp_session: aiohttp.ClientSession | None = None
        self._openai_client: Any | None = None

    async def _shutdown_vector_common(self) -> None:
        """Release the embedding cache and shared HTTP clients."""
        self._embedding_cache.clear()
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

    async def _ensure_client(self) -> None:
        """Ensure the ChromaDB client is initialized."""
        if self._client is None:
            try:
                # Create ChromaDB client in executor to avoid blocking the event loop
                # ChromaDB's HttpClient does SSL setup and file I/O during init
                from functools import partial

                create_client = partial(
                    chromadb.HttpClient,
                    host=self.host,
                    port=self.port,
                )
                self._client = await self.hass.async_add_executor_job(create_client)
                _LOGGER.debug("ChromaDB client connected")
            except Exception as err:
                raise ContextInjectionError(f"Failed to connect to ChromaDB: {err}") from err

    async def _embed_query(self, text: str) -> list[float]:
        """Embed text using configured embedding model."""
        cache_key = hashlib.md5(text.encode()).hexdigest()
        if cache_key in self._embedding_cache:
            self._embedding_cache.move_to_end(cache_key)
            return self._embedding_cache[cache_key]

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

            self._embedding_cache[cache_key] = embedding
            # Evict oldest entries if over limit
            while len(self._embedding_cache) > EMBEDDING_CACHE_MAX_SIZE:
                self._embedding_cache.popitem(last=False)
            return embedding

        except Exception as err:
            raise ContextInjectionError(f"Embedding failed: {err}") from err

    async def _embed_with_openai(self, text: str) -> list[float]:
        """Generate embedding using OpenAI API."""
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
        """Generate embedding using Ollama API."""
        url = f"{self.embedding_base_url.rstrip('/')}/api/embeddings"
        payload = {"model": self.embedding_model, "prompt": text}

        try:
            session = await self._ensure_aiohttp_session()
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise ContextInjectionError(f"Ollama API error {response.status}: {error_text}")
                result = await response.json()
                embedding: list[float] = result["embedding"]
                return embedding
        except asyncio.TimeoutError as err:
            raise EmbeddingTimeoutError(
                f"Ollama embedding timed out after 30s for model {self.embedding_model}"
            ) from err
        except aiohttp.ClientError as err:
            raise ContextInjectionError(
                f"Failed to connect to Ollama at {self.embedding_base_url}: {err}"
            ) from err
