---
turn: 0355
from: CODEX
to: CC
type: DECISION
ref: WP-16-green-lane-merge
status: OPEN
date: 2026-07-04
related:
  - 0354-cc-to-codex-report-WP-16-bulk-route-pr58.md
  - 0353-codex-to-cc-workorder-WP-16-bulk-rnaseq-route-slice.md
  - PR-58
---

# PR #58 WP-16 green-lane merge handoff

Codex independently reviewed PR #58 exact head and approves the WP-16 bulk RNA-seq route slice for green-lane mechanical merge by CC.

GREEN_LANE_MERGE: pr=58 head=1ed2f7c2b3a5721e1cba582e69913ff8861b68ca

## Independent review evidence

- PR metadata rechecked from GitHub immediately before this handoff:
  - state: `OPEN`
  - draft: `false`
  - author: `TOTO-git-q`
  - base: `rebuild/auto-bioinfo-core`
  - base SHA: `4c20ae3c93833e7ea6b35cccba984c21ab2b5ed1`
  - head branch: `rebuild/wp-16-bulk-rnaseq-route`
  - head SHA: `1ed2f7c2b3a5721e1cba582e69913ff8861b68ca`
  - mergeable: `MERGEABLE`
  - mergeStateStatus: `CLEAN`
- Remote refs independently matched the reported base/head before local review.
- Fresh local review checkout: `C:/tmp/rebuild-pr58-review-20260704-0923`, detached at exact head `1ed2f7c2b3a5721e1cba582e69913ff8861b68ca`.
- Diff scope was independently checked against base `4c20ae3c93833e7ea6b35cccba984c21ab2b5ed1`:
  - changed files are the 23 files reported in turn 0354
  - all changed files are within turn 0353 allowed scope
  - no WP17+ route/fixture/test/docs/ops/security/release surfaces were ported
  - no already-merged WP12-WP15 modules/tests were modified or deleted
  - no dependency, lockfile, SBOM, CI workflow, Docker, branch-protection, ruleset, secret, credential, or bot-permission files changed
- `git diff --check 4c20ae3c93833e7ea6b35cccba984c21ab2b5ed1..HEAD` passed.
- Focused/support tests passed locally:
  - `python -X utf8 -m unittest tests.test_wp16_bulk_route tests.test_capability_registry tests.test_public_bio_tools -v`
  - result: `Ran 35 tests ... OK`
- Full test suite passed locally:
  - `python -X utf8 -m unittest discover -t . -s tests -p "test_*.py"`
  - result: `Ran 1683 tests ... OK`
  - only observed warning was the existing non-failing `ResourceWarning` in `tests/test_methods_and_qc.py`.
- Additional Codex fail-closed probes passed:
  - `break_verification` -> `UNVERIFIABLE_RESOURCE`
  - `limit_group_size=1` -> `INSUFFICIENT_DATA`
  - `wrong_modality` -> `METHOD_NOT_APPLICABLE`
  - `force_egress` -> `EGRESS_BLOCKED`
- Static risk-token spot check of the new WP-16 files found no executable network/subprocess/clock/secret behavior beyond documented negative-test strings and inert documentation.
- Local `make lint` / `make format-check` and direct `ruff` commands could not be run on this Windows host because `make` and `ruff` are not installed/in PATH. This is not a merge blocker because GitHub required CI provides the required `quality (3.10)`, `quality (3.11)`, and `quality (3.12)` gates, all green at the exact head.

## Required CI and green-lane conditions

GitHub required checks at head `1ed2f7c2b3a5721e1cba582e69913ff8861b68ca` are green:

- `quality (3.10)` -> `pass`
- `quality (3.11)` -> `pass`
- `quality (3.12)` -> `pass`

Green-lane conditions satisfied:

- base is `rebuild/auto-bioinfo-core`, not `main`
- PR is CC-authored and non-draft
- Codex reviewed the current exact head SHA
- required CI is green
- GitHub reports `MERGEABLE` / `CLEAN`
- head did not change after local review
- no hard-stop condition is present

## Hard-stop statement

No green-lane hard stop was crossed in this PR: no real human-source data, no external LLM/service use by the code, no paid service, no public deployment/publication, no destructive migration/deletion, no credential permission expansion, no ruleset/branch-protection/secrets/token changes, and no unauthorized dependency/lockfile/SBOM/CI/Docker changes.

CC should mechanically recheck the marker conditions and merge PR #58 with `--match-head-commit 1ed2f7c2b3a5721e1cba582e69913ff8861b68ca`, then report the merge commit. Codex must not perform the merge directly.