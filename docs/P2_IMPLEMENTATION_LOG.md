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

## 2026-07-16 — Commit 2a landed: `chroma_factory.py`

Commit `4de2f0c`, merged to main via PR #4 as `db80c82`. Factory, both placements, availability, placement-aware health check; `VectorDBManager` sources its client from the factory. Unit 1513, offline integration 268 (baseline), zero new mypy errors.

Deviation recorded: the persist-dir config field is always visible rather than "shown only when embedded" (spec §4.2). Home Assistant renders a step's schema statically, so true conditionality requires splitting the step in two; judged not worth the flow churn for one field. Documented at the schema site.

Also added, unrequested but load-bearing: translation strings for the placement selector and the repair issue (`strings.json`, `translations/en.json`). Without them both render as raw slugs in the UI.

### Process failure worth recording

Only the unit suite was being run during 2a's development. When the offline integration suite was finally run, it was 9 tests red — the `VectorDBManager` constructor change had broken them several steps earlier, unnoticed. Baseline on `main` was 268 passing, so they were genuinely new breakage, since fixed. Both suites are now run at every checkpoint, plus a `--collect-only` pass over the excluded live-service tests, which construct `VectorDBManager` too and would otherwise fail at the next live run.

---

## 2026-07-16 — Finding 5: the declared `embed_text` signature cannot express its own namespacing

**Falsifies:** spec §4.2's `embed_text(self, text: str, entity_id: str | None = None)`.

§4.3 requires entity and memory embeddings to occupy separate cache namespaces, on the rationale that "memory recall queries and entity state-text evict each other" under one LRU. But the namespace is a property of the **caller**, not of the arguments: `MemoryManager`'s recall queries and `VectorDBManager`'s *query* embeds both pass `entity_id=None`. `entity_id` therefore cannot select the namespace, and the declared signature has no other parameter that can.

**Resolved:** an explicit `namespace: CacheNamespace = CACHE_NS_ENTITY` parameter on `Embedder.embed_text()` and `ChromaClientFactory.embed_text()`. Defaulting to the entity namespace preserves `VectorDBManager`'s behavior exactly, including through the `_embed_text` shim, which passes no namespace. `MemoryManager` will pass `CACHE_NS_MEMORY` explicitly in commit 3.

## 2026-07-16 — Amendment 2: Finding 3's count was 8; the real number is 16

**Supersedes:** Finding 3's "8 tests" and this log's earlier statement that commit 2b carries a rewrite of 8.

Finding 3 counted only tests asserting on cache internals. José's ruling on Finding 4 — extract an `Embedder` — moved the embedding **providers** as well, so the provider tests moved with them. The full set that had to leave `test_vector_db_manager.py` is 16:

- 8 cache-internal (Finding 3's original list)
- 7 provider: `test_embed_with_openai_{success,api_error,missing_api_key,library_not_available}`, `test_embed_with_ollama_{success,api_error,timeout}`, plus `test_embed_text_unknown_provider`

15 were removed outright and ported to the new `tests/unit/test_embedder.py`; `test_async_shutdown_cleans_up_listeners` was rewritten in place, since listener teardown remains `VectorDBManager`'s concern while the cache assertion in its tail did not.

Three integration tests in `test_config_variations.py` also asserted on `vector_db_manager.embedding_provider` / `.embedding_base_url` and patched `_embed_with_ollama` on the manager. They now reach the same state through `vector_db_manager.chroma_factory.embedder`. Not previously counted anywhere.

The lesson generalizes: a count taken before a design ruling is a count of the old design. Finding 3 was honest when written and wrong once Finding 4 was resolved.

## 2026-07-16 — Commit 2b landed: `embedder.py`

The embedding stack leaves `VectorDBManager` whole: provider config, `_embed_with_openai`, `_embed_with_ollama`, `_ensure_aiohttp_session`, both client lifecycles, and the cache. What remains in the manager is a deprecated `_embed_text` shim delegating to the factory.

Per José's rulings:

- **`evict_entity()` and a namespace-scoped `clear_cache()`** added to the factory surface. `async_remove_entity` evicts through the factory; `async_shutdown` calls `clear_cache(CACHE_NS_ENTITY)` and **nothing else**.
- **`VectorDBManager.async_shutdown()` no longer closes the shared HTTP clients.** It used to close `_aiohttp_session` and `_openai_client`; those are now the shared embedder's, and closing them would break `MemoryManager` — the same cross-manager side effect as the cache clear, one layer down. `ChromaClientFactory.async_shutdown()` closes the embedder, once, at unload, after both managers stop.
- **No cache proxy shims.** The `_embed_text` shim survives for its callers and one release of deprecation; the cache attributes moved clean. The asymmetry is deliberate — do not restore symmetry by adding cache proxies back.

Cache budgets moved to `const.py` as `EMBEDDING_CACHE_MAX_SIZE` (entity, unchanged at 1000) and `MEMORY_EMBEDDING_CACHE_MAX_SIZE` (memory, 1000). Retuning either is P6's call.

Verified: unit 1526, offline integration 268 (baseline), live-service tests collect (14). mypy **removed** one pre-existing error (`Returning Any` in `_embed_with_ollama`, annotated during the move) and added none — 23/10 against main's 24/11.

---

## 2026-07-16 — Finding 6: there is a seventh consumer

**Falsifies:** spec §5's "six call sites", and its own warning that the conduit is "the easiest to miss".

`context_manager.py::set_memory_provider` constructs `MemoryContextProvider(memory_manager=...)`. §5 lists `context_providers/memory.py` as consumer #4, but that row names the module that *uses* memory, not the site that *wires* it. The wiring site is a distinct file and took the parameter as `Any`, so it evaded both the import scan and the method-call grep — the same evasion the spec correctly diagnosed for `agent/core.py`, present twice and caught once.

It was found by mypy, not by grep: renaming the provider's parameter made the call site a type error. Worth noting for the remaining lanes — a typed seam finds its own consumers, an `Any`-typed one does not.

Resolved: `set_memory_provider(memory: MemoryInterface)`, provider parameter renamed to `memory`.

## 2026-07-16 — Commits 4 and 5 landed: wiring and consumers

**Commit 4** — `hass.data[...]["memory"]`, typed `MemoryInterface`, is the handle consumers read. The legacy `"memory_manager"` key remains for one release as a deprecated alias, and `__init__.py`'s unload still reaches the concrete manager for `async_shutdown` deliberately: lifecycle is a backend concern, not part of the contract.

**Commit 5** — all seven consumers migrated. Notable decisions:

- **`StoreMemoryTool` → `fast_track()`.** An LLM tool write is the resident asking to be remembered, so source is forced to `explicit_user` and trust to 1.0. Trust is deliberately not an LLM-settable parameter: a model that can set its own credibility has no credibility.
- **`RecallMemoryTool` now formats trust and source** into the result text instead of importance, so the model can hedge on a 0.5-trust inference rather than asserting it. Retrieval is not endorsement, made literal in the tool output.
- **`min_importance` is filtered by callers, not by `recall()`.** The context provider and the search service both used to pass `min_importance` into the backend search. The contract has no importance filter, and `min_trust` is **not** its equivalent — passing one as the other would silently drop trustworthy-but-unremarkable memories (a fact the resident stated outright, kept at importance 0.1, would vanish). Both now filter post-recall on `metadata["importance"]`, preserving behavior exactly. A regression test pins the distinction.
- **`relevance_score` carried through `metadata`.** `search_memories` sets it on its results and the search service reports it; `MemoryRecord` has no field for it, so `_to_record()` carries it as a backend extra rather than letting the service response silently lose a field.

### Tests: two obsolete tests replaced rather than deleted

`test_format_memories_missing_fields` and `test_execute_handles_missing_fields` fed dicts lacking `type`/`content` and asserted the formatter defaulted them. `MemoryRecord` requires both, so that failure mode is now unrepresentable rather than handled. Both were replaced with tests that pin *why* the old ones are gone — deleting them silently would have looked like lost coverage.

One test was found asserting on a phantom: `test_chromadb_failure_graceful_degradation` set `side_effect` on `factory._client`, an attribute the factory does not have. `MagicMock` auto-created it, the failure never fired, and the test passed without exercising degradation at all. It now fails at the real path.

Verified: unit 1540, offline integration 268 (baseline), live-service collect 14, zero new mypy errors, AC#4 and both AC#6 scans green.

---

## 2026-07-16 — Commit 6 landed: conformance suite and docs

`tests/unit/test_memory_interface_conformance.py` is written against the contract and parametrized by backend. Adding the Memory Arm backend means adding a fixture to `backend` and nothing else. If a conformance test ever needs a per-backend special case, the contract is wrong, not the test.

`docs/MEMORY_INTERFACE.md` carries the vocabulary, the interim backend's honest noes, the `vector_recall` staleness bound verbatim, the placement ladder, the namespaced-cache rationale with its P6 pointer, and the layered-enforcement explanation. README is untouched — it does not name `MemoryManager` publicly, so spec §7's condition does not fire.

### The conformance suite found a real bug on its first run

`_derive_trust` consulted `metadata["extraction_method"]` **before** provenance. `add_memory()` defaults `extraction_method` to `"manual"` for any write that does not set one (`memory_manager.py:343`), so every `write(source="behavioral")` came back with **trust 1.0** — Pepa believing its own inferences exactly as firmly as the resident's own words. That is the false-memory failure class the trust axis exists to prevent, reintroduced by the very code meant to express it.

Fixed by ordering: explicit provenance decides, and the `extraction_method` heuristic is consulted only for legacy rows written before the contract, which carry no source. Pinned by `test_inferred_writes_are_not_fully_trusted`.

Worth recording as more than a bug — it is the argument for the conformance suite existing. Every other test in the repo passed with it in place, including the ones written for `_to_record` in commit 3. Only a test written against *what the contract promises*, rather than against what the code does, caught it.

### The conformance fixture is store-only, deliberately

It constructs the interim backend with `chroma_factory=None`, so `recall()` exercises the real keyword-fallback path. Mocking ChromaDB would mean asserting against a fake collection that answers every query with whatever the mock was told to say — testing the mock, not the contract. The degraded path is also the one that matters at 3 AM with the network down, and the contract has to hold there. Vector-backed recall is covered against a real ChromaDB in `tests/integration/test_memory_vectordb_integration.py`.

---

## 2026-07-16 — Amendment 3: the Chroma placement default is `embedded`, and the P6 gate was aimed wrong

**Supersedes:** spec §4.1's `DEFAULT_CHROMA_PLACEMENT = CHROMA_PLACEMENT_REMOTE`, spec §2's routing of the flip to P6, and this log's "Open discrepancy: Chroma placement default" entry below, which recorded the tension without resolving it.

**Decided (José, 2026-07-16):** the default is `embedded`. This is José overriding his own spec in favor of Ledger §2.2, which he is entitled to do; recorded here so the code and the spec do not silently disagree.

### Why the gate dissolved rather than being overridden

The P6 gate existed to protect the 4 GB HAOS VM (Ledger §3) from an embedded footprint measured outside that VM. But that invariant is **Casa Delta's constraint, not a property of every install** — and the Ledger's own rationale for embedded-by-default is "zero-infrastructure for public HACS users", for whom a `remote` default is simply broken on first run.

So the gate was aimed at the wrong target. Pinning the constrained host to `remote` **explicitly** protects the invariant directly, by configuration rather than by a default, and P6 is freed to measure the question it should have been measuring: whether embedded is viable in-VM if mmm4 ever wants to move there.

### What made this more than a one-line change

Placement resolves as `config.get(CONF_CHROMA_PLACEMENT, DEFAULT_CHROMA_PLACEMENT)`, and the option only came into existence in commit 2a. No existing entry has the key. Flipping the constant alone would have silently relocated every current install's vector store into the HA VM on upgrade — including Casa Delta's.

The data half of that is survivable by design (Ledger §2.2: ChromaDB is "working memory — disposable, rebuildable"; `_sync_to_chromadb` repopulates from the HA Store). The RAM half is not survivable by assertion.

**Resolved:** `async_migrate_entry`, config entry `VERSION` 1 → 2 (`CONFIG_ENTRY_VERSION` in const.py is the single source of truth, shared by the flow and the migration). v1 entries get `chroma_placement: remote` written into `entry.data`, using `setdefault` so an explicit choice is never overwritten. Written to `data` rather than `options` so a later options-flow choice still wins.

A downgrade (`entry.version > CONFIG_ENTRY_VERSION`) returns False rather than guessing what a newer schema meant.

### What this does not fix

The loud-failure ladder catches import and init failure. It does not — and cannot — catch a store that grows to ~485 MB over twenty years inside a 4 GB VM. That failure has no exception to raise. It remains P6's question, now for the right reason.

Also still open: `_vector_common.py` carries a third ChromaDB client construction site and a third embedding cache (see the AC#3 audit). A default-embedded install therefore runs three 1000-vector caches alongside an in-VM Chroma process. Unresolved, and worth knowing before P6 measures anything.

---

## 2026-07-16 — Open discrepancy: Chroma placement default

*(Heading restored: an earlier edit in this session accidentally absorbed it, orphaning this section's body under the commits 4/5 entry. Content below is unchanged from when it was first written.)*

Ledger §2.2 states Chroma placement defaults to `embedded` ("zero-infrastructure for public HACS users"), optional `remote`. Spec §4.1 states `DEFAULT_CHROMA_PLACEMENT = CHROMA_PLACEMENT_REMOTE`, with the embedded flip gated on P6's in-VM benchmark, and §2 routes the flip out of scope.

Implementation follows the spec (`remote`): it is newer, declares itself sole authority, and its caution is corroborated by Ledger §4, which records that the in-VM ground-truth run of the sizing harness is still pending. The measured figures in §4 (~222 MB RSS at ~5,000 vectors, ~485 MB at 50,000) were taken outside the 4 GB HAOS VM, so they do not yet discharge the §3 invariant.

Recorded because commit 2 writes that constant, and a reader arriving from Ledger §2.2 will otherwise read the code as a bug. Resolution belongs to P6, not P2.
