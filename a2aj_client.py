"""
A2AJ REST API client for searching and fetching Federal Court cases.

Uses the public API at https://api.a2aj.ca (no authentication required).

HOW THIS MODULE WORKS:
  1. search_fc_cases()  — Searches for all FC "judicial review" cases in a date range.
                          This is a broad search that returns ALL JR cases, not just
                          immigration ones.
  2. filter_imm_cases() — Takes the broad search results and filters down to only
                          immigration cases by checking for an "IMM-xxxx" docket number
                          in the first 500 characters of each case. Only IMM-docket cases
                          are included — T-docket cases (citizenship, mandamus, etc.) are
                          excluded even if they are immigration-related.
  3. fetch_case_text()  — Downloads the full text of a single case by its citation.
                          Used both for the IMM filtering (partial fetch) and for
                          getting the complete text to send to Claude (full fetch).

WHAT IS A REST API?
  A REST API is a web service you can call by making HTTP requests to URLs.
  In this case, we make GET requests (like opening a URL in your browser) to
  endpoints like https://api.a2aj.ca/search?query=... and get back JSON data.

WHAT IS httpx?
  httpx is a Python library for making HTTP requests. It's similar to the
  popular 'requests' library but with better async support. We use it to
  call the A2AJ API endpoints.
"""

# 're' is Python's regular expression module. We use it to search for
# patterns in text — specifically, the "IMM-1234" docket number pattern.
import re

# httpx is our HTTP client library for making web requests to the A2AJ API.
import httpx

# Import our configuration values — the API URL, dataset name, and page size.
from config import A2AJ_BASE_URL, A2AJ_DATASET, A2AJ_SEARCH_PAGE_SIZE

# Import our data model for search results.
from models import CaseSearchResult

# ── Constants ─────────────────────────────────────────────────────────────────

# This is a "compiled regular expression" (regex) pattern.
# It matches strings like "IMM-1234" or "IMM-56789" — the docket numbers
# used for immigration cases in Federal Court.
#
# Breaking down the pattern:
#   IMM-   = the literal text "IMM-"
#   \d+    = one or more digits (0-9)
#
# re.IGNORECASE means it will also match "imm-1234" or "Imm-1234".
#
# We compile it once here (instead of in the function) for performance —
# compiling a regex takes a tiny bit of time, and we'll use this pattern
# many times (once per case).
#
# WHY ONLY IMM- DOCKETS?
#   Federal Court immigration cases use IMM- docket numbers. Other immigration-
#   adjacent cases (citizenship, some mandamus) use T- dockets. We intentionally
#   exclude T-docket cases — this report focuses specifically on IMM JR cases.
IMM_DOCKET_PATTERN = re.compile(r"IMM-\d+", re.IGNORECASE)

# How long to wait (in seconds) for the API to respond before giving up.
# 30 seconds is generous — most requests complete in under 5 seconds.
REQUEST_TIMEOUT = 30.0


def search_fc_cases(start_date: str, end_date: str) -> list[CaseSearchResult]:
    """
    Search the A2AJ API for all Federal Court judicial review cases in a date range.

    This performs a BROAD search — it finds ALL FC cases mentioning "judicial review",
    not just immigration ones. The filtering to IMM cases happens later in
    filter_imm_cases().

    The search supports pagination: the API returns at most 50 results at a time.
    If there are more than 50, we keep requesting the next page until we've
    collected them all.

    Args:
        start_date: Start of the date range in "YYYY-MM-DD" format (e.g., "2026-03-09")
        end_date:   End of the date range in "YYYY-MM-DD" format (e.g., "2026-03-15")

    Returns:
        A list of CaseSearchResult objects — one for each case found.
        Could be empty if no cases were decided in that date range.
    """
    # This list will accumulate all results across all pages.
    all_results = []

    # 'offset' tracks our position in the paginated results.
    # offset=0 means "start from the first result",
    # offset=50 means "start from the 51st result", etc.
    offset = 0

    # Keep requesting pages until we've gotten all results.
    # "while True" creates an infinite loop — we break out of it when done.
    while True:
        # Build the query parameters for the API request.
        # These get appended to the URL as ?query=...&dataset=...&start_date=... etc.
        params = {
            "query": '"judicial review"',      # Search for this exact phrase
            "dataset": A2AJ_DATASET,           # "FC" — Federal Court only
            "start_date": start_date,          # Only cases from this date onward
            "end_date": end_date,              # Only cases up to this date
            "size": A2AJ_SEARCH_PAGE_SIZE,     # How many results per page (50)
            "sort_results": "newest_first",    # Most recent cases first
            "offset": offset,                  # Skip this many results (for pagination)
        }

        # Make the actual HTTP GET request to the A2AJ search endpoint.
        # This is like opening this URL in your browser, but programmatically:
        #   https://api.a2aj.ca/search?query="judicial review"&dataset=FC&...
        response = httpx.get(
            f"{A2AJ_BASE_URL}/search",
            params=params,
            timeout=REQUEST_TIMEOUT,
        )

        # raise_for_status() will throw an error if the request failed
        # (e.g., server returned a 404 Not Found or 500 Internal Server Error).
        # If everything is fine (200 OK), it does nothing.
        response.raise_for_status()

        # Parse the JSON response body into a Python dictionary.
        # The API returns something like: {"results": [{...}, {...}, ...]}
        data = response.json()

        # Extract the list of case results. If "results" key is missing
        # for some reason, default to an empty list.
        results = data.get("results", [])

        # If this page returned zero results, we've gone past the end — stop.
        if not results:
            break

        # Convert each raw API result (a dictionary) into our CaseSearchResult model.
        # The API uses field names like "citation_en" and "name_en" (with _en suffix
        # because the API supports both English and French). We map them to our
        # simpler field names.
        for item in results:
            case = CaseSearchResult(
                citation=item["citation_en"],           # e.g., "2026 FC 348"
                name=item["name_en"],                   # e.g., "Famugbode v. Canada (...)"
                date=item["document_date_en"],          # e.g., "2026-03-13T00:00:00+00:00"
                url=item["url_en"],                     # Link to full decision
                snippet=item.get("snippet", ""),        # Short text excerpt (may be empty)
            )
            all_results.append(case)

        # PAGINATION CHECK: Did we get a full page of results?
        # If yes, there might be more results on the next page.
        # If no (e.g., we got 23 results but page size is 50), we've reached the end.
        if len(results) < A2AJ_SEARCH_PAGE_SIZE:
            break

        # Move to the next page by advancing the offset.
        offset += A2AJ_SEARCH_PAGE_SIZE

    return all_results


def fetch_case_text(citation: str, end_char: int = -1) -> str:
    """
    Fetch the full text (or a partial preview) of a case from the A2AJ API.

    This is used in two ways:
      1. Partial fetch (end_char=500): To check if a case has an IMM docket number
         in the first 500 characters. This is cheap and fast.
      2. Full fetch (end_char=-1): To get the entire decision text for Claude to analyze.
         This can be thousands of characters long.

    Args:
        citation: The case citation to fetch, e.g., "2026 FC 348"
        end_char:  How many characters to fetch.
                   -1 means "fetch the entire document" (this is the default).
                   500 means "fetch only the first 500 characters".

    Returns:
        The case text as a string. Returns an empty string if the case wasn't found.
    """
    # Build the query parameters for the fetch endpoint.
    params = {
        "citation": citation,           # Which case to fetch
        "doc_type": "cases",            # We want case decisions (not legislation, etc.)
        "output_language": "en",        # English version
        "start_char": 0,               # Start from the beginning of the document
    }

    # Only add end_char if we want a partial fetch.
    # If end_char is -1 (the default), we omit it and the API returns everything.
    if end_char > 0:
        params["end_char"] = end_char

    # Make the HTTP GET request to the fetch endpoint.
    response = httpx.get(
        f"{A2AJ_BASE_URL}/fetch",
        params=params,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()

    # The response has a "results" array. For a fetch-by-citation, it should
    # contain exactly one result (or zero if the citation wasn't found).
    results = data.get("results", [])
    if not results:
        return ""

    # Extract the case text from the first (and only) result.
    # "unofficial_text_en" is the field name the API uses for the English text.
    return results[0].get("unofficial_text_en", "")


def filter_imm_cases(cases: list[CaseSearchResult]) -> list[CaseSearchResult]:
    """
    Filter a list of search results to only include IMM-docket immigration cases.

    HOW IT WORKS:
    The broad search returns ALL Federal Court judicial review cases — immigration,
    tax, IP, etc. We need to filter down to just immigration cases with IMM- docket
    numbers (e.g., "IMM-1234-25").

    For each case, we fetch just the first 500 characters (which includes the
    header/docket info) and check for an "IMM-xxxx" pattern using regex.

    NOTE: This intentionally excludes T-docket cases, even if they are immigration-
    related (e.g., citizenship cases, some mandamus applications). This report
    focuses specifically on IMM judicial reviews.

    Args:
        cases: The full list of CaseSearchResult objects from search_fc_cases().

    Returns:
        A filtered list containing only the cases with IMM docket numbers.
    """
    imm_cases = []

    for case in cases:
        try:
            # Fetch just the first 500 characters of the case — enough to see
            # the docket number in the header, but much faster than fetching
            # the entire decision (which could be 50,000+ characters).
            text_preview = fetch_case_text(case.citation, end_char=500)

            # Use our regex pattern to search the preview for "IMM-" followed
            # by digits. .search() returns a match object if found, or None.
            if IMM_DOCKET_PATTERN.search(text_preview):
                imm_cases.append(case)

        except httpx.HTTPError as e:
            # If the API request fails for one case (e.g., network timeout),
            # print a warning and skip it rather than crashing the whole script.
            # The case can be picked up on the next run.
            print(f"  Warning: Could not fetch preview for {case.citation}: {e}")
            continue

    return imm_cases
