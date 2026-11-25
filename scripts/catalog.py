"""Build a local legal research catalogue and preserve candidate provenance."""
import argparse
import csv
import hashlib
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "assets"


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def header(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return next(csv.reader(handle))


def write(path, fields, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def norm(value):
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def doi(row):
    return re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", norm(row["doi"]))


def strong_key(row):
    guards = tuple(norm(row[key]) for key in (
        "country", "language", "category", "version", "original_title", "year"
    ))
    number = (norm(row["identifier_series"]), norm(row["document_number"]))
    if all(guards) and (doi(row) or all(number)) and row["verification"] == "verified":
        return guards, doi(row), number
    return None


def group(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[strong_key(row) or ("id", row["id"])].append(row)
    canonical = []
    decisions = []
    for same in groups.values():
        main = max(same, key=lambda row: (bool(row["download_path"]), row["verification"] == "verified"))
        canonical.append(main)
        decisions.extend(dict(primary_id=main["id"], candidate_id=row["id"],
                              decision="merged", basis="verified explicit version + identifiers + original title",
                              candidate_url=row["source_url"])
                         for row in same if row is not main)
    titles = defaultdict(list)
    for row in canonical:
        keys = tuple(norm(row[k]) for k in ("country", "original_title", "year"))
        if all(keys):
            for other in titles[keys]:
                decisions.append(dict(primary_id=other["id"], candidate_id=row["id"],
                                      decision="review", basis="same original title/year; check identifiers and versions",
                                      candidate_url=row["source_url"]))
            titles[keys].append(row)
    return canonical, decisions


def file_metadata(run, relative):
    path = (run / relative).resolve(strict=True)
    if not path.is_relative_to((run / "downloads").resolve()) or not path.is_file():
        raise ValueError(f"Attachment outside downloads or not a file: {relative}")
    with path.open("rb") as handle:
        prefix = handle.read(1024)
        if not prefix.strip() or (path.suffix.lower() == ".pdf" and b"%PDF-" not in prefix):
            raise ValueError(f"Unexpected file signature: {relative}")
        handle.seek(0)
        digest = hashlib.sha256()
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return str(path.stat().st_size), digest.hexdigest()


def build(run, baseline=None, require_evidence=False):
    fields = header(ASSETS / "candidates.csv")
    tables = {}
    for template in ASSETS.glob("*.csv"):
        path = run / template.name
        if header(path) != header(template):
            raise ValueError(f"Schema mismatch: {path}")
        tables[template.stem] = read(path)
    candidates = tables["candidates"]
    evidence_path = run / "verification-evidence.csv"
    reviewed = {row["id"]: row for row in read(evidence_path)} if evidence_path.is_file() else {}
    files = {}
    identifiers = set()
    (run / "downloads").mkdir(exist_ok=True)
    for row in candidates:
        if not row["id"] or row["id"] in identifiers:
            raise ValueError(f"Missing or repeated candidate ID: {row['id']}")
        identifiers.add(row["id"])
        if row["download_path"]:
            files[row["id"]] = file_metadata(run, row["download_path"])
            evidence = reviewed.get(row["id"], {})
            if row["full_text"] != "yes" and not (
                    evidence.get("body_status") == "partial"
                    and evidence.get("reviewed_sha256") == files[row["id"]][1]
                    and evidence.get("metadata_evidence_url") and evidence.get("body_locator")):
                raise ValueError(f"Attachment lacks a full-text claim or reviewed partial evidence: {row['id']}")
    if require_evidence:
        from audit_research import audit_rows
        previous = {}
        if baseline:
            from package_delivery import read_snapshot
            previous_root, _ = read_snapshot(baseline)
            previous = {row["id"]: row for row in read(previous_root / "catalog.csv")}
        assess = [row for row in candidates if row["download_path"] and not (
            previous.get(row["id"], {}).get("sha256") == files[row["id"]][1]
            and previous[row["id"]]["full_text"] == "yes"
            and previous[row["id"]]["verification"] == "verified")]
        checks = audit_rows(assess, {r["download_path"]: run / r["download_path"] for r in assess}, reviewed, None)
        outstanding = [row["id"] for row in checks if row["status"] not in {"source_verified_fulltext", "reviewed_partial"}]
        if outstanding:
            raise ValueError("New or replaced attachments need verified body evidence: " + ", ".join(outstanding))
    for edge in tables["citation-chain"]:
        if {edge["from_id"], edge["to_id"]} - identifiers:
            raise ValueError(f"Unresolved citation IDs: {edge}")
    rows, decisions = group(candidates)
    catalogue = [dict(row, bytes=files.get(row["id"], ("", ""))[0],
                      sha256=files.get(row["id"], ("", ""))[1]) for row in rows]
    write(run / "catalog.csv", fields + ["bytes", "sha256"], catalogue)
    write(run / "duplicates.csv", ["primary_id", "candidate_id", "decision", "basis", "candidate_url"], decisions)
    missing = [row for row in rows if not row["download_path"]]
    write(run / "missing.csv", ["id", "title", "source_url", "verification", "full_text", "missing_reason"],
          [{k: row[k] for k in ("id", "title", "source_url", "verification", "full_text")} |
           {"missing_reason": row["missing_reason"] or "Acquisition reason not yet recorded"} for row in missing])
    if baseline:
        from package_delivery import read_snapshot

        prior_catalog = read_snapshot(baseline)[0] / "catalog.csv"
        prior = {row["id"]: row for row in read(prior_catalog)}
        current = {row["id"]: row for row in catalogue}
        changes = []
        for identifier in sorted(prior.keys() | current.keys()):
            before, after = prior.get(identifier), current.get(identifier)
            changed = [k for k in fields + ["sha256"] if k != "retrieved_on"
                       and before and after and before.get(k) != after.get(k)]
            status = "added" if before is None else "absent" if after is None else "changed"
            if before is None or after is None or changed:
                changes.append(dict(id=identifier, change=status, fields=", ".join(changed)))
        write(run / "update-diff.csv", ["id", "change", "fields"], changes)
    languages = Counter(r["language"] for r in tables["search-log"])
    categories = Counter(r["category"] for r in rows)
    verified = Counter(r["verification"] for r in rows)
    notes = run / "coverage-notes.md"
    stats = [
        "# Backend coverage", "",
        f"- {len(candidates)} candidates, {len(rows)} catalogue records, {len(candidates) - len(rows)} merged.",
        f"- Local copies: {len(rows) - len(missing)}. No local copy: {len(missing)}.",
        f"- Source entries: {len(tables['country-sources'])}. Citation edges: {len(tables['citation-chain'])}.",
        "- Query languages: " + ", ".join(f"{k} {v}" for k, v in sorted(languages.items())),
        "- Document types: " + ", ".join(f"{k} {v}" for k, v in sorted(categories.items())),
        "- Source verification: " + ", ".join(f"{k} {v}" for k, v in sorted(verified.items())),
        "", notes.read_text(encoding="utf-8") if notes.exists() else "No editorial coverage notes."
    ]
    (run / "coverage.md").write_text("\n".join(stats) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--require-evidence", action="store_true")
    args = parser.parse_args()
    build(args.run.resolve(), args.baseline, args.require_evidence)
