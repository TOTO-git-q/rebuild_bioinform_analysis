<!--
PR / change template for rebuild_bioinform_analysis.
Fill every section. Keep it short and factual. Delete a section only if it is
genuinely not applicable, and say why.
Coordination is on the `coordination` branch (append-only turn log); code review
happens on the PR. See docs/coordination/PROTOCOL.md and CONSTITUTION.md.
-->

## Work package / turn reference

- Work Order / WP id:
- Authorizing turn (e.g. `log/NNNN-codex-to-cc-workorder-...md`):
- Implementation branch (`rebuild/wo-<id>-<slug>`):
- Base branch: `rebuild/auto-bioinfo-core`

## Scope summary

<!-- One paragraph: what this PR does, strictly within the authorizing WO. -->

## Changed files / risk tier

<!-- List changed paths with a one-line rationale each.
Risk tier (per the frozen architecture plan), if applicable: -->

| Path | Why it changed |
|------|----------------|
|      |                |

## Validation commands and results

<!-- Paste the exact commands and the real result lines. Self-reported green is
only self-reported; do not claim CEO acceptance or OPS-00 PASS. -->

- Test suite:
  `source ~/miniforge3/etc/profile.d/conda.sh && conda activate bioinform && python3 -m unittest discover -t . -s tests -p "test_*.py"`
  → result:
- `git diff --check` → result:
- Other (lint / format-check / typecheck), if run:

## Required CI status

<!-- Status of the required GitHub Actions checks for the current head SHA.
If template/docs-only and CI is skipped or not triggered, state the exact
GitHub behavior instead of leaving this blank. -->

- Head SHA:
- Required checks (`quality (3.10/3.11/3.12)`):

## Hard-stop confirmation

Confirm each (the constitution's HARD STOPS require explicit CEO authorization
and are never auto-crossed):

- [ ] No first use of real human-source data.
- [ ] No data sent to an external LLM / service.
- [ ] No paid service enabled.
- [ ] No public deploy / publish.
- [ ] No destructive / irreversible operation.
- [ ] No expansion of bot credential permissions.
- [ ] R0-02 was not started; no out-of-scope WP was started.
- [ ] Nothing was self-merged by CC.

## Merge / auto-merge

Protected-base flow (turn 0063): **PR + required CI + Codex independent review +
GitHub auto-merge**. Direct base push, hard merge, force push, ruleset/secret/token
changes, and bypassing required CI are **forbidden**.

- [ ] Auto-merge is **not** enabled by CC. It is enabled (`gh pr merge <PR> --auto --merge`)
      only by Codex, and only after Codex's independent review approves.
