"""Retrieval context provider for Pepa Sensory Arm.

This module provides the RetrievalContextProvider class: a generic retrieval
pipe over the configured "additional collections" in ChromaDB. It was
extracted from VectorDBContextProvider's tier-2 path and serves both prompt
modes — in default prompt mode it feeds the Retrieved Context section of the
prompt TAIL alongside memories; in replacement mode it is appended to the
entity/memory merge.

Degraded = empty, never raise: on any failure it logs a warning and returns
an empty string.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from homeassistant.core import HomeAssistant

from ..const import (
    CONF_ADDITIONAL_COLLECTIONS,
    CONF_ADDITIONAL_L2_DISTANCE_THRESHOLD,
    CONF_ADDITIONAL_TOP_K,
    DEFAULT_ADDITIONAL_COLLECTIONS,
    DEFAULT_ADDITIONAL_L2_DISTANCE_THRESHOLD,
    DEFAULT_ADDITIONAL_TOP_K,
)
from ._vector_common import CHROMADB_AVAILABLE, VectorClientMixin
from .base import ContextProvider

_LOGGER = logging.getLogger(__name__)

ADDITIONAL_CONTEXT_BANNER = (
    "### RELEVANT ADDITIONAL CONTEXT FOR ANSWERING QUESTIONS, NOT CONTROL ###"
)


class RetrievalContextProvider(VectorClientMixin, ContextProvider):
    """Context provider querying the configured additional ChromaDB collections."""

    def __init__(self, hass: HomeAssistant, config: dict[str, Any]) -> None:
        """Initialize the retrieval context provider."""
        super().__init__(hass, config)

        self.additional_collections = config.get(
            CONF_ADDITIONAL_COLLECTIONS, DEFAULT_ADDITIONAL_COLLECTIONS
        )
        self.additional_top_k = config.get(CONF_ADDITIONAL_TOP_K, DEFAULT_ADDITIONAL_TOP_K)
        self.additional_threshold = config.get(
            CONF_ADDITIONAL_L2_DISTANCE_THRESHOLD, DEFAULT_ADDITIONAL_L2_DISTANCE_THRESHOLD
        )

        self._init_vector_common(hass, config)

        if self.additional_collections:
            _LOGGER.info(
                "Retrieval provider initialized (host=%s:%s, collections=%s)",
                self.host,
                self.port,
                self.additional_collections,
            )

    async def async_shutdown(self) -> None:
        """Clean up resources."""
        await self._shutdown_vector_common()
        self._client = None

    async def get_context(self, user_input: str) -> str:
        """Get supplementary context from the additional collections.

        Returns an empty string when no additional collections are configured,
        when there are no results, or on any failure.
        """
        if not self.additional_collections or not isinstance(self.additional_collections, list):
            return ""

        if not CHROMADB_AVAILABLE:
            _LOGGER.warning("ChromaDB not installed; skipping additional-collections retrieval")
            return ""

        try:
            await self._ensure_client()
            query_embedding = await self._embed_query(user_input)
            additional_results = await self._query_additional_collections(query_embedding)
        except Exception as err:
            _LOGGER.warning("Additional-collections retrieval failed: %s", err)
            return ""

        if not additional_results:
            return ""

        additional_context = json.dumps(
            {
                "additional_context": additional_results,
                "count": len(additional_results),
            },
            indent=2,
            default=str,
        )
        return f"{ADDITIONAL_CONTEXT_BANNER}\n{additional_context}"

    async def _query_additional_collections(
        self, query_embedding: list[float]
    ) -> list[dict[str, Any]]:
        """Query additional collections and return merged, ranked results.

        Args:
            query_embedding: The embedding vector to query with

        Returns:
            List of merged results from all additional collections, sorted by distance
        """
        if not self.additional_collections:
            return []

        if self._client is None:
            _LOGGER.warning("ChromaDB client not initialized, cannot query additional collections")
            return []

        all_results = []

        # Query each additional collection
        for collection_name in self.additional_collections:
            try:
                # Try to get the collection
                collection = await self.hass.async_add_executor_job(
                    self._client.get_collection,
                    collection_name,
                )

                # Query the collection with extra results for merging
                results = await self.hass.async_add_executor_job(
                    lambda col=collection: col.query(
                        query_embeddings=[query_embedding],
                        n_results=self.additional_top_k * len(self.additional_collections),
                        include=["documents", "metadatas", "distances"],
                    )
                )

                # Parse and add results with collection name
                if results and "ids" in results and results["ids"]:
                    ids = results["ids"][0]
                    distances = results.get("distances", [[]])[0]
                    documents = results.get("documents", [[]])[0]
                    metadatas = results.get("metadatas", [[]])[0]

                    for i in range(len(ids)):
                        result = {
                            "id": ids[i],
                            "distance": distances[i] if i < len(distances) else float("inf"),
                            "document": documents[i] if i < len(documents) else "",
                            "metadata": metadatas[i] if i < len(metadatas) else {},
                            "collection": collection_name,
                        }
                        all_results.append(result)

            except Exception as err:
                # Log warning but continue with other collections
                _LOGGER.warning(
                    "Collection '%s' not found or inaccessible, skipping. Error: %s",
                    collection_name,
                    str(err),
                )
                continue

        if not all_results:
            return []

        # Sort by distance (ascending - lower is better)
        all_results.sort(key=lambda x: x.get("distance", float("inf")))

        # Filter by threshold
        filtered_results = [
            r for r in all_results if r.get("distance", float("inf")) <= self.additional_threshold
        ]

        # Take top K from merged pool
        top_results = filtered_results[: self.additional_top_k]

        return top_results
