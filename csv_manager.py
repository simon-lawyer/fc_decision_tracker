"""
CSV master document manager for accumulating extracted case data across weeks.

The master CSV (data/cases_master.csv) stores ALL processed cases — both allowed
and dismissed — so that:
  1. Re-runs can skip already-processed cases (no duplicate API calls to Claude)
  2. The data can be used for analysis or statistics over time
  3. We have a permanent record of every case we've processed

WHAT IS A CSV?
  CSV stands for "Comma-Separated Values". It's a simple text file format where
  each line is a row of data and values are separated by commas. The first line
  is usually the header (column names). CSVs can be opened in Excel, Google Sheets,
  or any text editor.

  Example:
    citation,case_name,date,disposition
    2026 FC 348,Famugbode v. Canada,2026-03-13,dismissed
    2026 FC 338,Li Li v. Canada,2026-03-13,allowed
"""

# Python's built-in 'csv' module handles reading and writing CSV files.
# It takes care of tricky things like values that contain commas or quotes.
import csv

# 'json' is used to serialize list/object fields (like legal_issues and
# irpa_sections) into JSON strings for CSV storage, and to deserialize
# them back when loading.
import json

# 'os' for file path operations and checking if files exist.
import os

from models import CaseExtraction, LegalIssue
from config import MASTER_CSV_PATH, DATA_DIR

# ── Column definitions ────────────────────────────────────────────────────────

# This list defines the exact columns (and their order) in the master CSV.
# It must match the fields in the CaseExtraction model in models.py.
# If you add a new field to CaseExtraction, add it here too.
CSV_COLUMNS = [
    "citation",
    "case_name",
    "date",
    "url",
    "judge",
    "lawyer_applicant",
    "lawyer_respondent",
    "category",
    "disposition",
    "decision_maker",
    "visa_office",
    "irpa_sections",
    "legal_issues",
    "nationality",
    "nature_of_persecution",
    "facts_summary",
    "error_statement",
    "error_explanation",
    "certified_question",
    "week_processed",
]

# Fields that contain lists or objects and need to be stored as JSON strings
# in the CSV. When writing, we serialize them to JSON. When reading, we
# deserialize them back.
JSON_FIELDS = {"irpa_sections", "legal_issues"}


def load_master() -> list[dict]:
    """
    Load the entire master CSV file into memory as a list of dictionaries.

    Each row becomes a dictionary where keys are column names and values are
    the cell values. For example:
        {"citation": "2026 FC 348", "case_name": "Famugbode v. Canada", ...}

    If the CSV file doesn't exist yet (first run), returns an empty list.

    Returns:
        A list of dictionaries, one per row in the CSV.
    """
    # Check if the file exists yet. On the very first run, it won't.
    if not os.path.exists(MASTER_CSV_PATH):
        return []

    # Open the file for reading.
    # - "r" means read mode (as opposed to "w" for write or "a" for append).
    # - newline="" is required by the csv module to handle line endings correctly.
    # - encoding="utf-8" ensures we can handle accented characters in names
    #   (common in Canadian immigration cases with names from many languages).
    with open(MASTER_CSV_PATH, "r", newline="", encoding="utf-8") as f:
        # csv.DictReader reads the CSV and automatically uses the first row
        # (the header) as dictionary keys. Each subsequent row becomes a dict.
        reader = csv.DictReader(f)
        # list() converts the reader (which reads one row at a time) into a
        # complete list of all rows. This loads the entire file into memory.
        return list(reader)


def get_processed_citations() -> set[str]:
    """
    Get a set of all case citations that have already been processed.

    This is used for deduplication — before analyzing a case, we check if
    its citation is already in this set. If so, we skip it to avoid
    wasting Claude API credits on a case we've already processed.

    WHY A SET?
      A Python set is an unordered collection of unique values. Looking up
      whether a value is "in" a set is extremely fast (O(1) time), compared
      to searching through a list (O(n) time). Since we check every case
      against this collection, using a set makes it efficient.

    Returns:
        A set of citation strings, e.g., {"2026 FC 348", "2026 FC 338", ...}
    """
    rows = load_master()
    # This is a "set comprehension" — similar to a list comprehension but
    # creates a set instead. It pulls the "citation" value from each row.
    return {row["citation"] for row in rows}


def save_cases(new_cases: list[CaseExtraction]) -> None:
    """
    Append new cases to the master CSV file, skipping any duplicates.

    If the CSV file doesn't exist yet, it creates it with a header row first.
    If a case's citation is already in the CSV, it's skipped (not duplicated).

    HOW APPENDING WORKS:
      Opening a file with mode "a" (append) adds new content to the END of the
      file without erasing what's already there. This is different from "w" (write)
      which would overwrite the entire file.

    Args:
        new_cases: A list of CaseExtraction objects to save. Can contain cases
                   that are already in the CSV — duplicates are automatically skipped.
    """
    # If there are no cases to save, do nothing.
    if not new_cases:
        return

    # Make sure the data/ directory exists. os.makedirs() creates the directory
    # (and any parent directories) if they don't exist. exist_ok=True means
    # "don't raise an error if the directory already exists."
    os.makedirs(DATA_DIR, exist_ok=True)

    # Load the set of citations already in the CSV for deduplication.
    existing_citations = get_processed_citations()

    # Filter out any cases whose citation is already in the CSV.
    # This is a "list comprehension" — a concise way to filter a list.
    # It's equivalent to:
    #   unique_new = []
    #   for c in new_cases:
    #       if c.citation not in existing_citations:
    #           unique_new.append(c)
    unique_new = [c for c in new_cases if c.citation not in existing_citations]

    # If all cases were duplicates, nothing to do.
    if not unique_new:
        return

    # Check if the file already exists. We need to know this because:
    # - If the file is NEW, we need to write the header row first.
    # - If the file ALREADY EXISTS, we just append data rows (no header).
    file_exists = os.path.exists(MASTER_CSV_PATH)

    # Open the file in append mode ("a").
    # - "a" means we add to the end of the file (not overwrite).
    # - newline="" and encoding="utf-8" are the same as in load_master().
    with open(MASTER_CSV_PATH, "a", newline="", encoding="utf-8") as f:
        # csv.DictWriter writes dictionaries as CSV rows.
        # fieldnames=CSV_COLUMNS tells it the column order.
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)

        # Write the header row only if this is a brand new file.
        if not file_exists:
            writer.writeheader()

        # Write each case as a new row in the CSV.
        for case in unique_new:
            # .model_dump() is a Pydantic method that converts the model object
            # into a plain Python dictionary, e.g.:
            #   {"citation": "2026 FC 348", "case_name": "Famugbode v. Canada", ...}
            row = case.model_dump()

            # Some fields (irpa_sections, legal_issues) are lists/objects in Python
            # but need to be stored as JSON strings in the CSV. We serialize them here.
            # For example: [{"primary": "reasonableness", "secondary": "..."}]
            # becomes the string '[{"primary": "reasonableness", "secondary": "..."}]'
            for field in JSON_FIELDS:
                if field in row:
                    row[field] = json.dumps(row[field])

            writer.writerow(row)
