"""Render the two-page case study from the digit-free template and metrics.json.

The template ``case-study/template/case_study.template.html`` contains no figure
of its own -- every number is a ``{{placeholder}}`` that is filled here from
``data/metrics.json``, block ``case_study`` (decision A5). The two analysis
charts are drawn as inline SVG from the weekly series in the same file, so the
document needs no image file and no charting library.

The build fails loudly rather than quietly (decision A13):

* a placeholder without a value in ``metrics.json``  -> error
* a ``{{...}}`` left over in the rendered document   -> error
* a justification sentence longer than 110 characters -> error (OP-17)
* a PDF that is not exactly two pages or above 700 KB -> error (tools/pdf.py)

Usage::

    python case-study/build_case_study.py
    python case-study/build_case_study.py --tool-url "https://example.org/cockpit"

The address of the published tool is kept in one place, ``site.json`` at the
repository root (key ``tool_url``); ``--tool-url`` overrides it for one run.
Without an address the line that would carry it is left out entirely -- a
visible placeholder in an application document would be an error.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "data"))

import formatting as fmt  # noqa: E402  (path is set above)
from tools.pdf import PdfError, html_to_pdf  # noqa: E402

TEMPLATE = ROOT / "case-study" / "template" / "case_study.template.html"
RENDERED = ROOT / "case-study" / "case_study.html"
PDF = ROOT / "case-study" / "Case_Study_Julian_Wueltner.pdf"
METRICS = ROOT / "data" / "metrics.json"
SITE = ROOT / "site.json"

PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}")
REASON = re.compile(r'<span class="begruendung">(.*?)</span>', re.S)

#: Statements about the data that are filled from metrics.json rather than typed
#: into the template: the responsible department of a finding, its traffic light,
#: the rating of an evaluation cell and the responsible roles. They are written as
#: HTML comments so the template stays free of figures and of claims (A5).
MARKER = re.compile(r"<!--([A-Z]+)(?::([^>]*?))?-->")

#: Traffic light after F1 / UI_GUIDE 3.3. The colour carries the symbol only; the
#: label is printed in the body colour (OP-11).
AMPEL = {
    "rot": ("rot", "■", "Handlungsbedarf"),
    "gelb": ("gelb", "▲", "beobachten"),
    "gruen": ("gruen", "●", "Ziel erreicht"),
}

#: Filled at build time, not from metrics.json (decision A13).
BUILD_TIME_PLACEHOLDERS = {"TOOL_URL"}

#: The paragraph that carries the address. Without an address it is removed
#: as a whole, so the document never shows a placeholder.
TOOL_URL_PARAGRAPH = re.compile(r"[ \t]*<p\b[^>]*>[^<]*\{\{\s*TOOL_URL\s*\}\}[^<]*</p>\n?")


def site_tool_url() -> str | None:
    """The single source of the tool address (site.json), or None if not yet set."""
    if not SITE.exists():
        return None
    value = json.loads(SITE.read_text(encoding="utf-8")).get("tool_url") or ""
    return value.strip() or None

#: Longest admissible justification sentence in the evaluation matrix (OP-17).
REASON_LIMIT = 110


class BuildError(RuntimeError):
    """The case study could not be rendered."""


# --------------------------------------------------------------------------- #
# Chart drawing -- inline SVG, built from the series in metrics.json
# --------------------------------------------------------------------------- #

# Geometry of both charts, in user units of the viewBox. The SVG scales to the
# column width, so these numbers are proportions, not millimetres.
VIEW_W, VIEW_H = 240.0, 112.0
PLOT_L, PLOT_R = 34.0, 233.0
PLOT_T, PLOT_B = 11.0, 89.0

COLOR_SERIES = "#2f4f6f"
COLOR_TARGET = "#2e7d32"
COLOR_START = "#b3261e"
COLOR_GRID = "#ccd2d7"
COLOR_LABEL = "#5a6670"


def nice_domain(values: list[float], *, include: float) -> tuple[float, float, float]:
    """Return ``(minimum, maximum, step)`` of an axis that covers every value.

    The step is chosen from a fixed ladder so the labels stay readable numbers
    instead of the arbitrary result of dividing the range by five.
    """
    low = min(min(values), include)
    high = max(max(values), include)
    if high == low:  # a flat series still needs an axis with extent
        high = low + 1.0

    span = high - low
    magnitude = 10.0 ** (len(str(int(abs(span)))) - 1) if span >= 1 else 0.1
    for factor in (0.1, 0.2, 0.25, 0.5, 1.0, 2.0, 2.5, 5.0, 10.0):
        step = magnitude * factor
        if span / step <= 5:
            break
    minimum = step * math.floor(low / step)
    maximum = step * math.ceil(high / step)
    while (maximum - minimum) / step > 6:
        step *= 2
        minimum = step * math.floor(minimum / step)
        maximum = step * math.ceil(maximum / step)
    return minimum, maximum, step


def line_chart(
    *,
    series: list[dict],
    scale: float,
    target: float,
    target_label: str,
    start_week: int,
    start_label: str,
    y_title: str,
    x_title: str,
    tick_format,
    title: str,
    description: str,
) -> str:
    """Draw one weekly line chart as inline SVG.

    Every element that carries meaning is labelled in words: the axes name their
    unit, the target line and the starting week carry their own text. Series,
    target line and start marker differ in colour **and** dash pattern **and**
    marker shape, so the chart survives a black-and-white printout.
    """
    weeks = [int(point["week"]) for point in series]
    values = [float(point["value"]) * scale for point in series]
    target_scaled = target * scale

    y_min, y_max, y_step = nice_domain(values, include=target_scaled)
    w_min, w_max = min(weeks), max(weeks)

    def x_of(week: int) -> float:
        if w_max == w_min:
            return (PLOT_L + PLOT_R) / 2
        return PLOT_L + (week - w_min) / (w_max - w_min) * (PLOT_R - PLOT_L)

    def y_of(value: float) -> float:
        return PLOT_B - (value - y_min) / (y_max - y_min) * (PLOT_B - PLOT_T)

    parts: list[str] = []
    parts.append(
        f'<svg viewBox="0 0 {VIEW_W:g} {VIEW_H:g}" role="img" '
        f'xmlns="http://www.w3.org/2000/svg" aria-labelledby="t-{start_week} d-{start_week}">'
    )
    parts.append(f'<title id="t-{start_week}">{title}</title>')
    parts.append(f'<desc id="d-{start_week}">{description}</desc>')

    # Horizontal grid with value labels
    ticks: list[float] = []
    value = y_min
    while value <= y_max + y_step / 1000:
        ticks.append(value)
        value += y_step
    for tick in ticks:
        y = y_of(tick)
        parts.append(
            f'<line x1="{PLOT_L:.1f}" y1="{y:.1f}" x2="{PLOT_R:.1f}" y2="{y:.1f}" '
            f'stroke="{COLOR_GRID}" stroke-width="0.5"/>'
        )
        parts.append(
            f'<text x="{PLOT_L - 2.5:.1f}" y="{y + 2:.1f}" text-anchor="end" '
            f'font-size="6" fill="{COLOR_LABEL}">{tick_format(tick)}</text>'
        )

    # Axes
    parts.append(
        f'<line x1="{PLOT_L:.1f}" y1="{PLOT_T:.1f}" x2="{PLOT_L:.1f}" y2="{PLOT_B:.1f}" '
        f'stroke="{COLOR_LABEL}" stroke-width="0.7"/>'
    )
    parts.append(
        f'<line x1="{PLOT_L:.1f}" y1="{PLOT_B:.1f}" x2="{PLOT_R:.1f}" y2="{PLOT_B:.1f}" '
        f'stroke="{COLOR_LABEL}" stroke-width="0.7"/>'
    )

    # Week labels: first, last, the starting week and a few round numbers between
    label_weeks = sorted({w_min, w_max, start_week} | {w for w in weeks if w % 10 == 0})
    label_weeks = [w for w in label_weeks if w_min <= w <= w_max]
    kept: list[int] = []
    for week in label_weeks:
        if kept and x_of(week) - x_of(kept[-1]) < 16:
            if week in (w_max, start_week):
                kept.pop()
            else:
                continue
        kept.append(week)
    for week in kept:
        x = x_of(week)
        parts.append(
            f'<line x1="{x:.1f}" y1="{PLOT_B:.1f}" x2="{x:.1f}" y2="{PLOT_B + 2:.1f}" '
            f'stroke="{COLOR_LABEL}" stroke-width="0.7"/>'
        )
        parts.append(
            f'<text x="{x:.1f}" y="{PLOT_B + 8:.1f}" text-anchor="middle" '
            f'font-size="6" fill="{COLOR_LABEL}">{week}</text>'
        )

    # Target line, dashed, with its own label
    y_target = y_of(target_scaled)
    parts.append(
        f'<line x1="{PLOT_L:.1f}" y1="{y_target:.1f}" x2="{PLOT_R:.1f}" y2="{y_target:.1f}" '
        f'stroke="{COLOR_TARGET}" stroke-width="1.1" stroke-dasharray="5 3"/>'
    )
    parts.append(
        f'<text x="{PLOT_R:.1f}" y="{y_target - 2.2:.1f}" text-anchor="end" '
        f'font-size="6" fill="{COLOR_LABEL}">{target_label}</text>'
    )

    # Marker of the starting week, dotted, with its own label
    x_start = x_of(start_week)
    parts.append(
        f'<line x1="{x_start:.1f}" y1="{PLOT_T:.1f}" x2="{x_start:.1f}" y2="{PLOT_B:.1f}" '
        f'stroke="{COLOR_START}" stroke-width="1.1" stroke-dasharray="2 2"/>'
    )
    anchor = "end" if x_start > (PLOT_L + PLOT_R) / 2 else "start"
    offset = -2.0 if anchor == "end" else 2.0
    parts.append(
        f'<text x="{x_start + offset:.1f}" y="{PLOT_T + 5:.1f}" text-anchor="{anchor}" '
        f'font-size="6" fill="{COLOR_LABEL}">{start_label}</text>'
    )

    # The series itself
    points = " ".join(f"{x_of(w):.1f},{y_of(v):.1f}" for w, v in zip(weeks, values))
    parts.append(
        f'<polyline points="{points}" fill="none" stroke="{COLOR_SERIES}" '
        f'stroke-width="1.6" stroke-linejoin="round"/>'
    )

    # Triangle on the starting week: the marker is readable without colour
    if start_week in weeks:
        vy = y_of(values[weeks.index(start_week)])
        parts.append(
            f'<polygon points="{x_start:.1f},{vy - 3:.1f} {x_start - 2.6:.1f},{vy + 1.6:.1f} '
            f'{x_start + 2.6:.1f},{vy + 1.6:.1f}" fill="{COLOR_START}"/>'
        )

    # Axis titles, each with its unit
    parts.append(
        f'<text x="8" y="{(PLOT_T + PLOT_B) / 2:.1f}" text-anchor="middle" font-size="6" '
        f'fill="{COLOR_LABEL}" transform="rotate(-90 8 {(PLOT_T + PLOT_B) / 2:.1f})">{y_title}</text>'
    )
    parts.append(
        f'<text x="{(PLOT_L + PLOT_R) / 2:.1f}" y="{VIEW_H - 3:.1f}" text-anchor="middle" '
        f'font-size="6" fill="{COLOR_LABEL}">{x_title}</text>'
    )

    parts.append("</svg>")
    return "".join(parts)


def ampel_markup(finding: dict) -> str:
    """Traffic light of one finding, derived from its own data.

    ``docs/KPI_DEFINITIONS.md`` rule R6 gives every finding exactly one severity
    and one status; the case study must not invent a milder light than the data
    carries. A resolved finding is green, a severe one red, everything else
    yellow.
    """
    if finding.get("status") == "behoben":
        key = "gruen"
    elif finding.get("severity") == "hoch":
        key = "rot"
    else:
        key = "gelb"
    css, symbol, label = AMPEL[key]
    return (
        f'<span class="ampel {css}"><span class="zeichen" aria-hidden="true">'
        f"{symbol}</span>{label}</span>"
    )


def rating_of(metrics: dict, option: str, dimension: str) -> str:
    """Rating of one cell of the evaluation matrix, out of ``decision_paper``."""
    for row in metrics.get("decision_paper", {}).get("evaluation", {}).get("rows", []):
        if row.get("option") == option:
            cell = row.get("cells", {}).get(dimension)
            if not cell:
                break
            return str(cell["rating"])
    raise BuildError(
        f"Bewertung fuer Option {option}, Dimension '{dimension}' fehlt in metrics.json"
    )


def fill_markers(html: str, metrics: dict) -> str:
    """Replace every data marker; an unknown marker breaks the build."""
    measures = metrics.get("measures", [])
    trigger = metrics.get("decision_paper", {}).get("escalation_trigger", {})

    def resolve(match: re.Match[str]) -> str:
        kind, argument = match.group(1), match.group(2) or ""
        if kind == "CHART":
            return match.group(0)  # charts are placed before this pass
        if kind == "FACHBEREICH":
            return str(find_finding(metrics, argument)["department"])
        if kind == "AMPEL":
            return ampel_markup(find_finding(metrics, argument))
        if kind == "EINSTUFUNG":
            option, _, dimension = argument.partition(":")
            return rating_of(metrics, option, dimension)
        if kind == "VERANTWORTLICH":
            owner = trigger.get("owner") or (measures[0].get("owner") if measures else None)
            if not owner:
                raise BuildError("Verantwortlicher fehlt in metrics.json")
            return str(owner)
        if kind == "BETEILIGT":
            involved = measures[0].get("also_affected_departments", []) if measures else []
            if not involved:
                raise BuildError("Beteiligte Fachbereiche fehlen in metrics.json")
            return ", ".join(str(item) for item in involved)
        raise BuildError(f"Unbekannte Datenmarke im Template: {match.group(0)}")

    return MARKER.sub(resolve, html)


def find_finding(metrics: dict, finding_id: str) -> dict:
    for finding in metrics.get("findings", []):
        if finding.get("id") == finding_id:
            return finding
    raise BuildError(f"Auffaelligkeit '{finding_id}' fehlt in metrics.json")


def build_charts(metrics: dict) -> dict[str, str]:
    """Draw both analysis charts from the weekly series of the findings."""
    win = next((f for f in metrics.get("findings", []) if f.get("kpi") == "quote_win_rate"), None)
    lead = next((f for f in metrics.get("findings", []) if f.get("kpi") == "quote_lead_time_h"), None)
    if not win or not lead:
        raise BuildError("Befunde zur Angebotserfolgsquote und Angebotsdurchlaufzeit fehlen")

    kpis = metrics.get("kpis", {})
    target_win = kpis["quote_win_rate"]["target"]
    target_lead = kpis["quote_lead_time_h"]["target"]

    market = win.get("entity", {}).get("market", "")

    chart_win = line_chart(
        series=win["series"],
        scale=100.0,
        target=target_win,
        target_label="Zielwert " + fmt.percent(target_win, 1),
        start_week=int(win["start_week"]),
        start_label="Beginn " + win["start_week_text"],
        y_title="Erfolgsquote in %",
        x_title="Kalenderwoche",
        tick_format=lambda value: fmt.number(value, 0),
        title=f"Angebotserfolgsquote im Markt {market} je Woche",
        description=(
            "Wochenwerte der Angebotserfolgsquote in Prozent mit gestrichelter Zielwertlinie "
            "und gepunkteter Markierung der Beginnwoche."
        ),
    )

    chart_lead = line_chart(
        series=lead["series"],
        scale=1.0,
        target=target_lead,
        target_label="Zielwert " + fmt.number(target_lead, 1) + fmt.NNBSP + "h",
        start_week=int(lead["start_week"]),
        start_label="Beginn " + lead["start_week_text"],
        y_title="Stunden je Angebot",
        x_title="Kalenderwoche",
        tick_format=lambda value: fmt.number(value, 0),
        title=f"Angebotsdurchlaufzeit im Markt {market} je Woche",
        description=(
            "Wochenwerte der Angebotsdurchlaufzeit in Stunden mit gestrichelter "
            "Zielwertlinie und gepunkteter Markierung der Beginnwoche."
        ),
    )
    return {"erfolgsquote": chart_win, "angebotszeit": chart_lead}


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #

def check_reason_length(html: str) -> None:
    """OP-17: no justification sentence longer than 110 characters."""
    too_long = []
    for match in REASON.finditer(html):
        text = re.sub(r"\s+", " ", match.group(1)).strip()
        if len(text) > REASON_LIMIT:
            too_long.append(f"{len(text)} Zeichen: {text}")
    if too_long:
        raise BuildError(
            f"Begruendungssaetze ueber {REASON_LIMIT} Zeichen (OP-17):\n" + "\n".join(too_long)
        )


def render(template: str, metrics: dict, tool_url: str | None) -> tuple[str, list[str]]:
    values = metrics.get("case_study")
    if not values:
        raise BuildError("Block 'case_study' fehlt in data/metrics.json")

    used = sorted(set(PLACEHOLDER.findall(template)))
    missing = [key for key in used if key not in values and key not in BUILD_TIME_PLACEHOLDERS]
    if missing:
        raise BuildError(
            "Platzhalter ohne Wert in metrics.json['case_study'] (Entscheidung A13):\n"
            + "\n".join(missing)
        )

    charts = build_charts(metrics)
    html = template
    for name, svg in charts.items():
        marker = f"<!--CHART:{name}-->"
        if marker not in html:
            raise BuildError(f"Grafikmarke {marker} fehlt in der Vorlage")
        html = html.replace(marker, svg)

    html = fill_markers(html, metrics)

    if tool_url:
        link = f'<a href="{tool_url}">{tool_url}</a>'
    else:
        html = TOOL_URL_PARAGRAPH.sub("", html)
        link = ""

    def substitute(match: re.Match[str]) -> str:
        key = match.group(1)
        if key == "TOOL_URL":
            return link
        return str(values[key])

    html = PLACEHOLDER.sub(substitute, html)

    stale = sorted({m.group(0) for m in MARKER.finditer(html)})
    if stale:
        raise BuildError("Nicht aufgeloeste Datenmarken: " + ", ".join(stale))

    leftovers = sorted(set(PLACEHOLDER.findall(html)))
    if leftovers:
        raise BuildError(
            "Unaufgeloeste Platzhalter im fertigen Dokument (Entscheidung A13): "
            + ", ".join(leftovers)
        )

    check_reason_length(html)
    return html, used


def main() -> int:
    parser = argparse.ArgumentParser(description="Case Study rendern und als PDF ausgeben.")
    parser.add_argument(
        "--tool-url",
        dest="tool_url",
        default=None,
        help="Adresse des veroeffentlichten Cockpits; Standard ist tool_url aus site.json.",
    )
    parser.add_argument(
        "--no-pdf",
        action="store_true",
        help="Nur die HTML-Datei erzeugen, kein PDF (fuer schnelle Durchlaeufe).",
    )
    arguments = parser.parse_args()

    if not TEMPLATE.exists():
        print(f"Vorlage fehlt: {TEMPLATE}")
        return 1
    if not METRICS.exists():
        print(f"Kennzahlen fehlen: {METRICS}")
        return 1

    metrics = json.loads(METRICS.read_text(encoding="utf-8"))
    template = TEMPLATE.read_text(encoding="utf-8")

    try:
        tool_url = arguments.tool_url or site_tool_url()
        html, used = render(template, metrics, tool_url)
    except BuildError as error:
        print(f"Abbruch: {error}")
        return 1

    RENDERED.write_text(html, encoding="utf-8")
    print(f"{RENDERED.name}: {len(used)} Platzhalter aufgeloest, {len(html) / 1024:.0f} KB")
    if not tool_url:
        print("Hinweis: keine Tool-Adresse in site.json -- die Zeile mit der Adresse entfaellt.")

    if arguments.no_pdf:
        return 0

    try:
        result = html_to_pdf(RENDERED, PDF, expect_pages=2, max_kb=700)
    except PdfError as error:
        print(f"Abbruch: {error}")
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
