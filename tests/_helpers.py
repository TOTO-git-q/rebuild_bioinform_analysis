"""Shared test helpers (offline, deterministic).

Fixture lifecycle rules live in ``tests/README.md`` (WP-01c / T-01-09).  The
short version enforced here: every fixture is **synthetic**, written under the
**system temp dir** (never the repo, never a database or object store), and the
temp workspace is **cleaned up automatically** so the suite leaves no residue.
"""

from __future__ import annotations

import atexit
import contextlib
import json
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

from auto_bioinfo.adapters.fixture_resources import FixtureResourceAdapter

DEMO_QUESTION = "Which genes are differentially expressed in tissue_x between condition_a and condition_b?"

# Temp roots created by fixture helpers, removed at interpreter exit so the suite
# never leaks directories (the old ``mkdtemp`` calls were never cleaned up).
_TEMP_ROOTS: list[Path] = []


def _new_temp_root(prefix: str = "auto_bioinfo_fx_") -> Path:
    """Create a fresh temp dir under the system temp and schedule its cleanup."""
    root = Path(tempfile.mkdtemp(prefix=prefix))
    _TEMP_ROOTS.append(root)
    return root


@atexit.register
def _cleanup_temp_roots() -> None:
    while _TEMP_ROOTS:
        shutil.rmtree(_TEMP_ROOTS.pop(), ignore_errors=True)


@contextlib.contextmanager
def temp_workspace(prefix: str = "auto_bioinfo_ws_") -> Iterator[Path]:
    """Yield an isolated temp workspace and remove it on exit.

    Reusable lifecycle helper for tests that need a scratch directory with
    deterministic, eager cleanup (instead of relying on the atexit sweep).
    """
    root = Path(tempfile.mkdtemp(prefix=prefix))
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def tiny_fixture(group_a_n: int = 3, group_b_n: int = 3) -> Path:
    """Write a tiny committed-style fixture with a chosen number of replicates."""
    base = _new_temp_root() / "fx"
    base.mkdir(parents=True)
    samples = ["sample\tgroup"]
    cols = []
    for i in range(group_a_n):
        cols.append(f"a{i}")
        samples.append(f"a{i}\tcondition_a")
    for i in range(group_b_n):
        cols.append(f"b{i}")
        samples.append(f"b{i}\tcondition_b")
    header = "gene\t" + "\t".join(cols)
    # Small within-group variation so the t-test is well-defined (non-degenerate).
    up_vals = [str(1000 + 30 * i) for i in range(group_a_n)] + [str(50 + 5 * i) for i in range(group_b_n)]
    flat_vals = [str(500 + 5 * i) for i in range(group_a_n)] + [str(500 + 4 * i) for i in range(group_b_n)]
    up = "GENE_UP\t" + "\t".join(up_vals)
    flat = "GENE_FLAT\t" + "\t".join(flat_vals)
    (base / "counts.tsv").write_text(header + "\n" + up + "\n" + flat + "\n", encoding="utf-8")
    (base / "samples.tsv").write_text("\n".join(samples) + "\n", encoding="utf-8")
    card = {
        "dataset_id": "FIXTURE_TINY",
        "accession": "FIXTURE-TINY",
        "source_status": "committed_fixture",
        "source_class": "SYNTHETIC_FIXTURE",
        "retrieval_mode": "LOCAL_CACHE",
        "verification_level": "FILES_CHECKSUM_VERIFIED",
        "modality": "bulk_expression_matrix",
        "organism": "synthetic_fixture_organism",
        "tissue": "tissue_x",
        "platform": "synthetic",
        "files": {"counts": "counts.tsv", "samples": "samples.tsv"},
        "group_sizes": {"condition_a": group_a_n, "condition_b": group_b_n},
        "comparison_groups": ["condition_a", "condition_b"],
        "known_limitations": ["synthetic fixture"],
    }
    (base / "dataset_card.json").write_text(json.dumps(card), encoding="utf-8")
    return base


def fixture_adapter(group_a_n: int = 3, group_b_n: int = 3) -> FixtureResourceAdapter:
    return FixtureResourceAdapter(fixture_dir=tiny_fixture(group_a_n, group_b_n))


def real_like_fixture(group_a_n: int = 3, group_b_n: int = 3) -> Path:
    """Like :func:`tiny_fixture`, but the dataset card is labelled as genuinely
    real ``PUBLIC_DATABASE`` data obtained from a ``LOCAL_CACHE`` and verified to
    ``FILES_CHECKSUM_VERIFIED``.  A REAL run over this card flows all the way to an
    ELIGIBLE ``ScientificEligibilityDecision`` and a successful formal export, so
    the review-fix downstream tests have a genuine eligible baseline to tamper.

    This is a *test double*: its bytes are the same deterministic offline fixture;
    relabelling its structured provenance lets the eligibility gate treat it as
    real, which is exactly the baseline the adversarial tamper tests then attack.
    """
    base = tiny_fixture(group_a_n, group_b_n)
    card = json.loads((base / "dataset_card.json").read_text(encoding="utf-8"))
    card.update(
        {
            "dataset_id": "GSE_REAL_TEST",
            "accession": "GSE123456",
            "source_status": "public_database",
            "source_class": "PUBLIC_DATABASE",
            "retrieval_mode": "LOCAL_CACHE",
            "verification_level": "FILES_CHECKSUM_VERIFIED",
            "known_limitations": [],
        }
    )
    (base / "dataset_card.json").write_text(json.dumps(card), encoding="utf-8")
    return base


def real_like_fixture_adapter(group_a_n: int = 3, group_b_n: int = 3) -> FixtureResourceAdapter:
    return FixtureResourceAdapter(fixture_dir=real_like_fixture(group_a_n, group_b_n))
