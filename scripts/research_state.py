"""Persist search checkpoints and reusable, evidence-backed source observations."""
import argparse
import hashlib
import json
import re
import sqlite3
from contextlib import closing
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

TASK_STATES = {"planned", "running", "executed", "blocked", "failed"}
SOURCE_STATES = {"verified", "pending", "access_limited", "changed", "dead"}
COVERAGE = dict(zip("ABCDEFGH", (
    "Law and amendments", "Preparatory documents", "Legislative proceedings", "International sources", "Advocacy",
    "Implementation and official statistics", "Scholarship", "Case law and application",
)))


def timestamp(value):
    value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.utcoffset() is None:
        raise ValueError("Event time requires a timezone")
    return value


def web_url(value):
    parsed = urlsplit(value)
    return parsed.scheme in {"https", "http"} and bool(parsed.hostname) and not parsed.username


def key(payload, fields):
    text = json.dumps([payload[field] for field in fields], ensure_ascii=False)
    return hashlib.sha256(text.encode()).hexdigest()[:24]


def validate(event):
    kind = event["kind"]
    when = timestamp(event["at"])
    if not re.fullmatch(r"[A-Z]{2,3}", event["country"]):
        raise ValueError("Use a stable uppercase country code")
    if kind == "search":
        task = ("country", "layer", "database", "query", "language", "scope")
        if any(not str(event[k]).strip() for k in task):
            raise ValueError("Empty search identity")
        cats = event["categories"]
        if event["layer"] not in range(1, 6) or not cats or set(cats) - COVERAGE.keys():
            raise ValueError("Search needs layer 1–5 and one or more A–H categories")
        state = event["state"]
        if state not in TASK_STATES:
            raise ValueError("Invalid search state")
        if state == "executed":
            count = event["result_count"]
            if (count is not None and (type(count) is not int or count < 0)
                    or not event["count_basis"] or not event["evidence"]):
                raise ValueError("Executed search needs evidence and count basis")
        if state in {"blocked", "failed"} and not event["evidence"]:
            raise ValueError("Blocked or failed search needs a reason")
        return key(event, task), when
    if kind != "source" or event["status"] not in SOURCE_STATES:
        raise ValueError("Invalid event kind or source state")
    for field in ("source_id", "name", "operator", "url", "role", "coverage", "languages",
                  "free_access", "full_text_search", "formats", "ownership_url", "function_url"):
        if field not in event:
            raise ValueError(f"Missing source field {field}")
    if not event["source_id"] or not event["name"]:
        raise ValueError("Source requires a stable ID and a name")
    if event["status"] == "verified" and (
        not event["operator"] or not event["coverage"]
        or not all(web_url(event[field]) for field in ("url", "ownership_url", "function_url"))
    ):
        raise ValueError("Verified source needs ownership and function evidence")
    if event["free_access"] not in {"yes", "no", "partial", "unknown"} or event[
        "full_text_search"
    ] not in {"yes", "no", "partial", "unknown"}:
        raise ValueError("Invalid source access capability")
    return key(event, ("country", "source_id")), when


def record(journal, event):
    event_id, when = validate(event)
    payload = json.dumps(event, ensure_ascii=False, sort_keys=True)
    with closing(sqlite3.connect(journal)) as db, db:
        with db:
            db.execute("""CREATE TABLE IF NOT EXISTS events (
                seq INTEGER PRIMARY KEY, kind TEXT, country TEXT, task TEXT, at TEXT,
                payload TEXT UNIQUE)""")
            db.execute("INSERT OR IGNORE INTO events (kind,country,task,at,payload) VALUES (?,?,?,?,?)",
                       (event["kind"], event["country"], event_id,
                        when.astimezone(timezone.utc).isoformat(), payload))


def history(journal, kind=None, country=None):
    if not journal.is_file():
        return []
    with closing(sqlite3.connect(journal.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        rows = db.execute("""SELECT task, payload FROM events
            WHERE (? IS NULL OR kind=?) AND (? IS NULL OR country=?) ORDER BY at,seq""",
                          (kind, kind, country, country))
        return [(task, json.loads(payload)) for task, payload in rows]


def latest(journal, kind, country=None):
    return dict(history(journal, kind, country))


def resume(journal, country=None):
    events = history(journal, "search", country)
    counts = {}
    tasks = dict(events)
    for identifier, event in events:
        if event["state"] in {"failed", "blocked"}:
            counts[identifier] = counts.get(identifier, 0) + 1
    return [dict(event, task_id=identifier,
                 disposition="manual_review" if event["state"] == "blocked" or counts.get(identifier, 0) >= 2
                 else "pending")
            for identifier, event in tasks.items() if event["state"] != "executed"]


def cutoff_label(checked, cutoff):
    if not cutoff or not checked:
        return ""
    actual = date.fromisoformat(checked[:10])
    return "post_cutoff_check" if actual > date.fromisoformat(cutoff) else "within_cutoff"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("journal", type=Path)
    parser.add_argument("action", choices=["record", "history", "sources", "resume"])
    parser.add_argument("--input", type=Path)
    parser.add_argument("--country")
    args = parser.parse_args()
    if args.action == "record":
        if not args.input:
            parser.error("record requires --input")
        data = json.loads(args.input.read_text(encoding="utf-8"))
        for event in data if isinstance(data, list) else [data]:
            record(args.journal, event)
        return
    if args.action == "sources":
        result = list(latest(args.journal, "source", args.country).values())
    elif args.action == "resume":
        result = resume(args.journal, args.country)
    else:
        result = [event for _, event in history(args.journal, country=args.country)]
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
