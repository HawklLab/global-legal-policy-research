# Research profile template

Copy this file to `<profile-id>.md` in your local staging directory. Change the ID and select dimensions and categories appropriate to the question. This template is illustrative and is never loaded automatically.

```json profile
{
  "id": "template",
  "name": {"en": "Research topic", "zh-CN": "研究主题"},
  "topic": "Policy instruments for the chosen research problem",
  "objectives": ["Trace document provenance and implementation history"],
  "questions": ["What instruments, preparatory documents and evaluations can be verified?"],
  "jurisdictions": [],
  "time_range": {"from": "", "to": ""},
  "search_languages": [],
  "keywords": {"en": ["legislative proposal", "public consultation"], "local": []},
  "synonyms": {},
  "priority_sources": ["official gazette", "legislature", "consultation portal"],
  "primary_categories": {
    "instruments": {"en": "Policy instruments", "zh-CN": "政策工具"},
    "evidence": {"en": "Implementation evidence", "zh-CN": "实施证据"}
  },
  "themes": {"design": {"en": "Design", "zh-CN": "制度设计"}, "review": {"en": "Review", "zh-CN": "评估"}},
  "priority": ["design"],
  "settings": {},
  "include": ["Documents directly relevant to a research question with identifiable provenance"],
  "exclude": ["Site navigation, duplicate manifestations and unrelated material"],
  "full_text_priority": ["instruments", "evidence"],
  "coverage_requirements": ["Trace the legislative history and key cited sources"],
  "stop_conditions": ["Search the relevant official sources and document remaining high-priority gaps"]
}
```

Fields such as keywords and stop conditions guide the executing agent. Categories, theme and dimension codes, priority coverage and retrieval order are also consumed by the local tools. Profiles never override verification, access or privacy safeguards.
