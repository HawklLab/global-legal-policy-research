# Global Legal & Policy Research Skill

[简体中文](README_CN.md) · [HawkLab](https://github.com/HawkLab) · [Releases](https://github.com/HawkLab/global-legal-policy-research/releases)

A Codex skill for building traceable research libraries across jurisdictions. Use it to map official sources, search in relevant languages, trace legislative history and advocacy, retrieve originals, audit evidence, and publish a local catalogue. Developed independently by HawkLab. The project does not represent any institution or international organization.

## Workflow and modes

| Mode | Typical request | Local command |
| --- | --- | --- |
| Discovery | Find official sources and map a new question | `research_run.py discovery RUN --config CONFIG` |
| Collection | Verify candidates and catalogue acquired originals | `research_run.py collection RUN` |
| Audit | Check source, version, attachment and coverage evidence | `research_run.py audit RUN --output CHECKS` |
| Full-text Retrieval | Recover missing originals from an existing catalogue | `research_run.py full-text-retrieval RUN --output QUEUE` |

Commands above are relative to `scripts/` and run with Python. Discovery prepares the local run. Codex executes live discovery, search and download steps with the browsing tools available to it. The local tools maintain templates, a jurisdictional source registry, a resumable search journal, verification evidence, citation and version relationships, and a retrieval queue. See [workflow](references/workflow.md) and [record formats](references/records.md).

## Installation

Requires Python 3.9+ and [openpyxl](https://openpyxl.readthedocs.io/). Poppler's `pdfinfo` and `pdftotext` are optional for automatic PDF checks. Scans and non-text media still require manual evidence.

From a local checkout, use an empty destination:

```sh
skill_dir="${CODEX_HOME:-$HOME/.codex}/skills/global-legal-policy-research"
mkdir -p "$(dirname "$skill_dir")"
mkdir "$skill_dir" && git archive HEAD | tar -x -C "$skill_dir"
python3 -m pip install -r requirements.txt
```

Install the tagged release from the [GitHub repository](https://github.com/HawkLab/global-legal-policy-research). Use an unused destination or name when keeping another installation.

```sh
python3 "${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-installer/scripts/install-skill-from-github.py" \
  --repo HawkLab/global-legal-policy-research --path . --name global-legal-policy-research --ref v0.1.0 --method download
```

Install the Python requirements from the installed folder, then restart Codex or begin a session that discovers the installed skill. The live GitHub command requires a reachable published repository.

## Example

Tell Codex: “Use `$global-legal-policy-research` to discover primary sources for EU Regulation 2024/1689, including the legislative procedure. Search in English and German for these documents. Produce a bilingual catalogue.” Start with the [official act on EUR-Lex](https://eur-lex.europa.eu/eli/reg/2024/1689/oj) and use its procedure link for the legislative file. The example is a small workflow illustration and does not include a research dataset.

```json
{
  "country": "EU",
  "topic": "Artificial intelligence regulation",
  "research_scope": "Adopted regulation and preparatory documents",
  "search_languages": ["en", "de"],
  "output_language": "bilingual",
  "preserve_original_title": true,
  "translate_title": true
}
```

The example limits queries to two languages. For a general run, ask Codex to verify the relevant official languages and include English. When presentation language is omitted, Codex follows the user's conversation language and writes `user_language`; the CLI defaults to English if neither setting is present. Use `en`, `zh-CN` or `bilingual`. Working translations are supplemental. Keep original metadata in the backend even when hiding the original-title display column values with `preserve_original_title: false`.

## Profiles and localized delivery

Use a profile by ID, ask Codex to create one from a clear scope, or omit it for general coverage and document types. Copy [the template](profiles/template.md) to a local `<id>.md` next to the run config or into staging, put that ID in `research_profile`, and use stable codes in the [classification table](references/records.md). Put only material research-boundary decisions to the user. Profiles define the scope, languages, priorities, custom categories, themes, dimensions, inclusion and stopping criteria. They preserve core evidence and access rules.

Supply localized titles and prose in staging `presentation.json`. Values may use `{"en": "...", "zh-CN": "..."}`. Supported fields include `country`, `topic`, `scope`, `titles` and `issues` (keyed by record ID), `gaps` (a list) and `note`. Titles are added only when supplied or already recorded as English title metadata. Original author or publisher names, original source URLs, legal identifiers and DOIs remain intact. User-supplied prose appears as entered when no matching translation is available.

One stable output directory per jurisdiction and topic contains one workbook, an originals directory, research notes and backend records, with localized names. The workbook has three sheets for the catalogue, record-level issues and sources. Keep the outer destination path stable across languages. Re-render an existing snapshot through a sibling staging directory to replace its presentation:

```sh
python3 scripts/start_increment.py outputs/eu-ai work/eu-ai
python3 scripts/package_delivery.py work/eu-ai outputs/eu-ai --update --output-language en
```

No search or download is involved in re-rendering. Preserve human edits by carrying them back into staging or presentation fields before publishing updates.

## Limitations and contributing

Live tools, network access, jurisdictional search coverage and licensing vary. Dynamic registries, paywalls, digitized archives and scanned or audiovisual files may require user-reviewed evidence or remain inaccessible. The CLI never logs in or crawls sites by itself. The catalogue is an evidence-management aid, not a comprehensive statement of the law or legal advice.

Run `python3 -m unittest discover -s scripts -v`. Submit minimal reproducible examples with synthetic or appropriately authorized public metadata. Keep private records, raw downloads, credentials and unpublished materials outside the repository. See [license](LICENSE) and [dependency notes](THIRD_PARTY.md).
