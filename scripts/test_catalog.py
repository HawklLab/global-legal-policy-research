import tempfile
import unittest
from pathlib import Path

import catalog


def record(identifier, **fields):
    row = dict.fromkeys(catalog.header(catalog.ASSETS / "candidates.csv"), "")
    row.update(id=identifier, year="2001", country="Example jurisdiction", language="xx",
               version="enacted", category="amendment", original_title="Sample amending act",
               identifier_series="Act", document_number="2001:45", verification="verified",
               full_text="yes", source_url="https://example.org")
    row.update(fields)
    return row


class CatalogTest(unittest.TestCase):
    def test_verified_alias_and_conflicting_versions(self):
        main = record("original")
        alias = record("alias", download_path="downloads/file.pdf")
        newer = record("newer", version="consolidated-2020")
        other = record("other", document_number="2001:46")
        unknown = record("unknown", version="")
        different_language = record("translation", language="en")
        rows, decisions = catalog.group([main, alias, newer, other, unknown, different_language])
        self.assertEqual({r["id"] for r in rows}, {"alias", "newer", "other", "unknown", "translation"})
        self.assertEqual([(r["primary_id"], r["candidate_id"]) for r in decisions
                          if r["decision"] == "merged"], [("alias", "original")])

    def test_doi_normalization_and_title_review(self):
        fields = dict(document_number="", identifier_series="")
        main = record("doi", doi="10.1234/AbC", **fields)
        alias = record("resolver", doi="https://doi.org/10.1234/abc", **fields)
        book = record("title", **fields)
        rows, decisions = catalog.group([main, alias, book])
        self.assertEqual(len(rows), 2)
        self.assertEqual({r["decision"] for r in decisions}, {"merged", "review"})

    def test_file_and_update(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            for name in ("prior", "current"):
                run = root / name
                (run / "downloads").mkdir(parents=True)
                for template in catalog.ASSETS.glob("*.csv"):
                    (run / template.name).write_bytes(template.read_bytes())
            prior, current = root / "prior", root / "current"
            catalog.build(prior)
            fields = catalog.header(catalog.ASSETS / "candidates.csv")
            catalog.write(current / "candidates.csv", fields, [record("x", download_path="downloads/x.pdf")])
            target = current / "downloads" / "x.pdf"
            target.write_text("<html>Access denied</html>")
            with self.assertRaises(ValueError):
                catalog.build(current, prior)
            target.write_bytes(b"%PDF-1.7 test")
            catalog.build(current, prior)
            self.assertEqual(len(catalog.read(current / "catalog.csv")[0]["sha256"]), 64)
            self.assertEqual(catalog.read(current / "update-diff.csv")[0]["change"], "added")
            self.assertEqual(catalog.read(current / "missing.csv"), [])


if __name__ == "__main__":
    unittest.main()
