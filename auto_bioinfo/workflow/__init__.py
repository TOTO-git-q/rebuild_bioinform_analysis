"""Lane-2 workflow package (WP-12..WP-15).

Offline, deterministic, inert modules for the method/workflow/execution spine:

- :mod:`auto_bioinfo.workflow.dag_compiler` — compile a method plan into an
  explicit, acyclic WorkflowPlan + Artifact DAG (WP-12).
- :mod:`auto_bioinfo.workflow.artifact_registry` — artifact registration,
  integrity and lineage (WP-15).

Every module is a pure function of its in-memory inputs: no real workflow engine,
no subprocess, no container, no network, no clock read, no filesystem side effect
outside recorded fixtures.  Produced drafts carry an empty ``created_at`` so
byte-identical inputs yield byte-identical outputs.
"""
