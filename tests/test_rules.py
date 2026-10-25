"""Guardrail tests for the project's non-negotiable rules (PROMPT.md, section 2).

These tests are owned by the program lead, not by a single role. They scan the whole
repository for violations that would disqualify the work sample:

* real company, brand or logistics provider names anywhere in the deliverables
* the word "KI" used for something that is rule-based or statistical
* API keys or credentials
* the mandatory disclosure line missing from the tool or the case study
* external sources other than the two that are allowed
* numbers written by hand into the case study template

The blocklist below necessarily contains the very names it forbids, so this file
excludes itself from every scan.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# --------------------------------------------------------------------------- #
# Repository scanning helpers
# --------------------------------------------------------------------------- #

SCANNED_SUFFIXES = {".md", ".py", ".html", ".json", ".mjs", ".js", ".css", ".txt"}
SKIPPED_DIRS = {".git", "node_modules", "__pycache__", ".pytest_cache", ".venv", "venv"}
SELF = Path(__file__).resolve()


def iter_repo_files() -> list[Path]:
    """Every text file of the project, except this test file itself."""
    files = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in SCANNED_SUFFIXES:
            continue
        if any(part in SKIPPED_DIRS for part in path.parts):
            continue
        if path.resolve() == SELF:
            continue
        files.append(path)
    return sorted(files)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def require(relative_path: str) -> Path:
    """Return a deliverable, or skip while it has not been built yet.

    Completeness itself is asserted by ``test_deliverables_complete``, so a skip
    here never hides a missing file at the end of the project.
    """
    path = ROOT / relative_path
    if not path.exists():
        pytest.skip(f"{relative_path} existiert noch nicht")
    return path


# --------------------------------------------------------------------------- #
# Rule 1 + 2: no real companies, brands, logistics providers
# --------------------------------------------------------------------------- #

# Real names that must never appear. Matched as whole words, case-insensitively.
BLOCKED_NAMES = [
    # Parcel services and postal operators
    "DHL", "DPD", "GLS", "Hermes", "UPS", "FedEx", "TNT", "Trans-o-flex",
    "Deutsche Post", "Oesterreichische Post", "Österreichische Post", "Swiss Post",
    "PostNL", "Colissimo", "Chronopost", "Mondial Relay", "Poste Italiane",
    "Bartolini", "Bpost", "Royal Mail", "Evri", "Colis Prive",
    # Logistics and platform providers
    "Arvato", "Fiege", "Rhenus", "Kuehne", "Kühne", "Dachser", "Schenker",
    "Ingram", "Zalando", "Amazon", "About You", "Shopify", "Salesforce",
    "Microsoft Dynamics", "Zendesk", "Salesfive", "Exotec",
    "Schaefer + Peitz", "Dematic", "Witron", "Vanderlande",
    # Manufacturers and distributors of industrial components
    "Bosch Rexroth", "Rexroth", "Festo", "item Industrietechnik", "Norelem",
    "Ganter", "Kipp", "Misumi", "Würth", "Wuerth", "Hilti", "Schaeffler", "SKF",
    "Igus", "Murrplastik", "Phoenix Contact", "Rittal", "Weidmüller", "Siemens",
    "Trumpf", "Bossard", "Fischer", "Hoffmann Group", "Elesa", "Halder",
]

# Names that collide with ordinary German or English vocabulary ("knapp", "think",
# "Post"). They are matched with exact capitalisation, so the everyday word passes
# and the brand spelling is still caught.
BLOCKED_NAMES_EXACT_CASE = [
    "Knapp", "Think", "Vans", "Ara", "Puma", "Camper", "Otto", "Lloyd", "SAP",
    "Oracle", "SSI", "BRT", "SDA", "TGW",
]


def _blocked_pattern(name: str, ignore_case: bool = True) -> re.Pattern[str]:
    # Whole-word match; tolerate the punctuation that appears inside some names.
    escaped = re.escape(name).replace(r"\ ", r"\s+")
    flags = re.IGNORECASE if ignore_case else 0
    return re.compile(rf"(?<![\w-]){escaped}(?![\w-])", flags)


BLOCKED_PATTERNS = [(name, _blocked_pattern(name)) for name in BLOCKED_NAMES]
BLOCKED_PATTERNS += [
    (name, _blocked_pattern(name, ignore_case=False)) for name in BLOCKED_NAMES_EXACT_CASE
]


def test_no_real_company_or_brand_names():
    """Rule 1 and 2: only fictitious partners; no brands, no logos, no real providers."""
    hits: list[str] = []
    for path in iter_repo_files():
        text = read(path)
        for name, pattern in BLOCKED_PATTERNS:
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                hits.append(f"{rel(path)}:{line} enthaelt '{match.group(0)}' (Blockliste: {name})")
    assert not hits, "Echte Firmen-, Marken- oder Dienstleisternamen gefunden:\n" + "\n".join(hits)


def test_partners_use_neutral_labels():
    """Sales partners must be referred to by their neutral demo labels."""
    spec = require("docs/KPI_DEFINITIONS.md")
    text = read(spec)
    assert "Vertretung 4" in text, "Neutrale Partnerbezeichnung fehlt in den KPI-Definitionen"


# --------------------------------------------------------------------------- #
# Rule 4: honest wording around "KI"
# --------------------------------------------------------------------------- #

# "KI" may only describe how this project was produced, or an explicitly future
# language-model connection -- never the rule-based analysis that is actually built.
ALLOWED_KI_TERMS = {
    "KI-Unterstützung",
    "KI-Unterstuetzung",
    "KI-Agententeam",
    "KI-Agenten",
    "KI-Einsatz",
    "KI-Anbindung",
    "KI-basierte",
    "KI-basierten",
    "KI-basierter",
    "KI-Auswertungen",
    "KI-Werkzeugen",
    "KI-Tools",
    "KI-Schnittstelle",  # only ever used to say that none is built
}

KI_TOKEN = re.compile(r"(?<![\w-])KI(?:-[A-Za-zÄÖÜäöüß]+)?(?![\w-])")

# A bare KI inside quotation marks is a *mention*, not a use: documents have to be
# able to write down the very rule they follow ("heisst automatische Analyse, nie
# 'KI'"). Quoting it is the opposite of claiming it.
KI_MENTION = re.compile(r"[„“”\"»«']KI[“”„\"«»']")

# PROMPT.md quotes the job advertisement verbatim; the agent role files describe how
# the team itself was built. Neither is a deliverable the hiring manager reads.
KI_SCAN_EXCLUDED = {"PROMPT.md"}


def test_rule_based_analysis_is_never_called_ki():
    """Rule 4: what is computed by rules or statistics is an 'automatische Analyse'."""
    hits: list[str] = []
    for path in iter_repo_files():
        if rel(path) in KI_SCAN_EXCLUDED or rel(path).startswith(".claude/"):
            continue
        text = read(path)
        mentions = {match.start() + 1 for match in KI_MENTION.finditer(text)}
        for match in KI_TOKEN.finditer(text):
            token = match.group(0)
            if token in ALLOWED_KI_TERMS or match.start() in mentions:
                continue
            line = text.count("\n", 0, match.start()) + 1
            hits.append(f"{rel(path)}:{line} verwendet '{token}'")
    assert not hits, (
        "Unerlaubte Verwendung von 'KI' gefunden. Regelbasiertes heisst "
        "'automatische Analyse':\n" + "\n".join(hits)
    )


def test_generated_explanations_are_marked_as_automatic():
    """Generated narrative must be labelled as machine-written."""
    app = require("app/index.html")
    assert "automatisch erstellt" in read(app), (
        "Kennzeichnung 'automatisch erstellt' fehlt im Cockpit"
    )


# --------------------------------------------------------------------------- #
# Rule 4: no secrets in the repository
# --------------------------------------------------------------------------- #

SECRET_PATTERNS = [
    ("Anthropic-Key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{10,}")),
    ("OpenAI-Key", re.compile(r"sk-[A-Za-z0-9]{32,}")),
    ("Google-Key", re.compile(r"AIza[A-Za-z0-9_\-]{30,}")),
    ("AWS-Key", re.compile(r"AKIA[A-Z0-9]{16}")),
    ("Bearer-Token", re.compile(r"Bearer\s+[A-Za-z0-9._\-]{20,}")),
    ("Zuweisung", re.compile(r"(?i)\b(api[_-]?key|secret|passwort|password|token)\b\s*[:=]\s*['\"][^'\"\s]{12,}['\"]")),
]


def test_no_api_keys_or_credentials():
    """Rule 4: no API keys are stored in code or repository."""
    hits: list[str] = []
    for path in iter_repo_files():
        text = read(path)
        for label, pattern in SECRET_PATTERNS:
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                hits.append(f"{rel(path)}:{line} sieht aus wie {label}")
    assert not hits, "Moegliche Zugangsdaten im Repository:\n" + "\n".join(hits)


# --------------------------------------------------------------------------- #
# Rule 3: the disclosure line
# --------------------------------------------------------------------------- #

NOTICE = "Demo mit fiktiven Daten · eigene Initiative · erstellt mit KI-Unterstützung"


def test_disclosure_line_in_tool_header():
    """Rule 3: visible notice in the tool header."""
    app = require("app/index.html")
    text = read(app)
    assert NOTICE in text, f"Hinweiszeile fehlt in app/index.html: {NOTICE!r}"
    # It must sit in the page header, not buried in a footer at the very end.
    position = text.index(NOTICE) / len(text)
    assert position < 0.5, "Hinweiszeile steht nicht im Kopfbereich der Seite"


def test_disclosure_line_on_case_study_page_one():
    """Rule 3: visible notice at the top of page 1 of the case study."""
    doc = require("case-study/case_study.html")
    text = read(doc)
    assert NOTICE in text, f"Hinweiszeile fehlt in case_study.html: {NOTICE!r}"
    position = text.index(NOTICE) / len(text)
    assert position < 0.5, "Hinweiszeile steht nicht auf Seite 1 der Case Study"


# --------------------------------------------------------------------------- #
# Technical constraints (PROMPT.md, section 5)
# --------------------------------------------------------------------------- #

ALLOWED_HOSTS = {
    "cdnjs.cloudflare.com",
    "fonts.googleapis.com",
    "fonts.gstatic.com",
}

URL_IN_MARKUP = re.compile(r"(?:src|href)\s*=\s*[\"'](https?://[^\"']+)[\"']", re.IGNORECASE)


def test_tool_uses_only_allowed_external_sources():
    """Only versioned cdnjs builds and Google Fonts are permitted."""
    app = require("app/index.html")
    hits = []
    for url in URL_IN_MARKUP.findall(read(app)):
        host = url.split("/")[2].lower()
        if host not in ALLOWED_HOSTS:
            hits.append(url)
    assert not hits, "Nicht erlaubte externe Quellen in app/index.html:\n" + "\n".join(hits)


def test_cdn_scripts_are_pinned_to_an_exact_version():
    """A floating CDN version would change the demo without notice."""
    app = require("app/index.html")
    for url in URL_IN_MARKUP.findall(read(app)):
        if "cdnjs.cloudflare.com" in url:
            assert re.search(r"/\d+\.\d+\.\d+/", url), f"CDN-Quelle ohne feste Version: {url}"


def test_tool_does_not_fetch_its_data_at_runtime():
    """The file is opened by double click; fetch() would fail under file://."""
    app = require("app/index.html")
    text = read(app)
    assert "cockpit-data" in text, "Eingebetteter Datenblock 'cockpit-data' fehlt"
    for forbidden in ("fetch(", "XMLHttpRequest"):
        assert forbidden not in text, f"{forbidden} macht das Tool per Doppelklick unbrauchbar"


def test_tool_does_not_depend_on_localstorage():
    """Rule: no localStorage for mandatory functionality."""
    app = require("app/index.html")
    assert "localStorage" not in read(app), (
        "localStorage darf fuer Pflichtfunktionen nicht verwendet werden"
    )


def test_tool_file_size_below_limit():
    app = require("app/index.html")
    size_mb = app.stat().st_size / 1024 / 1024
    assert size_mb < 1.5, f"app/index.html ist {size_mb:.2f} MB gross (Grenze 1,5 MB)"


# --------------------------------------------------------------------------- #
# Rule 5: one single source of truth
# --------------------------------------------------------------------------- #

# Digits are allowed inside markup that is not read as text: hex colours, CSS
# lengths, SVG geometry, viewBox values, and the placeholder syntax itself.
def _strip_non_text_markup(html: str) -> str:
    html = re.sub(r"<style\b.*?</style>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<script\b.*?</script>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    html = re.sub(r"<[^>]+>", " ", html)          # attributes carry geometry, not prose
    html = re.sub(r"\{\{[^}]+\}\}", " ", html)    # placeholders are filled at build time
    return html


def test_case_study_template_contains_no_hand_written_numbers():
    """Rule 5: every number in the case study comes from metrics.json."""
    template = require("case-study/template/case_study.template.html")
    prose = _strip_non_text_markup(read(template))
    digits = re.findall(r"\d[\d.,]*", prose)
    assert not digits, (
        "Das Template enthaelt handgeschriebene Zahlen -- sie gehoeren als "
        f"Platzhalter in metrics.json: {sorted(set(digits))}"
    )


def test_metrics_file_is_valid_and_non_empty():
    metrics = require("data/metrics.json")
    data = json.loads(read(metrics))
    assert isinstance(data, dict) and data, "metrics.json ist leer"


# --------------------------------------------------------------------------- #
# Case study output (PROMPT.md, section 4.5)
# --------------------------------------------------------------------------- #

PDF_RELATIVE = "case-study/Case_Study_Julian_Wueltner.pdf"


def _pdf_page_count(raw: bytes) -> int:
    counts = [int(value) for value in re.findall(rb"/Count\s+(\d+)", raw)]
    if counts:
        return max(counts)
    return len(re.findall(rb"/Type\s*/Page[^s]", raw))


def test_case_study_pdf_has_exactly_two_pages():
    pdf = require(PDF_RELATIVE)
    pages = _pdf_page_count(pdf.read_bytes())
    assert pages == 2, f"Die Case Study hat {pages} Seiten, gefordert sind genau 2"


def test_case_study_pdf_below_size_limit():
    pdf = require(PDF_RELATIVE)
    size_kb = pdf.stat().st_size / 1024
    assert size_kb < 700, f"Das PDF ist {size_kb:.0f} KB gross (Grenze 700 KB)"


# --------------------------------------------------------------------------- #
# Definition of Done: completeness
# --------------------------------------------------------------------------- #

DELIVERABLES = [
    "app/index.html",
    "data/generate_data.py",
    "data/dataset.json",
    "data/metrics.json",
    "data/analysis.py",
    "data/compute_metrics.py",
    "data/build_app.py",
    "case-study/template/case_study.template.html",
    "case-study/build_case_study.py",
    "case-study/case_study.html",
    PDF_RELATIVE,
    "docs/KPI_DEFINITIONS.md",
    "docs/DATA_ASSUMPTIONS.md",
    "README.md",
]


def test_deliverables_complete():
    """Fails until every deliverable of the project brief exists.

    This is the progress indicator of the project: it turns green in the last phase.
    """
    missing = [name for name in DELIVERABLES if not (ROOT / name).exists()]
    assert not missing, "Noch nicht vorhandene Ergebnisse:\n" + "\n".join(missing)
