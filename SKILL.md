---
name: global-legal-policy-research
description: Discover, verify and organize legal and policy sources across jurisdictions. Use for official source mapping, multilingual documentary research, legislative history, evidence audits and retrieval of missing full texts.
---

# Global legal and policy research

Support English and Chinese requests. Use the user's conversation language for the response and default presentation, unless they select another output language. Accept jurisdiction, research question, scope, publication date range, search cutoff, optional research profile and mode. Record the actual retrieval language in `search_languages`. Default to English plus the relevant official research languages, verified for the jurisdiction and document coverage. Store `output_language` as `en`, `zh-CN` or `bilingual`, independently of query language. Store both the original metadata and any working title translations. Set `preserve_original_title` (default true) and `translate_title` (default true if translations are supplied). Use `user_language` as the fallback for output in non-interactive runs. Match the final response to the output language, or provide both versions for bilingual output.

## Choose a mode

- **Discovery**: map official sources, build search terms in each relevant language, run searches and record what actually executed.
- **Collection**: resolve candidate metadata, retrieve authorized originals, verify evidence and build the catalogue.
- **Audit**: review existing sources, files, version relations and coverage. Resume only material gaps.
- **Full-text Retrieval**: inventory what already exists and target existing records without full text. Avoid a new thematic search.

Read [workflow](references/workflow.md) for source discovery, journal and stopping criteria. Read [records and retrieval](references/records.md) for evidence, versions, attachment safeguards and output.

## Custom profiles

Use an explicitly named profile when provided. For a sufficiently clear natural-language request, copy [the template](profiles/template.md), assign stable category, theme and optional dimension codes, then write a local profile for the requested scope. Confirm scope and classification when a material research boundary is uncertain. With no profile, use the general documentary categories and coverage checks. Never infer one jurisdiction's institutions or vocabulary from another. Persist the profile in staging and set its ID in `run.json`.

Keep one formal library per stable jurisdiction and topic. Re-render the same snapshot to change presentation language. Put individual documents in the catalogue and their open acquisition or verification issues in the pending sheet. Summarize coverage gaps in the research notes and retain detailed evidence and tasks in the backend. Follow access restrictions and keep working data out of the release repository.
