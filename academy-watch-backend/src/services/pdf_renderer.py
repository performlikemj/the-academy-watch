"""PDF rendering for newsletters.

Converts rendered newsletter HTML (from ``newsletter_email.html`` Jinja2
template) into a paginated PDF via WeasyPrint. The email template is already
narrow (600px), single-column, and styled in the Tactical Lens design system,
which makes it ideal as a PDF source: we only need to inject a small print
stylesheet that enforces clean page breaks around atomic content units
(player cards, highlights, the table of contents, match blocks, etc.).

Public API:
    html_to_pdf(html, base_url=None) -> bytes
        Inject print CSS and render the provided HTML string to PDF bytes.

    build_pdf_filename(team_name, week_end_date, newsletter_id) -> str
        Deterministic, filesystem-safe filename for downloads.

The renderer is deliberately unaware of the Newsletter model and the Jinja2
context. The route in ``api.py`` is responsible for loading the newsletter,
building the template context, and calling ``render_template``; it then hands
the resulting HTML here. This keeps the pdf_renderer free of circular
dependencies on the routes module.
"""

from __future__ import annotations

import re
from datetime import date, datetime


# Print stylesheet injected before </head> prior to handing HTML to WeasyPrint.
#
# The class names referenced below are verified against
# ``src/templates/newsletter_email.html``:
#   .item            — a single player card (atomic; do not split across pages)
#   .item-header     — player card header row (name, loan club, headshot)
#   .highlights      — top-of-issue highlights panel
#   .toc             — in-this-issue table of contents block
#   .matches-section — per-player "this week's matches" block
#   .match-row       — individual match row inside .matches-section
#   .es-card         — expanded stats subcard (attacking/passing/defending/etc.)
#   .tweet-card      — embedded tweet reaction
#   .footer          — email footer (kept in PDF, including unsubscribe link)
#
# Sections in the email template are bare <h2> tags followed by flat .item
# divs — there is no wrapping .section element. The rule
# ``.content h2 { break-before: page }`` therefore forces a page break at the
# start of each section (First Team, On Loan, Academy Rising). The first <h2>
# naturally appears after the highlights + TOC on page 1, so it correctly
# starts the first section on page 2.
_PRINT_CSS = """
<style id="pdf-print-css">
@page {
    size: A4;
    margin: 18mm 16mm 22mm 16mm;
    @bottom-center {
        content: "The Academy Watch \\00B7 Page " counter(page) " of " counter(pages);
        font-family: 'Inter', 'DejaVu Sans', sans-serif;
        font-size: 9pt;
        color: #64748b;
    }
}

/* Force the dark Tactical Lens background to render in print.
   WeasyPrint honours backgrounds by default, but we make the intent explicit. */
html, body {
    background: #0b1326 !important;
    -weasy-color-adjust: exact;
    print-color-adjust: exact;
}

/* Atomic content units — never split these across pages. If any block is
   genuinely taller than a page WeasyPrint will fall back to splitting it,
   which is the correct behaviour. */
.item,
.item-header,
.highlights,
.toc,
.matches-section,
.match-row,
.es-card,
.tweet-card,
.sofascore-card,
.notes,
img,
table {
    break-inside: avoid;
    page-break-inside: avoid;
}

/* Keep section headings with their next sibling so we never orphan a title
   at the bottom of a page. */
h1, h2, h3 {
    break-after: avoid-page;
    page-break-after: avoid;
}

/* Force each top-level newsletter section onto a fresh page for
   stakeholder scan-ability. The first <h2> lives after the highlights/TOC
   on page 1, so this naturally starts the first section on page 2. */
.content h2 {
    break-before: page;
    page-break-before: always;
}

/* Widows and orphans on body copy. */
p, li {
    orphans: 3;
    widows: 3;
}

/* Give the expanded stats grid a little more room to lay out cleanly. */
.expanded-stats {
    page-break-inside: auto;
    break-inside: auto;
}
</style>
"""


def _inject_print_css(html: str) -> str:
    """Splice the print stylesheet into the document ``<head>``.

    Falls back to prepending the style block if no ``</head>`` is found — that
    shouldn't happen with the current Jinja2 template but makes the function
    robust against template changes.
    """
    if not html:
        return _PRINT_CSS
    # Case-insensitive replace of the first </head>.
    match = re.search(r"</head\s*>", html, flags=re.IGNORECASE)
    if match:
        idx = match.start()
        return html[:idx] + _PRINT_CSS + html[idx:]
    return _PRINT_CSS + html


def html_to_pdf(html: str, base_url: str | None = None) -> bytes:
    """Render newsletter HTML to a PDF byte string.

    Parameters
    ----------
    html:
        Fully rendered newsletter HTML (typically the output of
        ``render_template('newsletter_email.html', **context)``).
    base_url:
        Base URL used by WeasyPrint to resolve any relative asset references.
        For newsletters generated from an HTTP request this should be
        ``request.url_root`` so that team logos and chart images load
        correctly when the template emits relative URLs. Absolute URLs and
        data URIs are unaffected.

    Returns
    -------
    bytes
        A complete PDF document.
    """
    # Imported lazily so that the module can be imported in environments where
    # WeasyPrint's system libraries (libpango, libcairo, …) are not yet
    # installed — e.g. during static analysis or partial local runs.
    from weasyprint import HTML  # type: ignore

    augmented = _inject_print_css(html)
    return HTML(string=augmented, base_url=base_url).write_pdf()


_FILENAME_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _slugify_filename_component(value: str) -> str:
    cleaned = _FILENAME_SAFE.sub("-", (value or "").strip()).strip("-")
    return cleaned or "newsletter"


def build_pdf_filename(
    team_name: str | None,
    week_end_date: date | datetime | None,
    newsletter_id: int,
) -> str:
    """Return a deterministic, filesystem-safe PDF filename.

    Example: ``nottingham-forest-2026-04-06-issue-42.pdf``
    """
    team_slug = _slugify_filename_component(team_name or "newsletter").lower()
    if isinstance(week_end_date, datetime):
        date_part = week_end_date.date().isoformat()
    elif isinstance(week_end_date, date):
        date_part = week_end_date.isoformat()
    else:
        date_part = ""
    parts = [team_slug]
    if date_part:
        parts.append(date_part)
    parts.append(f"issue-{int(newsletter_id)}")
    return "-".join(parts) + ".pdf"
