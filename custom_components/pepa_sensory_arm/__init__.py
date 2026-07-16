"""Pepa Sensory Arm - Intelligent conversation agent for Home Assistant.

This custom component provides advanced conversational AI capabilities with
tool calling, context injection, and conversation history management.
"""

from __future__ import annotations

import logging
from typing import Any, cast

from homeassistant.components import conversation as ha_conversation
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers.typing import ConfigType

from .agent import PepaSensoryArm
from .chroma_factory import ChromaClientFactory
from .const import (
    CONF_CONTEXT_MODE,
    CONF_MEMORY_ENABLED,
    CONF_PROMPT_USE_DEFAULT,
    CONF_SESSION_PERSISTENCE_ENABLED,
    CONF_SESSION_TIMEOUT,
    CONF_TOOLS_CUSTOM,
    CONF_VECTOR_DB_EMBEDDING_BASE_URL,
    CONF_VECTOR_DB_EMBEDDING_PROVIDER,
    CONTEXT_MODE_VECTOR_DB,
    DEFAULT_MEMORY_ENABLED,
    DEFAULT_PROMPT_USE_DEFAULT,
    DEFAULT_SESSION_PERSISTENCE_ENABLED,
    DEFAULT_SESSION_TIMEOUT,
    DEFAULT_VECTOR_DB_EMBEDDING_BASE_URL,
    DOMAIN,
    EMBEDDING_PROVIDER_OLLAMA,
)
from .conversation_session import ConversationSessionManager
from .helpers import check_ollama_health
from .memory_interface import MemoryInterface

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = []  # No additional platforms needed for conversation agent


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Pepa Sensory Arm component from YAML configuration.

    Args:
        hass: Home Assistant instance
        config: Configuration dictionary

    Returns:
        True if setup was successful
    """
    # Store YAML config for later use (especially custom tools)
    hass.data.setdefault(DOMAIN, {})
    if DOMAIN in config:
        hass.data[DOMAIN]["yaml_config"] = config[DOMAIN]
        _LOGGER.info("Loaded Pepa Sensory Arm YAML configuration")

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Pepa Sensory Arm from a config entry.

    Args:
        hass: Home Assistant instance
        entry: Config entry instance

    Returns:
        True if setup was successful
    """
    _LOGGER.info("Setting up Pepa Sensory Arm config entry: %s", entry.entry_id)

    # Merge config data
    config = dict(entry.data) | dict(entry.options)

    # The default system prompt's device tables read sensor.pepa_entity_context,
    # published by the bundled pyscript (custom_components/pyscript/entities_list.py,
    # entity_context.py). There is no fallback to exposed_entities - warn if it's
    # missing so the integration doesn't silently send an empty device catalog.
    if config.get(CONF_PROMPT_USE_DEFAULT, DEFAULT_PROMPT_USE_DEFAULT):
        entity_context_state = hass.states.get("sensor.pepa_entity_context")
        if entity_context_state is None or not entity_context_state.attributes.get("csv"):
            _LOGGER.warning(
                "The default system prompt requires the bundled pyscript "
                "entity-context sensor (sensor.pepa_entity_context), which is "
                "missing or has no data. Install/enable the pyscript integration "
                "with the bundled scripts, or the device catalog in the system "
                "prompt will be empty. See the documentation for setup details."
            )

    # Also merge YAML config for custom tools (if present)
    # This allows users to define custom tools in configuration.yaml
    if "yaml_config" in hass.data.get(DOMAIN, {}):
        yaml_config = hass.data[DOMAIN]["yaml_config"]
        if CONF_TOOLS_CUSTOM in yaml_config:
            config[CONF_TOOLS_CUSTOM] = yaml_config[CONF_TOOLS_CUSTOM]
            _LOGGER.info(
                "Loaded %d custom tool(s) from YAML configuration",
                len(yaml_config[CONF_TOOLS_CUSTOM]),
            )

    # Initialize conversation session manager for persistent voice conversations
    session_persistence_enabled = config.get(
        CONF_SESSION_PERSISTENCE_ENABLED, DEFAULT_SESSION_PERSISTENCE_ENABLED
    )
    if session_persistence_enabled:
        # Get timeout from config (stored in minutes, convert to seconds)
        session_timeout_minutes = config.get(CONF_SESSION_TIMEOUT, DEFAULT_SESSION_TIMEOUT // 60)
        session_timeout = session_timeout_minutes * 60  # Convert to seconds
    else:
        # Disabled - use 0 which makes get_conversation_id always return None
        session_timeout = 0
    session_manager = ConversationSessionManager(hass, session_timeout)
    await session_manager.async_load()
    if session_persistence_enabled:
        _LOGGER.info(
            "Conversation Session Manager initialized with persistence enabled (timeout: %ds)",
            session_timeout,
        )
    else:
        _LOGGER.info("Conversation Session Manager initialized with persistence disabled")

    # Create Pepa Sensory Arm instance with session manager
    agent = PepaSensoryArm(hass, config, session_manager)

    # Store agent instance and session manager
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "agent": agent,
        "session_manager": session_manager,
    }

    # Construct the ChromaDB client factory if anything needs ChromaDB.
    #
    # "Either", not "and": memory's vector capability is independent of the
    # entity-context Context Mode. Tying them together is the borrowed-client
    # bug -- setting Context Mode to Direct used to silently kill memory vector
    # search, sync, and dedup.
    context_mode = config.get(CONF_CONTEXT_MODE)
    memory_enabled = config.get(CONF_MEMORY_ENABLED, DEFAULT_MEMORY_ENABLED)
    chroma_factory = None

    if context_mode == CONTEXT_MODE_VECTOR_DB or memory_enabled:
        chroma_factory = ChromaClientFactory(hass, config)
        await chroma_factory.async_setup()
        hass.data[DOMAIN][entry.entry_id]["chroma_factory"] = chroma_factory

        # Placement-aware health check. The previous probe here hit host/port
        # unconditionally, which is meaningless under embedded placement.
        chromadb_healthy, chromadb_msg = await chroma_factory.health_check()
        if not chromadb_healthy:
            _LOGGER.warning(
                "ChromaDB health check failed (placement=%s) - %s. "
                "Vector DB and memory features may not work until ChromaDB is available.",
                chroma_factory.placement,
                chromadb_msg,
            )
        else:
            _LOGGER.info(
                "ChromaDB health check passed (placement=%s): %s",
                chroma_factory.placement,
                chromadb_msg,
            )

    # Check Ollama health if using Ollama embeddings.
    #
    # Left here deliberately: this is an embedding-provider concern, not a
    # placement concern, so it does not belong to the client factory. It follows
    # the embedding stack into embedder.py in P2 commit 2b.
    if context_mode == CONTEXT_MODE_VECTOR_DB:
        embedding_provider = config.get(CONF_VECTOR_DB_EMBEDDING_PROVIDER)
        embedding_base_url = config.get(
            CONF_VECTOR_DB_EMBEDDING_BASE_URL, DEFAULT_VECTOR_DB_EMBEDDING_BASE_URL
        )

        if embedding_provider == EMBEDDING_PROVIDER_OLLAMA:
            ollama_healthy, ollama_msg = await check_ollama_health(embedding_base_url)
            if not ollama_healthy:
                _LOGGER.warning(
                    "Ollama health check failed at %s - %s. "
                    "Embedding generation may not work until Ollama is available.",
                    embedding_base_url,
                    ollama_msg,
                )
            else:
                _LOGGER.info("Ollama health check passed: %s", ollama_msg)

    # Set up vector DB manager if using vector DB mode.
    #
    # Still gated on Context Mode -- entity indexing genuinely is a Context Mode
    # concern. What is no longer gated on it is memory's access to ChromaDB,
    # which now comes from the factory above rather than from this object.
    vector_manager = None
    if context_mode == CONTEXT_MODE_VECTOR_DB and chroma_factory is not None:
        try:
            from .vector_db_manager import VectorDBManager

            vector_manager = VectorDBManager(hass, config, chroma_factory)
            await vector_manager.async_setup()
            hass.data[DOMAIN][entry.entry_id]["vector_manager"] = vector_manager
            _LOGGER.info("Vector DB Manager enabled for this entry")
        except Exception as err:
            _LOGGER.error("Failed to set up Vector DB Manager: %s", err)
            # Continue setup without vector DB

    # Set up memory manager if enabled
    if memory_enabled:
        try:
            from .memory_manager import MemoryManager

            # The borrowed client dies here. Memory takes the factory directly;
            # it no longer receives VectorDBManager (or None, when Context Mode
            # was Direct -- which is exactly how setting Direct used to
            # silently kill memory's vector search, sync, and dedup).
            memory_manager = MemoryManager(
                hass=hass,
                chroma_factory=chroma_factory,
                config=config,
            )
            await memory_manager.async_initialize()

            # The interface-typed handle. Consumers depend on the contract, not
            # on which backend happens to be behind it -- that is what makes the
            # Memory Arm a backend swap rather than a rewrite.
            memory: MemoryInterface = memory_manager
            hass.data[DOMAIN][entry.entry_id]["memory"] = memory

            # Deprecated alias, kept for one release. No first-party code may
            # read it; tests/unit/test_borrowed_client_killed.py enforces that.
            hass.data[DOMAIN][entry.entry_id]["memory_manager"] = memory_manager
            _LOGGER.info("Memory Manager enabled for this entry")
        except Exception as err:
            _LOGGER.error("Failed to set up Memory Manager: %s", err)
            # Continue setup without memory manager

    # Register as a conversation agent
    ha_conversation.async_set_agent(hass, entry, agent)

    # Setup scheduled cleanup for conversation history
    agent.conversation_manager.setup_scheduled_cleanup()

    # Register services
    await async_setup_services(hass, entry.entry_id)

    # Register update listener to reload on config changes
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    _LOGGER.info("Pepa Sensory Arm setup complete")
    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry when it's updated.

    Args:
        hass: Home Assistant instance
        entry: Config entry that was updated
    """
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry.

    Args:
        hass: Home Assistant instance
        entry: Config entry instance

    Returns:
        True if unload was successful
    """
    _LOGGER.info("Unloading Pepa Sensory Arm config entry: %s", entry.entry_id)

    # Unregister conversation agent
    ha_conversation.async_unset_agent(hass, entry)

    # Clean up agent, memory manager, and vector DB manager
    if entry.entry_id in hass.data[DOMAIN]:
        entry_data = hass.data[DOMAIN][entry.entry_id]

        # Shut down memory manager if it exists. async_shutdown is a backend
        # lifecycle concern, not part of the contract, so this reaches the
        # concrete manager deliberately.
        if "memory_manager" in entry_data:
            await entry_data["memory_manager"].async_shutdown()

        # Shut down vector DB manager if it exists
        if "vector_manager" in entry_data:
            await entry_data["vector_manager"].async_shutdown()

        # Shut down the client factory last: it is shared between the managers
        # above, so it can only be released once both have stopped using it.
        if "chroma_factory" in entry_data:
            await entry_data["chroma_factory"].async_shutdown()

        # Clean up agent
        agent: PepaSensoryArm = entry_data["agent"]

        # Shutdown scheduled cleanup for conversation history
        agent.conversation_manager.shutdown_scheduled_cleanup()

        await agent.close()

        del hass.data[DOMAIN][entry.entry_id]

    # Remove services if this was the last entry
    if not hass.data[DOMAIN]:
        await async_remove_services(hass)

    return True


async def async_setup_services(
    hass: HomeAssistant,
    entry_id: str,
) -> None:
    """Register Pepa Sensory Arm services.

    Args:
        hass: Home Assistant instance
        entry_id: Config entry ID
    """

    def _get_entry_data(target_entry_id: str) -> dict[str, Any]:
        """Get entry data, defaulting to provided entry_id."""
        if target_entry_id in hass.data[DOMAIN]:
            return cast(dict[str, Any], hass.data[DOMAIN][target_entry_id])
        return cast(dict[str, Any], hass.data[DOMAIN].get(entry_id, {}))

    async def handle_process(call: ServiceCall) -> dict[str, Any]:
        """Handle the process service call.

        Processes a user message through the agent and returns the response.
        """
        text = call.data.get("text", "")
        conversation_id = call.data.get("conversation_id")
        user_id = call.data.get("user_id")
        target_entry_id = call.data.get("entry_id", entry_id)

        # Get the right agent instance
        entry_data = _get_entry_data(target_entry_id)
        target_agent = entry_data.get("agent")

        if target_agent is None:
            raise ValueError("Agent not found for entry")

        target_agent = cast(PepaSensoryArm, target_agent)

        try:
            response = await target_agent.process_message(
                text=text,
                conversation_id=conversation_id,
                user_id=user_id,
            )

            _LOGGER.info("Processed message successfully")

            # Return response (Home Assistant will handle this)
            return {
                "response": response,
                "conversation_id": conversation_id,
            }

        except Exception as err:
            _LOGGER.error("Failed to process message: %s", err)
            raise

    async def handle_clear_history(call: ServiceCall) -> None:
        """Handle the clear_history service call.

        Clears conversation history for a specific conversation or all conversations.
        """
        conversation_id = call.data.get("conversation_id")
        target_entry_id = call.data.get("entry_id", entry_id)

        # Get the right agent instance
        entry_data = _get_entry_data(target_entry_id)
        target_agent = entry_data.get("agent")

        if target_agent is None:
            raise ValueError("Agent not found for entry")

        target_agent = cast(PepaSensoryArm, target_agent)

        await target_agent.clear_history(conversation_id)

        _LOGGER.info(
            "Cleared history for %s",
            conversation_id if conversation_id else "all conversations",
        )

    async def handle_reload_context(call: ServiceCall) -> None:
        """Handle the reload_context service call.

        Reloads entity context (useful after entity changes).
        """
        target_entry_id = call.data.get("entry_id", entry_id)

        # Get the right agent instance
        entry_data = _get_entry_data(target_entry_id)
        target_agent = entry_data.get("agent")

        if target_agent is None:
            raise ValueError("Agent not found for entry")

        target_agent = cast(PepaSensoryArm, target_agent)

        await target_agent.reload_context()

        _LOGGER.info("Reloaded context")

    async def handle_execute_tool(call: ServiceCall) -> dict[str, Any]:
        """Handle the execute_tool service call (debug/testing).

        Manually executes a tool for testing purposes.
        """
        tool_name = call.data.get("tool_name", "")
        parameters = call.data.get("parameters", {})
        target_entry_id = call.data.get("entry_id", entry_id)

        # Get the right agent instance
        entry_data = _get_entry_data(target_entry_id)
        target_agent = entry_data.get("agent")

        if target_agent is None:
            raise ValueError("Agent not found for entry")

        target_agent = cast(PepaSensoryArm, target_agent)

        try:
            result = await target_agent.execute_tool_debug(tool_name, parameters)

            _LOGGER.info("Executed tool %s successfully", tool_name)

            return {
                "tool_name": tool_name,
                "result": result,
            }

        except Exception as err:
            _LOGGER.error("Failed to execute tool %s: %s", tool_name, err)
            raise

    async def handle_reindex_entities(call: ServiceCall) -> dict[str, Any]:
        """Handle the reindex_entities service call.

        Forces a full reindex of all entities into the vector database.
        """
        target_entry_id = call.data.get("entry_id", entry_id)

        # Get vector DB manager
        entry_data = _get_entry_data(target_entry_id)
        vector_manager = entry_data.get("vector_manager")

        if not vector_manager:
            _LOGGER.error("Vector DB Manager not enabled for this entry")
            return {"error": "Vector DB Manager not enabled"}

        try:
            stats: dict[str, Any] = await vector_manager.async_reindex_all_entities()
            _LOGGER.info("Reindex complete: %s", stats)
            return stats

        except Exception as err:
            _LOGGER.error("Failed to reindex entities: %s", err)
            raise

    async def handle_index_entity(call: ServiceCall) -> dict[str, Any]:
        """Handle the index_entity service call.

        Indexes a specific entity into the vector database.
        """
        entity_id = call.data.get("entity_id")
        target_entry_id = call.data.get("entry_id", entry_id)

        if not entity_id:
            _LOGGER.error("entity_id is required")
            return {"error": "entity_id is required"}

        # Get vector DB manager
        entry_data = _get_entry_data(target_entry_id)
        vector_manager = entry_data.get("vector_manager")

        if not vector_manager:
            _LOGGER.error("Vector DB Manager not enabled for this entry")
            return {"error": "Vector DB Manager not enabled"}

        try:
            await vector_manager.async_index_entity(entity_id)
            _LOGGER.info("Indexed entity: %s", entity_id)
            return {"entity_id": entity_id, "status": "indexed"}

        except Exception as err:
            _LOGGER.error("Failed to index entity %s: %s", entity_id, err)
            raise

    # Memory management services
    async def handle_list_memories(call: ServiceCall) -> dict[str, Any]:
        """Handle the list_memories service call.

        Lists all stored memories with optional filtering.
        """
        target_entry_id = call.data.get("entry_id", entry_id)
        memory_type = call.data.get("memory_type")
        limit = call.data.get("limit")

        # Get memory manager
        entry_data = _get_entry_data(target_entry_id)
        memory: MemoryInterface | None = entry_data.get("memory")

        if not memory:
            _LOGGER.error("Memory Manager not enabled for this entry")
            return {"error": "Memory Manager not enabled", "memories": [], "total": 0}

        try:
            records = await memory.list_all(
                limit=limit if limit is not None else 100,
                category=memory_type,
            )

            # Format for service response. Shape preserved; trust and source are
            # additions, since a service caller inspecting memory should see what
            # each belief is worth.
            return {
                "memories": [
                    {
                        "id": r.id,
                        "type": r.category,
                        "content": r.content,
                        "importance": r.metadata.get("importance", 0.0),
                        "extracted_at": r.created_at,
                        "last_accessed": r.metadata.get("last_accessed", r.updated_at),
                        "source_conversation_id": r.metadata.get("source_conversation_id"),
                        "trust": r.trust,
                        "source": r.source,
                    }
                    for r in records
                ],
                "total": len(records),
            }

        except Exception as err:
            _LOGGER.error("Failed to list memories: %s", err)
            raise

    async def handle_delete_memory(call: ServiceCall) -> None:
        """Handle the delete_memory service call.

        Deletes a specific memory by ID.
        """
        memory_id = call.data["memory_id"]
        target_entry_id = call.data.get("entry_id", entry_id)

        # Get memory manager
        entry_data = _get_entry_data(target_entry_id)
        memory: MemoryInterface | None = entry_data.get("memory")

        if not memory:
            _LOGGER.error("Memory Manager not enabled for this entry")
            return

        try:
            success = await memory.delete(memory_id)

            if success:
                _LOGGER.info("Deleted memory %s", memory_id)
            else:
                _LOGGER.warning("Failed to delete memory %s", memory_id)

        except Exception as err:
            _LOGGER.error("Failed to delete memory %s: %s", memory_id, err)
            raise

    async def handle_clear_memories(call: ServiceCall) -> dict[str, Any]:
        """Handle the clear_memories service call.

        Clears all memories (requires confirmation).
        """
        confirm = call.data.get("confirm", False)
        target_entry_id = call.data.get("entry_id", entry_id)

        if not confirm:
            _LOGGER.error("Must set 'confirm: true' to clear all memories")
            return {"error": "confirmation_required", "deleted_count": 0}

        # Get memory manager
        entry_data = _get_entry_data(target_entry_id)
        memory: MemoryInterface | None = entry_data.get("memory")

        if not memory:
            _LOGGER.error("Memory Manager not enabled for this entry")
            return {"error": "Memory Manager not enabled", "deleted_count": 0}

        try:
            deleted_count = await memory.clear_all()
            _LOGGER.info("Cleared %d memories", deleted_count)

            return {
                "deleted_count": deleted_count,
            }

        except Exception as err:
            _LOGGER.error("Failed to clear memories: %s", err)
            raise

    async def handle_search_memories(call: ServiceCall) -> dict[str, Any]:
        """Handle the search_memories service call.

        Searches memories by semantic similarity.
        """
        query = call.data["query"]
        limit = call.data.get("limit", 10)
        min_importance = call.data.get("min_importance", 0.0)
        target_entry_id = call.data.get("entry_id", entry_id)

        # Get memory manager
        entry_data = _get_entry_data(target_entry_id)
        memory: MemoryInterface | None = entry_data.get("memory")

        if not memory:
            _LOGGER.error("Memory Manager not enabled for this entry")
            return {"error": "Memory Manager not enabled", "memories": [], "total": 0}

        try:
            records = await memory.recall(query=query, top_k=limit)

            # min_importance filters salience, which the contract does not model
            # -- and min_trust is not its equivalent. Filtering here keeps this
            # service's behavior identical rather than quietly redefining what
            # the parameter means.
            if min_importance > 0.0:
                records = [
                    r for r in records if r.metadata.get("importance", 0.0) >= min_importance
                ]

            return {
                "memories": [
                    {
                        "id": r.id,
                        "type": r.category,
                        "content": r.content,
                        "importance": r.metadata.get("importance", 0.0),
                        "relevance_score": r.metadata.get("relevance_score", 0.0),
                        "trust": r.trust,
                        "source": r.source,
                    }
                    for r in records
                ],
                "total": len(records),
            }

        except Exception as err:
            _LOGGER.error("Failed to search memories: %s", err)
            raise

    async def handle_add_memory(call: ServiceCall) -> dict[str, Any]:
        """Handle the add_memory service call.

        Manually adds a memory.
        """
        content = call.data["content"]
        memory_type = call.data.get("type", "fact")
        importance = call.data.get("importance", 0.5)
        target_entry_id = call.data.get("entry_id", entry_id)

        # Get memory manager
        entry_data = _get_entry_data(target_entry_id)
        memory: MemoryInterface | None = entry_data.get("memory")

        if not memory:
            _LOGGER.error("Memory Manager not enabled for this entry")
            return {"error": "Memory Manager not enabled"}

        try:
            # A service-call write is the user stating something, so it is the
            # explicit_user path -- not an inference the system made.
            memory_id = await memory.write(
                content=content,
                category=memory_type,
                source="explicit_user",
                conversation_id=None,
                metadata={
                    "importance": importance,
                    "extraction_method": "manual_service",
                    "topics": [],
                    "entities_involved": [],
                },
            )

            _LOGGER.info("Added memory via service: %s", memory_id)

            return {
                "memory_id": memory_id,
            }

        except Exception as err:
            _LOGGER.error("Failed to add memory: %s", err)
            raise

    async def handle_clear_conversation(call: ServiceCall) -> None:
        """Handle the clear_conversation service call.

        Clears conversation session for a user or device, allowing them to
        start a fresh conversation with no previous context.
        """
        user_id = call.data.get("user_id")
        device_id = call.data.get("device_id")
        target_entry_id = call.data.get("entry_id", entry_id)

        # Get session manager
        entry_data = _get_entry_data(target_entry_id)
        session_manager = entry_data.get("session_manager")

        if not session_manager:
            _LOGGER.error("Session Manager not available for this entry")
            return

        if user_id or device_id:
            # Clear specific session
            success = await session_manager.clear_session(
                user_id=user_id,
                device_id=device_id,
            )
            if success:
                _LOGGER.info(
                    "Cleared conversation session for user_id=%s device_id=%s",
                    user_id,
                    device_id,
                )
            else:
                _LOGGER.warning(
                    "No active conversation found for user_id=%s device_id=%s",
                    user_id,
                    device_id,
                )
        else:
            # Clear all sessions
            count = await session_manager.clear_all_sessions()
            _LOGGER.info("Cleared all %d conversation session(s)", count)

    # Register services (only once for all instances)
    if not hass.services.has_service(DOMAIN, "process"):
        hass.services.async_register(DOMAIN, "process", handle_process)
        _LOGGER.debug("Registered service: process")

    if not hass.services.has_service(DOMAIN, "clear_history"):
        hass.services.async_register(DOMAIN, "clear_history", handle_clear_history)
        _LOGGER.debug("Registered service: clear_history")

    if not hass.services.has_service(DOMAIN, "reload_context"):
        hass.services.async_register(DOMAIN, "reload_context", handle_reload_context)
        _LOGGER.debug("Registered service: reload_context")

    if not hass.services.has_service(DOMAIN, "execute_tool"):
        hass.services.async_register(DOMAIN, "execute_tool", handle_execute_tool)
        _LOGGER.debug("Registered service: execute_tool")

    if not hass.services.has_service(DOMAIN, "reindex_entities"):
        hass.services.async_register(DOMAIN, "reindex_entities", handle_reindex_entities)
        _LOGGER.debug("Registered service: reindex_entities")

    if not hass.services.has_service(DOMAIN, "index_entity"):
        hass.services.async_register(DOMAIN, "index_entity", handle_index_entity)
        _LOGGER.debug("Registered service: index_entity")

    # Register memory management services
    if not hass.services.has_service(DOMAIN, "list_memories"):
        hass.services.async_register(
            DOMAIN,
            "list_memories",
            handle_list_memories,
            supports_response=SupportsResponse.ONLY,
        )
        _LOGGER.debug("Registered service: list_memories")

    if not hass.services.has_service(DOMAIN, "delete_memory"):
        hass.services.async_register(DOMAIN, "delete_memory", handle_delete_memory)
        _LOGGER.debug("Registered service: delete_memory")

    if not hass.services.has_service(DOMAIN, "clear_memories"):
        hass.services.async_register(
            DOMAIN,
            "clear_memories",
            handle_clear_memories,
            supports_response=SupportsResponse.ONLY,
        )
        _LOGGER.debug("Registered service: clear_memories")

    if not hass.services.has_service(DOMAIN, "search_memories"):
        hass.services.async_register(
            DOMAIN,
            "search_memories",
            handle_search_memories,
            supports_response=SupportsResponse.ONLY,
        )
        _LOGGER.debug("Registered service: search_memories")

    if not hass.services.has_service(DOMAIN, "add_memory"):
        hass.services.async_register(
            DOMAIN,
            "add_memory",
            handle_add_memory,
            supports_response=SupportsResponse.ONLY,
        )
        _LOGGER.debug("Registered service: add_memory")

    if not hass.services.has_service(DOMAIN, "clear_conversation"):
        hass.services.async_register(DOMAIN, "clear_conversation", handle_clear_conversation)
        _LOGGER.debug("Registered service: clear_conversation")


async def async_remove_services(hass: HomeAssistant) -> None:
    """Remove Pepa Sensory Arm services.

    Args:
        hass: Home Assistant instance
    """
    services = [
        "process",
        "clear_history",
        "reload_context",
        "execute_tool",
        "reindex_entities",
        "index_entity",
        "list_memories",
        "delete_memory",
        "clear_memories",
        "search_memories",
        "add_memory",
        "clear_conversation",
    ]

    for service in services:
        if hass.services.has_service(DOMAIN, service):
            hass.services.async_remove(DOMAIN, service)
            _LOGGER.debug("Removed service: %s", service)
