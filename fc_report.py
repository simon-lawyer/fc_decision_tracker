#!/usr/bin/env python3
"""
FC Immigration JR Weekly Report Generator — Main Orchestrator.

This is the main script that ties everything together. It coordinates the
full pipeline from searching for cases to generating the final report.

THE PIPELINE (what happens when you run this script):
  1. Search the A2AJ API for all FC cases in the date range
  2. Filter to only immigration (IMM) cases
  3. Skip cases we've already processed (deduplication via the SQLite database)
  4. Fetch the full text of each new case
  5. Send each case to Claude for analysis (extract judge, lawyers, category, etc.)
     — Each case is normalized, reconciled, and saved to the database IMMEDIATELY
       after analysis. This means if the pipeline crashes partway through, the
       cases that already finished are safely saved.
  6. Generate a markdown report with ONLY the allowed cases
  7. Write the report to the output/ folder

HOW TO RUN:
  # Process last week's cases (the default):
  python fc_report.py

  # Process a specific week:
  python fc_report.py --start-date 2026-03-09 --end-date 2026-03-15

  # Just search and see what cases exist (no Claude API calls):
  python fc_report.py --dry-run

  # Save the report to a custom location:
  python fc_report.py --output my_report.md

WHAT IS #!/usr/bin/env python3?
  The first line (called a "shebang") tells the operating system which program
  to use to run this file. It means "find python3 on this system and use it."
  This lets you run the script directly as ./fc_report.py on Mac/Linux.
"""

# ── Standard library imports ─────────────────────────────────────────────────
# These are built into Python — no pip install needed.

# argparse: Handles command-line arguments (--start-date, --dry-run, etc.).
# When you run "python fc_report.py --dry-run", argparse is what parses
# that "--dry-run" flag and makes it available in your code.
import argparse

# asyncio: Python's async framework. We use it to run multiple Claude API
# calls concurrently (at the same time) for faster processing.
import asyncio

# os: Operating system utilities — file paths, creating directories, etc.
import os

# sys: System-level operations. Not heavily used here but imported for
# potential error handling.
import sys

# date: Represents calendar dates like 2026-03-20.
from datetime import date, timedelta

# ── Project imports ──────────────────────────────────────────────────────────
# These import from the other .py files in this project.

from config import ANTHROPIC_API_KEY
from a2aj_client import search_fc_cases, fetch_case_text, filter_imm_cases
from case_analyzer import analyze_cases_concurrent
from normalizer import normalize_case, reconcile
from db_manager import get_processed_citations, save_cases
from models import CaseSearchResult


def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments.

    WHAT ARE COMMAND-LINE ARGUMENTS?
      When you run a script from the terminal, you can pass extra options:
        python fc_report.py --start-date 2026-03-09 --end-date 2026-03-15

      argparse reads these options and makes them available as Python variables.

    Returns:
        An argparse.Namespace object where you can access the arguments as
        attributes, e.g., args.start_date, args.dry_run, etc.
    """
    # Create a parser with a description that shows up when you run:
    #   python fc_report.py --help
    parser = argparse.ArgumentParser(
        description="Generate weekly FC immigration JR report."
    )

    # Define each command-line argument.
    # type=str means the value should be treated as a string.
    # help=... is the description shown in --help output.
    parser.add_argument(
        "--start-date",
        type=str,
        help="Start date (YYYY-MM-DD). Default: previous Monday.",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        help="End date (YYYY-MM-DD). Default: previous Sunday.",
    )
    # action="store_true" means this is a flag (no value needed).
    # If --dry-run is present, args.dry_run = True. Otherwise, False.
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Search and filter only — skip analysis and report generation.",
    )

    # parse_args() reads sys.argv (the actual command-line input) and returns
    # the parsed values.
    return parser.parse_args()


def run_pipeline(start_date: str, end_date: str, dry_run: bool) -> None:
    """
    Run the case ingestion pipeline: search, filter, analyze, save to database.

    Args:
        start_date:  Start of the date range (YYYY-MM-DD), e.g., "2026-03-09"
        end_date:    End of the date range (YYYY-MM-DD), e.g., "2026-03-15"
        dry_run:     If True, only search and list cases — don't analyze.
    """

    # ── FAIL-FAST: Check for the Anthropic API key ────────────────────────
    # We need the API key to send cases to Claude for analysis (Step 5).
    # If it's missing, there's no point doing all the A2AJ searching first
    # only to fail later. In dry-run mode, we skip this check because
    # Claude is never called.
    if not dry_run and not ANTHROPIC_API_KEY:
        print("ERROR: ANTHROPIC_API_KEY is not set.")
        print("  Add it to your .env file:  ANTHROPIC_API_KEY=sk-ant-...")
        print("  Or export it:              export ANTHROPIC_API_KEY=sk-ant-...")
        sys.exit(1)

    # ── STEP 1: Search A2AJ for all FC cases in the date range ──────────
    # This calls the A2AJ API and finds ALL Federal Court cases decided in
    # the given week (both English and French). The filtering to IMM cases
    # happens in the next step.
    print(f"Searching A2AJ for FC cases ({start_date} to {end_date})...")
    all_cases = search_fc_cases(start_date, end_date)
    print(f"  Found {len(all_cases)} FC cases.")

    # If the API returned nothing (rare, but possible for holidays), stop here.
    if not all_cases:
        print("No cases found. Exiting.")
        return

    # ── STEP 2: Filter to immigration (IMM) cases only ───────────────────
    # Out of all the FC JR cases, we only care about immigration ones.
    # This step fetches the first 500 chars of each case and checks for
    # an "IMM-" docket number.
    print("Filtering to immigration (IMM) cases...")
    imm_cases = filter_imm_cases(all_cases)
    print(f"  {len(imm_cases)} IMM cases identified.")

    if not imm_cases:
        print("No IMM cases found. Exiting.")
        return

    # ── DRY RUN: Just list the cases and stop ────────────────────────────
    # In dry-run mode, we show what we found but don't fetch full text,
    # call Claude, or generate a report. Useful for testing/debugging.
    if dry_run:
        print("\n-- DRY RUN: Cases found --")
        for case in imm_cases:
            # Clean up the date — remove the time/timezone part if present.
            case_date = case.date.split("T")[0] if "T" in case.date else case.date
            print(f"  {case.citation} — {case.name} ({case_date})")
        print(f"\nTotal: {len(imm_cases)} IMM cases.")
        return

    # ── STEP 3: Skip cases we've already processed ───────────────────────
    # Check the database for citations we've already analyzed in a previous
    # run. This prevents duplicate work (and duplicate Claude API charges)
    # if you run the script twice for the same week.
    processed = get_processed_citations()

    # List comprehension: keep only cases whose citation is NOT in the
    # already-processed set.
    new_cases = [c for c in imm_cases if c.citation not in processed]

    skipped = len(imm_cases) - len(new_cases)
    if skipped:
        print(f"  Skipping {skipped} already-processed case(s).")

    if not new_cases:
        print("All cases already processed.")
        return

    # ── STEP 4: Fetch the full text of each new case ─────────────────────
    # Now we need the complete decision text for Claude to analyze.
    # This is a separate step from the IMM filtering (which only fetched
    # the first 500 characters).
    print(f"Fetching full text for {len(new_cases)} new case(s)...")

    # Build a list of (text, metadata) tuples for the cases we successfully fetch.
    # We use a list of tuples because the analyzer needs both the text AND the
    # metadata (citation, name, url) for each case.
    cases_with_text: list[tuple[str, CaseSearchResult]] = []
    for case in new_cases:
        try:
            # Fetch the entire case text (no end_char limit).
            text = fetch_case_text(case.citation)
            if text:
                cases_with_text.append((text, case))
                print(f"  Fetched: {case.citation}")
            else:
                print(f"  Warning: Empty text for {case.citation}, skipping.")
        except Exception as e:
            # If one case fails to download, skip it and continue with the rest.
            print(f"  Error fetching {case.citation}: {e}")

    if not cases_with_text:
        print("No case text retrieved. Exiting.")
        return

    # ── STEP 5: Analyze all cases with Claude (with incremental saving) ──
    # Send each case's full text to Claude and extract structured data
    # (judge, lawyers, category, disposition, summary, etc.).
    # This runs up to 3 cases at a time for speed (see MAX_CONCURRENT_ANALYSES).
    #
    # INCREMENTAL SAVING: Instead of waiting for ALL cases to finish before
    # saving anything, we save each case to database as soon as it's done. This way,
    # if the pipeline crashes after analyzing 10 of 15 cases, those 10 are
    # already safely in the database. On the next run, they'll be skipped as
    # duplicates and the pipeline picks up where it left off.
    week_processed = start_date   # Use the Monday date as the "week processed" marker
    print(f"Analyzing {len(cases_with_text)} case(s) with Claude...")

    # We need existing database rows for reconciliation (typo detection).
    # Load them once here so we don't re-query the database for every single case.
    from db_manager import load_master
    existing_rows = load_master()

    # This list collects all successful extractions so we can still print
    # a disposition summary and generate the report at the end.
    extractions: list = []

    def on_case_done(extraction):
        """
        Callback that runs each time a single case finishes analysis.

        WHAT IS A CALLBACK?
          A callback is a function you pass to another function, saying
          "call this when something happens." Here, we're telling
          analyze_cases_concurrent: "every time you finish analyzing a case,
          call this function with the result."

        This function:
          1. Normalizes the extracted data (clean up names, etc.)
          2. Reconciles against existing database data (flags typos)
          3. Saves the case to database immediately
          4. Adds it to our running list of results
        """
        # ── Normalize ────────────────────────────────────────────────
        # Clean up judge names (strip honorifics → surname only), nationalities
        # (adjective → country name), and lawyer names (whitespace cleanup).
        # This ensures consistent values for filtering and analysis.
        normalized = normalize_case(extraction)

        # ── Reconcile ────────────────────────────────────────────────
        # Compare new values against what's already in the database.
        # Flags potential typos or inconsistencies (e.g., "Browuer" vs "Brouwer").
        # This is a human-review step — it prints warnings but doesn't block.
        # We pass a single-item list because reconcile() expects a list.
        reconcile([normalized], existing_rows)

        # ── Save to database immediately ──────────────────────────────────
        # save_cases() handles deduplication internally, so it's safe to
        # call it after each case — if the same citation is already in
        # the database, it will be skipped automatically.
        save_cases([normalized])
        print(f"  Saved {normalized.citation} to database.")

        # ── Track in our running list ────────────────────────────────
        # We still collect all results so we can print a summary and
        # generate the report at the end of the pipeline.
        extractions.append(normalized)

    # asyncio.run() is the bridge between regular Python code and async code.
    # It starts the async event loop, runs our concurrent analysis, and returns
    # the results when everything is done.
    # The on_case_done callback saves each case to database as soon as it finishes.
    asyncio.run(
        analyze_cases_concurrent(cases_with_text, week_processed, on_case_done)
    )
    print(f"  Successfully extracted data from {len(extractions)} case(s).")

    # ── Done — print disposition breakdown ──────────────────────────────
    allowed_new = [c for c in extractions if c.disposition in ("allowed", "granted_in_part")]
    dismissed_new = [c for c in extractions if c.disposition == "dismissed"]
    print(f"\n  Disposition breakdown (new cases):")
    print(f"    Allowed:          {len(allowed_new)}")
    print(f"    Dismissed:        {len(dismissed_new)}")
    other_disp = len(extractions) - len(allowed_new) - len(dismissed_new)
    if other_disp:
        print(f"    Other:            {other_disp}")


def main() -> None:
    """
    Entry point: parse command-line arguments, set defaults, and run the pipeline.
    """
    args = parse_args()

    # If the user specified dates, use those. Otherwise, default to the last
    # 14 days — wide enough to catch any cases that appear with a lag on A2AJ.
    if args.start_date and args.end_date:
        start_date = args.start_date
        end_date = args.end_date
    else:
        today = date.today()
        start_date = (today - timedelta(days=14)).isoformat()
        end_date = today.isoformat()

    run_pipeline(start_date, end_date, args.dry_run)


# ── Script entry point ───────────────────────────────────────────────────────
#
# This is a Python idiom that means:
#   "Only run main() if this file is being executed directly (not imported)."
#
# When you run "python fc_report.py", Python sets __name__ to "__main__",
# so the condition is True and main() gets called.
#
# If another file does "import fc_report", __name__ would be "fc_report"
# (not "__main__"), so main() would NOT run — the file would just make its
# functions available for import.
if __name__ == "__main__":
    main()
