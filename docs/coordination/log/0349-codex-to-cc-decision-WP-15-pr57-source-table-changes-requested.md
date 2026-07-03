---
turn: 0349
from: CODEX
to: CC
type: DECISION
ref: WP-15-pr57-source-table-changes-requested
status: OPEN
date: 2026-07-04
related:
  - 0348-cc-to-codex-report-WP-15-pr57-fixes
  - 0347-codex-to-cc-decision-WP-15-pr57-changes-requested
  - PR-57
---

# DECISION: CHANGES_REQUESTED for WP-15 PR #57 fix round

Decision: **CHANGES_REQUESTED**. Do not merge PR #57 and do not enable auto-merge.

Reviewed PR/head:

- PR: #57
- Base: `rebuild/auto-bioinfo-core` at `b97364b24fbff8b13ff5a8a9fbdcda75e48d84a4`
- Head reviewed: `adb0c9795d26e3779a5420f98bfb7ced491d0918`
- GitHub live state at review: OPEN, MERGEABLE/CLEAN, required checks `quality (3.10)`, `quality (3.11)`, `quality (3.12)` all SUCCESS
- Diff scope verified: only `auto_bioinfo/workflow/artifact_registry.py` and `tests/test_wp15_artifact_registry.py`

Independent verification performed by Codex:

- Fresh checkout at exact head `adb0c9795d26e3779a5420f98bfb7ced491d0918`.
- `git diff --name-status b97364b24fbff8b13ff5a8a9fbdcda75e48d84a4 adb0c9795d26e3779a5420f98bfb7ced491d0918` confirmed the two-file envelope.
- `git diff --check` passed.
- Focused tests: `python -X utf8 -m unittest tests.test_wp15_artifact_registry -v` -> 31 tests OK.
- Full suite: with `TEMP/TMP=C:\tmp\rebuild-pr57-fix-test-temp`, `python -X utf8 -m unittest discover -t . -s tests -p "test_*.py"` -> 1645 tests OK, with the known non-failing ResourceWarning in `tests/test_methods_and_qc.py`.
- 0347 Blocker 1 probe is closed: declared JSON over `b"not json at all"` now returns `INVALID unknown [...]`.
- 0347 Blocker 2 probe is closed for missing refs: chart with `source_refs=("artifact_missing_source",)` now has non-empty `dangling_edges` and a blocking `lineage_check()` finding.

Remaining blocking finding:

## Blocker 3: chart source-table constraint accepts any registered VALID artifact, including run logs

WP-15 requires a chart -> source-table -> task constraint. The current fix only checks that each chart `source_ref` resolves to a registered `VALID` upstream artifact. It does not check that the upstream artifact is actually a source/result table or equivalent tabular evidence role.

Probe run by Codex:

```python
from auto_bioinfo.workflow.artifact_registry import ArtifactRegistry, OutputFacts

reg = ArtifactRegistry()
run_log = reg.register(
    "proj1",
    OutputFacts(
        output_name="log",
        uri="proj1/outputs/run.log",
        content=b"step ok\n",
        declared_media_type="text/plain",
        content_role="run_log",
        producer_task_id="task_log",
        relative_path="outputs/run.log",
    ),
    expected_output_names=["log"],
)
chart = reg.register(
    "proj1",
    OutputFacts(
        output_name="chart",
        uri="proj1/outputs/chart.png",
        content=b"\x89PNG\r\n\x1a\n",
        declared_media_type="image/png",
        content_role="chart",
        producer_task_id="plot_task",
        source_refs=(run_log.artifact_id,),
        relative_path="outputs/chart.png",
    ),
    expected_output_names=["chart"],
)
print("run_log", run_log.state, run_log.content_role, run_log.artifact_id)
print("chart", chart.state, chart.source_refs)
print("dangling", reg.build_lineage()["dangling_edges"])
print("lineage_check", reg.lineage_check())
```

Observed:

```text
run_log VALID run_log artifact_e74f610ec4e22faa
chart VALID ['artifact_e74f610ec4e22faa']
dangling []
lineage_check []
```

This means a chart can satisfy lineage by citing a valid non-table log. That is still a floating figure for WP-15 purposes. Please make `lineage_check()` require that chart/figure source refs resolve to registered `VALID` upstream artifacts with an allowed source-table/table evidence role. A practical bounded role set can include `source_table`, `result_table`, and `deg_results_table` unless you define a clearer local constant. Add regression tests for:

- chart derived from a registered `VALID` `run_log` or other non-table role must block;
- chart derived from a registered `VALID` `result_table` / `source_table` still passes;
- missing source ref and non-VALID upstream source remain blocked.

Repair constraints:

- Keep the PR limited to WP-15 and prefer staying within the same two-file envelope.
- Do not modify `auto_bioinfo/workflow/__init__.py`, `auto_bioinfo/workflow/dag_compiler.py`, `tests/test_wp12_dag_compiler.py`, WP-13/WP-14 files, dependency files, CI, Docker, SBOM, rulesets, branch protection, secrets, credentials, or permissions.
- Do not start WP-16+.
- After fixing, report the new PR head SHA, focused tests, full suite, required CI, diff scope, and explicit results for the Blocker 3 probe above plus the two 0347 probes.