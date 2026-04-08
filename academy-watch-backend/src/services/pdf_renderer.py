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

import base64
import html as html_lib
import logging
import os
import re
from datetime import date, datetime
from typing import Any, Iterable

logger = logging.getLogger(__name__)

# Public origin used to absolutize links inside the exported chat PDF so that
# ``/players/123`` inside an LLM response becomes a clickable link when the
# PDF is opened outside the browser. Falls back to the production host if the
# env var isn't set so local dev exports still produce reachable links.
_DEFAULT_PUBLIC_BASE_URL = "https://theacademywatch.com"


def _public_base_url() -> str:
    base = (os.getenv("PUBLIC_BASE_URL") or os.getenv("PUBLIC_API_BASE_URL") or "").strip()
    if not base:
        base = _DEFAULT_PUBLIC_BASE_URL
    return base.rstrip("/")


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
    color-adjust: exact;
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


# ---------------------------------------------------------------------------
# GOL chat export
# ---------------------------------------------------------------------------

# Columns that the frontend/backend treat as internal plumbing and should
# never appear in an exported artifact. Mirrors the HIDDEN_COLUMNS list in
# `academy-watch-frontend/src/components/gol/exportChat.js`.
_GOL_HIDDEN_COLUMNS = {"player_api_id"}


_REL_HREF_PATTERN = re.compile(
    r'(<a\b[^>]*\bhref=")(/[^"#][^"]*)"',
    flags=re.IGNORECASE,
)

# Recognises bare ``http(s)://…`` URLs so that plain-text cells (e.g. a
# DataFrame column containing a tweet URL) get wrapped in a clickable
# anchor. Deliberately narrow: we only match URLs that stand alone in a
# text context, and we rely on the caller to apply this to already-escaped
# text so there's no HTML-injection risk.
_BARE_URL_PATTERN = re.compile(
    r"(https?://[^\s<>\"'()]+[^\s<>\"'().,;!?])",
    flags=re.IGNORECASE,
)


def _absolutize_links(html: str, base_url: str) -> str:
    """Rewrite root-relative ``href="/..."`` links to use ``base_url``.

    WeasyPrint turns any ``<a href>`` into a clickable PDF link annotation,
    but if the href is relative the link is effectively dead once the PDF
    leaves the browser. This helper rewrites only root-relative hrefs
    (``/players/123``) — fragment-only (``#section``), scheme-relative
    (``//cdn...``) and already-absolute hrefs are left alone.
    """
    if not html or not base_url:
        return html
    base = base_url.rstrip("/")

    def _replace(match: re.Match[str]) -> str:
        prefix = match.group(1)
        path = match.group(2)
        return f'{prefix}{base}{path}"'

    return _REL_HREF_PATTERN.sub(_replace, html)


def _markdown_to_html(text: str) -> str:
    """Render GOL markdown content to safe HTML.

    Uses ``markdown-it-py`` with a GFM-like preset so tables, autolinks and
    strikethrough work. If ``linkify-it-py`` is installed we also turn bare
    ``https://…`` URLs (including tweet / x.com links) into clickable
    anchors. Any relative links emitted by the LLM are absolutized to the
    public origin so they remain clickable once the PDF leaves the browser.

    The renderer degrades gracefully in three stages:
      1. markdown-it + linkify  (production, best fidelity)
      2. markdown-it alone      (explicit ``[text](url)`` still works)
      3. plain escape + wrap    (last resort so the PDF is never broken)
    """
    if not text:
        return ""

    rendered: str | None = None
    try:
        from markdown_it import MarkdownIt  # type: ignore

        # linkify-it-py is optional. The ``gfm-like`` preset enables the
        # linkify rule by default; if the backing module is missing,
        # md.render() itself raises, so we must explicitly *disable*
        # linkify when linkify-it-py isn't importable.
        try:
            import linkify_it  # type: ignore  # noqa: F401

            has_linkify = True
        except ImportError:
            has_linkify = False

        md = MarkdownIt("gfm-like")
        if has_linkify:
            md.options["linkify"] = True
        else:
            md.disable("linkify")
        rendered = md.render(text)
    except Exception:
        logger.warning("markdown-it-py unavailable, falling back to plain wrap")

    if rendered is None:
        escaped = (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        # Post-process the escaped plain text to wrap bare http(s) URLs in
        # anchors — important for the fallback path because without
        # markdown-it we'd otherwise lose every link.
        escaped = _BARE_URL_PATTERN.sub(
            lambda m: f'<a href="{m.group(1)}">{m.group(1)}</a>',
            escaped,
        )
        paragraphs = [p.strip() for p in escaped.split("\n\n") if p.strip()]
        rendered = "\n".join(
            f"<p>{p.replace(chr(10), '<br/>')}</p>" for p in paragraphs
        )

    return _absolutize_links(rendered, _public_base_url())


def _filter_hidden_columns(
    columns: list[str], rows: list[list[Any]]
) -> tuple[list[str], list[list[Any]]]:
    """Drop any column whose header is in the internal-only allowlist."""
    visible_indices = [
        idx for idx, col in enumerate(columns) if col not in _GOL_HIDDEN_COLUMNS
    ]
    filtered_cols = [columns[idx] for idx in visible_indices]
    filtered_rows = [
        [row[idx] if idx < len(row) else None for idx in visible_indices]
        for row in rows
    ]
    return filtered_cols, filtered_rows


# Column-name patterns that identify "link anchor" cells and the ID column
# that should be used to build the destination URL. The first entry that
# matches both a name column and an id column wins; the id column is
# subsequently hidden from the visible output so stakeholders don't see raw
# API ids in the exported table.
_LINK_RULES: list[tuple[tuple[str, ...], tuple[str, ...], str]] = [
    # (name column candidates, id column candidates, url path prefix)
    (
        ("player_name", "player", "name"),
        ("player_api_id", "player_id"),
        "/players/",
    ),
    (
        (
            "team_name",
            "club_name",
            "loan_club",
            "loan_team",
            "loan_team_name",
            "parent_club",
            "academy_club",
            "current_club_name",
            "origin_club_name",
        ),
        ("team_api_id", "club_api_id", "team_id"),
        "/teams/",
    ),
]


def _build_linkified_table(
    raw_columns: list[str],
    raw_rows: list[list[Any]],
) -> tuple[list[str], list[list[str]]]:
    """Return (visible_columns, rendered_rows) for a GOL table card.

    Each cell in ``rendered_rows`` is an HTML-safe string. Cells under
    linkable name columns are wrapped in ``<a href>`` tags pointing at the
    public site, using the corresponding ID column from the raw row. The ID
    columns themselves are then hidden from the visible output, joining the
    standard hidden-column allowlist.
    """
    base_url = _public_base_url()

    # Work out which columns should become link anchors and which columns
    # provide the IDs for them. A single table can have both player and
    # team links.
    name_to_id_idx: dict[int, tuple[int, str]] = {}
    extra_hidden_indices: set[int] = set()
    lower_cols = [c.lower() for c in raw_columns]
    for name_candidates, id_candidates, prefix in _LINK_RULES:
        name_idx = next(
            (i for i, c in enumerate(lower_cols) if c in name_candidates),
            None,
        )
        id_idx = next(
            (i for i, c in enumerate(lower_cols) if c in id_candidates),
            None,
        )
        if name_idx is not None and id_idx is not None:
            name_to_id_idx[name_idx] = (id_idx, prefix)
            extra_hidden_indices.add(id_idx)

    # Build the visible column list (hidden columns + id columns used for
    # links are removed). We keep the original indices so we can still read
    # the id cell when rendering.
    visible_indices = [
        i
        for i, col in enumerate(raw_columns)
        if col not in _GOL_HIDDEN_COLUMNS and i not in extra_hidden_indices
    ]
    visible_columns = [raw_columns[i] for i in visible_indices]

    def _fmt(cell: Any) -> str:
        if cell is None:
            return "\u2013"
        escaped = html_lib.escape(str(cell))
        # Wrap bare http(s) URLs (e.g. tweet/x.com links sitting in a
        # DataFrame column) in an anchor so they're clickable in the PDF.
        return _BARE_URL_PATTERN.sub(
            lambda m: f'<a href="{m.group(1)}">{m.group(1)}</a>',
            escaped,
        )

    rendered_rows: list[list[str]] = []
    for row in raw_rows:
        out_row: list[str] = []
        for i in visible_indices:
            cell = row[i] if i < len(row) else None
            link_info = name_to_id_idx.get(i)
            if link_info is not None:
                id_idx, prefix = link_info
                id_value = row[id_idx] if id_idx < len(row) else None
                if id_value is not None and cell is not None:
                    href = f"{base_url}{prefix}{html_lib.escape(str(id_value))}"
                    out_row.append(
                        f'<a href="{href}">{_fmt(cell)}</a>'
                    )
                    continue
            out_row.append(_fmt(cell))
        rendered_rows.append(out_row)

    return visible_columns, rendered_rows


def _normalize_gol_data_card(card: dict[str, Any]) -> dict[str, Any] | None:
    """Convert a raw SSE ``data_card`` payload into a flat dict the Jinja2
    template can iterate over.

    The SSE shape is::

        {
          "type": "analysis_result",
          "payload": {
            "result_type": "table" | "scalar" | "list" | "dict" | "error",
            "display":     "table" | "bar_chart" | "line_chart" | "number" | "list" | ...,
            "columns":     [...],   # table / chart only
            "rows":        [...],   # table / chart only
            "value":       ...,     # scalar only
            "items":       [...],   # list only
            "data":        {...},   # dict only
            "error":       str,     # error only
            "meta":        {"description": str},
            "total_rows":  int,
            "truncated":   bool,
          }
        }

    Chart renderings are produced eagerly here so the returned dict carries a
    ``chart_image_data_uri`` ready to splice into an ``<img src>`` tag.
    """
    if not isinstance(card, dict):
        return None
    payload = card.get("payload") or {}
    if not isinstance(payload, dict):
        return None

    result_type = payload.get("result_type")
    display = payload.get("display")
    meta = payload.get("meta") or {}
    description = meta.get("description") if isinstance(meta, dict) else None

    # Charts. The backend sandbox emits bar/line charts as tables with a
    # ``display`` hint, so we detect them from display rather than
    # result_type. Render the PNG via the generic matplotlib helpers and
    # embed it as a data URI. We also keep the raw table data so a small
    # summary table can appear beneath the chart — useful for stakeholders
    # who want the numbers behind the picture.
    if display in ("bar_chart", "line_chart"):
        columns = payload.get("columns") or []
        rows = payload.get("rows") or []
        if not columns or not rows:
            return {
                "kind": "empty",
                "description": description,
            }

        # The chart is rendered from the numeric-first cells, so we use the
        # hidden-column-filtered copy for matplotlib. The summary table
        # under the chart, however, is linkified like a regular table card.
        chart_columns, chart_rows = _filter_hidden_columns(columns, rows)
        try:
            from src.services.chart_renderer import (
                render_generic_bar_chart,
                render_generic_line_chart,
            )

            renderer = (
                render_generic_bar_chart
                if display == "bar_chart"
                else render_generic_line_chart
            )
            png_bytes = renderer(chart_columns, chart_rows, title=description or None)
            data_uri = "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")
        except Exception:
            logger.exception("Failed to render GOL chart; falling back to table")
            visible_cols, rendered_rows = _build_linkified_table(columns, rows)
            return {
                "kind": "table",
                "description": description,
                "columns": visible_cols,
                "rendered_rows": rendered_rows,
                "total_rows": payload.get("total_rows"),
                "truncated": bool(payload.get("truncated")),
            }

        # Keep the numeric summary table alongside the chart only when it's
        # small enough to be useful — more than ~8 rows and it starts to
        # overwhelm the chart visually.
        if len(rows) <= 8:
            visible_cols, rendered_rows = _build_linkified_table(columns, rows)
        else:
            visible_cols, rendered_rows = None, None
        return {
            "kind": "chart",
            "description": description,
            "chart_image_data_uri": data_uri,
            "table_columns": visible_cols,
            "rendered_rows": rendered_rows,
        }

    # Tables.
    if result_type == "table" or display == "table":
        columns = payload.get("columns") or []
        rows = payload.get("rows") or []
        visible_cols, rendered_rows = _build_linkified_table(columns, rows)
        return {
            "kind": "table",
            "description": description,
            "columns": visible_cols,
            "rendered_rows": rendered_rows,
            "total_rows": payload.get("total_rows"),
            "truncated": bool(payload.get("truncated")),
        }

    # Scalars.
    if result_type == "scalar" or display == "number":
        columns = payload.get("columns") or []
        label = columns[0] if columns else None
        return {
            "kind": "number",
            "description": description,
            "label": label,
            "value": payload.get("value"),
        }

    # Lists.
    if result_type == "list":
        return {
            "kind": "list",
            "description": description,
            "items": [str(item) for item in (payload.get("items") or [])],
        }

    # Dicts.
    if result_type == "dict":
        data = payload.get("data") or {}
        return {
            "kind": "dict",
            "description": description,
            "data": data if isinstance(data, dict) else {},
        }

    # Errors.
    if result_type == "error":
        return {
            "kind": "error",
            "description": description,
            "error": payload.get("error") or "Analysis error",
        }

    return None


def _normalize_gol_messages(
    messages: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Filter + normalize the raw client-side message list for templating.

    - Drops empty assistant messages (tool-call placeholders with no text
      and no data cards).
    - Renders markdown bodies to HTML once, so the template can simply
      ``{{ content_html | safe }}``.
    - Normalizes every data card to a flat dict keyed by ``kind``.
    """
    normalized: list[dict[str, Any]] = []
    for msg in messages or []:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        if role not in ("user", "assistant"):
            continue
        content = (msg.get("content") or "").strip()
        raw_cards = msg.get("dataCards") or msg.get("data_cards") or []
        cards: list[dict[str, Any]] = []
        if role == "assistant":
            for raw in raw_cards:
                norm = _normalize_gol_data_card(raw)
                if norm is not None:
                    cards.append(norm)
            if not content and not cards:
                # Skip loading placeholders that carry neither text nor data.
                continue
        normalized.append(
            {
                "role": role,
                "content_html": _markdown_to_html(content) if content else "",
                "data_cards": cards if role == "assistant" else [],
            }
        )
    return normalized


def render_gol_chat_pdf(messages: list[dict[str, Any]]) -> tuple[bytes, str]:
    """Render a GOL chat transcript to a PDF.

    Calls WeasyPrint directly rather than going through :func:`html_to_pdf`
    because the GOL template owns its own ``@page`` rule (landscape A4, to
    give data tables enough horizontal room) — the newsletter print CSS
    injected by :func:`html_to_pdf` forces portrait A4 and would override
    it.

    Parameters
    ----------
    messages:
        The client-side message array (role / content / dataCards) as sent
        by the frontend chat state.

    Returns
    -------
    tuple[bytes, str]
        PDF bytes and a suggested download filename.
    """
    # Imported lazily to avoid import errors when WeasyPrint's system
    # libraries aren't installed in dev.
    from weasyprint import HTML  # type: ignore
    from flask import render_template, request

    normalized = _normalize_gol_messages(messages)
    exported_date = datetime.utcnow().strftime("%d %B %Y")
    html = render_template(
        "gol_chat_export.html",
        messages=normalized,
        exported_date=exported_date,
        site_url=_public_base_url(),
    )

    try:
        base_url = request.url_root
    except RuntimeError:
        base_url = None

    pdf_bytes = HTML(string=html, base_url=base_url).write_pdf()
    filename = (
        "gol-chat-"
        + datetime.utcnow().strftime("%Y-%m-%d-%H%M%S")
        + ".pdf"
    )
    return pdf_bytes, filename
