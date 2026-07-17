"""Unit tests for PepaSensoryArm._build_system_prompt (PSA prompt assembly)."""

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import jinja2
import pytest
from homeassistant.core import HomeAssistant

from custom_components.pepa_sensory_arm.agent import PepaSensoryArm
from custom_components.pepa_sensory_arm.const import (
    CONF_EXTERNAL_LLM_ENABLED,
    CONF_LLM_MODEL,
    CONF_PROMPT_CUSTOM,
    CONF_PROMPT_CUSTOM_ADDITIONS,
    CONF_PROMPT_USE_CUSTOM,
    CONF_PROMPT_USE_DEFAULT,
    DEFAULT_PROMPT_HEAD,
    DEFAULT_PROMPT_TAIL,
    PROMPT_TRAILER,
)

_TEMPLATE_PATCH = "custom_components.pepa_sensory_arm.agent.core.template.Template"


class _FakeTemplate:
    """Real-Jinja2 stand-in for homeassistant.helpers.template.Template.

    Evaluates {{ }}/{% %} for real (so `external_llm_enabled` if-blocks and
    variable substitution behave correctly) without needing a live HA
    instance for HA-specific globals like state_attr/area_name/now.
    """

    _ENV = jinja2.Environment()
    _ENV.globals.update(
        state_attr=lambda *a, **k: None,
        states=lambda *a, **k: "",
        area_id=lambda *a, **k: None,
        area_name=lambda *a, **k: None,
        now=lambda: "2026-01-01T00:00:00",
        is_state=lambda *a, **k: False,
    )

    def __init__(self, template_str, hass=None):
        self.template_str = template_str

    def async_render(self, variables=None):
        return self._ENV.from_string(self.template_str).render(**(variables or {}))


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = MagicMock(spec=HomeAssistant)
    hass.states = MagicMock()
    hass.states.async_all = MagicMock(return_value=[])
    hass.data = {}
    hass.bus = MagicMock()
    hass.bus.async_fire = MagicMock()
    hass.config = MagicMock()
    hass.config.location_name = "Casa Delta"
    return hass


@pytest.fixture
def agent(mock_hass):
    """Create a PepaSensoryArm instance with entity lookups stubbed out."""
    from custom_components.pepa_sensory_arm.conversation_session import ConversationSessionManager

    config = {CONF_LLM_MODEL: "llama2"}
    session_manager = ConversationSessionManager(mock_hass)
    instance = PepaSensoryArm(mock_hass, config, session_manager)
    instance.get_exposed_entities = MagicMock(return_value=[])
    return instance


@pytest.fixture(autouse=True)
def _patch_template():
    with patch(_TEMPLATE_PATCH, _FakeTemplate):
        yield


class TestTruthTableStates:
    """Spec §9 item 1: four truth-table states produce the expected order."""

    def test_default_only(self, agent):
        agent.config[CONF_PROMPT_USE_DEFAULT] = True
        agent.config[CONF_PROMPT_USE_CUSTOM] = False

        result = agent._build_system_prompt()

        head_idx = result.find("friendly but succinct AI voice assistant")
        tail_idx = result.find("## DEVICE CATALOG (resolve devices here first)")
        trailer_idx = result.find(PROMPT_TRAILER)
        assert head_idx != -1
        assert tail_idx != -1
        assert trailer_idx != -1
        assert head_idx < tail_idx < trailer_idx
        assert result.rstrip().endswith(PROMPT_TRAILER)
        assert result.count(PROMPT_TRAILER) == 1

    def test_default_with_additions(self, agent):
        agent.config[CONF_PROMPT_USE_DEFAULT] = True
        agent.config[CONF_PROMPT_USE_CUSTOM] = True
        agent.config[CONF_PROMPT_CUSTOM_ADDITIONS] = "House rule: quiet hours after 10pm."

        result = agent._build_system_prompt()

        head_idx = result.find("friendly but succinct AI voice assistant")
        additions_idx = result.find("House rule: quiet hours after 10pm.")
        tail_idx = result.find("## DEVICE CATALOG (resolve devices here first)")
        trailer_idx = result.find(PROMPT_TRAILER)
        assert -1 not in (head_idx, additions_idx, tail_idx, trailer_idx)
        assert head_idx < additions_idx < tail_idx < trailer_idx
        assert "## Additional Context" not in result

    def test_full_replacement(self, agent):
        agent.config[CONF_PROMPT_USE_DEFAULT] = False
        agent.config[CONF_PROMPT_USE_CUSTOM] = True  # should be ignored
        agent.config[CONF_PROMPT_CUSTOM] = "You are a minimal test assistant."

        result = agent._build_system_prompt()

        assert result == "You are a minimal test assistant."
        assert PROMPT_TRAILER not in result
        assert "DEVICE CATALOG" not in result

    def test_full_replacement_ignores_use_custom_false(self, agent):
        agent.config[CONF_PROMPT_USE_DEFAULT] = False
        agent.config[CONF_PROMPT_USE_CUSTOM] = False
        agent.config[CONF_PROMPT_CUSTOM] = "Another minimal prompt."

        result = agent._build_system_prompt()

        assert result == "Another minimal prompt."


class TestUseCustomEmptyAdditions:
    """Spec §9 item 2: use_custom=True with empty additions == use_custom=False."""

    def test_empty_additions_falls_back_to_default_only(self, agent):
        agent.config[CONF_PROMPT_USE_DEFAULT] = True
        agent.config[CONF_PROMPT_USE_CUSTOM] = True
        agent.config[CONF_PROMPT_CUSTOM_ADDITIONS] = "   "  # whitespace only

        with_empty = agent._build_system_prompt()

        agent.config[CONF_PROMPT_USE_CUSTOM] = False
        without_custom = agent._build_system_prompt()

        assert with_empty == without_custom


class TestEmptyFullPromptFallback:
    """Spec §9 item 3: use_default=False with empty full prompt logs an error
    and falls back to the default assembly (True/False row)."""

    def test_empty_full_prompt_falls_back_and_logs(self, agent, caplog):
        agent.config[CONF_PROMPT_USE_DEFAULT] = False
        agent.config[CONF_PROMPT_CUSTOM] = ""
        agent.config[CONF_PROMPT_USE_CUSTOM] = True
        agent.config[CONF_PROMPT_CUSTOM_ADDITIONS] = "should be ignored by the fallback"

        with caplog.at_level(logging.ERROR):
            result = agent._build_system_prompt()

        assert any("prompt_custom is empty" in record.getMessage() for record in caplog.records)
        # Falls back to the True/False row, not True/True - additions are not spliced in.
        assert "should be ignored by the fallback" not in result
        assert "DEVICE CATALOG" in result
        assert result.rstrip().endswith(PROMPT_TRAILER)


class TestSinglePassRender:
    """Spec §9 item 4: additions containing {{ ha_name }} render correctly,
    proving the assembled string is rendered in a single pass."""

    def test_additions_template_var_renders(self, agent):
        agent.config[CONF_PROMPT_USE_DEFAULT] = True
        agent.config[CONF_PROMPT_USE_CUSTOM] = True
        agent.config[CONF_PROMPT_CUSTOM_ADDITIONS] = "Welcome to {{ ha_name }}!"

        result = agent._build_system_prompt()

        assert "Welcome to Casa Delta!" in result
        assert "{{ ha_name }}" not in result


class TestExternalLlmEnabledToggle:
    """Spec §9 item 5: external_llm_enabled toggles tool/rule text in HEAD."""

    def test_disabled_omits_external_llm_content(self, agent):
        agent.config[CONF_EXTERNAL_LLM_ENABLED] = False
        agent.config[CONF_PROMPT_USE_DEFAULT] = True

        result = agent._build_system_prompt()

        assert "query_external_llm" not in result
        assert "MUST use query_external_llm" not in result

    def test_enabled_includes_external_llm_content(self, agent):
        agent.config[CONF_EXTERNAL_LLM_ENABLED] = True
        agent.config[CONF_PROMPT_USE_DEFAULT] = True

        result = agent._build_system_prompt()

        assert "query_external_llm" in result
        assert "MUST use query_external_llm" in result


class TestTrailerNotInPromptConstants:
    """Spec §9 item 6: trailer string is not baked into HEAD/TAIL (regression guard)."""

    def test_trailer_absent_from_head_and_tail(self):
        assert PROMPT_TRAILER not in DEFAULT_PROMPT_HEAD
        assert PROMPT_TRAILER not in DEFAULT_PROMPT_TAIL

    def test_trailer_appears_exactly_once_in_const_source(self):
        const_path = (
            Path(__file__).parents[2] / "custom_components" / "pepa_sensory_arm" / "const.py"
        )
        source = const_path.read_text()
        assert source.count(PROMPT_TRAILER) == 1

    def test_default_system_prompt_removed(self):
        const_path = (
            Path(__file__).parents[2] / "custom_components" / "pepa_sensory_arm" / "const.py"
        )
        source = const_path.read_text()
        assert "DEFAULT_SYSTEM_PROMPT" not in source


class TestConversationContextTemplateVar:
    """conversation_context is the template variable; entity_context is a deprecated alias."""

    def test_conversation_context_and_alias_render_identically(self, agent):
        agent.config[CONF_PROMPT_USE_DEFAULT] = False
        agent.config[CONF_PROMPT_CUSTOM] = "A:{{ conversation_context }}|B:{{ entity_context }}"

        result = agent._build_system_prompt(conversation_context="THE CONTEXT")

        assert result == "A:THE CONTEXT|B:THE CONTEXT"

    def test_default_tail_renders_context_under_retrieved_context_heading(self, agent):
        agent.config[CONF_PROMPT_USE_DEFAULT] = True
        agent.config[CONF_PROMPT_USE_CUSTOM] = False

        result = agent._build_system_prompt(conversation_context="MEMORY AND RETRIEVAL BLOB")

        heading_idx = result.find("## Retrieved Context (memories and related information)")
        context_idx = result.find("MEMORY AND RETRIEVAL BLOB")
        trailer_idx = result.find(PROMPT_TRAILER)
        assert -1 not in (heading_idx, context_idx, trailer_idx)
        assert heading_idx < context_idx < trailer_idx

    def test_default_tail_no_longer_references_entity_context(self):
        """Regression guard: the TAIL uses conversation_context, not entity_context."""
        assert "{{ entity_context }}" not in DEFAULT_PROMPT_TAIL
        assert "{{ conversation_context }}" in DEFAULT_PROMPT_TAIL

    def test_entity_context_sensor_reference_untouched(self):
        """The pyscripts sensor name is not affected by the template-var rename."""
        assert "sensor.pepa_entity_context" in DEFAULT_PROMPT_TAIL


class TestExposedEntitiesGating:
    """get_exposed_entities only runs when the assembled prompt references it."""

    def test_default_prompt_skips_exposed_entities(self, agent):
        agent.config[CONF_PROMPT_USE_DEFAULT] = True
        agent.config[CONF_PROMPT_USE_CUSTOM] = False

        agent._build_system_prompt(conversation_context="ctx")

        agent.get_exposed_entities.assert_not_called()

    def test_replacement_prompt_without_reference_skips_exposed_entities(self, agent):
        agent.config[CONF_PROMPT_USE_DEFAULT] = False
        agent.config[CONF_PROMPT_CUSTOM] = "No entity var here: {{ conversation_context }}"

        agent._build_system_prompt(conversation_context="ctx")

        agent.get_exposed_entities.assert_not_called()

    def test_replacement_prompt_with_reference_computes_exposed_entities(self, agent):
        agent.config[CONF_PROMPT_USE_DEFAULT] = False
        agent.config[CONF_PROMPT_CUSTOM] = "Devices: {{ exposed_entities }}"

        result = agent._build_system_prompt(conversation_context="ctx")

        agent.get_exposed_entities.assert_called_once()
        assert result == "Devices: []"

    def test_additions_referencing_exposed_entities_compute_it(self, agent):
        agent.config[CONF_PROMPT_USE_DEFAULT] = True
        agent.config[CONF_PROMPT_USE_CUSTOM] = True
        agent.config[CONF_PROMPT_CUSTOM_ADDITIONS] = "Extra: {{ exposed_entities }}"

        agent._build_system_prompt(conversation_context="ctx")

        agent.get_exposed_entities.assert_called_once()
