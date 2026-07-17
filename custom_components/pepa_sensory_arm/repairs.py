"""Repair flows for the Pepa Sensory Arm integration.

Currently one flow: deploying the bundled pyscript perception scripts. The
user's Fix confirmation is the consent for the first write into
<config>/pyscript/; after the copy, HA's setup retry brings the entry up.
"""

from __future__ import annotations

import voluptuous as vol
from homeassistant import data_entry_flow
from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from . import pyscript_deploy
from .const import DOMAIN


class PyscriptPayloadFixFlow(RepairsFlow):
    """Confirm-then-deploy flow for the missing pyscript payload."""

    async def async_step_init(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        """Handle the first step of the fix flow."""
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        """Copy the payload on confirmation.

        The fix flow only deploys the files and clears the issue; it does not
        reload the config entry. HA's ConfigEntryNotReady retry loop picks the
        deployment up and completes setup on its own.
        """
        target_dir = pyscript_deploy.pyscript_target_dir(self.hass)

        if user_input is not None:
            await self.hass.async_add_executor_job(pyscript_deploy.deploy_payload_sync, target_dir)
            ir.async_delete_issue(self.hass, DOMAIN, pyscript_deploy.ISSUE_PYSCRIPT_PAYLOAD_MISSING)
            return self.async_create_entry(data={})

        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema({}),
            description_placeholders={
                "pyscript_dir": str(target_dir),
                "payload_files": ", ".join(pyscript_deploy.PAYLOAD_FILES),
            },
        )


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, str | int | float | None] | None,
) -> RepairsFlow:
    """Create a fix flow for a repair issue raised by this integration."""
    return PyscriptPayloadFixFlow()
