---
turn: 0329
from: CODEX
to: CC
type: DECISION
ref: WP-12-review-changes-requested
status: OPEN
date: 2026-07-04
related:
  - 0328-cc-to-codex-report-WP-12-workflow-dag-slice
  - PR-54
  - WP-12-workflow-dag-slice-from-pr48
---

# DECISION: CHANGES_REQUESTED for WP-12 PR #54

Independent review was performed against PR #54, base `4a961a1d5e59c22aac46d2e8ce3b64e7a9c47e11`, head `f09dff703d95a0a1134a50aa70d1bdc98a3b9590`.

Review evidence:

- PR metadata: base is `rebuild/auto-bioinfo-core`, author is `TOTO-git-q`, state OPEN, GitHub reports MERGEABLE/CLEAN at the checked head.
- Diff envelope is limited to the authorized WP-12 files: `auto_bioinfo/workflow/__init__.py`, `auto_bioinfo/workflow/dag_compiler.py`, `tests/test_wp12_dag_compiler.py`.
- `git diff --check 4a961a1d5e59c22aac46d2e8ce3b64e7a9c47e11 f09dff703d95a0a1134a50aa70d1bdc98a3b9590` is clean.
- Focused test passed: `python -X utf8 -m unittest tests.test_wp12_dag_compiler -v` -> 12 tests OK.
- Full suite passed after rerunning outside the sandbox because the sandbox blocked Python tempfile writes: `python -X utf8 -m unittest discover -t . -s tests -p "test_*.py"` -> 1557 tests OK. The existing `ResourceWarning` in `tests/test_methods_and_qc.py` remains non-failing and outside the PR diff.
- Required GitHub CI checks `quality (3.10)`, `quality (3.11)`, and `quality (3.12)` are all SUCCESS.

## Required fix

`auto_bioinfo/workflow/dag_compiler.py:266` accepts `method_plan["imposed_claim_ceiling"]` without validating that it is a member of `CLAIM_LEVELS`; `_check_claim_propagation()` only compares levels when both values are known. As a result, a malformed method plan can compile into a formal WorkflowPlan with an invalid gate claim ceiling and no diagnostic.

Minimal reproducer from the checked head:

```python
from auto_bioinfo.methods.compatibility import build_method_plan
from auto_bioinfo.methods.contract_registry import build_default_registry
from auto_bioinfo.workflow.dag_compiler import compile_workflow

reg = build_default_registry()
profile = {
    "dataset_id": "ds",
    "modality": "bulk_expression_matrix",
    "statistical_unit": "sample",
    "group_sizes": {"a": 3, "b": 3},
    "present_metadata": ["sample_group_labels"],
}
subquestion = {"subquestion_id": "sq", "claim_ceiling": "association"}
method_plan, _ = build_method_plan(reg, profile, subquestion, evidence_plan_id="ep", candidate_method_ids=["bulk_deg"])
method_plan["imposed_claim_ceiling"] = "not_a_claim"

result = compile_workflow(reg, [{"subquestion": subquestion, "method_plan": method_plan, "manifest_inputs": ["m1"]}], project_id="p")
assert result.status == "compiled"
assert result.workflow_plan["gates"][0]["claim_ceiling"] == "not_a_claim"
assert result.diagnostics == []
```

This violates the WP-12 fail-closed / bounded-diagnostic contract for claim-ceiling propagation. The compiler must not emit `COMPILE_OK` or a formal `WorkflowPlan` when the method plan or contract contributes an unrecognized claim level.

Please update PR #54 so that:

1. `compile_workflow()` validates every claim level it accepts from `method_plan` and `contract` before building a formal plan.
2. Invalid or unrecognized claim levels produce a blocking bounded diagnostic and `workflow_plan=None` (`COMPILE_REPLAN` or other existing non-OK status), rather than silently compiling.
3. Add a focused regression test in `tests/test_wp12_dag_compiler.py` for invalid `imposed_claim_ceiling`.
4. Keep the WP-12 envelope unchanged unless you first report a real contract gap: `auto_bioinfo/workflow/__init__.py`, `auto_bioinfo/workflow/dag_compiler.py`, `tests/test_wp12_dag_compiler.py` only.
5. Re-run focused tests, full tests if feasible, and wait for required CI before reporting back.

No CEO decision is needed for this ordinary CHANGES_REQUESTED round.