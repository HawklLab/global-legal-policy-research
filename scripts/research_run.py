"""Initialize, collect, audit or prioritize full text from a local research run."""
import argparse
import json
import re
import shutil
from pathlib import Path

from audit_research import audit
from catalog import ASSETS, build, read, write
from fulltext_status import SAVED, access_state
from package_delivery import read_snapshot
from research_profile import load_profile

MODES = ("discovery", "collection", "audit", "full-text-retrieval")


def run_mode(mode, root, output=None, config=None, baseline=None):
    root = root.resolve()
    if mode == "discovery":
        if root.exists():
            raise FileExistsError(root)
        settings = json.loads(config.read_text(encoding="utf-8"))
        if not all(settings.get(key) for key in ("country", "topic", "search_languages")):
            raise ValueError("A jurisdiction, topic and verified search languages are required")
        profile = settings.get("research_profile")
        if profile:
            if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", profile):
                raise ValueError("Invalid research profile identifier")
            load_profile(profile, config.parent) if (config.parent / (profile + ".md")).is_file() else load_profile(profile)
        settings["mode"] = mode
        root.mkdir(parents=True)
        (root / "downloads").mkdir()
        for template in ASSETS.glob("*.csv"):
            shutil.copy2(template, root / template.name)
        if profile and (config.parent / (profile + ".md")).is_file():
            shutil.copy2(config.parent / (profile + ".md"), root / (profile + ".md"))
        (root / "run.json").write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    elif mode == "collection":
        if read_snapshot(root)[0] != root:
            raise ValueError("Create a staging snapshot before collection")
        build(root, baseline, True)
    elif mode in ("audit", "full-text-retrieval"):
        backend, _ = read_snapshot(root)
        settings = json.loads((backend / "run.json").read_text(encoding="utf-8"))
        audit(root, output, cutoff=settings.get("search_cutoff"))
        if mode == "full-text-retrieval":
            rows = read(output / "verification-audit.csv")
            catalogue = {r["id"]: r for r in read(backend / "catalog.csv")}
            evidence_path = backend / "verification-evidence.csv"
            evidence = {r["id"]: r for r in read(evidence_path)} if evidence_path.is_file() else {}
            receipt_path = backend / "fulltext-review.csv"
            receipts = {r["id"]: r for r in read(receipt_path)} if receipt_path.is_file() else {}
            profile_id = settings.get("research_profile")
            profile = (load_profile(profile_id, backend) if (backend / (profile_id + ".md")).is_file()
                       else load_profile(profile_id)) if profile_id else {}
            priority = {code: i for i, code in enumerate(profile.get("full_text_priority", []))}
            classification_path = backend / "profile-classification.csv"
            classifications = {r["id"]: r.get("primary_category") for r in read(classification_path)
                               } if classification_path.is_file() else {}
            queue = []
            for check in rows:
                identifier = check["id"]
                row = catalogue[identifier]
                state = access_state(row["download_path"], check["sha256"], evidence.get(identifier, {}),
                                     receipts.get(identifier, {}))
                if state in SAVED and check["status"] == "source_verified_fulltext":
                    continue
                queue.append({"id": identifier, "source_url": row["source_url"], "doi": row["doi"],
                              "access_status": state, "next_step": check["next_step"]})
            queue.sort(key=lambda r: priority.get(classifications.get(r["id"]) or catalogue[r["id"]]["category"],
                                                  len(priority)))
            write(output / "retrieval-queue.csv", ["id", "source_url", "doi", "access_status", "next_step"], queue)
    else:
        raise ValueError(f"Unknown research mode: {mode}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=MODES)
    parser.add_argument("root", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--baseline", type=Path)
    args = parser.parse_args()
    if args.mode == "discovery" and not args.config:
        parser.error("discovery requires --config")
    if args.mode in ("audit", "full-text-retrieval") and not args.output:
        parser.error("local review requires a new --output directory")
    run_mode(args.mode, args.root, args.output, args.config, args.baseline)
