"""Render a verified research snapshot in the requested language."""
import argparse
import hashlib
import json
import re
import shutil
import tempfile
import unicodedata
from pathlib import Path

from catalog import read, write
from fulltext_status import PARTIAL, PENDING, SAVED, access_state
from link_workbook import add_links, verify_links
from locales import folder, folders, label, output_language, text
from publish_library import replace_library
from research_profile import classify, coverage, load_profile, primary_metadata

def filename_part(text, fallback, limit):
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", text).strip(" .-_")
    return (text or fallback).encode("utf-8")[:limit].decode("utf-8", "ignore").strip(" .")


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def document_rows(catalog, labels):
    """Keep legacy research tasks traceable in the backend only."""
    task_ids = set(labels.get("research_task_ids", []))
    if task_ids - {row["id"] for row in catalog}:
        raise ValueError("Unknown research task record ID")
    if any(row["download_path"] for row in catalog if row["id"] in task_ids):
        raise ValueError("Reconcile attachments before excluding a research task")
    return [row for row in catalog if row["id"] not in task_ids]


def library_folders(root):
    for name in sorted(folders("records")):
        if (root / name / "file-map.csv").is_file():
            from locales import LANGUAGES

            language = next(code for code in LANGUAGES if folder("records", code) == name)
            return root / name, root / folder("originals", language)
    return None


def read_snapshot(run):
    layout = library_folders(run)
    if layout:
        backend, originals = layout
        files = {row["staging_path"]: run / row["library_path"] for row in read(backend / "file-map.csv")}
        if any(not path.resolve().is_relative_to(originals.resolve()) for path in files.values()):
            raise ValueError("Mapped path escapes the originals directory")
        return backend, files
    directory = run / "downloads"
    files = {p.relative_to(run).as_posix(): p for p in directory.rglob("*")
             if p.is_file() and p.name != ".DS_Store"}
    if not directory.resolve().is_relative_to(run.resolve()) or any(
            not path.resolve().is_relative_to(directory.resolve()) for path in files.values()):
        raise ValueError("Staged attachment escapes the downloads directory")
    return run, files


DOCUMENT_FIELDS = ("id", "title", "translation", "creator", "date", "category", "themes", "settings",
                   "type", "number", "doi", "language", "url", "local", "access", "verification",
                   "retrieved", "remarks")
PENDING_FIELDS = ("id", "title", "translation", "access", "verification", "reason", "url")
SOURCE_FIELDS = ("institution", "url", "type", "authority", "language", "limitations", "checked",
                 "verification", "evidence_url")


def prepare(run, stage, labels, override=None):
    backend, files = read_snapshot(run)
    config = json.loads((backend / "run.json").read_text(encoding="utf-8"))
    lang = output_language(config, override)

    def label_for(key):
        return label(key, lang)

    all_rows = read(backend / "catalog.csv")
    catalog = document_rows(all_rows, labels)
    profile_id = config.get("research_profile")
    if profile_id and not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", profile_id):
        raise ValueError("Invalid research profile identifier")
    profile_path = backend / (profile_id + ".md") if profile_id else None
    profile = load_profile(profile_id, backend) if profile_path and profile_path.is_file() else (
        load_profile(profile_id) if profile_id else None)
    tags = classify(profile, backend, all_rows) if profile else {}
    primary = primary_metadata(profile, backend, all_rows) if profile else {}
    categories = profile.get("primary_categories", {}) if profile else {}
    evidence = optional_index(backend, "verification-evidence.csv")
    receipts = optional_index(backend, "fulltext-review.csv")
    sources = read(backend / "country-sources.csv")
    by_path = {r["download_path"]: r for r in catalog if r["download_path"]}
    if set(files) != set(by_path) or len(by_path) != sum(bool(r["download_path"]) for r in catalog):
        raise ValueError("Catalogue and attachment paths are not one-to-one; reconcile before publication")

    records = stage / folder("records", lang)
    records.mkdir()
    for item in backend.iterdir():
        if item.is_file() and item.name not in {".DS_Store", "file-map.csv", "presentation.json", "last-backup.zip"} and not (
                item.name.startswith("prior-") and item.suffix == ".xlsx"):
            shutil.copy2(item, records / item.name)
    (records / "presentation.json").write_text(json.dumps(labels, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if profile and not (records / (profile_id + ".md")).is_file():
        from research_profile import PROFILES

        shutil.copy2(PROFILES / (profile_id + ".md"), records / (profile_id + ".md"))

    original_dir = Path(folder("originals", lang))
    (stage / original_dir).mkdir()
    category_paths = {}
    if categories:
        for code, names in categories.items():
            localized = filename_part(text(names, lang, code), code, 70)
            category_paths[code] = original_dir / f"{code} - {localized}"
            (stage / category_paths[code]).mkdir()

    from audit_research import extract

    mapping, paths, checks, duplicates = [], {}, {}, {}
    for path, source in files.items():
        row = by_path[path]
        identifier = row["id"]
        digest = file_hash(source)
        if not row.get("sha256") or row["sha256"] != digest:
            raise ValueError(f"Attachment hash mismatch or missing for {identifier}")
        category = primary.get(identifier, {}).get("primary_category")
        directory = category_paths.get(category, original_dir)
        original_title = row["original_title"] or row["title"]
        title = working_title(labels, identifier, config, lang, row["english_title"])
        basename = filename_part(f"{identifier}_{title or original_title}", identifier, 135)
        destination = (directory / (basename + source.suffix.lower())).as_posix()
        if destination.casefold() in {p.casefold() for p in paths.values()}:
            raise ValueError(f"Attachment filename collision: {identifier}")
        shutil.copy2(source, stage / destination)
        if file_hash(stage / destination) != digest:
            raise ValueError(f"Copy verification failed: {identifier}")
        checks[identifier] = extract(source)[:2]
        duplicates.setdefault(digest, []).append(identifier)
        paths[identifier] = destination
        mapping.append({"staging_path": path, "library_path": destination, "sha256": digest})
    write(records / "file-map.csv", ["staging_path", "library_path", "sha256"], mapping)
    duplicate_ids = {identifier for group in duplicates.values() if len(group) > 1 for identifier in group}
    listing = [[label_for(key) for key in DOCUMENT_FIELDS]]
    pending = [[label_for(key) for key in PENDING_FIELDS]]
    sites = [[label_for(key) for key in SOURCE_FIELDS]]
    complete_ids = set()
    partial_count = 0
    for row in catalog:
        identifier = row["id"]
        review = evidence.get(identifier, {})
        receipt = receipts.get(identifier, {})
        local = paths.get(identifier, "")
        state, parser_reason = checks.get(identifier, ("", ""))
        access = access_state(local, row["sha256"], review, receipt) if state != "invalid" else PENDING
        if access in SAVED:
            complete_ids.add(identifier)
        if access == PARTIAL:
            partial_count += 1
        flags = []
        if state == "invalid":
            flags.append(label_for("invalid_file").format(reason=parser_reason))
        elif local and access == PENDING:
            flags.append(label_for("review_file"))
        if identifier in duplicate_ids:
            flags.append(label_for("duplicate"))
        if access not in SAVED:
            notes = labels.get("issues", {}).get(identifier, {})
            flags.append(text(notes, lang, receipt.get("reason") or row["missing_reason"] or
                              review.get("body_locator") or row["evidence"]))
        reason = " ".join(filter(None, flags))
        verification = row["verification"] or "pending"
        verified_label = label_for("pending_status" if verification == "pending" else verification)
        name = row["original_title"] or row["title"]
        title = name if config.get("preserve_original_title", True) else ""
        translation = working_title(labels, identifier, config, lang, row["english_title"])
        entry = primary.get(identifier, {})
        category = entry.get("primary_category", row["category"])
        category_label = text(categories.get(category), lang, label_for(category))
        themes, settings, _ = tags.get(identifier, ([], [], {}))
        theme_label = " | ".join(text(profile["themes"][code], lang, code) for code in themes)
        setting_label = " | ".join(text(profile["settings"][code], lang, code) for code in settings)
        remarks = " ".join(filter(None, [entry.get("remarks"), reason]))
        listing.append([identifier, title, translation, row["creator"], entry.get("publication_date") or row["year"],
                        category_label, theme_label, setting_label, label_for(row["category"]),
                        " ".join(filter(None, (row["identifier_series"], row["document_number"]))), row["doi"],
                        row["language"], row["source_url"], local, label_for(access), verified_label,
                        row["retrieved_on"], remarks])
        if access not in SAVED or reason or verification != "verified":
            pending.append([identifier, title, translation, label_for(access), verified_label,
                            reason or label_for("unverified"), receipt.get("evidence_url") or row["source_url"]])
    for row in sources:
        sites.append([row["institution"], row["url"], label_for(row["data_type"]), row["authority"],
                      row["languages"], row["limitations"], row["verified_on"],
                      label_for("pending_status" if row["status"] == "pending" else row["status"]),
                      row["evidence_url"]])
    if profile:
        matrix = coverage(profile, {row["id"]: tags[row["id"]] for row in catalog}, backend, complete_ids)
        if matrix:
            write(records / "profile-coverage.csv", list(matrix[0]), matrix)

    jurisdiction = filename_part(text(labels.get("country"), lang, config["country"]), "Jurisdiction", 72)
    description = label_for("counts").format(total=len(catalog), complete=len(complete_ids),
                                            partial=partial_count, missing=len(catalog) - len(mapping))
    languages = config.get("search_languages", config.get("languages", []))
    summary = [f"# {jurisdiction} · {label_for('summary')}", "",
               f"**{label_for('topic')}** {text(labels.get('topic'), lang, config['topic'])}",
               f"**{label_for('scope')}** {text(labels.get('scope'), lang, config.get('research_scope', ''))}",
               f"**{label_for('search_languages')}** {', '.join(languages)}",
               f"**{label_for('cutoff')}** {config.get('search_cutoff') or '—'}",
               f"**{label_for('retrieved')}** {', '.join(sorted({r['retrieved_on'] for r in catalog if r['retrieved_on']})) or '—'}",
               "", description, "",
               f"## {label_for('gaps')}", "", *[f"- {text(gap, lang)}" for gap in labels.get("gaps", [])],
               "", label_for("details"), "", text(labels.get("note"), lang), ""]
    (stage / (folder("summary", lang) + ".md")).write_text("\n".join(summary), encoding="utf-8")
    return f"{jurisdiction}_{folder('workbook', lang)}.xlsx", {
        folder("catalog", lang): listing, folder("pending", lang): pending, folder("sources", lang): sites}


def optional_index(root, name):
    path = root / name
    if not path.is_file():
        return {}
    rows = read(path)
    result = {row["id"]: row for row in rows}
    if len(result) != len(rows):
        raise ValueError(f"Duplicate record IDs in {name}")
    return result


def working_title(labels, identifier, config, lang, english_title):
    if not config.get("translate_title", True):
        return ""
    value = labels.get("titles", {}).get(identifier, {})
    if isinstance(value, str):
        return value
    combined = {"en": english_title, **value}
    if lang == "bilingual":
        return text(combined, lang)
    return combined.get(lang, "")


def export(workbook_path, sheets):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    workbook = Workbook()
    workbook.remove(workbook.active)
    for name, rows in sheets.items():
        sheet = workbook.create_sheet(name)
        for values in rows:
            sheet.append(values)
            for cell in sheet[sheet.max_row]:
                if cell.data_type == "f":
                    cell.data_type = "s"
                cell.alignment = Alignment(wrap_text=True, vertical="top")
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for cell in sheet[1]:
            cell.fill = PatternFill("solid", fgColor="16465A")
            cell.font = Font(color="FFFFFF", bold=True)
            sheet.column_dimensions[get_column_letter(cell.column)].width = 42 if len(cell.value) > 12 else 23
    workbook.save(workbook_path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--labels", type=Path)
    parser.add_argument("--output-language", choices=("en", "zh-CN", "bilingual"))
    parser.add_argument("--update", action="store_true")
    args = parser.parse_args()
    run, output = args.run.resolve(), args.output.resolve()
    if output.is_relative_to(run) or run.is_relative_to(output):
        parser.error("Input and output directories must be independent")
    if args.update != output.is_dir() or (not args.update and output.exists()):
        parser.error("Use --update only for an existing formal library")
    backend, _ = read_snapshot(run)
    labels_path = args.labels or backend / "presentation.json"
    labels = json.loads(labels_path.read_text(encoding="utf-8")) if labels_path.is_file() else {}
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".delivery-", dir=output.parent) as temporary:
        stage = Path(temporary) / "result"
        stage.mkdir()
        name, sheets = prepare(run, stage, labels, args.output_language)
        workbook = stage / name
        export(workbook, sheets)
        add_links(workbook, sheets, stage)
        verify_links(workbook, sheets, stage)
        if args.update:
            replace_library(stage, output)
        else:
            stage.rename(output)


if __name__ == "__main__":
    main()
