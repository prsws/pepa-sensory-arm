# Degraded Mode — Design and Acceptance Assertions

**Lane:** Design Ledger §6, Priority 5 · **Drafted:** 2026-07-17 · **Status:** draft for review

> Design Ledger §3, hard invariant: *"Degraded mode is designed, not accidental: mmm4 alone must hear, act, speak, and retain explicit facts with all off-box services down."*

This document turns that invariant into assertions that can be checked — against code, against the test suite, and against a live host via the companion UAT checklist (`docs/DEGRADED_MODE_UAT.md`). Pointers use symbol names first; line numbers are indicative and drift.

## 1. What "degraded" means here

PSA has exactly one class of designed degradation: **loss of the vector layer and/or off-box services**, while the local spine (STT → tier ladder → local LLM → tools → TTS, plus the HA Store) keeps running. Degradation is never silent — every path below either logs a warning, raises a Home Assistant repair issue, or declares itself through `MemoryCapabilities`. A degradation that announces itself is a designed state; one that doesn't is a defect.

The invariant decomposes into four capabilities that must survive with all off-box services down:

| Capability | Carried by | Off-box dependency |
|---|---|---|
| **Hear** | Wyoming STT bridge (mmm4 host glue, :10301) | none |
| **Act** | HA-native tiers + local LLM tool calls | none |
| **Speak** | Wyoming TTS bridge (mmm4 host glue, :10201) | none |
| **Retain explicit facts** | `fast_track()` → HA Store (disk) | none |

The Wyoming bridges are Casa Delta glue outside this repo; they are asserted by the UAT checklist, not by this repo's test suite.

## 2. The degradation inventory

Each row is a designed path. **Loudness** is the mechanism that makes the state visible; a row with no loudness mechanism would be a bug by definition.

| # | Trigger | Where handled | Degraded behavior | Loudness |
|---|---|---|---|---|
| D1 | Embedded Chroma init fails; remote host/port configured | `ChromaClientFactory.get_client` → `_can_fall_back_to_remote` | Falls back to remote placement; `placement` property reports the *actual* placement, not the configured one | Repair issue `chroma_embedded_failed` + error log |
| D2 | Embedded Chroma init fails; no remote configured | `ChromaClientFactory.get_client` raises `ContextInjectionError`; caught in `MemoryManager` init | Store-only mode (`_chromadb_available = False`) | Repair issue + "using store-only mode" warning |
| D3 | `chromadb` package not importable | `CHROMADB_AVAILABLE` guard (module-level `except ImportError`) | Store-only mode from birth | Info log at init |
| D4 | Remote Chroma unreachable at runtime | Factory availability tracking (`_mark_unavailable` / retry ladder); consumed live by `MemoryManager.capabilities` | `vector_recall` flips False dynamically; recall reroutes per D5 | Warning log; capability flag readable by any consumer |
| D5 | Recall attempted while Chroma unavailable | `search_memories` → `_fallback_search` | Keyword search over the HA Store — recall degrades, **never silences** | "falling back to keyword search" warning |
| D6 | Explicit-user write ("remember this") in store-only mode | `MemoryManager.fast_track` | Write lands in the HA Store via a **directly awaited** `_save_to_store()` — deliberately bypassing the debounced `_schedule_save`. Durable on disk before the response is spoken | n/a — this path is full-function, not degraded |
| D7 | Operation the interim backend cannot honor (`supersede`, trust dynamics) | `MemoryCapabilityError`; capability flags `supersession=False`, `trust_dynamics=False` | Honest refusal — "arrives with the Memory Arm backend" | Once-per-op-per-session `_LOGGER.warning` |
| D8 | External LLM (punt) unreachable / timeout / auth failure | `tools/external_llm.py` (`asyncio.TimeoutError`, `ClientResponseError` handlers) | Tool returns an error result; the **local** model continues the conversation and answers with what it has | Warning log; error surfaced in tool result |
| D9 | Device perception with zero vector store | P1 CSV catalog (`sensor.pepa_entity_context`) baked into the prompt TAIL; empty `conversation_context` contributes nothing | Full device query/control capability — perception never depended on the vector layer | n/a — full-function by design (Ledger §2.4) |

Adjacent but distinct: a missing pyscript payload (the catalog's producer) gates setup behind a fixable repair flow — loud, but an install-time precondition rather than a runtime degradation.

## 3. Acceptance assertions

The invariant holds if and only if all of the following are true. Existing automated coverage is noted; unchecked assertions belong to the UAT checklist.

**A1 — Retention survives total vector loss.** `fast_track()` with no Chroma of any kind persists the fact to disk before returning, and the fact is recallable in the same session.
*Covered:* conformance suite runs store-only by construction (`chroma_factory=None`), exercising the real path — not a mock.

**A2 — Recall never silences.** With Chroma unavailable, `recall()` returns keyword-search results from the HA Store; it does not return empty-because-broken or raise.
*Covered:* conformance suite (store-only fixture); `test_chromadb_failure_graceful_degradation` (repaired in P2 to exercise the real path).

**A3 — Degradation is loud.** Every row in §2 emits its stated loudness signal. An embedded-placement failure specifically must raise the `chroma_embedded_failed` repair issue.
*Covered:* factory unit tests; field-proven by the Fresh Installation V2 walkthrough (2026-07-17).

**A4 — Capabilities tell the truth, live.** `capabilities.vector_recall` reflects *current* factory availability, not init-time state; consumers reading the flag get the world as it is.
*Covered:* unit tests on the capabilities property.

**A5 — Honest noes stay honest.** `supersede()` on the interim backend raises `MemoryCapabilityError`; nothing pretends by no-op-ing.
*Covered:* conformance suite.

**A6 — Placement fallback is visible.** After a D1 fallback, `ChromaClientFactory.placement` reports `remote`, and the repair issue is present even though the system recovered.
*Covered:* factory unit tests.

**A7 — The punt fails inward, not outward.** With the external LLM unreachable, the local model still answers; no utterance dies waiting on a remote service.
*UAT only* — requires live inference.

**A8 — Device perception is vector-independent.** With no vector store, "show me a list of detected devices" (EN) / "muéstrame los dispositivos detectados" (ES) returns the full catalog.
*Field-proven* (Fresh Installation V2, "Bingo!" step); pinned as UAT item.

**A9 — Hear / act / speak are mmm4-local.** Wake→STT→tier ladder→TTS completes with the network cable to everything off-box pulled.
*UAT only* — glue-layer scope, outside this repo's suite.

## 4. What this document does not cover

- **Canonical memory (SurrealDB) outages** — no canonical backend exists yet. When the Memory Arm lands, its WAL drain-and-promotion path gets its own rows here (Ledger §2.2: canonical is never blocking; nothing at 3 AM waits on pve2).
- **Growth-class failure** — a store swelling inside the 4 GB VM over years raises no exception and cannot be caught by this ladder. That is P6's question, by design (Ledger §2.6).
- **Tier-ladder observability** — utterances that never reach PSA are the utterance-ledger design's concern (Ledger §2.3), not a degradation.
