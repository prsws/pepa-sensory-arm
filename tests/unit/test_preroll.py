"""Unit tests for the pre-roll tone played before Pepa speaks (agent/preroll.py)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.pepa_sensory_arm.agent import preroll
from custom_components.pepa_sensory_arm.agent.preroll import (
    PREROLL_PATH,
    PREROLL_URL,
    PrerollGate,
    async_play_preroll,
)

MODULE = "custom_components.pepa_sensory_arm.agent.preroll"


async def _agen(items):
    for item in items:
        yield item


@pytest.fixture
def hass():
    hass = MagicMock()
    hass.services.async_call = AsyncMock()
    return hass


@pytest.fixture(autouse=True)
def no_sleep():
    with patch(f"{MODULE}.asyncio.sleep", new=AsyncMock()) as sleep:
        yield sleep


def test_tone_file_ships_with_integration():
    assert PREROLL_PATH.is_file()


async def test_plays_on_satellite_media_player(hass, no_sleep):
    with patch(f"{MODULE}.find_satellite_media_player", return_value="media_player.sat"):
        assert await async_play_preroll(hass, "dev1") is True

    hass.services.async_call.assert_awaited_once()
    domain, service, data = hass.services.async_call.await_args.args
    assert (domain, service) == ("media_player", "play_media")
    assert data["entity_id"] == "media_player.sat"
    assert data["media_content_id"] == PREROLL_URL
    assert data["announce"] is True
    no_sleep.assert_awaited_once_with(preroll.PREROLL_PLAY_SECONDS)


async def test_skips_device_without_media_player(hass):
    with patch(f"{MODULE}.find_satellite_media_player", return_value=None):
        assert await async_play_preroll(hass, "pinevoice") is False
    hass.services.async_call.assert_not_awaited()


async def test_skips_when_no_device(hass):
    # CarPlay / typed chat: no device_id at all
    assert await async_play_preroll(hass, None) is False
    hass.services.async_call.assert_not_awaited()


async def test_service_failure_never_raises(hass):
    hass.services.async_call.side_effect = RuntimeError("satellite offline")
    with patch(f"{MODULE}.find_satellite_media_player", return_value="media_player.sat"):
        assert await async_play_preroll(hass, "dev1") is False


async def test_lookup_failure_never_raises(hass):
    with patch(f"{MODULE}.find_satellite_media_player", side_effect=KeyError("registry")):
        assert await async_play_preroll(hass, "dev1") is False


async def test_gate_fires_before_first_spoken_delta_only(hass):
    order = []

    async def fake_play(_hass, _device_id):
        order.append("TONE")
        return True

    deltas = [
        {"role": "assistant"},
        {"tool_calls": ["x"]},
        {"content": "   "},
        {"content": "Hola José."},
        {"content": " Listo."},
    ]
    gate = PrerollGate(hass, "dev1")
    with patch(f"{MODULE}.async_play_preroll", side_effect=fake_play):
        async for d in gate.wrap(_agen(deltas)):
            order.append(d)

    assert order == [
        {"role": "assistant"},
        {"tool_calls": ["x"]},
        {"content": "   "},
        "TONE",
        {"content": "Hola José."},
        {"content": " Listo."},
    ]


async def test_gate_fires_once_across_iterations(hass):
    play = AsyncMock(return_value=True)
    gate = PrerollGate(hass, "dev1")
    with patch(f"{MODULE}.async_play_preroll", new=play):
        # first pass: tool call only, second pass: spoken text, third: more text
        for batch in ([{"tool_calls": ["x"]}], [{"content": "Uno."}], [{"content": "Dos."}]):
            async for _ in gate.wrap(_agen(batch)):
                pass
    play.assert_awaited_once()


async def test_gate_disabled_never_plays(hass):
    play = AsyncMock(return_value=True)
    gate = PrerollGate(hass, "dev1", enabled=False)
    with patch(f"{MODULE}.async_play_preroll", new=play):
        out = [d async for d in gate.wrap(_agen([{"content": "Hola."}]))]
        await gate.async_fire()
    assert out == [{"content": "Hola."}]
    play.assert_not_awaited()
