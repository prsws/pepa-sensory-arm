"""Vector database manager for entity embeddings.

This module handles indexing Home Assistant entities into ChromaDB
for semantic search capabilities in the Pepa Sensory Arm integration.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any, Callable, Sequence, cast

from homeassistant.components import conversation as ha_conversation
from homeassistant.components.homeassistant.exposed_entities import async_should_expose
from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_time_interval

if TYPE_CHECKING:
    from chromadb.api import ClientAPI
    from chromadb.api.models.Collection import Collection

from .chroma_factory import ChromaClientFactory
from .const import (
    CONF_VECTOR_DB_COLLECTION,
    CONF_VECTOR_DB_HOST,
    CONF_VECTOR_DB_PORT,
    DEFAULT_VECTOR_DB_COLLECTION,
    DEFAULT_VECTOR_DB_HOST,
    DEFAULT_VECTOR_DB_PORT,
)
from .embedder import CACHE_NS_ENTITY
from .exceptions import ContextInjectionError

# Conditional import for ChromaDB. Imported only to detect availability -- the
# client is constructed by ChromaClientFactory, not here.
try:
    import chromadb  # noqa: F401

    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False

_LOGGER = logging.getLogger(__name__)

# How often to run background cleanup and maintenance
MAINTENANCE_INTERVAL = timedelta(hours=1)

# Maximum batch size for indexing
MAX_BATCH_SIZE = 50

# Debounce delay for state change reindexing (seconds)
REINDEX_DEBOUNCE_DELAY = 2.0

# Maximum concurrent reindex operations
MAX_CONCURRENT_REINDEX = 3


class VectorDBManager:
    """Manages entity embeddings in ChromaDB."""

    def __init__(
        self,
        hass: HomeAssistant,
        config: dict[str, Any],
        chroma_factory: ChromaClientFactory,
    ) -> None:
        """Initialize the Vector DB manager.

        Args:
            hass: Home Assistant instance
            config: Configuration dictionary
            chroma_factory: The entry's client factory. The only source of
                ChromaDB clients -- this manager no longer constructs its own,
                which is what stops MemoryManager from having to borrow one.
        """
        if not CHROMADB_AVAILABLE:
            raise ContextInjectionError(
                "ChromaDB not installed. Install with: pip install chromadb"
            )

        self.hass = hass
        self.config = config
        self.chroma_factory = chroma_factory

        # ChromaDB configuration
        self.host = config.get(CONF_VECTOR_DB_HOST, DEFAULT_VECTOR_DB_HOST)
        self.port = config.get(CONF_VECTOR_DB_PORT, DEFAULT_VECTOR_DB_PORT)
        self.collection_name = config.get(CONF_VECTOR_DB_COLLECTION, DEFAULT_VECTOR_DB_COLLECTION)

        # Embedding configuration, generation, and cache all live in the shared
        # Embedder, reached through the factory.

        # State
        self._client: ClientAPI | None = None
        self._collection: Collection | None = None
        self._indexing_lock = asyncio.Lock()
        self._state_listener: Callable[[], None] | None = None
        self._maintenance_listener: Callable[[], None] | None = None

        # Background task management for state change reindexing
        self._pending_reindex: dict[str, float] = {}
        self._reindex_task: asyncio.Task[None] | None = None
        self._reindex_semaphore = asyncio.Semaphore(MAX_CONCURRENT_REINDEX)
        self._initial_index_task: asyncio.Task[dict[str, Any]] | None = None

        _LOGGER.info(
            "Vector DB Manager initialized (host=%s:%s, collection=%s)",
            self.host,
            self.port,
            self.collection_name,
        )

    async def async_setup(self) -> None:
        """Set up the vector DB manager.

        Initializes ChromaDB connection and performs initial entity indexing.
        """
        try:
            await self._ensure_initialized()

            # Schedule initial indexing as a background task so it doesn't
            # block config entry setup (HA cancels setup after 60s timeout)
            _LOGGER.info("Scheduling initial entity indexing in background...")
            self._initial_index_task = self.hass.async_create_background_task(
                self.async_reindex_all_entities(),
                "pepa_sensory_arm_initial_entity_indexing",
            )

            # Set up state change listener for incremental updates
            # Listen directly to state_changed events
            self._state_listener = self.hass.bus.async_listen(
                EVENT_STATE_CHANGED, self._async_handle_state_change
            )

            # Set up periodic maintenance
            self._maintenance_listener = async_track_time_interval(
                self.hass, self._async_run_maintenance, MAINTENANCE_INTERVAL
            )

            _LOGGER.info("Vector DB Manager setup complete")

        except Exception as err:
            _LOGGER.error("Failed to set up Vector DB Manager: %s", err, exc_info=True)
            raise

    async def async_shutdown(self) -> None:
        """Shut down the vector DB manager.

        Cleans up listeners, connections, and background tasks.
        """
        if self._state_listener:
            self._state_listener()
            self._state_listener = None

        if self._maintenance_listener:
            self._maintenance_listener()
            self._maintenance_listener = None

        # Cancel initial index task if still running
        if self._initial_index_task and not self._initial_index_task.done():
            self._initial_index_task.cancel()
            try:
                await self._initial_index_task
            except asyncio.CancelledError:
                pass

        # Cancel and await pending reindex task
        if self._reindex_task and not self._reindex_task.done():
            self._reindex_task.cancel()
            try:
                await self._reindex_task
            except asyncio.CancelledError:
                pass
        self._pending_reindex.clear()

        # Clear only this manager's cache namespace. The embedder is shared with
        # MemoryManager, so clearing everything -- or closing the embedder's HTTP
        # clients, which this used to do -- would break the other manager. The
        # embedder is closed by the factory, once, at unload.
        self.chroma_factory.clear_cache(CACHE_NS_ENTITY)

        _LOGGER.info("Vector DB Manager shut down")

    async def async_reindex_all_entities(self) -> dict[str, Any]:
        """Reindex all Home Assistant entities.

        Returns:
            Dictionary with indexing statistics
        """
        async with self._indexing_lock:
            try:
                all_states = self.hass.states.async_all()
                total = len(all_states)

                _LOGGER.info("Starting full reindex of %d entities", total)

                indexed = 0
                failed = 0
                skipped = 0

                # Process in batches
                for i in range(0, total, MAX_BATCH_SIZE):
                    batch = all_states[i : i + MAX_BATCH_SIZE]

                    for state in batch:
                        try:
                            # Skip entities that shouldn't be indexed
                            if self._should_skip_entity(state.entity_id):
                                skipped += 1
                                continue

                            await self.async_index_entity(state.entity_id)
                            indexed += 1

                        except Exception as err:
                            _LOGGER.warning(
                                "Failed to index entity %s: %s",
                                state.entity_id,
                                err,
                            )
                            failed += 1

                    # Allow other tasks to run
                    await asyncio.sleep(0)

                _LOGGER.info(
                    "Reindex complete: %d indexed, %d failed, %d skipped",
                    indexed,
                    failed,
                    skipped,
                )

                return {
                    "total": total,
                    "indexed": indexed,
                    "failed": failed,
                    "skipped": skipped,
                }

            except Exception as err:
                _LOGGER.error("Full reindex failed: %s", err, exc_info=True)
                raise

    async def async_index_entity(self, entity_id: str) -> None:
        """Index a single entity into ChromaDB.

        Args:
            entity_id: The entity ID to index
        """
        try:
            await self._ensure_initialized()

            # Skip entities that shouldn't be indexed
            if self._should_skip_entity(entity_id):
                _LOGGER.debug("Skipping non-exposed entity: %s", entity_id)
                return

            # Get entity state
            state = self.hass.states.get(entity_id)
            if state is None:
                _LOGGER.warning("Entity not found for indexing: %s", entity_id)
                return

            # Create text representation for embedding
            text = self._create_entity_text(state)

            # Generate embedding (pass entity_id for cache eviction)
            embedding = await self._embed_text(text, entity_id=entity_id)

            # Store in ChromaDB
            metadata = {
                "entity_id": entity_id,
                "domain": entity_id.split(".")[0],
                "state": state.state,
                "friendly_name": state.attributes.get("friendly_name", entity_id),
            }

            # Add to collection
            # Type narrowing assertion for mypy
            assert self._collection is not None
            collection = self._collection
            # Cast to list[Sequence[float]] to satisfy chromadb's type signature
            embeddings = cast(list[Sequence[float]], [embedding])
            await self.hass.async_add_executor_job(
                lambda: collection.upsert(
                    ids=[entity_id],
                    embeddings=embeddings,
                    metadatas=[metadata],
                    documents=[text],
                )
            )

            _LOGGER.debug("Indexed entity: %s", entity_id)

        except Exception as err:
            _LOGGER.error(
                "Failed to index entity %s: %s",
                entity_id,
                err,
                exc_info=True,
            )
            raise

    async def async_remove_entity(self, entity_id: str) -> None:
        """Remove an entity from ChromaDB.

        Args:
            entity_id: The entity ID to remove
        """
        try:
            await self._ensure_initialized()

            # Type narrowing assertion for mypy
            assert self._collection is not None
            collection = self._collection
            await self.hass.async_add_executor_job(lambda: collection.delete(ids=[entity_id]))

            # Clean up embedding cache entry for this entity
            self.chroma_factory.evict_entity(entity_id)

            _LOGGER.debug("Removed entity from index: %s", entity_id)

        except Exception as err:
            _LOGGER.error(
                "Failed to remove entity %s: %s",
                entity_id,
                err,
            )

    async def async_collection_exists(self, collection_name: str) -> bool:
        """Check if a collection exists in ChromaDB.

        Args:
            collection_name: Name of the collection to check

        Returns:
            True if collection exists, False otherwise
        """
        try:
            await self._ensure_initialized()
            if self._client is None:
                return False
            await self.hass.async_add_executor_job(
                self._client.get_collection,
                collection_name,
            )
            return True
        except Exception:
            return False

    @callback
    def _async_handle_state_change(self, event: Event[Any]) -> None:
        """Handle entity state changes for incremental indexing.

        Records the entity for debounced batch reindexing instead of
        spawning an unbounded task per state change.

        Args:
            event: State change event
        """
        entity_id = event.data.get("entity_id")

        if not entity_id or self._should_skip_entity(entity_id):
            return

        # Skip reindex if state and attributes haven't changed
        old_state = event.data.get("old_state")
        new_state = event.data.get("new_state")
        if (
            old_state is not None
            and new_state is not None
            and old_state.state == new_state.state
            and old_state.attributes == new_state.attributes
        ):
            return

        # Record pending reindex (deduplicates rapid changes for same entity)
        self._pending_reindex[entity_id] = asyncio.get_event_loop().time()

        # Schedule debounced batch reindex if not already scheduled
        if self._reindex_task is None or self._reindex_task.done():
            self._reindex_task = asyncio.create_task(self._async_debounced_reindex())

    async def _async_debounced_reindex(self) -> None:
        """Process pending reindex requests after debounce delay."""
        await asyncio.sleep(REINDEX_DEBOUNCE_DELAY)

        # Swap out pending set atomically
        pending = self._pending_reindex
        self._pending_reindex = {}

        if not pending:
            return

        _LOGGER.debug("Processing %d debounced entity reindex requests", len(pending))

        async def _reindex_one(entity_id: str) -> None:
            async with self._reindex_semaphore:
                try:
                    await self.async_index_entity(entity_id)
                except Exception as err:
                    _LOGGER.debug(
                        "Failed to reindex entity %s after state change: %s",
                        entity_id,
                        err,
                    )

        await asyncio.gather(
            *[_reindex_one(eid) for eid in pending],
            return_exceptions=True,
        )

    async def _async_run_maintenance(self, _: Any) -> None:
        """Run periodic maintenance tasks.

        Removes embeddings for entities that no longer exist.
        """
        try:
            _LOGGER.debug("Running vector DB maintenance")

            # Get all indexed entity IDs
            # Type narrowing assertion for mypy
            assert self._collection is not None
            collection = self._collection
            result = await self.hass.async_add_executor_job(lambda: collection.get())

            if not result or "ids" not in result:
                return

            indexed_ids = set(result["ids"])
            current_ids = set(self.hass.states.async_entity_ids())

            # Find stale entries
            stale_ids = indexed_ids - current_ids

            if stale_ids:
                _LOGGER.info("Removing %d stale entity embeddings", len(stale_ids))
                for entity_id in stale_ids:
                    await self.async_remove_entity(entity_id)

        except Exception as err:
            _LOGGER.warning("Maintenance task failed: %s", err)

    def _should_skip_entity(self, entity_id: str) -> bool:
        """Determine if an entity should be skipped during indexing.

        Args:
            entity_id: The entity ID to check

        Returns:
            True if entity should be skipped
        """
        # Skip internal entities
        if entity_id.startswith("group.all_"):
            return True

        # Skip sun entity (no meaningful state for embedding)
        if entity_id == "sun.sun":
            return True

        # Skip persistent notification entities
        if entity_id.startswith("persistent_notification."):
            return True

        # Skip entities that are not exposed to conversation/voice assistant
        # This ensures we only index entities the user has explicitly exposed
        if not async_should_expose(self.hass, ha_conversation.DOMAIN, entity_id):
            return True

        return False

    def _create_entity_text(self, state: State) -> str:
        """Create text representation of entity for embedding.

        Args:
            state: Entity state object

        Returns:
            Text representation suitable for embedding
        """
        entity_id = state.entity_id
        domain = entity_id.split(".")[0]
        friendly_name = state.attributes.get("friendly_name", entity_id)

        # Start with entity identification
        parts = [
            f"Entity: {friendly_name} ({entity_id})",
            f"Type: {domain}",
            f"Current state: {state.state}",
        ]

        # Add relevant attributes based on domain
        if domain == "sensor":
            unit = state.attributes.get("unit_of_measurement")
            if unit:
                parts.append(f"Unit: {unit}")

            device_class = state.attributes.get("device_class")
            if device_class:
                parts.append(f"Measures: {device_class}")

        elif domain in ("light", "switch", "fan"):
            parts.append(f"Can be turned {state.state}")

        elif domain == "climate":
            temp = state.attributes.get("current_temperature")
            if temp:
                parts.append(f"Temperature: {temp}")

            mode = state.attributes.get("hvac_mode")
            if mode:
                parts.append(f"Mode: {mode}")

        elif domain == "cover":
            position = state.attributes.get("current_position")
            if position is not None:
                parts.append(f"Position: {position}%")

        elif domain == "media_player":
            source = state.attributes.get("source")
            if source:
                parts.append(f"Source: {source}")

        # Add location information if available
        entity_registry = er.async_get(self.hass)
        area_registry = ar.async_get(self.hass)
        device_registry = dr.async_get(self.hass)
        try:
            if entity_entry := entity_registry.async_get(entity_id):
                area_id = entity_entry.area_id
                if not area_id and entity_entry.device_id:
                    device_entry = device_registry.async_get(entity_entry.device_id)
                    if device_entry:
                        area_id = device_entry.area_id
                if area_id:
                    if area := area_registry.async_get_area(area_id):
                        parts.append(f"Location: {area.name}")
                if entity_entry.aliases:
                    clean_aliases = [a for a in entity_entry.aliases if isinstance(a, str)]
                    if clean_aliases:
                        parts.append(f"Aliases: {', '.join(clean_aliases)}")
        except Exception:
            _LOGGER.debug("Could not determine area for entity: %s", entity_id)

        return " | ".join(parts)

    async def _ensure_initialized(self) -> None:
        """Ensure ChromaDB client and collection are initialized."""
        if self._client is None:
            # Client construction, placement, retry, and availability tracking all
            # live in the factory now. This manager just asks for a client.
            self._client = await self.chroma_factory.get_client()

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

    async def _embed_text(self, text: str, entity_id: str | None = None) -> list[float]:
        """Embed text via the shared embedder.

        Deprecated: kept for one release so existing callers and tests keep
        working. New code should use ``chroma_factory.embed_text()`` directly.
        Entity embeds belong to the entity cache namespace, which is this
        method's default.

        Args:
            text: Text to embed
            entity_id: Optional entity ID to enable per-entity cache eviction.

        Returns:
            Embedding vector
        """
        return await self.chroma_factory.embed_text(text, entity_id=entity_id)
