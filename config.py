"""
Configuration and date helpers for the FC Immigration JR Weekly Report Generator.

This file is the central place for all settings used across the project.
Other files import values from here so that if you need to change something
(like a URL or file path), you only change it in one place.

Think of this file as the "control panel" for the whole project.
"""

# 'os' lets us interact with the operating system — read environment variables,
# build file paths, etc.
import os

# 'date' represents a calendar date (like 2026-03-20).
# 'timedelta' represents a duration (like "7 days") that we can add/subtract from dates.
from datetime import date, timedelta

# 'load_dotenv' reads the .env file in this folder and loads its values as
# environment variables. This is how we keep secrets (like API keys) out of
# the source code — they live in .env which is .gitignored.
from dotenv import load_dotenv

# Actually load the .env file now. After this call, os.getenv("ANTHROPIC_API_KEY")
# will return whatever value is set in the .env file.
load_dotenv()


# ── API Keys ──────────────────────────────────────────────────────────────────

# Read the Anthropic API key from the environment. This key authenticates us
# with Claude's API so we can send case text for analysis.
# If the .env file is missing or doesn't have this key, this will be None,
# and the Claude API calls will fail with an auth error.
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")


# ── A2AJ API ──────────────────────────────────────────────────────────────────

# Base URL for the A2AJ (Access to Administrative Justice) REST API.
# This is a free, public API that provides Canadian court decisions.
# No authentication needed — we just make HTTP GET requests to it.
A2AJ_BASE_URL = "https://api.a2aj.ca"

# We only want Federal Court ("FC") cases. The API has other datasets
# (like the Supreme Court, Tax Court, etc.) but we filter to FC only.
A2AJ_DATASET = "FC"

# How many results to request per page from the search API.
# If there are more than 50 results, we paginate (request the next 50, etc.).
A2AJ_SEARCH_PAGE_SIZE = 50


# ── Claude Model ──────────────────────────────────────────────────────────────

# Which Claude model to use for analyzing case text. Sonnet is a good balance
# of speed, cost, and quality. The date suffix is the model version.
CLAUDE_MODEL = "claude-sonnet-4-20250514"

# How many cases to analyze at the same time. We limit this to 3 to avoid
# overwhelming the API with too many simultaneous requests.
# Higher = faster but more likely to hit rate limits.
MAX_CONCURRENT_ANALYSES = 3


# ── Category ordering for the report ─────────────────────────────────────────

# The order in which case categories appear in the weekly markdown report.
# Each case gets classified into one of these categories by Claude.
CATEGORY_ORDER = [
    "RAD", "PRRA", "RPD", "IAD", "H&C", "Visa",
    "ID Admissibility", "Misrepresentation", "Inadmissibility",
    "Detention", "Stay", "Procedural", "Other",
]


# ── File paths ────────────────────────────────────────────────────────────────

# __file__ is a special Python variable that holds the path to THIS file (config.py).
# os.path.abspath() converts it to a full/absolute path (e.g., /Users/simon/...).
# os.path.dirname() strips the filename, leaving just the directory.
# So BASE_DIR = the folder where config.py lives (the project root).
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Build paths to the data/ and output/ subdirectories.
# os.path.join() combines path parts in a cross-platform way
# (handles / on Mac/Linux and \ on Windows).
DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

# Path to the master CSV file that accumulates all processed cases over time.
MASTER_CSV_PATH = os.path.join(DATA_DIR, "cases_master.csv")


def get_previous_week_range() -> tuple[date, date]:
    """
    Calculate the date range for the previous Monday through Sunday.

    This is used as the default date range when you run the script without
    specifying --start-date and --end-date. For example, if today is
    Wednesday March 18, this returns (Monday March 9, Sunday March 15).

    Returns:
        A tuple of two date objects: (last_monday, last_sunday).
        For example: (date(2026, 3, 9), date(2026, 3, 15))
    """
    today = date.today()

    # .weekday() returns 0 for Monday, 1 for Tuesday, ..., 6 for Sunday.
    # So if today is Wednesday, days_since_monday = 2.
    days_since_monday = today.weekday()

    # To find LAST week's Monday, we first go back to THIS week's Monday
    # (subtract days_since_monday), then go back 7 more days.
    # Example: Wednesday March 18 → subtract 2 → Monday March 16 → subtract 7 → Monday March 9
    last_monday = today - timedelta(days=days_since_monday + 7)

    # Sunday is 6 days after Monday.
    last_sunday = last_monday + timedelta(days=6)

    return last_monday, last_sunday
