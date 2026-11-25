import json
import tempfile
import unittest
from pathlib import Path

from catalog import write
from research_profile import classify, coverage, load_profile, primary_metadata


class ResearchProfileTest(unittest.TestCase):
    def test_template_validates(self):
        self.assertIn("instruments", load_profile("template")["primary_categories"])
        with self.assertRaises(ValueError):
            load_profile("../private")

    def test_custom_dimensions_and_search_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = dict(id="local-test", primary_categories={"briefs": "Briefs"},
                           themes={"review": "Review", "adopt": "Adoption"},
                           settings={"municipal": "Municipal"}, priority=["review"])
            (root / "local-test.md").write_text("# Test\n```json profile\n" + json.dumps(profile) + "\n```\n")
            profile = load_profile("local-test", root)
            row = {"id": "one", "primary_category": "briefs", "themes": "review|adopt",
                   "settings": "municipal", "theme_settings": "review=municipal", "evidence": "Test fixture"}
            write(root / "profile-classification.csv", list(row), [row])
            (root / "profile-search.csv").write_text(
                "theme,setting,status,evidence\nadopt,municipal,executed,fixture receipt\n")
            catalogue = [{"id": "one"}]
            tags = classify(profile, root, catalogue)
            self.assertEqual(primary_metadata(profile, root, catalogue)["one"]["primary_category"], "briefs")
            matrix = {(r["theme"], r["dimension"]): r for r in coverage(profile, tags, root, {"one"})}
            self.assertEqual(matrix["review", "municipal"]["complete"], 1)
            self.assertEqual(matrix["adopt", "municipal"]["coverage_status"], "no_records_after_search")
            self.assertEqual(matrix["adopt", ""]["documents"], 1)
            with self.assertRaises(ValueError):
                classify(profile, root, [{"id": "missing"}])
