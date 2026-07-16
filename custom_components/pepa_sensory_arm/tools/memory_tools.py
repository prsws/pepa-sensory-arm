"""Memory management tools for Pepa Sensory Arm.

This module provides tools for the LLM to manually store and recall memories.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant

from ..exceptions import ToolExecutionError
from .registry import BaseTool

if TYPE_CHECKING:
    from ..memory_interface import MemoryInterface

_LOGGER = logging.getLogger(__name__)

# Tool name constants
TOOL_STORE_MEMORY = "store_memory"
TOOL_RECALL_MEMORY = "recall_memory"


class StoreMemoryTool(BaseTool):
    """Tool for manually storing memories.

    Allows the LLM to explicitly store important facts, preferences,
    or contextual information about the user or their home.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        memory: MemoryInterface,
        conversation_id: str | None = None,
    ) -> None:
        """Initialize the store memory tool.

        Args:
            hass: Home Assistant instance
            memory: The memory backend, behind the contract
            conversation_id: Optional conversation ID for context
        """
        super().__init__(hass)
        self._memory = memory
        self._conversation_id = conversation_id

    @property
    def name(self) -> str:
        """Return the tool name."""
        return TOOL_STORE_MEMORY

    @property
    def description(self) -> str:
        """Return the tool description."""
        return (
            "Store an important fact, preference, or piece of information "
            "for future conversations. Use this when the user shares information "
            "that should be remembered (preferences, facts about their home, etc.). "
            "Do NOT store temporary states like 'light is on' - only persistent information."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        """Return the tool parameter schema."""
        return {
            "type": "object",
            "properties": {
                "memory_type": {
                    "type": "string",
                    "enum": ["fact", "preference", "context", "event"],
                    "description": (
                        "Type of memory: 'fact' for concrete information, "
                        "'preference' for user preferences, 'context' for background info, "
                        "'event' for time-sensitive actions or state changes"
                    ),
                },
                "content": {
                    "type": "string",
                    "description": "Clear, concise description of what to remember (1-2 sentences)",
                },
                "importance": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "description": "Importance score from 0.0 to 1.0 (optional, default 0.5)",
                },
            },
            "required": ["content"],
        }

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """Execute the store_memory tool.

        Args:
            **kwargs: Tool parameters

        Returns:
            Result dictionary with success status and message

        Raises:
            ToolExecutionError: If memory storage fails
        """
        try:
            content = kwargs.get("content")
            if not content:
                raise ToolExecutionError("Missing required parameter: content")

            memory_type = kwargs.get("memory_type", "fact")
            importance = kwargs.get("importance", 0.5)

            # The "remember this" path: a tool write is the resident asking to
            # be remembered, so it goes through fast_track -- source is forced to
            # explicit_user, trust to 1.0, and it is durable before we return.
            # Trust is deliberately not exposed to the LLM as a parameter: a
            # model that can set its own credibility has no credibility.
            memory_id = await self._memory.fast_track(
                content=content,
                category=memory_type,
                conversation_id=self._conversation_id,
                metadata={
                    "importance": importance,
                    "extraction_method": "manual",
                    "tool": TOOL_STORE_MEMORY,
                },
            )

            _LOGGER.info(
                "Stored memory via tool: type=%s, importance=%.2f, id=%s",
                memory_type,
                importance,
                memory_id,
            )

            return {
                "success": True,
                "message": f"Memory stored successfully (ID: {memory_id})",
            }

        except Exception as err:
            _LOGGER.error("Error executing store_memory tool: %s", err)
            raise ToolExecutionError(f"Failed to store memory: {err}") from err


class RecallMemoryTool(BaseTool):
    """Tool for searching and recalling memories.

    Allows the LLM to search for relevant memories based on semantic
    similarity to a query.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        memory: MemoryInterface,
    ) -> None:
        """Initialize the recall memory tool.

        Args:
            hass: Home Assistant instance
            memory: The memory backend, behind the contract
        """
        super().__init__(hass)
        self._memory = memory

    @property
    def name(self) -> str:
        """Return the tool name."""
        return TOOL_RECALL_MEMORY

    @property
    def description(self) -> str:
        """Return the tool description."""
        return (
            "Search stored memories for relevant information. "
            "Use this to check if you already know something about the user's "
            "preferences, home setup, or past conversations."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        """Return the tool parameter schema."""
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What to search for in memories",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 20,
                    "description": "Maximum number of memories to retrieve (default 5)",
                },
            },
            "required": ["query"],
        }

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """Execute the recall_memory tool.

        Args:
            **kwargs: Tool parameters

        Returns:
            Result dictionary with success status and found memories

        Raises:
            ToolExecutionError: If memory search fails
        """
        try:
            query = kwargs.get("query")
            if not query:
                raise ToolExecutionError("Missing required parameter: query")

            limit = kwargs.get("limit", 5)

            # Recall, not search: every record arrives carrying its own weight.
            memories = await self._memory.recall(
                query=query,
                top_k=limit,
                min_trust=0.0,  # Include all memories for explicit recall
            )

            if not memories:
                return {
                    "success": True,
                    "message": "No relevant memories found.",
                }

            # Format for LLM consumption, trust and provenance included.
            # Retrieval is not endorsement -- the model is told how much each
            # recollection is worth and where it came from, so it can hedge on a
            # 0.5-trust inference instead of asserting it as fact.
            result = f"Found {len(memories)} relevant memories:\n\n"
            for i, record in enumerate(memories, 1):
                result += (
                    f"{i}. [{record.category.title()}] {record.content} "
                    f"(trust: {record.trust:.2f}, source: {record.source})\n"
                )

            _LOGGER.info(
                "Recalled %d memories via tool for query: %s",
                len(memories),
                query,
            )

            return {
                "success": True,
                "message": result.strip(),
            }

        except Exception as err:
            _LOGGER.error("Error executing recall_memory tool: %s", err)
            raise ToolExecutionError(f"Failed to recall memories: {err}") from err
