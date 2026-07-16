# P2 Implementation Log — Memory Interface Contract Surface

**Lane:** Design Ledger §6, Priority 2 · **Branch:** `psa-memory-interface` · **Spec:** PSA Refactor — P2 Implementation Spec v2 (2026-07-16)

Append-only, per the Ledger working agreement ("corrections go in new entries or new documents"). This log records what implementation found that the spec did not predict, and what was decided in response. Entries are never edited after the fact; corrections get a new entry.

The spec remains the authority on *what* P2 delivers. This log is the authority on *what actually happened* while delivering it, including where reality falsified the spec.

---

## 2026-07-16 — Recon against `1bcda54`

Recon before commit 1. Every §10 provenance pointer in the spec resolved as claimed, including the four `_embed_text` reaches (`memory_manager.py:429`, `:529`, `:783`, `:842`), the borrowed-client birth (`__init__.py:179`, `:197–201`), the conduit (`agent/core.py:255–256`), the embedding signature (`vector_db_manager.py:649`), and the borrowed-shape fixture (`tests/unit/test_memory_manager.py:54`). All six consumers in §5 confirmed at their stated call sites.

Three spec claims were falsified. Per spec §0, counts are claims rather than permissions, so these were reported and held rather than absorbed.

### Finding 1 — Six borrowed reaches, not five

`_ensure_chromadb_initialized` touches `vector_db_manager._client` twice, not once: the guard at `:713` (which the spec names) and the use at `:719` (`self.vector_db_manager._client.get_or_create_collection`, which it does not).

Low impact: both sit in the same method body and both die with the same §4.4 change, and AC#4's object-level grep would have caught the omission regardless. Recorded for count accuracy only.

### Finding 2 — The §4.2 factory surface is incomplete; AC#8 cannot hold without additions

The embedding cache is not reached only through `_embed_text`. Moving `_embedding_cache` and `_entity_cache_keys` into the factory orphans two live behaviors in `VectorDBManager`:

- `async_shutdown` (`vector_db_manager.py:218–219`) clears both structures.
- `async_remove_entity` (`vector_db_manager.py:374–376`) evicts the per-entity key when an entity leaves the index.

Neither has a home in the declared surface (`get_client` / `embed_text` / `health_check` / `available` / `placement`). AC#8 requires per-entity eviction behavior identical to pre-change, which is unreachable without them.

This also surfaces a lifecycle question the spec does not address: the factory is per-config-entry and shared by both managers, so `VectorDBManager.async_shutdown()` clearing a *shared* cache would wipe memory-namespace entries too — a cross-manager side effect with no equivalent in today's code.

**Decided (José, 2026-07-16):** add `evict_entity()` and a namespace-scoped clear to the factory surface. `VectorDBManager.async_shutdown()` clears **only** the `entity` namespace.

### Finding 3 — §6.5 understates the test work, and the `_embed_text` shim does not cover it

The spec expects "~15" `_embed_text` references riding the delegating shim, plus one pass to confirm none assert on moved cache internals.

Actual: 23 `_embed_text` references, and 28 lines across **8 tests** assert directly on `manager._embedding_cache` / `manager._entity_cache_keys` — the exact structures §4.3 moves. The shim covers the method, not the attributes, so these break by construction:

- `test_embed_text_uses_cache`
- `test_embed_text_cache_miss_generates_new`
- `test_embed_text_entity_id_evicts_stale_cache`
- `test_embed_text_without_entity_id_no_eviction`
- `test_index_entity_state_change_evicts_stale_cache`
- `test_remove_entity_cleans_embedding_cache`
- `test_shutdown_clears_entity_cache_keys`
- `test_async_shutdown_cleans_up_listeners`

**Decided (José, 2026-07-16):** rewrite the 8 tests onto factory fixtures. No cache-attribute proxy shims.

Consequence worth stating plainly, since it is the kind of thing a later reader will try to "fix": the `_embed_text` shim and the cache attributes are now decided on *different* grounds. The shim survives per §4.3 for its 23 test references and one release of deprecation; the cache attributes move clean with no shim. This asymmetry is intentional. Do not restore symmetry by adding cache proxies back.

---

## 2026-07-16 — Amendment 1: §8 commit sequencing

**Supersedes:** spec §8's placement of all test work in commit 6, and §2's in-scope list naming only the `test_memory_manager.py` fixture rewrite.

§8 requires each of the six commits to be independently green. Following the §6 ruling above, that constraint and §8's literal commit contents cannot both hold: commit 2 moves the cache out of `VectorDBManager`, which is precisely what the 8 tests in Finding 3 assert on, so they would go red at commit 2 and stay red through commit 5. The same shape applies at commit 3 for `tests/unit/test_memory_manager.py:54`.

Test rewrites travel with the commit that moves the thing they test:

| Commit | Test work it carries |
|---|---|
| 2 — `chroma_factory.py`, cache move | Rewrite of the 8 cache-internal tests onto factory fixtures |
| 3 — `MemoryManager` onto the factory | `test_memory_manager.py` fixture rewrite (§6.5) |
| 6 — tests + docs | Conformance suite, factory tests, borrowed-client-kill tests, docs |

This is bookkeeping on work already in scope, not new scope. Commit 6 keeps everything genuinely new; it loses only the rewrites that cannot wait for it.

---

## 2026-07-16 — Commit 1 landed: `memory_interface.py`

Commit `0583132`. Contract, `MemoryRecord`, `MemoryCapabilities`, `MemoryCapabilityError`. No consumers touched. Unit suite green at 1496 passed; module is black/isort/flake8 clean and adds zero mypy errors against a pre-existing HEAD baseline of 24 errors across 11 files.

Two judgment calls made inside the spec:

- **`MemoryCapabilityError` inherits `PepaSensoryArmError`.** Spec §3.4 fixes the error's *location* in `memory_interface.py`; every other error in this component inherits that base. Location and base class are independent, so both hold.
- **`MemoryRecord.__post_init__` enforces `trust ∈ [0, 1]`.** Not requested by the spec. Added because the frozen dataclass is the only cheap enforcement point, and `provenance_enforced = False` on the interim backend concedes the store will not catch it.

**Verified behaviorally, not just asserted:** error message renders as `supersede() is not supported by the interim MemoryManager backend; arrives with the Memory Arm backend` and catches as `PepaSensoryArmError`; trust range rejects `1.5` and `-0.1`; record is frozen (`FrozenInstanceError`); `metadata` default is isolated per instance; `isinstance()` accepts a complete stub and rejects a partial one.

### Carried forward — AC#1 is only half-satisfied

`@runtime_checkable` verifies member *presence*, not signatures. Confirmed empirically on Python 3.14.5: a class whose `write()` takes entirely the wrong arguments still passes `isinstance()`. `issubclass()` is unavailable by construction — `capabilities` is a property, making this a data protocol, and data protocols raise `TypeError` on `issubclass()`.

So AC#1's "runtime check in tests" is weaker than it reads. Enforcement is layered, and all three layers are required:

1. **Presence** — `isinstance()`, at runtime.
2. **Signatures** — a mypy-checked assignment of a backend instance to a `MemoryInterface`-annotated name. **Deferred to commit 3**, which is where a real `MemoryManager` instance first exists to assign. Until then the Protocol is documentation, not enforcement.
3. **Behavior** — the conformance suite, commit 6.

Also deferred to commit 3: the once-per-op-per-session `_LOGGER.warning` required by §3.4. The error class carries the message; nothing logs it yet.

---

## 2026-07-16 — Open discrepancy: Chroma placement default

Ledger §2.2 states Chroma placement defaults to `embedded` ("zero-infrastructure for public HACS users"), optional `remote`. Spec §4.1 states `DEFAULT_CHROMA_PLACEMENT = CHROMA_PLACEMENT_REMOTE`, with the embedded flip gated on P6's in-VM benchmark, and §2 routes the flip out of scope.

Implementation follows the spec (`remote`): it is newer, declares itself sole authority, and its caution is corroborated by Ledger §4, which records that the in-VM ground-truth run of the sizing harness is still pending. The measured figures in §4 (~222 MB RSS at ~5,000 vectors, ~485 MB at 50,000) were taken outside the 4 GB HAOS VM, so they do not yet discharge the §3 invariant.

Recorded because commit 2 writes that constant, and a reader arriving from Ledger §2.2 will otherwise read the code as a bug. Resolution belongs to P6, not P2.
