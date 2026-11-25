"""Publish into a single formal library and retain one compact change backup."""
import json
import os
import tempfile
from pathlib import Path
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from catalog import read


BACKUP = "last-backup.zip"


def identity(backend):
    params = json.loads((backend / "run.json").read_text(encoding="utf-8"))
    return params["country"], params.get("research_profile") or params["topic"]


def replace_library(stage, library):
    from package_delivery import file_hash, library_folders

    previous, originals = library_folders(library)
    incoming, _ = library_folders(stage)
    if identity(previous) != identity(incoming):
        raise ValueError("Country and research topic must match the formal library")
    from locales import folders

    listed = {previous.name, originals.name, ".DS_Store"}
    listed |= {name + ".md" for name in folders("summary")}
    books = [path for path in library.glob("*.xlsx") if any(
        path.stem.endswith("_" + suffix) for suffix in folders("workbook"))]
    if len(books) != 1:
        raise ValueError("Expected exactly one formal catalogue workbook")
    listed.add(books[0].name)
    if {p.name for p in library.iterdir()} - listed:
        raise ValueError("Unmanaged top-level files need reconciliation before update")
    if {r["id"] for r in read(previous / "candidates.csv")} - {
        r["id"] for r in read(incoming / "candidates.csv")
    }:
        raise ValueError("Staging omitted existing candidates; reconcile before updating")
    mapped = {r["library_path"]: r["sha256"] for r in read(previous / "file-map.csv")}
    untracked = {p.relative_to(library).as_posix() for p in originals.rglob("*")
                 if p.is_file() and p.name != ".DS_Store"} - mapped.keys()
    new_hashes = {r["sha256"] for r in read(incoming / "file-map.csv")}
    if untracked:
        unresolved = [value for value in sorted(untracked) if file_hash(library / value) not in new_hashes]
        if unresolved:
            raise ValueError(f"Unmanaged attachments need reconciliation: {unresolved}")
    for path in previous.iterdir():
        if not path.is_file() and not (incoming / path.name).exists():
            raise ValueError(f"Existing backend directory was not carried forward: {path.name}")
    with ZipFile(incoming / BACKUP, "w", ZIP_DEFLATED) as backup:
        for path in library.iterdir():
            if path.is_file() and path.name != ".DS_Store":
                backup.write(path, path.name)
        for path in previous.iterdir():
            updated = incoming / path.name
            if path.is_file() and path.name not in {BACKUP, ".DS_Store"} and (
                    not updated.is_file() or path.read_bytes() != updated.read_bytes()):
                backup.write(path, f"{previous.name}/{path.name}")
        for value, digest in mapped.items():
            if digest not in new_hashes:
                backup.write(library / value, value)
    with tempfile.TemporaryDirectory(prefix=".rollback-", dir=library.parent) as temporary:
        displaced = Path(temporary) / "previous"
        os.rename(library, displaced)
        try:
            os.rename(stage, library)
        except BaseException:
            os.rename(displaced, library)
            raise
