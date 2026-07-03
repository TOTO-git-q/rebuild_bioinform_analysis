"""Offline end-to-end research routes (WP-16 / WP-17 / WP-26 — the capstone).

This package *wires* the independently-built lane packages
(:mod:`auto_bioinfo.intake`, :mod:`auto_bioinfo.planning`,
:mod:`auto_bioinfo.resources`, :mod:`auto_bioinfo.methods`,
:mod:`auto_bioinfo.workflow`, :mod:`auto_bioinfo.execution`,
:mod:`auto_bioinfo.quality`, :mod:`auto_bioinfo.evidence`,
:mod:`auto_bioinfo.reporting`, :mod:`auto_bioinfo.reproduction`) into a single,
deterministic, offline research *route* that carries a natural-language question
all the way to a constrained report and a reproduction bundle.

Nothing here rebuilds a lane; it only *chains* them and, where two independently
built lane surfaces do not line up, provides a thin deterministic offline
adapter (see :mod:`auto_bioinfo.routes.glue`).  Every route is:

* PURE / OFFLINE — no real network, data, compute, subprocess, container, clock,
  or paid service.  The "real" routes run over recorded, committed synthetic
  fixtures (``auto_bioinfo/fixtures/bulk_rnaseq_route`` and
  ``.../scrna_donor_route``).
* DETERMINISTIC — byte-identical inputs yield byte-identical outputs; produced
  records carry an empty ``created_at``.
* GATED — every hard gate (verification, feasibility, authorization, four-layer
  QC, evidence admission, claim ceiling, alignment audit) is respected.  A
  failing hard gate stops the route with a recorded terminal status and reason;
  the claim ceiling is never exceeded.
"""

from .route_run import (
    TERMINAL_ALIGNMENT_REVIEW,
    TERMINAL_COMPLETED,
    TERMINAL_CONFLICTING_EVIDENCE,
    TERMINAL_EGRESS_BLOCKED,
    TERMINAL_EVIDENCE_REFUSED,
    TERMINAL_INSUFFICIENT_DATA,
    TERMINAL_METHOD_NOT_APPLICABLE,
    TERMINAL_NEEDS_CLARIFICATION,
    TERMINAL_QC_REJECTED,
    TERMINAL_STATUSES,
    TERMINAL_UNVERIFIABLE_RESOURCE,
    RouteRun,
    StageResult,
)

__all__ = [
    "RouteRun",
    "StageResult",
    "TERMINAL_STATUSES",
    "TERMINAL_COMPLETED",
    "TERMINAL_NEEDS_CLARIFICATION",
    "TERMINAL_UNVERIFIABLE_RESOURCE",
    "TERMINAL_INSUFFICIENT_DATA",
    "TERMINAL_METHOD_NOT_APPLICABLE",
    "TERMINAL_EGRESS_BLOCKED",
    "TERMINAL_QC_REJECTED",
    "TERMINAL_EVIDENCE_REFUSED",
    "TERMINAL_CONFLICTING_EVIDENCE",
    "TERMINAL_ALIGNMENT_REVIEW",
]
