"""
Pydantic data models for case search results and extracted case information.

WHAT ARE MODELS?
Models define the "shape" of our data. Think of them like a template or form
that says "a case must have a citation, a name, a date, etc." If you try to
create a case without a required field, Pydantic will raise an error.

WHY USE PYDANTIC?
Pydantic models give us:
  1. Automatic validation — catches bad data early (e.g., missing fields)
  2. Type hints — your editor can autocomplete field names like case.judge
  3. Easy conversion — .model_dump() turns a model into a plain dict for CSV export

We have three models:
  - CaseSearchResult: The basic info we get back from searching the A2AJ API
  - LegalIssue: A single legal issue the Court addressed in a case
  - CaseExtraction: The full structured data after Claude analyzes a case
"""

# Optional means a field can be either a value OR None (Python's version of null).
# For example, Optional[str] means "a string or None".
from typing import Optional

# BaseModel is the parent class from Pydantic. Any class that inherits from it
# automatically gets validation, serialization, and other goodies.
from pydantic import BaseModel


class CaseSearchResult(BaseModel):
    """
    A case as returned from the A2AJ search API.

    This is the "lightweight" version — just the basic metadata we get from
    a search query, BEFORE we fetch the full case text or analyze it.

    Fields:
        citation: The legal citation, e.g. "2026 FC 348"
        name:     The case name, e.g. "Famugbode v. Canada (Citizenship and Immigration)"
        date:     The decision date as a string (may include time zone info from the API)
        url:      Link to the full decision on the court's website
        snippet:  A short text excerpt from the search results (may contain HTML tags)
    """
    citation: str
    name: str
    date: str
    url: str
    snippet: str = ""   # Default to empty string if no snippet provided


class LegalIssue(BaseModel):
    """
    A single legal issue the Court addressed in its decision.

    Each case can have multiple legal issues. For dismissed cases, the Court
    typically addresses all arguments raised (2-4 issues). For allowed cases,
    the Court usually only addresses the issue(s) it finds error on (1-2 issues)
    and doesn't bother with the rest.

    Fields:
        primary:   The legal framework — the type of analysis the Court applied.
                   Typically "reasonableness", "procedural fairness", or "correctness",
                   but could be anything the Court relied on (e.g., "jurisdiction",
                   "abuse of process", "Charter").
        secondary: The specific substantive issue within that framework.
                   This is what a lawyer would use to find the case — e.g.,
                   "IFA analysis inadequate", "credibility findings lacked justification",
                   "failed to disclose extrinsic evidence".
    """
    primary: str
    secondary: str


class CaseExtraction(BaseModel):
    """
    Structured data extracted from a case decision by Claude.

    This is the "full" version — created after we send the case text to Claude
    and get back all the structured information. This is what gets saved to the
    master CSV and used to generate the markdown report.

    Fields:
        citation:               Legal citation, e.g. "2026 FC 348"
        case_name:              Full case name
        date:                   Decision date (YYYY-MM-DD format, time stripped)
        url:                    Link to the full decision
        judge:                  Surname of the judge who decided the case
        lawyer_applicant:       Lawyer representing the migrant (the non-citizen,
                                regardless of whether they are applicant or respondent)
        lawyer_respondent:      Lawyer representing the other side (usually the Crown)
        category:               One of: RAD, PRRA, RPD, IAD, H&C, Visa,
                                ID Admissibility, Misrepresentation, Inadmissibility,
                                Detention, Stay, Procedural, Other
        disposition:            The outcome: "allowed", "dismissed", or "granted_in_part"
        decision_maker:         Name of the underlying decision-maker (RAD member,
                                visa officer, etc.) if stated in the decision. None if
                                not named — do not guess or fill in "the officer".
        visa_office:            For visa/permit cases, the visa office or processing
                                centre (e.g., "New Delhi", "Manila"). None if not stated
                                or not a visa case.
        irpa_sections:          List of relevant IRPA/IRPR sections cited in the decision
                                (e.g., ["s.96", "s.97(1)(b)", "s.40(1)(a)"])
        legal_issues:           List of legal issues the Court actually addressed.
                                See LegalIssue model for details. For allowed cases,
                                only the issue(s) the Court found error on. For dismissed
                                cases, all issues the Court considered and rejected.
        nationality:            Applicant's country of origin (if mentioned in decision)
        nature_of_persecution:  Type of persecution claimed (refugee cases only),
                                e.g. "political opinion", "gender-based violence"
        facts_summary:          2-3 sentence summary of what happened
        error_statement:        One sentence describing what the Court found wrong
                                (None if the case was dismissed)
        error_explanation:      2-3 sentences explaining the error in detail
                                (None if the case was dismissed)
        certified_question:     A question of general importance certified by the Court
                                (rare — most cases won't have one)
        week_processed:         The Monday date of the week this case was processed,
                                used for tracking which weekly run picked it up
    """
    citation: str
    case_name: str
    date: str
    url: str
    judge: str
    lawyer_applicant: str
    lawyer_respondent: str
    category: str
    disposition: str
    decision_maker: Optional[str] = None
    visa_office: Optional[str] = None
    irpa_sections: list[str] = []
    legal_issues: list[LegalIssue] = []
    nationality: Optional[str] = None
    nature_of_persecution: Optional[str] = None
    facts_summary: str
    error_statement: Optional[str] = None
    error_explanation: Optional[str] = None
    certified_question: Optional[str] = None
    week_processed: str
