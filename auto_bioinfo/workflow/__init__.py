"""Lane-2 workflow package (WP-12 slice).

Offline, deterministic, inert modelling for the workflow spine:

- :mod:`auto_bioinfo.workflow.dag_compiler` — compile a method plan into an
  explicit, acyclic WorkflowPlan + Artifact DAG (WP-12).

The module is a pure function of its in-memory inputs: no real workflow engine,
no subprocess, no container, no network, no clock read, no filesystem side
effect.  Produced drafts carry an empty ``created_at`` so byte-identical inputs
yield byte-identical outputs.
"""

from . import dag_compiler

__all__ = ["dag_compiler"]
