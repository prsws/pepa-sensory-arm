"""Unit tests for ContextManager class."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.pepa_sensory_arm.const import (
    CONF_CONTEXT_FORMAT,
    CONF_CONTEXT_MODE,
    CONF_DIRECT_ENTITIES,
    CONF_PROMPT_INCLUDE_LABELS,
    CONF_PROMPT_USE_DEFAULT,
    CONTEXT_FORMAT_JSON,
    CONTEXT_MODE_DIRECT,
    CONTEXT_MODE_VECTOR_DB,
    DEFAULT_CONTEXT_MODE,
    DEFAULT_PROMPT_INCLUDE_LABELS,
    EVENT_CONTEXT_INJECTED,
    MAX_CONTEXT_TOKENS,
    TOKEN_WARNING_THRESHOLD,
)
from custom_components.pepa_sensory_arm.context_manager import ContextManager
from custom_components.pepa_sensory_arm.context_providers import (
    ContextProvider,
    DirectContextProvider,
)
from custom_components.pepa_sensory_arm.exceptions import ContextInjectionError, TokenLimitExceeded


class MockContextProvider(ContextProvider):
    """Mock context provider for testing."""

    def __init__(self, hass, config, context_to_return="Mock context"):
        """Initialize mock provider."""
        super().__init__(hass, config)
        self.context_to_return = context_to_return
        self.get_context_called = False
        self.last_user_input = None

    async def get_context(self, user_input: str) -> str:
        """Mock get_context method."""
        self.get_context_called = True
        self.last_user_input = user_input
        return self.context_to_return


@pytest.fixture
def mock_hass():
    """Create mock Home Assistant instance."""
    hass = MagicMock()
    hass.bus = MagicMock()
    hass.bus.async_fire = AsyncMock()
    hass.states = MagicMock()
    hass.states.get = MagicMock(return_value=None)
    hass.states.async_entity_ids = MagicMock(return_value=[])
    return hass


@pytest.fixture
def default_config():
    """Create a replacement-prompt-mode configuration (entity provider active)."""
    return {
        CONF_PROMPT_USE_DEFAULT: False,
        "mode": CONTEXT_MODE_DIRECT,
        "format": CONTEXT_FORMAT_JSON,
        "entities": [{"entity_id": "light.living_room", "attributes": ["brightness"]}],
        "cache_enabled": False,
        "cache_ttl": 60,
        "emit_events": True,
        "max_context_tokens": MAX_CONTEXT_TOKENS,
    }


@pytest.fixture
def context_manager(mock_hass, default_config):
    """Create ContextManager instance."""
    return ContextManager(mock_hass, default_config)


class TestContextManagerInitialization:
    """Test ContextManager initialization."""

    def test_init_with_config(self, mock_hass, default_config):
        """Test initialization with config."""
        manager = ContextManager(mock_hass, default_config)

        assert manager.hass == mock_hass
        assert manager.config == default_config
        assert manager._cache_enabled is False
        assert manager._cache_ttl == 60
        assert manager._emit_events is True
        assert manager._max_context_tokens == MAX_CONTEXT_TOKENS
        assert manager._provider is not None
        assert isinstance(manager._provider, DirectContextProvider)
        assert hasattr(manager._provider, "get_context")
        assert callable(manager._provider.get_context)

    def test_init_with_defaults(self, mock_hass):
        """Test initialization with default values."""
        manager = ContextManager(mock_hass, {CONF_PROMPT_USE_DEFAULT: False})

        assert manager._cache_enabled is False
        assert manager._cache_ttl == 60
        assert manager._emit_events is True
        assert manager._max_context_tokens == MAX_CONTEXT_TOKENS
        assert manager._provider is not None
        assert isinstance(manager._provider, ContextProvider)
        assert hasattr(manager._provider, "get_context")
        assert callable(manager._provider.get_context)

    def test_init_with_cache_enabled(self, mock_hass):
        """Test initialization with cache enabled."""
        config = {
            "cache_enabled": True,
            "cache_ttl": 120,
        }
        manager = ContextManager(mock_hass, config)

        assert manager._cache_enabled is True
        assert manager._cache_ttl == 120

    def test_init_direct_mode(self, mock_hass):
        """Test initialization with direct mode."""
        config = {CONF_PROMPT_USE_DEFAULT: False, "mode": CONTEXT_MODE_DIRECT}
        manager = ContextManager(mock_hass, config)

        assert isinstance(manager._provider, DirectContextProvider)

    def test_init_vector_db_mode_fallback(self, mock_hass):
        """Test initialization with vector DB mode falls back to direct when unavailable."""
        config = {CONF_PROMPT_USE_DEFAULT: False, "mode": CONTEXT_MODE_VECTOR_DB}
        manager = ContextManager(mock_hass, config)

        # Should fallback to DirectContextProvider since chromadb is not available in test env
        assert isinstance(manager._provider, DirectContextProvider)

    def test_init_vector_db_mode_fallback_on_import_error(self, mock_hass):
        """Test that vector_db mode gracefully falls back to direct mode on import error."""
        config = {CONF_PROMPT_USE_DEFAULT: False, CONF_CONTEXT_MODE: CONTEXT_MODE_VECTOR_DB}

        with patch.object(
            ContextManager,
            "_create_vector_db_provider",
            side_effect=ImportError("No module named 'chromadb'"),
        ):
            manager = ContextManager(mock_hass, config)
            # Should fall back to direct provider, NOT raise
            assert isinstance(manager._provider, DirectContextProvider)

    def test_init_direct_mode_failure_raises(self, mock_hass):
        """Test that direct mode failure still raises ContextInjectionError."""
        config = {CONF_PROMPT_USE_DEFAULT: False, CONF_CONTEXT_MODE: CONTEXT_MODE_DIRECT}

        with patch.object(
            ContextManager,
            "_create_direct_provider",
            side_effect=Exception("Provider creation failed"),
        ):
            with pytest.raises(ContextInjectionError, match="Failed to initialize"):
                ContextManager(mock_hass, config)

    def test_init_invalid_mode_fallback(self, mock_hass):
        """Test initialization with invalid mode (should fallback to direct)."""
        config = {CONF_PROMPT_USE_DEFAULT: False, "mode": "invalid_mode"}
        manager = ContextManager(mock_hass, config)

        assert isinstance(manager._provider, DirectContextProvider)

    def test_init_provider_failure(self, mock_hass):
        """Test initialization when provider creation fails."""
        config = {CONF_PROMPT_USE_DEFAULT: False, "mode": CONTEXT_MODE_DIRECT}

        with patch.object(
            ContextManager,
            "_create_direct_provider",
            side_effect=Exception("Provider creation failed"),
        ):
            with pytest.raises(ContextInjectionError, match="Failed to initialize"):
                ContextManager(mock_hass, config)


class TestIncludeLabelsConfiguration:
    """Test include_labels configuration handling."""

    def test_include_labels_defaults_to_false(self, mock_hass):
        """Test that include_labels defaults to False when not in config."""
        config = {
            CONF_PROMPT_USE_DEFAULT: False,
            CONF_CONTEXT_MODE: CONTEXT_MODE_DIRECT,
        }
        manager = ContextManager(mock_hass, config)

        # Verify the provider was created with include_labels=False
        assert isinstance(manager._provider, DirectContextProvider)
        assert manager._provider.include_labels is False
        assert manager._provider.include_labels == DEFAULT_PROMPT_INCLUDE_LABELS

    def test_include_labels_set_to_true(self, mock_hass):
        """Test that include_labels=True is correctly passed to DirectContextProvider."""
        config = {
            CONF_PROMPT_USE_DEFAULT: False,
            CONF_CONTEXT_MODE: CONTEXT_MODE_DIRECT,
            CONF_PROMPT_INCLUDE_LABELS: True,
        }
        manager = ContextManager(mock_hass, config)

        # Verify the provider was created with include_labels=True
        assert isinstance(manager._provider, DirectContextProvider)
        assert manager._provider.include_labels is True

    def test_include_labels_set_to_false_explicitly(self, mock_hass):
        """Test that include_labels=False is correctly passed to DirectContextProvider."""
        config = {
            CONF_PROMPT_USE_DEFAULT: False,
            CONF_CONTEXT_MODE: CONTEXT_MODE_DIRECT,
            CONF_PROMPT_INCLUDE_LABELS: False,
        }
        manager = ContextManager(mock_hass, config)

        # Verify the provider was created with include_labels=False
        assert isinstance(manager._provider, DirectContextProvider)
        assert manager._provider.include_labels is False

    def test_include_labels_with_entities_and_format(self, mock_hass):
        """Test include_labels is passed along with other provider config."""
        config = {
            CONF_PROMPT_USE_DEFAULT: False,
            CONF_CONTEXT_MODE: CONTEXT_MODE_DIRECT,
            CONF_DIRECT_ENTITIES: [{"entity_id": "light.test", "attributes": ["brightness"]}],
            CONF_CONTEXT_FORMAT: CONTEXT_FORMAT_JSON,
            CONF_PROMPT_INCLUDE_LABELS: True,
        }
        manager = ContextManager(mock_hass, config)

        # Verify the provider was created with all config options
        assert isinstance(manager._provider, DirectContextProvider)
        assert manager._provider.include_labels is True
        assert manager._provider.format_type == CONTEXT_FORMAT_JSON
        assert len(manager._provider.entities_config) == 1
        assert manager._provider.entities_config[0]["entity_id"] == "light.test"

    def test_create_direct_provider_passes_include_labels(self, mock_hass):
        """Test that _create_direct_provider correctly reads and passes include_labels."""
        # Test with include_labels=True
        config_with_labels = {
            CONF_PROMPT_USE_DEFAULT: False,
            CONF_CONTEXT_MODE: CONTEXT_MODE_DIRECT,
            CONF_PROMPT_INCLUDE_LABELS: True,
        }
        manager_with_labels = ContextManager(mock_hass, config_with_labels)
        provider_with_labels = manager_with_labels._create_direct_provider()
        assert provider_with_labels.include_labels is True

        # Test with include_labels=False
        config_without_labels = {
            CONF_PROMPT_USE_DEFAULT: False,
            CONF_CONTEXT_MODE: CONTEXT_MODE_DIRECT,
            CONF_PROMPT_INCLUDE_LABELS: False,
        }
        manager_without_labels = ContextManager(mock_hass, config_without_labels)
        provider_without_labels = manager_without_labels._create_direct_provider()
        assert provider_without_labels.include_labels is False

    def test_include_labels_not_affected_by_other_config_keys(self, mock_hass):
        """Test that include_labels is independent of other config keys."""
        config = {
            CONF_PROMPT_USE_DEFAULT: False,
            CONF_CONTEXT_MODE: CONTEXT_MODE_DIRECT,
            CONF_PROMPT_INCLUDE_LABELS: True,
            "cache_enabled": True,
            "cache_ttl": 120,
            "emit_events": False,
            "max_context_tokens": 16000,
        }
        manager = ContextManager(mock_hass, config)

        # Verify include_labels is correctly set regardless of other config
        assert isinstance(manager._provider, DirectContextProvider)
        assert manager._provider.include_labels is True
        # Verify other config options didn't interfere
        assert manager._cache_enabled is True
        assert manager._cache_ttl == 120
        assert manager._emit_events is False
        assert manager._max_context_tokens == 16000


class TestSetProvider:
    """Test set_provider method."""

    def test_set_provider(self, context_manager, mock_hass):
        """Test setting a custom provider."""
        custom_provider = MockContextProvider(mock_hass, {})

        context_manager.set_provider(custom_provider)

        assert context_manager._provider == custom_provider
        assert isinstance(context_manager._provider, MockContextProvider)
        assert hasattr(context_manager._provider, "get_context")
        assert len(context_manager._cache) == 0
        assert len(context_manager._cache_timestamps) == 0
        assert isinstance(context_manager._cache, dict)
        assert isinstance(context_manager._cache_timestamps, dict)

    def test_set_provider_clears_cache(self, context_manager, mock_hass):
        """Test that setting provider clears cache."""
        # Add some cache entries
        context_manager._cache["key1"] = "value1"
        context_manager._cache_timestamps["key1"] = time.time()

        custom_provider = MockContextProvider(mock_hass, {})
        context_manager.set_provider(custom_provider)

        assert len(context_manager._cache) == 0
        assert len(context_manager._cache_timestamps) == 0


@pytest.mark.asyncio
class TestGetContext:
    """Test get_context method."""

    async def test_get_context_success(self, context_manager):
        """Test successful context retrieval."""
        provider = MockContextProvider(context_manager.hass, {}, "Test context")
        context_manager.set_provider(provider)

        context = await context_manager.get_context("test input")

        assert context == "Test context"
        assert provider.get_context_called
        assert provider.last_user_input == "test input"

    async def test_get_context_no_provider(self, mock_hass):
        """Test get_context with no provider configured."""
        manager = ContextManager.__new__(ContextManager)
        manager.hass = mock_hass
        manager.config = {CONF_PROMPT_USE_DEFAULT: False}
        manager._provider = None
        manager._cache_enabled = False

        with pytest.raises(ContextInjectionError, match="No context provider"):
            await manager.get_context("test input")

    async def test_get_context_provider_failure(self, context_manager):
        """Test get_context when provider fails."""
        provider = MockContextProvider(context_manager.hass, {})
        provider.get_context = AsyncMock(side_effect=Exception("Provider failed"))
        context_manager.set_provider(provider)

        with pytest.raises(ContextInjectionError, match="Failed to retrieve context"):
            await context_manager.get_context("test input")

    async def test_get_context_with_cache_hit(self, context_manager):
        """Test get_context with cache hit."""
        context_manager._cache_enabled = True
        provider = MockContextProvider(context_manager.hass, {}, "Fresh context")
        context_manager.set_provider(provider)

        # Cache a value
        cache_key = context_manager._generate_cache_key("test input")
        context_manager._cache[cache_key] = "Cached context"
        context_manager._cache_timestamps[cache_key] = time.time()

        context = await context_manager.get_context("test input")

        assert context == "Cached context"
        assert not provider.get_context_called

    async def test_get_context_with_cache_miss(self, context_manager):
        """Test get_context with cache miss."""
        context_manager._cache_enabled = True
        provider = MockContextProvider(context_manager.hass, {}, "Fresh context")
        context_manager.set_provider(provider)

        context = await context_manager.get_context("test input")

        assert context == "Fresh context"
        assert provider.get_context_called

    async def test_get_context_with_expired_cache(self, context_manager):
        """Test get_context with expired cache.

        When cache is expired, should fetch fresh context and re-cache it.
        """
        context_manager._cache_enabled = True
        context_manager._cache_ttl = 1
        provider = MockContextProvider(context_manager.hass, {}, "Fresh context")
        context_manager.set_provider(provider)

        # Cache a value with old timestamp
        cache_key = context_manager._generate_cache_key("test input")
        context_manager._cache[cache_key] = "Expired context"
        context_manager._cache_timestamps[cache_key] = time.time() - 10

        context = await context_manager.get_context("test input")

        # Should return fresh context
        assert context == "Fresh context"
        # Provider should have been called to fetch fresh data
        assert provider.get_context_called
        # Cache should now contain the fresh context (re-cached)
        assert context_manager._cache[cache_key] == "Fresh context"
        # Timestamp should be updated to recent time
        assert context_manager._cache_timestamps[cache_key] > time.time() - 5

    async def test_get_context_caches_result(self, context_manager):
        """Test that get_context caches the result."""
        context_manager._cache_enabled = True
        provider = MockContextProvider(context_manager.hass, {}, "Fresh context")
        context_manager.set_provider(provider)

        await context_manager.get_context("test input")

        cache_key = context_manager._generate_cache_key("test input")
        assert cache_key in context_manager._cache
        assert context_manager._cache[cache_key] == "Fresh context"


@pytest.mark.asyncio
class TestGetFormattedContext:
    """Test get_formatted_context method."""

    async def test_get_formatted_context_success(self, context_manager):
        """Test successful formatted context retrieval."""
        provider = MockContextProvider(context_manager.hass, {}, "Test context")
        context_manager.set_provider(provider)

        context = await context_manager.get_formatted_context("test input", "conv_123")

        assert context is not None
        assert isinstance(context, str)
        assert len(context) > 0
        # Verify the exact expected content is returned
        assert "Test context" in context, f"Expected 'Test context' in result, got: {context}"
        assert provider.get_context_called
        assert provider.last_user_input == "test input"

    async def test_get_formatted_context_optimizes_size(self, context_manager):
        """Test that get_formatted_context optimizes size."""
        # Create context with excessive whitespace
        provider = MockContextProvider(
            context_manager.hass, {}, "Test    context   with    lots     of     spaces"
        )
        context_manager.set_provider(provider)

        context = await context_manager.get_formatted_context("test input")

        # Should have normalized whitespace
        assert "  " not in context
        assert isinstance(context, str)
        assert len(context) > 0
        assert "Test" in context and "context" in context and "with" in context

    async def test_get_formatted_context_fires_event(self, context_manager, mock_hass):
        """Test that get_formatted_context fires event."""
        provider = MockContextProvider(context_manager.hass, {}, "Test context")
        context_manager.set_provider(provider)

        await context_manager.get_formatted_context("test input", "conv_123")

        mock_hass.bus.async_fire.assert_called_once()
        event_name, event_data = mock_hass.bus.async_fire.call_args[0]
        assert event_name == EVENT_CONTEXT_INJECTED
        assert isinstance(event_data, dict)
        assert event_data["conversation_id"] == "conv_123"
        assert "mode" in event_data
        assert "token_count" in event_data

    async def test_get_formatted_context_no_event_when_disabled(self, context_manager, mock_hass):
        """Test that no event is fired when disabled."""
        context_manager._emit_events = False
        provider = MockContextProvider(context_manager.hass, {}, "Test context")
        context_manager.set_provider(provider)

        await context_manager.get_formatted_context("test input")

        mock_hass.bus.async_fire.assert_not_called()

    async def test_get_formatted_context_exceeds_token_limit(self, context_manager):
        """Test get_formatted_context when token limit exceeded."""
        # Create very large context
        large_context = "x" * (MAX_CONTEXT_TOKENS * 5)
        provider = MockContextProvider(context_manager.hass, {}, large_context)
        context_manager.set_provider(provider)

        with pytest.raises(TokenLimitExceeded, match="exceeds limit"):
            await context_manager.get_formatted_context("test input")

    async def test_get_formatted_context_approaching_token_limit(self, context_manager):
        """Test get_formatted_context warns when approaching limit."""
        # Create context near the limit
        warning_threshold = int(MAX_CONTEXT_TOKENS * TOKEN_WARNING_THRESHOLD)
        large_context = "x" * (warning_threshold * 4 + 100)
        provider = MockContextProvider(context_manager.hass, {}, large_context)
        context_manager.set_provider(provider)

        # Should succeed but log warning
        context = await context_manager.get_formatted_context("test input")
        assert context is not None
        assert isinstance(context, str)
        assert len(context) > 0
        # Should contain the original content (possibly truncated)
        assert "x" in context

    async def test_get_formatted_context_truncates_if_needed(self, context_manager):
        """Test that context is truncated if too large."""
        # Create context that's too large
        max_chars = context_manager._max_context_tokens * 4
        large_context = "x" * (max_chars + 1000)
        provider = MockContextProvider(context_manager.hass, {}, large_context)
        context_manager.set_provider(provider)

        # Should be truncated in optimization step
        optimized = context_manager._optimize_context_size(large_context)
        assert len(optimized) <= max_chars + 20  # Allow for truncation suffix


class TestOptimizeContextSize:
    """Test _optimize_context_size method."""

    def test_optimize_context_size_removes_whitespace(self, context_manager):
        """Test that optimization removes excessive whitespace."""
        context = "Test    context   with    lots     of     spaces"

        optimized = context_manager._optimize_context_size(context)

        assert "  " not in optimized
        assert optimized == "Test context with lots of spaces"

    def test_optimize_context_size_truncates_if_needed(self, context_manager):
        """Test that optimization truncates if needed."""
        max_chars = context_manager._max_context_tokens * 4
        context = "x" * (max_chars + 1000)

        optimized = context_manager._optimize_context_size(context)

        assert len(optimized) <= max_chars + 20
        assert "[truncated]" in optimized

    def test_optimize_context_size_no_change_if_small(self, context_manager):
        """Test that small context is not changed."""
        context = "Small context"

        optimized = context_manager._optimize_context_size(context)

        assert optimized == context


class TestCacheBehavior:
    """Test cache behavior."""

    def test_generate_cache_key_direct_mode(self, context_manager):
        """Test cache key generation for direct mode."""
        context_manager.config["mode"] = CONTEXT_MODE_DIRECT

        key1 = context_manager._generate_cache_key("input 1")
        key2 = context_manager._generate_cache_key("input 2")

        # Direct mode should use same key regardless of input
        assert key1 == key2
        assert key1 == "direct_context"

    def test_generate_cache_key_vector_db_mode(self, context_manager):
        """Test cache key generation for vector DB mode."""
        context_manager.config["mode"] = CONTEXT_MODE_VECTOR_DB

        key1 = context_manager._generate_cache_key("input 1")
        key2 = context_manager._generate_cache_key("input 2")

        # Vector DB mode should use different keys for different inputs
        assert key1 != key2
        assert len(key1) == 32  # MD5 hash length
        assert len(key2) == 32

    def test_cache_context(self, context_manager):
        """Test caching context."""
        context_manager._cache_context("test input", "test context")

        cache_key = context_manager._generate_cache_key("test input")
        assert cache_key in context_manager._cache
        assert context_manager._cache[cache_key] == "test context"
        assert isinstance(context_manager._cache[cache_key], str)
        assert cache_key in context_manager._cache_timestamps
        assert isinstance(context_manager._cache_timestamps[cache_key], (int, float))
        assert context_manager._cache_timestamps[cache_key] > 0

    def test_get_cached_context_hit(self, context_manager):
        """Test getting cached context when available."""
        cache_key = context_manager._generate_cache_key("test input")
        context_manager._cache[cache_key] = "cached context"
        context_manager._cache_timestamps[cache_key] = time.time()

        result = context_manager._get_cached_context("test input")

        assert result == "cached context"

    def test_get_cached_context_miss(self, context_manager):
        """Test getting cached context when not available."""
        result = context_manager._get_cached_context("test input")

        assert result is None

    def test_get_cached_context_expired(self, context_manager):
        """Test getting expired cached context."""
        context_manager._cache_ttl = 1
        cache_key = context_manager._generate_cache_key("test input")
        context_manager._cache[cache_key] = "cached context"
        context_manager._cache_timestamps[cache_key] = time.time() - 10

        result = context_manager._get_cached_context("test input")

        assert result is None
        # Cache should be cleaned up after expiration
        assert cache_key not in context_manager._cache
        assert cache_key not in context_manager._cache_timestamps

    def test_clear_cache(self, context_manager):
        """Test clearing cache."""
        context_manager._cache["key1"] = "value1"
        context_manager._cache["key2"] = "value2"
        context_manager._cache_timestamps["key1"] = time.time()
        context_manager._cache_timestamps["key2"] = time.time()

        context_manager._clear_cache()

        assert len(context_manager._cache) == 0
        assert len(context_manager._cache_timestamps) == 0


@pytest.mark.asyncio
class TestUpdateConfig:
    """Test update_config method."""

    async def test_update_config_basic(self, context_manager):
        """Test basic config update."""
        new_config = {
            "cache_enabled": True,
            "cache_ttl": 120,
        }

        await context_manager.update_config(new_config)

        assert context_manager._cache_enabled is True
        assert context_manager._cache_ttl == 120
        assert context_manager.config["cache_enabled"] is True

    async def test_update_config_changes_mode(self, context_manager, mock_hass):
        """Test updating config with mode change."""
        original_provider = context_manager._provider

        new_config = {"mode": CONTEXT_MODE_VECTOR_DB}

        await context_manager.update_config(new_config)

        # Provider should be reinitialized
        assert context_manager._provider != original_provider
        assert context_manager._provider is not None
        assert isinstance(context_manager._provider, ContextProvider)
        assert context_manager.config["mode"] == CONTEXT_MODE_VECTOR_DB

    async def test_update_config_clears_cache(self, context_manager):
        """Test that updating config clears cache."""
        context_manager._cache["key1"] = "value1"
        context_manager._cache_timestamps["key1"] = time.time()

        await context_manager.update_config({"cache_ttl": 120})

        assert len(context_manager._cache) == 0
        assert len(context_manager._cache_timestamps) == 0
        assert isinstance(context_manager._cache, dict)
        assert isinstance(context_manager._cache_timestamps, dict)

    async def test_update_config_same_mode_no_reinit(self, context_manager):
        """Test updating config without mode change."""
        original_provider = context_manager._provider

        new_config = {"cache_enabled": True}

        await context_manager.update_config(new_config)

        # Provider should be the same
        assert context_manager._provider == original_provider

    async def test_update_config_updates_max_tokens(self, context_manager):
        """Test updating max context tokens."""
        new_config = {"max_context_tokens": 16000}

        await context_manager.update_config(new_config)

        assert context_manager._max_context_tokens == 16000
        assert isinstance(context_manager._max_context_tokens, int)
        assert context_manager._max_context_tokens > 0
        assert context_manager.config["max_context_tokens"] == 16000


class TestGetCurrentMode:
    """Test get_current_mode method."""

    def test_get_current_mode(self, context_manager):
        """Test getting current mode."""
        mode = context_manager.get_current_mode()

        assert mode == CONTEXT_MODE_DIRECT
        assert isinstance(mode, str)
        assert len(mode) > 0
        assert mode in [CONTEXT_MODE_DIRECT, CONTEXT_MODE_VECTOR_DB]

    def test_get_current_mode_default(self, mock_hass):
        """Test getting current mode with no mode in config (replacement prompt)."""
        manager = ContextManager(mock_hass, {CONF_PROMPT_USE_DEFAULT: False})

        mode = manager.get_current_mode()

        assert mode == DEFAULT_CONTEXT_MODE
        assert isinstance(mode, str)
        assert len(mode) > 0
        assert mode in [CONTEXT_MODE_DIRECT, CONTEXT_MODE_VECTOR_DB]

    def test_get_current_mode_default_prompt(self, mock_hass):
        """Test that default prompt mode reports the 'default' composition mode."""
        manager = ContextManager(mock_hass, {})

        assert manager.get_current_mode() == "default"


class TestGetProviderInfo:
    """Test get_provider_info method."""

    def test_get_provider_info_direct(self, context_manager):
        """Test getting provider info for direct provider."""
        info = context_manager.get_provider_info()

        assert isinstance(info, dict)
        assert info["provider_class"] == "DirectContextProvider"
        assert info["mode"] == CONTEXT_MODE_DIRECT
        assert info["cache_enabled"] is False
        assert info["cache_ttl"] == 60
        assert info["max_context_tokens"] == MAX_CONTEXT_TOKENS
        assert "format" in info
        assert isinstance(info["format"], str)
        assert "entity_count" in info
        assert isinstance(info["entity_count"], int)
        assert info["entity_count"] >= 0

    def test_get_provider_info_no_provider(self, context_manager):
        """Test getting provider info when no provider set."""
        context_manager._provider = None

        info = context_manager.get_provider_info()

        assert isinstance(info, dict)
        assert info["provider_class"] is None
        assert "mode" in info
        assert isinstance(info["mode"], str)
        assert info["mode"] in [CONTEXT_MODE_DIRECT, CONTEXT_MODE_VECTOR_DB, DEFAULT_CONTEXT_MODE]

    def test_get_provider_info_custom_provider(self, context_manager, mock_hass):
        """Test getting provider info for custom provider."""
        custom_provider = MockContextProvider(mock_hass, {})
        context_manager.set_provider(custom_provider)

        info = context_manager.get_provider_info()

        assert isinstance(info, dict)
        assert info["provider_class"] == "MockContextProvider"
        assert isinstance(info["provider_class"], str)
        assert len(info["provider_class"]) > 0


@pytest.mark.asyncio
class TestEventFiring:
    """Test event firing behavior."""

    async def test_fire_context_injected_event(self, context_manager, mock_hass):
        """Test firing context injected event."""
        provider = MockContextProvider(context_manager.hass, {}, "Test context")
        context_manager.set_provider(provider)

        await context_manager.get_formatted_context("test input", "conv_123")

        mock_hass.bus.async_fire.assert_called_once()
        event_name, event_data = mock_hass.bus.async_fire.call_args[0]

        assert event_name == EVENT_CONTEXT_INJECTED
        assert isinstance(event_data, dict)
        assert event_data["conversation_id"] == "conv_123"
        assert event_data["mode"] == CONTEXT_MODE_DIRECT
        assert "token_count" in event_data
        assert isinstance(event_data["token_count"], int)
        assert event_data["token_count"] > 0

    async def test_fire_context_injected_event_with_entities(self, context_manager, mock_hass):
        """Test firing event includes entity information."""
        # Set up a mock state
        mock_state = MagicMock()
        mock_state.entity_id = "light.living_room"
        mock_state.state = "on"
        mock_state.attributes = {"friendly_name": "Living Room Light"}
        mock_hass.states.get = MagicMock(return_value=mock_state)
        mock_hass.states.async_entity_ids = MagicMock(return_value=["light.living_room"])

        provider = DirectContextProvider(
            mock_hass, {"entities": [{"entity_id": "light.living_room"}], "format": "json"}
        )
        context_manager.set_provider(provider)

        await context_manager.get_formatted_context("test input", "conv_123")

        event_data = mock_hass.bus.async_fire.call_args[0][1]
        assert isinstance(event_data, dict)
        assert "entities_included" in event_data
        assert isinstance(event_data["entities_included"], list)
        assert "entity_count" in event_data
        assert isinstance(event_data["entity_count"], int)
        assert event_data["entity_count"] >= 0

    async def test_fire_context_injected_event_vector_db_mode(self, context_manager, mock_hass):
        """Test firing event in vector DB mode includes query."""
        context_manager.config["mode"] = CONTEXT_MODE_VECTOR_DB
        provider = MockContextProvider(context_manager.hass, {}, "Test context")
        context_manager.set_provider(provider)

        await context_manager.get_formatted_context("test input", "conv_123")

        event_data = mock_hass.bus.async_fire.call_args[0][1]
        assert isinstance(event_data, dict)
        assert "vector_db_query" in event_data
        assert isinstance(event_data["vector_db_query"], str)
        assert event_data["vector_db_query"] == "test input"
        assert len(event_data["vector_db_query"]) > 0


class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_get_context_with_empty_string(self, context_manager):
        """Test get_context with empty user input."""
        provider = MockContextProvider(context_manager.hass, {}, "Context")
        context_manager.set_provider(provider)

        context = await context_manager.get_context("")

        assert context == "Context"
        assert isinstance(context, str)
        assert len(context) > 0
        assert provider.get_context_called
        assert provider.last_user_input == ""
        assert isinstance(provider.last_user_input, str)

    @pytest.mark.asyncio
    async def test_get_formatted_context_with_empty_context(self, context_manager):
        """Test get_formatted_context with empty context."""
        provider = MockContextProvider(context_manager.hass, {}, "")
        context_manager.set_provider(provider)

        context = await context_manager.get_formatted_context("test")

        assert context == ""
        assert isinstance(context, str)
        assert len(context) == 0
        assert provider.get_context_called
        assert provider.last_user_input == "test"

    def test_optimize_context_size_with_empty_string(self, context_manager):
        """Test optimizing empty context."""
        optimized = context_manager._optimize_context_size("")

        assert optimized == ""
        assert isinstance(optimized, str)
        assert len(optimized) == 0

    @pytest.mark.asyncio
    async def test_concurrent_cache_access(self, context_manager):
        """Test concurrent access to cache doesn't cause issues."""
        context_manager._cache_enabled = True
        provider = MockContextProvider(context_manager.hass, {}, "Test context")
        context_manager.set_provider(provider)

        # Make multiple concurrent requests
        import asyncio

        tasks = [context_manager.get_context(f"input {i}") for i in range(10)]
        results = await asyncio.gather(*tasks)

        assert len(results) == 10
        assert all(r == "Test context" for r in results)
        assert all(isinstance(r, str) for r in results)
        assert all(len(r) > 0 for r in results)
        # Verify provider was actually called
        assert provider.get_context_called


class FailingContextProvider(ContextProvider):
    """Context provider that always raises."""

    async def get_context(self, user_input: str) -> str:
        """Raise an error."""
        raise Exception("Provider failed")


@pytest.fixture
def default_mode_manager(mock_hass):
    """Create a ContextManager in default prompt mode (composition: memory + retrieval)."""
    return ContextManager(mock_hass, {})


class TestDefaultModeInitialization:
    """Test provider initialization in default prompt mode."""

    def test_entity_providers_never_instantiated(self, mock_hass):
        """In default mode neither Direct nor VectorDB providers are created."""
        with (
            patch.object(ContextManager, "_create_direct_provider") as mock_direct,
            patch.object(ContextManager, "_create_vector_db_provider") as mock_vector,
        ):
            manager = ContextManager(mock_hass, {CONF_CONTEXT_MODE: CONTEXT_MODE_DIRECT})
            assert manager._provider is None
            manager_v = ContextManager(mock_hass, {CONF_CONTEXT_MODE: CONTEXT_MODE_VECTOR_DB})
            assert manager_v._provider is None

        mock_direct.assert_not_called()
        mock_vector.assert_not_called()

    def test_provider_info_reports_default_mode(self, mock_hass):
        """get_provider_info reports the composition and entity modes."""
        info = ContextManager(mock_hass, {}).get_provider_info()

        assert info["provider_class"] is None
        assert info["mode"] == "default"
        assert info["entity_context_mode"] == DEFAULT_CONTEXT_MODE


@pytest.mark.asyncio
class TestDefaultModeComposition:
    """Test context composition in default prompt mode (memory + retrieval only)."""

    async def test_entity_provider_never_invoked(self, default_mode_manager, mock_hass):
        """Even a manually injected entity provider is not consulted in default mode."""
        entity_provider = MockContextProvider(mock_hass, {}, "ENTITY CONTEXT")
        default_mode_manager._provider = entity_provider
        default_mode_manager._memory_provider = MockContextProvider(mock_hass, {}, "memory part")

        context = await default_mode_manager.get_context("test input")

        assert not entity_provider.get_context_called
        assert context == "memory part"

    async def test_memory_and_retrieval_merged_in_order(self, default_mode_manager, mock_hass):
        """Both legs present: memory first, retrieval second, newline-joined."""
        default_mode_manager._memory_provider = MockContextProvider(mock_hass, {}, "memory part")
        default_mode_manager._retrieval_provider = MockContextProvider(
            mock_hass, {}, "retrieval part"
        )

        context = await default_mode_manager.get_context("test input")

        assert context == "memory part\nretrieval part"

    async def test_memory_only(self, default_mode_manager, mock_hass):
        """Retrieval leg absent/empty: memory output returned alone."""
        default_mode_manager._memory_provider = MockContextProvider(mock_hass, {}, "memory part")

        assert await default_mode_manager.get_context("x") == "memory part"

        default_mode_manager._retrieval_provider = MockContextProvider(mock_hass, {}, "")
        assert await default_mode_manager.get_context("x") == "memory part"

    async def test_retrieval_only(self, default_mode_manager, mock_hass):
        """Memory leg absent/empty: retrieval output returned alone."""
        default_mode_manager._retrieval_provider = MockContextProvider(
            mock_hass, {}, "retrieval part"
        )

        assert await default_mode_manager.get_context("x") == "retrieval part"

        default_mode_manager._memory_provider = MockContextProvider(mock_hass, {}, "")
        assert await default_mode_manager.get_context("x") == "retrieval part"

    async def test_both_empty_returns_empty(self, default_mode_manager, mock_hass):
        """Both legs empty: empty string, no error."""
        default_mode_manager._memory_provider = MockContextProvider(mock_hass, {}, "")
        default_mode_manager._retrieval_provider = MockContextProvider(mock_hass, {}, "")

        assert await default_mode_manager.get_context("x") == ""

    async def test_no_providers_returns_empty(self, default_mode_manager):
        """No memory and no retrieval provider: empty string, no error."""
        assert await default_mode_manager.get_context("x") == ""

    async def test_memory_failure_returns_retrieval(self, default_mode_manager, mock_hass, caplog):
        """Memory leg raising: retrieval output returned, warning logged."""
        default_mode_manager._memory_provider = FailingContextProvider(mock_hass, {})
        default_mode_manager._retrieval_provider = MockContextProvider(
            mock_hass, {}, "retrieval part"
        )

        context = await default_mode_manager.get_context("x")

        assert context == "retrieval part"
        assert "Failed to get memory context" in caplog.text

    async def test_retrieval_failure_returns_memory(self, default_mode_manager, mock_hass, caplog):
        """Retrieval leg raising: memory output returned, warning logged."""
        default_mode_manager._memory_provider = MockContextProvider(mock_hass, {}, "memory part")
        default_mode_manager._retrieval_provider = FailingContextProvider(mock_hass, {})

        context = await default_mode_manager.get_context("x")

        assert context == "memory part"
        assert "Failed to get retrieval context" in caplog.text

    async def test_no_sentinel_strings_in_output(self, default_mode_manager, mock_hass):
        """Entity-provider sentinels never appear in default-mode output."""
        default_mode_manager._memory_provider = MockContextProvider(mock_hass, {}, "")
        default_mode_manager._retrieval_provider = FailingContextProvider(mock_hass, {})

        context = await default_mode_manager.get_context("x")

        assert "No relevant context found" not in context
        assert "[Fallback mode - Vector DB unavailable]" not in context
        assert context == ""

    async def test_metrics_mode_reports_default(self, default_mode_manager, mock_hass):
        """get_formatted_context reports composition mode 'default' in metrics."""
        default_mode_manager._memory_provider = MockContextProvider(mock_hass, {}, "memory part")
        metrics = {}

        await default_mode_manager.get_formatted_context("x", "conv_1", metrics)

        assert metrics["context"]["mode"] == "default"


@pytest.mark.asyncio
class TestReplacementModeRetrievalLeg:
    """Test the retrieval leg appended to the legacy replacement-mode merge."""

    async def test_retrieval_appended_after_memory(self, context_manager, mock_hass):
        """Entity, memory, retrieval composed in order."""
        context_manager.set_provider(MockContextProvider(mock_hass, {}, "entity part"))
        context_manager._memory_provider = MockContextProvider(mock_hass, {}, "memory part")
        context_manager._retrieval_provider = MockContextProvider(mock_hass, {}, "retrieval part")

        context = await context_manager.get_context("x")

        assert context == "entity part\nmemory part\nretrieval part"

    async def test_retrieval_appended_without_memory(self, context_manager, mock_hass):
        """Retrieval leg works with no memory provider."""
        context_manager.set_provider(MockContextProvider(mock_hass, {}, "entity part"))
        context_manager._retrieval_provider = MockContextProvider(mock_hass, {}, "retrieval part")

        context = await context_manager.get_context("x")

        assert context == "entity part\nretrieval part"

    async def test_empty_retrieval_leg_skipped(self, context_manager, mock_hass):
        """Empty retrieval output adds no separator."""
        context_manager.set_provider(MockContextProvider(mock_hass, {}, "entity part"))
        context_manager._memory_provider = MockContextProvider(mock_hass, {}, "memory part")
        context_manager._retrieval_provider = MockContextProvider(mock_hass, {}, "")

        context = await context_manager.get_context("x")

        assert context == "entity part\nmemory part"

    async def test_retrieval_failure_skipped(self, context_manager, mock_hass, caplog):
        """A failing retrieval leg is skipped with a warning."""
        context_manager.set_provider(MockContextProvider(mock_hass, {}, "entity part"))
        context_manager._memory_provider = MockContextProvider(mock_hass, {}, "memory part")
        context_manager._retrieval_provider = FailingContextProvider(mock_hass, {})

        context = await context_manager.get_context("x")

        assert context == "entity part\nmemory part"
        assert "Failed to get retrieval context" in caplog.text

    async def test_sentinel_replacement_preserved_with_retrieval(self, context_manager, mock_hass):
        """Sentinel entity context is still replaced by memory; retrieval appended."""
        context_manager.set_provider(
            MockContextProvider(mock_hass, {}, "No relevant context found.")
        )
        context_manager._memory_provider = MockContextProvider(mock_hass, {}, "memory part")
        context_manager._retrieval_provider = MockContextProvider(mock_hass, {}, "retrieval part")

        context = await context_manager.get_context("x")

        assert context == "memory part\nretrieval part"

    async def test_entity_failure_still_raises(self, context_manager, mock_hass):
        """Entity leg failure still raises even with retrieval configured."""
        context_manager.set_provider(FailingContextProvider(mock_hass, {}))
        context_manager._retrieval_provider = MockContextProvider(mock_hass, {}, "retrieval part")

        with pytest.raises(ContextInjectionError, match="Failed to retrieve entity context"):
            await context_manager.get_context("x")
