"""
Markdown report generator for weekly FC immigration JR case summaries.

Generates a formatted markdown report grouped by case category.

WHAT GOES IN THE REPORT?
  Most categories only show ALLOWED cases (where the JR was granted).
  But some categories show ALL cases regardless of disposition:
    - Stays of Removal: all stays are shown (granted or dismissed)

WHAT IS MARKDOWN?
  Markdown is a simple text formatting language. For example:
    # Heading          → big heading
    ## Subheading      → smaller heading
    **bold text**      → bold text
    [link text](url)   → clickable link
    ---                → horizontal line

  The reports this module generates are .md files that can be viewed nicely
  in any markdown viewer (GitHub, VS Code, email clients that support it, etc.).
"""

from models import CaseExtraction
from config import CATEGORY_ORDER

# ── Category Labels ───────────────────────────────────────────────────────────

# Maps the short category codes (used internally and in the CSV) to
# human-readable names that appear as section headings in the report.
# For example, "RAD" becomes "Refugee Appeal Division (RAD)".
CATEGORY_LABELS = {
    "RAD": "Refugee Appeal Division (RAD)",
    "PRRA": "Pre-Removal Risk Assessment (PRRA)",
    "RPD": "Refugee Protection Division (RPD)",
    "IAD": "Immigration Appeal Division (IAD)",
    "H&C": "Humanitarian & Compassionate (H&C)",
    "Visa": "Visa / Permit Refusals",
    "ID Admissibility": "Immigration Division Admissibility Hearings",
    "Misrepresentation": "Misrepresentation (s.40)",
    "Inadmissibility": "Other Inadmissibility",
    "Detention": "Detention Reviews",
    "Stay": "Stays of Removal",
    "Procedural": "Procedural",
    "Other": "Other",
}

# Categories where ALL cases are shown (both allowed and dismissed),
# not just allowed ones. For most categories we only show allowed cases,
# but stays of removal are important to track regardless of outcome.
SHOW_ALL_DISPOSITIONS = {"Stay"}


def generate_report(
    allowed_cases: list[CaseExtraction],
    all_cases: list[CaseExtraction],
    start_date: str,
    end_date: str,
) -> str:
    """
    Generate a complete markdown report of immigration JR cases for the week.

    The report is organized by category (RAD, PRRA, RPD, etc.). Each category
    gets its own section, even if there are no cases in it that week (it will
    show "No cases this week.").

    Most categories only include allowed cases. Categories listed in
    SHOW_ALL_DISPOSITIONS (like Stay) include all cases regardless of outcome.

    Args:
        allowed_cases: Cases where the JR was allowed or granted in part.
                       Used for most categories.
        all_cases:     ALL cases (allowed + dismissed). Used for categories
                       in SHOW_ALL_DISPOSITIONS (like Stay).
        start_date:    The Monday of the report week, e.g., "2026-03-09"
        end_date:      The Sunday of the report week, e.g., "2026-03-15"

    Returns:
        The complete report as a single markdown-formatted string.
    """
    # ── Group cases by category ──────────────────────────────────────────

    # Create empty buckets for each category.
    # We maintain two sets of buckets: one for allowed-only, one for all cases.
    allowed_by_cat: dict[str, list[CaseExtraction]] = {cat: [] for cat in CATEGORY_ORDER}
    all_by_cat: dict[str, list[CaseExtraction]] = {cat: [] for cat in CATEGORY_ORDER}

    for case in allowed_cases:
        cat = case.category if case.category in CATEGORY_ORDER else "Other"
        allowed_by_cat[cat].append(case)

    for case in all_cases:
        cat = case.category if case.category in CATEGORY_ORDER else "Other"
        all_by_cat[cat].append(case)

    # Count total allowed cases for the header (excluding stay-only categories).
    total_allowed = len(allowed_cases)

    # ── Build the report line by line ────────────────────────────────────

    # We build the report as a list of strings (one per line), then join
    # them all together at the end with newlines. This is a common pattern
    # in Python for building up large strings — it's more efficient and
    # easier to read than string concatenation with +.
    lines = []

    # Report title and header
    lines.append(f"# Federal Court Immigration JR — Weekly Report")
    lines.append(f"**Week of {start_date} to {end_date}** | **{total_allowed} allowed case{'s' if total_allowed != 1 else ''}**")
    lines.append("")       # Empty string = blank line in the output
    lines.append("---")   # Horizontal rule (visual separator)
    lines.append("")

    # ── One section per category ─────────────────────────────────────────

    # Loop through categories in the defined order (RAD first, Other last).
    for category in CATEGORY_ORDER:
        label = CATEGORY_LABELS[category]

        # Decide which bucket to use for this category.
        # For categories in SHOW_ALL_DISPOSITIONS (like Stay), we show
        # every case regardless of outcome. For all other categories,
        # we only show allowed cases.
        if category in SHOW_ALL_DISPOSITIONS:
            category_cases = all_by_cat[category]
        else:
            category_cases = allowed_by_cat[category]

        # Section heading
        lines.append(f"## {label}")
        lines.append("")

        # If no cases in this category, say so and move on.
        if not category_cases:
            lines.append("No cases this week.")
            lines.append("")
            continue    # Skip to the next category

        # Format each case and add it to the report.
        for case in category_cases:
            # For categories that show all dispositions, we pass a flag
            # so the formatter knows to display the disposition prominently.
            show_disposition = category in SHOW_ALL_DISPOSITIONS
            lines.append(format_case(case, show_disposition=show_disposition))
            lines.append("")

    # Join all lines with newline characters to create the final string.
    return "\n".join(lines)


def format_case(case: CaseExtraction, show_disposition: bool = False) -> str:
    """
    Format a single case entry for the markdown report.

    Produces a block of markdown that looks like this when rendered:

        #### Case Name (linked to full decision)
        **Citation** | Date | **Disposition: Allowed** (only if show_disposition=True)
        **Judge:** Name | **Applicant's Counsel:** Name | **Respondent's Counsel:** Name
        **Nationality:** Country | **Persecution type:** Type

        **Facts:** Summary of the case...

        **Error Found:** What the Court found wrong...

        **Explanation:** More detail about the error...

        **Certified Question:** None

        ---

    Args:
        case:              A CaseExtraction object with all the case data.
        show_disposition:  If True, show the disposition (allowed/dismissed) on the
                           citation line. Used for categories like Stay where we
                           include all outcomes, so the reader needs to see which.

    Returns:
        A formatted markdown string for this one case.
    """
    lines = []

    # ── Title line: case name as a clickable link ────────────────────────
    # Markdown link format: [visible text](url)
    lines.append(f"#### [{case.case_name}]({case.url})")

    # ── Citation, date, and optionally disposition ───────────────────────
    citation_line = f"**{case.citation}** | {case.date}"
    if show_disposition:
        # Capitalize the disposition for display, e.g., "allowed" → "Allowed"
        disp_label = case.disposition.replace("_", " ").title()
        citation_line += f" | **{disp_label}**"
    lines.append(citation_line)

    # ── Judge and counsel ────────────────────────────────────────────────
    # We build this as a list of parts, then join with " | " (pipe separator).
    counsel_parts = [f"**Judge:** {case.judge}"]
    counsel_parts.append(f"**Applicant's Counsel:** {case.lawyer_applicant}")
    counsel_parts.append(f"**Respondent's Counsel:** {case.lawyer_respondent}")
    lines.append(" | ".join(counsel_parts))

    # ── Nationality and persecution type (if available) ──────────────────
    # These are optional fields — only shown if Claude extracted them.
    if case.nationality:
        nationality_line = f"**Nationality:** {case.nationality}"
        # nature_of_persecution only applies to refugee/RAD/PRRA cases.
        if case.nature_of_persecution:
            nationality_line += f" | **Persecution type:** {case.nature_of_persecution}"
        lines.append(nationality_line)

    # ── IRPA sections (if any) ──────────────────────────────────────────
    if case.irpa_sections:
        lines.append(f"**Sections:** {', '.join(case.irpa_sections)}")

    lines.append("")   # Blank line before the substantive content

    # ── Facts summary ────────────────────────────────────────────────────
    lines.append(f"**Facts:** {case.facts_summary}")
    lines.append("")

    # ── Legal issues ─────────────────────────────────────────────────────
    # Show each legal issue the Court addressed, with its primary framework
    # and the specific substantive issue.
    if case.legal_issues:
        lines.append("**Legal Issues:**")
        for issue in case.legal_issues:
            # Capitalize the primary for display, e.g., "reasonableness" → "Reasonableness"
            lines.append(f"- *{issue.primary.title()}*: {issue.secondary}")
        lines.append("")

    # ── Error found (only for allowed cases) ─────────────────────────────
    # error_statement is None for dismissed cases, so we check before adding it.
    if case.error_statement:
        lines.append(f"**Error Found:** {case.error_statement}")
        lines.append("")

    # ── Error explanation (only for allowed cases) ───────────────────────
    if case.error_explanation:
        lines.append(f"**Explanation:** {case.error_explanation}")
        lines.append("")

    # ── Certified question ───────────────────────────────────────────────
    # Most cases don't have a certified question, so we show "None" as default.
    certified = case.certified_question if case.certified_question else "None"
    lines.append(f"**Certified Question:** {certified}")

    lines.append("")
    lines.append("---")   # Horizontal rule to separate cases visually

    return "\n".join(lines)
