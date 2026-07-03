"""Lane-4 failure-recovery and release/ops layer (WP-25, WP-27).

Pure, offline, deterministic domain logic that turns failure handling and release
readiness into predictable, bounded decisions rather than ad-hoc retries or prose:

- :mod:`auto_bioinfo.ops.failure_taxonomy` — a bounded catalogue of exactly twelve
  failure classes, the error-code → class mapping, and the retryability matrix
  (scientific / design failures are non-retryable) (WP-25 / T-25-01, T-25-02);
- :mod:`auto_bioinfo.ops.retry_policy` — deterministic exponential backoff with
  bounded jitter, a maximum attempt count, a total time budget, and per-scope
  retry budgets, so a retryable failure can never loop forever (T-25-03, T-25-04);
- :mod:`auto_bioinfo.ops.rerun_planner` — partial-failure isolation and
  affected-subgraph invalidation so only the correct descendants of a changed /
  failed node are re-run and unrelated paths are never cancelled (T-25-05, T-25-06);
- :mod:`auto_bioinfo.ops.replan` — the REPLAN / RECONFIRM_REQUIRED / human-override
  / terminal-decision engine, so a failure that cannot be retried is routed to a
  re-plan, a human re-confirmation, a bounded override, or a legitimate terminal
  state with a mandatory reason (T-25-07..T-25-10);
- :mod:`auto_bioinfo.ops.release_readiness` — an offline release-readiness
  checklist object with hard-stop gates and the explicit MVP evolution boundary
  (what is in and out of scope) (WP-27 / T-27-01, T-27-09, T-27-10, T-27-12).

Every module is a total function of its explicit in-memory inputs: no clock, no
network, no persistence, no subprocess.  Decisions are bounded, reason-coded
*values*; nothing is retried, re-planned, deleted, or released for real here.
"""
