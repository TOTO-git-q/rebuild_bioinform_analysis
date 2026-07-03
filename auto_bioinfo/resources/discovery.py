"""Local deterministic resource discovery + search-audit contract (WP-08 / T-08-05..10).

The resource-discovery stage's *local, offline, deterministic* core.  Given a
frozen :class:`~auto_bioinfo.core.schemas.EvidencePlan` (and an optional resolved
scope + ontology mappings), it constructs an **auditable**
:class:`SearchQuery` that keeps the original and the standardised entities
separate (T-08-05), runs an offline replay adapter
(:mod:`auto_bioinfo.adapters.offline_search`) through the inert network policy
(:mod:`auto_bioinfo.resources.search_policy`), and records everything needed to
*replay the same request* — tool identity, echoed params, pagination and the
raw-response hash — as a :class:`SearchRun` (T-08-06).  From the raw response it
normalises :class:`~auto_bioinfo.core.schemas.ResourceCandidate` records and
de-duplicates them by ``namespace``/``identifier`` (T-08-07), proposes a
:class:`RankingProposal` whose priority is **never** a fact-verification and
whose every reason traces back to a candidate field (T-08-08), decides a bounded
:class:`SearchStopDecision` so an unbounded search loop is impossible (T-08-09),
and keeps explicit audit records for empty / failed / filtered results (T-08-10).

Design constraints (mirroring the house contract style):

- **Pure, deterministic, offline.**  Every function is a total function of its
  explicit in-memory inputs plus the offline adapter's recorded response.  No
  network/socket, no HTTP, no environment/credential read, **no real clock read**,
  no randomness, no subprocess, no file/DB/queue/event side effect.  Inputs are
  never mutated.  Produced ``SearchQuery`` / candidate projections carry an empty
  ``created_at`` so byte-identical inputs yield byte-identical output.
- **Audit first, no silent drop.**  An empty, failed, or un-normalisable
  (filtered) result is *recorded* with a reason, never quietly discarded, so the
  final report can explain why there were no candidates.
- **Ranking is priority, not truth.**  A :class:`RankingProposal` orders
  candidates for review only; it asserts nothing about whether a candidate exists
  or is usable — that is verification's (WP-09) and feasibility's (WP-10) job.
- **No fabricated identifiers.**  A candidate's accession / PMID / DOI comes from
  the offline tool's recorded response, never from this module, and every produced
  candidate stays ``UNVERIFIED`` until WP-09 verifies it.
- **Bounded vocabulary.**  Statuses and reason codes are small stable sets; a
  caller branches on the machine-readable code, never the human message.

This module defines command contracts only.  It does not verify a candidate,
build a profile, assess feasibility, lock anything, persist, or emit an event.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ..adapters.offline_search import (
    RAW_STATUS_EMPTY,
    RAW_STATUS_ERROR,
    REPLAY_RETRIEVAL_MODE,
    SEARCH_DOMAINS,
)
from ..core import common
from ..core.ids import hash_payload, make_stable_id
from ..core.schemas import CANONICAL_SCHEMA_VERSION, ResourceCandidate
from ..core.validation import validate_resource_candidate
from .search_policy import NetworkAccessPolicy

DRAFT_STATUS = "draft"

# --- Bounded SearchRun status + reason vocabularies --------------------------
RUN_STATUS_CANDIDATES_FOUND = "candidates_found"
RUN_STATUS_EMPTY = "empty"
RUN_STATUS_FAILED = "failed"
RUN_STATUS_BLOCKED = "blocked"
RUN_STATUS_REJECTED_MALFORMED = "rejected_malformed"
RUN_STATUSES = (
    RUN_STATUS_CANDIDATES_FOUND,
    RUN_STATUS_EMPTY,
    RUN_STATUS_FAILED,
    RUN_STATUS_BLOCKED,
    RUN_STATUS_REJECTED_MALFORMED,
)

CODE_QUERY_BUILT = "SEARCH_QUERY_BUILT"
CODE_CANDIDATES_FOUND = "SEARCH_CANDIDATES_FOUND"
CODE_EMPTY_RESULT = "SEARCH_EMPTY_RESULT"
CODE_TOOL_FAILED = "SEARCH_TOOL_FAILED"
CODE_DOMAIN_BLOCKED = "SEARCH_DOMAIN_BLOCKED"
CODE_QUERY_MALFORMED = "SEARCH_QUERY_MALFORMED"
CODE_ADAPTER_MALFORMED = "SEARCH_ADAPTER_MALFORMED"
RUN_REASON_CODES = (
    CODE_QUERY_BUILT,
    CODE_CANDIDATES_FOUND,
    CODE_EMPTY_RESULT,
    CODE_TOOL_FAILED,
    CODE_DOMAIN_BLOCKED,
    CODE_QUERY_MALFORMED,
    CODE_ADAPTER_MALFORMED,
)

# --- Bounded per-record audit disposition ------------------------------------
DISPOSITION_NORMALIZED = "normalized"
DISPOSITION_DUPLICATE = "duplicate"
DISPOSITION_FILTERED = "filtered"
RECORD_DISPOSITIONS = (DISPOSITION_NORMALIZED, DISPOSITION_DUPLICATE, DISPOSITION_FILTERED)

# --- Bounded stop-condition vocabulary (T-08-09) -----------------------------
STOP_RESULTS_STABLE = "results_stable"
STOP_PAGE_BUDGET = "page_budget_reached"
STOP_RESULT_BUDGET = "result_budget_reached"
STOP_DUPLICATE_RATE = "duplicate_rate_exceeded"
STOP_MANUAL = "manual_decision"
STOP_CONTINUE = "continue"
STOP_CONDITIONS = (
    STOP_RESULTS_STABLE,
    STOP_PAGE_BUDGET,
    STOP_RESULT_BUDGET,
    STOP_DUPLICATE_RATE,
    STOP_MANUAL,
    STOP_CONTINUE,
)

# --- Query-build result vocabulary -------------------------------------------
QUERY_BUILT = "query_built"
QUERY_NO_TERMS = "no_terms"
QUERY_MALFORMED = "malformed"
QUERY_STATUSES = (QUERY_BUILT, QUERY_NO_TERMS, QUERY_MALFORMED)


# =============================================================================
# T-08-05: auditable SearchQuery construction from an EvidencePlan
# =============================================================================
@dataclass(frozen=True)
class SearchQuery:
    """An inert, auditable query built from an EvidencePlan + resolved scope.

    ``original_terms`` are the verbatim entities the request/scope stated;
    ``standard_terms`` are the standardised identifiers from resolved ontology
    mappings.  Keeping them **separate** is the T-08-05 guarantee: the query never
    loses the original entity, and never presents a standardised id as if it were
    the user's word.  ``filters`` carry bounded structured constraints (e.g.
    organism / modality).  The query is a draft projection; it is never persisted
    or executed on its own.
    """

    domain: str
    original_terms: list[str] = field(default_factory=list)
    standard_terms: list[str] = field(default_factory=list)
    filters: dict[str, Any] = field(default_factory=dict)
    page: int = 1
    page_size: int = 20
    evidence_plan_id: str = ""
    research_spec_id: str = ""
    schema_version: str = CANONICAL_SCHEMA_VERSION
    search_query_id: str = ""
    status: str = DRAFT_STATUS
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = {
            "domain": self.domain,
            "original_terms": list(self.original_terms),
            "standard_terms": list(self.standard_terms),
            "filters": copy.deepcopy(self.filters),
            "page": self.page,
            "page_size": self.page_size,
            "evidence_plan_id": self.evidence_plan_id,
            "research_spec_id": self.research_spec_id,
            "schema_version": self.schema_version,
            "status": self.status,
            "created_at": self.created_at,
        }
        data["search_query_id"] = self.search_query_id or make_stable_id(
            "search_query",
            {
                "domain": self.domain,
                "original_terms": sorted(self.original_terms),
                "standard_terms": sorted(self.standard_terms),
                "filters": self.filters,
                "evidence_plan_id": self.evidence_plan_id,
                "page": self.page,
            },
        )
        return data

    def replay_key_payload(self) -> dict[str, Any]:
        """The content-bearing projection an adapter replays against."""
        return {
            "domain": self.domain,
            "original_terms": list(self.original_terms),
            "standard_terms": list(self.standard_terms),
            "filters": copy.deepcopy(self.filters),
            "page": self.page,
            "page_size": self.page_size,
        }


@dataclass(frozen=True)
class SearchQueryResult:
    status: str
    reason_code: str
    message: str
    query: dict[str, Any] | None = None
    binding: dict[str, Any] = field(default_factory=dict)

    @property
    def built(self) -> bool:
        return self.status == QUERY_BUILT

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason_code": self.reason_code,
            "message": self.message,
            "built": self.built,
            "query": copy.deepcopy(self.query) if self.query is not None else None,
            "binding": copy.deepcopy(self.binding),
        }


def _as_mapping(obj: Any) -> Mapping[str, Any] | None:
    if isinstance(obj, Mapping):
        return obj
    to_dict = getattr(obj, "to_dict", None)
    if callable(to_dict):
        result = to_dict()
        if isinstance(result, Mapping):
            return result
    return None


def _distinct_nonblank(values: Any) -> list[str]:
    """Order-preserving distinct non-blank strings from an iterable-or-none."""
    out: list[str] = []
    if not isinstance(values, (list, tuple)):
        return out
    for v in values:
        if isinstance(v, str) and v.strip() and v.strip() not in out:
            out.append(v.strip())
    return out


def build_search_query(
    evidence_plan: Any,
    *,
    domain: str,
    scope_bundle: Any = None,
    ontology_mappings: Any = None,
    filters: Mapping[str, Any] | None = None,
    page: int = 1,
    page_size: int = 20,
) -> SearchQueryResult:
    """Construct an auditable :class:`SearchQuery` from an EvidencePlan (+ scope).

    ``original_terms`` are drawn from the resolved scope (species / tissues /
    conditions / comparisons) and the evidence plan's axes — the verbatim entities.
    ``standard_terms`` are the ``mapped_id`` of any *resolved* ontology mapping;
    an unresolved / ambiguous mapping never contributes a standard term (it is not
    a fact).  Fails closed on a malformed plan / domain and when no usable term
    could be derived (``no_terms``) rather than issuing an empty query.
    """
    binding: dict[str, Any] = {"domain": domain, "evidence_plan_kind": type(evidence_plan).__name__}

    if domain not in SEARCH_DOMAINS:
        return SearchQueryResult(QUERY_MALFORMED, CODE_QUERY_MALFORMED, f"domain must be one of {SEARCH_DOMAINS}, got {domain!r}", binding=binding)

    plan = _as_mapping(evidence_plan)
    if plan is None:
        return SearchQueryResult(
            QUERY_MALFORMED, CODE_QUERY_MALFORMED, f"evidence_plan must be a mapping/EvidencePlan, not {type(evidence_plan).__name__}", binding=binding
        )

    research_spec_id = str(plan.get("research_spec_id", "") or "")
    if common.validate_identifier(research_spec_id, "research_spec_id"):
        return SearchQueryResult(QUERY_MALFORMED, CODE_QUERY_MALFORMED, "evidence_plan is missing a valid research_spec_id", binding=binding)

    if page < 1 or page_size < 1:
        return SearchQueryResult(QUERY_MALFORMED, CODE_QUERY_MALFORMED, "page and page_size must be >= 1", binding=binding)

    # Original entities: verbatim scope facts + evidence axes.
    original: list[str] = []
    scope = _as_mapping(scope_bundle) if scope_bundle is not None else None
    if scope is not None:
        for axis in ("species", "tissues", "conditions", "comparisons"):
            for term in _distinct_nonblank(scope.get(axis)):
                if term not in original:
                    original.append(term)
    for axis in _distinct_nonblank(plan.get("evidence_axes")):
        if axis not in original:
            original.append(axis)

    # Standard entities: only *resolved* ontology mappings contribute an id.
    standard: list[str] = []
    if isinstance(ontology_mappings, (list, tuple)):
        for m in ontology_mappings:
            mapping = _as_mapping(m)
            if mapping is None:
                continue
            if str(mapping.get("status")) == "mapped":
                mapped_id = str(mapping.get("mapped_id", "") or "").strip()
                if mapped_id and mapped_id not in standard:
                    standard.append(mapped_id)

    if not original and not standard:
        return SearchQueryResult(
            QUERY_NO_TERMS,
            CODE_QUERY_MALFORMED,
            "no original or standard search term could be derived from the plan/scope; refusing to issue an empty query",
            binding=binding,
        )

    query = SearchQuery(
        domain=domain,
        original_terms=original,
        standard_terms=standard,
        filters=dict(filters or {}),
        page=page,
        page_size=page_size,
        evidence_plan_id=str(plan.get("evidence_plan_id", "") or ""),
        research_spec_id=research_spec_id,
    ).to_dict()
    binding["original_term_count"] = len(original)
    binding["standard_term_count"] = len(standard)
    return SearchQueryResult(QUERY_BUILT, CODE_QUERY_BUILT, "search query built", query=query, binding=binding)


# =============================================================================
# T-08-07: ResourceCandidate normalisation + dedup by namespace/identifier
# =============================================================================
def _candidate_dedup_key(namespace: str, identifier: str) -> str:
    return f"{namespace.strip().upper()}::{identifier.strip().upper()}"


def normalize_candidate(raw_record: Mapping[str, Any], query: Mapping[str, Any]) -> dict[str, Any] | None:
    """Normalise one raw search record into a ResourceCandidate dict, or ``None``.

    A record must carry a non-blank ``namespace`` and ``identifier`` (its stable
    address); a record without one cannot be de-duplicated or verified and is
    *filtered* (the caller records why).  The produced candidate is always
    ``UNVERIFIED`` — discovery never asserts a resource exists.
    """
    if not isinstance(raw_record, Mapping):
        return None
    namespace = str(raw_record.get("namespace", "") or "").strip()
    identifier = str(raw_record.get("identifier", "") or raw_record.get("accession", "") or "").strip()
    if not namespace or not identifier:
        return None

    domain = str(query.get("domain", "") or "")
    resource_type = {
        "dataset": "dataset_candidate",
        "literature": "paper_candidate",
        "annotation": "annotation_candidate",
    }.get(domain, "resource_candidate")

    source_class = str(raw_record.get("source_class", "") or "PUBLIC_DATABASE")
    candidate = ResourceCandidate(
        resource_name=str(raw_record.get("title", "") or identifier),
        resource_type=resource_type,
        verified=False,  # discovery never verifies; WP-09 does
        source_status=str(raw_record.get("source_status", "") or "reported_by_search_tool"),
        status="candidate",
        accession=identifier,
        source_class=source_class,
        retrieval_mode=REPLAY_RETRIEVAL_MODE,
        verification_level="UNVERIFIED",
    )
    data: dict[str, Any] = {
        "schema_version": candidate.schema_version,
        "resource_candidate_id": make_stable_id(
            "resource_candidate", {"namespace": namespace, "identifier": identifier, "evidence_plan_id": query.get("evidence_plan_id", "")}
        ),
        "resource_name": candidate.resource_name,
        "resource_type": candidate.resource_type,
        "verified": candidate.verified,
        "source_status": candidate.source_status,
        "status": candidate.status,
        "accession": candidate.accession,
        "source_class": candidate.source_class,
        "retrieval_mode": candidate.retrieval_mode,
        "verification_level": candidate.verification_level,
        "created_at": "",
        # Discovery metadata (audit-only; not a verification fact).
        "namespace": namespace.upper(),
        "identifier": identifier,
        "dedup_key": _candidate_dedup_key(namespace, identifier),
        "discovery_domain": domain,
        "discovery_tool": str(query.get("tool_name", "") or ""),
        "source_uri": str(raw_record.get("source_uri", "") or ""),
        "raw_fields": {k: v for k, v in raw_record.items() if k not in {"namespace", "identifier"}},
    }
    return data


def dedupe_candidates(candidates: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """De-duplicate by ``dedup_key`` (namespace/identifier).

    Returns ``(unique, duplicate_audit_records)``.  The first occurrence of a key
    is kept; later occurrences are recorded as duplicate audit records (never
    silently dropped), so the same resource is not filed twice merely because two
    queries surfaced it (T-08-07).
    """
    seen: dict[str, str] = {}
    unique: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    for cand in candidates:
        key = str(cand.get("dedup_key", ""))
        if key in seen:
            duplicates.append(
                {
                    "disposition": DISPOSITION_DUPLICATE,
                    "dedup_key": key,
                    "resource_candidate_id": cand.get("resource_candidate_id", ""),
                    "kept_resource_candidate_id": seen[key],
                    "reason": "same namespace/identifier already recorded from an earlier result",
                }
            )
        else:
            seen[key] = str(cand.get("resource_candidate_id", ""))
            unique.append(cand)
    return unique, duplicates


# =============================================================================
# T-08-08: ranking as *priority*, never fact-verification
# =============================================================================
@dataclass(frozen=True)
class RankingProposal:
    """An ordered *priority* proposal over candidates, with traceable reasons.

    ``order`` lists candidate ids best-first; ``reasons`` maps each candidate id
    to the concrete fields that drove its priority.  A ranking asserts **nothing**
    about existence or usability — the flags below stay ``False`` and the object
    is explicit that priority is not verification (T-08-08).
    """

    order: list[str] = field(default_factory=list)
    scores: dict[str, float] = field(default_factory=dict)
    reasons: dict[str, list[str]] = field(default_factory=dict)
    asserts_verification: bool = False
    asserts_feasibility: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "order": list(self.order),
            "scores": dict(self.scores),
            "reasons": {k: list(v) for k, v in self.reasons.items()},
            "asserts_verification": False,
            "asserts_feasibility": False,
            "note": "ranking is a review priority only; it is not evidence a resource exists or is usable",
        }


def propose_ranking(candidates: list[dict[str, Any]], query: Mapping[str, Any]) -> RankingProposal:
    """Propose a deterministic review priority whose reasons trace to fields.

    The priority signal is intentionally shallow and field-derived: a candidate
    scores for each query term (original or standard) that appears in its title /
    identifier / raw fields.  Ties break by candidate id so the order is stable.
    No score is a verification; the proposal says so explicitly.
    """
    terms = [t.lower() for t in list(query.get("original_terms", [])) + list(query.get("standard_terms", [])) if str(t).strip()]
    scores: dict[str, float] = {}
    reasons: dict[str, list[str]] = {}
    for cand in candidates:
        cid = str(cand.get("resource_candidate_id", ""))
        haystack = " ".join(
            [str(cand.get("resource_name", "")), str(cand.get("identifier", "")), " ".join(f"{k}={v}" for k, v in (cand.get("raw_fields") or {}).items())]
        ).lower()
        matched: list[str] = []
        for term in terms:
            if term and term in haystack:
                matched.append(f"query term {term!r} appears in candidate field(s)")
        scores[cid] = float(len(matched))
        reasons[cid] = matched or ["no query term matched a candidate field; lowest priority"]
    order = sorted(scores, key=lambda cid: (-scores[cid], cid))
    return RankingProposal(order=order, scores=scores, reasons=reasons)


# =============================================================================
# T-08-09: bounded stop decision (no unbounded loop)
# =============================================================================
@dataclass(frozen=True)
class SearchStopDecision:
    """A bounded reason for stopping (or continuing) a search session."""

    condition: str
    stop: bool
    message: str
    observed: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"condition": self.condition, "stop": self.stop, "message": self.message, "observed": dict(self.observed)}


def decide_stop(
    *,
    page: int,
    page_budget: int,
    total_unique: int,
    result_budget: int,
    new_unique_this_page: int,
    duplicate_rate: float,
    max_duplicate_rate: float = 0.9,
    manual_stop: bool = False,
) -> SearchStopDecision:
    """Decide whether to stop, evaluating the bounded stop conditions in order.

    A hard ``page_budget`` guarantees termination (T-08-09: no unbounded loop).
    The other conditions — a manual decision, a filled result budget, a
    no-new-unique "stable" page, and an excessive duplicate rate — stop earlier.
    All inputs are caller-tracked counters (never a wall-clock read).
    """
    observed = {
        "page": page,
        "page_budget": page_budget,
        "total_unique": total_unique,
        "result_budget": result_budget,
        "new_unique_this_page": new_unique_this_page,
        "duplicate_rate": round(float(duplicate_rate), 6),
    }
    if manual_stop:
        return SearchStopDecision(STOP_MANUAL, True, "a human decided to stop the search", observed)
    if page >= page_budget:
        return SearchStopDecision(STOP_PAGE_BUDGET, True, f"page budget {page_budget} reached", observed)
    if result_budget > 0 and total_unique >= result_budget:
        return SearchStopDecision(STOP_RESULT_BUDGET, True, f"result budget {result_budget} reached", observed)
    if new_unique_this_page == 0:
        return SearchStopDecision(STOP_RESULTS_STABLE, True, "no new unique candidate on the last page; results are stable", observed)
    if duplicate_rate >= max_duplicate_rate:
        return SearchStopDecision(STOP_DUPLICATE_RATE, True, f"duplicate rate {duplicate_rate:.3f} exceeded {max_duplicate_rate}", observed)
    return SearchStopDecision(STOP_CONTINUE, False, "no stop condition met; more pages may be fetched", observed)


# =============================================================================
# T-08-06 + T-08-10: SearchRun record (replayable) + empty/failed/filtered audit
# =============================================================================
@dataclass(frozen=True)
class SearchRun:
    """A replayable record of one search call (T-08-06) + its audit (T-08-10).

    Carries the query, the tool identity, the echoed params, the pagination facts
    and the ``raw_response_hash`` — enough to replay the exact request — plus the
    normalised candidates, the per-record audit dispositions (duplicate /
    filtered), and, when nothing usable came back, an explicit empty/failed reason.
    """

    status: str
    reason_code: str
    message: str
    search_run_id: str
    query: dict[str, Any]
    tool: dict[str, Any] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)
    pagination: dict[str, Any] = field(default_factory=dict)
    raw_response_hash: str = ""
    retrieval_mode: str = ""
    candidates: list[dict[str, Any]] = field(default_factory=list)
    audit_records: list[dict[str, Any]] = field(default_factory=list)
    ranking: dict[str, Any] | None = None
    network_decision: dict[str, Any] | None = None
    created_at: str = ""

    @property
    def has_candidates(self) -> bool:
        return self.status == RUN_STATUS_CANDIDATES_FOUND

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason_code": self.reason_code,
            "message": self.message,
            "has_candidates": self.has_candidates,
            "search_run_id": self.search_run_id,
            "query": copy.deepcopy(self.query),
            "tool": dict(self.tool),
            "params": copy.deepcopy(self.params),
            "pagination": dict(self.pagination),
            "raw_response_hash": self.raw_response_hash,
            "retrieval_mode": self.retrieval_mode,
            "candidates": copy.deepcopy(self.candidates),
            "audit_records": copy.deepcopy(self.audit_records),
            "ranking": copy.deepcopy(self.ranking) if self.ranking is not None else None,
            "network_decision": copy.deepcopy(self.network_decision) if self.network_decision is not None else None,
            "created_at": self.created_at,
        }


def _run_id(query: Mapping[str, Any], raw_response_hash: str) -> str:
    return make_stable_id("search_run", {"query": query.get("search_query_id", ""), "raw_response_hash": raw_response_hash})


def run_search(
    query: Mapping[str, Any],
    adapter: Any,
    *,
    policy: NetworkAccessPolicy | None = None,
    policy_domain: str = "",
    prior_calls: int = 0,
) -> SearchRun:
    """Run one offline search + audit pass, fail-closed, returning a :class:`SearchRun`.

    Order of gates: (1) query / adapter shape; (2) network policy — a blocked
    domain never reaches the adapter (T-08-12); (3) offline replay; (4) raw status
    mapping (error -> failed, empty -> empty audit); (5) candidate normalisation +
    dedup with filtered/duplicate audit records; (6) ranking.  Every non-candidate
    outcome still records an auditable reason (T-08-10).
    """
    qdict = _as_mapping(query)
    if qdict is None:
        return SearchRun(RUN_STATUS_REJECTED_MALFORMED, CODE_QUERY_MALFORMED, "query must be a mapping/SearchQuery", search_run_id="", query={})
    qdict = dict(qdict)

    if not (hasattr(adapter, "search") and callable(adapter.search) and hasattr(adapter, "tool_name")):
        return SearchRun(
            RUN_STATUS_REJECTED_MALFORMED, CODE_ADAPTER_MALFORMED, "adapter does not satisfy the SearchAdapter protocol", search_run_id="", query=qdict
        )

    tool = {"name": str(getattr(adapter, "tool_name", "")), "version": str(getattr(adapter, "tool_version", "")), "domain": str(getattr(adapter, "domain", ""))}

    # (2) Network policy — inert data-only gate, but fail closed if it says blocked.
    network_decision: dict[str, Any] | None = None
    if policy is not None:
        decision = policy.evaluate(domain=policy_domain or tool["domain"], prior_calls=prior_calls)
        network_decision = decision.to_dict()
        if not decision.allowed:
            audit = [{"disposition": "blocked", "reason": decision.reason_code, "message": decision.message}]
            return SearchRun(
                RUN_STATUS_BLOCKED,
                CODE_DOMAIN_BLOCKED,
                f"network policy blocked the call: {decision.message}",
                search_run_id=make_stable_id("search_run", {"query": qdict.get("search_query_id", ""), "blocked": decision.reason_code}),
                query=qdict,
                tool=tool,
                audit_records=audit,
                network_decision=network_decision,
            )

    # (3) Offline replay.
    raw = adapter.search(dict(qdict))
    if not isinstance(raw, Mapping):
        return SearchRun(
            RUN_STATUS_FAILED,
            CODE_TOOL_FAILED,
            "adapter returned a non-mapping raw response",
            search_run_id=make_stable_id("search_run", {"query": qdict.get("search_query_id", ""), "err": "non_mapping"}),
            query=qdict,
            tool=tool,
            network_decision=network_decision,
        )

    raw_response_hash = hash_payload(dict(raw))
    run_id = _run_id(qdict, raw_response_hash)
    pagination = dict(raw.get("pagination", {}))
    params = dict(raw.get("echoed_params", {}))
    retrieval_mode = str(raw.get("retrieval_mode", REPLAY_RETRIEVAL_MODE))
    raw_status = str(raw.get("status", RAW_STATUS_EMPTY))

    # (4) Raw status mapping.
    if raw_status == RAW_STATUS_ERROR:
        audit = [{"disposition": "failed", "reason": "tool_error", "message": str(raw.get("error", "recorded tool error"))}]
        return SearchRun(
            RUN_STATUS_FAILED,
            CODE_TOOL_FAILED,
            f"search tool reported an error: {raw.get('error', '')}",
            search_run_id=run_id,
            query=qdict,
            tool=tool,
            params=params,
            pagination=pagination,
            raw_response_hash=raw_response_hash,
            retrieval_mode=retrieval_mode,
            audit_records=audit,
            network_decision=network_decision,
        )

    results = raw.get("results", [])
    if not isinstance(results, list):
        results = []

    # (5) Normalise + dedup; record filtered records explicitly.
    normalized: list[dict[str, Any]] = []
    audit_records: list[dict[str, Any]] = []
    q_for_norm = dict(qdict)
    q_for_norm["tool_name"] = tool["name"]
    for idx, rec in enumerate(results):
        cand = normalize_candidate(rec, q_for_norm) if isinstance(rec, Mapping) else None
        if cand is None:
            audit_records.append(
                {"disposition": DISPOSITION_FILTERED, "index": idx, "reason": "record has no namespace/identifier and cannot be normalised or verified"}
            )
            continue
        # Defensive: a normalised candidate must pass the resource-candidate validator.
        if validate_resource_candidate(cand):
            audit_records.append({"disposition": DISPOSITION_FILTERED, "index": idx, "reason": "normalised candidate failed resource-candidate validation"})
            continue
        normalized.append(cand)

    unique, duplicates = dedupe_candidates(normalized)
    audit_records.extend(duplicates)
    for cand in unique:
        audit_records.append(
            {"disposition": DISPOSITION_NORMALIZED, "resource_candidate_id": cand.get("resource_candidate_id", ""), "dedup_key": cand.get("dedup_key", "")}
        )

    if not unique:
        return SearchRun(
            RUN_STATUS_EMPTY,
            CODE_EMPTY_RESULT,
            "search returned no usable candidate (empty or all-filtered); recorded so the report can explain why",
            search_run_id=run_id,
            query=qdict,
            tool=tool,
            params=params,
            pagination=pagination,
            raw_response_hash=raw_response_hash,
            retrieval_mode=retrieval_mode,
            audit_records=audit_records,
            network_decision=network_decision,
        )

    ranking = propose_ranking(unique, qdict).to_dict()
    return SearchRun(
        RUN_STATUS_CANDIDATES_FOUND,
        CODE_CANDIDATES_FOUND,
        f"{len(unique)} candidate(s) discovered and audited",
        search_run_id=run_id,
        query=qdict,
        tool=tool,
        params=params,
        pagination=pagination,
        raw_response_hash=raw_response_hash,
        retrieval_mode=retrieval_mode,
        candidates=unique,
        audit_records=audit_records,
        ranking=ranking,
        network_decision=network_decision,
    )
