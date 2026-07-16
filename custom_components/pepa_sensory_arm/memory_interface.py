"""Memory Interface contract for the Pepa Sensory Arm.

This module defines the single contract behind which memory backends are
swappable implementations: today the interim ChromaDB-backed ``MemoryManager``,
later the SurrealDB-backed Memory Arm. Migration is a backend swap, not a
rewrite -- the target backend satisfies this Protocol and passes the same
conformance suite.

Why a Protocol and not an ABC:
    ``MemoryManager`` is inherited Radlein code being reshaped in place. A
    Protocol imposes no inheritance on it, and the Memory Arm backend -- which
    will live outside this component entirely -- satisfies the contract
    structurally, without importing anything from here.

Field semantics are sourced from the Pepa Memory Architecture Design,
SurrealDB schema v0.1 (2026-07-06). That alignment is load-bearing: the
vocabulary below is 1:1 with the target schema so that ETL into the Memory
Arm is a mapping, not a reinterpretation.

Runtime checking, and its limits:
    ``MemoryInterface`` is ``@runtime_checkable``, so ``isinstance(obj, MemoryInterface)``
    works and verifies that every required member is *present*. It does NOT
    verify signatures -- a backend whose ``write()`` takes entirely the wrong
    arguments still passes ``isinstance``. ``issubclass()`` is unavailable by
    construction: ``capabilities`` is a property, which makes this a data
    protocol, and data protocols raise ``TypeError`` on ``issubclass()``.

    Presence is therefore checked at runtime, signatures are checked statically
    by mypy (assign a backend instance to a ``MemoryInterface``-annotated name),
    and behavior is checked by the conformance suite. All three are needed; none
    substitutes for another.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

from .exceptions import PepaSensoryArmError

# Coarse taxonomy. 1:1 with the interim backend's existing memory types --
# ETL fidelity to SurrealDB schema v0.1 wins over a tidier taxonomy.
Category = Literal["fact", "preference", "context", "event"]

# Provenance class. Assigned at write, immutable thereafter: how a belief
# entered the system is a historical fact, not a revisable judgment.
#   explicit_user -- the resident stated it (tool writes, service calls)
#   behavioral    -- inferred from observed conversation (extraction pipeline)
#   measured      -- read from an instrument. Reserved; no current producer.
Source = Literal["explicit_user", "behavioral", "measured"]

# Pepa's revisable judgment about what kind of belief this is.
#
# NOTE: 'policy' is intentionally absent, and its absence is structural rather
# than an oversight. Flat files are the policy store; the memory system must be
# unable to hold policy, so that no amount of conversation can talk Pepa into a
# new rule about care.
EpistemicClass = Literal["observation", "interpretation", "prediction"]

# Corroboration-gated lifecycle. One-directional: a belief advances as evidence
# accumulates and does not silently fall back.
Status = Literal["raw", "hypothesis", "tested", "confirmed"]


class MemoryCapabilityError(PepaSensoryArmError):
    """Raised when an operation is not supported by the active backend.

    Degradation is loud. A backend that cannot honor part of the contract says
    so by name -- it never returns a plausible-looking approximation, and it
    never silently no-ops. The message identifies the operation, the backend
    that refused it, and the lane in which the capability arrives, so that a
    log line is actionable without reading this source.

    Example:
        raise MemoryCapabilityError(
            "supersede",
            "interim MemoryManager",
            "the Memory Arm backend",
        )
    """

    def __init__(self, op: str, backend: str, arrives_with: str | None = None) -> None:
        """Initialize the error.

        Args:
            op: The unsupported operation, e.g. "supersede".
            backend: The backend that does not support it.
            arrives_with: Where the capability lands, if known.
        """
        self.op = op
        self.backend = backend
        self.arrives_with = arrives_with

        message = f"{op}() is not supported by the {backend} backend"
        if arrives_with is not None:
            message = f"{message}; arrives with {arrives_with}"
        super().__init__(message)


@dataclass(frozen=True)
class MemoryCapabilities:
    """What a backend can actually do. Declared honestly, including the noes.

    Consumers read these flags to decide whether an operation is worth
    attempting. A backend that lies here defeats the point of the contract.

    Attributes:
        supersession: ``supersede()`` creates successors and maintains the
            forward pointer. False backends raise ``MemoryCapabilityError``.
        trust_dynamics: Trust changes over time as evidence accumulates. False
            means trust is fixed at write.
        vector_recall: Semantic recall is available -- see the liveness contract
            below. False backends degrade to their declared fallback (interim:
            keyword search), never to silence.
        durable_fast_track: ``fast_track()`` survives process death before
            canonical promotion.
        provenance_enforced: The store itself enforces source immutability.
            False means immutability is convention, upheld by this component's
            own discipline and nothing else.

    The ``vector_recall`` liveness contract -- bounded staleness:
        The naive reading, "True iff the vector store is reachable right now",
        cannot be implemented by a sync property: reachability is network I/O.
        The contract therefore defines ``vector_recall`` as bounded-staleness
        availability. The value reflects the client factory's availability flag,
        refreshed (a) as a side effect of every real client operation -- any call
        that succeeds sets it True, any connection-class failure sets it False --
        and (b) by a TTL'd background probe.

        So "available" means "was reachable within the last TTL seconds, or on
        the last operation" -- not "is reachable at this instant". Backends whose
        availability is genuinely static may hold the flag constant.

        This is deliberately not solved by making ``capabilities`` async. The
        sync shape is what the Memory Arm backend must satisfy later, and the
        conformance suite reads it without awaiting.
    """

    supersession: bool
    trust_dynamics: bool
    vector_recall: bool
    durable_fast_track: bool
    provenance_enforced: bool


@dataclass(frozen=True)
class MemoryRecord:
    """A single belief, carrying its own epistemic weight.

    Every record surfaced by ``recall()`` carries trust, status, and source so
    that the consumer decides how much authority to grant it. Retrieval is not
    endorsement.

    Content is immutable. Corrections go through ``supersede()``, which appends
    a successor and leaves the original intact -- what Pepa believed last week
    remains inspectable after it turns out to be wrong.
    """

    id: str
    """Backend-issued identifier."""

    content: str
    """The assertion, as captured (EN/ES/Spanglish). Immutable."""

    category: Category
    """Coarse taxonomy."""

    source: Source
    """Provenance. Written once, never relabeled."""

    created_at: float
    """Epoch seconds. Immutable."""

    updated_at: float
    """Epoch seconds."""

    epistemic_class: EpistemicClass = "observation"
    """Pepa's revisable judgment about the kind of belief."""

    trust: float = 0.5
    """Epistemic weight in [0, 1].

    Distinct from importance, which lives in ``metadata`` and measures salience.
    Trust is how much a belief should be believed; importance is how much it
    should be surfaced. Never map one onto the other -- a trivial certainty and
    a load-bearing guess are not the same thing.
    """

    status: Status = "raw"
    """Corroboration-gated lifecycle position."""

    safety_critical: bool = False
    """Exempt from decay and pruning; maximum retrieval authority."""

    superseded_by: str | None = None
    """Forward pointer to the successor record. None means current."""

    attribute: str | None = None
    """Normalized key (e.g. "ac_temperature") for contradiction candidacy."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Backend extras. The interim backend's importance, expires_at,
    is_transient, entities_involved, topics, and extraction_method live here:
    implementation detail, not contract."""

    def __post_init__(self) -> None:
        """Enforce the trust range.

        The frozen dataclass is the only place this invariant can be enforced
        cheaply, and it is worth enforcing precisely because
        ``provenance_enforced`` is False on the interim backend -- the store is
        not going to catch it.
        """
        if not 0.0 <= self.trust <= 1.0:
            raise ValueError(f"trust must be in [0, 1], got {self.trust!r} (memory id: {self.id})")


@runtime_checkable
class MemoryInterface(Protocol):
    """The contract every memory backend satisfies.

    Four core operations carry the epistemics; an admin surface exists because
    the Home Assistant services and current consumers need it. See the module
    docstring for what runtime checking against this Protocol does and does not
    verify.
    """

    # ---- Core contract ---------------------------------------------------

    async def write(
        self,
        content: str,
        category: Category,
        source: Source,
        *,
        epistemic_class: EpistemicClass = "observation",
        trust: float | None = None,
        safety_critical: bool = False,
        attribute: str | None = None,
        conversation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Persist a belief. Provenance is fixed here, forever.

        Args:
            content: The assertion, as captured.
            category: Coarse taxonomy.
            source: Provenance class. Immutable once written.
            epistemic_class: The kind of belief this is.
            trust: Epistemic weight in [0, 1]. None means the backend's default
                for this source.
            safety_critical: Exempt from decay; maximum retrieval authority.
            attribute: Normalized key for contradiction candidacy.
            conversation_id: Originating conversation, if any.
            metadata: Backend extras.

        Returns:
            The new record's id.
        """
        ...

    async def fast_track(
        self,
        content: str,
        *,
        category: Category = "fact",
        conversation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """The "remember this" path.

        Contract guarantee: locally durable and immediately recallable before
        the call returns. When the resident says "remember this", the thing is
        remembered by the time Pepa answers -- not eventually.

        ``source`` is forced to "explicit_user" and ``trust`` to 1.0; neither is
        a parameter, because this path is definitionally the resident speaking.
        Canonical promotion is a backend concern (interim: none; target: WAL
        then SurrealDB).

        Args:
            content: The assertion, as stated.
            category: Coarse taxonomy.
            conversation_id: Originating conversation, if any.
            metadata: Backend extras.

        Returns:
            The new record's id.
        """
        ...

    async def recall(
        self,
        query: str,
        *,
        top_k: int = 5,
        categories: list[Category] | None = None,
        min_trust: float = 0.0,
        include_superseded: bool = False,
    ) -> list[MemoryRecord]:
        """Semantic recall. Retrieval is not endorsement.

        Every result carries trust, status, and source so the consumer decides
        weight. Backends that cannot vector-search degrade per their declared
        capabilities (interim: keyword fallback) and never silently return
        nothing -- an empty list means "nothing matched", not "the vector store
        was down".

        Args:
            query: Natural-language query.
            top_k: Maximum results.
            categories: Restrict to these categories; None means all.
            min_trust: Drop results below this trust.
            include_superseded: Include records that have a successor.

        Returns:
            Matching records, most relevant first.
        """
        ...

    async def supersede(
        self,
        old_id: str,
        new_content: str,
        *,
        source: Source,
        epistemic_class: EpistemicClass = "observation",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Append-only correction.

        Creates a successor and points ``old.superseded_by`` at it. Never
        mutates the original's content: the history of what Pepa believed is
        itself evidence, and overwriting it destroys the only record of how a
        wrong belief was arrived at.

        Args:
            old_id: The record being corrected.
            new_content: The corrected assertion.
            source: Provenance of the correction.
            epistemic_class: The kind of belief the successor is.
            metadata: Backend extras for the successor.

        Returns:
            The successor's id.

        Raises:
            MemoryCapabilityError: If ``capabilities.supersession`` is False.
        """
        ...

    # ---- Admin / maintenance surface -------------------------------------
    # Non-canonical. Exists because the HA services and current consumers need
    # it, not because the epistemics call for it.

    async def get(self, memory_id: str) -> MemoryRecord | None:
        """Fetch one record by id, or None if absent."""
        ...

    async def delete(self, memory_id: str) -> bool:
        """Hard delete.

        The target backend MUST reject deleting a record that another record
        supersedes (schema v0.1: ON DELETE REJECT) -- deleting a superseded
        record would strand its successor's history. The interim backend has no
        supersession and so performs a plain delete.

        Returns:
            True if a record was deleted.
        """
        ...

    async def list_all(
        self,
        *,
        category: Category | None = None,
        limit: int = 100,
    ) -> list[MemoryRecord]:
        """List records, most recent first."""
        ...

    async def clear_all(self) -> int:
        """Delete every record.

        Returns:
            The number deleted.
        """
        ...

    # ---- Honesty surface -------------------------------------------------

    @property
    def capabilities(self) -> MemoryCapabilities:
        """What this backend can actually do. Sync by contract."""
        ...
