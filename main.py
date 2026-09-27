from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import sqlite3
import uuid
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
STORAGE_DIR = ROOT / "storage"
UPLOAD_DIR = ROOT / "backend" / "uploads"
DB_PATH = STORAGE_DIR / "skillup.db"
CATALOG_PATH = DATA_DIR / "course_catalogue.csv"
BASELINE_PATH = DATA_DIR / "government_baseline_pune.csv"
DEMO_JOBS_PATH = DATA_DIR / "demo_jobs.csv"

for p in (DATA_DIR, STORAGE_DIR, UPLOAD_DIR):
    p.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="SkillUp Evidence-first Labour Market Intelligence API", version="4.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:5174", "http://127.0.0.1:5174",
    ],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

DISTRICTS = ["Pune", "Nashik"]
SECTORS = [
    "All", "Automotive", "Manufacturing", "Capital Goods", "Agriculture", "Healthcare",
    "Construction", "Logistics", "IT/ITeS", "Electronics", "BFSI", "Retail",
    "Tourism & Hospitality", "Apparel", "Food Processing", "Power & Energy",
]

SKILL_ALIASES: dict[str, str] = {
    "plc": "PLC Programming", "plc programming": "PLC Programming",
    "programmable logic controller": "PLC Programming",
    "ev diagnostics": "EV Diagnostics", "electric vehicle diagnostics": "EV Diagnostics",
    "ev diagnosis": "EV Diagnostics", "ev": "EV Systems", "electric vehicle": "EV Systems",
    "can bus": "CAN Bus", "canbus": "CAN Bus", "controller area network": "CAN Bus",
    "battery management system": "Battery Management Systems", "bms": "Battery Management Systems",
    "battery diagnostics": "Battery Diagnostics", "battery testing": "Battery Testing",
    "charging systems": "EV Charging Systems", "ev charging": "EV Charging Systems",
    "cnc": "CNC Machining", "cnc machining": "CNC Machining",
    "cad": "CAD/CAM", "cam": "CAD/CAM", "cad/cam": "CAD/CAM",
    "robotics": "Industrial Robotics", "industrial robotics": "Industrial Robotics",
    "robot programming": "Industrial Robotics", "automation": "Industrial Automation",
    "preventive maintenance": "Preventive Maintenance", "maintenance": "Preventive Maintenance",
    "troubleshooting": "Troubleshooting", "electrical troubleshooting": "Electrical Troubleshooting",
    "welding": "Welding", "quality control": "Quality Control",
    "ev systems": "EV Systems", "quality assurance": "Quality Assurance",
    "inventory management": "Inventory Management", "warehouse management": "Warehouse Management",
    "cold chain": "Cold Chain Operations", "solar pump": "Solar Pump Maintenance",
    "drip irrigation": "Drip Irrigation", "power bi": "Power BI", "excel": "Advanced Excel",
    "advanced excel": "Advanced Excel", "sql": "SQL", "python": "Python", "javascript": "JavaScript",
    "react": "React", "data analysis": "Data Analysis", "machine learning": "Machine Learning",
    "artificial intelligence": "Artificial Intelligence", "ai": "Artificial Intelligence",
    "cyber security": "Cybersecurity", "cybersecurity": "Cybersecurity",
    "network security": "Network Security", "food safety": "Food Safety", "food packaging": "Food Packaging",
    "patient care": "Patient Care", "phlebotomy": "Phlebotomy", "retail operations": "Retail Operations",
    "pcb": "PCB Design", "printed circuit board": "PCB Design", "pcb design": "PCB Design",
    "eda": "EDA/CAD", "eda tools": "EDA/CAD", "electronic design automation": "EDA/CAD",
    "pcb manufacturing": "PCB Manufacturing", "pcb assembly": "PCB Assembly",
    "surface mounted": "SMD Assembly", "surface-mounted": "SMD Assembly", "smd assembly": "SMD Assembly",
    "leaded device assembly": "Through-Hole Assembly", "through-hole assembly": "Through-Hole Assembly",
    "circuit simulation": "Circuit Simulation", "waveform analysis": "Waveform Analysis",
    "design rule": "PCB Design Rules", "design-rule": "PCB Design Rules",
    "film-master": "PCB Manufacturing Documentation", "manufacturing documentation": "PCB Manufacturing Documentation",
    "customer service": "Customer Service", "sales": "Sales", "communication": "Communication",
    "hydraulics": "Hydraulics", "mechanical maintenance": "Mechanical Maintenance",
    "solar pv": "Solar PV", "solar photovoltaic": "Solar PV", "drone": "Drone Operations",
    "soldering": "Soldering", "pcb assembly": "PCB Assembly", "instrumentation": "Instrumentation",
    "technical drawing": "Technical Drawing", "engineering drawing": "Technical Drawing",
    "food processing": "Food Processing", "hygiene": "Workplace Hygiene", "barcode": "Barcode Operations",
}

SECTOR_RULES: list[tuple[str, list[str]]] = [
    ("Automotive", ["automotive", "vehicle", "ev ", "electric vehicle", "auto technician", "mechanic", "two wheeler", "four wheeler"]),
    ("Manufacturing", ["manufacturing", "production", "factory", "assembly", "production technician", "precision parts"]),
    ("Capital Goods", ["capital goods", "industrial automation", "industrial robotics", "plc", "cnc", "machine operator"]),
    ("Agriculture", ["agriculture", "agri", "farm", "irrigation", "crop", "tractor", "solar pump"]),
    ("Healthcare", ["healthcare", "hospital", "clinical", "nurse", "patient", "pharmacy", "medical"]),
    ("Construction", ["construction", "civil", "site engineer", "masonry", "building"]),
    ("Logistics", ["warehouse", "logistics", "supply chain", "dispatch", "delivery", "inventory"]),
    ("IT/ITeS", ["software", "developer", "data analyst", "python", "sql", "it support", "cyber", "technology"]),
    ("Electronics", ["electronics", "embedded", "pcb", "instrumentation", "electronic"]),
    ("BFSI", ["bank", "finance", "insurance", "accounts", "financial"]),
    ("Retail", ["retail", "store", "merchandising", "sales associate"]),
    ("Tourism & Hospitality", ["hotel", "hospitality", "tourism", "front office", "chef", "housekeeping"]),
    ("Apparel", ["apparel", "garment", "textile", "tailor", "sewing"]),
    ("Food Processing", ["food processing", "food safety", "dairy", "bakery", "packaging"]),
    ("Power & Energy", ["power", "energy", "solar", "electrical", "utility"]),
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_skill(skill: str) -> str:
    x = re.sub(r"\s+", " ", str(skill or "").strip().lower())
    if not x:
        return ""
    if x in SKILL_ALIASES:
        return SKILL_ALIASES[x]
    for canonical in set(SKILL_ALIASES.values()):
        if canonical.lower() == x:
            return canonical
    return x.title()


def classify_sector(title: str, desc: str, current: Optional[str] = None) -> str:
    if current and current in SECTORS and current != "All":
        return current
    text = f"{title} {desc}".lower()
    for sector, keys in SECTOR_RULES:
        if any(k in text for k in keys):
            return sector
    return "Other"


def deterministic_skills(text: str) -> list[str]:
    found: list[str] = []
    low = text.lower()
    for alias, canonical in SKILL_ALIASES.items():
        if re.search(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])", low):
            if canonical not in found:
                found.append(canonical)
    return found[:20]


def call_groq(text: str) -> list[str]:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        return []
    import urllib.request
    payload = {
        "model": os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"),
        "messages": [
            {"role": "system", "content": (
                "Extract only explicit job/curriculum competencies supported by the supplied text. "
                "Return JSON only with key technical_skills as an array of concise strings. Do not invent."
            )},
            {"role": "user", "content": text[:12000]},
        ],
        "temperature": 0,
        "max_completion_tokens": 700,
        "include_reasoning": False,
        "reasoning_effort": "low",
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "skill_extract", "strict": True, "schema": {
                "type": "object", "properties": {"technical_skills": {"type": "array", "items": {"type": "string"}}},
                "required": ["technical_skills"], "additionalProperties": False,
            }}
        },
    }
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "Accept": "application/json", "User-Agent": "SkillUp/4.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            body = json.loads(resp.read().decode("utf-8", errors="replace"))
        content = body["choices"][0]["message"]["content"]
        values = json.loads(content).get("technical_skills", [])
        return [normalize_skill(v) for v in values if isinstance(v, str) and v.strip()]
    except Exception:
        return []


def extract_skills(text: str, portal_skills: Optional[list[str]] = None) -> tuple[list[str], str]:
    portal = [normalize_skill(x) for x in (portal_skills or []) if str(x).strip()]
    llm = call_groq(text)
    source = "Groq LLM" if llm else "Deterministic evidence matcher"
    values = (llm + portal) if llm else (portal + deterministic_skills(text))
    seen: set[str] = set(); out: list[str] = []
    for value in values:
        if value and value not in seen:
            out.append(value); seen.add(value)
    return out[:24], source


# Curriculum-specific extraction is deliberately separate from job-posting extraction.
# This prevents generic words such as "packaging" from being mapped to an unrelated
# sector skill (e.g. Food Packaging) merely because the word appears in an official
# electronics/semiconductor curriculum.
CURRICULUM_SKILL_PATTERNS: list[tuple[str, str]] = [
    (r"\bpcb\b|printed circuit board", "PCB Design"),
    (r"\bpcb design\b|pcb design and analysis", "PCB Design"),
    (r"\beda\b|eda tools|electronic design automation|cad workflow", "EDA/CAD"),
    (r"pcb manufacturing", "PCB Manufacturing"),
    (r"pcb manufacturing and assembly|pcb assembly", "PCB Assembly"),
    (r"surface[- ]mounted|smd assembly|surface mounted device", "SMD Assembly"),
    (r"leaded (?:and )?surface[- ]mounted|leaded device assembly|through[- ]hole assembly", "Through-Hole Assembly"),
    (r"circuit simulation", "Circuit Simulation"),
    (r"waveform analysis", "Waveform Analysis"),
    (r"design[- ]rule|design rule adherence", "PCB Design Rules"),
    (r"manufacturing documentation|design/manufacturing documentation|film-master", "PCB Manufacturing Documentation"),
    (r"electronic component packages|component packages", "Electronic Components"),
    (r"circuit analysis", "Circuit Analysis"),
    (r"design documentation", "Technical Documentation"),
    (r"on[- ]the[- ]job training|\bojt\b", "On-the-Job Training"),
    (r"employability skills", "Employability Skills"),
]

CURRICULUM_MODULE_PATTERNS: list[tuple[str, str]] = [
    (r"fundamentals of pcb design", "Fundamentals of PCB Design"),
    (r"printed circuit board design and analysis techniques", "Printed Circuit Board Design and Analysis Techniques"),
    (r"pcb manufacturing and assembly techniques", "PCB Manufacturing and Assembly Techniques"),
    (r"implementation of pcb design project\s*/?\s*ojt", "Implementation of PCB Design Project / OJT"),
    (r"employability skills", "Employability Skills"),
]


def extract_curriculum_skills(text: str) -> list[str]:
    """Extract only skills explicitly evidenced by curriculum text."""
    low = text.lower()
    found: list[str] = []
    for pattern, canonical in CURRICULUM_SKILL_PATTERNS:
        if re.search(pattern, low, re.I):
            if canonical not in found:
                found.append(canonical)

    # Preserve explicitly stated competency-family names from curriculum tables.
    competency_aliases = {
        "pcb fundamentals": "PCB Design",
        "eda / cad": "EDA/CAD",
        "pcb design": "PCB Design",
        "manufacturing documentation": "PCB Manufacturing Documentation",
        "assembly": "PCB Assembly",
        "analysis": "Circuit Analysis",
        "project / ojt": "On-the-Job Training",
        "employability": "Employability Skills",
    }
    for raw, canonical in competency_aliases.items():
        if re.search(r"(?<![a-z0-9])" + re.escape(raw) + r"(?![a-z0-9])", low):
            if canonical not in found:
                found.append(canonical)
    return found[:40]


def extract_curriculum_modules(text: str) -> list[str]:
    """Extract module titles from known curriculum wording without inventing modules."""
    found: list[str] = []
    for pattern, title in CURRICULUM_MODULE_PATTERNS:
        if re.search(pattern, text, re.I) and title not in found:
            found.append(title)
    return found[:30]


def extract_curriculum_tables(pdf) -> tuple[list[str], list[dict[str, Any]]]:
    """Read module/competency tables when the PDF exposes them as tables."""
    modules: list[str] = []
    evidence: list[dict[str, Any]] = []

    for page_no, page in enumerate(pdf.pages, start=1):
        try:
            tables = page.extract_tables() or []
        except Exception:
            tables = []

        for table in tables:
            rows = []
            for row in table:
                cells = [clean_text(c or "") for c in (row or [])]
                if any(cells):
                    rows.append(cells)
            if not rows:
                continue

            header = " ".join(rows[0]).lower()

            # Typical module/NOS table: first column is the module title.
            if ("module" in header or "nos" in header) and (
                "code" in header or "hours" in header or "duration" in header
            ):
                for row in rows[1:]:
                    title = row[0] if row else ""
                    if (
                        title
                        and title.lower() not in {"total", "module / nos"}
                        and len(title) <= 180
                    ):
                        modules.append(title)

            # Typical competency table: first column is the competency family,
            # second column is its supporting curriculum evidence.
            if "skill / competency family" in header or (
                "competency" in header and len(rows[0]) >= 2
            ):
                for row in rows[1:]:
                    if len(row) < 2 or not row[0]:
                        continue
                    family = row[0]
                    supporting_text = row[1]
                    combined = f"{family}. {supporting_text}".strip()
                    for skill in extract_curriculum_skills(combined):
                        evidence.append({
                            "page_number": page_no,
                            "evidence_type": "curriculum_table",
                            "skill": skill,
                            "text": combined[:360],
                        })

    return list(dict.fromkeys(modules))[:30], evidence[:100]


def db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    con = db()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        stable_id TEXT UNIQUE NOT NULL,
        source TEXT NOT NULL,
        source_job_id TEXT,
        source_url TEXT,
        posted_date TEXT,
        collected_at TEXT NOT NULL,
        district TEXT,
        location_text TEXT,
        sector TEXT,
        functional_role TEXT,
        title TEXT,
        employer TEXT,
        salary TEXT,
        openings INTEGER,
        description TEXT,
        evidence_text TEXT,
        description_hash TEXT,
        raw_skills_json TEXT DEFAULT '[]',
        skills_json TEXT DEFAULT '[]',
        extraction_source TEXT,
        extraction_confidence REAL DEFAULT 0,
        is_demo INTEGER DEFAULT 0,
        updated_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_jobs_context ON jobs(district, sector, functional_role);
    CREATE INDEX IF NOT EXISTS idx_jobs_posted ON jobs(posted_date);
    CREATE INDEX IF NOT EXISTS idx_jobs_hash ON jobs(description_hash);

    CREATE TABLE IF NOT EXISTS curriculum_documents (
        document_id TEXT PRIMARY KEY,
        filename TEXT NOT NULL,
        imported_at TEXT NOT NULL,
        source TEXT NOT NULL,
        sector TEXT NOT NULL,
        course_name TEXT,
        pages INTEGER DEFAULT 0,
        status TEXT NOT NULL,
        skills_json TEXT DEFAULT '[]',
        module_titles_json TEXT DEFAULT '[]',
        evidence_json TEXT DEFAULT '[]',
        stored_path TEXT,
        notes TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_curriculum_sector ON curriculum_documents(sector);

    CREATE TABLE IF NOT EXISTS curriculum_evidence (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        document_id TEXT NOT NULL,
        page_number INTEGER,
        evidence_type TEXT,
        skill TEXT,
        text TEXT,
        FOREIGN KEY(document_id) REFERENCES curriculum_documents(document_id)
    );

    CREATE TABLE IF NOT EXISTS sync_runs (
        run_id TEXT PRIMARY KEY,
        started_at TEXT NOT NULL,
        finished_at TEXT,
        status TEXT NOT NULL,
        district TEXT,
        source TEXT,
        pages_requested INTEGER DEFAULT 0,
        pages_processed INTEGER DEFAULT 0,
        discovered INTEGER DEFAULT 0,
        new_jobs INTEGER DEFAULT 0,
        updated_jobs INTEGER DEFAULT 0,
        skipped_jobs INTEGER DEFAULT 0,
        total_jobs INTEGER DEFAULT 0,
        skills_updated INTEGER DEFAULT 0,
        message TEXT,
        error TEXT
    );

    CREATE TABLE IF NOT EXISTS proposals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'PROPOSED',
        district TEXT,
        sector TEXT,
        skill TEXT,
        learning_outcome TEXT,
        practical_change TEXT,
        assessment_change TEXT,
        equipment TEXT,
        evidence_json TEXT
    );

    CREATE TABLE IF NOT EXISTS validations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT NOT NULL,
        skill TEXT,
        status TEXT,
        comment TEXT
    );

    CREATE TABLE IF NOT EXISTS imports (
        import_id TEXT PRIMARY KEY,
        filename TEXT NOT NULL,
        imported_at TEXT NOT NULL,
        file_type TEXT NOT NULL,
        rows_processed INTEGER DEFAULT 0,
        status TEXT NOT NULL,
        notes TEXT
    );
    """)
    con.commit(); con.close()


def read_catalogue() -> list[dict[str, Any]]:
    if not CATALOG_PATH.exists():
        return []
    with CATALOG_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def read_baseline() -> list[dict[str, Any]]:
    if not BASELINE_PATH.exists():
        return []
    with BASELINE_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def seed_demo_if_empty() -> None:
    con = db(); count = con.execute("SELECT COUNT(*) AS n FROM jobs").fetchone()["n"]; con.close()
    if count or not DEMO_JOBS_PATH.exists():
        return
    with DEMO_JOBS_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    for j in rows:
        skills, source = extract_skills(j.get("description", ""), [])
        upsert_job({
            **j,
            "stable_id": j["source_job_id"],
            "skills": skills,
            "extraction_source": source,
            "extraction_confidence": 0.90 if skills else 0.50,
            "evidence_text": j.get("description", ""),
            "is_demo": True,
        })


def upsert_job(job: dict[str, Any]) -> str:
    desc = re.sub(r"\s+", " ", str(job.get("description") or "")).strip()
    d_hash = hashlib.sha256(desc.lower().encode()).hexdigest()
    stable = job.get("stable_id") or hashlib.sha256(
        "||".join(str(job.get(k, "")) for k in ("source", "source_job_id", "source_url", "title", "employer", "posted_date", "district", "location_text")).encode()
    ).hexdigest()[:24]
    con = db()
    existing = con.execute("SELECT stable_id, description_hash FROM jobs WHERE stable_id=?", (stable,)).fetchone()
    if existing and existing["description_hash"] == d_hash:
        con.close(); return "skipped"

    raw_skills = job.get("skills") or job.get("portal_skills") or []
    extracted, extraction_source = extract_skills(f"{job.get('title','')}\n{desc}", raw_skills)
    extraction_source = job.get("extraction_source") or extraction_source
    confidence = float(job.get("extraction_confidence") or (0.95 if extracted else 0.55))
    payload = (
        stable, job.get("source", ""), job.get("source_job_id"), job.get("source_url"), job.get("posted_date"), utc_now(),
        job.get("district"), job.get("location_text"), job.get("sector") or classify_sector(job.get("title", ""), desc),
        job.get("functional_role") or job.get("role") or job.get("title"), job.get("title"), job.get("employer"), job.get("salary"),
        int(job["openings"]) if str(job.get("openings", "")).isdigit() else None, desc, job.get("evidence_text") or desc,
        d_hash, json.dumps(raw_skills, ensure_ascii=False), json.dumps(extracted, ensure_ascii=False), extraction_source, confidence,
        int(bool(job.get("is_demo"))), utc_now(),
    )
    if existing:
        con.execute("""UPDATE jobs SET source=?,source_job_id=?,source_url=?,posted_date=?,collected_at=?,district=?,location_text=?,sector=?,functional_role=?,title=?,employer=?,salary=?,openings=?,description=?,evidence_text=?,description_hash=?,raw_skills_json=?,skills_json=?,extraction_source=?,extraction_confidence=?,is_demo=?,updated_at=? WHERE stable_id=?""", payload[1:] + (stable,))
        con.commit(); con.close(); return "updated"
    duplicate = con.execute("SELECT stable_id FROM jobs WHERE source=? AND title=? AND employer=? AND description_hash=?", (job.get("source", ""), job.get("title", ""), job.get("employer", ""), d_hash)).fetchone()
    if duplicate:
        con.close(); return "skipped"
    con.execute("""INSERT INTO jobs(stable_id,source,source_job_id,source_url,posted_date,collected_at,district,location_text,sector,functional_role,title,employer,salary,openings,description,evidence_text,description_hash,raw_skills_json,skills_json,extraction_source,extraction_confidence,is_demo,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", payload)
    con.commit(); con.close(); return "new"


def query_jobs(district="All", sector="All", role="All") -> list[dict[str, Any]]:
    clauses = []; params: list[Any] = []
    if district and district != "All": clauses.append("district=?"); params.append(district)
    if sector and sector != "All": clauses.append("sector=?"); params.append(sector)
    if role and role != "All": clauses.append("functional_role=?"); params.append(role)
    q = "SELECT * FROM jobs" + ((" WHERE " + " AND ".join(clauses)) if clauses else "") + " ORDER BY posted_date DESC, updated_at DESC"
    con = db(); rows = con.execute(q, params).fetchall(); con.close()
    out=[]
    for row in rows:
        item = dict(row)
        item["skills"] = json.loads(item.pop("skills_json") or "[]")
        item["raw_skills"] = json.loads(item.pop("raw_skills_json") or "[]")
        item["is_demo"] = bool(item["is_demo"])
        out.append(item)
    return out


def demand_for(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counter = Counter(); evidence: dict[str, list[str]] = defaultdict(list)
    for job in jobs:
        seen_in_job=set()
        for normalized in (normalize_skill(x) for x in job.get("skills", [])):
            if not normalized or normalized in seen_in_job:
                continue
            counter[normalized] += 1
            evidence[normalized].append(job["stable_id"])
            seen_in_job.add(normalized)
    total = max(1, len(jobs))
    alias_map=defaultdict(list)
    for raw, canonical in SKILL_ALIASES.items():
        if raw != canonical.lower() and raw not in alias_map[canonical]:
            alias_map[canonical].append(raw)
    return [{
        "skill": skill, "postings": count, "demand_pct": round(count / total * 100, 1),
        "raw_variants": (alias_map.get(skill) or [skill])[:6], "evidence_job_ids": evidence[skill],
    } for skill, count in counter.most_common()]


def curriculum_documents(sector="All") -> list[dict[str, Any]]:
    con = db()
    if sector and sector != "All":
        rows = con.execute("SELECT * FROM curriculum_documents WHERE sector=? ORDER BY imported_at DESC", (sector,)).fetchall()
    else:
        rows = con.execute("SELECT * FROM curriculum_documents ORDER BY imported_at DESC").fetchall()
    con.close()
    out=[]
    for row in rows:
        d=dict(row); d["skills"] = json.loads(d.pop("skills_json") or "[]"); d["module_titles"] = json.loads(d.pop("module_titles_json") or "[]"); d["evidence"] = json.loads(d.pop("evidence_json") or "[]"); out.append(d)
    return out


def course_matches_skill(course: dict[str, Any], skill: str) -> bool:
    text = " ".join(str(course.get(k, "")) for k in course.keys()).lower()
    aliases = {
        "EV Systems": ["electric vehicle", "electric mobility", "ev"],
        "EV Diagnostics": ["ev diagnostic", "electric vehicle diagnostic"],
        "Battery Management Systems": ["battery management", "bms"],
        "Battery Testing": ["battery testing", "battery test"],
        "CAN Bus": ["can bus", "controller area network"],
        "Preventive Maintenance": ["preventive maintenance", "maintenance"],
        "Electrical Troubleshooting": ["electrical troubleshooting", "electrical fault"],
        "CNC Machining": ["cnc"], "CAD/CAM": ["cad", "cam"],
        "Industrial Robotics": ["industrial robot", "robotics"],
        "PLC Programming": ["plc", "programmable logic controller"],
        "Solar Pump Maintenance": ["solar pump"], "Patient Care": ["patient care", "healthcare assistant", "general duty assistant"],
        "Food Safety": ["food safety"], "Food Processing": ["food processing"],
        "Food Packaging": ["food packaging"],
        "PCB Design": ["pcb", "printed circuit board", "pcb design"],
        "EDA/CAD": ["eda", "electronic design automation", "cad"],
        "PCB Manufacturing": ["pcb manufacturing"],
        "PCB Assembly": ["pcb assembly", "assembly of pcb"],
        "SMD Assembly": ["surface mounted", "surface-mounted", "smd assembly"],
        "Through-Hole Assembly": ["leaded device assembly", "through-hole assembly"],
        "Circuit Simulation": ["circuit simulation"],
        "Waveform Analysis": ["waveform analysis"],
        "PCB Design Rules": ["design rule", "design-rule"],
        "PCB Manufacturing Documentation": ["manufacturing documentation", "film-master"],
        "Electronic Components": ["electronic component", "component packages"],
        "Circuit Analysis": ["circuit analysis", "pcb design analysis"],
        "Technical Documentation": ["design documentation", "technical documentation"],
        "On-the-Job Training": ["on-the-job training", "ojt"],
        "Employability Skills": ["employability skills"],
    }
    terms = aliases.get(skill, [skill.lower()])
    return any(t in text for t in terms)


def curriculum_status(skill: str, sector: str) -> dict[str, Any]:
    catalogue = read_catalogue()
    relevant = catalogue if sector == "All" else [r for r in catalogue if str(r.get("sector", "")).strip().lower() == sector.lower()]
    catalogue_matches = [r for r in relevant if course_matches_skill(r, skill)]

    docs = curriculum_documents(sector)
    uploaded_hits=[]
    evidence=[]
    for doc in docs:
        for e in doc.get("evidence", []):
            if normalize_skill(e.get("skill", "")) == normalize_skill(skill):
                uploaded_hits.append(doc)
                evidence.append(e)
    if uploaded_hits:
        return {"status": "Covered", "coverage": 100, "evidence_level": "Explicit text evidence from uploaded syllabus", "course_count": len(catalogue_matches), "courses": catalogue_matches[:5], "documents": uploaded_hits[:5], "evidence": evidence[:8]}
    if catalogue_matches:
        return {"status": "Covered", "coverage": 100, "evidence_level": "Explicit text evidence in imported course catalogue", "course_count": len(catalogue_matches), "courses": catalogue_matches[:5], "documents": [], "evidence": []}
    return {"status": "Not evidenced", "coverage": 0, "evidence_level": "No explicit text match in the available curriculum evidence", "course_count": 0, "courses": [], "documents": [], "evidence": []}


def make_gaps(jobs: list[dict[str, Any]], sector: str) -> list[dict[str, Any]]:
    out=[]
    for item in demand_for(jobs):
        cur = curriculum_status(item["skill"], sector)
        gap_score = round(item["demand_pct"] * (1 - cur["coverage"] / 100), 1)
        out.append({**item, "curriculum_status": cur["status"], "curriculum_coverage": cur["coverage"], "curriculum_evidence": cur["evidence_level"], "course_count": cur["course_count"], "curriculum_courses": cur["courses"], "curriculum_documents": cur["documents"], "curriculum_evidence_items": cur["evidence"], "gap": gap_score > 0, "gap_score": gap_score})
    return out


def alignment(gaps: list[dict[str, Any]]) -> float:
    denom = sum(float(g["postings"]) for g in gaps)
    if not denom: return 0.0
    covered = sum(float(g["postings"]) for g in gaps if g["curriculum_status"] == "Covered")
    return round(covered / denom * 100, 1)


def trend_for(jobs: list[dict[str, Any]], days=21) -> list[dict[str, Any]]:
    today = date.today(); counts=Counter()
    for j in jobs:
        try:
            d = date.fromisoformat(str(j.get("posted_date"))[:10]); counts[d.isoformat()] += 1
        except Exception:
            pass
    return [{"date": (today - timedelta(days=i)).isoformat(), "jobs": counts.get((today - timedelta(days=i)).isoformat(), 0)} for i in range(days - 1, -1, -1)]


def last_sync(district: Optional[str] = None):
    con = db()
    if district and district != "All":
        row = con.execute("SELECT * FROM sync_runs WHERE district=? ORDER BY started_at DESC LIMIT 1", (district,)).fetchone()
    else:
        row = con.execute("SELECT * FROM sync_runs ORDER BY started_at DESC LIMIT 1").fetchone()
    con.close(); return dict(row) if row else None


def parse_date_text(s: str) -> Optional[str]:
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y", "%d/%b/%Y"):
        try: return datetime.strptime(s.strip(), fmt).date().isoformat()
        except ValueError: pass
    return None


def clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip(" |•-\t")


def parse_ncs_blocks(body: str, source_url: str, district: str) -> list[dict[str, Any]]:
    pattern = re.compile(
        r"(?P<title>[^\n]{3,180})\n\s*Company:\s*(?P<company>[^\n]*)\n.*?Job Location:\s*(?P<location>[^\n]*)\n.*?Skill Required:\s*(?P<skills>[^\n]*)\n.*?Job Description:\s*(?P<desc>.*?)(?:Read more\.\.\.|Posted On\s+)(?P<tail>.*?)(?:Posted On\s+)?(?P<date>\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        re.S | re.I,
    )
    found=[]
    for match in pattern.finditer(body.replace("\r", "")):
        title=clean_text(match.group("title")); loc=clean_text(match.group("location")); desc=clean_text(match.group("desc")); posted=parse_date_text(match.group("date"));
        if not posted or len(desc) < 10 or district.lower() not in loc.lower():
            continue
        portal_skills=[clean_text(x) for x in re.split(r"[;,]", match.group("skills") or "") if clean_text(x)]
        found.append({
            "source": "NCS public job search", "source_url": source_url, "source_job_id": None,
            "posted_date": posted, "district": district, "location_text": loc,
            "sector": classify_sector(title, desc), "functional_role": title, "title": title,
            "employer": clean_text(match.group("company")), "description": desc, "evidence_text": desc,
            "skills": portal_skills, "is_demo": False,
        })
    return found


async def _try_apply_location(page, district: str) -> bool:
    try:
        inputs = page.locator("input")
        for i in range(await inputs.count()):
            el=inputs.nth(i)
            meta=" ".join([await el.get_attribute("placeholder") or "", await el.get_attribute("aria-label") or "", await el.get_attribute("name") or ""]).lower()
            if not any(k in meta for k in ("location", "city", "district")):
                continue
            await el.fill(district); await page.wait_for_timeout(800)
            match=page.get_by_text(district, exact=True)
            if await match.count() and await match.first().is_visible(): await match.first().click(timeout=2500)
            else: await el.press("Enter")
            await page.wait_for_timeout(1200); return True
    except Exception:
        return False
    return False


async def collect_ncs_live(district: str = "Pune", max_pages: int = 4, lookback_days: int = 45) -> dict[str, Any]:
    try:
        from playwright.async_api import async_playwright
    except Exception:
        return {"ok": False, "error": "Playwright is not installed. Install it and run playwright install chromium.", "jobs": [], "pages": 0}
    urls = ["https://www.ncs.gov.in/Pmis-jobList", "https://ncs.gov.in/Pmis-jobList"]
    cutoff = date.today() - timedelta(days=lookback_days); all_jobs=[]; seen=set(); errors=[]; pages=0
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 1100}, user_agent="Mozilla/5.0 (SkillUp research prototype)")
        page = await context.new_page()
        for url in urls:
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(2500); await _try_apply_location(page, district)
                for page_no in range(max_pages):
                    pages += 1
                    body = await page.locator("body").inner_text(timeout=20000)
                    jobs = parse_ncs_blocks(body, page.url, district)
                    before=len(all_jobs)
                    for job in jobs:
                        if job["posted_date"] >= cutoff.isoformat():
                            key=(job["title"], job["employer"], job["posted_date"], job["district"])
                            if key not in seen: all_jobs.append(job); seen.add(key)
                    if len(all_jobs) == before:
                        try:
                            nxt = page.get_by_text("Next", exact=True)
                            if await nxt.count() and await nxt.first().is_visible():
                                await nxt.first().click(timeout=5000); await page.wait_for_timeout(1800); continue
                        except Exception:
                            pass
                        break
                if all_jobs: break
            except Exception as exc:
                errors.append(f"{url}: {type(exc).__name__}: {exc}")
        await browser.close()
    if all_jobs:
        return {"ok": True, "jobs": all_jobs, "pages": pages, "errors": errors}
    return {"ok": False, "jobs": [], "pages": pages, "error": "No matching district postings were parsed from NCS. The source UI/access conditions may have changed.", "errors": errors}


# ---------- API models ----------
class ContextRequest(BaseModel):
    district: str="Pune"; sector: str="Automotive"; role: str="All"
class WhatIfRequest(BaseModel):
    district: str="Pune"; sector: str="Automotive"; role: str="All"; added_skills: list[str]=Field(default_factory=list)
class ProposalRequest(BaseModel):
    district: str; sector: str; skill: str; learning_outcome: str=""; practical_change: str=""; assessment_change: str=""; equipment: str=""; evidence: list[dict[str, Any]]=Field(default_factory=list)
class ValidationRequest(BaseModel):
    skill: str; status: str; comment: str
class SyncRequest(BaseModel):
    district: str="Pune"; max_pages: int=4; lookback_days: int=45
class ExtractRequest(BaseModel):
    text: str


init_db(); seed_demo_if_empty()


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "4.0.0"}

@app.get("/api/context")
def context():
    roles = sorted({j["functional_role"] for j in query_jobs("All", "All", "All") if j.get("functional_role")})
    return {"districts": DISTRICTS, "sectors": SECTORS, "roles": ["All"] + roles, "evidence_types": ["Current labour market", "Government baseline", "Official curriculum", "Employer validation"]}

@app.get("/api/source-status")
def source_status():
    playwright_ready=False
    try:
        import playwright  # noqa
        playwright_ready=True
    except Exception: pass
    return {
        "ncs": {"url": "https://www.ncs.gov.in/Pmis-jobList", "adapter": "Playwright collection adapter", "playwright_installed": playwright_ready},
        "mahaswayam": {"url": "https://rojgar.mahaswayam.gov.in/", "mode": "Official employment signal; expansion adapter"},
        "last_sync": last_sync(),
    }

@app.get("/api/overview")
def overview(district: str="Pune", sector: str="All", role: str="All"):
    jobs=query_jobs(district,sector,role)
    gaps=make_gaps(jobs, sector)
    baseline = next((x for x in read_baseline() if x.get("sector", "").lower() == sector.lower()), None) if district == "Pune" and sector != "All" else None
    return {
        "district": district, "sector": sector, "role": role, "jobs": jobs, "demand_skills": demand_for(jobs), "gaps": gaps,
        "alignment": alignment(gaps), "course_count": len([r for r in read_catalogue() if sector == "All" or str(r.get("sector", "")).lower() == sector.lower()]),
        "projection_context": baseline, "trend": trend_for(jobs), "last_sync": last_sync(district),
    }

@app.get("/api/jobs")
def get_jobs(district="All", sector="All", role="All"):
    return {"items": query_jobs(district,sector,role)}

@app.get("/api/evidence/{skill}")
def evidence(skill: str, district="Pune", sector="All", role="All"):
    normalized=normalize_skill(skill); jobs=query_jobs(district,sector,role)
    matches=[j for j in jobs if normalized in [normalize_skill(x) for x in j.get("skills", [])]]
    ctx_sector=sector if sector != "All" else (matches[0]["sector"] if matches else "All")
    cur=curriculum_status(normalized,ctx_sector)
    con=db(); validations=[dict(r) for r in con.execute("SELECT * FROM validations WHERE skill=? ORDER BY created_at DESC LIMIT 8",(normalized,)).fetchall()]; con.close()
    return {
        "skill": normalized, "job_count": len(matches), "job_evidence": matches[:12], "curriculum": cur, "validations": validations,
        "interpretation": "Demand share is the percentage of postings in the selected analysed dataset that mention this normalized skill. It is not a population-wide employment percentage.",
    }

@app.get("/api/curriculum/library")
def curriculum_library(sector="All", query=""):
    courses=read_catalogue(); docs=curriculum_documents(sector)
    if sector != "All": courses=[c for c in courses if str(c.get("sector","")).lower()==sector.lower()]
    if query.strip():
        q=query.lower(); courses=[c for c in courses if q in " ".join(str(v).lower() for v in c.values())]
    return {"courses": courses, "documents": docs, "total_courses": len(courses), "total_documents": len(docs)}

@app.post("/api/curriculum/upload")
async def curriculum_upload(file: UploadFile=File(...), sector: str=Form("Automotive"), course_name: str=Form("")):
    name=file.filename or "curriculum.pdf"
    if Path(name).suffix.lower() != ".pdf":
        raise HTTPException(status_code=400, detail="Upload a PDF syllabus/curriculum document.")
    raw=await file.read(); document_id=str(uuid.uuid4()); stored=UPLOAD_DIR/f"{document_id}_{Path(name).name}"; stored.write_bytes(raw)
    try:
        import pdfplumber
        page_texts=[]
        with pdfplumber.open(io.BytesIO(raw)) as pdf:
            for idx,page in enumerate(pdf.pages, start=1):
                page_texts.append((idx, clean_text(page.extract_text() or "")))
        full_text="\n".join(t for _,t in page_texts)

        # Curriculum PDFs use a dedicated evidence-safe extractor. We do not use
        # the generic job-posting skill extractor here because broad aliases such
        # as "packaging" can create false sector skills.
        skills = extract_curriculum_skills(full_text)
        modules = extract_curriculum_modules(full_text)
        table_modules, table_evidence = extract_curriculum_tables(pdf)

        for module in table_modules:
            if module not in modules:
                modules.append(module)
        evidence = list(table_evidence)

        # Add page-level evidence for every extracted curriculum skill.
        for page_no, text in page_texts:
            for skill in skills:
                pattern = None
                for candidate_pattern, canonical in CURRICULUM_SKILL_PATTERNS:
                    if canonical == skill:
                        pattern = candidate_pattern
                        break
                if pattern and re.search(pattern, text, re.I):
                    m = re.search(r".{0,120}" + pattern + r".{0,180}", text, re.I)
                    if m:
                        item = {
                            "page_number": page_no,
                            "evidence_type": "explicit_text",
                            "skill": skill,
                            "text": clean_text(m.group(0))[:360],
                        }
                        if not any(
                            e["page_number"] == page_no
                            and e["skill"] == skill
                            and e["text"] == item["text"]
                            for e in evidence
                        ):
                            evidence.append(item)
        con=db()
        con.execute("INSERT INTO curriculum_documents(document_id,filename,imported_at,source,sector,course_name,pages,status,skills_json,module_titles_json,evidence_json,stored_path,notes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            document_id,name,utc_now(),"User uploaded official/working curriculum PDF",sector,course_name or Path(name).stem,len(page_texts),"processed",json.dumps(skills,ensure_ascii=False),json.dumps(modules[:30],ensure_ascii=False),json.dumps(evidence[:100],ensure_ascii=False),str(stored),"Text extracted with pdfplumber. Scanned-image-only pages may require OCR.")
        )
        for item in evidence:
            con.execute("INSERT INTO curriculum_evidence(document_id,page_number,evidence_type,skill,text) VALUES(?,?,?,?,?)", (document_id,item["page_number"],item["evidence_type"],item["skill"],item["text"]))
        con.commit(); con.close()
        con=db(); con.execute("INSERT INTO imports(import_id,filename,imported_at,file_type,rows_processed,status,notes) VALUES(?,?,?,?,?,?,?)",(document_id,name,utc_now(),".pdf",len(page_texts),"processed","Curriculum PDF parsed; explicit skill evidence saved for gap analysis.")); con.commit(); con.close()
        return {"status":"processed","document_id":document_id,"filename":name,"pages":len(page_texts),"skills":skills,"modules":modules[:12],"evidence_count":len(evidence)}
    except Exception as exc:
        con=db(); con.execute("INSERT INTO imports(import_id,filename,imported_at,file_type,rows_processed,status,notes) VALUES(?,?,?,?,?,?,?)",(document_id,name,utc_now(),".pdf",0,"failed",str(exc))); con.commit(); con.close()
        raise HTTPException(status_code=400,detail=f"Curriculum PDF could not be processed: {exc}")

@app.post("/api/import")
async def generic_import(file: UploadFile=File(...)):
    raw=await file.read(); name=file.filename or "evidence"; ext=Path(name).suffix.lower(); import_id=str(uuid.uuid4()); target=UPLOAD_DIR/f"{import_id}_{Path(name).name}"; target.write_bytes(raw)
    rows=0; notes="Registered for evidence review."
    try:
        if ext==".csv": rows=max(0,sum(1 for _ in csv.DictReader(io.StringIO(raw.decode("utf-8-sig",errors="replace")))))
        elif ext==".json": rows=len(json.loads(raw.decode("utf-8",errors="replace")))
        elif ext in {".xlsx",".xls"}:
            import pandas as pd; book=pd.ExcelFile(io.BytesIO(raw)); rows=sum(len(pd.read_excel(book,s).index) for s in book.sheet_names)
        elif ext==".pdf":
            import pdfplumber
            with pdfplumber.open(io.BytesIO(raw)) as pdf: rows=len(pdf.pages); notes="Use Curriculum upload for syllabi so skill evidence is mapped into the curriculum layer."
        else: rows=1
    except Exception as exc: raise HTTPException(status_code=400,detail=f"Import failed: {exc}")
    con=db(); con.execute("INSERT INTO imports(import_id,filename,imported_at,file_type,rows_processed,status,notes) VALUES(?,?,?,?,?,?,?)",(import_id,name,utc_now(),ext,rows,"registered",notes)); con.commit(); con.close()
    return {"status":"registered","name":name,"rows":rows,"type":ext,"notes":notes}

@app.get("/api/imports")
def imports():
    con=db(); rows=[dict(r) for r in con.execute("SELECT * FROM imports ORDER BY imported_at DESC LIMIT 30").fetchall()]; con.close(); return {"items":rows}

@app.post("/api/ai/extract-skills")
def ai_extract(req: ExtractRequest):
    skills,source=extract_skills(req.text); return {"skills":skills,"source":source,"ai_enabled":bool(os.getenv("GROQ_API_KEY"))}

@app.post("/api/what-if")
def what_if(req: WhatIfRequest):
    jobs=query_jobs(req.district,req.sector,req.role); gaps=make_gaps(jobs,req.sector); current=alignment(gaps); added={normalize_skill(x) for x in req.added_skills if str(x).strip()}; simulated=[]
    for g in gaps:
        simulated.append({**g,"curriculum_status":"Covered" if g["skill"] in added else g["curriculum_status"]})
    projected=alignment(simulated); return {"current_alignment":current,"projected_alignment":projected,"delta":round(projected-current,1),"added_skills":sorted(added),"note":"Deterministic scenario: selected skills are treated as covered evidence for the scenario only. This is not a placement forecast."}

@app.post("/api/proposals")
def proposal(req: ProposalRequest):
    con=db(); con.execute("INSERT INTO proposals(created_at,status,district,sector,skill,learning_outcome,practical_change,assessment_change,equipment,evidence_json) VALUES(?,?,?,?,?,?,?,?,?,?)",(utc_now(),"PROPOSED",req.district,req.sector,normalize_skill(req.skill),req.learning_outcome,req.practical_change,req.assessment_change,req.equipment,json.dumps(req.evidence,ensure_ascii=False))); con.commit(); con.close(); return {"status":"saved"}

@app.get("/api/proposals")
def proposals():
    con=db(); rows=[dict(r) for r in con.execute("SELECT * FROM proposals ORDER BY created_at DESC LIMIT 30").fetchall()]; con.close(); return {"items":rows}

@app.post("/api/validate")
def validate(req: ValidationRequest):
    con=db(); con.execute("INSERT INTO validations(created_at,skill,status,comment) VALUES(?,?,?,?)",(utc_now(),normalize_skill(req.skill),req.status,req.comment)); con.commit(); con.close(); return {"status":"saved"}

@app.get("/api/validations")
def validations():
    con=db(); rows=[dict(r) for r in con.execute("SELECT * FROM validations ORDER BY created_at DESC LIMIT 30").fetchall()]; con.close(); return {"items":rows}


def _finish_sync(run_id: str, status: str, message: str, counts: dict[str, int], errors: Any):
    con=db(); con.execute("UPDATE sync_runs SET finished_at=?,status=?,pages_processed=?,discovered=?,new_jobs=?,updated_jobs=?,skipped_jobs=?,total_jobs=?,skills_updated=?,message=?,error=? WHERE run_id=?", (utc_now(),status,counts.get("pages",0),counts.get("discovered",0),counts.get("new",0),counts.get("updated",0),counts.get("skipped",0),counts.get("total",0),counts.get("new",0)+counts.get("updated",0),message,json.dumps(errors,ensure_ascii=False) if errors else None,run_id)); con.commit(); con.close()


def _run_sync(run_id: str, req: SyncRequest):
    con=db(); con.execute("INSERT OR REPLACE INTO sync_runs(run_id,started_at,status,district,source,pages_requested) VALUES(?,?,?,?,?,?)",(run_id,utc_now(),"running",req.district,"NCS",req.max_pages)); con.commit(); con.close()
    if os.getenv("LIVE_COLLECTION_ENABLED","true").lower() != "true": _finish_sync(run_id,"failed","Live collection disabled by LIVE_COLLECTION_ENABLED=false",{},None); return
    try:
        import asyncio
        result=asyncio.run(collect_ncs_live(req.district,req.max_pages,req.lookback_days)); counts=Counter()
        for job in result.get("jobs",[]): counts[upsert_job(job)] += 1
        total=len(query_jobs(req.district,"All","All")); status="success" if result.get("ok") else "partial"; msg="Live market collection completed." if result.get("ok") else result.get("error","No data")
        _finish_sync(run_id,status,msg,{"pages":result.get("pages",0),"discovered":len(result.get("jobs",[])),"new":counts["new"],"updated":counts["updated"],"skipped":counts["skipped"],"total":total},result.get("errors"))
    except Exception as exc: _finish_sync(run_id,"failed",str(exc),{},None)

@app.post("/api/sync")
def sync(req: SyncRequest, background_tasks: BackgroundTasks):
    run_id=str(uuid.uuid4()); background_tasks.add_task(_run_sync,run_id,req); return {"run_id":run_id,"status":"queued","mode":"live_ncs_collection","district":req.district}

@app.get("/api/sync/{run_id}")
def sync_status(run_id: str):
    con=db(); row=con.execute("SELECT * FROM sync_runs WHERE run_id=?",(run_id,)).fetchone(); con.close()
    if not row: raise HTTPException(status_code=404,detail="Sync run not found")
    return dict(row)

@app.get("/api/status")
def status():
    con=db(); result={
        "jobs": con.execute("SELECT COUNT(*) n FROM jobs").fetchone()["n"],
        "live_jobs": con.execute("SELECT COUNT(*) n FROM jobs WHERE is_demo=0").fetchone()["n"],
        "demo_jobs": con.execute("SELECT COUNT(*) n FROM jobs WHERE is_demo=1").fetchone()["n"],
        "curriculum_documents": con.execute("SELECT COUNT(*) n FROM curriculum_documents").fetchone()["n"],
        "imports": con.execute("SELECT COUNT(*) n FROM imports").fetchone()["n"],
    }; con.close(); return {**result,"last_sync":last_sync(),"live_collection_enabled":os.getenv("LIVE_COLLECTION_ENABLED","true").lower()=="true"}
