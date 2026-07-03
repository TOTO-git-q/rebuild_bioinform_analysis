"""Local/offline resource-discovery stage contracts (WP-08, phase 5).

This package holds the *local, deterministic, offline* command contracts for the
resource-discovery lane: real resource *discovery & search audit* (WP-08) —
turning a frozen :class:`~auto_bioinfo.core.schemas.EvidencePlan` into audited
:class:`~auto_bioinfo.core.schemas.ResourceCandidate` records — **before** any
real search, data acquisition, approval grant, event emission, persistence, or
pipeline transition.  Later resource-closure phases (verification, feasibility)
are intentionally *not* imported or exported here yet.

Every module mirrors the :mod:`auto_bioinfo.intake` / :mod:`auto_bioinfo.planning`
contract style: pure and total over explicit in-memory inputs, no I/O of any kind,
no wall-clock read (produced drafts carry an empty ``created_at`` so byte-identical
inputs yield byte-identical output), bounded status/reason-code vocabularies, and
results that are inert reviewable data — never authoritative, never persisted,
never a grant to execute.  The only "tool" access is through the offline replay
adapters in :mod:`auto_bioinfo.adapters.offline_search`; no real network / API /
GEO / PubMed call is ever made.
"""

from .discovery import (
    RankingProposal,
    SearchQuery,
    SearchQueryResult,
    SearchRun,
    SearchStopDecision,
    build_search_query,
    decide_stop,
    dedupe_candidates,
    normalize_candidate,
    propose_ranking,
    run_search,
)
from .search_policy import NetworkAccessDecision, NetworkAccessPolicy

__all__ = [
    "NetworkAccessDecision",
    "NetworkAccessPolicy",
    "RankingProposal",
    "SearchQuery",
    "SearchQueryResult",
    "SearchRun",
    "SearchStopDecision",
    "build_search_query",
    "decide_stop",
    "dedupe_candidates",
    "normalize_candidate",
    "propose_ranking",
    "run_search",
]
