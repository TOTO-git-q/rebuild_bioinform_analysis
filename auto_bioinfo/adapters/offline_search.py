"""Offline search adapter protocols + deterministic fake implementations (WP-08 / T-08-01..04, T-08-11).

The *local, offline, deterministic* seam through which the resource-discovery
stage (WP-08) reaches a dataset / literature / annotation search tool — realised
here **only** as in-process fakes backed by recorded fixtures, never a real
network call.  Where the production system would (later) reach GEO / Europe PMC /
an annotation catalogue over an audited HTTP tool broker, this module defines the
three adapter *protocols* (:class:`DatasetSearchAdapter`,
:class:`LiteratureSearchAdapter`, :class:`AnnotationSearchAdapter`) and a single
:class:`OfflineRecordedSearchAdapter` fake that *replays* a recorded raw response
for an exactly-matching query and otherwise returns a recorded-empty response.

The plan mandates this shape directly: T-08-01 "fake adapter 契约测试", T-08-11
"录制 fixture 和离线回放模式 / CI 不调用真实 API".  Accordingly:

- **Pure, deterministic, offline.**  An adapter's :meth:`search` is a total
  function of its explicit in-memory recordings plus the query handed to it: no
  network/socket, no HTTP client, no environment/credential read, no real clock
  read, no randomness, no subprocess, no file/DB/queue side effect.  The same
  query always replays the same recorded raw response (byte-identically), and an
  unrecorded query always returns the same recorded-empty response.  Inputs are
  never mutated.
- **Honest, non-authoritative fixtures.**  A recording is a clearly-synthetic,
  committed raw response, honestly labelled by its ``retrieval_mode`` /
  ``source_class`` markers.  A fixture is *replayed*, never fetched; the adapter
  therefore reports ``retrieval_mode == "RECORDED_REPLAY"`` and never claims a
  ``LIVE`` retrieval or invents a real accession / PMID / DOI as a fact.
- **Raw response only.**  An adapter returns the *raw* recorded response (its tool
  identity, the echoed params, the pagination facts, and the raw result records).
  It performs **no** normalisation, dedup, ranking, verification, or persistence —
  those are the auditor's job (:mod:`auto_bioinfo.resources.discovery`).  It emits
  no event and writes no state.

This module defines adapters + fixtures only.  It does not build a
:class:`~auto_bioinfo.resources.discovery.SearchQuery`, run policy enforcement,
verify a candidate, or lock anything — those remain the caller's / later stages'
job.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from ..core.ids import hash_payload

# --- Bounded search-domain vocabulary ----------------------------------------
# The kind of resource a search adapter looks for.  A candidate normaliser keys
# its namespace off this, and the network policy allowlists by domain.
SEARCH_DOMAIN_DATASET = "dataset"
SEARCH_DOMAIN_LITERATURE = "literature"
SEARCH_DOMAIN_ANNOTATION = "annotation"
SEARCH_DOMAINS = (SEARCH_DOMAIN_DATASET, SEARCH_DOMAIN_LITERATURE, SEARCH_DOMAIN_ANNOTATION)

# --- Bounded raw-response status vocabulary ----------------------------------
# The status a recorded raw response carries.  ``ok`` is a non-empty recorded
# result; ``empty`` is an honestly-recorded no-hit response; ``error`` is a
# recorded tool/transport failure (mapped, never raised).
RAW_STATUS_OK = "ok"
RAW_STATUS_EMPTY = "empty"
RAW_STATUS_ERROR = "error"
RAW_STATUSES = (RAW_STATUS_OK, RAW_STATUS_EMPTY, RAW_STATUS_ERROR)

# A replayed fixture is, by construction, obtained by replay — never a live fetch.
REPLAY_RETRIEVAL_MODE = "RECORDED_REPLAY"


@runtime_checkable
class SearchAdapter(Protocol):
    """The common shape every offline search adapter matches.

    An adapter names a stable tool identity (``tool_name`` / ``tool_version``) and
    the :data:`SEARCH_DOMAINS` it serves, and exposes a single pure
    :meth:`search` that maps an inert query dict to an inert raw-response dict.
    Structural typing (a ``Protocol``) keeps the dependency arrow pointing inward:
    the auditor depends on this shape, not on any concrete adapter.
    """

    tool_name: str
    tool_version: str
    domain: str

    def search(self, query: dict[str, Any]) -> dict[str, Any]:
        """Return the raw recorded response for ``query`` (never a live fetch)."""


@runtime_checkable
class DatasetSearchAdapter(SearchAdapter, Protocol):
    """Searches a public dataset catalogue (GEO / equivalent) — offline fake only.

    RESERVED production adapter: a GEO / ArrayExpress / ENA search reached over an
    audited HTTP tool broker with recorded responses.  The offline fake replays a
    committed dataset-search fixture and never invents a real accession.
    """


@runtime_checkable
class LiteratureSearchAdapter(SearchAdapter, Protocol):
    """Searches a public literature index — offline fake only.

    RESERVED production adapter: a Europe PMC / PubMed search over the tool
    broker.  Every returned record must carry a unique identifier and source; a
    record without one may never be marked VERIFIED downstream (T-08-03).
    """


@runtime_checkable
class AnnotationSearchAdapter(SearchAdapter, Protocol):
    """Searches an annotation-resource catalogue — offline fake only.

    RESERVED production adapter: an annotation source catalogue (e.g. gene / GO /
    pathway resources).  A returned record records version, evidence tier and
    licence, and a database annotation is never labelled experimentally validated
    (T-08-04).
    """


@dataclass(frozen=True)
class RecordedSearchResponse:
    """One committed, synthetic raw response keyed by its exact query.

    ``query`` is the exact query dict the response was recorded for; ``response``
    is the raw response body (results / pagination / echoed params).  Both are
    treated as immutable — the adapter deep-copies on the way out so a caller can
    never mutate the recording.
    """

    query: dict[str, Any]
    response: dict[str, Any]


def canonical_query_key(query: dict[str, Any]) -> str:
    """A stable content key for a query, so replay matches by content not identity.

    Only the *content-bearing* fields are keyed (domain + terms + filters +
    pagination request); presentation-only fields are ignored so an equivalent
    query always replays the same recording.
    """
    keyed = {
        "domain": query.get("domain", ""),
        "original_terms": sorted(str(t) for t in query.get("original_terms", []) if str(t).strip()),
        "standard_terms": sorted(str(t) for t in query.get("standard_terms", []) if str(t).strip()),
        "filters": query.get("filters", {}),
        "page": query.get("page", 1),
        "page_size": query.get("page_size", 0),
    }
    return hash_payload(keyed)


class OfflineRecordedSearchAdapter:
    """A deterministic fake adapter that replays recorded raw responses.

    Constructed with a tool identity, a :data:`SEARCH_DOMAINS` value and a list of
    :class:`RecordedSearchResponse` recordings.  :meth:`search` looks the query up
    by :func:`canonical_query_key`; a hit replays the recorded raw response
    verbatim (deep-copied), a miss returns a recorded-empty response.  It performs
    no I/O of any kind and is a pure function of its recordings plus the query.
    """

    def __init__(
        self,
        *,
        tool_name: str,
        tool_version: str,
        domain: str,
        recordings: list[RecordedSearchResponse] | None = None,
    ) -> None:
        if domain not in SEARCH_DOMAINS:
            raise ValueError(f"domain must be one of {SEARCH_DOMAINS}, got {domain!r}")
        self.tool_name = str(tool_name)
        self.tool_version = str(tool_version)
        self.domain = domain
        self._recordings: dict[str, dict[str, Any]] = {}
        for rec in recordings or []:
            self._recordings[canonical_query_key(rec.query)] = copy.deepcopy(rec.response)

    def _envelope(self, query: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
        """Wrap a recorded body with the adapter's stable identity + replay marker."""
        out = copy.deepcopy(body)
        out.setdefault("results", [])
        out.setdefault("status", RAW_STATUS_EMPTY if not out["results"] else RAW_STATUS_OK)
        out.setdefault("pagination", {"page": query.get("page", 1), "page_size": query.get("page_size", 0), "total": len(out["results"])})
        out["tool"] = {"name": self.tool_name, "version": self.tool_version, "domain": self.domain}
        out["retrieval_mode"] = REPLAY_RETRIEVAL_MODE
        out["echoed_params"] = {
            "domain": query.get("domain", self.domain),
            "original_terms": list(query.get("original_terms", [])),
            "standard_terms": list(query.get("standard_terms", [])),
            "filters": copy.deepcopy(query.get("filters", {})),
            "page": query.get("page", 1),
            "page_size": query.get("page_size", 0),
        }
        return out

    def search(self, query: dict[str, Any]) -> dict[str, Any]:
        key = canonical_query_key(query)
        if key in self._recordings:
            return self._envelope(query, self._recordings[key])
        # Recorded-empty: an honestly no-hit response, never a fabricated result.
        return self._envelope(query, {"results": [], "status": RAW_STATUS_EMPTY})


@dataclass(frozen=True)
class SearchFixtureBundle:
    """A committed set of recordings for the three offline adapters.

    Purely synthetic and clearly-labelled; it lets a test drive the full
    discovery + audit path offline with byte-stable inputs.
    """

    dataset: list[RecordedSearchResponse] = field(default_factory=list)
    literature: list[RecordedSearchResponse] = field(default_factory=list)
    annotation: list[RecordedSearchResponse] = field(default_factory=list)
