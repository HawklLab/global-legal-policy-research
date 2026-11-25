"""Audit local attachments and search coverage without network access."""
import argparse
import re
import shutil
import subprocess
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

from catalog import read, write
from package_delivery import file_hash, read_snapshot
from research_state import COVERAGE, history, cutoff_label

CARE = dict(zip("ABCDEFGH", (
    "legislation amendment",
    "bill preparatory-report",
    "debate parliamentary-decision committee-report campaign-proposal",
    "country-report international-report international-record",
    "advocacy campaign-history campaign-material",
    "policy consultation",
    "journal-article evaluation",
    "court-decision",
)))
BUCKET = {c: k for k, types in CARE.items() for c in types.split()}
LEGAL = {"original", "amendment", "point_in_time", "consolidated", "related"}
RELATIONS = {"version_of", "amends", "related_to", "translation_of", "format_of"}


def optional(root, name):
    path = root / name
    return read(path) if path.is_file() else []


def fold(text):
    return "".join(char for char in unicodedata.normalize("NFKC", text).casefold() if char.isalnum())


class HtmlText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.heading = 0
        self.text = []
        self.titles = []
        self.password = False

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "template", "noscript"}:
            self.hidden += 1
        if tag in {"h1", "title"}:
            self.heading += 1
        if tag == "input" and dict(attrs).get("type") == "password":
            self.password = True

    def handle_endtag(self, tag):
        if tag in {"script", "style", "template", "noscript"}:
            self.hidden = max(0, self.hidden - 1)
        if tag in {"h1", "title"}:
            self.heading = max(0, self.heading - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.text.append(data)
            if self.heading:
                self.titles.append(data)


def extract(path):
    size = path.stat().st_size
    with path.open("rb") as handle:
        start = handle.read(1024)
        handle.seek(max(0, size - 4096))
        end = handle.read()
    if not start.strip():
        return "invalid", "empty", "", ""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        if b"%PDF-" not in start or b"%%EOF" not in end:
            return "invalid", "bad_pdf_signature_or_missing_eof", "", ""
        if not shutil.which("pdfinfo") or not shutil.which("pdftotext"):
            return "review", "poppler_unavailable", "", ""
        try:
            info = subprocess.run(["pdfinfo", str(path)], capture_output=True, timeout=20)
            parsed = subprocess.run(["pdftotext", "-f", "1", "-l", "8", str(path), "-"],
                                    capture_output=True, timeout=35)
        except subprocess.TimeoutExpired:
            return "review", "pdf_parse_timeout", "", ""
        if info.returncode or not re.search(rb"(?m)^Pages:\s+[1-9]\d*", info.stdout) or parsed.returncode:
            return "invalid", "pdf_parser_error", "", ""
        text = parsed.stdout.decode("utf-8", "replace")
        if len(fold(text)) < 35 or sum(c.isalpha() for c in text) < 30:
            return "review", "scan_or_unusable_text", "", ""
        return "readable", "pdf_parse_ok", text, ""
    if suffix in {".html", ".htm", ".xhtml"}:
        if size > 35 * 1024 * 1024:
            return "review", "large_html_needs_review", "", ""
        html = path.read_bytes()
        if not re.search(rb"<(?:!doctype\s+html|html|head|body|main|article)\b", html[:8192], re.I):
            return "invalid", "html_signature_missing", "", ""
        encoding = re.search(rb"charset\s*=\s*[\"']?([-\w]+)", html[:8192], re.I)
        try:
            text = html.decode(encoding[1].decode() if encoding else "utf-8", "replace")
        except LookupError:
            text = html.decode("utf-8", "replace")
        parser = HtmlText()
        parser.feed(text)
        headings = " ".join(parser.titles)
        body = " ".join(parser.text)
        if re.search(r"(?i)\b(?:404|403|access denied|page not found|just a moment|captcha|service unavailable|verify you are human)\b", headings):
            return "invalid", "html_error_or_challenge", "", headings
        if parser.password and re.search(r"(?i)\b(?:log\s?in|sign\s?in|anmelden|iniciar sesión)\b", headings):
            return "invalid", "html_login", "", headings
        if len(fold(body)) < 80:
            return "review", "html_too_little_text", body, headings
        if re.search(r"(?i)\b(?:abstract only|article preview|purchase access)\b", headings):
            return "review", "possible_abstract_only", body, headings
        return "readable", "html_parse_ok", body, headings
    return "review", "format_requires_manual_review", "", ""


def article_status(row, actual, expected, evidence):
    source = evidence.get("source_status", "")
    if source == "dead":
        return "link_dead"
    if not actual:
        if evidence.get("download_status") == "failed":
            return "download_failed"
        if source == "lead" or (not row["source_url"] and not source):
            return "lead_only"
        return "source_verified_no_fulltext" if source == "verified" or (
            not source and row["verification"] == "verified") else "source_pending"
    if actual in {"invalid", "missing", "hash_mismatch"}:
        return "download_failed"
    if (expected and evidence.get("reviewed_sha256") == expected
            and all(evidence.get(k) for k in ("metadata_evidence_url", "body_locator"))):
        if evidence.get("body_status") == "partial":
            return "reviewed_partial"
        if source == "verified" and evidence.get("body_status") == "complete":
            return "source_verified_fulltext"
    return "body_review_needed"


def audit_rows(catalogue, downloads, evidence, cutoff):
    results = []
    same_hash = {}
    for row in catalogue:
        identifier = row["id"]
        detail = evidence.get(identifier, {})
        relative = row["download_path"]
        path = downloads.get(relative)
        digest, match, duplicate = "", "", ""
        state, reason = ("missing", "catalogued_file_missing") if relative else ("", "")
        if path and path.is_file():
            digest = file_hash(path)
            if row.get("sha256") and row["sha256"] != digest:
                state, reason = "hash_mismatch", "previous_sha256_changed"
            else:
                state, reason, body, headings = extract(path)
                folded = fold(body)
                title = fold(row["original_title"])
                number = fold(row["document_number"])
                if title and len(title) >= 8 and title in fold(headings):
                    match = "heading"
                elif number and len(number) >= 5 and number in folded:
                    match = "document_number"
                elif title and len(title) >= 10 and title in folded:
                    match = "title_in_text"
                elif state == "readable":
                    reason += ";identity_not_confirmed"
            duplicate = same_hash.get(digest, "")
            same_hash.setdefault(digest, identifier)
        status = article_status(row, state, digest, detail)
        historical_ok = (relative and digest and row.get("sha256") == digest and
                         row["verification"] == "verified" and row["full_text"] == "yes")
        if not relative or state in {"invalid", "missing", "hash_mismatch"}:
            next_step = "check_source_or_retry"
        elif status == "source_verified_fulltext" or (historical_ok and bool(match) and state == "readable"):
            next_step = "reuse_local"
        else:
            next_step = "review_local_first"
        results.append(dict(id=identifier, status=status, file_check=state, content_match=match,
                            reason=reason, reviewed_source_status=detail.get("source_status", ""),
                            checked_at=datetime.now(timezone.utc).isoformat(), retrieved_on=row["retrieved_on"],
                            cutoff_phase=cutoff_label(row["retrieved_on"], cutoff),
                            audit_cutoff_phase=cutoff_label(datetime.now(timezone.utc).isoformat(), cutoff),
                            path=relative, sha256=digest, same_bytes_as=duplicate, next_step=next_step))
    return results


def coverage_rows(catalogue, candidates, checks, queries, gaps):
    output = []
    checks = {r["id"]: r for r in checks}
    for code, label in COVERAGE.items():
        attempts = [s for s in queries if code in s["categories"] and s["state"] != "planned"]
        done = [s for s in attempts if s["state"] == "executed"]
        rows = [r for r in catalogue if BUCKET.get(r["category"]) == code]
        full = sum(checks[r["id"]]["status"] == "source_verified_fulltext" for r in rows)
        if not done:
            state = "attempt_incomplete" if attempts else "not_searched_or_no_execution_evidence"
        elif not rows:
            state = ("searched_no_candidates" if all(q["result_count"] == 0 for q in done)
                     else "results_need_triage")
        else:
            state = "materials_with_confirmed_fulltext" if full else "materials_no_new_fulltext_confirmation"
        output.append(dict(category=code, label=label, search_status=state,
                           databases=" | ".join(sorted({q["database"] for q in done})),
                           open_attempts=sum(q["state"] != "executed" for q in attempts),
                           candidates=sum(BUCKET.get(r["category"]) == code for r in candidates),
                           source_verified=sum(r["verification"] == "verified" or
                                               checks[r["id"]]["reviewed_source_status"] == "verified" for r in rows),
                           historically_saved=sum(bool(r["download_path"]) for r in rows),
                           fulltext_confirmed=full,
                           gap=gaps.get(code, ""),
                           further_search="review" if gaps.get(code) or not done or not rows or not full
                           else "decide_from_scope"))
    return output


def version_rows(catalogue, claims):
    docs = {row["id"]: row for row in catalogue}
    output = []
    for item in claims:
        identifier = item["id"]
        kind = item["version_kind"]
        relation = item["relation"]
        target = item["related_id"]
        if (identifier not in docs or kind not in LEGAL or relation not in RELATIONS or
                (target and (target not in docs or target == identifier)) or not item["law_id"] or
                not item["evidence_url"] or (kind == "point_in_time" and not item["effective_on"])):
            raise ValueError(f"Invalid legal version claim for {identifier}")
        output.append(item)
    covered = {row["id"] for row in output}
    for row in catalogue:
        if row["id"] not in covered and row["category"] in {"legislation", "amendment"}:
            output.append(dict(id=row["id"], law_id="", version_kind="needs_review", effective_on="",
                               relation="", related_id="", evidence_url=""))
    return output


def audit(run, output, journal=None, country=None, cutoff=None, annotations=None):
    if output.exists() or output.resolve().is_relative_to(run.resolve()):
        raise ValueError("Audit output must be a new location outside the input snapshot")
    root, paths = read_snapshot(run)
    notes = annotations or root
    catalogue = read(root / "catalog.csv")
    candidates = read(root / "candidates.csv")
    evidence = {r["id"]: r for r in optional(notes, "verification-evidence.csv")}
    gaps = {r["category"]: r["gap"] for r in optional(notes, "coverage-gaps.csv")}
    events = history(journal or root / "research.sqlite", "search", country)
    queries = list(dict(events).values())
    checks = audit_rows(catalogue, paths, evidence, cutoff)
    coverage = coverage_rows(catalogue, candidates, checks, queries, gaps)
    versions = version_rows(candidates, optional(notes, "legal-versions.csv"))
    output.mkdir(parents=True)
    for name, rows in (("verification-audit.csv", checks), ("coverage-audit.csv", coverage),
                       ("version-audit.csv", versions)):
        if rows:
            write(output / name, list(rows[0]), rows)
    print(f"{len(candidates)} candidates; {len(catalogue)} catalogue records")
    print(dict(Counter(row["next_step"] for row in checks)))
    print(dict(Counter(row["status"] for row in checks)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--journal", type=Path)
    parser.add_argument("--country")
    parser.add_argument("--cutoff")
    parser.add_argument("--annotations", type=Path)
    args = parser.parse_args()
    audit(args.run, args.output, args.journal, args.country, args.cutoff, args.annotations)
