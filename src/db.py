"""SQLite persistence layer: criteria, runs, supplier results."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "rfp.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS evaluation_criteria (
    criterion_id INTEGER PRIMARY KEY,
    name         TEXT NOT NULL,
    description  TEXT NOT NULL DEFAULT '',
    weight       REAL NOT NULL CHECK (weight >= 0),
    max_score    REAL NOT NULL DEFAULT 10 CHECK (max_score > 0),
    is_active    INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

CREATE TABLE IF NOT EXISTS rfp_runs (
    rfp_run_id        TEXT PRIMARY KEY,
    created_at        TEXT NOT NULL,
    status            TEXT NOT NULL,
    provider          TEXT,
    model             TEXT,
    criteria_snapshot TEXT,
    warnings          TEXT,
    run_json          TEXT
);

CREATE TABLE IF NOT EXISTS supplier_results (
    rfp_run_id        TEXT NOT NULL REFERENCES rfp_runs(rfp_run_id),
    supplier_name     TEXT NOT NULL,
    submission_date   TEXT NOT NULL,
    experience_rating REAL NOT NULL,
    absolute_score    REAL,
    ppi               REAL,
    final_rank        INTEGER,
    source_file       TEXT,
    result_json       TEXT,
    PRIMARY KEY (rfp_run_id, supplier_name)
);
"""

SEED_CRITERIA = [
    (1, "Technical Capability", "Architecture, integrations, scalability, technical fit", 30, 10, 1),
    (2, "Implementation Plan", "Timeline, milestones, staffing, risk plan", 20, 10, 1),
    (3, "Commercial Value", "Pricing clarity, total cost, assumptions", 20, 10, 1),
    (4, "Security & Compliance", "Controls, certifications, privacy, auditability", 20, 10, 1),
    (5, "Support & Experience", "Support model, similar projects, references", 10, 10, 1),
]


def connect(db_path: str | Path = DEFAULT_DB) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: str | Path = DEFAULT_DB, reset_criteria: bool = False) -> None:
    """Create tables and seed criteria if the table is empty (idempotent)."""
    conn = connect(db_path)
    try:
        with conn:
            conn.executescript(SCHEMA)
            if reset_criteria:
                conn.execute("DELETE FROM evaluation_criteria")
            if conn.execute("SELECT COUNT(*) FROM evaluation_criteria").fetchone()[0] == 0:
                conn.executemany(
                    "INSERT INTO evaluation_criteria VALUES (?,?,?,?,?,?)", SEED_CRITERIA
                )
    finally:
        conn.close()


# ----------------------------------------------------------------- criteria
def get_criteria(db_path=DEFAULT_DB, active_only: bool = True) -> list[dict]:
    sql = "SELECT * FROM evaluation_criteria"
    if active_only:
        sql += " WHERE is_active = 1"
    sql += " ORDER BY criterion_id"
    conn = connect(db_path)
    try:
        rows = [dict(r) for r in conn.execute(sql)]
    finally:
        conn.close()
    for r in rows:
        r["is_active"] = bool(r["is_active"])
    return rows


def update_criteria(rows: list[dict], db_path=DEFAULT_DB) -> None:
    conn = connect(db_path)
    try:
        with conn:
            for r in rows:
                conn.execute(
                    "UPDATE evaluation_criteria SET name=?, description=?, weight=?, "
                    "max_score=?, is_active=? WHERE criterion_id=?",
                    (
                        str(r["name"]).strip(),
                        str(r.get("description") or "").strip(),
                        float(r["weight"]),
                        float(r["max_score"]),
                        1 if r["is_active"] else 0,
                        int(r["criterion_id"]),
                    ),
                )
    finally:
        conn.close()


# --------------------------------------------------------------------- runs
def new_run_id() -> str:
    return "RFP-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4].upper()


def create_run(criteria: list[dict], provider: str, model: str, db_path=DEFAULT_DB) -> str:
    run_id = new_run_id()
    conn = connect(db_path)
    try:
        with conn:
            conn.execute(
                "INSERT INTO rfp_runs (rfp_run_id, created_at, status, provider, model, criteria_snapshot) "
                "VALUES (?,?,?,?,?,?)",
                (run_id, datetime.now(timezone.utc).isoformat(timespec="seconds"), "RUNNING",
                 provider, model, json.dumps(criteria)),
            )
    finally:
        conn.close()
    return run_id


def mark_run_failed(run_id: str, message: str, db_path=DEFAULT_DB) -> None:
    conn = connect(db_path)
    try:
        with conn:
            conn.execute(
                "UPDATE rfp_runs SET status='FAILED', warnings=? WHERE rfp_run_id=?",
                (json.dumps([message]), run_id),
            )
    finally:
        conn.close()


def save_run(run_result: dict, db_path=DEFAULT_DB) -> None:
    """Persist the complete result atomically (one transaction, one RFP_RUN_ID)."""
    run_id = run_result["rfp_run_id"]
    conn = connect(db_path)
    try:
        with conn:
            conn.execute(
                "UPDATE rfp_runs SET status=?, warnings=?, run_json=? WHERE rfp_run_id=?",
                ("COMPLETED", json.dumps(run_result["warnings"]), json.dumps(run_result), run_id),
            )
            conn.execute("DELETE FROM supplier_results WHERE rfp_run_id=?", (run_id,))
            for s in run_result["suppliers"]:
                conn.execute(
                    "INSERT INTO supplier_results VALUES (?,?,?,?,?,?,?,?,?)",
                    (run_id, s["supplier_name"], s["submission_date"], s["experience_rating"],
                     s["absolute_score"], s["ppi"], s["final_rank"], s.get("source_file"),
                     json.dumps(s)),
                )
    finally:
        conn.close()


def list_runs(db_path=DEFAULT_DB) -> list[dict]:
    conn = connect(db_path)
    try:
        return [dict(r) for r in conn.execute(
            "SELECT rfp_run_id, created_at, status, provider, model FROM rfp_runs "
            "ORDER BY created_at DESC, rfp_run_id DESC")]
    finally:
        conn.close()


def get_run(run_id: str, db_path=DEFAULT_DB) -> dict | None:
    conn = connect(db_path)
    try:
        row = conn.execute("SELECT run_json FROM rfp_runs WHERE rfp_run_id=?", (run_id,)).fetchone()
    finally:
        conn.close()
    return json.loads(row["run_json"]) if row and row["run_json"] else None
