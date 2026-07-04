"""Constrained report generation and traceability (WP-21).

This package turns already-audited objects (spec / manifest / QC / evidence / claims
/ alignment) into a human- and machine-readable report *without ever creating new
evidence or raising a conclusion's level*.  Every claim in the report traces back
through evidence → artifact → dataset (:mod:`.trace_index`), the report language is
lint-checked for over-claim leaps (:mod:`.claim_lint`), and the report itself is
assembled by the constrained builder (:mod:`.report_builder`).  Everything is pure,
offline and deterministic.
"""

from .claim_lint import CLAIM_LINT_KINDS, lint_report_language
from .report_builder import (
    REPORT_STATUSES,
    REQUIRED_RESULT_SECTIONS,
    ReportBuildResult,
    advance_report_status,
    build_report,
    build_report_input_bundle,
)
from .trace_index import (
    build_coverage_matrix,
    build_figure_list,
    build_method_trace_table,
    build_trace_index,
)

__all__ = [
    "CLAIM_LINT_KINDS",
    "lint_report_language",
    "REPORT_STATUSES",
    "REQUIRED_RESULT_SECTIONS",
    "ReportBuildResult",
    "advance_report_status",
    "build_report",
    "build_report_input_bundle",
    "build_trace_index",
    "build_figure_list",
    "build_coverage_matrix",
    "build_method_trace_table",
]
