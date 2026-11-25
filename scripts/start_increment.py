"""Start a separate staging snapshot from an existing delivery or legacy run."""
import argparse
import shutil
import tempfile
from pathlib import Path

from catalog import read
from package_delivery import file_hash, read_snapshot


def start(baseline, target):
    baseline, target = baseline.resolve(), target.resolve()
    if target.exists() or target.is_relative_to(baseline):
        raise ValueError("Incremental staging requires a new directory outside the baseline")
    backend, paths = read_snapshot(baseline)
    recorded = {r["download_path"]: r["sha256"] for r in read(backend / "catalog.csv")
                if r["download_path"]}
    loaded = {r["download_path"] for r in read(backend / "candidates.csv") if r["download_path"]}
    if loaded - paths.keys():
        raise ValueError("Some registered files are missing; audit the baseline before staging")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".increment-", dir=target.parent) as temporary:
        stage = Path(temporary) / "stage"
        stage.mkdir()
        (stage / "downloads").mkdir()
        for item in backend.iterdir():
            if item.is_file() and item.name != ".DS_Store":
                shutil.copy2(item, stage / item.name)
        if backend != baseline:
            for book in baseline.glob("*.xlsx"):
                shutil.copy2(book, stage / ("prior-" + book.name))
        for original, stored in paths.items():
            destination = (stage / original).resolve()
            if not destination.is_relative_to(stage / "downloads") or not stored.is_file():
                raise ValueError(f"Invalid original attachment path {original}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(stored, destination)
            if recorded.get(original) and file_hash(destination) != recorded[original]:
                raise ValueError(f"Attachment differs from recorded hash {original}")
        if target.exists():
            raise FileExistsError(target)
        stage.rename(target)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    start(args.baseline, args.target)
