"""Unit tests for memory tools."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.pepa_sensory_arm.exceptions import ToolExecutionError
from custom_components.pepa_sensory_arm.tools.memory_tools import (
    TOOL_RECALL_MEMORY,
    TOOL_STORE_MEMORY,
    RecallMemoryTool,
    StoreMemoryTool,
)

from .conftest import make_record


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    return MagicMock()


@pytest.fixture
def mock_memory():
    """Create a mock MemoryManager instance."""
    mock_manager = MagicMock()
    mock_manager.fast_track = AsyncMock()
    mock_manager.recall = AsyncMock()
    return mock_manager


@pytest.fixture
def store_memory_tool(mock_hass, mock_memory):
    """Create a StoreMemoryTool instance."""
    return StoreMemoryTool(mock_hass, mock_memory, conversation_id="test_conv")


@pytest.fixture
def recall_memory_tool(mock_hass, mock_memory):
    """Create a RecallMemoryTool instance."""
    return RecallMemoryTool(mock_hass, mock_memory)


class TestStoreMemoryTool:
    """Tests for StoreMemoryTool."""

    def test_tool_name(self, store_memory_tool):
        """Test that tool name is correct."""
        assert store_memory_tool.name == TOOL_STORE_MEMORY

    def test_tool_description(self, store_memory_tool):
        """Test that tool has a description."""
        description = store_memory_tool.description
        assert isinstance(description, str)
        assert len(description) > 0
        assert "store" in description.lower()

    def test_tool_parameters_schema(self, store_memory_tool):
        """Test that parameter schema is valid."""
        params = store_memory_tool.parameters

        assert params["type"] == "object"
        assert "content" in params["properties"]
        assert "memory_type" in params["properties"]
        assert "importance" in params["properties"]
        assert params["required"] == ["content"]

    def test_tool_openai_format(self, store_memory_tool):
        """Test tool definition in OpenAI format."""
        definition = store_memory_tool.to_openai_format()

        assert definition["type"] == "function"
        assert definition["function"]["name"] == TOOL_STORE_MEMORY
        assert "description" in definition["function"]
        assert "parameters" in definition["function"]

    @pytest.mark.asyncio
    async def test_execute_success(self, store_memory_tool, mock_memory):
        """Test successful memory storage."""
        mock_memory.fast_track.return_value = "mem_123"

        result = await store_memory_tool.execute(
            content="User prefers lights at 50% brightness",
            memory_type="preference",
            importance=0.8,
        )

        assert result["success"] is True
        assert "mem_123" in result["message"]

        # Verify memory was stored correctly
        # A tool write is the resident asking to be remembered: fast_track
        # forces source=explicit_user and trust=1.0, and importance -- which is
        # salience, not credibility -- rides in metadata.
        mock_memory.fast_track.assert_called_once_with(
            content="User prefers lights at 50% brightness",
            category="preference",
            conversation_id="test_conv",
            metadata={
                "importance": 0.8,
                "extraction_method": "manual",
                "tool": TOOL_STORE_MEMORY,
            },
        )

    @pytest.mark.asyncio
    async def test_execute_with_defaults(self, store_memory_tool, mock_memory):
        """Test execute with default parameters."""
        mock_memory.fast_track.return_value = "mem_456"

        result = await store_memory_tool.execute(
            content="Test fact",
        )

        assert result["success"] is True

        # Verify defaults were used
        mock_memory.fast_track.assert_called_once()
        call_kwargs = mock_memory.fast_track.call_args[1]
        assert call_kwargs["category"] == "fact"
        assert call_kwargs["metadata"]["importance"] == 0.5

    @pytest.mark.asyncio
    async def test_execute_missing_content(self, store_memory_tool, mock_memory):
        """Test execute fails when content is missing."""
        with pytest.raises(ToolExecutionError, match="Missing required parameter: content"):
            await store_memory_tool.execute()

    @pytest.mark.asyncio
    async def test_execute_empty_content(self, store_memory_tool, mock_memory):
        """Test execute fails when content is empty."""
        with pytest.raises(ToolExecutionError, match="Missing required parameter: content"):
            await store_memory_tool.execute(content="")

    @pytest.mark.asyncio
    async def test_execute_memory_manager_error(self, store_memory_tool, mock_memory):
        """Test execute handles memory manager errors."""
        mock_memory.fast_track.side_effect = Exception("Database error")

        with pytest.raises(ToolExecutionError, match="Failed to store memory"):
            await store_memory_tool.execute(content="Test")


class TestRecallMemoryTool:
    """Tests for RecallMemoryTool."""

    def test_tool_name(self, recall_memory_tool):
        """Test that tool name is correct."""
        assert recall_memory_tool.name == TOOL_RECALL_MEMORY

    def test_tool_description(self, recall_memory_tool):
        """Test that tool has a description."""
        description = recall_memory_tool.description
        assert isinstance(description, str)
        assert len(description) > 0
        assert "search" in description.lower() or "recall" in description.lower()

    def test_tool_parameters_schema(self, recall_memory_tool):
        """Test that parameter schema is valid."""
        params = recall_memory_tool.parameters

        assert params["type"] == "object"
        assert "query" in params["properties"]
        assert "limit" in params["properties"]
        assert params["required"] == ["query"]

    def test_tool_openai_format(self, recall_memory_tool):
        """Test tool definition in OpenAI format."""
        definition = recall_memory_tool.to_openai_format()

        assert definition["type"] == "function"
        assert definition["function"]["name"] == TOOL_RECALL_MEMORY
        assert "description" in definition["function"]
        assert "parameters" in definition["function"]

    @pytest.mark.asyncio
    async def test_execute_success(self, recall_memory_tool, mock_memory):
        """Test successful memory recall."""
        mock_memories = [
            make_record("Prefers bedroom at 68°F", category="preference", importance=0.8),
            make_record("Has 3 bedrooms", category="fact", importance=0.6),
        ]
        mock_memory.recall.return_value = mock_memories

        result = await recall_memory_tool.execute(
            query="bedroom temperature",
            limit=5,
        )

        assert result["success"] is True
        assert "Found 2 relevant memories" in result["message"]
        assert "[Preference] Prefers bedroom at 68°F" in result["message"]
        assert "[Fact] Has 3 bedrooms" in result["message"]

        # Verify search parameters
        mock_memory.recall.assert_called_once_with(
            query="bedroom temperature",
            top_k=5,
            min_trust=0.0,
        )

    @pytest.mark.asyncio
    async def test_execute_with_defaults(self, recall_memory_tool, mock_memory):
        """Test execute with default limit."""
        mock_memory.recall.return_value = []

        result = await recall_memory_tool.execute(query="test")

        # Verify default limit was used
        mock_memory.recall.assert_called_once()
        call_kwargs = mock_memory.recall.call_args[1]
        assert call_kwargs["top_k"] == 5
        # Verify result structure
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_execute_no_memories_found(self, recall_memory_tool, mock_memory):
        """Test execute when no memories are found."""
        mock_memory.recall.return_value = []

        result = await recall_memory_tool.execute(query="nonexistent")

        assert result["success"] is True
        assert "No relevant memories found" in result["message"]

    @pytest.mark.asyncio
    async def test_execute_missing_query(self, recall_memory_tool, mock_memory):
        """Test execute fails when query is missing."""
        with pytest.raises(ToolExecutionError, match="Missing required parameter: query"):
            await recall_memory_tool.execute()

    @pytest.mark.asyncio
    async def test_execute_empty_query(self, recall_memory_tool, mock_memory):
        """Test execute fails when query is empty."""
        with pytest.raises(ToolExecutionError, match="Missing required parameter: query"):
            await recall_memory_tool.execute(query="")

    @pytest.mark.asyncio
    async def test_execute_memory_manager_error(self, recall_memory_tool, mock_memory):
        """Test execute handles memory manager errors."""
        mock_memory.recall.side_effect = Exception("Database error")

        with pytest.raises(ToolExecutionError, match="Failed to recall memories"):
            await recall_memory_tool.execute(query="test")

    @pytest.mark.asyncio
    async def test_execute_formats_trust_and_source(self, recall_memory_tool, mock_memory):
        """The LLM is told what each recollection is worth and where it came from.

        This replaces a test asserting importance was formatted into the result.
        The change is deliberate (spec §5): importance is salience and is the
        backend's own bookkeeping, while trust and source are what let the model
        hedge on a shaky inference instead of asserting it. Retrieval is not
        endorsement, and the tool output now says so.
        """
        mock_memory.recall.return_value = [
            make_record("Test memory", category="fact", trust=0.5, source="behavioral"),
        ]

        result = await recall_memory_tool.execute(query="test")

        assert "(trust: 0.50, source: behavioral)" in result["message"]
        assert "importance" not in result["message"]

    @pytest.mark.asyncio
    async def test_execute_distinguishes_stated_from_inferred(
        self, recall_memory_tool, mock_memory
    ):
        """A user-stated fact and an inference are visibly different to the model."""
        mock_memory.recall.return_value = [
            make_record("Ana takes pills at 8", source="explicit_user", trust=1.0),
            make_record("Ana probably dislikes cold", source="behavioral", trust=0.5),
        ]

        result = await recall_memory_tool.execute(query="Ana")

        assert "(trust: 1.00, source: explicit_user)" in result["message"]
        assert "(trust: 0.50, source: behavioral)" in result["message"]

    @pytest.mark.asyncio
    async def test_recall_results_cannot_have_missing_fields(self, recall_memory_tool, mock_memory):
        """The contract makes "memory without type/content" unrepresentable.

        This replaces a test that fed the tool dicts missing `type` and
        `content`. MemoryRecord requires both, so the tool can no longer be
        handed one -- the failure mode is gone rather than defended against.
        """
        mock_memory.recall.return_value = [make_record("Complete memory", category="preference")]

        result = await recall_memory_tool.execute(query="test")

        assert result["success"] is True
        assert "[Preference] Complete memory" in result["message"]

    @pytest.mark.asyncio
    async def test_store_and_recall_workflow(self, mock_hass, mock_memory):
        """Test complete workflow of storing and recalling a memory."""
        # Store a memory
        store_tool = StoreMemoryTool(mock_hass, mock_memory, "conv_123")
        mock_memory.fast_track.return_value = "mem_xyz"

        store_result = await store_tool.execute(
            content="User's favorite color is blue",
            memory_type="preference",
            importance=0.7,
        )

        assert store_result["success"] is True

        # Recall the memory
        recall_tool = RecallMemoryTool(mock_hass, mock_memory)
        mock_memory.recall.return_value = [
            make_record(
                "User's favorite color is blue",
                category="preference",
                source="explicit_user",
                trust=1.0,
                importance=0.7,
            )
        ]

        recall_result = await recall_tool.execute(query="favorite color")

        assert recall_result["success"] is True
        assert "favorite color is blue" in recall_result["message"]
        # Stored via the tool, so it comes back as the resident's own word.
        assert "source: explicit_user" in recall_result["message"]

    def test_both_tools_registered_correctly(self, mock_hass, mock_memory):
        """Test that both tools can be instantiated and have correct names."""
        store_tool = StoreMemoryTool(mock_hass, mock_memory)
        recall_tool = RecallMemoryTool(mock_hass, mock_memory)

        assert store_tool.name == TOOL_STORE_MEMORY
        assert recall_tool.name == TOOL_RECALL_MEMORY
        assert store_tool.name != recall_tool.name
