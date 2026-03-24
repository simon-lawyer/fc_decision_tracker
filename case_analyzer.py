"""
Case analysis using the Claude API.

Sends full case text to Claude Sonnet and extracts structured information
including judge, lawyers, category, disposition, and case summaries.

HOW THIS MODULE WORKS:
  1. We send the full text of a court decision to Claude along with a detailed
     prompt telling it exactly what information to extract.
  2. Claude reads the decision and returns a JSON object with all the fields
     we need (judge name, lawyers, category, disposition, summary, etc.).
  3. We parse that JSON and create a CaseExtraction model from it.

WHY USE AN AI FOR THIS?
  Court decisions are unstructured prose — there's no consistent format for
  where the judge's name appears, how lawyers are listed, or how the
  disposition is stated. An AI model like Claude can understand the text
  and extract the right information regardless of formatting variations.

WHAT IS ASYNC / CONCURRENCY?
  When we have 14 cases to analyze, we don't want to wait for each one to
  finish before starting the next. "Async" lets us send multiple requests
  at the same time (concurrently), which is much faster. We limit it to 3
  at a time to be polite to the API.
"""

# 'json' lets us parse JSON strings into Python dictionaries and vice versa.
import json

# 'asyncio' is Python's built-in library for writing concurrent (async) code.
# It lets us run multiple API calls at the same time instead of one at a time.
import asyncio

# 'Anthropic' is the official Python client for Claude's API.
# It handles authentication, request formatting, and response parsing.
from anthropic import Anthropic

# Import our configuration — API key, model name, and concurrency limit.
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, MAX_CONCURRENT_ANALYSES

# Import our data models.
from models import CaseSearchResult, CaseExtraction, LegalIssue

# ── Create the API client ─────────────────────────────────────────────────────

# Create a single Anthropic client instance that we'll reuse for all API calls.
# The api_key authenticates us — it's loaded from the .env file via config.py.
client = Anthropic(api_key=ANTHROPIC_API_KEY)

# ── Extraction prompt ─────────────────────────────────────────────────────────

# This is the prompt we send to Claude along with each case's text.
# It tells Claude exactly what to extract and how to format the response.
# The prompt is very specific to get consistent, predictable output.
#
# IMPORTANT: If you need to change what information is extracted (e.g., add a
# new field), you need to update BOTH this prompt AND the CaseExtraction model
# in models.py, AND the Case dataclass in db.py.
EXTRACTION_PROMPT = """You are a legal analyst extracting structured information from a Federal Court of Canada immigration judicial review decision.

IMPORTANT — PRIVACY: Do NOT include any personal names (of applicants, family members, or other individuals) in the facts_summary, error_statement, or error_explanation fields. Refer to individuals by their role only (e.g., "the applicant", "her spouse", "the principal applicant's son"). Do not reproduce personal information such as addresses, phone numbers, immigration file numbers, or other identifying details. Focus only on legally relevant information. Lawyer names and judge names are fine — they are public officers of the court.

IMPORTANT — LEGISLATIVE REFERENCES: When citing sections of IRPA or IRPR, include a short plain-language summary in square brackets after the section number. For example: "s.35 [war crimes/crimes against humanity]", "s.40(1)(a) [misrepresentation]", "s.96 [Convention refugee]", "s.97(1)(b) [risk to life/cruel treatment]", "s.36(1)(a) [serious criminality]", "s.48 [enforceable removal order]". Apply this format in all fields that reference legislation: irpa_sections, facts_summary, error_statement, error_explanation, and legal_issues.

Analyze the case text below and extract the following fields as JSON:

1. **judge**: The judge's SURNAME ONLY (e.g., "Southcott", "Aylen", "Brouwer"). Strip all honorifics, titles, and first names. Just the last name.
2. **lawyer_migrant**: The MIGRANT'S lawyer/counsel. In most cases the migrant is the applicant, but sometimes the Minister is the applicant (e.g., Minister's application to vacate refugee status). Always identify the lawyer representing the non-citizen / migrant / refugee / person subject to the immigration decision. Use "First Last" format (e.g., "Vakkas Bilsin"). If self-represented, return "Self-represented".
3. **lawyer_respondent**: The OTHER side's lawyer/counsel (usually the Crown / Minister's counsel, but the migrant's counsel if the Minister is the applicant). Same format as above.
4. **category**: Classify the case into exactly one of these categories:
   - "RAD" — judicial review of a Refugee Appeal Division decision
   - "PRRA" — judicial review of a Pre-Removal Risk Assessment decision
   - "RPD" — judicial review of a Refugee Protection Division decision (direct, no RAD appeal)
   - "IAD" — judicial review of an Immigration Appeal Division decision (sponsorship appeals, removal order appeals, residency obligation appeals)
   - "H&C" — judicial review of a humanitarian and compassionate application decision
   - "Visa" — judicial review of a visa/permit refusal (work permit, study permit, TRV, PR application)
   - "ID Admissibility" — judicial review of an Immigration Division admissibility hearing decision (where a s.44 report was referred to the ID for a formal hearing)
   - "Misrepresentation" — judicial review of a misrepresentation finding under s.40 IRPA (whether by an officer or the ID). This is distinct from Visa refusals — use this when misrepresentation is the central issue, not merely a ground cited in a visa refusal
   - "Inadmissibility" — judicial review of other inadmissibility findings (criminality under s.36, security under s.34, human rights violations under s.35, health grounds under s.38) that are NOT ID admissibility hearings and NOT misrepresentation. Typically these are officer-level findings in the context of a visa or PR application
   - "Detention" — judicial review of an Immigration Division detention review decision
   - "Stay" — application for a stay of removal (an order to pause deportation pending JR)
   - "Procedural" — costs decisions, reconsideration motions, motions to strike, jurisdiction disputes, or other procedural matters
   - "Other" — anything that doesn't fit the above categories (e.g., mandamus, cessation/vacation of refugee status)
   Note: If a case is a mandamus application, classify it by the underlying subject matter where possible (e.g., mandamus to compel a visa decision is "Visa"). Only use "Other" for mandamus if the underlying subject is unclear.
5. **disposition**: One of "allowed", "dismissed", or "granted_in_part"
   - Look at the judgment/order section at the end of the decision
   - For mandamus applications (seeking to compel a decision), treat the outcome the same way: if the Court grants mandamus, the disposition is "allowed"
6. **decision_maker**: The name of the underlying decision-maker whose decision is being reviewed (e.g., the RAD member, the visa officer, the ID member), if stated in the decision. Return null if the decision-maker is not named — do not guess or fill in generic terms like "the officer".
7. **visa_office**: For visa/permit cases, the visa office or processing centre where the decision was made (e.g., "New Delhi", "Manila", "Islamabad"), if stated. Null if not stated or not a visa case.
8. **irpa_sections**: List of relevant IRPA/IRPR sections cited in the decision, with a short plain-language summary in square brackets (e.g., ["s.96 [Convention refugee]", "s.97(1)(b) [risk to life/cruel treatment]", "s.40(1)(a) [misrepresentation]"]). Include the key provisions at issue, not every section mentioned in passing. Empty list if none are prominent.
9. **legal_issues**: A list of the legal issues the Court actually addressed in its analysis. You MUST populate this field — do not leave it empty. Each issue is an object with:
   - "primary": The standard of review or legal framework the Court applied. Typically one of: "reasonableness", "procedural fairness", or "correctness". Use whatever the Court actually identified as the applicable standard.
   - "secondary": The specific substantive issue within that framework. Be precise but concise — this is what a lawyer would use to find this case (e.g., "credibility findings lacked justification", "failed to assess IFA", "did not disclose extrinsic evidence").
   For dismissed cases, include all issues the Court considered and rejected. For allowed cases, include only the issue(s) on which the Court found error (the Court typically does not address remaining issues once it finds a basis to allow).
10. **nationality**: The migrant's country of origin as a COUNTRY NAME — not an adjective or territory name. Use "India" not "Indian", "Philippines" not "Filipino", "Palestine" not "Palestinian Territory", "China" not "Chinese". Null if not stated.
11. **nature_of_persecution**: For refugee/RAD/PRRA/RPD cases only — the type of persecution alleged (e.g., "political opinion", "ethnicity", "religion", "gender-based violence", "sexual orientation"). Set to null for non-refugee cases.
12. **facts_summary**: 2-3 sentence summary of the key facts. Do NOT use any personal names — use roles only (e.g., "the applicant", "the sponsor", "their child").
13. **error_statement**: If allowed or granted in part, one clear sentence stating what error the Court found. For mandamus cases, this should describe the unreasonable delay or failure to decide. Null if dismissed. No personal names.
14. **error_explanation**: If allowed or granted in part, 2-3 sentences explaining the error in more detail. Null if dismissed. No personal names.
15. **certified_question**: The certified question of general importance, if any. Null if none.

Return ONLY a JSON object with these exact field names. No markdown, no explanation."""


def extract_case_info(case_text: str, case_meta: CaseSearchResult, week_processed: str) -> CaseExtraction:
    """
    Send a single case's full text to Claude and extract structured information.

    This is the core function that talks to the Claude API. It:
      1. Sends the extraction prompt + case text to Claude
      2. Gets back a JSON string with all the extracted fields
      3. Parses that JSON into a Python dictionary
      4. Creates and returns a CaseExtraction model object

    Args:
        case_text:      The full text of the court decision (can be very long).
        case_meta:      The search result metadata for this case (citation, name, etc.).
                        We use this for fields that come from the search API rather
                        than from Claude's extraction.
        week_processed: The Monday date (as a string like "2026-03-09") of the week
                        this case is being processed. Used for tracking purposes.

    Returns:
        A CaseExtraction object with all fields populated.

    Raises:
        Various exceptions if the API call fails or the response can't be parsed.
    """
    # ── Call the Claude API ──────────────────────────────────────────────

    # client.messages.create() sends a message to Claude and waits for a response.
    # This is a synchronous (blocking) call — it won't return until Claude
    # has finished generating its response.
    response = client.messages.create(
        model=CLAUDE_MODEL,          # Which Claude model to use (Sonnet)
        max_tokens=2500,             # Maximum length of Claude's response (in tokens).
                                     # 2500 gives room for legal issues, IRPA sections, etc.
        messages=[
            {
                "role": "user",      # We're sending a message as the "user"
                "content": f"{EXTRACTION_PROMPT}\n\n---\n\nCASE TEXT:\n\n{case_text}",
            }
        ],
    )

    # ── Parse Claude's response ──────────────────────────────────────────

    # The response object contains a list of "content blocks". For a text response,
    # there's typically one block with a .text attribute containing Claude's reply.
    # .strip() removes any leading/trailing whitespace.
    raw_text = response.content[0].text.strip()

    # Sometimes Claude wraps its JSON in markdown code fences like:
    #   ```json
    #   {"judge": "Smith", ...}
    #   ```
    # We need to strip those fences to get the pure JSON.
    if raw_text.startswith("```"):
        lines = raw_text.split("\n")
        # Remove the first line (which is "```json" or just "```")
        # and filter out any closing "```" lines.
        lines = [l for l in lines[1:] if l.strip() != "```"]
        raw_text = "\n".join(lines)

    # json.loads() parses the JSON string into a Python dictionary.
    # For example: '{"judge": "Smith"}' becomes {"judge": "Smith"}
    extracted = json.loads(raw_text)

    # ── Clean up the date ────────────────────────────────────────────────

    # The date from the search API includes timezone info like "2026-03-13T00:00:00+00:00".
    # We only want the date part "2026-03-13", so we split on "T" and take the first part.
    case_date = case_meta.date
    if "T" in case_date:
        case_date = case_date.split("T")[0]

    # ── Build and return the CaseExtraction ──────────────────────────────

    # Some fields come from the search API metadata (citation, name, date, url)
    # and the rest come from Claude's extraction.
    #
    # .get(key, default) is a safe way to read from a dictionary — if the key
    # is missing, it returns the default value instead of crashing.
    # For required string fields, we default to "Unknown" or empty string.
    # For optional fields (like nationality), we default to None.
    # ── Parse legal issues ────────────────────────────────────────────────

    # Claude returns legal_issues as a list of dicts like:
    #   [{"primary": "reasonableness", "secondary": "credibility..."}, ...]
    # We convert each dict into a LegalIssue Pydantic model.
    raw_issues = extracted.get("legal_issues", [])
    legal_issues = [
        LegalIssue(primary=issue["primary"], secondary=issue["secondary"])
        for issue in raw_issues
        if "primary" in issue and "secondary" in issue
    ]

    return CaseExtraction(
        citation=case_meta.citation,
        case_name=case_meta.name,
        date=case_date,
        url=case_meta.url,
        judge=extracted.get("judge", "Unknown"),
        lawyer_migrant=extracted.get("lawyer_migrant", "Unknown"),
        lawyer_respondent=extracted.get("lawyer_respondent", "Unknown"),
        category=extracted.get("category", "Other"),
        disposition=extracted.get("disposition", "unknown"),
        decision_maker=extracted.get("decision_maker"),
        visa_office=extracted.get("visa_office"),
        irpa_sections=extracted.get("irpa_sections", []),
        legal_issues=legal_issues,
        nationality=extracted.get("nationality"),
        nature_of_persecution=extracted.get("nature_of_persecution"),
        facts_summary=extracted.get("facts_summary", ""),
        error_statement=extracted.get("error_statement"),
        error_explanation=extracted.get("error_explanation"),
        certified_question=extracted.get("certified_question"),
        week_processed=week_processed,
    )


async def analyze_cases_concurrent(
    cases_with_text: list[tuple[str, CaseSearchResult]],
    week_processed: str,
    on_case_done: "callable | None" = None,
) -> list[CaseExtraction]:
    """
    Analyze multiple cases concurrently (in parallel), with a concurrency limit.

    Instead of analyzing cases one at a time (which would be slow for 14 cases),
    this function sends up to MAX_CONCURRENT_ANALYSES (3) requests at the same time.
    As each one finishes, the next one starts. This is much faster overall.

    HOW ASYNC WORKS (simplified):
      - "async def" defines a function that can be paused and resumed.
      - "await" pauses the current function until some slow operation (like an API call)
        completes, letting other functions run in the meantime.
      - asyncio.gather() runs multiple async functions at the same time and waits
        for all of them to finish.
      - A Semaphore is like a bouncer at a club — it only lets a certain number of
        tasks run at once (in our case, 3).

    Args:
        cases_with_text: A list of tuples. Each tuple is (full_case_text, case_metadata).
                         For example: [("The applicant seeks...", CaseSearchResult(...)), ...]
        week_processed:  The Monday date string for tracking purposes.
        on_case_done:    Optional callback function. If provided, this function is called
                         with each CaseExtraction as soon as that case finishes analysis.
                         This is useful for saving results incrementally — if the pipeline
                         crashes partway through, the cases that already finished are saved.
                         The callback receives one argument: a CaseExtraction object.

    Returns:
        A list of CaseExtraction objects for all successfully analyzed cases.
        Cases that failed (e.g., API error) are skipped with a warning message.
    """
    # A Semaphore limits how many tasks can run at the same time.
    # With a value of 3, at most 3 Claude API calls will be in-flight simultaneously.
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_ANALYSES)

    # This will hold our successful results.
    results = []

    async def analyze_one(text: str, meta: CaseSearchResult) -> CaseExtraction | None:
        """
        Analyze a single case, respecting the concurrency limit.

        The "async with semaphore" line means: "wait here if 3 other tasks are
        already running, and only proceed when one of them finishes."
        """
        async with semaphore:
            try:
                # extract_case_info() is a regular (synchronous) function that calls
                # the Claude API. We can't call it directly in async code because it
                # would block everything.
                #
                # run_in_executor() runs it in a separate thread, which lets the async
                # event loop continue handling other tasks while we wait for Claude's
                # response. Think of it as: "run this slow function on a background
                # worker while I keep doing other things."
                loop = asyncio.get_running_loop()
                extraction = await loop.run_in_executor(
                    None,                   # Use the default thread pool
                    extract_case_info,      # The function to call
                    text,                   # Argument 1: case text
                    meta,                   # Argument 2: case metadata
                    week_processed          # Argument 3: week processed date
                )

                # If a callback was provided, call it right away with this result.
                # This lets the caller save each case to CSV as soon as it's done,
                # rather than waiting for ALL cases to finish first.
                if on_case_done is not None:
                    on_case_done(extraction)

                return extraction
            except Exception as e:
                # If anything goes wrong (API error, JSON parsing error, etc.),
                # print a warning and return None instead of crashing.
                # The case will be missing from the results but the script continues.
                print(f"  Error analyzing {meta.citation}: {e}")
                return None

    # Create a list of async tasks — one for each case.
    # These tasks haven't started yet; they're just "promises" to do work.
    tasks = [analyze_one(text, meta) for text, meta in cases_with_text]

    # asyncio.gather() starts all tasks and waits for ALL of them to complete.
    # It returns a list of results in the same order as the input tasks.
    # Some results might be None (if that case's analysis failed).
    completed = await asyncio.gather(*tasks)

    # Filter out the None results (failed analyses) and keep only successes.
    for result in completed:
        if result is not None:
            results.append(result)

    return results
