"""
Database manager for accumulating extracted case data across weeks.

Uses SQLite via FastHTML's fastlite module. The database (data/cases.db)
stores ALL processed cases — both allowed and dismissed — so that:
  1. Re-runs can skip already-processed cases (no duplicate API calls to Claude)
  2. The data can be used for analysis or statistics over time
  3. We have a permanent record of every case we've processed

WHY SQLITE INSTEAD OF CSV?
  SQLite is a file-based database that doesn't need a separate server.
  Compared to CSV:
    - Supports concurrent reads/writes safely (no file corruption)
    - Proper indexing for fast lookups
    - Works well on Railway with a persistent volume
    - No need to load the entire dataset into memory for a single query
"""

import json

from models import CaseExtraction
from db import cases

# Fields that contain lists or objects and are stored as JSON strings
# in the database. When writing, we serialize them to JSON. When reading,
# we deserialize them back.
JSON_FIELDS = {"irpa_sections", "legal_issues"}


def load_master() -> list[dict]:
    """
    Load all cases from the database as a list of dictionaries.

    Each row becomes a dictionary where keys are column names and values are
    the cell values. For example:
        {"citation": "2026 FC 348", "case_name": "Famugbode v. Canada", ...}

    Returns:
        A list of dictionaries, one per row in the database.
    """
    # cases() with no arguments returns all rows as dataclass instances.
    # We convert each to a dict for compatibility with existing code.
    rows = cases()
    return [_row_to_dict(row) for row in rows]


def get_processed_citations() -> set[str]:
    """
    Get a set of all case citations that have already been processed.

    This is used for deduplication — before analyzing a case, we check if
    its citation is already in this set. If so, we skip it to avoid
    wasting Claude API credits on a case we've already processed.

    Returns:
        A set of citation strings, e.g., {"2026 FC 348", "2026 FC 338", ...}
    """
    rows = cases()
    return {row.citation for row in rows}


def save_cases(new_cases: list[CaseExtraction]) -> None:
    """
    Save new cases to the database, skipping any duplicates.

    Uses upsert (insert-or-update) so that if a case with the same citation
    already exists, it won't be duplicated.

    Args:
        new_cases: A list of CaseExtraction objects to save. Can contain cases
                   that are already in the database — duplicates are automatically
                   handled by the upsert.
    """
    if not new_cases:
        return

    for case in new_cases:
        # Convert the Pydantic model to a plain dict.
        row = case.model_dump()

        # Serialize list/object fields to JSON strings for storage.
        for field in JSON_FIELDS:
            if field in row:
                row[field] = json.dumps(row[field])

        # upsert: insert the row, or update it if a row with the same
        # primary key (citation) already exists.
        cases.upsert(row)


def _row_to_dict(row) -> dict:
    """Convert a fastlite dataclass row to a plain dictionary."""
    if hasattr(row, '__dict__'):
        return {k: v for k, v in row.__dict__.items() if not k.startswith('_')}
    return dict(row)
