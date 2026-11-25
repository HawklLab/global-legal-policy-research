import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from fulltext_status import access_state
from link_workbook import OFFICE_REL, SHEET, add_links, verify_links


class FullTextTest(unittest.TestCase):
    def setUp(self):
        self.evidence = {"reviewed_sha256": "hash", "source_status": "verified",
                         "metadata_evidence_url": "https://example.org/item",
                         "body_locator": "Title and entire body", "body_status": "complete"}

    def test_local_format_and_stale_evidence(self):
        for path, label in [("a.pdf", "saved_pdf"), ("a.xhtml", "saved_html"), ("a.png", "saved_other")]:
            self.assertEqual(access_state(path, "hash", self.evidence, {}), label)
            self.assertEqual(access_state(path, "stale", self.evidence, {}), "unverified")
        self.evidence["body_status"] = "partial"
        self.assertEqual(access_state("a.html", "hash", self.evidence, {}), "partial")

    def test_online_requires_receipt_and_is_independent_of_source_status(self):
        for label in ("subscription", "online_full", "abstract", "archive_lead"):
            receipt = {"access_status": label, "evidence_url": "https://example.org/item",
                       "reason": "出版页的正文或获取信息"}
            self.assertEqual(access_state("", None, self.evidence, receipt), label)
        self.assertEqual(access_state("", None, self.evidence, {"access_status": "saved_pdf"}), "unverified")

    def test_round_trip_hyperlinks_and_orphan_guard(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            documents = root / "Originals"
            documents.mkdir()
            (documents / "资料.html").touch()
            book = root / "catalog.xlsx"
            sheets = {"Catalogue": [["Local file"], ["Originals/资料.html"]]}
            with ZipFile(book, "w") as archive:
                archive.writestr("xl/worksheets/sheet1.xml", f'<worksheet xmlns="{SHEET}"/>')
            add_links(book, sheets, root)
            verify_links(book, sheets, root)
            (documents / "孤立.html").touch()
            with self.assertRaises(ValueError):
                verify_links(book, sheets, root)
