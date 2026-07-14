# pepa_behavioral_capture.py
# Behavioral observation tap for the Pepa memory arm -- CAPTURE STAGE ONLY.
#
# HA never puts the spoken utterance or recognized intent on the event bus
# (confirmed by probe). What IS on the bus, for every voice interaction on any
# path -- local fast-path or LLM -- is the assist_satellite state machine:
#     idle -> listening -> processing -> responding -> idle
# plus call_service events for any actuation. This taps both, assembles one
# behavioral observation per interaction, and FIRES it as a `pepa_observation`
# event. Storage is intentionally NOT here: a future memory writer subscribes to
# pepa_observation and persists to SurrealDB once the memory-arm schema settles.
# Capture (now) is decoupled from storage (later).
#
# Bonus: resolution_s (processing -> responding) is a free per-interaction
# latency metric. In testing, local fast-path ~0.2s vs LLM ~18s on the same host.
#
# Deploy: <config>/pyscript/pepa_behavioral_capture.py

import time

_BC_SAT_PREFIX = "assist_satellite."
_BC_LLM_THRESHOLD_S = 2.0   # resolution slower than this => LLM path; else fast

# in-flight interactions, keyed by satellite entity_id (module globals persist)
_BC_ACTIVE = {}


@event_trigger("state_changed")
def _bc_on_state(**kwargs):
    entity_id = kwargs.get("entity_id")
    if not entity_id or not entity_id.startswith(_BC_SAT_PREFIX):
        return

    new_state = kwargs.get("new_state")
    phase = getattr(new_state, "state", None) if new_state else None
    if phase is None:
        return

    now = time.monotonic()

    if phase == "listening":
        # start a fresh interaction envelope
        _BC_ACTIVE[entity_id] = {
            "listening": now,
            "processing": None,
            "responding": None,
            "actions": [],
            "epoch": time.time(),
        }
        return

    rec = _BC_ACTIVE.get(entity_id)
    if rec is None:
        # joined mid-cycle; start a partial envelope so we don't drop it
        rec = {"listening": None, "processing": None, "responding": None,
               "actions": [], "epoch": time.time()}
        _BC_ACTIVE[entity_id] = rec

    if phase == "processing":
        rec["processing"] = now
    elif phase == "responding":
        rec["responding"] = now
    elif phase == "idle":
        _bc_emit(entity_id, rec)
        if entity_id in _BC_ACTIVE:
            del _BC_ACTIVE[entity_id]


@event_trigger("call_service")
def _bc_on_service(**kwargs):
    # attach actuations to any open interaction (time-window correlation).
    # NOTE: this also catches non-voice service calls that happen to land inside
    # an open window. Acceptable for behavioral capture; context-lineage
    # correlation is the precise future refinement (see header notes).
    if not _BC_ACTIVE:
        return
    action = {
        "domain": kwargs.get("domain"),
        "service": kwargs.get("service"),
        "data": kwargs.get("service_data"),
        "t": time.monotonic(),
    }
    for rec in _BC_ACTIVE.values():
        rec["actions"].append(action)


def _bc_dur(a, b):
    if a is None or b is None:
        return None
    return round(b - a, 3)


def _bc_emit(entity_id, rec):
    listening_s  = _bc_dur(rec.get("listening"), rec.get("processing"))
    resolution_s = _bc_dur(rec.get("processing"), rec.get("responding"))

    path = "unknown"
    if resolution_s is not None:
        path = "llm" if resolution_s >= _BC_LLM_THRESHOLD_S else "fast"

    obs = {
        "type": "voice_interaction",
        "satellite": entity_id,
        "epoch": rec.get("epoch"),
        "listening_s": listening_s,
        "resolution_s": resolution_s,
        "path": path,
        "actions": rec.get("actions", []),
        "source": "ha_event",
        "provenance": "behavioral_observation",
    }

    event.fire("pepa_observation", observation=obs)
    log.info("pepa_observation: path={} resolution_s={} actions={} sat={}".format(
        path, resolution_s, len(obs["actions"]), entity_id))
