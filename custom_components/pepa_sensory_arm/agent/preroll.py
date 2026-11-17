"""Pre-roll tone played on the satellite just before Pepa speaks a reply.

Why: the satellites (Voice PE, Satellite1) stutter at the very start of a
streamed TTS reply. Playing a short tone first puts a known sound in that spot,
the same tone HA's local fast path ("Prefer handling commands locally") uses,
so a fast-path reply and a Pepa reply begin the same way.

How: the tone is served as a static file by the integration and played on the
satellite's own media player (``media_player.play_media`` with
``announce: true``). The media player is found through the ``device_id`` HA
passes with the conversation turn.

Limits, by design:
- Only devices with a media player in HA get the tone. Wyoming satellites such
  as the PineVoice, and conversations with no device (CarPlay, the HA app,
  typed chat), get none.
- The tone is fire-once per conversation turn, even when the model takes
  several passes (tool calls) before it speaks.
- Nothing here may break or block a reply: every failure is logged and the
  reply goes out as before.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator, AsyncIterable
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

_LOGGER = logging.getLogger(__name__)

PREROLL_URL = "/pepa_sensory_arm/static/preroll.mp3"
PREROLL_PATH = Path(__file__).parent.parent / "sounds" / "preroll.mp3"

# How long the tone lasts. play_media returns when the satellite accepts the
# clip, not when it finishes playing, so we wait this long before letting the
# reply through; otherwise the reply's audio would cut the tone off.
PREROLL_PLAY_SECONDS = 0.85

# Upper bound for the play_media call itself. A slow or offline satellite must
# not hold up the reply.
PREROLL_CALL_TIMEOUT = 2.0


async def async_register_preroll_path(hass: HomeAssistant) -> None:
    """Serve the tone file so satellites can fetch it."""
    if not PREROLL_PATH.is_file():
        _LOGGER.warning("Pre-roll tone file missing at %s; tone disabled", PREROLL_PATH)
        return
    try:
        from homeassistant.components.http import StaticPathConfig

        await hass.http.async_register_static_paths(
            [StaticPathConfig(PREROLL_URL, str(PREROLL_PATH), True)]
        )
    except Exception as err:  # noqa: BLE001 - a missing tone must never stop setup
        _LOGGER.warning("Could not register pre-roll tone path: %s", err)


def find_satellite_media_player(hass: HomeAssistant, device_id: str | None) -> str | None:
    """Return the enabled media_player entity that belongs to this device, if any."""
    if not device_id:
        return None
    registry = er.async_get(hass)
    for entry in er.async_entries_for_device(registry, device_id):
        if entry.domain == "media_player" and entry.disabled_by is None:
            return entry.entity_id
    return None


async def async_play_preroll(hass: HomeAssistant, device_id: str | None) -> bool:
    """Play the tone on the satellite and wait for it to finish.

    Returns True if the tone was played, False if it was skipped or failed.
    """
    try:
        entity_id = find_satellite_media_player(hass, device_id)
    except Exception as err:  # noqa: BLE001 - the reply must go out regardless
        _LOGGER.warning("Pre-roll tone: could not look up device %s: %s", device_id, err)
        return False
    if entity_id is None:
        _LOGGER.debug("No media player for device %s; skipping pre-roll tone", device_id)
        return False

    try:
        async with asyncio.timeout(PREROLL_CALL_TIMEOUT):
            await hass.services.async_call(
                "media_player",
                "play_media",
                {
                    "entity_id": entity_id,
                    "media_content_id": PREROLL_URL,
                    "media_content_type": "music",
                    "announce": True,
                },
                blocking=True,
            )
    except Exception as err:  # noqa: BLE001 - the reply must go out regardless
        _LOGGER.warning("Pre-roll tone failed on %s: %s", entity_id, err)
        return False

    await asyncio.sleep(PREROLL_PLAY_SECONDS)
    return True


def _delta_has_speech(delta: Any) -> bool:
    """True if a chat-log delta carries text that will be spoken."""
    return isinstance(delta, dict) and bool(str(delta.get("content") or "").strip())


class PrerollGate:
    """Plays the tone once per conversation turn, just before the first spoken text."""

    def __init__(self, hass: HomeAssistant, device_id: str | None, enabled: bool = True) -> None:
        self._hass = hass
        self._device_id = device_id
        self._done = not enabled

    async def async_fire(self) -> None:
        """Play the tone now, unless it was already played (or disabled) this turn."""
        if self._done:
            return
        self._done = True
        await async_play_preroll(self._hass, self._device_id)

    async def wrap(self, deltas: AsyncIterable[Any]) -> AsyncGenerator[Any, None]:
        """Pass deltas through unchanged, playing the tone before the first spoken one."""
        async for delta in deltas:
            if not self._done and _delta_has_speech(delta):
                await self.async_fire()
            yield delta
