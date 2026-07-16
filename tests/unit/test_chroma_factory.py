"""Unit tests for ChromaClientFactory.

The factory is the single place a ChromaDB client is constructed, and the single
source of availability truth. These tests cover placement selection, the loud
failure ladder for embedded placement, the bounded-staleness availability
contract, and the placement-aware health check.

The embedding cache and embed_text() arrive in P2 commit 2b; their tests come
with them.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.pepa_sensory_arm.chroma_factory import (
    ISSUE_CHROMA_EMBEDDED_FAILED,
    ChromaClientFactory,
)
from custom_components.pepa_sensory_arm.const import (
    CHROMA_PLACEMENT_EMBEDDED,
    CHROMA_PLACEMENT_REMOTE,
    CONF_CHROMA_PERSIST_DIR,
    CONF_CHROMA_PLACEMENT,
    CONF_VECTOR_DB_HOST,
    CONF_VECTOR_DB_PORT,
)
from custom_components.pepa_sensory_arm.exceptions import ContextInjectionError


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = MagicMock()
    hass.config = MagicMock()
    hass.config.path = MagicMock(side_effect=lambda d: f"/tmp/test_config/{d}")
    hass.async_add_executor_job = AsyncMock(
        side_effect=lambda func, *args, **kwargs: (
            func(*args, **kwargs) if args or kwargs else func()
        )
    )
    return hass


@pytest.fixture
def remote_config():
    """Config selecting remote placement."""
    return {
        CONF_CHROMA_PLACEMENT: CHROMA_PLACEMENT_REMOTE,
        CONF_VECTOR_DB_HOST: "localhost",
        CONF_VECTOR_DB_PORT: 8000,
    }


@pytest.fixture
def embedded_config():
    """Config selecting embedded placement, with a remote fallback available."""
    return {
        CONF_CHROMA_PLACEMENT: CHROMA_PLACEMENT_EMBEDDED,
        CONF_CHROMA_PERSIST_DIR: "pepa_chroma",
        CONF_VECTOR_DB_HOST: "localhost",
        CONF_VECTOR_DB_PORT: 8000,
    }


@pytest.fixture
def mock_chromadb():
    """Mock the chromadb module inside the factory."""
    with patch("custom_components.pepa_sensory_arm.chroma_factory.chromadb") as mock:
        mock.HttpClient = MagicMock(return_value=MagicMock(name="http_client"))
        mock.PersistentClient = MagicMock(return_value=MagicMock(name="persistent_client"))
        yield mock


@pytest.fixture(autouse=True)
def no_retry_delay():
    """Run retry_async's callable once, without backoff sleeps."""

    async def _call_once(func, **kwargs):
        return await func()

    with patch(
        "custom_components.pepa_sensory_arm.chroma_factory.retry_async",
        side_effect=_call_once,
    ):
        yield


@pytest.fixture(autouse=True)
def mock_issue_registry():
    """Capture repair issues instead of touching the real registry."""
    with patch("custom_components.pepa_sensory_arm.chroma_factory.ir") as mock_ir:
        yield mock_ir


# ---- Placement selection ------------------------------------------------


def test_placement_defaults_to_embedded(mock_hass):
    """With no placement configured, the factory is embedded.

    A fresh install should work with zero infrastructure (Ledger §2.2). Existing
    installs never reach this default -- async_migrate_entry pins them to remote
    explicitly, so an upgrade never relocates a running store.
    """
    factory = ChromaClientFactory(mock_hass, {})
    assert factory.placement == CHROMA_PLACEMENT_EMBEDDED


def test_placement_reads_config(mock_hass, embedded_config):
    """Placement comes from config, never from a heuristic."""
    factory = ChromaClientFactory(mock_hass, embedded_config)
    assert factory.placement == CHROMA_PLACEMENT_EMBEDDED


@pytest.mark.asyncio
async def test_remote_placement_builds_http_client(mock_hass, remote_config, mock_chromadb):
    """Remote placement constructs an HttpClient against the configured host."""
    factory = ChromaClientFactory(mock_hass, remote_config)

    client = await factory.get_client()

    mock_chromadb.HttpClient.assert_called_once_with(host="localhost", port=8000)
    assert client is mock_chromadb.HttpClient.return_value
    mock_chromadb.PersistentClient.assert_not_called()


@pytest.mark.asyncio
async def test_embedded_placement_builds_persistent_client(
    mock_hass, embedded_config, mock_chromadb
):
    """Embedded placement constructs a PersistentClient under the config dir."""
    factory = ChromaClientFactory(mock_hass, embedded_config)

    client = await factory.get_client()

    mock_chromadb.PersistentClient.assert_called_once_with(path="/tmp/test_config/pepa_chroma")
    assert client is mock_chromadb.PersistentClient.return_value
    mock_chromadb.HttpClient.assert_not_called()


@pytest.mark.asyncio
async def test_client_is_constructed_once(mock_hass, remote_config, mock_chromadb):
    """The client is cached: the factory is a factory, not a churn machine."""
    factory = ChromaClientFactory(mock_hass, remote_config)

    first = await factory.get_client()
    second = await factory.get_client()

    assert first is second
    mock_chromadb.HttpClient.assert_called_once()


# ---- Embedded failure ladder --------------------------------------------


@pytest.mark.asyncio
async def test_embedded_failure_raises_repair_issue_and_falls_back(
    mock_hass, embedded_config, mock_chromadb, mock_issue_registry
):
    """Embedded failure is loud: repair issue raised, then fall back to remote."""
    mock_chromadb.PersistentClient.side_effect = RuntimeError("disk on fire")

    factory = ChromaClientFactory(mock_hass, embedded_config)
    client = await factory.get_client()

    # Loud: the user sees a repair issue.
    mock_issue_registry.async_create_issue.assert_called_once()
    assert mock_issue_registry.async_create_issue.call_args.args[2] == ISSUE_CHROMA_EMBEDDED_FAILED

    # Fallen back, and honest about it.
    assert client is mock_chromadb.HttpClient.return_value
    assert factory.placement == CHROMA_PLACEMENT_REMOTE


@pytest.mark.asyncio
async def test_embedded_failure_without_remote_is_unavailable_not_silent(
    mock_hass, mock_chromadb, mock_issue_registry
):
    """With no remote to fall back to, embedded failure raises rather than degrading quietly."""
    config = {
        CONF_CHROMA_PLACEMENT: CHROMA_PLACEMENT_EMBEDDED,
        CONF_CHROMA_PERSIST_DIR: "pepa_chroma",
    }
    mock_chromadb.PersistentClient.side_effect = RuntimeError("disk on fire")

    factory = ChromaClientFactory(mock_hass, config)

    with pytest.raises(ContextInjectionError, match="no remote"):
        await factory.get_client()

    mock_issue_registry.async_create_issue.assert_called_once()
    assert factory.available is False
    # Placement is not rewritten to remote when there is no remote to use.
    assert factory.placement == CHROMA_PLACEMENT_EMBEDDED


# ---- Availability: bounded staleness ------------------------------------


def test_availability_starts_false(mock_hass, remote_config):
    """Nothing has been reached yet, so nothing is claimed.

    Init-time state must never masquerade as live state.
    """
    factory = ChromaClientFactory(mock_hass, remote_config)
    assert factory.available is False


@pytest.mark.asyncio
async def test_availability_true_after_successful_client_operation(
    mock_hass, remote_config, mock_chromadb
):
    """A successful operation refreshes availability."""
    factory = ChromaClientFactory(mock_hass, remote_config)

    await factory.get_client()

    assert factory.available is True


@pytest.mark.asyncio
async def test_availability_flips_false_on_connection_failure(
    mock_hass, remote_config, mock_chromadb
):
    """A connection-class failure marks the factory unavailable."""
    mock_chromadb.HttpClient.side_effect = ConnectionError("refused")
    factory = ChromaClientFactory(mock_hass, remote_config)

    with pytest.raises(ContextInjectionError):
        await factory.get_client()

    assert factory.available is False


@pytest.mark.asyncio
async def test_availability_recovers_on_subsequent_success(mock_hass, remote_config, mock_chromadb):
    """Availability recovers when ChromaDB comes back."""
    mock_chromadb.HttpClient.side_effect = ConnectionError("refused")
    factory = ChromaClientFactory(mock_hass, remote_config)

    with pytest.raises(ContextInjectionError):
        await factory.get_client()
    assert factory.available is False

    mock_chromadb.HttpClient.side_effect = None
    await factory.get_client()

    assert factory.available is True


@pytest.mark.asyncio
async def test_probe_registered_for_remote_only(mock_hass, remote_config, embedded_config):
    """The TTL probe runs for remote placement; embedded has no network to lose."""
    with patch(
        "custom_components.pepa_sensory_arm.chroma_factory.async_track_time_interval"
    ) as mock_track:
        await ChromaClientFactory(mock_hass, remote_config).async_setup()
        assert mock_track.call_count == 1

    with patch(
        "custom_components.pepa_sensory_arm.chroma_factory.async_track_time_interval"
    ) as mock_track:
        await ChromaClientFactory(mock_hass, embedded_config).async_setup()
        mock_track.assert_not_called()


# ---- Health check: placement-aware --------------------------------------


@pytest.mark.asyncio
async def test_health_check_remote_probes_host_port(mock_hass, remote_config):
    """Remote health is the server's heartbeat."""
    with patch(
        "custom_components.pepa_sensory_arm.chroma_factory.check_chromadb_health",
        AsyncMock(return_value=(True, "ChromaDB healthy")),
    ) as mock_check:
        factory = ChromaClientFactory(mock_hass, remote_config)
        healthy, _ = await factory.health_check()

    mock_check.assert_awaited_once_with("localhost", 8000)
    assert healthy is True
    assert factory.available is True


@pytest.mark.asyncio
async def test_health_check_embedded_does_not_probe_host_port(
    mock_hass, embedded_config, mock_chromadb
):
    """Embedded health never touches the network.

    This is the whole point of relocating the check: the old unconditional
    host/port probe reported failure for users who never ran a server.
    """
    with patch(
        "custom_components.pepa_sensory_arm.chroma_factory.check_chromadb_health"
    ) as mock_check:
        factory = ChromaClientFactory(mock_hass, embedded_config)
        healthy, message = await factory.health_check()

    mock_check.assert_not_called()
    assert healthy is True
    assert "/tmp/test_config/pepa_chroma" in message


@pytest.mark.asyncio
async def test_health_check_embedded_reports_unwritable_persist_dir(
    mock_hass, embedded_config, mock_chromadb
):
    """An unwritable persist dir is a health failure, named as such."""
    with patch("os.access", return_value=False), patch("os.makedirs"):
        factory = ChromaClientFactory(mock_hass, embedded_config)
        healthy, message = await factory.health_check()

    assert healthy is False
    assert "not writable" in message
    assert factory.available is False


@pytest.mark.asyncio
async def test_health_check_failure_marks_unavailable(mock_hass, remote_config):
    """A failed health check is recorded in the availability flag."""
    with patch(
        "custom_components.pepa_sensory_arm.chroma_factory.check_chromadb_health",
        AsyncMock(return_value=(False, "connection refused")),
    ):
        factory = ChromaClientFactory(mock_hass, remote_config)
        healthy, _ = await factory.health_check()

    assert healthy is False
    assert factory.available is False


# ---- Shutdown -----------------------------------------------------------


@pytest.mark.asyncio
async def test_shutdown_releases_client_and_probe(mock_hass, remote_config, mock_chromadb):
    """Shutdown cancels the probe and drops the client."""
    cancel_probe = MagicMock()
    with patch(
        "custom_components.pepa_sensory_arm.chroma_factory.async_track_time_interval",
        return_value=cancel_probe,
    ):
        factory = ChromaClientFactory(mock_hass, remote_config)
        await factory.async_setup()
        await factory.get_client()

        await factory.async_shutdown()

    cancel_probe.assert_called_once()
    assert factory.available is False
