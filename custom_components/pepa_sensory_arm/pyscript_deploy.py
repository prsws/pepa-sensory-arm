"""Deployment of the bundled pyscript perception scripts.

PSA ships its pyscript payload inside the integration folder, because that
folder is all HACS delivers. These helpers copy the payload into the user's
``<config>/pyscript/`` autoload directory, keep it current on upgrade, and
remove it on uninstall.

Every ``*_sync`` function does blocking file I/O and must run in an executor
(``hass.async_add_executor_job``), never directly in the event loop.
"""

from __future__ import annotations

import shutil
from enum import Enum
from pathlib import Path
from typing import Final

from homeassistant.core import HomeAssistant

# The deployable payload, by filename. This tuple is the single source of
# truth for what gets copied, compared, and removed. The bundled pyscripts/
# directory also contains an __init__.py package marker -- that is not
# payload and must never be listed here.
PAYLOAD_FILES: Final[tuple[str, ...]] = (
    "entity_context.py",
    "entities_list.py",
    "pepa_behavioral_capture.py",
)

# Stable Repair issue id for the payload-missing case, so re-raising the
# issue across setup retries stays idempotent.
ISSUE_PYSCRIPT_PAYLOAD_MISSING: Final = "pyscript_payload_missing"

# Copy source: the pyscripts/ directory bundled inside this integration.
PAYLOAD_SOURCE_DIR: Final = Path(__file__).parent / "pyscripts"


class DeploymentState(Enum):
    """State of the pyscript payload on the user's system."""

    MISSING = "missing"
    STALE = "stale"
    CURRENT = "current"


def pyscript_target_dir(hass: HomeAssistant) -> Path:
    """Return the pyscript autoload directory for this installation."""
    return Path(hass.config.path("pyscript"))


def check_deployment_sync(target_dir: Path) -> tuple[DeploymentState, list[str]]:
    """Determine the payload deployment state. Blocking; run in executor.

    Returns the state and the list of payload files that are absent or
    byte-differ from the bundled versions.
    """
    absent: list[str] = []
    stale: list[str] = []
    for name in PAYLOAD_FILES:
        deployed = target_dir / name
        if not deployed.is_file():
            absent.append(name)
        elif deployed.read_bytes() != (PAYLOAD_SOURCE_DIR / name).read_bytes():
            stale.append(name)

    if absent:
        return DeploymentState.MISSING, absent + stale
    if stale:
        return DeploymentState.STALE, stale
    return DeploymentState.CURRENT, []


def deploy_payload_sync(target_dir: Path, files: list[str] | None = None) -> list[str]:
    """Copy payload files into target_dir, overwriting. Blocking; run in executor.

    Creates the directory if absent. Copies all payload files unless a
    subset is given. Returns the filenames copied.
    """
    names = list(files) if files is not None else list(PAYLOAD_FILES)
    target_dir.mkdir(parents=True, exist_ok=True)
    for name in names:
        shutil.copyfile(PAYLOAD_SOURCE_DIR / name, target_dir / name)
    return names


def remove_payload_sync(target_dir: Path) -> list[str]:
    """Delete payload files from target_dir. Blocking; run in executor.

    Only files named in PAYLOAD_FILES are touched; anything else in the
    directory is left alone. Missing files are ignored. Returns the
    filenames actually removed.
    """
    removed: list[str] = []
    for name in PAYLOAD_FILES:
        try:
            (target_dir / name).unlink()
        except FileNotFoundError:
            continue
        removed.append(name)
    return removed
