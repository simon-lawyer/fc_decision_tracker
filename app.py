#!/usr/bin/env python3
"""
FC Immigration JR Case Browser — Single-Page Web App.

A minimal front end for browsing Federal Court immigration judicial review
cases. Built with FastHTML and Monster UI.

HOW TO RUN:
  python app.py
  Then open http://localhost:5001 in your browser.
"""

# ── Imports ──────────────────────────────────────────────────────────────────
import json
import os

from fasthtml.common import *
from monsterui.all import *

# Import the database table and config.
from config import DATA_DIR
from db import cases as cases_table

# ── Constants ────────────────────────────────────────────────────────────────

PAGE_SIZE = 10


# ── Custom CSS ───────────────────────────────────────────────────────────────
# Override Monster UI / FrankenUI defaults to strip away visual noise.
# The goal: let typography and whitespace do the work, not borders and boxes.

CUSTOM_CSS = Style("""
    /* Kill all card/component borders and shadows globally */
    .uk-card, .uk-card-default, .uk-card-body,
    [class*="uk-card"] {
        border: none !important;
        box-shadow: none !important;
        background: transparent !important;
    }

    /* Strip borders off form inputs — just a subtle bottom line */
    .uk-input, .uk-select, .uk-textarea {
        border: none !important;
        border-bottom: 1px solid hsl(var(--muted-foreground) / 0.2) !important;
        border-radius: 0 !important;
        box-shadow: none !important;
        background: transparent !important;
        padding-left: 0 !important;
    }
    .uk-input:focus, .uk-select:focus {
        border-bottom-color: hsl(var(--foreground) / 0.5) !important;
        outline: none !important;
        box-shadow: none !important;
    }

    /* Plain select styling — clean underline to match inputs */
    .filter-select {
        border: none !important;
        border-bottom: 1px solid hsl(var(--muted-foreground) / 0.2) !important;
        border-radius: 0 !important;
        background-color: transparent !important;
        box-shadow: none !important;
        padding: 0.5rem 1.5rem 0.5rem 0;
        outline: none;
        cursor: pointer;
        font-size: 0.75rem;
        color: hsl(var(--foreground));
        min-width: 8rem;
        -webkit-appearance: none;
        appearance: none;
        background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%23888' stroke-width='2'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E") !important;
        background-repeat: no-repeat !important;
        background-position: right 0.25rem center !important;
    }
    .filter-select:focus {
        border-bottom-color: hsl(var(--foreground) / 0.5) !important;
    }

    /* Thin, quiet separator between cases instead of card borders */
    .case-entry + .case-entry {
        border-top: 1px solid hsl(var(--muted-foreground) / 0.1);
    }

    /* Tighten up the page — no excessive whitespace */
    body {
        font-feature-settings: "kern" 1, "liga" 1;
    }

    /* Collapsible filter drawer */
    .filter-drawer {
        max-height: 0;
        overflow: hidden;
        transition: max-height 0.3s ease, opacity 0.3s ease;
        opacity: 0;
    }
    .filter-drawer.open {
        max-height: 30rem;
        opacity: 1;
    }

    /* Underline the toggle when filters are open */
    #filter-toggle.active {
        text-decoration: underline;
    }

    /* Back-to-top button — positioned just outside the text column */
    #back-to-top {
        position: fixed;
        bottom: 2rem;
        /* Anchor to the right edge of the content column */
        left: calc(50% + 22rem);
        width: 2.5rem;
        height: 2.5rem;
        border-radius: 50%;
        background: hsl(var(--foreground));
        color: hsl(var(--background));
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        opacity: 0;
        transition: opacity 0.3s ease;
        pointer-events: none;
        border: none;
        box-shadow: 0 1px 3px rgba(0,0,0,0.2);
    }
    #back-to-top.visible {
        opacity: 1;
        pointer-events: auto;
    }
    /* On smaller screens, fall back to right edge */
    @media (max-width: 960px) {
        #back-to-top {
            left: auto;
            right: 1rem;
        }
    }

    /* Floating search/filter button — anchored near the content column */
    #filter-fab {
        position: fixed;
        top: 24rem;
        /* Sit just outside the max-w-2xl column (42rem = 672px) */
        left: calc(50% + 22rem);
        width: 3.5rem;
        height: 3.5rem;
        padding: 0;
        font-size: 0.55rem;
        line-height: 1.3;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        text-align: center;
        background: hsl(var(--foreground));
        color: hsl(var(--background));
        border: none;
        border-radius: 50%;
        cursor: pointer;
        z-index: 40;
        box-shadow: 0 1px 4px rgba(0,0,0,0.15);
        display: flex;
        align-items: center;
        justify-content: center;
    }
    #filter-fab:hover { opacity: 0.85; }
    @media (max-width: 960px) {
        #filter-fab {
            left: auto;
            right: 1rem;
        }
    }

    /* Slide-in panel overlay */
    #filter-overlay {
        position: fixed;
        inset: 0;
        background: rgba(0,0,0,0.2);
        z-index: 45;
        opacity: 0;
        pointer-events: none;
        transition: opacity 0.25s ease;
    }
    #filter-overlay.open {
        opacity: 1;
        pointer-events: auto;
    }

    /* Slide-in panel */
    #filter-panel {
        position: fixed;
        top: 0;
        right: 0;
        bottom: 0;
        width: 18rem;
        background: hsl(var(--background));
        z-index: 50;
        transform: translateX(100%);
        transition: transform 0.25s ease;
        padding: 1.5rem;
        overflow-y: auto;
        box-shadow: -2px 0 8px rgba(0,0,0,0.1);
    }
    #filter-panel.open {
        transform: translateX(0);
    }
""")


# ── Data Loading ─────────────────────────────────────────────────────────────

def _row_to_dict(row) -> dict:
    """Convert a fastlite dataclass row to a plain dict with parsed JSON fields."""
    if hasattr(row, '__dict__'):
        d = {k: v for k, v in row.__dict__.items() if not k.startswith('_')}
    else:
        d = dict(row)

    # Parse JSON fields back into Python lists/objects.
    for field in ("legal_issues", "irpa_sections"):
        val = d.get(field, "")
        if val and isinstance(val, str):
            try:
                d[field] = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                d[field] = []
        elif not val:
            d[field] = []

    return d


def load_cases():
    """Read all cases from the database, sorted newest first.
    Parses JSON fields (legal_issues, irpa_sections) back into Python objects.
    """
    rows = cases_table()
    result = [_row_to_dict(row) for row in rows]
    result.sort(key=lambda c: (c.get("date", ""), c.get("citation", "")), reverse=True)
    return result


def get_unique_values(cases, field):
    """Extract sorted unique non-empty values for a field."""
    return sorted({row[field] for row in cases if row.get(field)})


# ── Filtering ────────────────────────────────────────────────────────────────

def filter_cases(cases, query="", category="", disposition="", judge="",
                 nationality="", date_from="", date_to=""):
    """
    Filter cases by all active criteria (AND logic).
    Only filters that have a non-empty value are applied.
    """
    results = cases

    if query:
        q = query.lower()
        results = [
            c for c in results
            if q in (c.get("case_name") or "").lower()
            or q in (c.get("facts_summary") or "").lower()
            or q in (c.get("error_statement") or "").lower()
            or q in (c.get("error_explanation") or "").lower()
            or q in (c.get("citation") or "").lower()
            or q in (c.get("lawyer_migrant") or "").lower()
            or q in (c.get("lawyer_respondent") or "").lower()
        ]

    if category:
        results = [c for c in results if c.get("category") == category]
    if disposition:
        results = [c for c in results if c.get("disposition") == disposition]
    if judge:
        results = [c for c in results if c.get("judge") == judge]
    if nationality:
        results = [c for c in results if c.get("nationality") == nationality]
    if date_from:
        results = [c for c in results if c.get("date", "") >= date_from]
    if date_to:
        results = [c for c in results if c.get("date", "") <= date_to]

    return results


# ── UI Components ────────────────────────────────────────────────────────────

def clickable_filter(label, value, field):
    """
    A clickable metadata item that links to the case list filtered by this value.
    E.g. clicking "Justice: Southcott" navigates to /?judge=Southcott.
    """
    return A(
        Span(f"{label} ", cls="font-semibold"), value,
        href=f"/?{field}={value}",
        cls="hover:underline cursor-pointer",
    )


def disposition_label(disposition):
    """
    Clickable disposition — filters to show only cases with this outcome.
    Green for allowed, muted for dismissed.
    """
    colors = {
        "allowed": "text-green-600",
        "dismissed": "text-red-300",
        "granted_in_part": "text-amber-600",
    }
    display = disposition.replace("_", " ")
    return A(
        display,
        href=f"/?disposition={disposition}",
        cls=f"text-xs tracking-wide uppercase hover:underline cursor-pointer {colors.get(disposition, 'text-muted-foreground')}",
    )


def case_title(case):
    """
    Build the case title: full case name in italics, followed by citation.
    e.g. "Famugbode v. Canada (Citizenship and Immigration), 2026 FC 348"
    """
    full_name = case.get("case_name", "")
    return A(
        Em(full_name), f", {case['citation']}",
        href=case.get("url", "#"), target="_blank",
        cls="font-medium hover:underline",
    )


def case_entry(case):
    """
    Render a single case as a minimal text block.
    No card, no border, no box — just structured typography with a thin
    separator between entries (handled by CSS on .case-entry).
    """
    # Title line: short case name + citation (linked), date, disposition
    title_line = Div(
        case_title(case),
        Span(" · ", cls="text-muted-foreground"),
        Span(case.get("date", ""), cls="text-muted-foreground"),
        Span(" · ", cls="text-muted-foreground"),
        disposition_label(case.get("disposition", "")),
        cls="text-sm"
    )

    # Metadata line: clickable judge, category, nationality, persecution
    meta_parts = []
    if case.get("judge"):
        meta_parts.append(clickable_filter("Justice:", case["judge"], "judge"))
    if case.get("category"):
        meta_parts.append(clickable_filter("Category:", case["category"], "category"))
    if case.get("nationality"):
        meta_parts.append(clickable_filter("Nationality:", case["nationality"], "nationality"))

    # Nature of persecution — only for refugee cases (RPD, RAD, PRRA)
    if case.get("category") in {"RPD", "RAD", "PRRA"} and case.get("nature_of_persecution"):
        meta_parts.append(Span(Span("Persecution: ", cls="font-semibold"), case["nature_of_persecution"]))

    # Interleave with dot separators
    meta_items = []
    for i, part in enumerate(meta_parts):
        if i > 0:
            meta_items.append(Span(" · ", cls="text-muted-foreground"))
        meta_items.append(part)

    meta_line = Div(*meta_items, cls="text-xs text-muted-foreground mt-1") if meta_items else Div()

    # Facts — prefixed with bold "Facts:"
    facts = Div()
    if case.get("facts_summary"):
        facts = P(
            Span("Facts: ", cls="font-semibold"),
            case["facts_summary"],
            cls="text-sm leading-relaxed mt-2",
        )

    # Allegations — each legal issue as its own line, with standard of review in brackets
    # e.g. "Allegations: credibility findings lacked justification (reasonableness)"
    legal_issues = case.get("legal_issues", [])
    allegations_block = Div()
    if legal_issues and isinstance(legal_issues, list):
        allegation_lines = []
        for issue in legal_issues:
            if isinstance(issue, dict) and issue.get("secondary"):
                secondary = issue["secondary"]
                primary = issue.get("primary", "")
                if primary:
                    allegation_lines.append(f"{secondary} ({primary})")
                else:
                    allegation_lines.append(secondary)
        if allegation_lines:
            allegations_block = Div(
                P(Span("Allegations:", cls="font-semibold"), cls="text-sm"),
                Ol(
                    *[Li(line, cls="text-sm") for line in allegation_lines],
                    cls="list-decimal list-inside text-sm mt-1 pl-4",
                ),
                cls="mt-2",
            )

    # Outcome — green for allowed/granted_in_part (with full analysis), black for dismissed
    outcome_block = Div()
    disposition = case.get("disposition", "")
    if disposition in ("allowed", "granted_in_part"):
        label = "Granted in part: " if disposition == "granted_in_part" else "Application granted: "
        parts = [Span(label, cls="font-semibold text-green-700")]
        if case.get("error_statement"):
            parts.append(case["error_statement"])
        outcome_block = P(*parts, cls="text-sm mt-2")
        if case.get("error_explanation"):
            outcome_block = Div(
                outcome_block,
                P(case["error_explanation"], cls="text-sm mt-1"),
            )
    else:
        outcome_block = P("Case dismissed.", cls="text-sm font-semibold mt-2")

    # Certified question — only show if present
    cq_block = Div()
    if case.get("certified_question"):
        cq_block = P(
            Span("Certified Question: ", cls="font-semibold text-amber-700"),
            case["certified_question"],
            cls="text-sm mt-2",
        )

    # Counsel — at the bottom
    counsel_line = Div()
    if case.get("lawyer_migrant"):
        counsel_line = P(
            Span("Counsel: ", cls="font-semibold"), case["lawyer_migrant"],
            cls="text-xs text-muted-foreground mt-2",
        )

    return Div(title_line, meta_line, facts, allegations_block, outcome_block, cq_block, counsel_line, cls="case-entry py-5")


def case_list_fragment(cases, page=0):
    """
    Render a page of cases with an infinite-scroll sentinel at the bottom.
    When the sentinel scrolls into view, HTMX loads the next page.
    """
    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    page_cases = cases[start:end]

    # If there are no cases to show (either the CSV is empty or the active
    # filters excluded everything), display a friendly message instead of
    # an empty blank area.
    if not page_cases:
        return Div(
            P("No cases match your filters.", cls="text-sm text-muted-foreground py-8 text-center"),
        )

    cards = [case_entry(c) for c in page_cases]

    # If more cases exist, add a sentinel that triggers the next page load.
    # The sentinel uses hx-swap="outerHTML" so it replaces itself with the
    # next batch of case-entry divs, keeping them as siblings for the CSS
    # separator rule (.case-entry + .case-entry) to work.
    if end < len(cases):
        sentinel = Div(
            P("···", cls="text-center text-muted-foreground py-6"),
            hx_get="/cases",
            hx_trigger="intersect once",
            hx_swap="outerHTML",
            hx_vals=f'{{"page": {page + 1}}}',
            hx_include="#filter-form",
            cls="scroll-sentinel",
        )
        cards.append(sentinel)

    # For page 0, wrap in a container. For subsequent pages (infinite scroll),
    # return bare elements so they become siblings of existing case entries.
    if page == 0:
        return Div(*cards)
    else:
        # Return multiple elements — HTMX outerHTML swap replaces the sentinel
        # with these, so they become direct siblings of the previous entries.
        return tuple(cards)


def _header_description():
    """Build the greyed-out description paragraphs with live stats."""
    from datetime import date, timedelta

    all_cases = load_cases()

    # Last updated: most recent week_processed value in the database
    last_updated = ""
    if all_cases:
        last_updated = max(c.get("date", "") for c in all_cases if c.get("date"))

    # Rolling 30-day stats
    cutoff = (date.today() - timedelta(days=30)).isoformat()
    recent_cases = [c for c in all_cases if c.get("date", "") >= cutoff]
    total = len(recent_cases)
    allowed = sum(1 for c in recent_cases if c.get("disposition") in ("allowed", "granted_in_part"))
    grant_rate = (allowed / total * 100) if total > 0 else 0

    parts = [
        P("Federal Court immigration judicial review decisions, extracted and summarized by Claude. "
          "Case text is sourced from A2AJ. Verify all details against the original decisions before relying on this analysis.",
          cls="text-xs text-muted-foreground mt-2 leading-relaxed"),
    ]

    if total:
        parts.append(
            P(f"In the last 30 days, the Federal Court has released {total} IMM judicial review decisions. "
              f"Of these, {allowed} were granted, for an overall grant rate of {grant_rate:.1f}%.",
              cls="text-xs text-muted-foreground mt-1 leading-relaxed"),
        )

    if last_updated:
        parts.append(
            P(f"Last updated with decisions through {last_updated}.",
              cls="text-xs text-muted-foreground mt-1"),
        )

    return Div(*parts)


def page_header(active="cases"):
    """
    Shared page header with nav links between Cases and Stats pages.
    'active' indicates which page is current — it won't be a link.
    """
    cases_nav = Span("Cases", cls="font-semibold underline") if active == "cases" else A("Cases", href="/", cls="hover:underline")
    stats_nav = Span("Stats", cls="font-semibold underline") if active == "stats" else A("Stats", href="/stats", cls="hover:underline")

    return Div(
        H1(A("Professor Wallace's AI Analysis of FC IMM Cases", href="/", cls="no-underline hover:underline"), cls="text-lg font-semibold tracking-tight"),
        _header_description(),
        Div(
            A(Img(src="https://upload.wikimedia.org/wikipedia/commons/8/83/Lincoln_Alexander_School_of_Law_Logo.svg",
                  alt="Lincoln Alexander School of Law",
                  cls="h-24"),
              href="https://www.torontomu.ca/law/", target="_blank"),
            A(Img(src="https://a2aj.ca/assets/a2aj colour black logo@300x.png",
                  alt="A2AJ",
                  cls="h-24"),
              href="https://a2aj.ca/", target="_blank"),
            cls="flex items-center justify-center gap-6 mt-4",
        ),
        Div(cases_nav, Span(" · ", cls="text-muted-foreground"), stats_nav, cls="text-sm mt-2 text-center"),
        Hr(cls="mt-4 border-muted-foreground/20"),
        cls="pt-8 pb-6",
    )


def compute_stats(cases):
    """
    Compute summary statistics from the case list.
    Returns a dict with all the numbers needed for the stats page.
    """
    total = len(cases)
    if total == 0:
        return {"total": 0}

    # Disposition counts
    allowed = sum(1 for c in cases if c.get("disposition") == "allowed")
    dismissed = sum(1 for c in cases if c.get("disposition") == "dismissed")
    granted_in_part = sum(1 for c in cases if c.get("disposition") == "granted_in_part")

    # Category breakdown
    category_counts = {}
    for c in cases:
        cat = c.get("category", "Unknown")
        category_counts[cat] = category_counts.get(cat, 0) + 1

    # Judge breakdown — how many cases each, and their grant rate
    judge_stats = {}
    for c in cases:
        judge = c.get("judge", "Unknown")
        if judge not in judge_stats:
            judge_stats[judge] = {"total": 0, "allowed": 0}
        judge_stats[judge]["total"] += 1
        if c.get("disposition") in ("allowed", "granted_in_part"):
            judge_stats[judge]["allowed"] += 1

    # Nationality breakdown
    nationality_counts = {}
    for c in cases:
        nat = c.get("nationality", "")
        if nat:
            nationality_counts[nat] = nationality_counts.get(nat, 0) + 1

    # Date range
    dates = [c.get("date", "") for c in cases if c.get("date")]
    date_min = min(dates) if dates else ""
    date_max = max(dates) if dates else ""

    # Grant rate — includes both allowed and granted_in_part
    grant_rate = ((allowed + granted_in_part) / total * 100) if total > 0 else 0

    return {
        "total": total,
        "allowed": allowed,
        "dismissed": dismissed,
        "granted_in_part": granted_in_part,
        "grant_rate": grant_rate,
        "category_counts": dict(sorted(category_counts.items(), key=lambda x: x[1], reverse=True)),
        "judge_stats": dict(sorted(judge_stats.items(), key=lambda x: x[1]["total"], reverse=True)),
        "nationality_counts": dict(sorted(nationality_counts.items(), key=lambda x: x[1], reverse=True)),
        "date_min": date_min,
        "date_max": date_max,
    }


def results_count(count, oob=False):
    """Small text showing how many cases match.
    When oob=True, includes hx-swap-oob so HTMX can update it out-of-band.
    """
    label = "case" if count == 1 else "cases"
    attrs = {"id": "results-count", "cls": "text-xs text-muted-foreground"}
    if oob:
        attrs["hx_swap_oob"] = "true"
    return Span(f"{count} {label}", **attrs)


# ── Layout toggle ────────────────────────────────────────────────────────────
# Layout options: "slide" (floating button + slide-in panel),
#                  "sidebar" (always-visible left sidebar),
#                  "inline" (original single-column with collapsible drawer)
LAYOUT = "slide"


def _make_select(name, options, placeholder, selected_value=""):
    """Shared select builder used by both layouts."""
    return Select(
        Option(placeholder, value="", selected=(not selected_value)),
        *[Option(opt, value=opt, selected=(opt == selected_value)) for opt in options],
        name=name,
        cls="text-xs filter-select",
    )


def filter_slide_panel(cases, category="", disposition="", judge="", nationality="", query=""):
    """
    Slide-in panel layout: a floating button on the right edge opens a panel
    that glides in from the right with search and filters.
    """
    categories = get_unique_values(cases, "category")
    dispositions = get_unique_values(cases, "disposition")
    judges = get_unique_values(cases, "judge")
    nationalities = get_unique_values(cases, "nationality")

    toggle_js = "document.getElementById('filter-panel').classList.toggle('open'); document.getElementById('filter-overlay').classList.toggle('open');"
    close_js = "document.getElementById('filter-panel').classList.remove('open'); document.getElementById('filter-overlay').classList.remove('open');"

    return (
        # Floating button on right edge
        Button(Div("Search", Br(), "+", Br(), "Filter"), id="filter-fab", onclick=toggle_js),

        # Overlay — click to close
        Div(id="filter-overlay",
            onclick=close_js),

        # Slide-in panel — always starts closed; filters applied via URL don't need it open
        Div(
            Div(
                H3("Search & Filter", cls="text-sm font-semibold"),
                Button("X", onclick=close_js,
                       cls="text-xs px-2 py-1 bg-muted text-foreground hover:opacity-80"),
                cls="flex items-center justify-between mb-4",
            ),
            Form(
                Div(
                    Input(
                        name="query",
                        type="search",
                        placeholder="Search...",
                        value=query,
                        cls="uk-input text-sm flex-1",
                    ),
                    Button("Search", type="submit",
                           cls="text-xs px-3 py-1.5 bg-foreground text-background hover:opacity-80 whitespace-nowrap"),
                    cls="flex items-center gap-2",
                ),
                _make_select("category", categories, "Category", category),
                _make_select("disposition", dispositions, "Disposition", disposition),
                _make_select("judge", judges, "Justice", judge),
                _make_select("nationality", nationalities, "Nationality", nationality),
                Div(
                    Button("Filter", type="submit",
                           cls="text-xs px-3 py-1.5 bg-foreground text-background hover:opacity-80"),
                    A("Reset", href="/",
                      cls="text-xs px-3 py-1.5 bg-muted text-foreground hover:opacity-80"),
                    cls="flex items-center gap-2",
                ),
                results_count(len(cases)),
                id="filter-form",
                hx_get="/cases",
                hx_target="#case-list",
                hx_trigger="submit",
                hx_swap="innerHTML",
                hx_on__after_request=close_js,
                cls="flex flex-col gap-3",
            ),
            id="filter-panel",
        ),
    )


def filter_sidebar(cases, category="", disposition="", judge="", nationality="", query=""):
    """
    Sidebar layout: filters always visible in a fixed left column.
    Hidden on mobile behind a toggle.
    """
    categories = get_unique_values(cases, "category")
    dispositions = get_unique_values(cases, "disposition")
    judges = get_unique_values(cases, "judge")
    nationalities = get_unique_values(cases, "nationality")

    return Form(
        Input(
            name="query",
            type="search",
            placeholder="Search...",
            value=query,
            cls="uk-input text-sm w-full mb-3",
        ),
        _make_select("category", categories, "Category", category),
        _make_select("disposition", dispositions, "Disposition", disposition),
        _make_select("judge", judges, "Justice", judge),
        _make_select("nationality", nationalities, "Nationality", nationality),
        Div(
            Button("Apply", type="submit",
                   cls="text-xs px-3 py-1.5 bg-foreground text-background hover:opacity-80"),
            A("Reset", href="/",
              cls="text-xs px-3 py-1.5 bg-muted text-foreground hover:opacity-80 inline-block"),
            cls="flex gap-2 mt-4",
        ),
        results_count(len(cases)),
        id="filter-form",
        hx_get="/cases",
        hx_target="#case-list",
        hx_trigger="submit",
        hx_swap="innerHTML",
        cls="flex flex-col gap-3 mt-2",
    )


def filter_bar(cases, category="", disposition="", judge="", nationality="", query=""):
    """
    Original single-column layout: collapsible filter drawer above the case list.
    """
    categories = get_unique_values(cases, "category")
    dispositions = get_unique_values(cases, "disposition")
    judges = get_unique_values(cases, "judge")
    nationalities = get_unique_values(cases, "nationality")

    return Form(
        # Search row: input + Search button
        Div(
            Input(
                name="query",
                type="search",
                placeholder="Search the summaries...",
                value=query,
                cls="uk-input text-lg flex-1",
            ),
            Button("Search", type="submit",
                   cls="text-sm px-4 py-2 bg-foreground text-background hover:opacity-80 whitespace-nowrap"),
            cls="flex items-end gap-2 mb-2",
        ),

        # Filters toggle + results count
        Div(
            Button(
                "Filters",
                type="button",
                id="filter-toggle",
                cls="text-sm px-4 py-2 bg-foreground text-background hover:opacity-80",
                onclick="document.getElementById('filter-drawer').classList.toggle('open'); this.classList.toggle('active');",
            ),
            results_count(len(cases)),
            cls="flex items-center gap-3 mb-4",
        ),

        # Collapsible filter drawer — hidden by default, slides open
        Div(
            Div(
                _make_select("category", categories, "Category", category),
                _make_select("disposition", dispositions, "Disposition", disposition),
                _make_select("judge", judges, "Justice", judge),
                _make_select("nationality", nationalities, "Nationality", nationality),
                cls="flex flex-col gap-3",
            ),
            Div(
                Button("Apply", type="submit",
                       cls="text-sm px-4 py-2 bg-foreground text-background hover:opacity-80"),
                A("Reset", href="/",
                  cls="text-sm px-4 py-2 bg-muted text-foreground hover:opacity-80 inline-block"),
                cls="flex gap-3 mt-3",
            ),
            id="filter-drawer",
            cls="filter-drawer mb-4" + (" open" if any([category, disposition, judge, nationality]) else ""),
        ),

        id="filter-form",
        hx_get="/cases",
        hx_target="#case-list",
        hx_trigger="submit",
        hx_swap="innerHTML",
    )


# ── App Setup ────────────────────────────────────────────────────────────────

# Detect production environment (Railway sets PORT and RAILWAY_ENVIRONMENT).
IS_PRODUCTION = bool(os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("PORT"))

# Ensure the data directory exists (Railway starts with a clean filesystem).
os.makedirs(DATA_DIR, exist_ok=True)

app, rt = fast_app(
    hdrs=(
        *Theme.zinc.headers(),   # zinc = neutral/minimal palette
        CUSTOM_CSS,
        # Scales of justice emoji as favicon (no external file needed)
        Link(rel="icon", href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>&#x2696;</text></svg>"),
    ),
    pico=False,
    title="FC IMM Tracker",
    live=not IS_PRODUCTION,   # Auto-reload in dev only, not in production
)


# ── Routes ───────────────────────────────────────────────────────────────────

@rt("/")
def index(category: str = "", disposition: str = "", judge: str = "",
          nationality: str = "", query: str = ""):
    """Main page — header, filters, case list.
    Accepts optional query params so stats page links can pre-filter.
    """
    cases = load_cases()
    filtered = filter_cases(cases, query=query, category=category,
                            disposition=disposition, judge=judge,
                            nationality=nationality)

    back_to_top = (
        Button(
            UkIcon("arrow-up", height=16),
            id="back-to-top",
            onclick="window.scrollTo({top:0, behavior:'smooth'})",
        ),
        Script("""
            window.addEventListener('scroll', function() {
                var btn = document.getElementById('back-to-top');
                if (window.scrollY > 300) {
                    btn.classList.add('visible');
                } else {
                    btn.classList.remove('visible');
                }
            });
        """),
    )

    if LAYOUT == "slide":
        return Container(
            page_header("cases"),
            *filter_slide_panel(cases, category=category, disposition=disposition,
                                judge=judge, nationality=nationality, query=query),
            Div(case_list_fragment(filtered, page=0), id="case-list"),
            *back_to_top,
            cls="max-w-2xl mx-auto px-4",
        )

    if LAYOUT == "sidebar":
        return Container(
            page_header("cases"),
            Div(
                Aside(
                    filter_sidebar(cases, category=category, disposition=disposition,
                                   judge=judge, nationality=nationality, query=query),
                    cls="w-48 shrink-0 sticky top-4 self-start hidden lg:block",
                ),
                Div(
                    Div(case_list_fragment(filtered, page=0), id="case-list"),
                    cls="flex-1 min-w-0",
                ),
                cls="flex gap-8",
            ),
            *back_to_top,
            cls="max-w-5xl mx-auto px-4",
        )

    # ── "inline" — original single-column layout ──
    return Container(
        page_header("cases"),
        Div(
            filter_bar(cases, category=category, disposition=disposition,
                       judge=judge, nationality=nationality, query=query),
            Div(case_list_fragment(filtered, page=0), id="case-list"),
            id="main-content",
        ),
        *back_to_top,
        cls="max-w-2xl mx-auto px-4",
    )


@rt("/cases")
def cases_endpoint(query: str = "", category: str = "", disposition: str = "",
        judge: str = "", nationality: str = "", date_from: str = "",
        date_to: str = "", page: int = 0):
    """HTMX endpoint — returns filtered case cards."""
    cases = load_cases()
    filtered = filter_cases(cases, query=query, category=category,
                            disposition=disposition, judge=judge,
                            nationality=nationality, date_from=date_from,
                            date_to=date_to)

    if page == 0:
        return (
            # Return the case list content — gets swapped into #case-list via innerHTML
            case_list_fragment(filtered, page=0),
            # Out-of-band swap: update the results count without replacing the form.
            results_count(len(filtered), oob=True),
        )

    return case_list_fragment(filtered, page=page)


@rt("/reset")
def reset():
    """Clear all filters."""
    cases = load_cases()
    return Div(
        filter_bar(cases),
        Div(case_list_fragment(cases, page=0), id="case-list"),
        id="main-content",
    )


@rt("/stats")
def stats():
    """Stats page — text-based summary of all case data."""
    cases = load_cases()
    s = compute_stats(cases)

    if s["total"] == 0:
        return Container(
            page_header("stats"),
            P("No case data available yet. Run the pipeline to populate.", cls="text-sm text-muted-foreground"),
            cls="max-w-2xl mx-auto px-4",
        )

    # Helper: build a link to the cases page with filters pre-applied.
    # e.g. cases_link("5 cases", category="RAD") -> <a href="/?category=RAD">5 cases</a>
    def pl(n, word="case"):
        """Pluralize: 1 case, 2 cases."""
        return f"{n} {word}" if n == 1 else f"{n} {word}s"

    def cases_link(text, **filters):
        params = "&".join(f"{k}={v}" for k, v in filters.items() if v)
        href = f"/?{params}" if params else "/"
        return A(text, href=href, cls="hover:underline hover:text-foreground")

    # ── Build the page as prose paragraphs ──
    sections = []

    # Overview
    sections.append(
        Div(
            H2("Overview", cls="text-base font-semibold mb-2"),
            P(
                f"Between {s['date_min']} and {s['date_max']}, the Federal Court of Canada released ",
                cases_link(f"{pl(s['total'], 'immigration judicial review decision')}", ),
                f" captured in this database. Of these, ",
                cases_link(f"{s['allowed']} were granted", disposition="allowed"),
                f", ",
                cases_link(f"{s['dismissed']} were dismissed", disposition="dismissed"),
                *(
                    [", and ", cases_link(
                        f"{s['granted_in_part']} {'was' if s['granted_in_part'] == 1 else 'were'} granted in part",
                        disposition="granted_in_part")]
                    if s['granted_in_part'] else []
                ),
                f". The overall grant rate was {s['grant_rate']:.1f}%.",
                cls="text-sm leading-relaxed",
            ),
            cls="mb-6",
        )
    )

    # Category breakdown
    cat_lines = []
    for cat, count in s["category_counts"].items():
        cat_allowed = sum(1 for c in cases if c.get("category") == cat and c.get("disposition") == "allowed")
        cat_rate = (cat_allowed / count * 100) if count > 0 else 0
        cat_lines.append(
            Li(
                cases_link(cat, category=cat), f": ",
                cases_link(pl(count), category=cat),
                f" (",
                cases_link(f"{cat_allowed} granted", category=cat, disposition="allowed"),
                f", {cat_rate:.0f}% grant rate)",
                cls="text-sm",
            )
        )

    sections.append(
        Div(
            H2("By Category", cls="text-base font-semibold mb-2"),
            P("Cases broken down by the type of decision under review:", cls="text-sm text-muted-foreground mb-2"),
            Ul(*cat_lines, cls="list-disc list-inside space-y-1"),
            cls="mb-6",
        )
    )

    # Judge breakdown
    judge_lines = []
    for judge, js in s["judge_stats"].items():
        judge_lines.append(
            Li(
                f"Justice ",
                cases_link(judge, judge=judge), f": ",
                cases_link(pl(js['total']), judge=judge),
                f" (",
                cases_link(f"{js['allowed']} granted", judge=judge, disposition="allowed"),
                f")",
                cls="text-sm",
            )
        )

    sections.append(
        Div(
            H2("By Judge", cls="text-base font-semibold mb-2"),
            Ul(*judge_lines, cls="list-disc list-inside space-y-1"),
            cls="mb-6",
        )
    )

    # Nationality breakdown
    if s["nationality_counts"]:
        nat_lines = []
        for nat, count in s["nationality_counts"].items():
            nat_allowed = sum(1 for c in cases if c.get("nationality") == nat and c.get("disposition") == "allowed")
            nat_lines.append(
                Li(
                    cases_link(nat, nationality=nat), f": ",
                    cases_link(pl(count), nationality=nat),
                    f" (",
                    cases_link(f"{nat_allowed} granted", nationality=nat, disposition="allowed"),
                    f")",
                    cls="text-sm",
                )
            )

        sections.append(
            Div(
                H2("By Nationality", cls="text-base font-semibold mb-2"),
                Ul(*nat_lines, cls="list-disc list-inside space-y-1"),
                cls="mb-6",
            )
        )

    return Container(
        page_header("stats"),
        *sections,
        cls="max-w-2xl mx-auto px-4",
    )


serve(host="0.0.0.0", port=int(os.getenv("PORT", 5001)))
