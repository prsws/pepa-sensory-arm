"""Vector DB (ChromaDB) context provider for Pepa Sensory Arm.

This module provides semantic search-based context injection using ChromaDB
vector database and embedding models.

The "additional collections" retrieval that used to live here as a second
tier now lives in RetrievalContextProvider (retrieval.py); the shared
client/embedding helpers live in _vector_common.py.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, Sequence, cast

from homeassistant.core import HomeAssistant

if TYPE_CHECKING:
    from chromadb.api.models.Collection import Collection

from ..const import (
    CONF_EMIT_EVENTS,
    CONF_VECTOR_DB_COLLECTION,
    CONF_VECTOR_DB_SIMILARITY_THRESHOLD,
    CONF_VECTOR_DB_TOP_K,
    DEFAULT_VECTOR_DB_COLLECTION,
    DEFAULT_VECTOR_DB_SIMILARITY_THRESHOLD,
    DEFAULT_VECTOR_DB_TOP_K,
    EVENT_VECTOR_DB_QUERIED,
)
from ..exceptions import ContextInjectionError, EmbeddingTimeoutError
from ._vector_common import (  # noqa: F401  (re-exported for tests/consumers)
    CHROMADB_AVAILABLE,
    EMBEDDING_CACHE_MAX_SIZE,
    OPENAI_AVAILABLE,
    VectorClientMixin,
)
from .base import ContextProvider
from .direct import DirectContextProvider

_LOGGER = logging.getLogger(__name__)


class VectorDBContextProvider(VectorClientMixin, ContextProvider):
    """Context provider using ChromaDB for semantic entity search."""

    def __init__(self, hass: HomeAssistant, config: dict[str, Any]) -> None:
        """Initialize the Vector DB context provider."""
        super().__init__(hass, config)

        if not CHROMADB_AVAILABLE:
            raise ContextInjectionError(
                "ChromaDB not installed. Install with: pip install chromadb"
            )

        self.collection_name = config.get(CONF_VECTOR_DB_COLLECTION, DEFAULT_VECTOR_DB_COLLECTION)
        self.top_k = config.get(CONF_VECTOR_DB_TOP_K, DEFAULT_VECTOR_DB_TOP_K)
        self.similarity_threshold = config.get(
            CONF_VECTOR_DB_SIMILARITY_THRESHOLD, DEFAULT_VECTOR_DB_SIMILARITY_THRESHOLD
        )

        self._init_vector_common(hass, config)
        self._collection: Collection | None = None
        self._fallback_provider: DirectContextProvider | None = None
        self._emit_events = config.get(CONF_EMIT_EVENTS, True)

        _LOGGER.info(
            "Vector DB provider initialized (host=%s:%s, collection=%s)",
            self.host,
            self.port,
            self.collection_name,
        )

    async def async_shutdown(self) -> None:
        """Clean up resources."""
        await self._shutdown_vector_common()

    async def get_context(self, user_input: str) -> str:
        """Get relevant entity context via semantic search."""
        try:
            await self._ensure_initialized()
            query_embedding = await self._embed_query(user_input)

            # Query entity collection
            entity_results = await self._query_vector_db(query_embedding, self.top_k)

            # ChromaDB uses L2 distance - smaller distances mean more similar
            # Filter to keep only results with distance below threshold
            filtered_entity_results = [
                r
                for r in entity_results
                if r.get("distance", float("inf")) <= self.similarity_threshold
            ]

            # Build entity context
            entity_context = ""
            if filtered_entity_results:
                entity_ids = [r["entity_id"] for r in filtered_entity_results]
                entities = []

                for entity_id in entity_ids:
                    try:
                        entity_state = self._get_entity_state(entity_id)
                        if entity_state:
                            # Add available services for this entity
                            entity_state["available_services"] = self._get_entity_services(
                                entity_id
                            )
                            entities.append(entity_state)
                    except Exception as err:
                        _LOGGER.warning("Failed to get state for %s: %s", entity_id, err)

                if entities:
                    entity_context = json.dumps(
                        {"entities": entities, "count": len(entities)}, indent=2, default=str
                    )

            if entity_context:
                return entity_context
            return "No relevant context found."

        except EmbeddingTimeoutError:
            # Timeout during embedding - fall back to direct mode
            return await self._fallback_to_direct(user_input)
        except ContextInjectionError:
            # Vector DB or embedding failure - fall back to direct mode
            return await self._fallback_to_direct(user_input)
        except Exception as err:
            # Unexpected error - fall back to direct mode
            _LOGGER.error("Vector DB context retrieval failed: %s", err, exc_info=True)
            return await self._fallback_to_direct(user_input)

    def _get_fallback_provider(self) -> DirectContextProvider:
        """Lazy-initialize fallback direct context provider."""
        if self._fallback_provider is None:
            self._fallback_provider = DirectContextProvider(self.hass, {"entities": []})
        return self._fallback_provider

    async def _fallback_to_direct(self, user_input: str) -> str:
        """Fall back to direct context when vector DB fails."""
        _LOGGER.warning("Falling back to direct context provider")
        fallback = self._get_fallback_provider()
        context = await fallback.get_context(user_input)
        return f"[Fallback mode - Vector DB unavailable]\n{context}" if context else ""

    async def _ensure_initialized(self) -> None:
        """Ensure ChromaDB client and collection are initialized."""
        await self._ensure_client()

        if self._collection is None:
            try:
                # Collection operations should also be in executor as they may do I/O
                from functools import partial

                assert self._client is not None  # Type narrowing for mypy
                get_collection = partial(
                    self._client.get_or_create_collection,
                    name=self.collection_name,
                    metadata={"description": "Home Assistant entity embeddings"},
                )
                self._collection = await self.hass.async_add_executor_job(get_collection)
                _LOGGER.debug("ChromaDB collection ready")
            except Exception as err:
                raise ContextInjectionError(f"Failed to access collection: {err}") from err

    async def _query_vector_db(self, embedding: list[float], top_k: int) -> list[dict[str, Any]]:
        """Query ChromaDB with embedding vector."""
        if self._collection is None:
            raise ContextInjectionError("Collection not initialized")

        try:
            # Type narrowing assertion for mypy
            assert self._collection is not None
            collection = self._collection

            # Cast to list[Sequence[float]] to satisfy chromadb's type signature
            query_embeddings = cast(list[Sequence[float]], [embedding])

            results = await self.hass.async_add_executor_job(
                lambda: collection.query(
                    query_embeddings=query_embeddings,
                    n_results=top_k,
                )
            )

            parsed_results: list[dict[str, Any]] = []
            if results and "ids" in results and results["ids"]:
                ids_list = results["ids"]
                if ids_list and len(ids_list) > 0:
                    ids = ids_list[0]
                    distances_list: Any = results.get("distances", [[]])
                    distances = (
                        distances_list[0] if distances_list and len(distances_list) > 0 else []
                    )

                    for i, entity_id in enumerate(ids):
                        parsed_results.append(
                            {
                                "entity_id": entity_id,
                                "distance": distances[i] if i < len(distances) else 0,
                            }
                        )

            # Fire event for vector DB query
            if self._emit_events:
                try:
                    self.hass.bus.async_fire(
                        EVENT_VECTOR_DB_QUERIED,
                        {
                            "collection": self.collection_name,
                            "results_count": len(parsed_results),
                            "top_k": top_k,
                            "entity_ids": [r["entity_id"] for r in parsed_results],
                        },
                    )
                except Exception as err:
                    _LOGGER.warning("Failed to fire vector DB query event: %s", err)

            return parsed_results

        except Exception as err:
            raise ContextInjectionError(f"Vector DB query failed: {err}") from err
