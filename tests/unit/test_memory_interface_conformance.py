"""Conformance suite for MemoryInterface.

Written against the contract, parametrized by backend. It runs today against the
interim MemoryManager; the SurrealDB-backed Memory Arm backend must pass this
file **unmodified** later. That is the whole promise of P2: migration is a
backend swap, not a rewrite.

Adding a backend means adding a fixture to `backend` below and nothing else. If
a test here needs a special case for a particular backend, the contract is
wrong, not the test.
"""

import pytest

from custom_components.pepa_sensory_arm.memory_interface import (
    MemoryCapabilityError,
    MemoryInterface,
    MemoryRecord,
)
from custom_components.pepa_sensory_arm.memory_manager import MemoryManager


@pytest.fixture
async def interim_backend(mock_hass, mock_store):
    """The interim backend in its store-only configuration.

    No factory, so recall runs the real keyword-fallback path rather than a
    mocked-out ChromaDB whose fake collection would answer every query with
    whatever the mock was told to say. The contract has to hold in this
    configuration too: a backend that cannot vector-search degrades per its
    declared capabilities and still recalls, it does not silently return
    nothing. Testing the degraded path is testing the promise that matters at
    3 AM with the network down.

    Vector-backed recall is covered against a real ChromaDB in
    tests/integration/test_memory_vectordb_integration.py.
    """
    manager = MemoryManager(
        hass=mock_hass,
        chroma_factory=None,
        config={"memory_collection_name": "conformance"},
    )
    await manager.async_initialize()
    yield manager
    await manager.async_shutdown()


# Add the Memory Arm backend here when it lands. Nothing else should change.
@pytest.fixture(params=["interim"])
async def backend(request, interim_backend):
    """Every backend claiming to satisfy MemoryInterface."""
    return {"interim": interim_backend}[request.param]


# ---- The contract is satisfied ------------------------------------------


async def test_backend_satisfies_the_protocol(backend):
    """isinstance passes -- every required member is present.

    Presence only: @runtime_checkable does not check signatures. Signatures are
    checked statically (memory_manager._assert_satisfies_contract) and behavior
    is checked by the rest of this file. All three layers are needed.
    """
    assert isinstance(backend, MemoryInterface)


def test_issubclass_is_unavailable_by_construction():
    """`capabilities` is a property, which makes this a data protocol.

    Documented so nobody "fixes" the conformance check by reaching for
    issubclass() and concluding the contract is broken.
    """
    with pytest.raises(TypeError, match="non-method members"):
        issubclass(MemoryManager, MemoryInterface)


async def test_capabilities_is_readable_without_awaiting(backend):
    """capabilities is sync by contract -- the Memory Arm backend must match."""
    caps = backend.capabilities
    assert isinstance(caps.supersession, bool)
    assert isinstance(caps.vector_recall, bool)


# ---- write / recall ------------------------------------------------------


async def test_write_then_recall_carries_provenance(backend):
    """A written belief comes back carrying who said it and how much it weighs."""
    await backend.write(
        "Ana toma cafe a las siete",
        category="fact",
        source="explicit_user",
    )

    records = await backend.recall("cafe")

    assert records, "a written memory must be recallable"
    assert all(isinstance(r, MemoryRecord) for r in records)
    record = records[0]
    assert record.content == "Ana toma cafe a las siete"
    assert record.category == "fact"
    assert record.source == "explicit_user"


async def test_write_returns_an_id_that_get_resolves(backend):
    """The id write() returns identifies the record it wrote."""
    memory_id = await backend.write(
        "La puerta del garaje se atasca",
        category="fact",
        source="behavioral",
    )

    record = await backend.get(memory_id)

    assert record is not None
    assert record.id == memory_id
    assert record.content == "La puerta del garaje se atasca"


async def test_inferred_writes_are_not_fully_trusted(backend):
    """A behavioral inference does not arrive with a user-stated fact's weight."""
    memory_id = await backend.write(
        "Probablemente prefiere la casa fresca",
        category="preference",
        source="behavioral",
    )

    record = await backend.get(memory_id)

    assert record is not None
    assert record.source == "behavioral"
    assert record.trust < 1.0


async def test_recall_respects_min_trust(backend):
    """min_trust filters on epistemic weight."""
    await backend.write("Un hecho declarado", category="fact", source="explicit_user")
    await backend.write("Una inferencia", category="fact", source="behavioral")

    trusted = await backend.recall("hecho inferencia", top_k=10, min_trust=0.9)

    assert all(r.trust >= 0.9 for r in trusted)


async def test_recall_respects_categories(backend):
    """categories restricts the taxonomy of what comes back."""
    await backend.write("Le gusta la luz tenue", category="preference", source="behavioral")
    await backend.write("La cocina tiene tres luces", category="fact", source="behavioral")

    records = await backend.recall("luz", top_k=10, categories=["preference"])

    assert all(r.category == "preference" for r in records)


async def test_recall_never_returns_none(backend):
    """A backend that cannot vector-search degrades, it does not vanish.

    An empty list means "nothing matched", never "the store was unreachable".
    """
    records = await backend.recall("nada que coincida con esto en absoluto")
    assert isinstance(records, list)


# ---- fast_track ----------------------------------------------------------


async def test_fast_track_forces_explicit_user_and_full_trust(backend):
    """The "remember this" path is definitionally the resident speaking."""
    memory_id = await backend.fast_track("Recuerda que Ana odia el brocoli")

    record = await backend.get(memory_id)

    assert record is not None
    assert record.source == "explicit_user"
    assert record.trust == 1.0


async def test_fast_track_is_recallable_before_it_returns(backend):
    """When the resident says "remember this", it is remembered by the time we answer.

    Not eventually. This is the contract's one durability guarantee, and the
    reason fast_track does not go through the debounced save.
    """
    await backend.fast_track("El numero de la vecina es importante")

    records = await backend.recall("vecina")

    assert any("vecina" in r.content for r in records)


async def test_fast_track_accepts_a_category(backend):
    """Category is caller's choice; provenance is not."""
    memory_id = await backend.fast_track("Prefiere la puerta cerrada", category="preference")

    record = await backend.get(memory_id)

    assert record is not None
    assert record.category == "preference"
    assert record.source == "explicit_user"


# ---- Capability honesty --------------------------------------------------


async def test_supersede_matches_its_declared_capability(backend):
    """Either supersession works, or it raises by name. Never a quiet no-op."""
    memory_id = await backend.write("El AC a 72", category="fact", source="explicit_user")

    if backend.capabilities.supersession:
        new_id = await backend.supersede(memory_id, "El AC a 70", source="explicit_user")
        old = await backend.get(memory_id)
        assert old is not None
        assert old.superseded_by == new_id
        assert old.content == "El AC a 72", "supersede must never mutate the original"
    else:
        with pytest.raises(MemoryCapabilityError) as excinfo:
            await backend.supersede(memory_id, "El AC a 70", source="explicit_user")
        # The message must be actionable without reading the source.
        assert "supersede" in str(excinfo.value)
        assert excinfo.value.op == "supersede"
        assert excinfo.value.backend


async def test_records_read_as_current_when_supersession_is_unsupported(backend):
    """Without supersession, nothing may claim to have a successor."""
    if backend.capabilities.supersession:
        pytest.skip("backend supports supersession")

    await backend.write("Cualquier cosa", category="fact", source="behavioral")
    records = await backend.recall("cualquier")

    assert all(r.superseded_by is None for r in records)


async def test_interim_backend_declares_its_noes(interim_backend):
    """The interim backend's capability flags, pinned.

    Not parametrized: this asserts what THIS backend cannot do. The Memory Arm
    backend will declare different values, and that is the point -- the flags
    are honest per backend, so consumers can ask instead of assume.
    """
    caps = interim_backend.capabilities

    assert caps.supersession is False
    assert caps.trust_dynamics is False
    assert caps.durable_fast_track is True
    assert caps.provenance_enforced is False
    # Store-only fixture: no factory, so no vector recall -- and it says so
    # rather than pretending. Context Mode independence is pinned separately in
    # test_borrowed_client_killed.py.
    assert caps.vector_recall is False


# ---- Admin surface -------------------------------------------------------


async def test_get_returns_none_for_unknown_id(backend):
    """An unknown id is absence, not an error."""
    assert await backend.get("no-such-id") is None


async def test_delete_removes_the_record(backend):
    """A deleted record is gone."""
    memory_id = await backend.write("Efimero", category="event", source="behavioral")

    assert await backend.delete(memory_id) is True
    assert await backend.get(memory_id) is None


async def test_delete_reports_false_for_unknown_id(backend):
    """Deleting nothing deletes nothing, and says so."""
    assert await backend.delete("no-such-id") is False


async def test_list_all_returns_records(backend):
    """list_all speaks the contract's type, like everything else."""
    await backend.write("Uno", category="fact", source="behavioral")
    await backend.write("Dos", category="fact", source="behavioral")

    records = await backend.list_all()

    assert len(records) >= 2
    assert all(isinstance(r, MemoryRecord) for r in records)


async def test_list_all_filters_by_category(backend):
    """category narrows the listing."""
    await backend.write("Un hecho", category="fact", source="behavioral")
    await backend.write("Una preferencia", category="preference", source="behavioral")

    records = await backend.list_all(category="preference")

    assert records
    assert all(r.category == "preference" for r in records)


async def test_clear_all_empties_the_store(backend):
    """clear_all reports how many it removed, and leaves nothing."""
    await backend.write("Uno", category="fact", source="behavioral")
    await backend.write("Dos", category="fact", source="behavioral")

    removed = await backend.clear_all()

    assert removed >= 2
    assert await backend.list_all() == []
