"""ChromaDB client factory.

The single place a ChromaDB client is constructed. Both ``VectorDBManager`` and
``MemoryManager`` consume clients from here, which is what kills the
borrowed-client bug class: memory's vector capability stops being parasitic on
whether the entity-context Context Mode happens to be set to ``vector_db``.

One factory, one client policy, one availability truth.

Placement:
    ``remote`` -- ``chromadb.HttpClient`` against a ChromaDB server. Today's only
    behavior, and the current default.
    ``embedded`` -- ``chromadb.PersistentClient`` in-VM, no external service.

    Placement is configuration, never a heuristic. The factory does not sniff the
    environment and autoswitch: a memory system that silently relocates its store
    based on runtime conditions is a memory system nobody can reason about.

Memory-VM constraint:
    The HAOS VM is frozen at 4 GB (Design Ledger §3) -- every VM byte is taken
    from an already-thrashing Metal pool on the host. Embedded placement is
    implemented but default-off pending the P6 in-VM benchmark; see
    ``DEFAULT_CHROMA_PLACEMENT`` in const.py for why that gate exists.

Embedding:
    The factory holds an ``Embedder`` and exposes it, so that both managers embed
    through one object with one cache. The embedding stack itself lives in
    embedder.py -- generation, providers, and HTTP client lifecycles are not the
    factory's business, they are just reached through it.
"""

from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import TYPE_CHECKING, Any, Callable

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_track_time_interval

if TYPE_CHECKING:
    from chromadb.api import ClientAPI

from .const import (
    CHROMA_AVAILABILITY_TTL,
    CHROMA_PLACEMENT_EMBEDDED,
    CHROMA_PLACEMENT_REMOTE,
    CONF_CHROMA_PERSIST_DIR,
    CONF_CHROMA_PLACEMENT,
    CONF_VECTOR_DB_HOST,
    CONF_VECTOR_DB_PORT,
    DEFAULT_CHROMA_PERSIST_DIR,
    DEFAULT_CHROMA_PLACEMENT,
    DEFAULT_RETRY_BACKOFF_FACTOR,
    DEFAULT_RETRY_INITIAL_DELAY,
    DEFAULT_RETRY_JITTER,
    DEFAULT_RETRY_MAX_ATTEMPTS,
    DEFAULT_RETRY_MAX_DELAY,
    DEFAULT_VECTOR_DB_HOST,
    DEFAULT_VECTOR_DB_PORT,
    DOMAIN,
)
from .embedder import CACHE_NS_ENTITY, CacheNamespace, Embedder
from .exceptions import ContextInjectionError
from .helpers import check_chromadb_health, retry_async

try:
    import chromadb

    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False

_LOGGER = logging.getLogger(__name__)

# Repair issue raised when embedded placement cannot start. Embedded failure is
# loud by design (Design Ledger §2.2): the user sees a repair, not a silently
# degraded memory system.
ISSUE_CHROMA_EMBEDDED_FAILED = "chroma_embedded_failed"


class ChromaClientFactory:
    """Constructs and owns ChromaDB clients for one config entry.

    Constructed once per config entry in ``__init__.py`` whenever *either* the
    Context Mode is ``vector_db`` *or* memory is enabled -- the two are
    independent, which is the point.
    """

    def __init__(self, hass: HomeAssistant, config: dict[str, Any]) -> None:
        """Initialize the factory.

        Args:
            hass: Home Assistant instance.
            config: Configuration dictionary for this entry.
        """
        self.hass = hass
        self.config = config

        self._placement: str = config.get(CONF_CHROMA_PLACEMENT, DEFAULT_CHROMA_PLACEMENT)
        self.host: str = config.get(CONF_VECTOR_DB_HOST, DEFAULT_VECTOR_DB_HOST)
        self.port: int = config.get(CONF_VECTOR_DB_PORT, DEFAULT_VECTOR_DB_PORT)
        self.persist_dir: str = config.get(CONF_CHROMA_PERSIST_DIR, DEFAULT_CHROMA_PERSIST_DIR)

        self._embedder = Embedder(hass, config)
        self._client: ClientAPI | None = None

        # Bounded-staleness availability. Starts False: nothing has been reached
        # yet, and claiming otherwise would be the exact init-time-state-as-live-
        # state lie this contract exists to prevent.
        self._available: bool = False
        self._availability_checked_at: float = 0.0
        self._probe_listener: Callable[[], None] | None = None

    @property
    def placement(self) -> str:
        """The active placement. May differ from configuration after fallback."""
        return self._placement

    @property
    def embedder(self) -> Embedder:
        """The shared embedder. Exposed for cache maintenance by its owner."""
        return self._embedder

    async def embed_text(
        self,
        text: str,
        entity_id: str | None = None,
        namespace: CacheNamespace = CACHE_NS_ENTITY,
    ) -> list[float]:
        """Embed text through the shared embedder.

        The single embedding surface for both managers -- this is what ends
        MemoryManager reaching into VectorDBManager._embed_text.

        Args:
            text: Text to embed.
            entity_id: Enables per-entity cache eviction (entity namespace only).
            namespace: Which cache namespace this call belongs to.

        Returns:
            Embedding vector.
        """
        return await self._embedder.embed_text(text, entity_id=entity_id, namespace=namespace)

    def evict_entity(self, entity_id: str) -> None:
        """Drop an entity's cached embedding when it leaves the index."""
        self._embedder.evict_entity(entity_id)

    def clear_cache(self, namespace: CacheNamespace | None = None) -> None:
        """Clear an embedding cache namespace.

        Callers clear only their own namespace. The factory is shared between the
        managers, so clearing everything would evict the other one's entries --
        the cache-level shape of the same bug the factory exists to kill.
        """
        self._embedder.clear_cache(namespace)

    @property
    def available(self) -> bool:
        """Whether ChromaDB was reachable recently.

        Bounded staleness, not live truth: this is "succeeded on the last
        operation, or was probed within CHROMA_AVAILABILITY_TTL seconds". A sync
        property cannot do network I/O, and pretending otherwise would be the
        silent degradation the contract forbids. See
        ``MemoryCapabilities.vector_recall``.

        Embedded placement, once initialized, is genuinely static -- there is no
        network to lose -- so the flag stays True without probing.
        """
        return self._available

    def _mark_available(self) -> None:
        """Record a successful client operation."""
        self._available = True
        self._availability_checked_at = time.monotonic()

    def _mark_unavailable(self) -> None:
        """Record a connection-class failure."""
        self._available = False
        self._availability_checked_at = time.monotonic()

    async def async_setup(self) -> None:
        """Start the availability probe.

        Only remote placement is probed. An embedded PersistentClient has no
        network to lose, so its availability is genuinely static once
        initialized and a periodic probe would burn wakeups to learn nothing.
        """
        if self._placement == CHROMA_PLACEMENT_REMOTE:
            self._probe_listener = async_track_time_interval(
                self.hass,
                self._async_probe,
                timedelta(seconds=CHROMA_AVAILABILITY_TTL),
            )

    @callback
    async def _async_probe(self, now: Any) -> None:
        """Refresh the availability flag on the TTL.

        This is the (b) half of the bounded-staleness contract: real client
        operations keep the flag fresh while traffic flows, and this probe bounds
        how stale it can get when traffic stops.
        """
        await self.health_check()

    async def get_client(self) -> ClientAPI:
        """Return the ChromaDB client, constructing it on first use.

        Returns:
            The ChromaDB client for the active placement.

        Raises:
            ContextInjectionError: If no client can be constructed.
        """
        if self._client is not None:
            return self._client

        if not CHROMADB_AVAILABLE:
            self._mark_unavailable()
            raise ContextInjectionError(
                "ChromaDB not installed. Install with: pip install chromadb"
            )

        if self._placement == CHROMA_PLACEMENT_EMBEDDED:
            self._client = await self._create_embedded_client()
        else:
            self._client = await self._create_remote_client()

        self._mark_available()
        return self._client

    async def _create_embedded_client(self) -> ClientAPI:
        """Create a PersistentClient, falling back loudly if it cannot start.

        Embedded import or init failure lands loudly (Design Ledger §2.2): log an
        error, raise a repair issue, then fall back to remote *only if* host/port
        are configured. Otherwise the failure propagates and the caller runs
        store-only with vector_recall False -- degraded, but never silently.

        Returns:
            A PersistentClient, or a remote client if fallback applied.

        Raises:
            ContextInjectionError: If embedded fails and no fallback is available.
        """
        from functools import partial

        path = self.hass.config.path(self.persist_dir)

        try:
            # PersistentClient does file I/O and SQLite setup during init.
            create = partial(chromadb.PersistentClient, path=path)
            client: ClientAPI = await self.hass.async_add_executor_job(create)
            _LOGGER.info("ChromaDB embedded client ready at %s", path)
            return client
        except Exception as err:
            _LOGGER.error(
                "ChromaDB embedded placement failed at %s: %s. "
                "Memory and vector search will not use an embedded store.",
                path,
                err,
            )
            self._raise_repair_issue(str(err))

            if self._can_fall_back_to_remote():
                _LOGGER.warning(
                    "Falling back to remote ChromaDB at %s:%s after embedded failure",
                    self.host,
                    self.port,
                )
                self._placement = CHROMA_PLACEMENT_REMOTE
                return await self._create_remote_client()

            self._mark_unavailable()
            raise ContextInjectionError(
                f"ChromaDB embedded placement failed at {path} and no remote "
                f"host/port is configured to fall back to: {err}"
            ) from err

    def _can_fall_back_to_remote(self) -> bool:
        """Whether a remote host/port is configured to fall back to."""
        return bool(self.config.get(CONF_VECTOR_DB_HOST)) and bool(
            self.config.get(CONF_VECTOR_DB_PORT)
        )

    def _raise_repair_issue(self, error: str) -> None:
        """Surface embedded failure to the user as a repair issue."""
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            ISSUE_CHROMA_EMBEDDED_FAILED,
            is_fixable=False,
            severity=ir.IssueSeverity.ERROR,
            translation_key=ISSUE_CHROMA_EMBEDDED_FAILED,
            translation_placeholders={
                "path": self.hass.config.path(self.persist_dir),
                "error": error,
            },
        )

    async def _create_remote_client(self) -> ClientAPI:
        """Create an HttpClient against the configured ChromaDB server.

        Lifted unchanged from VectorDBManager._ensure_initialized: HttpClient does
        SSL setup and file I/O during init, so it is constructed in an executor,
        wrapped in the shared retry policy.

        Returns:
            An HttpClient.

        Raises:
            ContextInjectionError: If the client cannot be constructed.
        """
        from functools import partial

        async def create_client_func() -> ClientAPI:
            """Create ChromaDB client."""
            create_client = partial(
                chromadb.HttpClient,
                host=self.host,
                port=self.port,
            )
            client: ClientAPI = await self.hass.async_add_executor_job(create_client)
            return client

        try:
            client: ClientAPI = await retry_async(
                create_client_func,
                max_retries=DEFAULT_RETRY_MAX_ATTEMPTS,
                retryable_exceptions=(Exception,),
                initial_delay=DEFAULT_RETRY_INITIAL_DELAY,
                backoff_factor=DEFAULT_RETRY_BACKOFF_FACTOR,
                max_delay=DEFAULT_RETRY_MAX_DELAY,
                jitter=DEFAULT_RETRY_JITTER,
            )
        except Exception as err:
            self._mark_unavailable()
            raise ContextInjectionError(f"Failed to connect to ChromaDB: {err}") from err

        _LOGGER.debug("ChromaDB client connected to %s:%s", self.host, self.port)
        return client

    async def health_check(self) -> tuple[bool, str]:
        """Check ChromaDB health for the active placement.

        Placement-aware, which the previous unconditional host/port probe was not:
        probing a TCP port says nothing about an embedded store, and reported
        failure for users who never ran a server.

        Remote: probe the server's heartbeat.
        Embedded: verify the library imports and the persist dir is writable.

        Returns:
            (is_healthy, message)
        """
        if self._placement == CHROMA_PLACEMENT_EMBEDDED:
            healthy, message = await self._health_check_embedded()
        else:
            healthy, message = await check_chromadb_health(self.host, self.port)

        if healthy:
            self._mark_available()
        else:
            self._mark_unavailable()
        return healthy, message

    async def _health_check_embedded(self) -> tuple[bool, str]:
        """Verify embedded placement can work: import plus a writable persist dir.

        Returns:
            (is_healthy, message)
        """
        if not CHROMADB_AVAILABLE:
            return False, "ChromaDB library not installed"

        path = self.hass.config.path(self.persist_dir)

        def _check_writable() -> tuple[bool, str]:
            import os

            try:
                os.makedirs(path, exist_ok=True)
            except OSError as err:
                return False, f"Persist directory {path} could not be created: {err}"
            if not os.access(path, os.W_OK):
                return False, f"Persist directory {path} is not writable"
            return True, f"ChromaDB embedded healthy (persist dir: {path})"

        result: tuple[bool, str] = await self.hass.async_add_executor_job(_check_writable)
        return result

    async def async_shutdown(self) -> None:
        """Stop the probe, close the embedder, and release the client.

        Owned here rather than by either manager: the factory and its embedder are
        shared per config entry, so a manager closing either would tear it out
        from under the other one. Called from __init__.py's unload, after both
        managers stop.
        """
        if self._probe_listener is not None:
            self._probe_listener()
            self._probe_listener = None

        await self._embedder.async_shutdown()

        self._client = None
        self._available = False
