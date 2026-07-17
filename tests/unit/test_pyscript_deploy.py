"""Unit tests for the pyscript payload deployment mechanism.

Covers the deployment-state gate in async_setup_entry, the Repair fix flow,
and payload cleanup in async_remove_entry.
"""

import shutil
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from custom_components.pepa_sensory_arm import (
    async_remove_entry,
    async_setup_entry,
    pyscript_deploy,
)
from custom_components.pepa_sensory_arm.const import CONF_PROMPT_USE_DEFAULT, DOMAIN
from custom_components.pepa_sensory_arm.pyscript_deploy import (
    ISSUE_PYSCRIPT_PAYLOAD_MISSING,
    PAYLOAD_FILES,
    PAYLOAD_SOURCE_DIR,
    DeploymentState,
    check_deployment_sync,
    deploy_payload_sync,
    remove_payload_sync,
)
from custom_components.pepa_sensory_arm.repairs import (
    PyscriptPayloadFixFlow,
    async_create_fix_flow,
)


@pytest.fixture
def mock_hass(tmp_path):
    """Create a mock Home Assistant instance backed by a real tmp config dir."""
    hass = MagicMock(spec=HomeAssistant)
    hass.data = {}
    hass.services = MagicMock()
    hass.services.has_service = MagicMock(return_value=False)
    hass.services.async_register = MagicMock()
    hass.config_entries = MagicMock()
    hass.config = MagicMock()
    hass.config.config_dir = str(tmp_path)
    hass.config.path = MagicMock(side_effect=lambda *parts: str(tmp_path.joinpath(*parts)))
    # Run executor jobs inline: the file I/O under test is real, just synchronous.
    hass.async_add_executor_job = AsyncMock(side_effect=lambda func, *args: func(*args))
    hass.states = MagicMock()
    hass.states.get = MagicMock(return_value=None)
    return hass


@pytest.fixture
def mock_config_entry():
    """Create a mock config entry with the default prompt enabled."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry_123"
    entry.data = {
        "llm_base_url": "http://localhost:11434/v1",
        "llm_model": "gemma4:e4b",
    }
    entry.options = {}
    entry.add_update_listener = MagicMock(return_value=lambda: None)
    entry.async_on_unload = MagicMock()
    return entry


@pytest.fixture
def entity_context_sensor():
    """A sensor.pepa_entity_context state with a populated csv attribute."""
    state = MagicMock()
    state.attributes = {"csv": "entity_id,name\nlight.kitchen,Kitchen"}
    return state


@pytest.fixture(autouse=True)
def setup_dependency_mocks():
    """Patch the setup machinery unrelated to the deployment gate.

    These tests exercise the gate, not agent/session/service wiring, which
    test_init.py already covers.
    """
    with (
        patch("custom_components.pepa_sensory_arm.ConversationSessionManager") as session_cls,
        patch("custom_components.pepa_sensory_arm.PepaSensoryArm") as agent_cls,
        patch("custom_components.pepa_sensory_arm.ha_conversation.async_set_agent") as set_agent,
        patch("custom_components.pepa_sensory_arm.async_setup_services", new=AsyncMock()),
        patch("custom_components.pepa_sensory_arm.ChromaClientFactory") as factory_cls,
        patch("custom_components.pepa_sensory_arm.memory_manager.MemoryManager") as memory_cls,
    ):
        session_manager = MagicMock()
        session_manager.async_load = AsyncMock()
        session_cls.return_value = session_manager
        agent = MagicMock()
        agent.conversation_manager.setup_scheduled_cleanup = MagicMock()
        agent_cls.return_value = agent
        factory = MagicMock()
        factory.async_setup = AsyncMock()
        factory.health_check = AsyncMock(return_value=(True, "ChromaDB healthy"))
        factory.placement = "remote"
        factory_cls.return_value = factory
        memory_manager = MagicMock()
        memory_manager.async_initialize = AsyncMock()
        memory_cls.return_value = memory_manager
        yield {"set_agent": set_agent}


@pytest.fixture
def mock_ir():
    """Patch the issue registry helper as imported by __init__.py."""
    with patch("custom_components.pepa_sensory_arm.ir") as ir:
        yield ir


def pyscript_dir(tmp_path):
    """The deployment target directory for the mocked config dir."""
    return tmp_path / "pyscript"


def deploy_current_payload(tmp_path):
    """Put an up-to-date copy of the payload in the target directory."""
    target = pyscript_dir(tmp_path)
    target.mkdir(parents=True, exist_ok=True)
    for name in PAYLOAD_FILES:
        shutil.copyfile(PAYLOAD_SOURCE_DIR / name, target / name)
    return target


class TestCheckDeploymentSync:
    """Test the pure state-inspection helper."""

    def test_missing_when_directory_absent(self, tmp_path):
        state, pending = check_deployment_sync(pyscript_dir(tmp_path))
        assert state is DeploymentState.MISSING
        assert sorted(pending) == sorted(PAYLOAD_FILES)

    def test_missing_when_any_file_absent(self, tmp_path):
        target = deploy_current_payload(tmp_path)
        (target / PAYLOAD_FILES[0]).unlink()
        state, pending = check_deployment_sync(target)
        assert state is DeploymentState.MISSING
        assert PAYLOAD_FILES[0] in pending

    def test_stale_when_any_file_differs(self, tmp_path):
        target = deploy_current_payload(tmp_path)
        with open(target / PAYLOAD_FILES[1], "a", encoding="utf-8") as handle:
            handle.write("\n# local edit\n")
        state, pending = check_deployment_sync(target)
        assert state is DeploymentState.STALE
        assert pending == [PAYLOAD_FILES[1]]

    def test_current_when_all_identical(self, tmp_path):
        target = deploy_current_payload(tmp_path)
        state, pending = check_deployment_sync(target)
        assert state is DeploymentState.CURRENT
        assert pending == []


class TestSetupGateMissing:
    """Spec test 1: MISSING raises the Repair issue and ConfigEntryNotReady."""

    async def test_missing_payload_raises_issue_and_not_ready(
        self, mock_hass, mock_config_entry, mock_ir, setup_dependency_mocks, tmp_path
    ):
        with pytest.raises(ConfigEntryNotReady):
            await async_setup_entry(mock_hass, mock_config_entry)

        mock_ir.async_create_issue.assert_called_once()
        args, kwargs = mock_ir.async_create_issue.call_args
        assert args[1] == DOMAIN
        assert args[2] == ISSUE_PYSCRIPT_PAYLOAD_MISSING
        assert kwargs["is_fixable"] is True
        assert kwargs["translation_key"] == ISSUE_PYSCRIPT_PAYLOAD_MISSING

        # Setup must not complete: the agent is never registered and the
        # fix flow (not setup) performs the copy.
        setup_dependency_mocks["set_agent"].assert_not_called()
        assert not pyscript_dir(tmp_path).exists()


class TestFixFlow:
    """Spec test 2: confirming the fix flow deploys the payload."""

    def make_flow(self, mock_hass):
        flow = PyscriptPayloadFixFlow()
        flow.hass = mock_hass
        flow.flow_id = "test_flow"
        flow.handler = DOMAIN
        return flow

    async def test_create_fix_flow_returns_flow(self, mock_hass):
        flow = await async_create_fix_flow(mock_hass, ISSUE_PYSCRIPT_PAYLOAD_MISSING, None)
        assert isinstance(flow, PyscriptPayloadFixFlow)

    async def test_init_step_shows_confirm_form(self, mock_hass):
        flow = self.make_flow(mock_hass)
        result = await flow.async_step_init()
        assert result["type"] == "form"
        assert result["step_id"] == "confirm"

    async def test_confirm_copies_payload_and_deletes_issue(self, mock_hass, tmp_path):
        flow = self.make_flow(mock_hass)
        assert not pyscript_dir(tmp_path).exists()

        with patch("custom_components.pepa_sensory_arm.repairs.ir") as repairs_ir:
            result = await flow.async_step_confirm(user_input={})

        assert result["type"] == "create_entry"
        target = pyscript_dir(tmp_path)
        for name in PAYLOAD_FILES:
            assert (target / name).read_bytes() == (PAYLOAD_SOURCE_DIR / name).read_bytes()
        repairs_ir.async_delete_issue.assert_called_once_with(
            mock_hass, DOMAIN, ISSUE_PYSCRIPT_PAYLOAD_MISSING
        )

    async def test_confirm_overwrites_existing_files(self, mock_hass, tmp_path):
        target = pyscript_dir(tmp_path)
        target.mkdir(parents=True)
        (target / PAYLOAD_FILES[0]).write_text("# stray old copy\n", encoding="utf-8")

        flow = self.make_flow(mock_hass)
        with patch("custom_components.pepa_sensory_arm.repairs.ir"):
            await flow.async_step_confirm(user_input={})

        source = (PAYLOAD_SOURCE_DIR / PAYLOAD_FILES[0]).read_bytes()
        assert (target / PAYLOAD_FILES[0]).read_bytes() == source


class TestSetupGateStale:
    """Spec test 3: STALE files are silently overwritten, setup proceeds."""

    async def test_stale_file_overwritten_without_issue(
        self, mock_hass, mock_config_entry, mock_ir, entity_context_sensor, tmp_path
    ):
        target = deploy_current_payload(tmp_path)
        stale_file = target / PAYLOAD_FILES[2]
        with open(stale_file, "a", encoding="utf-8") as handle:
            handle.write("\n# drift from an older release\n")
        untouched_before = (target / PAYLOAD_FILES[0]).stat().st_mtime_ns

        mock_hass.states.get.return_value = entity_context_sensor
        result = await async_setup_entry(mock_hass, mock_config_entry)

        assert result is True
        assert stale_file.read_bytes() == (PAYLOAD_SOURCE_DIR / PAYLOAD_FILES[2]).read_bytes()
        # Only the differing file is rewritten.
        assert (target / PAYLOAD_FILES[0]).stat().st_mtime_ns == untouched_before
        mock_ir.async_create_issue.assert_not_called()


class TestSetupGateCurrent:
    """Spec test 4: CURRENT + live sensor means no issue and no writes."""

    async def test_current_payload_proceeds_without_writes(
        self, mock_hass, mock_config_entry, mock_ir, entity_context_sensor, tmp_path
    ):
        deploy_current_payload(tmp_path)
        mock_hass.states.get.return_value = entity_context_sensor

        with patch(
            "custom_components.pepa_sensory_arm.pyscript_deploy.deploy_payload_sync"
        ) as deploy:
            result = await async_setup_entry(mock_hass, mock_config_entry)

        assert result is True
        deploy.assert_not_called()
        mock_ir.async_create_issue.assert_not_called()
        # A completed setup clears any leftover issue from the recovery loop.
        mock_ir.async_delete_issue.assert_called_once_with(
            mock_hass, DOMAIN, ISSUE_PYSCRIPT_PAYLOAD_MISSING
        )


class TestSetupGateSensorMissing:
    """Spec test 5: deployed files but no live sensor -> retry, no churn."""

    async def test_sensor_absent_raises_not_ready_without_writes(
        self, mock_hass, mock_config_entry, mock_ir, tmp_path
    ):
        deploy_current_payload(tmp_path)
        mock_hass.states.get.return_value = None

        with patch(
            "custom_components.pepa_sensory_arm.pyscript_deploy.deploy_payload_sync"
        ) as deploy:
            with pytest.raises(ConfigEntryNotReady):
                await async_setup_entry(mock_hass, mock_config_entry)

        deploy.assert_not_called()
        mock_ir.async_create_issue.assert_not_called()

    async def test_sensor_with_empty_csv_raises_not_ready(
        self, mock_hass, mock_config_entry, mock_ir, tmp_path
    ):
        deploy_current_payload(tmp_path)
        empty_state = MagicMock()
        empty_state.attributes = {"csv": ""}
        mock_hass.states.get.return_value = empty_state

        with pytest.raises(ConfigEntryNotReady):
            await async_setup_entry(mock_hass, mock_config_entry)


class TestRemoveEntry:
    """Spec test 6: removing the last entry deletes only the payload."""

    async def test_last_entry_removes_payload_only(
        self, mock_hass, mock_config_entry, mock_ir, tmp_path
    ):
        target = deploy_current_payload(tmp_path)
        user_file = target / "users_own_script.py"
        user_file.write_text("# not ours\n", encoding="utf-8")
        mock_hass.config_entries.async_entries = MagicMock(return_value=[])

        await async_remove_entry(mock_hass, mock_config_entry)

        for name in PAYLOAD_FILES:
            assert not (target / name).exists()
        assert user_file.exists()
        mock_ir.async_delete_issue.assert_called_once_with(
            mock_hass, DOMAIN, ISSUE_PYSCRIPT_PAYLOAD_MISSING
        )

    async def test_remaining_entries_leave_payload_deployed(
        self, mock_hass, mock_config_entry, mock_ir, tmp_path
    ):
        target = deploy_current_payload(tmp_path)
        mock_hass.config_entries.async_entries = MagicMock(return_value=[MagicMock()])

        await async_remove_entry(mock_hass, mock_config_entry)

        for name in PAYLOAD_FILES:
            assert (target / name).exists()
        mock_ir.async_delete_issue.assert_not_called()

    async def test_missing_files_are_ignored(self, mock_hass, mock_config_entry, mock_ir):
        mock_hass.config_entries.async_entries = MagicMock(return_value=[])
        # Nothing deployed, directory absent: removal must not raise.
        await async_remove_entry(mock_hass, mock_config_entry)


class TestFullReplacementPromptMode:
    """Spec test 7: with the default prompt off, the mechanism is inert."""

    async def test_gate_inert_when_default_prompt_disabled(
        self, mock_hass, mock_config_entry, mock_ir, tmp_path
    ):
        mock_config_entry.data = {
            **mock_config_entry.data,
            CONF_PROMPT_USE_DEFAULT: False,
        }

        with (
            patch(
                "custom_components.pepa_sensory_arm.pyscript_deploy.check_deployment_sync"
            ) as check,
            patch(
                "custom_components.pepa_sensory_arm.pyscript_deploy.deploy_payload_sync"
            ) as deploy,
        ):
            result = await async_setup_entry(mock_hass, mock_config_entry)

        assert result is True
        check.assert_not_called()
        deploy.assert_not_called()
        mock_ir.async_create_issue.assert_not_called()
        mock_ir.async_delete_issue.assert_not_called()
        assert not pyscript_dir(tmp_path).exists()


class TestPayloadHelpers:
    """Deployment helpers behave per the manifest contract."""

    def test_payload_manifest_excludes_package_marker(self):
        assert "__init__.py" not in PAYLOAD_FILES
        for name in PAYLOAD_FILES:
            assert (PAYLOAD_SOURCE_DIR / name).is_file()

    def test_deploy_creates_directory(self, tmp_path):
        target = pyscript_dir(tmp_path)
        copied = deploy_payload_sync(target)
        assert sorted(copied) == sorted(PAYLOAD_FILES)
        for name in PAYLOAD_FILES:
            assert (target / name).is_file()

    def test_remove_returns_only_deleted_files(self, tmp_path):
        target = deploy_current_payload(tmp_path)
        (target / PAYLOAD_FILES[0]).unlink()
        removed = remove_payload_sync(target)
        assert sorted(removed) == sorted(PAYLOAD_FILES[1:])
