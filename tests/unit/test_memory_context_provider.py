"""Unit tests for MemoryContextProvider."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.pepa_sensory_arm.const import (
    CONF_MEMORY_CONTEXT_TOP_K,
    CONF_MEMORY_ENABLED,
    CONF_MEMORY_MIN_IMPORTANCE,
    DEFAULT_MEMORY_CONTEXT_TOP_K,
)
from custom_components.pepa_sensory_arm.context_providers.memory import MemoryContextProvider
from custom_components.pepa_sensory_arm.memory_interface import MemoryRecord

from .conftest import make_record


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    return MagicMock()


@pytest.fixture
def mock_memory():
    """Create a mock memory backend, typed by the contract's surface."""
    mock = MagicMock()
    mock.recall = AsyncMock()
    return mock


@pytest.fixture
def memory_context_provider(mock_hass, mock_memory):
    """Create a MemoryContextProvider instance."""
    config = {
        CONF_MEMORY_ENABLED: True,
        CONF_MEMORY_CONTEXT_TOP_K: 5,
        CONF_MEMORY_MIN_IMPORTANCE: 0.3,
    }
    return MemoryContextProvider(mock_hass, config, mock_memory)


@pytest.mark.asyncio
async def test_get_context_memory_disabled(mock_hass, mock_memory):
    """Test that get_context returns empty string when memory is disabled."""
    config = {CONF_MEMORY_ENABLED: False}
    provider = MemoryContextProvider(mock_hass, config, mock_memory)

    context = await provider.get_context("turn on the lights")

    assert context == ""
    mock_memory.recall.assert_not_called()


@pytest.mark.asyncio
async def test_get_context_no_memories_found(memory_context_provider, mock_memory):
    """Test get_context when no relevant memories are found."""
    mock_memory.recall.return_value = []

    context = await memory_context_provider.get_context("what's the weather?")

    assert context == ""
    mock_memory.recall.assert_called_once_with(
        query="what's the weather?",
        top_k=5,
    )


@pytest.mark.asyncio
async def test_get_context_with_memories(memory_context_provider, mock_memory):
    """Test get_context successfully retrieves and formats memories."""
    mock_memories = [
        make_record(
            "User prefers bedroom temperature at 68°F",
            memory_id="mem1",
            category="preference",
            importance=0.8,
        ),
        make_record(
            "Living room has smart lights",
            memory_id="mem2",
            category="fact",
            importance=0.6,
        ),
        make_record(
            "User usually wakes up at 7 AM",
            memory_id="mem3",
            category="context",
            importance=0.5,
        ),
    ]
    mock_memory.recall.return_value = mock_memories

    context = await memory_context_provider.get_context("set bedroom temperature")

    # Verify search was called with correct parameters
    mock_memory.recall.assert_called_once_with(
        query="set bedroom temperature",
        top_k=5,
    )

    # Verify context formatting
    assert "## Relevant Information from Past Conversations" in context
    assert "[Preference] User prefers bedroom temperature at 68°F" in context
    assert "[Fact] Living room has smart lights" in context
    assert "[Context] User usually wakes up at 7 AM" in context


@pytest.mark.asyncio
async def test_get_context_uses_config_parameters(mock_hass, mock_memory):
    """Test that get_context uses configured parameters."""
    config = {
        CONF_MEMORY_ENABLED: True,
        CONF_MEMORY_CONTEXT_TOP_K: 10,
        CONF_MEMORY_MIN_IMPORTANCE: 0.7,
    }
    provider = MemoryContextProvider(mock_hass, config, mock_memory)
    mock_memory.recall.return_value = []

    await provider.get_context("test query")

    # min_importance is NOT passed to recall: the contract has no importance
    # filter, and min_trust is a different axis. The provider filters instead.
    mock_memory.recall.assert_called_once_with(
        query="test query",
        top_k=10,
    )


@pytest.mark.asyncio
async def test_get_context_uses_defaults(mock_hass, mock_memory):
    """Test that get_context uses default values when not configured."""
    config = {}  # Empty config
    provider = MemoryContextProvider(mock_hass, config, mock_memory)
    mock_memory.recall.return_value = []

    await provider.get_context("test query")

    mock_memory.recall.assert_called_once_with(
        query="test query",
        top_k=DEFAULT_MEMORY_CONTEXT_TOP_K,
    )


@pytest.mark.asyncio
async def test_get_context_handles_search_error(memory_context_provider, mock_memory):
    """Test that get_context handles errors gracefully."""
    mock_memory.recall.side_effect = Exception("Database error")

    context = await memory_context_provider.get_context("test query")

    # Should return empty string on error
    assert context == ""


@pytest.mark.asyncio
async def test_format_memories_empty_list(memory_context_provider):
    """Test _format_memories with empty list."""
    result = memory_context_provider._format_memories([])

    assert result == ""


@pytest.mark.asyncio
async def test_format_memories_cannot_receive_missing_fields(memory_context_provider):
    """The contract makes "missing type/content" unrepresentable.

    This replaces a test that fed in dicts lacking `type` and `content` and
    checked the formatter defaulted them. MemoryRecord requires both, so the
    formatter can no longer be handed a memory without them -- the failure mode
    is gone rather than handled, which is why the old test is not just rewritten.
    """
    with pytest.raises(TypeError):
        MemoryRecord(id="mem1")  # type: ignore[call-arg]

    result = memory_context_provider._format_memories(
        [make_record("Test content", category="fact")]
    )
    assert "## Relevant Information from Past Conversations" in result
    assert "[Fact] Test content" in result


@pytest.mark.asyncio
async def test_format_memories_type_capitalization(memory_context_provider):
    """Test that memory types are properly capitalized."""
    memories = [
        make_record("Test 1", category="preference"),
        make_record("Test 2", category="fact"),
        make_record("Test 3", category="context"),
    ]

    result = memory_context_provider._format_memories(memories)

    assert "[Preference]" in result
    assert "[Fact]" in result
    assert "[Context]" in result


@pytest.mark.asyncio
async def test_get_context_with_conversation_id(memory_context_provider, mock_memory):
    """Test get_context accepts conversation_id parameter."""
    mock_memory.recall.return_value = []

    # conversation_id is accepted but not currently used in search
    context = await memory_context_provider.get_context(
        "test query",
        conversation_id="conv123",
    )

    assert context == ""
    # Verify search was called (conversation_id might be used in future)
    mock_memory.recall.assert_called_once()


@pytest.mark.asyncio
async def test_get_context_integration(memory_context_provider, mock_memory):
    """Test complete integration flow from query to formatted output."""
    mock_memories = [
        make_record(
            "Prefers lights dimmed at night",
            category="preference",
            importance=0.9,
        )
    ]
    mock_memory.recall.return_value = mock_memories

    context = await memory_context_provider.get_context(
        "turn on bedroom lights",
        conversation_id="test_conv",
    )

    # Verify full output structure
    assert context.startswith("## Relevant Information from Past Conversations\n\n")
    assert "- [Preference] Prefers lights dimmed at night\n" in context
    assert context.endswith("\n")


@pytest.mark.asyncio
async def test_get_context_filters_below_min_importance(mock_hass, mock_memory):
    """Low-importance memories are dropped, as before the contract.

    The filter moved out of the backend call and into the provider, because
    recall() has no importance filter and min_trust is not its equivalent --
    importance is salience, trust is epistemic weight. Behavior is unchanged.
    """
    config = {
        CONF_MEMORY_ENABLED: True,
        CONF_MEMORY_CONTEXT_TOP_K: 5,
        CONF_MEMORY_MIN_IMPORTANCE: 0.7,
    }
    provider = MemoryContextProvider(mock_hass, config, mock_memory)
    mock_memory.recall.return_value = [
        make_record("Salient enough", category="preference", importance=0.9),
        make_record("Too trivial to surface", category="fact", importance=0.2),
    ]

    context = await provider.get_context("test query")

    assert "Salient enough" in context
    assert "Too trivial to surface" not in context


@pytest.mark.asyncio
async def test_get_context_keeps_trustworthy_but_unremarkable_memories(mock_hass, mock_memory):
    """A fully trusted memory is not dropped for being unremarkable.

    Regression guard for the tempting shortcut of passing min_importance as
    min_trust: that would drop this record, which the resident stated outright.
    """
    config = {
        CONF_MEMORY_ENABLED: True,
        CONF_MEMORY_MIN_IMPORTANCE: 0.0,
    }
    provider = MemoryContextProvider(mock_hass, config, mock_memory)
    mock_memory.recall.return_value = [
        make_record(
            "Ana takes her pills at 8",
            category="fact",
            source="explicit_user",
            trust=1.0,
            importance=0.1,
        )
    ]

    context = await provider.get_context("pills")

    assert "Ana takes her pills at 8" in context
