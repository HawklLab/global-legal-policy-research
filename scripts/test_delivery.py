import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from openpyxl import load_workbook

from catalog import header, write
from link_workbook import add_links, verify_links
from locales import folder, label, output_language
from package_delivery import prepare, export, read_snapshot
from publish_library import replace_library
from research_run import run_mode
from start_increment import start
from test_catalog import record


class DeliveryTest(unittest.TestCase):
    def test_modes_default_and_custom_profiles_republish(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config.json"
            self.assertEqual(output_language({"user_language": "zh-Hans"}), "zh-CN")
            for profile_id, category in [(None, None), ("regulation", "instruments"), ("evaluation", "results")]:
                with self.subTest(profile=profile_id):
                    name = profile_id or "basic"
                    run = root / (name + "-run")
                    library = root / (name + "-library")
                    settings = dict(country="EU", topic="Digital regulation", search_languages=["en", "de"],
                                    user_language="zh-CN", research_profile=profile_id)
                    if profile_id:
                        profile = {"id": profile_id, "priority": ["design"], "themes": {"design": "Design"},
                                   "settings": {}, "primary_categories": {category: {"en": "Category", "zh-CN": "分类"}}}
                        (root / (profile_id + ".md")).write_text(
                            "```json profile\n" + json.dumps(profile, ensure_ascii=False) + "\n```\n")
                    config.write_text(json.dumps(settings))
                    run_mode("discovery", run, config=config)
                    canonical = record("document-1", original_title="Öffentliches Verfahren", creator="Original issuer",
                                       document_number="2024/123", doi="10.0000/example", download_path="downloads/act.html")
                    pending = record("document-2", document_number="2024/124", original_title="=UNTRUSTED()",
                                     full_text="unknown", missing_reason="Subscription")
                    raw = b"<html><h1>Document</h1><article>" + b"Complete body fixture. " * 10 + b"</article></html>"
                    (run / canonical["download_path"]).write_bytes(raw)
                    write(run / "candidates.csv", header(run / "candidates.csv"), [canonical, pending])
                    evidence = dict(id="document-1", source_status="verified", metadata_evidence_url="https://example.org",
                                    body_status="complete", body_locator="Entire article", reviewed_sha256=hashlib.sha256(raw).hexdigest())
                    write(run / "verification-evidence.csv", list(evidence), [evidence])
                    if profile_id:
                        rows = [dict(id=r["id"], primary_category=category, themes="design", settings="", evidence="Fixture")
                                for r in (canonical, pending)]
                        write(run / "profile-classification.csv", list(rows[0]), rows)
                    run_mode("collection", run)
                    run_mode("audit", run, root / (name + "-audit"))
                    queue = root / (name + "-queue")
                    run_mode("full-text-retrieval", run, queue)
                    self.assertIn("document-2", (queue / "retrieval-queue.csv").read_text())
                    self.assertNotIn("document-1", (queue / "retrieval-queue.csv").read_text())
                    labels = {"titles": {"document-1": {"en": "Public procedure", "zh-CN": "公开程序"}},
                              "gaps": [{"en": "Archive access", "zh-CN": "档案访问"}]}
                    baseline = run / "catalog.csv"
                    for lang in ("en", "zh-CN", "bilingual"):
                        stage = root / (name + "-" + lang)
                        stage.mkdir()
                        filename, sheets = prepare(run, stage, labels, lang)
                        book = stage / filename
                        export(book, sheets)
                        add_links(book, sheets, stage)
                        verify_links(book, sheets, stage)
                        wb = load_workbook(book)
                        sheet = wb[folder("catalog", lang)]
                        self.assertEqual([sheet.cell(2, c).value for c in (1, 2, 4, 10, 11, 13)],
                                         ["document-1", "Öffentliches Verfahren", "Original issuer", "Act 2024/123",
                                          "10.0000/example", "https://example.org"])
                        self.assertEqual(sheet.cell(2, 15).value, label("saved_html", lang))
                        self.assertEqual(sheet.cell(3, 2).data_type, "s")
                        self.assertEqual(wb[folder("pending", lang)].max_row, 2)
                        wb.close()
                        if library.exists():
                            replace_library(stage, library)
                        else:
                            stage.rename(library)
                        backend, files = read_snapshot(library)
                        self.assertEqual(backend.joinpath("catalog.csv").read_bytes(), baseline.read_bytes())
                        self.assertEqual(next(iter(files.values())).read_bytes(), raw)
                    start(library, root / (name + "-continued"))
