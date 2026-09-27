# SkillUp architecture

```text
Permitted labour-market sources
        ↓
Incremental collection layer
        ↓
Deduplication / description hash
        ↓
AI skill extraction (Groq) or deterministic fallback
        ↓
Canonical skill normalization
        ↓
District × Sector × Role demand dataset
        ↓                         ↓
Government planning context    Curriculum catalogue / PDFs
        ↓                         ↓
        └──────────── Evidence-backed gap engine ────────────┐
                                                               ↓
                                             Evidence layer / explain why
                                                               ↓
                                          Recommendation (PROPOSED)
                                                               ↓
                                           Employer / human review
                                                               ↓
                                            What-if scenario analysis
                                                               ↑
                                         New market refresh cycles
```

## Data boundaries

**Current market evidence:** analysed job postings, dates, source URL, location, role, description and extracted competencies.

**Government baseline:** district/sector planning context from official research assets. Kept separate from current market counts.

**Curriculum evidence:** imported course catalogue plus uploaded syllabus text. Explicit evidence is stored by skill and PDF page where available.

**Action layer:** editable recommendation objects; status remains `PROPOSED` until a human workflow is applied.

## Refresh mechanism

A refresh creates a run record, collects new/changed postings, uses a stable ID + description hash for deduplication, extracts only new/changed skills, writes the record to SQLite, and refreshes downstream demand/gap intelligence.

A Windows Scheduled Task can invoke the same endpoint daily.
