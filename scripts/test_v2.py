import tempfile
import unittest
from pathlib import Path

from audit_research import audit_rows, coverage_rows, extract, version_rows
from research_state import cutoff_label, latest, record, resume


def search(state, at, **changes):
    event = dict(kind="search", country="DE", at=at, layer=2, categories=["A"],
                 database="public catalogue", query="sample query", language="de", scope="test",
                 state=state, result_count=0, count_basis="returned results", evidence="receipt")
    event.update(changes)
    return event


class ResearchV2Test(unittest.TestCase):
    def test_resume_and_distinct_execution(self):
        with tempfile.TemporaryDirectory() as root:
            journal = Path(root) / "events.sqlite"
            record(journal, search("planned", "2025-01-01T10:00:00+02:00"))
            self.assertEqual(len(resume(journal)), 1)
            record(journal, search("failed", "2025-01-01T10:01:00+02:00"))
            record(journal, search("failed", "2025-01-01T10:02:00+02:00"))
            self.assertEqual(resume(journal)[0]["disposition"], "manual_review")
            record(journal, search("executed", "2025-01-01T10:03:00+02:00"))
            self.assertEqual(resume(journal), [])
            with self.assertRaises(ValueError):
                record(journal, search("executed", "2025-01-01T10:04:00+02:00", evidence=""))

    def test_reusable_source_and_check_history(self):
        with tempfile.TemporaryDirectory() as root:
            journal = Path(root) / "sources.sqlite"
            source = dict(kind="source", country="DE", at="2025-01-01T01:00:00Z",
                          source_id="law", name="Law registry", operator="Government", url="https://example.org",
                          role="official", coverage="acts", languages=["de"], free_access="yes",
                          full_text_search="unknown", formats=["html"], status="verified",
                          ownership_url="", function_url="https://example.org/catalogue")
            with self.assertRaises(ValueError):
                record(journal, source)
            record(journal, dict(source, ownership_url="https://example.org/about"))
            self.assertEqual(len(latest(journal, "source", "DE")), 1)
            self.assertEqual(latest(journal, "source", "AT"), {})

    def test_html_pdf_and_full_text(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            invalid = folder / "bad.pdf"
            invalid.write_bytes(b"<html>invalid</html>")
            self.assertEqual(extract(invalid)[0], "invalid")
            valid_html = folder / "act.html"
            valid_html.write_text("<html><h1>Test Act: Judicial procedure</h1><article>" +
                                  "The complete first provision of the act as approved. " * 4 + "</article></html>")
            self.assertEqual(extract(valid_html)[0], "readable")
            login = folder / "login.html"
            login.write_text("<html><title>Sign in</title><input type='password'></html>")
            self.assertEqual(extract(login)[:2], ("invalid", "html_login"))
            error = folder / "error.html"
            error.write_text("<html><title>404 Page not found</title></html>")
            self.assertEqual(extract(error)[:2], ("invalid", "html_error_or_challenge"))
            row = dict(id="law", download_path="act.html", original_title="Test Act: Judicial procedure",
                       document_number="", verification="verified", full_text="yes",
                       retrieved_on="2025-01-02", source_url="https://example.org", category="legislation")
            checks = audit_rows([row], {"act.html": valid_html}, {}, "2025-01-01")
            self.assertEqual(checks[0]["content_match"], "heading")
            self.assertEqual(checks[0]["status"], "body_review_needed")
            evidence = {"law": dict(source_status="verified", body_status="complete",
                                    reviewed_sha256=checks[0]["sha256"], body_locator="sections 1–2",
                                    metadata_evidence_url=row["source_url"])}
            self.assertEqual(audit_rows([row], {"act.html": valid_html}, evidence, None)[0]["status"],
                             "source_verified_fulltext")
            self.assertEqual(checks[0]["cutoff_phase"], "post_cutoff_check")
            self.assertEqual(cutoff_label("2025-01-01", "2025-01-01"), "within_cutoff")

    def test_coverage_and_historical_versions(self):
        day = "2025-01-02T01:00:00Z"
        checks = coverage_rows([], [], [], [
            search("executed", day, categories=["A"]),
            search("planned", day, categories=["B"]),
        ], {})
        self.assertEqual(checks[0]["search_status"], "searched_no_candidates")
        self.assertEqual(checks[1]["search_status"], "not_searched_or_no_execution_evidence")
        versions = version_rows([{"id": "act", "category": "legislation"},
                                 {"id": "amend", "category": "amendment"}],
                                [dict(id="amend", law_id="DE:act", version_kind="amendment",
                                      relation="amends", related_id="act", effective_on="",
                                      evidence_url="https://example.org")])
        self.assertEqual({row["version_kind"] for row in versions}, {"amendment", "needs_review"})


if __name__ == "__main__":
    unittest.main()
