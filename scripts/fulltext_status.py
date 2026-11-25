"""Resolve workbook access states from explicit access and body evidence."""
from pathlib import Path

SAVED = {"saved_pdf", "saved_html", "saved_other"}
PARTIAL = "partial"
PENDING = "unverified"
ONLINE = "online_full"
ACCESS_ONLY = {ONLINE, "abstract", "subscription", "archive_lead", PENDING}


def access_state(path, digest, body, receipt):
    if path:
        reviewed = (digest and body.get("reviewed_sha256") == digest
                    and body.get("metadata_evidence_url", "").strip()
                    and body.get("body_locator", "").strip())
        if not reviewed:
            return PENDING
        if body.get("body_status") == "partial":
            return PARTIAL
        if body.get("body_status") != "complete" or body.get("source_status") != "verified":
            return PENDING
        suffix = Path(path).suffix.lower()
        if suffix == ".pdf":
            return "saved_pdf"
        if suffix in {".html", ".htm", ".xhtml"}:
            return "saved_html"
        return "saved_other"
    declared = receipt.get("access_status", "")
    if (declared in ACCESS_ONLY and receipt.get("evidence_url", "").strip()
            and receipt.get("reason", "").strip()):
        return declared
    return PENDING
