"""Local/offline resource-closure stage contracts (WP-08 / WP-09 / WP-10, phases 5-7).

This package holds the *local, deterministic, offline* command contracts for the
resource-closure lane: real resource *discovery & search audit* (WP-08),
resource *verification & metadata factualisation* (WP-09), and *data feasibility
assessment & DatasetManifest lock* (WP-10) — turning a frozen
:class:`~auto_bioinfo.core.schemas.EvidencePlan` into audited candidates, verified
profiles, feasibility reports and, finally, a locked
:class:`~auto_bioinfo.core.schemas.DatasetManifest` — **before** any real search,
data acquisition, approval grant, event emission, persistence, or pipeline
transition.

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
