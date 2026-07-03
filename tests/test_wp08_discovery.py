"""WP-08 offline resource discovery + search audit tests (T-08-01..12)."""

from __future__ import annotations

import unittest

from auto_bioinfo.adapters.offline_search import (
    SEARCH_DOMAINS,
    AnnotationSearchAdapter,
    DatasetSearchAdapter,
    LiteratureSearchAdapter,
    OfflineRecordedSearchAdapter,
    RecordedSearchResponse,
    SearchAdapter,
    canonical_query_key,
)
from auto_bioinfo.core.validation import validate_resource_candidate
from auto_bioinfo.resources.discovery import (
    CODE_DOMAIN_BLOCKED,
    CODE_QUERY_MALFORMED,
    DISPOSITION_DUPLICATE,
    DISPOSITION_FILTERED,
    DISPOSITION_NORMALIZED,
    QUERY_NO_TERMS,
    RUN_STATUS_BLOCKED,
    RUN_STATUS_CANDIDATES_FOUND,
    RUN_STATUS_EMPTY,
    RUN_STATUS_FAILED,
    RUN_STATUS_REJECTED_MALFORMED,
    STOP_DUPLICATE_RATE,
    STOP_PAGE_BUDGET,
    STOP_RESULT_BUDGET,
    STOP_RESULTS_STABLE,
    build_search_query,
    decide_stop,
    dedupe_candidates,
    normalize_candidate,
    propose_ranking,
    run_search,
)
from auto_bioinfo.resources.search_policy import (
    CODE_CREDENTIAL_REFERENCE_INVALID,
    CODE_DOMAIN_NOT_ALLOWLISTED,
    CODE_RATE_LIMIT_EXCEEDED,
    CODE_USER_AGENT_MISSING,
    NetworkAccessPolicy,
)

PLAN = {"research_spec_id": "rs_demo", "evidence_plan_id": "evidence_plan_abc", "evidence_axes": ["transcriptomic_differential"]}
SCOPE = {"species": ["human"], "tissues": ["liver"], "conditions": ["tumor", "normal"], "comparisons": ["tumor", "normal"]}


def _dataset_response(query):
    return RecordedSearchResponse(
        query=query,
        response={
            "results": [
                {
                    "namespace": "GEO",
                    "identifier": "GSE111111",
                    "title": "Liver tumor vs normal",
                    "source_uri": "https://ex.test/GSE111111",
                    "source_class": "PUBLIC_DATABASE",
                },
                {"namespace": "GEO", "identifier": "GSE222222", "title": "Human liver RNA-seq", "source_class": "PUBLIC_DATABASE"},
                {"namespace": "GEO", "identifier": "GSE111111", "title": "duplicate hit from another query facet"},
                {"title": "record with no namespace/identifier"},
            ],
            "status": "ok",
        },
    )


class BuildSearchQueryTests(unittest.TestCase):
    def test_original_and_standard_terms_kept_separate(self):
        mappings = [{"status": "mapped", "mapped_id": "NCBITaxon:9606"}, {"status": "unresolved", "mapped_id": ""}]
        result = build_search_query(PLAN, domain="dataset", scope_bundle=SCOPE, ontology_mappings=mappings)
        self.assertTrue(result.built)
        q = result.query
        self.assertIn("human", q["original_terms"])
        self.assertIn("transcriptomic_differential", q["original_terms"])
        # Only the resolved mapping contributes a standard term (T-08-05).
        self.assertEqual(q["standard_terms"], ["NCBITaxon:9606"])

    def test_no_terms_fails_closed(self):
        result = build_search_query({"research_spec_id": "rs_demo"}, domain="dataset")
        self.assertEqual(result.status, QUERY_NO_TERMS)
        self.assertIsNone(result.query)

    def test_malformed_domain_and_plan(self):
        self.assertEqual(build_search_query(PLAN, domain="genome").reason_code, CODE_QUERY_MALFORMED)
        self.assertEqual(build_search_query("not a plan", domain="dataset").reason_code, CODE_QUERY_MALFORMED)
        self.assertEqual(build_search_query({"research_spec_id": "BAD ID"}, domain="dataset").reason_code, CODE_QUERY_MALFORMED)

    def test_query_id_is_deterministic(self):
        a = build_search_query(PLAN, domain="dataset", scope_bundle=SCOPE).query
        b = build_search_query(PLAN, domain="dataset", scope_bundle=SCOPE).query
        self.assertEqual(a["search_query_id"], b["search_query_id"])
        self.assertEqual(a["created_at"], "")


class AdapterContractTests(unittest.TestCase):
    def test_protocols_are_structural(self):
        ad = OfflineRecordedSearchAdapter(tool_name="geo", tool_version="1", domain="dataset")
        self.assertIsInstance(ad, SearchAdapter)
        self.assertIsInstance(ad, DatasetSearchAdapter)
        self.assertIsInstance(ad, LiteratureSearchAdapter)
        self.assertIsInstance(ad, AnnotationSearchAdapter)

    def test_all_domains_constructible(self):
        for d in SEARCH_DOMAINS:
            self.assertEqual(OfflineRecordedSearchAdapter(tool_name="t", tool_version="1", domain=d).domain, d)

    def test_bad_domain_rejected(self):
        with self.assertRaises(ValueError):
            OfflineRecordedSearchAdapter(tool_name="t", tool_version="1", domain="bogus")

    def test_recorded_replay_and_empty_miss(self):
        q = build_search_query(PLAN, domain="dataset", scope_bundle=SCOPE).query
        ad = OfflineRecordedSearchAdapter(tool_name="geo", tool_version="1", domain="dataset", recordings=[_dataset_response(q)])
        hit = ad.search(q)
        self.assertEqual(hit["status"], "ok")
        self.assertEqual(hit["retrieval_mode"], "RECORDED_REPLAY")
        miss = ad.search({**q, "original_terms": ["something-else-unrecorded"], "page": 9})
        self.assertEqual(miss["status"], "empty")
        self.assertEqual(miss["results"], [])

    def test_canonical_query_key_ignores_presentation_fields(self):
        q1 = {"domain": "dataset", "original_terms": ["a", "b"], "page": 1, "page_size": 20}
        q2 = {"domain": "dataset", "original_terms": ["b", "a"], "page": 1, "page_size": 20, "search_query_id": "x"}
        self.assertEqual(canonical_query_key(q1), canonical_query_key(q2))


class NormalizeAndDedupTests(unittest.TestCase):
    def test_candidate_normalization_is_unverified_and_valid(self):
        q = {"domain": "dataset", "evidence_plan_id": "evidence_plan_abc"}
        cand = normalize_candidate({"namespace": "GEO", "identifier": "GSE111111", "title": "t"}, q)
        self.assertIsNotNone(cand)
        self.assertFalse(cand["verified"])
        self.assertEqual(cand["verification_level"], "UNVERIFIED")
        self.assertEqual(validate_resource_candidate(cand), [])

    def test_record_without_identifier_is_filtered(self):
        self.assertIsNone(normalize_candidate({"title": "no id"}, {"domain": "dataset"}))

    def test_dedupe_by_namespace_identifier(self):
        q = {"domain": "dataset"}
        c1 = normalize_candidate({"namespace": "GEO", "identifier": "GSE1"}, q)
        c2 = normalize_candidate({"namespace": "geo", "identifier": "gse1"}, q)  # same after upper-casing
        c3 = normalize_candidate({"namespace": "GEO", "identifier": "GSE2"}, q)
        unique, dups = dedupe_candidates([c1, c2, c3])
        self.assertEqual(len(unique), 2)
        self.assertEqual(len(dups), 1)
        self.assertEqual(dups[0]["disposition"], DISPOSITION_DUPLICATE)


class RunSearchTests(unittest.TestCase):
    def setUp(self):
        self.q = build_search_query(PLAN, domain="dataset", scope_bundle=SCOPE).query
        self.adapter = OfflineRecordedSearchAdapter(tool_name="geo", tool_version="1", domain="dataset", recordings=[_dataset_response(self.q)])

    def test_full_run_records_replayable_audit(self):
        run = run_search(self.q, self.adapter)
        self.assertEqual(run.status, RUN_STATUS_CANDIDATES_FOUND)
        self.assertEqual(len(run.candidates), 2)  # GSE111111 + GSE222222 (dup collapsed, no-id filtered)
        self.assertTrue(run.raw_response_hash)
        self.assertEqual(run.tool["name"], "geo")
        dispositions = {a["disposition"] for a in run.audit_records}
        self.assertEqual(dispositions, {DISPOSITION_NORMALIZED, DISPOSITION_DUPLICATE, DISPOSITION_FILTERED})

    def test_run_is_deterministic(self):
        self.assertEqual(run_search(self.q, self.adapter).to_dict(), run_search(self.q, self.adapter).to_dict())

    def test_empty_result_is_audited_not_dropped(self):
        empty_ad = OfflineRecordedSearchAdapter(tool_name="geo", tool_version="1", domain="dataset")
        run = run_search(self.q, empty_ad)
        self.assertEqual(run.status, RUN_STATUS_EMPTY)
        self.assertEqual(run.candidates, [])

    def test_error_result_is_failed(self):
        q2 = build_search_query({**PLAN, "evidence_plan_id": "ep_err"}, domain="dataset", scope_bundle=SCOPE).query
        err = RecordedSearchResponse(query=q2, response={"results": [], "status": "error", "error": "HTTP 503"})
        ad = OfflineRecordedSearchAdapter(tool_name="geo", tool_version="1", domain="dataset", recordings=[err])
        run = run_search(q2, ad)
        self.assertEqual(run.status, RUN_STATUS_FAILED)
        self.assertTrue(any(a.get("disposition") == "failed" for a in run.audit_records))

    def test_malformed_adapter_and_query(self):
        self.assertEqual(run_search(self.q, object()).status, RUN_STATUS_REJECTED_MALFORMED)
        self.assertEqual(run_search("not a query", self.adapter).status, RUN_STATUS_REJECTED_MALFORMED)

    def test_ranking_is_priority_not_verification(self):
        run = run_search(self.q, self.adapter)
        self.assertFalse(run.ranking["asserts_verification"])
        self.assertFalse(run.ranking["asserts_feasibility"])
        for reasons in run.ranking["reasons"].values():
            self.assertTrue(reasons)  # every priority reason traces to a field
        # candidates are still UNVERIFIED regardless of rank
        self.assertTrue(all(not c["verified"] for c in run.candidates))

    def test_propose_ranking_orders_by_field_match(self):
        q = {"domain": "dataset", "original_terms": ["tumor"], "standard_terms": []}
        c_hit = normalize_candidate({"namespace": "GEO", "identifier": "GSE1", "title": "tumor study"}, q)
        c_miss = normalize_candidate({"namespace": "GEO", "identifier": "GSE2", "title": "unrelated"}, q)
        ranking = propose_ranking([c_miss, c_hit], q)
        self.assertEqual(ranking.order[0], c_hit["resource_candidate_id"])


class NetworkPolicyTests(unittest.TestCase):
    def test_blocked_domain_never_reaches_adapter(self):
        q = build_search_query(PLAN, domain="dataset", scope_bundle=SCOPE).query
        adapter = OfflineRecordedSearchAdapter(tool_name="geo", tool_version="1", domain="dataset", recordings=[_dataset_response(q)])
        policy = NetworkAccessPolicy(allowed_domains=("ncbi.nlm.nih.gov",), user_agent="auto-bioinfo/1.0", max_calls_per_run=5)
        run = run_search(q, adapter, policy=policy, policy_domain="evil.example.com")
        self.assertEqual(run.status, RUN_STATUS_BLOCKED)
        self.assertEqual(run.reason_code, CODE_DOMAIN_BLOCKED)
        self.assertEqual(run.candidates, [])
        self.assertEqual(run.network_decision["reason_code"], CODE_DOMAIN_NOT_ALLOWLISTED)

    def test_allowlisted_domain_permitted(self):
        q = build_search_query(PLAN, domain="dataset", scope_bundle=SCOPE).query
        adapter = OfflineRecordedSearchAdapter(tool_name="geo", tool_version="1", domain="dataset", recordings=[_dataset_response(q)])
        policy = NetworkAccessPolicy(allowed_domains=("geo",), user_agent="auto-bioinfo/1.0")
        run = run_search(q, adapter, policy=policy, policy_domain="geo")
        self.assertEqual(run.status, RUN_STATUS_CANDIDATES_FOUND)

    def test_rate_limit_and_user_agent_and_credential(self):
        policy = NetworkAccessPolicy(allowed_domains=("geo",), user_agent="ua", max_calls_per_run=2)
        self.assertTrue(policy.evaluate(domain="geo", prior_calls=0).allowed)
        self.assertEqual(policy.evaluate(domain="geo", prior_calls=2).reason_code, CODE_RATE_LIMIT_EXCEEDED)
        no_ua = NetworkAccessPolicy(allowed_domains=("geo",), user_agent="")
        self.assertEqual(no_ua.evaluate(domain="geo").reason_code, CODE_USER_AGENT_MISSING)

    def test_inline_credential_rejected_at_construction(self):
        with self.assertRaises(ValueError):
            NetworkAccessPolicy(credential_reference="sk-live-1234567890secret", user_agent="ua", allowed_domains=("geo",))
        ok = NetworkAccessPolicy(credential_reference="env:GEO_API_KEY", user_agent="ua", allowed_domains=("geo",))
        self.assertEqual(ok.credential_reference, "env:GEO_API_KEY")

    def test_credential_reference_invalid_code_defined(self):
        self.assertEqual(CODE_CREDENTIAL_REFERENCE_INVALID, "NETWORK_CREDENTIAL_REFERENCE_INVALID")


class StopConditionTests(unittest.TestCase):
    def test_page_budget_guarantees_termination(self):
        d = decide_stop(page=3, page_budget=3, total_unique=1, result_budget=0, new_unique_this_page=5, duplicate_rate=0.0)
        self.assertTrue(d.stop)
        self.assertEqual(d.condition, STOP_PAGE_BUDGET)

    def test_result_budget(self):
        d = decide_stop(page=1, page_budget=10, total_unique=50, result_budget=50, new_unique_this_page=5, duplicate_rate=0.0)
        self.assertEqual(d.condition, STOP_RESULT_BUDGET)

    def test_results_stable(self):
        d = decide_stop(page=2, page_budget=10, total_unique=5, result_budget=0, new_unique_this_page=0, duplicate_rate=0.2)
        self.assertEqual(d.condition, STOP_RESULTS_STABLE)

    def test_duplicate_rate(self):
        d = decide_stop(page=2, page_budget=10, total_unique=5, result_budget=0, new_unique_this_page=1, duplicate_rate=0.95)
        self.assertEqual(d.condition, STOP_DUPLICATE_RATE)

    def test_continue_when_nothing_triggers(self):
        d = decide_stop(page=1, page_budget=10, total_unique=3, result_budget=0, new_unique_this_page=3, duplicate_rate=0.1)
        self.assertFalse(d.stop)


if __name__ == "__main__":
    unittest.main()
