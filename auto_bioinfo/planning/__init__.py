"""Local/offline research-planning stage contracts (WP-07 / phases 3-4).

This package holds the *local, deterministic, offline* command contracts that
turn a frozen draft :class:`~auto_bioinfo.core.schemas.ResearchSpec` (and its
resolved scope) into inert, reviewable planning projections — sub-question
decomposition, a sub-question dependency graph with coverage, and per
sub-question evidence plans — **before** any real search, data acquisition,
approval grant, event emission, persistence, or pipeline transition.

Every module here mirrors the :mod:`auto_bioinfo.intake` contract style: pure
and total over explicit in-memory inputs, no I/O of any kind, no wall-clock read
(produced drafts carry an empty ``created_at`` so byte-identical inputs yield
byte-identical output), bounded status/reason-code vocabularies, and results
that are inert reviewable data — never authoritative, never persisted, never a
grant to execute.
"""
