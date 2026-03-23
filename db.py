"""
Database setup using FastHTML's fastlite (SQLite) module.

This replaces the CSV-based storage with a proper SQLite database.
SQLite is a file-based database that's perfect for this use case:
  - No separate database server needed
  - Works on Railway with a persistent volume
  - Supports proper queries, indexing, and concurrent access

HOW FASTLITE WORKS:
  fastlite is a thin wrapper around SQLite that lets you define tables
  using Python dataclasses. Each dataclass field becomes a column.
  It provides simple CRUD methods: insert(), get(), update(), delete().

  Complex fields (lists, nested objects) are stored as JSON text in the
  database and need to be serialized/deserialized manually.
"""

import os
from dataclasses import dataclass, field
from typing import Optional

from fastlite import database

from config import DATA_DIR

# ── Database connection ──────────────────────────────────────────────────────

# Store the SQLite file in the data/ directory alongside where the CSV used to live.
DB_PATH = os.path.join(DATA_DIR, "cases.db")

# Ensure the data directory exists before connecting.
os.makedirs(DATA_DIR, exist_ok=True)

# Create the database connection. fastlite enables WAL mode by default,
# which allows concurrent reads while writing.
db = database(DB_PATH)


# ── Table definition ─────────────────────────────────────────────────────────

@dataclass
class Case:
    """
    A Federal Court immigration case — mirrors the CaseExtraction Pydantic model.

    Fields that hold lists or objects (irpa_sections, legal_issues) are stored
    as JSON strings in the database. They must be serialized before insert and
    deserialized after retrieval.

    The citation is the primary key since each case has a unique citation
    (e.g., "2026 FC 348").
    """
    citation: str              # Primary key — e.g., "2026 FC 348"
    case_name: str = ""
    date: str = ""
    url: str = ""
    judge: str = ""
    lawyer_migrant: str = ""
    lawyer_respondent: str = ""
    category: str = ""
    disposition: str = ""
    decision_maker: Optional[str] = None
    visa_office: Optional[str] = None
    irpa_sections: str = "[]"           # JSON string — list of section references
    legal_issues: str = "[]"            # JSON string — list of {primary, secondary} objects
    nationality: Optional[str] = None
    nature_of_persecution: Optional[str] = None
    facts_summary: str = ""
    error_statement: Optional[str] = None
    error_explanation: Optional[str] = None
    certified_question: Optional[str] = None
    week_processed: str = ""


# Create the table if it doesn't exist. pk="citation" makes citation the primary key.
cases = db.create(Case, pk="citation")
