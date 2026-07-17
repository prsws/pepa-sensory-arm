# Degraded Mode — UAT Checklist

**Companion to:** `docs/DEGRADED_MODE.md` · **Drafted:** 2026-07-17 · **Status:** draft for review
**Method:** OBOSBS discipline — one variable at a time, record before/after, restore before the next phase. Do not stack degradations until Phase 5, which stacks them all deliberately.

Assertion IDs (A1–A9) refer to `DEGRADED_MODE.md` §3. Test utterances are given EN/ES; either language must pass — run both where time allows.

## Phase 0 — Baseline (nothing degraded)

- [ ] Record: PSA config entry loaded, Chroma placement (embedded or remote), `capabilities` state if inspectable, no `chroma_embedded_failed` repair issue present.
- [ ] Utterance: *"show me a list of detected devices"* / *"muéstrame la lista de dispositivos detectados"* → full catalog returned.
- [ ] Utterance: *"remember that my favorite coffee is Yaucono"* / *"recuerda que mi café favorito es Yaucono"* → acknowledged.
- [ ] Utterance: *"what is my favorite coffee?"* / *"¿cuál es mi café favorito?"* → answered from memory.
- [ ] Note the answer's source/trust presentation if surfaced.

**Gate:** all green before proceeding. If baseline fails, stop — you are not testing degradation, you are debugging installation.

## Phase 1 — Vector layer down (tests A1, A2, A4, A5) 

**Induce (one of, per current placement):**
- Remote placement: stop the ChromaDB service on the remote host (or block the host:port).
- Embedded placement: rename the persist dir while HA is stopped, or configure an unwritable path, then start HA.

- [ ] **A3:** the degradation announced itself — warning in the HA log ("store-only" / "keyword search") and, for an embedded failure, the `chroma_embedded_failed` repair issue.
- [ ] **A1:** *"remember that my niece's birthday is in November"* / *"recuerda que el cumpleaños de mi sobrina es en noviembre"* → acknowledged. Then **restart Home Assistant** (process death) and ask: *"when is my niece's birthday?"* / *"¿cuándo es el cumpleaños de mi sobrina?"* → recalled. This is the durability contract: the fact survived with no vector store and a dead process.
- [ ] **A2:** *"what do you remember about me?"* / *"¿qué recuerdas de mí?"* → keyword-fallback results returned; not empty, no error to the user.
- [ ] **A4:** capabilities reflect reality (`vector_recall` false) — verify via log or diagnostic surface.
- [ ] **A5:** no operation silently no-ops; any unsupported op logs its once-per-session warning.

**Restore:** bring the vector layer back. Confirm recovery (vector recall resumes) before Phase 2.

## Phase 2 — Embedded fails WITH remote configured (tests A6)

*Only applicable on a host with both placements configured (Casa Delta: mmm4 is pinned remote by migration; test on a sandbox HA if needed.)*

- [ ] Induce embedded failure with valid remote host/port present.
- [ ] **A6:** repair issue raised **and** system recovered onto remote — verify factory `placement` reports `remote` and vector recall works.
- [ ] The repair issue text matches: fallen back to remote, per `strings.json` wording.

**Restore.**

## Phase 3 — External LLM unreachable (tests A7)

**Induce:** block or stop the external LLM endpoint (leave local inference and vector layer up).

- [ ] Utterance that would normally punt (a general-knowledge question outside device control) → the **local** model answers with what it has; response arrives; no hang for the full timeout on simple queries.
- [ ] **A7:** log shows the timeout/connection warning; the error is contained in the tool result, not surfaced as a crash.

**Restore.**

## Phase 4 — Device perception with zero vector store (tests A8)

**Induce:** vector layer down (as Phase 1), fresh conversation.

- [ ] **A8:** *"show me a list of detected devices"* / *"muéstrame los dispositivos detectados"* → full catalog (the P1 CSV path needs no vectors). Field-proven in Fresh Installation V2; re-run here to pin it against regressions.
- [ ] Actuation: *"turn on the living room fan"* / *"prende el abanico de la sala"* → device responds.

**Restore.**

## Phase 5 — The 3 AM test: everything off-box down at once (tests A9 + all)

**Induce:** disconnect mmm4 from everything off-box (pull uplink or firewall it) — remote Chroma, external LLM, pve2, everything. Local loop stays: HA VM, rapid-mlx, Wyoming daemons.

- [ ] **Hear:** wake word + STT produce a transcript.
- [ ] **Act:** *"turn off the bedroom light"* / *"apaga la luz del cuarto"* → light responds.
- [ ] **Speak:** TTS response is audible.
- [ ] **Retain:** *"remember that the water was shut off today"* / *"recuerda que hoy cortaron el agua"* → acknowledged; recallable after HA restart, still offline.
- [ ] **Recall degrades, never silences:** memory questions return keyword results.
- [ ] **Loudness:** the logs show the degradations; nothing failed silently.

**Restore everything. Confirm full recovery: vector recall resumes, punt works, no stale repair issues beyond the expected ignorable ones.**

## Sign-off

| Phase | Date | Pass/Fail | Notes |
|---|---|---|---|
| 0 — Baseline | | | |
| 1 — Vector down | | | |
| 2 — Embedded→remote fallback | | | |
| 3 — Punt down | | | |
| 4 — Perception, no vectors | | | |
| 5 — 3 AM test | | | |

A failed phase is a finding, not a checklist edit: log it (Ledger / Leantime), fix, and re-run the phase from its start. The checklist itself only changes when the design changes.
