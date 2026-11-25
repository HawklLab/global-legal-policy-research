"""Load a topic profile and measure evidence by theme and setting."""
import json
import re
from pathlib import Path
from catalog import read

PROFILES = Path(__file__).resolve().parents[1] / "profiles"


def load_profile(name, directory=PROFILES):
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
        raise ValueError("Invalid research profile identifier")
    text = (directory / (name + ".md")).read_text(encoding="utf-8")
    block = re.search(r"(?ms)^```json profile\s*\n(.*?)^```\s*$", text)
    if not block:
        raise ValueError(f"Missing profile configuration: {name}")
    profile = json.loads(block[1])
    if profile["id"] != name or not set(profile["priority"]) <= profile["themes"].keys():
        raise ValueError(f"Inconsistent profile: {name}")
    for field in ("primary_categories", "themes", "settings"):
        codes = profile.get(field, {})
        if not isinstance(codes, dict) or any(not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]*", code)
                                               for code in codes):
            raise ValueError(f"Invalid {field} codes: {name}")
    return profile


def split_tags(value, allowed):
    tags = [tag.strip() for tag in value.split("|") if tag.strip()]
    if len(tags) != len(set(tags)) or set(tags) - allowed.keys():
        raise ValueError(f"Unknown or repeated profile tags: {value}")
    return tags


def classify(profile, root, catalog):
    classifications = {}
    expected = {row["id"] for row in catalog}
    for row in read(root / "profile-classification.csv"):
        identifier = row["id"]
        themes = split_tags(row["themes"], profile["themes"])
        settings = split_tags(row["settings"], profile["settings"])
        if identifier not in expected or identifier in classifications or (profile["themes"] and not themes) or not row["evidence"].strip():
            raise ValueError(f"Invalid classification or missing evidence: {identifier}")
        pairs = {}
        for entry in row.get("theme_settings", "").split(";"):
            if not entry.strip():
                continue
            theme, separator, scoped = entry.partition("=")
            if not separator or theme not in themes or theme in pairs:
                raise ValueError(f"Invalid theme–setting assignment: {identifier} {entry}")
            values = split_tags(scoped, profile["settings"])
            if not set(values) <= set(settings):
                raise ValueError(f"Theme-setting assignment exceeds row scope: {identifier}")
            pairs[theme] = values
        if len(themes) == 1 and settings and not pairs:
            pairs[themes[0]] = settings
        if set(settings) != {value for values in pairs.values() for value in values}:
            raise ValueError(f"Every setting needs an explicit theme link: {identifier}")
        classifications[identifier] = themes, settings, pairs
    if expected - classifications.keys():
        raise ValueError(f"Unclassified catalogue records: {sorted(expected - classifications.keys())}")
    return classifications


def primary_metadata(profile, root, catalog):
    categories = profile.get("primary_categories")
    if not categories:
        return {}
    expected = {row["id"] for row in catalog}
    rows = {row["id"]: row for row in read(root / "profile-classification.csv")}
    for identifier in sorted(expected):
        category = rows.get(identifier, {}).get("primary_category", "")
        if category not in categories:
            raise ValueError(f"Select one primary category for {identifier}: {category}")
    return rows


def coverage(profile, classifications, root, complete_ids):
    checks = {}
    path = root / "profile-search.csv"
    if path.is_file():
        for row in read(path):
            pair = row["theme"], row["setting"]
            if (pair[0] not in profile["themes"] or (pair[1] and pair[1] not in profile["settings"])
                    or row["status"] not in {"executed", "blocked"} or not row["evidence"].strip()
                    or pair in checks):
                raise ValueError(f"Invalid profile search record: {pair}")
            checks[pair] = row
    results = []
    for theme, description in profile["themes"].items():
        theme_rows = {identifier: pairs.get(theme, [])
                      for identifier, (themes, settings, pairs) in classifications.items() if theme in themes}
        for setting in [*profile["settings"], ""]:
            hits = {identifier for identifier, settings in theme_rows.items()
                    if not setting or setting in settings}
            observation = checks.get((theme, setting), {})
            state = observation.get("status", "")
            results.append({
                "theme": theme, "theme_label": json.dumps(description, ensure_ascii=False) if isinstance(description, dict) else description, "priority": "yes" if theme in profile["priority"] else "",
                "dimension": setting, "documents": len(hits), "complete": len(hits & complete_ids),
                "incomplete": len(hits - complete_ids),
                "search_status": {"executed": "executed", "blocked": "blocked"}.get(state, "not_recorded"),
                "coverage_status": ("has_fulltext" if hits & complete_ids else "has_records" if hits else
                               "no_records_after_search" if state == "executed" else "no_records"),
                "evidence": observation.get("evidence", ""), "record_ids": "|".join(sorted(hits))
            })
    return results
