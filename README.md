# Pepa Sensory Arm

[![Version](https://img.shields.io/badge/version-0.1.0-blue.svg)](https://github.com/prsws/pepa-sensory-arm/releases)
[![Build Status](https://github.com/prsws/pepa-sensory-arm/workflows/CI/badge.svg)](https://github.com/prsws/pepa-sensory-arm/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2026.6+-blue.svg)](https://www.home-assistant.io/)
[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz/)

A highly customizable Home Assistant custom component that performs as the sensory arm of the Pepa system.
AI capabilities include advanced tool calling, context injection, and conversation history management.

## What's New in v0.1.0-alpha

- **New version numbering** - PAS is now independent and protected from automatic upstream changes. 
- **Initial advanced context management** - Still alpha but a solid foundation for memory collection.
- **Updated requirements and installation instructions** - Read them thoroughly.

[View Full Changelog](https://github.com/prsws/pepa-sensory-arm/releases)

---

## Overview

Pepa Sensory Arm extends Home Assistant's native conversation platform to enable natural language control and monitoring of your smart home. It works with any OpenAI-compatible LLM provider, giving you flexibility to use cloud services or run models locally.

**Key Capabilities:**
- Natural language home control through any OpenAI-compatible LLM
- Automatic context injection - LLM knows your home's current state
- Persistent conversation memory across interactions
- Extensible tool system for custom integrations
- Streaming responses for voice assistants
- Long-term memory system for personalized experiences

## Features

### Core Features

- **LLM Integration** - Works with OpenAI, Azure OpenAI, Ollama, LocalAI, LM Studio, or any OpenAI-compatible endpoint
- **Entity Context** - Automatically provides relevant entity states to the LLM
- **Conversation History** - Maintains context across multiple interactions with persistent storage
- **Native Tools** - Built-in `ha_control` and `ha_query` tools for home automation
- **Custom Tools** - Define REST API and Home Assistant service tools in configuration
- **Event System** - Rich events for automation triggers and monitoring
- **Streaming Responses** - Low-latency streaming for voice assistant integration (~10x faster)

### Advanced Features

- **Vector Database Integration** - Semantic entity search using ChromaDB for efficient context management
- **Multi-LLM Support** - Use a fast local model for control + powerful cloud model for analysis
- **Memory System** - Automatic extraction and recall of facts, preferences, and context
- **Context Optimization** - Intelligent compression to stay within token limits
- **Tool Progress Indicators** - Real-time feedback during tool execution

## Requirements

### Required
- **Home Assistant** - Version 2026.6.1 or later (for Python 3.14 support)
- **Python Dependencies** - `aiohttp >= 3.9.0` (included with Home Assistant)
- **HACS** - Home Assistant Community Store (required for installation)
- **Pyscript** - Python HACS integration

### Optional (Enable Advanced Features)
- **ChromaDB** - For vector database context mode
  - `chromadb-client == 1.5.3`
  - Required for: Vector DB context injection and memory system
- **OpenAI** - For embeddings in vector DB mode
  - `openai >= 1.3.8`
  - Required for: Vector DB entity indexing (alternative: use Ollama)
- **Wyoming Protocol STT/TTS** - For streaming responses
  - Required for: Low-latency voice assistant integration

## Installation

### HACS (Recommended)

1. **In HACS, install Pyscript if not already running** refer to its docs
2. Return to HACS, go to **Integrations** → **⋮** → **Custom repositories**
2. Add repository: `https://github.com/prsws/pepa-sensory-arm`
3. Category: **Integration**
4. Click **Add**
5. Search for "Pepa Sensory Arm" in HACS
6. Click **Install**
7. Restart Home Assistant
8. Go to Settings > Devices & Services > Add Integration
9. Search for "Pepa Sensory Arm" and follow the setup wizard

### Manual Installation

1. Download the latest release from GitHub
2. Copy the `custom_components/pepa_sensory_arm` directory to your Home Assistant `config/custom_components` folder
3. Restart Home Assistant
4. Go to Settings > Devices & Services > Add Integration
5. Search for "Pepa Sensory Arm" and complete the configuration

**For detailed installation instructions, see [Installation Guide](docs/INSTALLATION.md)**

## Quick Start

### 1. Add the Integration

Navigate to Settings > Devices & Services > Add Integration, search for "Pepa Sensory Arm", and configure:

- **Name**: Friendly name (e.g., "Pepa Sensory Arm")
- **LLM Base URL**: Your OpenAI-compatible endpoint
  - OpenAI: `https://api.openai.com/v1`
  - Azure OpenAI: `https://<resource>.openai.azure.com/openai/deployments/<deployment>`
  - Ollama (local): `http://localhost:11434/v1`
  - LocalAI: Your LocalAI URL
- **API Key**: Your API key (if required)
- **Model**: Model name (e.g., `gpt-4o-mini`, `llama3.2`, etc.)
- **Temperature**: 0.7 (recommended for most use cases)
- **Max Tokens**: 500 (adjust based on your needs)

### 2. Test Basic Functionality

Call the conversation service:

```yaml
service: pepa_sensory_arm.process
data:
  text: "Turn on the living room lights"
```

### 3. Explore Advanced Configuration

Access Settings > Devices & Services > Pepa Sensory Arm > Configure to:
- Configure context injection mode (direct or vector DB)
- Enable conversation history
- Set up custom tools
- Configure external LLM for complex queries
- Enable memory system
- Enable streaming for voice assistants

**For detailed configuration options, see [Configuration Reference](docs/CONFIGURATION.md)**

## Documentation

### Quick Start Guides
- [Installation](docs/INSTALLATION.md) - Get up and running in minutes
- [Configuration](docs/CONFIGURATION.md) - Essential settings explained
- [Example Configurations](docs/EXAMPLE_CONFIGS.md) - Ready-to-use configs for common providers
- [FAQ](docs/FAQ.md) - Top 20 questions answered

### Feature Guides
- [Memory System](docs/MEMORY_SYSTEM.md) - Enable long-term memory
- [Vector DB Setup](docs/VECTOR_DB_SETUP.md) - Semantic entity search
- [Custom Tools](docs/CUSTOM_TOOLS.md) - Extend with REST APIs and services
- [External LLM](docs/EXTERNAL_LLM.md) - Multi-LLM workflows

### Reference
- [Architecture Overview](docs/ARCHITECTURE.md) - Component diagrams and system design
- [API Reference](docs/API_REFERENCE.md) - Services, events, and tools
- [Troubleshooting](docs/TROUBLESHOOTING.md) - Quick fixes for common issues
- [Examples](docs/EXAMPLES.md) - 10 ready-to-use examples
- [Migration Guide](docs/MIGRATION.md) - Moving from extended_openai_conversation

## Usage Examples

### Voice Control

```yaml
# Use with Home Assistant voice assistant
# Just speak naturally to your voice assistant
"Turn on the kitchen lights to 50%"
"What's the temperature in the living room?"
"Is the front door locked?"
```

### Automation Integration

```yaml
automation:
  - alias: "Morning Briefing"
    trigger:
      - platform: time
        at: "07:00:00"
    action:
      - service: pepa_sensory_arm.process
        data:
          text: "Good morning! Please prepare for the day."
          conversation_id: "morning_routine"
```

### Custom Tool Example

```yaml
# configuration.yaml
pepa_sensory_arm:
  tools_custom:
    - name: check_weather
      description: "Get weather forecast"
      handler:
        type: rest
        url: "https://api.open-meteo.com/v1/forecast"
        method: GET
        query_params:
          latitude: "47.6062"
          longitude: "-122.3321"
          current: "temperature_2m,precipitation"
```

**For more examples, see [Examples Documentation](docs/EXAMPLES.md)**

## Voice Conversation Persistence

Pepa Sensory Arm automatically maintains conversation context across multiple voice interactions, enabling natural multi-turn conversations with your voice assistant.

### How It Works

- Each user/device combination maintains a persistent conversation session
- Sessions automatically expire after 1 hour of inactivity (configurable)
- Conversation history is preserved within each session
- Different devices maintain independent conversation contexts

### Example

**Before (without persistence):**
```
User: "What's the temperature in the living room?"
Agent: "The living room is 72°F"

[Later]
User: "What about the bedroom?"
Agent: "I don't have context about what you're asking about"
```

**After (with persistence):**
```
User: "What's the temperature in the living room?"
Agent: "The living room is 72°F"

[Later]
User: "What about the bedroom?"
Agent: "The bedroom temperature is 68°F"
```

### Configuration

Configure the session timeout in integration settings:
- Minimum: 60 seconds (1 minute)
- Maximum: 86400 seconds (24 hours)
- Default: 3600 seconds (1 hour)

### Clearing Conversations

Reset your conversation context using the `clear_conversation` service:

```yaml
# Clear conversation for current user/device
service: pepa_sensory_arm.clear_conversation

# Clear conversation for specific device
service: pepa_sensory_arm.clear_conversation
data:
  device_id: "kitchen_satellite"

# Clear all conversations
service: pepa_sensory_arm.clear_conversation
```

### Multi-Device Behavior

Each device maintains its own conversation context:
- Kitchen satellite remembers kitchen-related conversations
- Bedroom satellite has independent context
- Same user on different devices = different conversations

## System Prompt

The system prompt is configured via **System Prompt** in the integration's options, with two independent toggles that together produce four states:

| Use Default | Append Custom Additions | Result |
|---|---|---|
| On | Off | Built-in default prompt only |
| On | On | Default prompt, with your additions spliced in **before** the device tables (inside the cacheable prefix) |
| Off | *(ignored)* | Your full-replacement prompt, used verbatim |

- **Default mode** builds the prompt from a frozen instructions block followed by the device catalog and live entity states, and automatically appends the trailer line that hands off to the model. This layering keeps the instructions/device-catalog portion identical between turns so it can be served from an LLM prefix cache — only the live-state section changes per utterance.
- **Additions** (when enabled) are inserted verbatim, with no automatic heading, immediately before the device tables — still inside the cached prefix. Supply your own heading if you want one.
- **Full replacement** disables the default prompt entirely. You own the entire prompt text, including any device context and trailer — nothing is prepended or appended. If left empty, the integration logs an error and falls back to the default prompt rather than sending an empty system prompt.

### Context composition

Context composition follows the prompt mode:

- **Default prompt mode**: device context comes **exclusively** from the pyscript CSV tables (`sensor.pepa_entity_context`) baked into the prompt. The prompt's **Retrieved Context** section carries only memories and additional-collection results — no entity retrieval runs per turn. If a retrieval leg fails, it contributes nothing (the section may be empty); it never injects fallback banners or "no context" placeholders.
- **Full replacement mode**: the legacy behavior is preserved — entity context is gathered per the **Context Mode** setting (Direct or Vector DB), merged with memories, and additional-collection results are appended when configured.

The **Context Mode** setting (Direct vs. Vector DB) therefore applies **only** to full-replacement prompts; it has no effect in default prompt mode.

### Template variables

Custom prompts (additions and full replacements) are Jinja-rendered with these variables:

- `conversation_context` — the composed retrieved context (memories, additional-collection results, and — in replacement mode — entity context).
- `entity_context` — **deprecated** alias of `conversation_context`, retained so existing custom prompts keep working. Prefer `conversation_context` in new prompts.
- `exposed_entities` — structured list of entities exposed to Assist. Only computed when the assembled prompt actually references it, so default-mode turns skip the registry walk.
- `ha_name`, `current_device_id`, `conversation_id`, `user_message`, `external_llm_enabled` — as before.

### Memory search degradation

Memory search uses ChromaDB semantic search whenever ChromaDB is available, regardless of the Context Mode setting. If ChromaDB is unreachable, memory search degrades to a local keyword search and a warning is logged for each degraded search — results may be less relevant, but memory recall never silently disappears.

### Cache discipline warning

Both the additions and full-replacement fields are Jinja-rendered, exactly like the default prompt. Any volatile template call — `now()`, `states()`, `state_attr()`, etc. — placed in the **additions** field runs on every turn and breaks the prefix cache for the entire prompt, measurably slowing every response. Whatever you put in either field is your responsibility; there is no sanitization or guardrail against this.

### Pyscript requirement (default mode only)

The default prompt's device catalog and live-state tables read `sensor.pepa_entity_context`, published by the bundled pyscript scripts (`custom_components/pyscript/entities_list.py` and `entity_context.py`). **There is no fallback** to Home Assistant's `exposed_entities` if this sensor is missing or empty — the device tables will simply be empty, and the integration logs a startup warning when this happens. Make sure the pyscript integration is installed and the bundled scripts are enabled if you use the default prompt.

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Write tests for new functionality
4. Ensure all tests pass (`pytest tests/`)
5. Follow the coding standards in [Development Guide](docs/DEVELOPMENT.md)
6. Submit a pull request

## Testing

Pepa Sensory Arm maintains >80% code coverage with comprehensive unit and integration tests:

```bash
# Set up environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements_dev.txt

# Run tests
pytest tests/unit/ -v

# Run with coverage
pytest tests/ --cov=custom_components.pepa_sensory_arm --cov-report=html
```

**Test Status**: 400+ passing tests across core functionality, vector DB, memory system, custom tools, and streaming.

## Support

- **Issues**: [GitHub Issues](https://github.com/prsws/pepa-sensory-arm/issues)
- **Discussions**: [GitHub Discussions](https://github.com/prsws/pepa-sensory-arm/discussions)
- **Documentation**: See [docs/](docs/) directory

## License

MIT License

## Credits

Based on Home Agent by Anton Radlein. Built with inspiration from the extended_openai_conversation integration. Special thanks to the Home Assistant community.

## Changelog

### v0.1.0 (Latest)
- **New version numbering** - PAS is now independent and protected from automatic upstream changes. 
- **Initial advanced context management** - Still alpha but a solid foundation for memory collection.
- **Updated requirements and installation instructions** - Read them thoroughly.


### v0.9.5 (from upstream)
- **New Release**: Initial release as Pepa Sensory Arm
