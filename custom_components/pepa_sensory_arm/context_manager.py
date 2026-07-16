"""Context manager for the Pepa Sensory Arm component.

This module provides the ContextManager class that orchestrates context injection
strategies for LLM conversations. It manages different context providers (direct
entity injection, vector DB retrieval) and handles context formatting, optimization,
and caching.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from homeassistant.core import HomeAssistant

from .const import (
    CONF_ADDITIONAL_COLLECTIONS,
    CONF_CONTEXT_FORMAT,
    CONF_CONTEXT_MODE,
    CONF_DIRECT_ENTITIES,
    CONF_PROMPT_INCLUDE_LABELS,
    CONF_PROMPT_USE_DEFAULT,
    CONTEXT_MODE_DIRECT,
    CONTEXT_MODE_VECTOR_DB,
    DEFAULT_CONTEXT_FORMAT,
    DEFAULT_CONTEXT_MODE,
    DEFAULT_PROMPT_INCLUDE_LABELS,
    DEFAULT_PROMPT_USE_DEFAULT,
    EVENT_CONTEXT_INJECTED,
    EVENT_CONTEXT_OPTIMIZED,
    MAX_CONTEXT_TOKENS,
    TOKEN_WARNING_THRESHOLD,
)
from .context_providers import ContextProvider, DirectContextProvider
from .exceptions import ContextInjectionError, TokenLimitExceeded

_LOGGER = logging.getLogger(__name__)


class ContextManager:
    """Manager for context injection into LLM conversations.

    The ContextManager orchestrates different context providers and provides
    a unified interface for retrieving, formatting, and optimizing entity
    context for LLM prompts.

    Attributes:
        hass: Home Assistant instance
        config: Configuration dictionary
        provider: Current context provider instance
        cache: Optional context cache with TTL
        emit_events: Whether to fire Home Assistant events
    """

    def __init__(
        self,
        hass: HomeAssistant,
        config: dict[str, Any],
    ) -> None:
        """Initialize the context manager.

        Args:
            hass: Home Assistant instance
            config: Configuration dictionary containing context settings

        Example:
            config = {
                "mode": "direct",
                "format": "json",
                "entities": [...],
                "cache_enabled": True,
                "cache_ttl": 60,
                "emit_events": True,
            }
        """
        self.hass = hass
        self.config = config
        self._provider: ContextProvider | None = None
        self._memory_provider: ContextProvider | None = None
        self._retrieval_provider: ContextProvider | None = None
        self._cache: dict[str, Any] = {}
        self._cache_timestamps: dict[str, float] = {}
        self._cache_enabled = config.get("cache_enabled", False)
        self._cache_ttl = config.get("cache_ttl", 60)
        self._emit_events = config.get("emit_events", True)
        self._max_context_tokens = config.get("max_context_tokens", MAX_CONTEXT_TOKENS)
        self._max_cache_size = config.get("max_cache_size", 128)

        # Initialize default provider
        self._initialize_provider()

    def _get_mode_from_config(self, config: dict[str, Any] | None = None) -> str:
        """Get mode from config, supporting both CONF_CONTEXT_MODE and 'mode' keys.

        Args:
            config: Config dict to check, or None to use self.config

        Returns:
            The mode value, or DEFAULT_CONTEXT_MODE if not found
        """
        cfg = config if config is not None else self.config
        if CONF_CONTEXT_MODE in cfg:
            mode = cfg[CONF_CONTEXT_MODE]
            return str(mode) if mode is not None else DEFAULT_CONTEXT_MODE
        elif "mode" in cfg:
            mode = cfg["mode"]
            return str(mode) if mode is not None else DEFAULT_CONTEXT_MODE
        else:
            return DEFAULT_CONTEXT_MODE

    def _use_default_prompt(self) -> bool:
        """Whether the built-in default prompt (HEAD/TAIL) is in use.

        Drives context composition: in default prompt mode the device picture
        comes from the prompt TAIL's CSV tables, so no entity provider is
        created and context is composed from memory + retrieval only.
        """
        return bool(self.config.get(CONF_PROMPT_USE_DEFAULT, DEFAULT_PROMPT_USE_DEFAULT))

    def _initialize_provider(self) -> None:
        """Initialize the context providers based on configuration.

        Raises:
            ContextInjectionError: If provider initialization fails
        """
        # The retrieval provider (additional collections) serves both prompt
        # modes; a failure to create it degrades to an empty retrieval leg.
        # With no additional collections configured there is nothing to
        # retrieve, so no provider is created at all.
        self._retrieval_provider = None
        if self.config.get(CONF_ADDITIONAL_COLLECTIONS):
            try:
                from .context_providers.retrieval import RetrievalContextProvider

                self._retrieval_provider = RetrievalContextProvider(self.hass, self.config)
            except Exception as error:
                _LOGGER.warning("Failed to initialize retrieval context provider: %s", error)
                self._retrieval_provider = None

        if self._use_default_prompt():
            # Default prompt mode: the entity picture lives in the prompt
            # TAIL's device tables — no entity provider is instantiated.
            self._provider = None
            _LOGGER.info("Default prompt mode: composing context from memory + retrieval providers")
            return

        # During initialization, use standard config key (CONF_CONTEXT_MODE)
        # The "mode" fallback is only for runtime config access
        mode = self.config.get(CONF_CONTEXT_MODE, DEFAULT_CONTEXT_MODE)

        try:
            if mode == CONTEXT_MODE_DIRECT:
                self._provider = self._create_direct_provider()
            elif mode == CONTEXT_MODE_VECTOR_DB:
                self._provider = self._create_vector_db_provider()
            else:
                _LOGGER.error("Invalid context mode: %s, using direct mode", mode)
                self._provider = self._create_direct_provider()

            _LOGGER.info("Initialized context provider: %s", self._provider.__class__.__name__)
        except Exception as error:
            if mode == CONTEXT_MODE_VECTOR_DB:
                _LOGGER.error(
                    "Failed to initialize vector DB context provider: %s. "
                    "Falling back to direct context mode.",
                    error,
                    exc_info=True,
                )
                self._provider = self._create_direct_provider()
                _LOGGER.info(
                    "Initialized fallback context provider: %s",
                    self._provider.__class__.__name__,
                )
            else:
                _LOGGER.error("Failed to initialize context provider: %s", error, exc_info=True)
                raise ContextInjectionError(
                    f"Failed to initialize context provider: {error}"
                ) from error

    def _create_direct_provider(self) -> DirectContextProvider:
        """Create and configure a direct context provider.

        Returns:
            Configured DirectContextProvider instance
        """
        provider_config = {
            "entities": self.config.get(CONF_DIRECT_ENTITIES, []),
            "format": self.config.get(CONF_CONTEXT_FORMAT, DEFAULT_CONTEXT_FORMAT),
            "include_labels": self.config.get(
                CONF_PROMPT_INCLUDE_LABELS, DEFAULT_PROMPT_INCLUDE_LABELS
            ),
        }
        return DirectContextProvider(self.hass, provider_config)

    def _create_vector_db_provider(self) -> ContextProvider:
        """Create and configure a vector DB context provider.

        Returns:
            Configured VectorDBContextProvider instance
        """
        from .context_providers.vector_db import VectorDBContextProvider

        # Pass all config to the vector DB provider
        return VectorDBContextProvider(self.hass, self.config)

    def set_provider(self, provider: ContextProvider) -> None:
        """Set a custom context provider.

        This allows external code to inject a custom provider implementation,
        useful for testing or advanced use cases.

        Args:
            provider: The context provider to use

        Example:
            >>> custom_provider = MyCustomProvider(hass, config)
            >>> context_manager.set_provider(custom_provider)
        """
        self._provider = provider
        _LOGGER.info("Context provider set to: %s", provider.__class__.__name__)
        # Clear cache when provider changes
        self._clear_cache()

    def set_memory_provider(
        self,
        memory_manager: Any,
    ) -> None:
        """Set the memory context provider.

        Initializes a MemoryContextProvider with the given memory manager.

        Args:
            memory_manager: MemoryManager instance
        """
        try:
            from .context_providers.memory import MemoryContextProvider

            self._memory_provider = MemoryContextProvider(
                hass=self.hass,
                config=self.config,
                memory_manager=memory_manager,
            )
            _LOGGER.info("Memory context provider initialized")
        except Exception as err:
            _LOGGER.error("Failed to initialize memory provider: %s", err)
            self._memory_provider = None

    async def get_context(
        self,
        user_input: str,
        conversation_id: str | None = None,
    ) -> str:
        """Get context from the current provider.

        Retrieves entity context relevant to the user's input. May use
        caching if enabled.

        Args:
            user_input: The user's query or message
            conversation_id: Optional conversation ID for tracking

        Returns:
            Raw context string from the provider

        Raises:
            ContextInjectionError: If context retrieval fails
        """
        use_default = self._use_default_prompt()

        if not use_default and self._provider is None:
            raise ContextInjectionError("No context provider configured")

        # Check cache first
        if self._cache_enabled:
            cached_context = self._get_cached_context(user_input)
            if cached_context is not None:
                _LOGGER.debug("Returning cached context for input")
                return cached_context

        try:
            if use_default:
                context = await self._get_context_default(user_input)
            else:
                context = await self._get_context_replacement(user_input)

            # Cache the result
            if self._cache_enabled:
                self._cache_context(user_input, context)

            _LOGGER.debug("Retrieved context: %d characters", len(context))

            return context

        except ContextInjectionError:
            raise
        except Exception as error:
            _LOGGER.error("Failed to get context: %s", error, exc_info=True)
            raise ContextInjectionError(f"Failed to retrieve context: {error}") from error

    async def _get_context_default(self, user_input: str) -> str:
        """Compose context in default prompt mode: memory + retrieval only.

        Each leg degrades to an empty string on failure — never raises and
        never emits the entity-provider sentinel strings.
        """
        legs: list[tuple[str, ContextProvider]] = []
        if self._memory_provider is not None:
            legs.append(("memory", self._memory_provider))
        if self._retrieval_provider is not None:
            legs.append(("retrieval", self._retrieval_provider))

        if not legs:
            return ""

        results = await asyncio.gather(
            *(provider.get_context(user_input) for _, provider in legs),
            return_exceptions=True,
        )

        pieces: list[str] = []
        for (name, _), result in zip(legs, results):
            if isinstance(result, BaseException):
                _LOGGER.warning("Failed to get %s context: %s", name, result)
            elif result:
                pieces.append(result)

        return "\n".join(pieces)

    async def _get_context_replacement(self, user_input: str) -> str:
        """Compose context in replacement prompt mode.

        Preserves the legacy entity + memory merge (including the sentinel
        replacement logic), with the retrieval leg appended when non-empty.
        """
        assert self._provider is not None  # Guarded by get_context

        if self._memory_provider is None and self._retrieval_provider is None:
            # No auxiliary providers, just get entity context
            return await self._provider.get_context(user_input)

        # Parallel execution using asyncio.gather
        tasks = [self._provider.get_context(user_input)]
        memory_index = None
        retrieval_index = None
        if self._memory_provider is not None:
            memory_index = len(tasks)
            tasks.append(self._memory_provider.get_context(user_input))
        if self._retrieval_provider is not None:
            retrieval_index = len(tasks)
            tasks.append(self._retrieval_provider.get_context(user_input))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle entity context result
        if isinstance(results[0], BaseException):
            _LOGGER.error("Failed to get entity context: %s", results[0])
            raise ContextInjectionError(
                f"Failed to retrieve entity context: {results[0]}"
            ) from results[0]
        context = results[0]

        # Handle memory context result
        if memory_index is not None:
            memory_result = results[memory_index]
            if isinstance(memory_result, BaseException):
                _LOGGER.warning("Failed to get memory context: %s", memory_result)
                # Continue without memory context
            elif memory_result:
                # Check if entity context is a "no context" message
                # If so, replace it entirely with memory context
                no_context_messages = [
                    "No relevant context found.",
                    "No relevant context found",
                    "[Fallback mode - Vector DB unavailable]",
                ]
                if any(msg in context for msg in no_context_messages):
                    # Replace unhelpful entity context with memory context
                    context = memory_result
                    _LOGGER.debug("Replaced empty entity context with memory context")
                else:
                    # Combine entity and memory context
                    context = f"{context}\n{memory_result}"
                    _LOGGER.debug("Added memory context to entity context")

        # Handle retrieval (additional collections) context result
        if retrieval_index is not None:
            retrieval_result = results[retrieval_index]
            if isinstance(retrieval_result, BaseException):
                _LOGGER.warning("Failed to get retrieval context: %s", retrieval_result)
            elif retrieval_result:
                retrieval_context = retrieval_result
                context = f"{context}\n{retrieval_context}" if context else retrieval_context
                _LOGGER.debug("Added retrieval context")

        return context

    async def get_formatted_context(
        self,
        user_input: str,
        conversation_id: str | None = None,
        metrics: dict[str, Any] | None = None,
    ) -> str:
        """Get context formatted and optimized for LLM injection.

        This method retrieves context, optimizes it for token limits,
        and fires events if configured.

        Args:
            user_input: The user's query or message
            conversation_id: Optional conversation ID for event tracking
            metrics: Optional metrics dictionary to populate

        Returns:
            Formatted and optimized context string ready for LLM

        Raises:
            ContextInjectionError: If context retrieval or formatting fails
            TokenLimitExceeded: If context cannot be reduced to fit limits
        """
        # Get raw context
        context = await self.get_context(user_input, conversation_id)

        # Store original context size for metrics
        original_tokens = len(context) // 4

        # Optimize context size
        optimized_context = self._optimize_context_size(context)

        # Estimate token count (rough approximation: ~4 chars per token)
        estimated_tokens = len(optimized_context) // 4

        # Populate metrics if provided
        if metrics is not None and "context" not in metrics:
            metrics["context"] = {
                "mode": self._get_composition_mode(),
                "original_tokens": original_tokens,
                "optimized_tokens": estimated_tokens,
                "compression_ratio": round(
                    estimated_tokens / original_tokens if original_tokens > 0 else 1.0,
                    3,
                ),
            }

        # Check if we're approaching token limits
        if estimated_tokens > self._max_context_tokens:
            _LOGGER.error(
                "Context size %d tokens exceeds maximum %d tokens",
                estimated_tokens,
                self._max_context_tokens,
            )
            raise TokenLimitExceeded(
                f"Context size {estimated_tokens} tokens exceeds limit "
                f"{self._max_context_tokens}. To reduce context size: "
                f"decrease 'Max Messages' in History Settings, "
                f"lower 'Top K' in Vector DB Settings, "
                f"or increase 'Max Context Tokens' in Context Settings."
            )

        # Warn if approaching limit
        warning_threshold = int(self._max_context_tokens * TOKEN_WARNING_THRESHOLD)
        if estimated_tokens > warning_threshold:
            _LOGGER.warning(
                "Context size %d tokens is approaching limit of %d tokens (%d%%)",
                estimated_tokens,
                self._max_context_tokens,
                int((estimated_tokens / self._max_context_tokens) * 100),
            )

        # Fire event if enabled
        if self._emit_events:
            await self._fire_context_injected_event(
                conversation_id=conversation_id,
                token_count=estimated_tokens,
                user_input=user_input,
            )

        _LOGGER.debug(
            "Formatted context ready: %d characters (~%d tokens)",
            len(optimized_context),
            estimated_tokens,
        )

        return optimized_context

    def _optimize_context_size(self, context: str) -> str:
        """Optimize context size to stay within token limits.

        This method attempts to reduce context size by:
        1. Removing excessive whitespace
        2. Truncating if necessary (with warning)

        Args:
            context: Raw context string

        Returns:
            Optimized context string
        """
        original_length = len(context)
        original_tokens = original_length // 4  # Rough estimate

        # Remove excessive whitespace and normalize
        optimized = " ".join(context.split())

        # Check if truncation is needed
        max_chars = self._max_context_tokens * 4  # Rough char-to-token ratio
        was_truncated = False
        if len(optimized) > max_chars:
            _LOGGER.warning("Context truncated from %d to %d characters", len(optimized), max_chars)
            optimized = optimized[:max_chars] + "... [truncated]"
            was_truncated = True

        optimized_tokens = len(optimized) // 4
        compression_ratio = len(optimized) / original_length if original_length > 0 else 1.0

        # Fire optimization event if context was changed
        if was_truncated or len(optimized) < original_length:
            if self._emit_events:
                try:
                    self.hass.bus.async_fire(
                        EVENT_CONTEXT_OPTIMIZED,
                        {
                            "original_tokens": original_tokens,
                            "optimized_tokens": optimized_tokens,
                            "compression_ratio": round(compression_ratio, 3),
                            "was_truncated": was_truncated,
                            "original_size_bytes": original_length,
                            "optimized_size_bytes": len(optimized),
                        },
                    )
                    _LOGGER.debug(
                        "Context optimized: %d -> %d tokens (ratio: %.2f)",
                        original_tokens,
                        optimized_tokens,
                        compression_ratio,
                    )
                except Exception as err:
                    _LOGGER.warning("Failed to fire context optimized event: %s", err)

        return optimized

    def _get_cached_context(self, user_input: str) -> str | None:
        """Get cached context if available and not expired.

        Args:
            user_input: The user input to use as cache key

        Returns:
            Cached context string or None if not cached or expired
        """
        # Proactively evict all expired entries
        self._evict_expired_cache_entries()

        cache_key = self._generate_cache_key(user_input)

        if cache_key not in self._cache:
            return None

        _LOGGER.debug(
            "Cache hit (age: %.1fs)", time.time() - self._cache_timestamps.get(cache_key, 0)
        )
        cached = self._cache[cache_key]
        return str(cached) if cached is not None else None

    def _cache_context(self, user_input: str, context: str) -> None:
        """Cache context with current timestamp.

        Args:
            user_input: The user input to use as cache key
            context: The context to cache
        """
        cache_key = self._generate_cache_key(user_input)
        self._cache[cache_key] = context
        self._cache_timestamps[cache_key] = time.time()

        # Evict expired and enforce size limit
        self._evict_expired_cache_entries()
        self._enforce_cache_size_limit()

        _LOGGER.debug("Cached context for key (cache size: %d)", len(self._cache))

    def _evict_expired_cache_entries(self) -> int:
        """Remove all expired cache entries.

        Returns:
            Number of entries evicted
        """
        now = time.time()
        expired_keys = [
            key for key, ts in self._cache_timestamps.items() if now - ts > self._cache_ttl
        ]
        for key in expired_keys:
            del self._cache[key]
            del self._cache_timestamps[key]
        if expired_keys:
            _LOGGER.debug("Evicted %d expired cache entries", len(expired_keys))
        return len(expired_keys)

    def _enforce_cache_size_limit(self) -> None:
        """Evict oldest entries if cache exceeds max size."""
        if len(self._cache) <= self._max_cache_size:
            return

        sorted_keys = sorted(
            self._cache_timestamps.keys(),
            key=lambda k: self._cache_timestamps[k],
        )
        to_evict = len(self._cache) - self._max_cache_size
        for key in sorted_keys[:to_evict]:
            del self._cache[key]
            del self._cache_timestamps[key]
        _LOGGER.debug("Evicted %d entries to enforce cache size limit", to_evict)

    def _generate_cache_key(self, user_input: str) -> str:
        """Generate a cache key from user input.

        For direct mode, the cache key is constant since context doesn't
        change based on input. For vector DB mode, the input matters.

        Args:
            user_input: The user input

        Returns:
            Cache key string
        """
        mode = self._get_mode_from_config()

        if not self._use_default_prompt() and mode == CONTEXT_MODE_DIRECT:
            # Direct mode always returns same entities
            return "direct_context"
        else:
            # Default mode (memory + retrieval) and vector DB mode are input-specific
            import hashlib

            return hashlib.md5(user_input.encode()).hexdigest()

    def _clear_cache(self) -> None:
        """Clear all cached context."""
        self._cache.clear()
        self._cache_timestamps.clear()
        _LOGGER.debug("Context cache cleared")

    async def _fire_context_injected_event(
        self,
        conversation_id: str | None,
        token_count: int,
        user_input: str,
    ) -> None:
        """Fire pepa_sensory_arm.context.injected event.

        Args:
            conversation_id: Conversation identifier
            token_count: Estimated token count
            user_input: The user's input (for vector DB query tracking)
        """
        mode = self._get_composition_mode()

        # Extract entity IDs from provider if possible
        entities_included = []
        if isinstance(self._provider, DirectContextProvider):
            # Get entities from direct provider config
            for entity_config in self._provider.entities_config:
                # Handle both dict format {"entity_id": "...", "attributes": [...]}
                # and simple string format "entity_id"
                if isinstance(entity_config, dict):
                    entity_id = entity_config.get("entity_id")
                else:
                    # Simple string format - just the entity_id
                    entity_id = str(entity_config)

                if entity_id:
                    # Expand wildcards
                    matching = self._provider._get_entities_matching_pattern(entity_id)
                    entities_included.extend(matching)

        event_data = {
            "conversation_id": conversation_id,
            "mode": mode,
            "entities_included": entities_included,
            "entity_count": len(entities_included),
            "token_count": token_count,
        }

        # Add vector DB specific data if applicable
        if mode == CONTEXT_MODE_VECTOR_DB:
            event_data["vector_db_query"] = user_input

        self.hass.bus.async_fire(EVENT_CONTEXT_INJECTED, event_data)

        _LOGGER.debug(
            "Fired context.injected event: mode=%s, entities=%d, tokens=%d",
            mode,
            len(entities_included),
            token_count,
        )

    async def update_config(self, config: dict[str, Any]) -> None:
        """Update context configuration.

        This method updates the configuration and reinitializes the provider
        if the mode or critical settings have changed.

        Args:
            config: New configuration dictionary

        Raises:
            ContextInjectionError: If reconfiguration fails

        Example:
            >>> new_config = {
            ...     "mode": "vector_db",
            ...     "vector_db_host": "localhost",
            ...     "vector_db_port": 8000,
            ... }
            >>> await context_manager.update_config(new_config)
        """
        old_mode = self._get_mode_from_config()
        old_use_default = self._use_default_prompt()

        # Update configuration
        self.config.update(config)

        # Get new mode after update
        new_mode = self._get_mode_from_config()
        new_use_default = self._use_default_prompt()

        # Update cache settings
        self._cache_enabled = config.get("cache_enabled", self._cache_enabled)
        self._cache_ttl = config.get("cache_ttl", self._cache_ttl)
        self._emit_events = config.get("emit_events", self._emit_events)
        self._max_context_tokens = config.get("max_context_tokens", self._max_context_tokens)

        # Reinitialize providers if the composition changed
        if old_mode != new_mode or old_use_default != new_use_default:
            _LOGGER.info(
                "Context composition changed (mode %s -> %s, default prompt %s -> %s), "
                "reinitializing providers",
                old_mode,
                new_mode,
                old_use_default,
                new_use_default,
            )
            self._initialize_provider()

        # Clear cache after config update
        self._clear_cache()

        _LOGGER.info("Context manager configuration updated")

    def _get_composition_mode(self) -> str:
        """Get the effective context composition mode.

        Returns:
            "default" when the built-in default prompt drives composition
            (memory + retrieval only), otherwise the configured entity
            context mode ("direct" or "vector_db").
        """
        if self._use_default_prompt():
            return "default"
        return self._get_mode_from_config()

    def get_current_mode(self) -> str:
        """Get the current context composition mode.

        Returns:
            "default" in default prompt mode, otherwise the entity context
            mode ("direct" or "vector_db")
        """
        return self._get_composition_mode()

    def get_provider_info(self) -> dict[str, Any]:
        """Get information about the current provider.

        Returns:
            Dictionary with provider information

        Example:
            {
                "provider_class": "DirectContextProvider",
                "mode": "direct",
                "format": "json",
                "entity_count": 5
            }
        """
        info = {
            "provider_class": (self._provider.__class__.__name__ if self._provider else None),
            "mode": self.get_current_mode(),
            "entity_context_mode": self._get_mode_from_config(),
            "retrieval_provider_class": (
                self._retrieval_provider.__class__.__name__ if self._retrieval_provider else None
            ),
            "cache_enabled": self._cache_enabled,
            "cache_ttl": self._cache_ttl,
            "max_context_tokens": self._max_context_tokens,
        }

        # Add provider-specific info
        if isinstance(self._provider, DirectContextProvider):
            info.update(
                {
                    "format": self._provider.format_type,
                    "entity_count": len(self._provider.entities_config),
                }
            )

        return info

    async def async_close(self) -> None:
        """Clean up provider resources."""
        if self._provider is not None and hasattr(self._provider, "async_shutdown"):
            await self._provider.async_shutdown()
        if self._memory_provider is not None and hasattr(self._memory_provider, "async_shutdown"):
            await self._memory_provider.async_shutdown()
        if self._retrieval_provider is not None and hasattr(
            self._retrieval_provider, "async_shutdown"
        ):
            await self._retrieval_provider.async_shutdown()
        self._clear_cache()
