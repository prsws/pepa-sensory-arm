"""Constants for the Pepa Sensory Arm integration."""

from typing import Final

# Domain and component info
DOMAIN: Final = "pepa_sensory_arm"
DEFAULT_NAME: Final = "Pepa Sensory Arm"
VERSION: Final = "0.9.5"

# Configuration keys - LLM Configuration
CONF_LLM_BASE_URL: Final = "llm_base_url"
CONF_LLM_API_KEY: Final = "llm_api_key"
CONF_LLM_MODEL: Final = "llm_model"
CONF_LLM_TEMPERATURE: Final = "llm_temperature"
CONF_LLM_MAX_TOKENS: Final = "llm_max_tokens"
CONF_LLM_TOP_P: Final = "llm_top_p"
CONF_LLM_KEEP_ALIVE: Final = "llm_keep_alive"
CONF_LLM_BACKEND: Final = "llm_backend"
CONF_LLM_PROXY_HEADERS: Final = "llm_proxy_headers"
CONF_THINKING_ENABLED: Final = "thinking_enabled"
CONF_AZURE_API_VERSION: Final = "azure_api_version"

# Configuration keys - LLM Retry Settings
CONF_RETRY_MAX_ATTEMPTS: Final = "retry_max_attempts"
CONF_RETRY_INITIAL_DELAY: Final = "retry_initial_delay"
CONF_RETRY_BACKOFF_FACTOR: Final = "retry_backoff_factor"
CONF_RETRY_MAX_DELAY: Final = "retry_max_delay"
CONF_RETRY_JITTER: Final = "retry_jitter"

# Configuration keys - Context Injection
CONF_CONTEXT_MODE: Final = "context_mode"
CONF_CONTEXT_ENTITIES: Final = "context_entities"
CONF_CONTEXT_FORMAT: Final = "context_format"

# Configuration keys - Direct Context Provider
CONF_DIRECT_ENTITIES: Final = "direct_entities"
CONF_DIRECT_UPDATE_FREQUENCY: Final = "direct_update_frequency"

# Configuration keys - Vector DB Context Provider
CONF_VECTOR_DB_ENABLED: Final = "vector_db_enabled"
CONF_VECTOR_DB_HOST: Final = "vector_db_host"
CONF_VECTOR_DB_PORT: Final = "vector_db_port"
CONF_VECTOR_DB_COLLECTION: Final = "vector_db_collection"
CONF_VECTOR_DB_TOP_K: Final = "vector_db_top_k"
CONF_VECTOR_DB_SIMILARITY_THRESHOLD: Final = "vector_db_similarity_threshold"
CONF_VECTOR_DB_EMBEDDING_MODEL: Final = "vector_db_embedding_model"
CONF_VECTOR_DB_EMBEDDING_PROVIDER: Final = "vector_db_embedding_provider"
CONF_VECTOR_DB_EMBEDDING_BASE_URL: Final = "vector_db_embedding_base_url"
CONF_OPENAI_API_KEY: Final = "openai_api_key"
CONF_EMBEDDING_KEEP_ALIVE: Final = "embedding_keep_alive"

# Configuration keys - Additional Collections
CONF_ADDITIONAL_COLLECTIONS: Final = "additional_collections"
CONF_ADDITIONAL_TOP_K: Final = "additional_top_k"
CONF_ADDITIONAL_L2_DISTANCE_THRESHOLD: Final = "additional_l2_distance_threshold"

# Configuration keys - Conversation History
CONF_HISTORY_ENABLED: Final = "history_enabled"
CONF_HISTORY_MAX_MESSAGES: Final = "history_max_messages"
CONF_HISTORY_MAX_TOKENS: Final = "history_max_tokens"
CONF_HISTORY_PERSIST: Final = "history_persist"
CONF_MAX_CONTEXT_TOKENS: Final = "max_context_tokens"

# Configuration keys - Context Optimization
CONF_COMPRESSION_LEVEL: Final = "compression_level"
CONF_PRESERVE_RECENT_MESSAGES: Final = "preserve_recent_messages"
CONF_SUMMARIZATION_ENABLED: Final = "summarization_enabled"
CONF_ENTITY_PRIORITY_WEIGHTS: Final = "entity_priority_weights"

# Configuration keys - System Prompt
CONF_PROMPT_USE_DEFAULT: Final = "prompt_use_default"
CONF_PROMPT_USE_CUSTOM: Final = "prompt_use_custom"
CONF_PROMPT_CUSTOM: Final = "prompt_custom"
CONF_PROMPT_CUSTOM_ADDITIONS: Final = "prompt_custom_additions"
CONF_PROMPT_INCLUDE_LABELS: Final = "prompt_include_labels"

# Configuration keys - Tool Configuration
CONF_TOOLS_ENABLE_NATIVE: Final = "tools_enable_native"
CONF_TOOLS_CUSTOM: Final = "tools_custom"
CONF_TOOLS_MAX_CALLS_PER_TURN: Final = "tools_max_calls_per_turn"
CONF_TOOLS_TIMEOUT: Final = "tools_timeout"

# Configuration keys - External LLM Tool
CONF_EXTERNAL_LLM_ENABLED: Final = "external_llm_enabled"
CONF_EXTERNAL_LLM_BASE_URL: Final = "external_llm_base_url"
CONF_EXTERNAL_LLM_API_KEY: Final = "external_llm_api_key"
CONF_EXTERNAL_LLM_MODEL: Final = "external_llm_model"
CONF_EXTERNAL_LLM_TEMPERATURE: Final = "external_llm_temperature"
CONF_EXTERNAL_LLM_MAX_TOKENS: Final = "external_llm_max_tokens"
CONF_EXTERNAL_LLM_TOOL_DESCRIPTION: Final = "external_llm_tool_description"
CONF_EXTERNAL_LLM_AUTO_INCLUDE_CONTEXT: Final = "external_llm_auto_include_context"
CONF_EXTERNAL_LLM_KEEP_ALIVE: Final = "external_llm_keep_alive"

# Configuration keys - Memory Configuration
CONF_MEMORY_ENABLED: Final = "memory_enabled"
CONF_MEMORY_MAX_MEMORIES: Final = "memory_max_memories"
CONF_MEMORY_MIN_IMPORTANCE: Final = "memory_min_importance"
CONF_MEMORY_COLLECTION_NAME: Final = "memory_collection_name"
CONF_MEMORY_IMPORTANCE_DECAY: Final = "memory_importance_decay"
CONF_MEMORY_DEDUP_THRESHOLD: Final = "memory_dedup_threshold"
CONF_MEMORY_EXTRACTION_ENABLED: Final = "memory_extraction_enabled"
CONF_MEMORY_EXTRACTION_LLM: Final = "memory_extraction_llm"
CONF_MEMORY_CONTEXT_TOP_K: Final = "memory_context_top_k"
CONF_MEMORY_EVENT_TTL: Final = "memory_event_ttl"
CONF_MEMORY_FACT_TTL: Final = "memory_fact_ttl"
CONF_MEMORY_PREFERENCE_TTL: Final = "memory_preference_ttl"
CONF_MEMORY_CLEANUP_INTERVAL: Final = "memory_cleanup_interval"
CONF_MEMORY_MIN_WORDS: Final = "memory_min_words"
CONF_MEMORY_QUALITY_VALIDATION_ENABLED: Final = "memory_quality_validation_enabled"
CONF_MEMORY_QUALITY_VALIDATION_INTERVAL: Final = "memory_quality_validation_interval"

# Configuration keys - Debugging and Events
CONF_DEBUG_LOGGING: Final = "debug_logging"
CONF_EMIT_EVENTS: Final = "emit_events"

# Configuration keys - Streaming
CONF_STREAMING_ENABLED: Final = "streaming_enabled"

# Configuration keys - Conversation Session
CONF_SESSION_TIMEOUT: Final = "session_timeout"
CONF_SESSION_PERSISTENCE_ENABLED: Final = "session_persistence_enabled"

# Context modes
CONTEXT_MODE_DIRECT: Final = "direct"
CONTEXT_MODE_VECTOR_DB: Final = "vector_db"

# Context format options
CONTEXT_FORMAT_JSON: Final = "json"
CONTEXT_FORMAT_NATURAL_LANGUAGE: Final = "natural_language"
CONTEXT_FORMAT_HYBRID: Final = "hybrid"

# Context compression levels
COMPRESSION_LEVEL_NONE: Final = "none"
COMPRESSION_LEVEL_LOW: Final = "low"
COMPRESSION_LEVEL_MEDIUM: Final = "medium"
COMPRESSION_LEVEL_HIGH: Final = "high"

# Embedding providers
EMBEDDING_PROVIDER_OPENAI: Final = "openai"
EMBEDDING_PROVIDER_OLLAMA: Final = "ollama"

# LLM Backend options
LLM_BACKEND_DEFAULT: Final = "default"
LLM_BACKEND_LLAMA_CPP: Final = "llama-cpp"
LLM_BACKEND_VLLM: Final = "vllm-server"
LLM_BACKEND_OLLAMA_GPU: Final = "ollama-gpu"

# Default values - LLM Configuration
DEFAULT_LLM_MODEL: Final = "gpt-4o-mini"
DEFAULT_TEMPERATURE: Final = 0.7
DEFAULT_MAX_TOKENS: Final = 500
DEFAULT_TOP_P: Final = 1.0
DEFAULT_LLM_KEEP_ALIVE: Final = "5m"
DEFAULT_LLM_BACKEND: Final = LLM_BACKEND_DEFAULT
DEFAULT_THINKING_ENABLED: Final = True  # Default: enabled (no /no_think appended)

# Default values - Azure OpenAI
# Azure API version used for chat completions endpoint.
# See: https://learn.microsoft.com/en-us/azure/ai-services/openai/reference#api-specs
DEFAULT_AZURE_API_VERSION: Final = "2024-12-01-preview"

# Default values - LLM Retry Settings
DEFAULT_RETRY_MAX_ATTEMPTS: Final = 1
DEFAULT_RETRY_INITIAL_DELAY: Final = 1.0  # seconds
DEFAULT_RETRY_BACKOFF_FACTOR: Final = 2.0  # exponential backoff: 1s, 2s, 4s, etc.
DEFAULT_RETRY_MAX_DELAY: Final = 30.0  # maximum delay cap in seconds
DEFAULT_RETRY_JITTER: Final = True  # add random jitter to prevent thundering herd

# Default values - Context Injection
DEFAULT_CONTEXT_MODE: Final = CONTEXT_MODE_DIRECT
DEFAULT_CONTEXT_FORMAT: Final = CONTEXT_FORMAT_JSON

# Default values - Vector DB
DEFAULT_VECTOR_DB_HOST: Final = "localhost"
DEFAULT_VECTOR_DB_PORT: Final = 8000
DEFAULT_VECTOR_DB_COLLECTION: Final = "home_entities"
DEFAULT_VECTOR_DB_TOP_K: Final = 5
DEFAULT_VECTOR_DB_SIMILARITY_THRESHOLD: Final = 250.0  # L2 distance threshold
DEFAULT_VECTOR_DB_EMBEDDING_MODEL: Final = "text-embedding-3-small"
DEFAULT_VECTOR_DB_EMBEDDING_PROVIDER: Final = EMBEDDING_PROVIDER_OLLAMA
DEFAULT_VECTOR_DB_EMBEDDING_BASE_URL: Final = "http://localhost:11434"
DEFAULT_EMBEDDING_KEEP_ALIVE: Final = "5m"

# Default values - Additional Collections
DEFAULT_ADDITIONAL_COLLECTIONS: Final[list[str]] = []
DEFAULT_ADDITIONAL_TOP_K: Final = 5
DEFAULT_ADDITIONAL_L2_DISTANCE_THRESHOLD: Final = 250.0

# Default values - Conversation History
DEFAULT_HISTORY_ENABLED: Final = True
DEFAULT_HISTORY_MAX_MESSAGES: Final = 10
DEFAULT_HISTORY_MAX_TOKENS: Final = 4000
DEFAULT_HISTORY_PERSIST: Final = True

# Default values - Context Optimization
DEFAULT_COMPRESSION_LEVEL: Final = "medium"
DEFAULT_PRESERVE_RECENT_MESSAGES: Final = 3
DEFAULT_SUMMARIZATION_ENABLED: Final = False

# Default values - System Prompt
DEFAULT_PROMPT_USE_DEFAULT: Final = True
DEFAULT_PROMPT_USE_CUSTOM: Final = False
DEFAULT_PROMPT_INCLUDE_LABELS: Final = False

# Default values - Tool Configuration
DEFAULT_TOOLS_ENABLE_NATIVE: Final = True
DEFAULT_TOOLS_MAX_CALLS_PER_TURN: Final = 5
DEFAULT_TOOLS_TIMEOUT: Final = 30

# Default values - External LLM Tool
DEFAULT_EXTERNAL_LLM_ENABLED: Final = False
DEFAULT_EXTERNAL_LLM_MODEL: Final = "gpt-4o"
DEFAULT_EXTERNAL_LLM_TEMPERATURE: Final = 0.8
DEFAULT_EXTERNAL_LLM_MAX_TOKENS: Final = 1000
DEFAULT_EXTERNAL_LLM_AUTO_INCLUDE_CONTEXT: Final = True
DEFAULT_EXTERNAL_LLM_KEEP_ALIVE: Final = "5m"
DEFAULT_EXTERNAL_LLM_TOOL_DESCRIPTION: Final = (
    "Use this when you need help with complex analysis, detailed explanations, "
    "or comprehensive recommendations beyond simple home control."
)

# Default values - Memory Configuration
DEFAULT_MEMORY_ENABLED: Final = True
DEFAULT_MEMORY_MAX_MEMORIES: Final = 100
DEFAULT_MEMORY_MIN_IMPORTANCE: Final = 0.3
DEFAULT_MEMORY_COLLECTION_NAME: Final = "pepa_sensory_arm_memories"
DEFAULT_MEMORY_IMPORTANCE_DECAY: Final = 0.0  # No decay by default
DEFAULT_MEMORY_DEDUP_THRESHOLD: Final = 0.85  # Lowered to catch near-duplicate memories
DEFAULT_MEMORY_EXTRACTION_ENABLED: Final = True
DEFAULT_MEMORY_EXTRACTION_LLM: Final = "external"  # "external" or "local"
DEFAULT_MEMORY_CONTEXT_TOP_K: Final = 5
DEFAULT_MEMORY_EVENT_TTL: Final = 300  # 5 minutes for events (in seconds)
DEFAULT_MEMORY_FACT_TTL: Final = None  # No expiration for facts
DEFAULT_MEMORY_PREFERENCE_TTL: Final = 7776000  # 90 days for preferences
DEFAULT_MEMORY_CLEANUP_INTERVAL: Final = 300  # Run cleanup every 5 minutes
DEFAULT_MEMORY_MIN_WORDS: Final = 10
DEFAULT_MEMORY_QUALITY_VALIDATION_ENABLED: Final = True
DEFAULT_MEMORY_QUALITY_VALIDATION_INTERVAL: Final = 3600  # Run quality validation every hour

# Default values - Debugging
DEFAULT_DEBUG_LOGGING: Final = False
DEFAULT_EMIT_EVENTS: Final = True

# Default values - Streaming
DEFAULT_STREAMING_ENABLED: Final = False

# Default values - Conversation Session
DEFAULT_SESSION_TIMEOUT: Final = 3600  # 1 hour in seconds
DEFAULT_SESSION_PERSISTENCE_ENABLED: Final = True

# Event names
EVENT_CONVERSATION_STARTED: Final = f"{DOMAIN}.conversation.started"
EVENT_CONVERSATION_FINISHED: Final = f"{DOMAIN}.conversation.finished"
EVENT_TOOL_EXECUTED: Final = f"{DOMAIN}.tool.executed"
EVENT_CONTEXT_INJECTED: Final = f"{DOMAIN}.context.injected"
EVENT_CONTEXT_OPTIMIZED: Final = f"{DOMAIN}.context.optimized"
EVENT_HISTORY_SAVED: Final = f"{DOMAIN}.history.saved"
EVENT_VECTOR_DB_QUERIED: Final = f"{DOMAIN}.vector_db.queried"
EVENT_MEMORY_EXTRACTED: Final = f"{DOMAIN}.memory.extracted"
EVENT_ERROR: Final = f"{DOMAIN}.error"
EVENT_STREAMING_ERROR: Final = f"{DOMAIN}.streaming.error"
EVENT_TOOL_PROGRESS: Final = f"{DOMAIN}.tool.progress"

# Tool names
TOOL_HA_CONTROL: Final = "ha_control"
TOOL_HA_QUERY: Final = "ha_query"
TOOL_QUERY_EXTERNAL_LLM: Final = "query_external_llm"

# Tool actions (for ha_control)
ACTION_TURN_ON: Final = "turn_on"
ACTION_TURN_OFF: Final = "turn_off"
ACTION_TOGGLE: Final = "toggle"
ACTION_SET_VALUE: Final = "set_value"

# Tool history aggregation types (for ha_query)
HISTORY_AGGREGATE_AVG: Final = "avg"
HISTORY_AGGREGATE_MIN: Final = "min"
HISTORY_AGGREGATE_MAX: Final = "max"
HISTORY_AGGREGATE_SUM: Final = "sum"
HISTORY_AGGREGATE_COUNT: Final = "count"

# Service names
SERVICE_PROCESS: Final = "process"
SERVICE_CLEAR_HISTORY: Final = "clear_history"
SERVICE_RELOAD_CONTEXT: Final = "reload_context"
SERVICE_EXECUTE_TOOL: Final = "execute_tool"

# Service parameter names
ATTR_TEXT: Final = "text"
ATTR_CONVERSATION_ID: Final = "conversation_id"
ATTR_CONTEXT_ENTITIES: Final = "context_entities"
ATTR_TOOL_NAME: Final = "tool_name"
ATTR_PARAMETERS: Final = "parameters"

# Storage keys
STORAGE_KEY: Final = f"{DOMAIN}.storage"
STORAGE_VERSION: Final = 1

# Conversation history storage
HISTORY_STORAGE_KEY: Final = f"{DOMAIN}.history"

# Memory storage
MEMORY_STORAGE_KEY: Final = f"{DOMAIN}.memories"
MEMORY_STORAGE_VERSION: Final = 1

# HTTP timeouts (seconds)
HTTP_TIMEOUT_DEFAULT: Final = 60
HTTP_TIMEOUT: Final = 60  # Alias for default timeout
HTTP_TIMEOUT_EXTERNAL_LLM: Final = 90

# Token limits and warnings
TOKEN_WARNING_THRESHOLD: Final = 0.8  # Warn at 80% of limit
MAX_CONTEXT_TOKENS: Final = 8000  # Maximum tokens for context before truncation

# Default values - Context Tokens
DEFAULT_MAX_CONTEXT_TOKENS: Final = 8000

# Update intervals (seconds)
CONTEXT_UPDATE_INTERVAL: Final = 60  # Update entity context every 60 seconds
CLEANUP_INTERVAL: Final = 3600  # Cleanup old conversations every hour

# Custom tool handler types
CUSTOM_TOOL_HANDLER_REST: Final = "rest"
CUSTOM_TOOL_HANDLER_SERVICE: Final = "service"
CUSTOM_TOOL_HANDLER_SCRIPT: Final = "script"
CUSTOM_TOOL_HANDLER_TEMPLATE: Final = "template"

# Domain service mappings - defines which services are available for each domain
# and which services require specific entity features.
# This is used by both context providers (to advertise accurate available_services)
# and ha_control (to determine the correct service to call).
#
# Structure:
# {
#   "domain": {
#     "base_services": [list of services always available],
#     "feature_services": {
#       feature_flag: [list of services requiring this feature]
#     },
#     "action_service_map": {
#       "action_name": {
#         "param_to_service": {
#           "parameter_name": "service_name"
#         }
#       }
#     }
#   }
# }
#
# Note: Feature flags are imported from homeassistant.components.<domain>.EntityFeature
# and must be imported in the code that uses this mapping.

DOMAIN_SERVICE_MAPPINGS: Final = {
    # Cover entities (blinds, shades, garage doors, etc.)
    "cover": {
        "base_services": ["toggle"],  # Always available
        "feature_services": {
            # CoverEntityFeature.OPEN (1)
            1: ["open_cover"],
            # CoverEntityFeature.CLOSE (2)
            2: ["close_cover"],
            # CoverEntityFeature.SET_POSITION (4)
            4: ["set_cover_position"],
            # CoverEntityFeature.STOP (8)
            8: ["stop_cover"],
            # CoverEntityFeature.OPEN_TILT (16)
            16: ["open_cover_tilt"],
            # CoverEntityFeature.CLOSE_TILT (32)
            32: ["close_cover_tilt"],
            # CoverEntityFeature.STOP_TILT (64)
            64: ["stop_cover_tilt"],
            # CoverEntityFeature.SET_TILT_POSITION (128)
            128: ["set_cover_tilt_position"],
        },
        "action_service_map": {
            "turn_on": "open_cover",
            "turn_off": "close_cover",
            "toggle": "toggle",
            "set_value": {
                "position": "set_cover_position",  # Requires feature 4
                "tilt_position": "set_cover_tilt_position",  # Requires feature 128
            },
        },
    },
    # Fan entities
    "fan": {
        "base_services": ["turn_on", "turn_off", "toggle"],
        "feature_services": {
            # FanEntityFeature.SET_SPEED (1) - legacy, now use percentage
            1: ["set_percentage", "increase_speed", "decrease_speed"],
            # FanEntityFeature.OSCILLATE (2)
            2: ["oscillate"],
            # FanEntityFeature.DIRECTION (4)
            4: ["set_direction"],
            # FanEntityFeature.PRESET_MODE (8)
            8: ["set_preset_mode"],
        },
        "action_service_map": {
            "turn_on": "turn_on",
            "turn_off": "turn_off",
            "toggle": "toggle",
            "set_value": {
                "percentage": "set_percentage",
                "preset_mode": "set_preset_mode",
                "oscillating": "oscillate",
                "direction": "set_direction",
            },
        },
    },
    # Light entities
    "light": {
        "base_services": ["turn_on", "turn_off", "toggle"],
        "feature_services": {},  # Lights don't use feature flags for basic services
        "action_service_map": {
            "turn_on": "turn_on",  # Accepts brightness, color, etc.
            "turn_off": "turn_off",
            "toggle": "toggle",
            "set_value": "turn_on",  # Set brightness, color via turn_on
        },
    },
    # Climate entities (thermostats, AC, heating)
    "climate": {
        "base_services": ["turn_on", "turn_off"],
        "feature_services": {
            # ClimateEntityFeature.TARGET_TEMPERATURE (1)
            1: ["set_temperature"],
            # ClimateEntityFeature.TARGET_TEMPERATURE_RANGE (2)
            2: ["set_temperature"],  # Same service, different params
            # ClimateEntityFeature.TARGET_HUMIDITY (4)
            4: ["set_humidity"],
            # ClimateEntityFeature.FAN_MODE (8)
            8: ["set_fan_mode"],
            # ClimateEntityFeature.PRESET_MODE (16)
            16: ["set_preset_mode"],
            # ClimateEntityFeature.SWING_MODE (32)
            32: ["set_swing_mode"],
            # ClimateEntityFeature.SWING_HORIZONTAL_MODE (512)
            512: ["set_swing_mode"],  # Uses same service
        },
        "action_service_map": {
            "turn_on": "set_hvac_mode",  # Special: needs hvac_mode parameter
            "turn_off": "set_hvac_mode",  # Special: hvac_mode = "off"
            "toggle": "toggle",
            "set_value": {
                "temperature": "set_temperature",
                "target_temp_high": "set_temperature",
                "target_temp_low": "set_temperature",
                "hvac_mode": "set_hvac_mode",
                "fan_mode": "set_fan_mode",
                "preset_mode": "set_preset_mode",
                "swing_mode": "set_swing_mode",
                "humidity": "set_humidity",
            },
        },
    },
    # Media Player entities
    "media_player": {
        "base_services": ["turn_on", "turn_off", "toggle", "play_media"],
        "feature_services": {
            # MediaPlayerEntityFeature.PAUSE (1)
            1: ["media_pause"],
            # MediaPlayerEntityFeature.SEEK (2)
            2: ["media_seek"],
            # MediaPlayerEntityFeature.VOLUME_SET (4)
            4: ["volume_set"],
            # MediaPlayerEntityFeature.VOLUME_MUTE (8)
            8: ["volume_mute"],
            # MediaPlayerEntityFeature.PREVIOUS_TRACK (16)
            16: ["media_previous_track"],
            # MediaPlayerEntityFeature.NEXT_TRACK (32)
            32: ["media_next_track"],
            # MediaPlayerEntityFeature.VOLUME_STEP (1024)
            1024: ["volume_up", "volume_down"],
            # MediaPlayerEntityFeature.SELECT_SOURCE (2048)
            2048: ["select_source"],
            # MediaPlayerEntityFeature.STOP (4096)
            4096: ["media_stop"],
            # MediaPlayerEntityFeature.CLEAR_PLAYLIST (8192)
            8192: ["clear_playlist"],
            # MediaPlayerEntityFeature.PLAY (16384)
            16384: ["media_play"],
            # MediaPlayerEntityFeature.SHUFFLE_SET (32768)
            32768: ["shuffle_set"],
            # MediaPlayerEntityFeature.SELECT_SOUND_MODE (65536)
            65536: ["select_sound_mode"],
            # MediaPlayerEntityFeature.BROWSE_MEDIA (131072)
            131072: ["browse_media"],
            # MediaPlayerEntityFeature.REPEAT_SET (262144)
            262144: ["repeat_set"],
            # MediaPlayerEntityFeature.GROUPING (524288)
            524288: ["join", "unjoin"],
        },
        "action_service_map": {
            "turn_on": "turn_on",
            "turn_off": "turn_off",
            "toggle": "toggle",
            "media_pause": "media_pause",
            "media_play": "media_play",
            "media_stop": "media_stop",
            "media_next_track": "media_next_track",
            "media_previous_track": "media_previous_track",
            "play_media": "play_media",
            "set_value": {
                "volume_level": "volume_set",
                "percentage": "volume_set",  # Alias for volume control
                "is_volume_muted": "volume_mute",
                "source": "select_source",
                "sound_mode": "select_sound_mode",
                "media_content_id": "play_media",
                "media_content_type": "play_media",  # For playlist/content type
                "shuffle": "shuffle_set",
                "repeat": "repeat_set",
            },
        },
    },
    # Lock entities
    "lock": {
        "base_services": ["lock", "unlock"],
        "feature_services": {},
        "action_service_map": {
            "turn_on": "lock",
            "turn_off": "unlock",
            "toggle": "toggle",
        },
    },
    # Switch entities (simple on/off)
    "switch": {
        "base_services": ["turn_on", "turn_off", "toggle"],
        "feature_services": {},
        "action_service_map": {
            "turn_on": "turn_on",
            "turn_off": "turn_off",
            "toggle": "toggle",
        },
    },
    # Input helpers
    "input_boolean": {
        "base_services": ["turn_on", "turn_off", "toggle"],
        "feature_services": {},
        "action_service_map": {
            "turn_on": "turn_on",
            "turn_off": "turn_off",
            "toggle": "toggle",
        },
    },
    "input_number": {
        "base_services": ["set_value", "increment", "decrement"],
        "feature_services": {},
        "action_service_map": {
            "set_value": {"value": "set_value"},
        },
    },
    "input_select": {
        "base_services": ["select_option", "select_next", "select_previous"],
        "feature_services": {},
        "action_service_map": {
            "set_value": {"option": "select_option"},
        },
    },
    "input_text": {
        "base_services": ["set_value"],
        "feature_services": {},
        "action_service_map": {
            "set_value": {"value": "set_value"},
        },
    },
    "input_datetime": {
        "base_services": ["set_datetime"],
        "feature_services": {},
        "action_service_map": {
            "set_value": "set_datetime",
        },
    },
    # Number helper
    "number": {
        "base_services": ["set_value"],
        "feature_services": {},
        "action_service_map": {
            "set_value": {"value": "set_value"},
        },
    },
    # Select helper
    "select": {
        "base_services": ["select_option", "select_next", "select_previous"],
        "feature_services": {},
        "action_service_map": {
            "set_value": {"option": "select_option"},
        },
    },
    # Text helper
    "text": {
        "base_services": ["set_value"],
        "feature_services": {},
        "action_service_map": {
            "set_value": {"value": "set_value"},
        },
    },
    # Humidifier
    "humidifier": {
        "base_services": ["turn_on", "turn_off", "toggle", "set_humidity"],
        "feature_services": {},
        "action_service_map": {
            "turn_on": "turn_on",
            "turn_off": "turn_off",
            "toggle": "toggle",
            "set_value": {"humidity": "set_humidity"},
        },
    },
    # Water heater
    "water_heater": {
        "base_services": ["turn_on", "turn_off", "set_temperature", "set_operation_mode"],
        "feature_services": {},
        "action_service_map": {
            "turn_on": "turn_on",
            "turn_off": "turn_off",
            "set_value": {
                "temperature": "set_temperature",
                "operation_mode": "set_operation_mode",
            },
        },
    },
    # Vacuum
    "vacuum": {
        "base_services": ["start", "pause", "stop", "return_to_base", "locate"],
        "feature_services": {},
        "action_service_map": {
            "turn_on": "start",
            "turn_off": "return_to_base",
            "toggle": "toggle",
        },
    },
    # Scene (only turn_on makes sense)
    "scene": {
        "base_services": ["turn_on"],
        "feature_services": {},
        "action_service_map": {
            "turn_on": "turn_on",
        },
    },
    # Script
    "script": {
        "base_services": ["turn_on", "turn_off", "toggle"],
        "feature_services": {},
        "action_service_map": {
            "turn_on": "turn_on",
            "turn_off": "turn_off",
            "toggle": "toggle",
        },
    },
    # Automation
    "automation": {
        "base_services": ["turn_on", "turn_off", "toggle", "trigger"],
        "feature_services": {},
        "action_service_map": {
            "turn_on": "turn_on",
            "turn_off": "turn_off",
            "toggle": "toggle",
        },
    },
    # Button
    "button": {
        "base_services": ["press"],
        "feature_services": {},
        "action_service_map": {
            "turn_on": "press",
        },
    },
    # Siren
    "siren": {
        "base_services": ["turn_on", "turn_off", "toggle"],
        "feature_services": {},
        "action_service_map": {
            "turn_on": "turn_on",
            "turn_off": "turn_off",
            "toggle": "toggle",
        },
    },
    # Alarm Control Panel
    "alarm_control_panel": {
        "base_services": ["alarm_arm_home", "alarm_arm_away", "alarm_arm_night", "alarm_disarm"],
        "feature_services": {},
        "action_service_map": {
            # Note: alarm control panel uses specific arm services, not generic turn_on/off
            "turn_on": "alarm_arm_home",  # Default to arm_home
            "turn_off": "alarm_disarm",
        },
    },
    # Valve
    "valve": {
        "base_services": ["open_valve", "close_valve", "toggle"],
        "feature_services": {
            # ValveEntityFeature.SET_POSITION (4)
            4: ["set_valve_position"],
            # ValveEntityFeature.STOP (8)
            8: ["stop_valve"],
        },
        "action_service_map": {
            "turn_on": "open_valve",
            "turn_off": "close_valve",
            "toggle": "toggle",
            "set_value": {"position": "set_valve_position"},
        },
    },
    # Lawn Mower
    "lawn_mower": {
        "base_services": ["start_mowing", "pause", "dock"],
        "feature_services": {},
        "action_service_map": {
            "turn_on": "start_mowing",
            "turn_off": "dock",
            "toggle": "toggle",
        },
    },
    # Camera
    "camera": {
        "base_services": ["turn_on", "turn_off"],
        "feature_services": {},
        "action_service_map": {
            "turn_on": "turn_on",
            "turn_off": "turn_off",
        },
    },
    # Group (aggregates multiple entities)
    "group": {
        "base_services": ["turn_on", "turn_off", "toggle"],
        "feature_services": {},
        "action_service_map": {
            "turn_on": "turn_on",
            "turn_off": "turn_off",
            "toggle": "toggle",
        },
    },
}

# Default system prompt - layered HEAD (frozen instructions, cache-stable) / TAIL
# (device catalog + live state, cache boundary partway through). The trailer line
# is appended by assembly code (agent/core.py::_build_system_prompt), not baked
# into either constant, so full-replacement prompts can supply their own or omit it.
DEFAULT_PROMPT_HEAD: Final = """You are a friendly but succinct AI voice assistant for {{ ha_name }}, a Home Assistant smart home.
- IMPORTANT: ALWAYS respond in the same language the user spoke. If English in → English out. If Spanish in → Spanish out. Never switch languages unprompted.

## Tools
**ha_control** — controls devices: turn on/off, set brightness, color, temperature, volume, etc.
**ha_query** — retrieves live device state; required for volatile entities.
{% if external_llm_enabled %}**query_external_llm** — delegates general-knowledge, educational, analytical, or open-ended questions to a more capable assistant.
{% endif %}
## How to Read the Device Tables
There are TWO tables at the end of this prompt:
1. DEVICE CATALOG — what exists in the house: entity_id, name, area, aliases, domain, services, volatile flag. Use it to resolve WHICH device the user means and to get the exact entity_id.
2. LIVE STATES — the current state and value for each entity_id, captured when this prompt was built (potentially seconds old).

Lookup process: resolve the device in the CATALOG → take its exact entity_id → read its state from LIVE STATES.

## Volatile Entities
Entities marked volatile=true in the CATALOG represent physical states that change faster than response latency (presence sensors, door contacts, motion). Their row in LIVE STATES is unreliable. Always call ha_query for volatile entities instead of reading LIVE STATES.

## Rules
1. Resolve the device in the DEVICE CATALOG first — before any tool call
2. Status of a non-volatile entity → answer from its row in LIVE STATES, no tools
3. Status of a volatile=true entity → call ha_query for live state
4. Control request → call ha_control with the exact entity_id from the CATALOG
5. Entity not in the CATALOG → say 'Device not found in configuration'
6. Multiple matches → ask which one
7. Some devices are controlled by smartplugs — if an entity is not found in its expected domain, check the switch domain
8. Always use the EXACT entity_id from the CATALOG — never shorten or guess
9. Never put tool calls in the content field — use tool_calls only
{% if external_llm_enabled %}10. Any general-knowledge, educational, analytical, or open-ended question MUST use query_external_llm; answer directly only for home state and control.
{% endif %}
## Service Parameters
turn_on / turn_off / toggle — no extra params
turn_on (light) — brightness_pct (0-100), rgb_color [R,G,B], color_temp optional
set_percentage (fan) — percentage 0-100
set_temperature (climate) — temperature value
set_cover_position — position 0-100
volume_set (media_player) — volume_level 0.0 to 1.0

## Response Style
- 4 sentences maximum, conversational tone
- No markdown, no emojis"""

DEFAULT_PROMPT_TAIL: Final = r"""## DEVICE CATALOG (resolve devices here first)
```csv
{{ state_attr('sensor.pepa_entity_context', 'csv') }}
```
{#- ============================================================
    CACHE BOUNDARY — everything above renders identically on
    every turn until the entity registry changes (pyscript
    republish). Everything below re-renders per utterance.
    Do not add volatile template calls above this line.
    ============================================================ -#}
## LIVE STATES (snapshot at prompt build — see volatile rule)
```csv
entity_id,state,current_value
{%- set _ctx = state_attr('sensor.pepa_entity_context', 'csv') or '' %}
{%- for line in _ctx.split('\n')[1:] %}
{%- set eid = line.split(',')[0] %}
{%- if '.' in eid %}
{%- set d = eid.split('.')[0] %}
{%- set ns = namespace(cv='') %}
{%- if d == 'light' %}
{%- set bri = state_attr(eid, 'brightness') %}
{%- set ns.cv = ((bri | int / 255.0 * 100) | round(0) | int | string) if bri else '' %}
{%- elif d == 'fan' %}
{%- set ns.cv = state_attr(eid, 'percentage') | default('') | string %}
{%- elif d == 'climate' %}
{%- set ns.cv = state_attr(eid, 'temperature') | default('') | string %}
{%- elif d == 'cover' %}
{%- set ns.cv = state_attr(eid, 'current_position') | default('') | string %}
{%- elif d == 'media_player' %}
{%- set ns.cv = state_attr(eid, 'volume_level') | default('') | string %}
{%- endif %}
{{ eid }},{{ states(eid) }},{{ ns.cv }}
{%- endif %}
{%- endfor %}
```
## Current Environment
Your immediate area is: {{ area_name(area_id(current_device_id)) | default('unspecified') }}
Time: {{ now() }}

## Retrieved Context (memories and related information)
{{ entity_context }}"""

PROMPT_TRAILER: Final = "Now respond to the user's request:"
