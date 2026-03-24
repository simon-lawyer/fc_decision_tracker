"""
Data normalization and reconciliation for extracted case data.

This module has two jobs:

1. NORMALIZE — Clean up extracted values so they're consistent:
   - Judge names: strip honorifics, keep only the surname
   - Nationality: convert adjectives to country names ("Indian" → "India")
   - Lawyer names: trim whitespace, normalize spacing

2. RECONCILE — After processing, compare new values against the existing
   master CSV to flag potential inconsistencies (typos, variant spellings).
   This prints a summary so a human can review.

WHY NORMALIZE?
  When you eventually build a website with filters (e.g., "show me all cases
  before Justice Aylen"), you need consistent values. If the same judge appears
  as "Aylen", "The Honourable Madam Justice Aylen", and "Justice Aylen", your
  filter won't work properly. Normalization ensures each entity has one
  canonical name.

WHY RECONCILE?
  Even with normalization, Claude might occasionally return slightly different
  values for the same entity (e.g., "De Montigny" vs "de Montigny"). The
  reconciliation step compares new values against what's already in the CSV
  and flags anything that looks like a near-miss. A human can then decide if
  it's a genuine new value or a typo to fix.
"""

import re
from models import CaseExtraction

# ── Judge name normalization ──────────────────────────────────────────────────

# Common prefixes/honorifics that appear before judge names in FC decisions.
# We strip all of these to get just the surname.
# The order matters — longer patterns should come first so they match before
# shorter ones (e.g., "The Honourable Mr. Justice" before "Justice").
JUDGE_PREFIXES = [
    "The Honourable Chief Justice",
    "The Honourable Associate Chief Justice",
    "The Honourable Madam Justice",
    "The Honourable Mr. Justice",
    "The Honourable Justice",
    "Associate Chief Justice",
    "Chief Justice",
    "Madam Justice",
    "Mr. Justice",
    "Mme Justice",
    "Justice",
]

# Compile into a single regex pattern for efficient matching.
# The pattern matches any of the prefixes (case-insensitive) followed by
# optional whitespace. We'll strip whatever matches.
_JUDGE_PREFIX_PATTERN = re.compile(
    r"^(?:" + "|".join(re.escape(p) for p in JUDGE_PREFIXES) + r")\s*",
    re.IGNORECASE,
)


def normalize_judge(name: str) -> str:
    """
    Normalize a judge name to just the surname.

    Examples:
        "The Honourable Mr. Justice Southcott"  → "Southcott"
        "The Honourable Madam Justice Aylen"    → "Aylen"
        "Mr. Justice Brouwer"                   → "Brouwer"
        "Justice A. Grant"                      → "Grant"
        "Thorne"                                → "Thorne"
        "The Honourable Mr. Justice A. Grant"   → "Grant"

    The approach:
      1. Strip any known honorific prefix
      2. Take the last word as the surname (handles "A. Grant" → "Grant")
    """
    name = name.strip()

    # Strip the honorific prefix if present.
    name = _JUDGE_PREFIX_PATTERN.sub("", name).strip()

    # If there are still multiple words (e.g., "A. Grant" or "Mary Smith"),
    # take the last word as the surname.
    parts = name.split()
    if parts:
        return parts[-1]

    return name


# ── Nationality normalization ─────────────────────────────────────────────────

# Map of common adjective forms to their country names.
# This catches cases where Claude returns the adjective form despite being
# asked for the country name. Add to this as needed.
NATIONALITY_MAP = {
    "afghan": "Afghanistan",
    "albanian": "Albania",
    "algerian": "Algeria",
    "american": "United States",
    "angolan": "Angola",
    "argentine": "Argentina",
    "armenian": "Armenia",
    "azerbaijani": "Azerbaijan",
    "bangladeshi": "Bangladesh",
    "belarusian": "Belarus",
    "brazilian": "Brazil",
    "burmese": "Myanmar",
    "burundian": "Burundi",
    "cambodian": "Cambodia",
    "cameroonian": "Cameroon",
    "canadian": "Canada",
    "chilean": "Chile",
    "chinese": "China",
    "colombian": "Colombia",
    "congolese": "Congo",
    "costa rican": "Costa Rica",
    "cuban": "Cuba",
    "dominican": "Dominican Republic",
    "ecuadorian": "Ecuador",
    "egyptian": "Egypt",
    "eritrean": "Eritrea",
    "ethiopian": "Ethiopia",
    "filipino": "Philippines",
    "french": "France",
    "georgian": "Georgia",
    "ghanaian": "Ghana",
    "guatemalan": "Guatemala",
    "guinean": "Guinea",
    "guyanese": "Guyana",
    "haitian": "Haiti",
    "honduran": "Honduras",
    "hungarian": "Hungary",
    "indian": "India",
    "indonesian": "Indonesia",
    "iranian": "Iran",
    "iraqi": "Iraq",
    "israeli": "Israel",
    "ivorian": "Ivory Coast",
    "jamaican": "Jamaica",
    "jordanian": "Jordan",
    "kazakh": "Kazakhstan",
    "kenyan": "Kenya",
    "korean": "South Korea",
    "kurdish": "Kurdistan",
    "kuwaiti": "Kuwait",
    "lebanese": "Lebanon",
    "libyan": "Libya",
    "malaysian": "Malaysia",
    "mexican": "Mexico",
    "moroccan": "Morocco",
    "nepali": "Nepal",
    "nicaraguan": "Nicaragua",
    "nigerian": "Nigeria",
    "north korean": "North Korea",
    "pakistani": "Pakistan",
    "palestinian": "Palestine",
    "palestinian territory": "Palestine",
    "palestinian territories": "Palestine",
    "peruvian": "Peru",
    "polish": "Poland",
    "romanian": "Romania",
    "russian": "Russia",
    "rwandan": "Rwanda",
    "salvadoran": "El Salvador",
    "saudi": "Saudi Arabia",
    "serbian": "Serbia",
    "sierra leonean": "Sierra Leone",
    "somali": "Somalia",
    "south african": "South Africa",
    "south korean": "South Korea",
    "sri lankan": "Sri Lanka",
    "sudanese": "Sudan",
    "syrian": "Syria",
    "taiwanese": "Taiwan",
    "tanzanian": "Tanzania",
    "thai": "Thailand",
    "trinidadian": "Trinidad and Tobago",
    "tunisian": "Tunisia",
    "turkish": "Turkey",
    "ugandan": "Uganda",
    "ukrainian": "Ukraine",
    "uruguayan": "Uruguay",
    "uzbek": "Uzbekistan",
    "venezuelan": "Venezuela",
    "vietnamese": "Vietnam",
    "yemeni": "Yemen",
    "zimbabwean": "Zimbabwe",
}


def normalize_nationality(nationality: str | None) -> str | None:
    """
    Normalize a nationality value to a country name.

    If the value is an adjective form (e.g., "Indian"), convert it to the
    country name ("India"). If it's already a country name or not in our
    map, return it as-is with consistent title casing.

    Examples:
        "Indian"     → "India"
        "Filipino"   → "Philippines"
        "India"      → "India"
        None         → None
    """
    if not nationality:
        return None

    nationality = nationality.strip()

    # Check if it's an adjective form we know about (case-insensitive).
    lookup = nationality.lower()
    if lookup in NATIONALITY_MAP:
        return NATIONALITY_MAP[lookup]

    # Not in our map — return with title casing for consistency.
    # Title case capitalizes the first letter of each word.
    return nationality.title()


def normalize_lawyer(name: str) -> str:
    """
    Normalize a lawyer name — just clean up whitespace and casing.

    We don't do heavy normalization on lawyer names because there are
    thousands of them and no canonical source to compare against.
    Just ensure consistent formatting.
    """
    # Collapse multiple spaces into one and strip leading/trailing whitespace.
    return " ".join(name.split())


# ── Apply all normalizations to a CaseExtraction ─────────────────────────────

def normalize_case(case: CaseExtraction) -> CaseExtraction:
    """
    Apply all normalization rules to a CaseExtraction object.

    Returns a new CaseExtraction with normalized values. The original
    object is not modified (Pydantic models are immutable by default).

    This is called after Claude's extraction, before saving to the CSV.
    """
    # .model_copy(update={...}) creates a copy of the Pydantic model with
    # the specified fields replaced. This is the Pydantic v2 way to create
    # a modified copy without mutating the original.
    return case.model_copy(update={
        "judge": normalize_judge(case.judge),
        "nationality": normalize_nationality(case.nationality),
        "lawyer_migrant": normalize_lawyer(case.lawyer_migrant),
        "lawyer_respondent": normalize_lawyer(case.lawyer_respondent),
    })


# ── Reconciliation: compare new values against existing CSV data ─────────────

def reconcile(new_cases: list[CaseExtraction], existing_cases: list[dict]) -> None:
    """
    Compare values in newly extracted cases against existing data in the CSV
    and print a summary highlighting potential inconsistencies.

    This is a human-review step. It prints:
      1. New judges not previously seen
      2. New nationalities not previously seen
      3. Near-matches that might be typos (e.g., "De Montigny" vs "de Montigny")

    Args:
        new_cases:      The newly extracted CaseExtraction objects (already normalized).
        existing_cases: Rows from the database (list of dicts from db_manager.load_master()).
    """
    # Build sets of existing unique values from the CSV.
    existing_judges = {row["judge"] for row in existing_cases if row.get("judge")}
    existing_nationalities = {row["nationality"] for row in existing_cases if row.get("nationality")}
    existing_lawyers = set()
    for row in existing_cases:
        if row.get("lawyer_migrant"):
            existing_lawyers.add(row["lawyer_migrant"])
        if row.get("lawyer_respondent"):
            existing_lawyers.add(row["lawyer_respondent"])

    # Collect new unique values from the fresh extractions.
    new_judges = {c.judge for c in new_cases}
    new_nationalities = {c.nationality for c in new_cases if c.nationality}
    new_lawyers = set()
    for c in new_cases:
        new_lawyers.add(c.lawyer_migrant)
        new_lawyers.add(c.lawyer_respondent)

    # Find values that are new (not in the existing CSV).
    novel_judges = new_judges - existing_judges
    novel_nationalities = new_nationalities - existing_nationalities
    novel_lawyers = new_lawyers - existing_lawyers

    # If there's nothing to report, say so and return.
    if not novel_judges and not novel_nationalities and not existing_cases:
        # First run — no existing data to compare against. Skip reconciliation.
        return

    print("\n── Data Reconciliation ─────────────────────────────────────────")

    # ── Judges ────────────────────────────────────────────────────────
    if novel_judges:
        print(f"\n  New judges ({len(novel_judges)}):")
        for j in sorted(novel_judges):
            # Check for near-matches in existing judges (possible typos).
            # A "near-match" is an existing judge whose name differs by only
            # case or has a very similar spelling.
            near = _find_near_matches(j, existing_judges)
            if near:
                print(f"    {j}  ⚠ similar to existing: {', '.join(near)}")
            else:
                print(f"    {j}")
    else:
        print(f"\n  Judges: all match existing values.")

    # ── Nationalities ─────────────────────────────────────────────────
    if novel_nationalities:
        print(f"\n  New nationalities ({len(novel_nationalities)}):")
        for n in sorted(novel_nationalities):
            near = _find_near_matches(n, existing_nationalities)
            if near:
                print(f"    {n}  ⚠ similar to existing: {', '.join(near)}")
            else:
                print(f"    {n}")
    else:
        print(f"\n  Nationalities: all match existing values.")

    # ── Lawyers ───────────────────────────────────────────────────────
    if novel_lawyers and existing_lawyers:
        # Only flag near-matches for lawyers, don't list all new ones
        # (there are too many unique lawyers to list them all).
        flagged = []
        for l in novel_lawyers:
            near = _find_near_matches(l, existing_lawyers)
            if near:
                flagged.append((l, near))
        if flagged:
            print(f"\n  Lawyer near-matches (possible typos):")
            for name, matches in sorted(flagged):
                print(f"    {name}  ⚠ similar to: {', '.join(matches)}")
        else:
            print(f"\n  Lawyers: no near-match concerns.")

    print("")


def _find_near_matches(value: str, existing: set[str], threshold: int = 2) -> list[str]:
    """
    Find values in the existing set that are "near-matches" to the given value.

    A near-match is a string that differs by at most `threshold` edits
    (insertions, deletions, or substitutions). This catches typos like
    "De Montigny" vs "de Montigny" or "Ayelen" vs "Aylen".

    WHAT IS EDIT DISTANCE?
      Edit distance (also called Levenshtein distance) is the minimum number
      of single-character changes needed to turn one string into another.
      For example:
        "cat" → "car" = 1 edit (substitute t→r)
        "Aylen" → "Ayelen" = 1 edit (insert e)

    Args:
        value:     The new value to check.
        existing:  Set of existing values to compare against.
        threshold: Maximum edit distance to consider a "near-match".

    Returns:
        List of existing values that are near-matches (but not exact matches).
    """
    matches = []
    value_lower = value.lower()

    for candidate in existing:
        # Skip exact matches — we're looking for *near* matches only.
        if candidate == value:
            continue

        # Quick check: if the case-insensitive versions are identical,
        # that's a near-match (e.g., "de Montigny" vs "De Montigny").
        if candidate.lower() == value_lower:
            matches.append(candidate)
            continue

        # Compute edit distance. Only bother if the lengths are close enough
        # that the distance could possibly be within the threshold.
        if abs(len(candidate) - len(value)) <= threshold:
            dist = _edit_distance(value.lower(), candidate.lower())
            if 0 < dist <= threshold:
                matches.append(candidate)

    return matches


def _edit_distance(s1: str, s2: str) -> int:
    """
    Compute the Levenshtein edit distance between two strings.

    This uses dynamic programming to efficiently calculate the minimum number
    of single-character edits (insertions, deletions, substitutions) needed
    to transform s1 into s2.

    This is a standard algorithm — you don't need to understand the implementation
    to use it. Just know: smaller number = more similar strings.
    """
    # Create a matrix of size (len(s1)+1) x (len(s2)+1).
    # Each cell [i][j] will hold the edit distance between
    # the first i characters of s1 and the first j characters of s2.
    if len(s1) < len(s2):
        return _edit_distance(s2, s1)

    # Use a single row for space efficiency (we only need the previous row).
    previous_row = list(range(len(s2) + 1))

    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            # Cost is 0 if characters match, 1 if they don't.
            cost = 0 if c1 == c2 else 1
            current_row.append(min(
                current_row[j] + 1,          # Insertion
                previous_row[j + 1] + 1,     # Deletion
                previous_row[j] + cost,       # Substitution
            ))
        previous_row = current_row

    return previous_row[-1]
