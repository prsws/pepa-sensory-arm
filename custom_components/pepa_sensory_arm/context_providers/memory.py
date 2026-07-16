"""Memory context provider for Pepa Sensory Arm.

This module provides the MemoryContextProvider class that retrieves
relevant memories based on user input using semantic search.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant

from ..const import (
    CONF_MEMORY_CONTEXT_TOP_K,
    CONF_MEMORY_ENABLED,
    CONF_MEMORY_MIN_IMPORTANCE,
    DEFAULT_MEMORY_CONTEXT_TOP_K,
    DEFAULT_MEMORY_ENABLED,
    DEFAULT_MEMORY_MIN_IMPORTANCE,
)
from .base import ContextProvider

if TYPE_CHECKING:
    from ..memory_interface import MemoryInterface, MemoryRecord

_LOGGER = logging.getLogger(__name__)


class MemoryContextProvider(ContextProvider):
    """Provide relevant memories as conversation context.

    This context provider searches stored memories for information
    relevant to the current user input and formats them for injection
    into the LLM's system prompt.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        config: dict[str, Any],
        memory: MemoryInterface,
    ) -> None:
        """Initialize memory context provider.

        Args:
            hass: Home Assistant instance
            config: Configuration dictionary
            memory: The memory backend, behind the contract
        """
        super().__init__(hass, config)
        self.memory = memory

    async def get_context(
        self,
        user_input: str,
        conversation_id: str | None = None,
    ) -> str:
        """Get relevant memories for this conversation.

        Uses semantic search to find memories related to user input.

        Args:
            user_input: User's message/query
            conversation_id: Optional conversation ID (unused for now)

        Returns:
            Formatted memory context string
        """
        # Check if memory is enabled
        if not self.config.get(CONF_MEMORY_ENABLED, DEFAULT_MEMORY_ENABLED):
            return ""

        try:
            # Search for relevant memories
            top_k = self.config.get(CONF_MEMORY_CONTEXT_TOP_K, DEFAULT_MEMORY_CONTEXT_TOP_K)
            min_importance = self.config.get(
                CONF_MEMORY_MIN_IMPORTANCE, DEFAULT_MEMORY_MIN_IMPORTANCE
            )

            relevant_memories = await self.memory.recall(
                query=user_input,
                top_k=top_k,
            )

            # Importance filtering happens here rather than in recall() because
            # the contract has no importance filter, and min_trust is NOT its
            # equivalent: importance is salience, trust is epistemic weight.
            # Passing min_importance as min_trust would silently start dropping
            # trustworthy-but-unremarkable memories. Filtering post-recall keeps
            # P1's composed context byte-identical.
            if min_importance > 0.0:
                relevant_memories = [
                    record
                    for record in relevant_memories
                    if record.metadata.get("importance", 0.0) >= min_importance
                ]

            if not relevant_memories:
                self._logger.debug("No relevant memories found for user input")
                return ""

            # Format memories for LLM context
            memory_context = self._format_memories(relevant_memories)

            self._logger.debug(
                "Retrieved %d relevant memories for context",
                len(relevant_memories),
            )

            return memory_context

        except Exception as err:
            self._logger.error("Error retrieving memory context: %s", err)
            return ""

    def _format_memories(self, memories: list[MemoryRecord]) -> str:
        """Format memories for LLM context injection.

        Args:
            memories: Records to format

        Returns:
            Formatted context string
        """
        if not memories:
            return ""

        context = "## Relevant Information from Past Conversations\n\n"

        for record in memories:
            # Shape is frozen: P1's composed context must not change. Trust and
            # source are deliberately NOT surfaced here -- this text lands in the
            # cache-unstable region of every prompt, and widening it is a P1
            # decision, not a side effect of P2.
            context += f"- [{record.category.title()}] {record.content}\n"

        context += "\n"
        return context
