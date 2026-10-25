"""One source of truth: tool, report and case study must show the same numbers.

Hard rule 5 of the project brief says every figure comes from the same generated
dataset and no figure is ever typed into a text by hand. These tests enforce it
from three directions:

1. the case study template resolves completely against ``metrics.json`` (A13)
2. every figure printed in the rendered case study is character-for-character the
   string stored in ``metrics.json`` -- no second rounding anywhere (A11, A12)
3. the headline figures in ``metrics.json`` really are what the raw dataset says,
   recomputed here independently of ``data/analysis.py``

Point 3 matters: a test that calls the same function it is testing proves nothing.
The aggregation below is written out on purpose, from the formulas in
``docs/KPI_DEFINITIONS.md``.
"""

from __future__ import annotations

import json
import re
import sys
from html import unescape
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data"))

TEMPLATE = ROOT / "case-study" / "template" / "case_study.template.html"
RENDERED = ROOT / "case-study" / "case_study.html"
METRICS = ROOT / "data" / "metrics.json"
DATASET = ROOT / "data" / "dataset.json"
APP = ROOT / "app" / "index.html"

PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}")

#: Placeholders filled at build time rather than from metrics.json (decision A13).
BUILD_TIME_PLACEHOLDERS = {"TOOL_URL"}


def load(path: Path) -> object:
    if not path.exists():
        pytest.skip(f"{path.relative_to(ROOT).as_posix()} existiert noch nicht")
    return json.loads(path.read_text(encoding="utf-8"))


def read(path: Path) -> str:
    if not path.exists():
        pytest.skip(f"{path.relative_to(ROOT).as_posix()} existiert noch nicht")
    return path.read_text(encoding="utf-8")


def table(dataset: dict, name: str) -> tuple[list[str], list[list]]:
    """Return columns and rows of one dataset table (row-array format, NFR-05)."""
    block = dataset.get(name)
    assert block, f"Tabelle '{name}' fehlt in dataset.json"
    return block["columns"], block["rows"]


def column_sum(dataset: dict, table_name: str, field: str) -> float:
    columns, rows = table(dataset, table_name)
    assert field in columns, f"Feld '{field}' fehlt in {table_name}: {columns}"
    index = columns.index(field)
    return sum(row[index] for row in rows)


# --------------------------------------------------------------------------- #
# 1. The template resolves completely
# --------------------------------------------------------------------------- #

def test_every_placeholder_has_a_value():
    """Decision A13: an unresolved placeholder must never reach an application."""
    template = read(TEMPLATE)
    metrics = load(METRICS)
    available = set(metrics.get("case_study", {})) | BUILD_TIME_PLACEHOLDERS

    used = set(PLACEHOLDER.findall(template))
    missing = sorted(used - available)
    assert not missing, (
        "Platzhalter ohne Wert in metrics.json['case_study']:\n" + "\n".join(missing)
    )


#: The figures the case study has to name, whatever else it says. Derived from
#: ``docs/SPEC.md`` section 4.5: page 1 shows the win-rate case and its follow-on
#: effect plus the two further fields of action, page 2 the recommendation with
#: its escalation trigger. A case study that leaves any of these out describes a
#: situation instead of making a case.
STORY_KEYS = [
    "fall_beginn_kw",
    "erfolgsquote_vorher",
    "erfolgsquote_nachher",
    "angebotszeit_vorher",
    "angebotszeit_nachher",
    "wirkung_fall_euro",
    "artikel_id",
    "artikel_quote",
    "wachstum_markt",
    "wachstum_wochen_ueber_engpass",
    "empfehlung_option",
    "eskalation_frist",
]


def test_the_case_study_names_the_figures_that_carry_the_argument():
    """Unused values are stock, not an error -- missing ones are.

    ``metrics.json`` deliberately offers more figures than any one version of the
    case study prints, so the text can be rewritten without asking for numbers
    again. What must not happen is the opposite: a case study that talks about a
    win-rate problem without naming what the rate fell from and to.
    """
    template = read(TEMPLATE)
    metrics = load(METRICS)
    available = set(metrics.get("case_study", {}))
    used = set(PLACEHOLDER.findall(template))

    unknown = sorted(key for key in STORY_KEYS if key not in available)
    assert not unknown, (
        "Diese Kennwerte erwartet der Test, aber metrics.json['case_study'] "
        "kennt sie nicht -- Schluesselnamen abgleichen:\n" + "\n".join(unknown)
    )

    missing = sorted(key for key in STORY_KEYS if key not in used)
    assert not missing, (
        "Die Case Study nennt diese tragenden Zahlen nicht:\n" + "\n".join(missing)
    )


def test_rendered_case_study_has_no_leftover_placeholder():
    rendered = read(RENDERED)
    leftovers = sorted(set(PLACEHOLDER.findall(rendered)))
    assert not leftovers, f"Unaufgeloeste Platzhalter im fertigen Dokument: {leftovers}"


# --------------------------------------------------------------------------- #
# 2. Printed figures equal the stored strings, character for character
# --------------------------------------------------------------------------- #

def test_case_study_prints_exactly_the_stored_strings():
    """Rule 5: the case study never rounds a number a second time."""
    rendered = read(RENDERED)
    metrics = load(METRICS)
    template = read(TEMPLATE)
    used = set(PLACEHOLDER.findall(template))

    missing = []
    for key, text in metrics.get("case_study", {}).items():
        if key not in used or not isinstance(text, str) or not text.strip():
            continue
        if text not in rendered:
            missing.append(f"{key}: erwartet {text!r}")
    assert not missing, (
        "Diese Werte aus metrics.json stehen nicht so im gerenderten Dokument:\n"
        + "\n".join(missing)
    )


def test_every_value_stands_where_the_template_puts_it():
    """Presence is not enough -- each figure has to sit in its own sentence.

    Checking only that a string occurs somewhere in the document lets two
    placeholders swap places without anyone noticing: the QA review exchanged
    the before and after value of the lead metric, rebuilt, and the case study
    then claimed the rate had fallen "von 84,6 % auf 95,2 %" while every check
    stayed green.

    This test therefore walks the template, takes the literal words immediately
    before each placeholder, and requires the matching value to follow them in
    the rendered document.
    """
    rendered = unescape(read(RENDERED))
    template = read(TEMPLATE)
    metrics = load(METRICS)
    values = dict(metrics.get("case_study", {}))

    wrong = []
    for match in PLACEHOLDER.finditer(template):
        key = match.group(1)
        expected = values.get(key)
        if key in BUILD_TIME_PLACEHOLDERS or not isinstance(expected, str) or not expected.strip():
            continue

        # The literal run right before the placeholder: text since the previous
        # placeholder ended, with markup removed, reduced to its last few words.
        head = template[: match.start()]
        head = head[head.rfind("}}") + 2:]
        context = re.sub(r"<[^>]+>", " ", head)
        context = unescape(re.sub(r"\s+", " ", context)).strip()
        context = " ".join(context.split()[-6:])
        if len(context) < 8:
            continue  # zu wenig Kontext, um eindeutig zu sein

        # Das schmale geschuetzte Leerzeichen zaehlt fuer \s als Leerraum. Beide
        # Seiten muessen deshalb gleich geglaettet werden, sonst findet der
        # Vergleich "9.200,46 €" nie im geglaetteten "9.200,46 €".
        flat = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", rendered))
        expected = re.sub(r"\s+", " ", expected)
        # Der Kontext kann mehrfach vorkommen (Legenden, Tabellenkoepfe). Es
        # genuegt, wenn an einer der Fundstellen der erwartete Wert folgt.
        stellen, suchstelle = [], flat.find(context)
        while suchstelle != -1:
            stellen.append(suchstelle)
            suchstelle = flat.find(context, suchstelle + 1)
        if not stellen:
            continue  # Kontext steht im Ergebnis anders da, etwa in einer Grafik

        treffer = False
        gesehen = []
        for stelle in stellen:
            ende = stelle + len(context)
            folgend = flat[ende: ende + len(expected) + 40]
            gesehen.append(folgend[:60])
            if expected in folgend:
                treffer = True
                break
        if not treffer:
            wrong.append(
                f"{key}: nach {context!r} erwartet {expected!r}, dort steht {gesehen[0]!r}"
            )

    assert not wrong, (
        "Diese Werte stehen nicht an der Stelle, an der die Vorlage sie setzt "
        "(Verdacht auf vertauschte Platzhalter):\n" + "\n".join(wrong)
    )


def test_stored_texts_are_the_formatting_of_their_values():
    """Decision A11 + A12: 'text' must be the formatted form of 'value', not a variant.

    How many decimals a metric shows is the metric's own business. Rule R5 in
    ``docs/KPI_DEFINITIONS.md`` asks for two on the complaint rates and one
    everywhere else (none on the contribution margin), so the entry carries
    ``decimals`` and this test uses it. An earlier version assumed a single
    decimal for every percentage, which put a rate of 0,49 % onto the tile as
    "0,5 %" beside a target of "0,5 %" -- the traffic light was then impossible
    to verify by reading, which is what ``test_a_tile_never_shows_its_value_as_
    its_own_target`` now rules out.
    """
    import formatting as fmt

    metrics = load(METRICS)

    def format_with(unit, value, decimals):
        if unit == "%":
            return fmt.percent(value, decimals)
        if unit == "Tage":
            return fmt.days(value, decimals)
        if unit == "Stunden":
            return fmt.number(value, decimals) + fmt.NNBSP + "Stunden"
        if unit == "€":
            return fmt.euro(value, decimals)
        return None

    mismatches = []
    for key, entry in metrics.get("kpis", {}).items():
        if not isinstance(entry, dict):
            continue
        value, text, unit = entry.get("value"), entry.get("text"), entry.get("unit")
        if not isinstance(value, (int, float)) or not isinstance(text, str):
            continue
        decimals = entry.get("decimals")
        if decimals is None:
            # Fall back to the precision the stored text itself uses, so the
            # rounding is still checked even before ``decimals`` exists.
            fraction = re.search(r",(\d+)", text)
            decimals = len(fraction.group(1)) if fraction else 0
        expected = format_with(unit, value, decimals)
        if expected is None:
            continue
        # Digits only: the unit spelling is the formatter's business, the number is ours.
        expected_digits = re.sub(r"[^\d,.\-]", "", expected)
        actual_digits = re.sub(r"[^\d,.\-]", "", text)
        if expected_digits != actual_digits:
            mismatches.append(f"{key}: text={text!r}, erwartet aus value={value}: {expected!r}")
    assert not mismatches, "Text und Rohwert passen nicht zusammen:\n" + "\n".join(mismatches)


def test_a_tile_never_shows_its_value_as_its_own_target():
    """The displayed precision must be fine enough to verify the traffic light.

    A rate of 0.4904 % printed as "0,5 %" next to a target printed as
    "0,5 %" is worse than useless: the tile is green and the reader cannot see
    why. Whenever the light takes a clear side, the two texts have to differ.
    """
    metrics = load(METRICS)
    offenders = []
    for key, entry in metrics.get("kpis", {}).items():
        if not isinstance(entry, dict) or entry.get("status") not in ("green", "red"):
            continue
        value, target = entry.get("value"), entry.get("target")
        text, target_text = entry.get("text"), entry.get("target_text")
        if not all(isinstance(x, (int, float)) for x in (value, target)):
            continue
        if value == target or not isinstance(text, str) or not isinstance(target_text, str):
            continue
        if text == target_text:
            offenders.append(
                f"{key}: Ist {text!r} und Ziel {target_text!r} sehen gleich aus "
                f"(Werte {value} gegen {target}) -- mehr Nachkommastellen noetig"
            )
    assert not offenders, "Ampel nicht ablesbar:\n" + "\n".join(offenders)


def test_app_and_case_study_use_the_same_metrics():
    """The tool must not be built from an older metrics file than the case study."""
    html = read(APP)
    metrics = load(METRICS)
    match = re.search(
        r'<script[^>]*id=["\']cockpit-data["\'][^>]*>([\s\S]*?)</script>', html, re.IGNORECASE
    )
    assert match, 'Datenblock <script id="cockpit-data"> fehlt in app/index.html'
    embedded = json.loads(match.group(1))
    assert embedded.get("metrics") == metrics, (
        "Die in app/index.html eingebetteten Kennzahlen weichen von data/metrics.json ab. "
        "Bitte 'python data/build_app.py' ausfuehren."
    )


# --------------------------------------------------------------------------- #
# 3. The stored metrics really are what the raw data says
# --------------------------------------------------------------------------- #

def kpi_value(metrics: dict, key: str) -> float:
    entry = metrics.get("kpis", {}).get(key)
    assert entry is not None, f"Kennzahl '{key}' fehlt in metrics.json"
    return entry["value"] if isinstance(entry, dict) else entry


@pytest.mark.parametrize(
    ("key", "numerator", "denominator", "factor"),
    [
        ("quote_win_rate", ["quotes_won"], ["quotes_decided"], 1),
        ("otif_rate", ["orders_otif"], ["orders_delivered"], 1),
        ("complaint_rate_lines", ["lines_complained"], ["lines_shipped"], 1),
        ("contribution_margin_per_order_eur", ["contribution_margin_eur"], ["orders_shipped"], 1),
        ("delivery_inquiries_per_100_orders", ["delivery_inquiries"], ["orders_placed"], 100),
        ("revenue_index", ["revenue_eur"], ["revenue_prior_year_eur"], 100),
        ("partner_activity_rate", ["key_accounts_active"], ["key_accounts_assigned"], 1),
        ("quote_lead_time_h", ["stage1_inquiry_to_quote_hours"], ["quotes_sent"], 1),
        (
            "order_lead_time_d",
            ["stage3_order_entry_hours", "stage4_production_shipping_hours"],
            ["orders_shipped"],
            1 / 24,
        ),
    ],
)
def test_headline_kpis_recomputed_from_the_raw_dataset(key, numerator, denominator, factor):
    """Independent recomputation: quotient of sums, exactly as KPI_DEFINITIONS says."""
    dataset = load(DATASET)
    metrics = load(METRICS)

    top = sum(column_sum(dataset, "facts_weekly", field) for field in numerator)
    bottom = sum(column_sum(dataset, "facts_weekly", field) for field in denominator)
    assert bottom > 0, f"Nenner von '{key}' ist null"

    expected = top / bottom * factor
    actual = kpi_value(metrics, key)
    assert actual == pytest.approx(expected, rel=1e-9), (
        f"'{key}': metrics.json sagt {actual}, aus dataset.json folgt {expected}"
    )


def test_subsets_add_up_to_the_whole():
    """Aggregation fidelity: the declared markets must sum to the total.

    An earlier version of this test derived the list of markets from the same
    rows it then summed. That made it a tautology -- any partition of a set by
    its own values adds up, so the test stayed green even when a row carried a
    market the rest of the project had never heard of. The QA review proved it
    by setting one row's market to "XX": seventeen checks, all green.

    The list now comes from ``metrics.json``, which is what the cockpit offers
    as filter values. A row outside it would be invisible in every filtered view
    of the tool, and that is exactly what this test has to catch.
    """
    dataset = load(DATASET)
    metrics = load(METRICS)
    columns, rows = table(dataset, "facts_weekly")
    market_index = columns.index("market")

    declared = metrics.get("dimensions", {}).get("markets")
    assert declared, "metrics.json nennt keine Maerkte unter 'dimensions'"

    present = sorted({row[market_index] for row in rows})
    unknown = sorted(set(present) - set(declared))
    assert not unknown, (
        f"Der Datensatz enthaelt Maerkte, die metrics.json nicht kennt: {unknown}. "
        "Zeilen mit solchen Werten waeren in jeder gefilterten Ansicht unsichtbar."
    )

    numeric_fields = [
        (name, index)
        for index, name in enumerate(columns)
        if index != market_index and rows and isinstance(rows[0][index], (int, float))
    ]

    for name, index in numeric_fields:
        total = sum(row[index] for row in rows)
        per_market = sum(
            sum(row[index] for row in rows if row[market_index] == market)
            for market in declared
        )
        assert per_market == pytest.approx(total, rel=1e-12, abs=1e-9), (
            f"Feld '{name}': Summe ueber die in metrics.json genannten Maerkte "
            f"({per_market}) weicht vom Gesamtwert ({total}) ab"
        )


def test_process_stages_add_up_to_the_lead_time():
    """AK-03.4: stage 3 + 4 must equal the order lead time (order to shipping)."""
    metrics = load(METRICS)
    stages = ["stage3_order_entry_h", "stage4_production_shipping_h"]
    if any(stage not in metrics.get("kpis", {}) for stage in stages):
        pytest.skip("Stufenkennzahlen noch nicht in metrics.json")

    total = sum(kpi_value(metrics, stage) for stage in stages)
    lead_time = kpi_value(metrics, "order_lead_time_d") * 24
    assert total == pytest.approx(lead_time, abs=0.1), (
        f"Summe der Stufen 3 und 4 ({total:.2f} h) weicht von der Auftragsdurchlaufzeit "
        f"({lead_time:.2f} h) ab -- Toleranz 0,1 h"
    )


# --------------------------------------------------------------------------- #
# 4. Not only figures are statements about the data
# --------------------------------------------------------------------------- #

#: The nine departments of the catalogue (docs/KPI_DEFINITIONS.md, rule R6).
DEPARTMENTS = {
    "Vertrieb",
    "Vertriebsinnendienst",
    "Auftragsabwicklung",
    "Logistik",
    "Qualität",
    "Kundenservice",
    "Controlling",
    "Partnermanagement",
    "externer Partner",
}

#: Organisational units that sound plausible in a German sales report but are
#: not in the catalogue. They are the failure mode this test exists for: an
#: invented responsible unit reads as authoritative and is impossible to defend
#: when someone asks which definition it comes from.
INVENTED_UNITS = [
    "Qualitätssicherung",
    "Qualitaetssicherung",
    "Einkauf",
    "Supply Chain",
    "Key Account Management",
    "Marketing",
    "Personalabteilung",
    "Geschäftsführung",
    "Produktmanagement",
    "Disposition",
    "Kundendienst",
    "Exportabteilung",
]


def test_the_case_study_names_no_department_outside_the_catalogue():
    """Rule R6: a metric has exactly one responsible unit, from a fixed list.

    The digit-free template rule catches invented numbers. It does not catch an
    invented *word* -- and "Qualitätssicherung Vertrieb" in a responsibility
    column is exactly as unfounded as a made-up figure, only harder to spot.
    """
    rendered = unescape(read(RENDERED))
    hits = [unit for unit in INVENTED_UNITS if unit in rendered]
    assert not hits, (
        "Diese Bezeichnungen stehen in der Case Study, aber in keinem "
        f"Fachbereichskatalog: {hits}. Erlaubt sind: {sorted(DEPARTMENTS)}"
    )


def test_every_department_in_the_case_study_comes_from_the_metrics():
    """Whatever responsibility the document assigns must be backed by the data."""
    # Departments may carry an ampersand or umlaut entity in the markup --
    # compare against the text a reader sees, not the markup.
    rendered = unescape(read(RENDERED))
    metrics = load(METRICS)

    known = {
        entry.get("department")
        for entry in list(metrics.get("findings", []))
        + list(metrics.get("kpis", {}).values())
        if isinstance(entry, dict) and entry.get("department")
    }
    assert known, "metrics.json weist keinem Eintrag einen Fachbereich zu"
    assert known <= DEPARTMENTS, (
        f"metrics.json nennt Fachbereiche ausserhalb des Katalogs: {sorted(known - DEPARTMENTS)}"
    )

    # Every department the finding list assigns has to be readable in the document,
    # otherwise the case study hides who has to act.
    responsible = {
        finding["department"]
        for finding in metrics.get("findings", [])
        if finding.get("status") != "behoben"
    }
    missing = sorted(unit for unit in responsible if unit not in rendered)
    assert not missing, (
        "Die Case Study nennt diese zustaendigen Fachbereiche nicht:\n" + "\n".join(missing)
    )


#: Richtungswörter und was sie über zwei benachbarte Zahlen aussagen.
DIRECTION_WORDS = [
    ("gefallen", "kleiner"), ("gesunken", "kleiner"), ("zurückgegangen", "kleiner"),
    ("gestiegen", "groesser"), ("zugenommen", "groesser"), ("angestiegen", "groesser"),
]

VON_AUF = re.compile(
    r"von\s+(-?[\d.]+,?\d*)\s*(?:%| %)?\s*[^.;]{0,40}?auf\s+(-?[\d.]+,?\d*)\s*(?:%| %)?"
    r"[^.;]{0,60}?\b(" + "|".join(word for word, _ in DIRECTION_WORDS) + r")\b"
)


def _zahl(text: str) -> float:
    return float(text.replace(".", "").replace(",", "."))


def test_the_sentences_agree_with_their_own_numbers():
    """A sentence that says "fallen" must name a smaller second number.

    This is the one class of error that comparing the template against the data
    cannot reach: swap two placeholders and template and document stay perfectly
    consistent with each other -- only the German stops being true. The QA review
    demonstrated it, producing "von 84,6 % auf 95,2 % gefallen", with every other
    check green.

    So this test reads the finished document the way a person does: it looks for
    "von A auf B <Richtungswort>" and checks that A and B stand in the relation
    the word claims.
    """
    rendered = unescape(read(RENDERED))
    flat = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", rendered))
    richtung = dict(DIRECTION_WORDS)

    widersprueche = []
    for match in VON_AUF.finditer(flat):
        von, auf, wort = _zahl(match.group(1)), _zahl(match.group(2)), match.group(3)
        erwartet = richtung[wort]
        stimmt = auf < von if erwartet == "kleiner" else auf > von
        if not stimmt:
            widersprueche.append(
                f"„{match.group(0)[:90]}" + ("..." if len(match.group(0)) > 90 else "") + "“ "
                f"— {wort} verlangt einen {erwartet}en zweiten Wert, "
                f"hier steht {match.group(1)} und dann {match.group(2)}"
            )

    assert not widersprueche, (
        "Der Text widerspricht seinen eigenen Zahlen:\n" + "\n".join(widersprueche)
    )
