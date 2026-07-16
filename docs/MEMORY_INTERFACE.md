# Memory Interface

The single contract behind which memory backends are swappable implementations.

Today: the interim ChromaDB-backed `MemoryManager`. Later: the SurrealDB-backed Memory Arm. The promise of this contract is that the second one is a **backend swap, not a rewrite** — it satisfies the same Protocol and passes the same conformance suite (`tests/unit/test_memory_interface_conformance.py`), unmodified.

Field semantics come from the Pepa Memory Architecture Design, SurrealDB schema v0.1 (2026-07-06). That alignment is load-bearing: the vocabulary is 1:1 with the target schema so ETL into the Memory Arm is a mapping, not a reinterpretation.

## Vocabulary

| Type | Values | Meaning |
|---|---|---|
| `Category` | `fact`, `preference`, `context`, `event` | Coarse taxonomy. 1:1 with the interim backend's existing memory types. |
| `Source` | `explicit_user`, `behavioral`, `measured` | Provenance. Assigned at write, immutable thereafter — how a belief entered the system is a historical fact, not a revisable judgment. `measured` is reserved; no current producer. |
| `EpistemicClass` | `observation`, `interpretation`, `prediction` | Pepa's revisable judgment about the kind of belief. |
| `Status` | `raw`, `hypothesis`, `tested`, `confirmed` | Corroboration-gated lifecycle. One-directional. |

**`policy` is deliberately absent from `EpistemicClass`.** Flat files are the policy store. The memory system must be *structurally unable* to hold policy, so that no amount of conversation can talk Pepa into a new rule about care.

## Trust is not importance

The single most important distinction in this contract, and the easiest to get wrong:

- **`trust`** is epistemic weight — how much a belief should be believed. It lives on `MemoryRecord`.
- **`importance`** is salience — how much a belief should be surfaced. It lives in `metadata`, as the interim backend's own bookkeeping.

Never map one onto the other. A trivial certainty and a load-bearing guess are not the same thing. Concretely: passing a `min_importance` filter as `min_trust` would silently drop a fact the resident stated outright but which scores low on salience — "Ana takes her pills at 8", importance 0.1, trust 1.0. Callers that need importance filtering do it themselves, after `recall()`.

## Operations

**Core** — these carry the epistemics:

| Op | Guarantee |
|---|---|
| `write()` | Persists a belief. Provenance is fixed here, forever. |
| `fast_track()` | The "remember this" path. Locally durable and immediately recallable **before the call returns** — when the resident says remember this, it is remembered by the time Pepa answers, not eventually. Forces `source=explicit_user`, `trust=1.0`. |
| `recall()` | Semantic recall. Every result carries trust, status, and source so the consumer decides weight. **Retrieval is not endorsement.** |
| `supersede()` | Append-only correction: creates a successor, points `old.superseded_by` at it, never mutates the original. |

**Admin** — non-canonical, exists because the HA services and current consumers need it: `get()`, `delete()`, `list_all()`, `clear_all()`.

**Honesty** — `capabilities`, a **sync property**. This shape is what the Memory Arm backend must satisfy, and the conformance suite reads it without awaiting.

## What does NOT work yet (interim backend)

Declared honestly via `capabilities`, so consumers can ask instead of assume:

| Capability | Interim | Notes |
|---|---|---|
| `supersession` | **False** | `supersede()` raises `MemoryCapabilityError`. Deliberately a stub, not a metadata-pointer approximation — a half-built supersession chain is worse than none, because callers would start trusting it. Arrives with the Memory Arm backend. |
| `trust_dynamics` | **False** | Trust is derived at read and fixed. Nothing moves it as evidence accumulates. |
| `provenance_enforced` | **False** | Source immutability is **convention only**, upheld by this component's discipline and nothing else. The store will not catch a violation. The target schema will. |
| `durable_fast_track` | True | Via HA Store; `fast_track()` awaits the save directly rather than the debounced path. |
| `vector_recall` | Varies | See the honesty section below. |

Degradation is **loud**: `MemoryCapabilityError` names the op, the backend, and the lane where the capability arrives, and emits a warning once per op per session — once, not spam.

Also still true of the interim backend, and not a capability flag: **dedup merge-and-reinforce survives**. `write()` delegates through it unchanged. It is a false-memory-climb engine (Ledger §5) and does not survive the refactor, but killing it is **P8's** job — see the routing comment at the delegation site.

## Honesty: the `vector_recall` staleness bound

`vector_recall` does **not** mean "the vector store is reachable right now". It cannot: `capabilities` is a sync property and reachability is network I/O.

It means **bounded-staleness availability**. The value reflects the client factory's availability flag, refreshed two ways:

1. **As a side effect of every real client operation** — any ChromaDB call that succeeds sets it True; any connection-class failure sets it False.
2. **By a TTL'd background probe** — every `CHROMA_AVAILABILITY_TTL` seconds (default 60), registered for `remote` placement only.

So **"available" means "was reachable within the last 60 seconds, or on the last operation"** — not "is reachable at this instant". Backends whose availability is genuinely static (an embedded `PersistentClient` after successful init, which has no network to lose) may hold the flag constant, and do.

This is deliberately not solved by making `capabilities` async. The sync shape is the contract.

Why this matters: the previous code set `_chromadb_available` once in `async_initialize` and never re-probed it. Init-time state masquerading as live state is itself a silent degradation — the thing this contract exists to prevent. A bounded lie you can measure beats an unbounded one you cannot.

## Client factory and placement

`ChromaClientFactory` is the only place a ChromaDB client is constructed. Both `VectorDBManager` and `MemoryManager` consume from it. This is what killed the **borrowed-client bug**, where memory parasitized the vector manager's client and setting Context Mode to Direct silently killed memory vector search, sync, and dedup.

Placement is configuration, never a heuristic — a memory system that silently relocates its store based on runtime conditions is one nobody can reason about.

| Placement | Client | Status |
|---|---|---|
| `remote` | `HttpClient` against a ChromaDB server | **Default** |
| `embedded` | `PersistentClient`, in-VM, no external service | Implemented, default-off |

**Why the default is `remote` when Ledger §2.2 says `embedded`:** the flip is gated on the **P6** in-VM benchmark. The measured embedded footprint on record (~222 MB RSS at ~5k vectors, ~485 MB at 50k) was taken *outside* the 4 GB HAOS VM, and Ledger §4 records that the in-VM ground-truth run is still pending. Shipping embedded-by-default before that run would bet the VM on an unmeasured number. Resolution belongs to P6, not P2.

**The loud-failure ladder** when embedded placement cannot start:

1. Log an error naming the path and the cause.
2. Create an HA repair issue (`chroma_embedded_failed`) — the user sees it.
3. Fall back to `remote` **iff** host/port are configured.
4. Otherwise raise. The caller runs store-only with `vector_recall=False`.

At no point does it degrade silently.

## Embedding cache namespacing

The shared `Embedder` keeps **separate LRU namespaces** for entity state-text and memory queries, each with its own budget (`EMBEDDING_CACHE_MAX_SIZE`, `MEMORY_EMBEDDING_CACHE_MAX_SIZE`, both 1000).

Sharing one LRU would let memory recall queries and entity state-text evict each other — a fast-path latency change on the 4 GB VM, smuggled in under a refactor. Namespacing preserves the entity hit-rate byte-for-byte and defers the shared-vs-split question to **P6**, whose benchmark is the instrument that should answer it. Retuning either budget is P6's call.

Namespace is a property of the **caller**, not of the arguments: both memory's recall queries and the vector manager's query embeds pass `entity_id=None`, so `entity_id` cannot select it. Hence the explicit `namespace` parameter.

Per-entity eviction applies within the `entity` namespace only. `VectorDBManager.async_shutdown()` clears **only** that namespace, and does not close the shared HTTP clients — both would break `MemoryManager`. The factory closes the embedder once, at unload.

## Enforcement is layered

`@runtime_checkable` verifies that members are **present**, not that they take the right arguments. A backend whose `write()` takes entirely the wrong parameters still passes `isinstance()`. And `issubclass()` raises `TypeError` by construction — `capabilities` is a property, which makes this a data protocol.

All three layers are required, and none substitutes for another:

1. **Presence** — `isinstance()`, at runtime.
2. **Signatures** — `memory_manager._assert_satisfies_contract()`, a never-called function mypy checks. Delete it and the contract silently becomes documentation.
3. **Behavior** — the conformance suite.

## The migration promise

The Memory Arm backend is a **new implementation of this Protocol that passes the same conformance suite**. Adding it means adding a fixture to `test_memory_interface_conformance.py`'s `backend` parametrization and nothing else.

If a conformance test needs a special case for a particular backend, the contract is wrong — not the test.
