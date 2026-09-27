# SkillUp — SIH 2026 Evidence-first Labour Market Intelligence Prototype

**Problem Statement:** SIH26134 — Challenges in aligning skill development programs with industry requirements and emerging job market demands.

This package is a deliberately focused screening prototype. The goal is one believable decision journey rather than many unrelated dashboards:

**District → Sector → Job demand → AI skill extraction → Skill normalization → Curriculum evidence → Gap → Evidence → Recommendation → What-if → Refresh**

## What is included

- Responsive React + Vite frontend with clean GovTech/SaaS-style UI.
- FastAPI backend with SQLite persistence.
- District selection: Pune / Nashik.
- Sector and role filtering across the demand analysis.
- Transparent demo/seed job dataset for offline demonstration. Seed records are never labelled as live.
- Incremental NCS collection adapter using Playwright, subject to the source's access/usage conditions.
- Groq-assisted skill extraction when `GROQ_API_KEY` is present; deterministic evidence matcher otherwise.
- Canonical skill normalization and raw-variant display.
- Government course catalogue dataset and separate government baseline context.
- Curriculum PDF upload with text extraction, explicit skill evidence, page-level evidence snippets, and syllabus library.
- Skill gap calculation with a visible deterministic gap score.
- Evidence drawer linking job evidence, curriculum evidence, and employer validation.
- Recommendation / Curriculum Change Studio with `PROPOSED` state.
- Deterministic What-if curriculum simulator.
- Posting trend chart and demand charts.
- Live refresh modal with new/updated/skipped counters.
- Windows daily refresh task helper.

## Run locally on Windows

### 1) Backend

```cmd
cd backend
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m playwright install chromium
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Optional AI extraction for new/changed postings and curriculum PDFs:

```cmd
set GROQ_API_KEY=YOUR_KEY
```

### 2) Frontend

```cmd
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

## Demo flow

1. Select **Pune** and **Automotive**.
2. Open **Market demand** to see posting share and normalized competencies.
3. Click a skill such as **EV Diagnostics** to open the evidence layer.
4. Open **Curriculum** and upload the official syllabus PDF you want to analyse.
5. Return to **Skill gaps**. The curriculum evidence can change from `Not evidenced` to `Covered` when explicit text evidence is found.
6. Open **Recommendations**, choose a gap, draft a learning outcome/practical/assessment/equipment proposal and save it as `PROPOSED`.
7. Open **What-if**, add a competency and recalculate the deterministic alignment scenario.
8. Open **Data & refresh** and run the market refresh. Live records are stored separately from demo seed records.

## Daily refresh

Run a one-off refresh:

```cmd
python scripts\run_sync.py
```

Register the Windows Task Scheduler job:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\register_windows_task.ps1 -District Pune -Time 09:00
```

The refresh path is incremental: existing unchanged jobs are skipped before AI extraction; new/changed jobs are processed, normalized and used for demand/gap recalculation.

## Evidence discipline

- Government projections are planning context, not current job-posting counts.
- Demand percentages are shares of the analysed posting dataset.
- `Not evidenced` means explicit curriculum evidence was not found in the available catalogue/PDFs; it is not proof that an official course lacks the skill.
- AI proposes; humans validate and approve curriculum changes.
- The collector does not bypass login, CAPTCHA, paywalls or access controls.
- Scanned image-only PDFs may need OCR in a future iteration.

## Important live-source limitation

The live collector is implemented and diagnostics are included, but live network access could not be validated inside this build environment. Before the SIH demo, run one refresh from the target Windows machine and confirm that the current NCS page structure and access conditions permit the collection flow.
