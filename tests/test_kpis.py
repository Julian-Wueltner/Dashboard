"""Kennzahlenformeln, Aggregationstreue und Randfälle.

Diese Tests rechnen die Formeln aus ``docs/KPI_DEFINITIONS.md`` **von Hand** nach --
mit einem eigenen, winzigen Aggregator, der nichts aus ``data/analysis.py`` benutzt.
Ein Test, der die Funktion aufruft, die er prüfen soll, beweist nichts.

Geprüft werden:

* Rechenregel R1 -- jede Kennzahl ist ein Quotient aus Summen, nie ein Mittel
  über gespeicherte Quoten
* Aggregationstreue -- die Summe über die Teilmengen ist die Gesamtmenge
* Randfälle -- Division durch null, leere Filtermenge, Woche ohne Daten
* AK-03.4 -- Stufe 3 + Stufe 4 ergibt die Auftragsdurchlaufzeit
* Festlegung F4 -- ``orders_sample`` speist keine Kennzahl
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data"))

import analysis as an  # noqa: E402
import compute_metrics as cm  # noqa: E402
import formatting as fmt  # noqa: E402

DATASET = ROOT / "data" / "dataset.json"
METRICS = ROOT / "data" / "metrics.json"


# --------------------------------------------------------------------------- #
# Ein unabhängiger Mini-Aggregator -- absichtlich ohne data/analysis.py
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def raw() -> dict:
    if not DATASET.exists():
        pytest.skip("data/dataset.json existiert noch nicht")
    return json.loads(DATASET.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def metrics() -> dict:
    if not METRICS.exists():
        pytest.skip("data/metrics.json existiert noch nicht")
    return json.loads(METRICS.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def dataset() -> an.Dataset:
    if not DATASET.exists():
        pytest.skip("data/dataset.json existiert noch nicht")
    return an.load_dataset(DATASET)


def hand_sum(raw: dict, table: str, field: str, where: dict | None = None) -> float:
    """Summe eines Felds -- die einfachste denkbare Implementierung."""
    block = raw[table]
    index = {name: position for position, name in enumerate(block["columns"])}
    total = 0.0
    for row in block["rows"]:
        if where and any(row[index[key]] != value for key, value in where.items()):
            continue
        total += row[index[field]]
    return total


def hand_ratio(raw: dict, table: str, numerator: list[str], denominator: list[str],
               factor: float = 1.0, minus: list[str] | None = None,
               where: dict | None = None) -> float:
    top = sum(hand_sum(raw, table, field, where) for field in numerator)
    if minus:
        top -= sum(hand_sum(raw, table, field, where) for field in minus)
    bottom = sum(hand_sum(raw, table, field, where) for field in denominator)
    return top / bottom * factor


# --------------------------------------------------------------------------- #
# 1. Die zehn Pflichtkennzahlen gegen die Formel des Katalogs
# --------------------------------------------------------------------------- #

FORMULAS = [
    ("quote_lead_time_h", "facts_weekly",
     ["stage1_inquiry_to_quote_hours"], ["quotes_sent"], 1.0, None),
    ("quote_win_rate", "facts_weekly", ["quotes_won"], ["quotes_decided"], 1.0, None),
    ("order_lead_time_d", "facts_weekly",
     ["stage3_order_entry_hours", "stage4_production_shipping_hours"],
     ["orders_shipped"], 1 / 24, None),
    ("otif_rate", "facts_weekly", ["orders_otif"], ["orders_delivered"], 1.0, None),
    ("complaint_rate_lines", "facts_weekly",
     ["lines_complained"], ["lines_shipped"], 1.0, None),
    ("complaint_processing_time_d", "facts_weekly",
     ["stage5_complaint_hours"], ["complaints_closed"], 1 / 24, None),
    ("delivery_inquiries_per_100_orders", "facts_weekly",
     ["delivery_inquiries"], ["orders_placed"], 100.0, None),
    ("contribution_margin_per_order_eur", "facts_weekly",
     ["contribution_margin_eur"], ["orders_shipped"], 1.0, None),
    ("revenue_index", "facts_weekly",
     ["revenue_eur"], ["revenue_prior_year_eur"], 100.0, None),
    ("partner_activity_rate", "facts_weekly",
     ["key_accounts_active"], ["key_accounts_assigned"], 1.0, None),
    ("complaint_rate_items", "assortment_periods",
     ["lines_complained"], ["lines_shipped"], 1.0, None),
    ("stage1_inquiry_to_quote_h", "facts_weekly",
     ["stage1_inquiry_to_quote_hours"], ["quotes_sent"], 1.0, None),
    ("stage2_quote_to_order_h", "facts_weekly",
     ["stage2_quote_to_order_hours"], ["quotes_won"], 1.0, None),
    ("stage3_order_entry_h", "facts_weekly",
     ["stage3_order_entry_hours"], ["orders_shipped"], 1.0, None),
    ("stage4_production_shipping_h", "facts_weekly",
     ["stage4_production_shipping_hours"], ["orders_shipped"], 1.0, None),
    ("stage5_complaint_h", "facts_weekly",
     ["stage5_complaint_hours"], ["complaints_closed"], 1.0, None),
]


@pytest.mark.parametrize(("key", "table", "numerator", "denominator", "factor", "minus"),
                         FORMULAS, ids=[entry[0] for entry in FORMULAS])
def test_kpi_matches_the_hand_written_formula(raw, metrics, key, table, numerator,
                                              denominator, factor, minus):
    expected = hand_ratio(raw, table, numerator, denominator, factor, minus)
    stored = metrics["kpis"][key]["value"]
    assert stored == pytest.approx(expected, rel=1e-9), (
        f"'{key}': metrics.json sagt {stored}, die Formel des Katalogs ergibt {expected}")


def test_every_catalogue_kpi_is_in_the_metrics_file(metrics):
    """Der Kennzahlenkatalog hat 16 Einträge; keiner darf fehlen."""
    missing = sorted(set(an.KPIS) - set(metrics["kpis"]))
    assert not missing, f"Kennzahlen fehlen in metrics.json: {missing}"
    extra = sorted(set(metrics["kpis"]) - set(an.KPIS))
    assert not extra, f"Kennzahlen ohne Eintrag im Katalog: {extra}"


def test_targets_and_directions_match_the_catalogue(metrics):
    for key, kpi in an.KPIS.items():
        entry = metrics["kpis"][key]
        assert entry["target"] == pytest.approx(kpi.target), key
        assert entry["warning"] == pytest.approx(kpi.warning), key
        assert entry["direction"] == kpi.direction, key
        assert entry["department"] == kpi.department, key


def test_texts_come_from_the_formatting_module(metrics):
    """Entscheidung A11: keine Zeichenkette entsteht per f-string in der Analyse."""
    for key, kpi in an.KPIS.items():
        entry = metrics["kpis"][key]
        assert entry["text"] == kpi.text(entry["value"]), key
        assert entry["target_text"] == kpi.text(kpi.target), key
        assert entry["warning_text"] == kpi.text(kpi.warning), key


# --------------------------------------------------------------------------- #
# 2. Aggregationstreue: die Summe der Teilmengen ist die Gesamtmenge
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("dimension", ["market", "channel", "partner"])
def test_numerator_and_denominator_add_up_over_a_dimension(raw, dataset, dimension):
    """Rechenregel R1: Zähler und Nenner sind additiv, die Quote ist es nicht."""
    block = raw["facts_weekly"]
    index = {name: position for position, name in enumerate(block["columns"])}
    values = sorted({row[index[dimension]] for row in block["rows"]})
    assert len(values) >= 2

    for kpi in an.KPIS.values():
        if kpi.table != "facts_weekly":
            continue
        total_numerator = sum(hand_sum(raw, "facts_weekly", field) for field in kpi.numerator)
        total_denominator = sum(hand_sum(raw, "facts_weekly", field)
                                for field in kpi.denominator)
        part_numerator = sum(
            sum(hand_sum(raw, "facts_weekly", field, {dimension: value})
                for field in kpi.numerator) for value in values)
        part_denominator = sum(
            sum(hand_sum(raw, "facts_weekly", field, {dimension: value})
                for field in kpi.denominator) for value in values)
        assert part_numerator == pytest.approx(total_numerator, rel=1e-9), kpi.key
        assert part_denominator == pytest.approx(total_denominator, rel=1e-9), kpi.key


def test_a_weighted_mean_of_stored_ratios_would_be_wrong(dataset):
    """Warum R1 so streng ist: der naive Mittelwert weicht messbar ab.

    Dieser Test hält fest, dass "über Quoten mitteln" und "Summen dividieren"
    nicht dasselbe Ergebnis liefern. Wäre der Unterschied null, wäre die ganze
    Regel folgenlos -- und niemand würde sie im Gespräch ernst nehmen.
    """
    kpi = an.KPIS["otif_rate"]
    correct, _ = an.kpi_value(dataset, kpi)
    weekly = an.series_of(dataset, kpi)
    naive = sum(point["value"] for point in weekly) / len(weekly)
    assert correct != pytest.approx(naive, abs=1e-9)


def test_breakdown_entries_use_the_same_formula_as_the_total(dataset, metrics):
    """Eine Aufteilung muss dieselbe Formel benutzen wie die Gesamtkennzahl."""
    kpi = an.KPIS["otif_rate"]
    for market, entry in metrics["breakdowns"]["otif_rate"]["by_market"].items():
        value, _ = an.kpi_value(dataset, kpi, {"market": {market}})
        assert entry["value"] == pytest.approx(value, rel=1e-9), market


# --------------------------------------------------------------------------- #
# 3. Randfälle
# --------------------------------------------------------------------------- #

def test_empty_selection_returns_no_value_instead_of_an_exception(dataset):
    """Leere Filtermenge: keine Ausnahme, kein Wert, graue Ampel."""
    kpi = an.KPIS["otif_rate"]
    value, denominator = an.kpi_value(dataset, kpi, {"market": {"XX"}})
    assert value is None
    assert denominator == 0
    assert an.traffic_light(kpi, value, denominator, dataset.min_denominator) == "grey"


def test_division_by_zero_returns_none(dataset):
    kpi = an.KPIS["otif_rate"]
    assert kpi.compute(0.0, 0.0) is None
    assert kpi.compute(17.0, 0.0) is None
    assert kpi.compute(0.0, 5.0) == 0.0


def test_week_without_data_is_not_scored(dataset):
    """Eine Woche ohne Zeilen taucht nicht mit einem erfundenen Wert auf."""
    kpi = an.KPIS["otif_rate"]
    value, denominator = an.window_value(dataset, kpi, 99, 99)
    assert value is None and denominator == 0


def test_below_minimum_sample_the_light_stays_grey(dataset):
    """Festlegung F2: unter der Mindeststichprobe gibt es keinen Zahlenwert."""
    kpi = an.KPIS["otif_rate"]
    below = dataset.min_denominator - 1
    assert an.traffic_light(kpi, 0.99, below, dataset.min_denominator) == "grey"
    assert an.traffic_light(kpi, 0.99, dataset.min_denominator,
                            dataset.min_denominator) == "green"


def test_traffic_light_covers_all_four_states(dataset):
    """F1: grün, gelb, rot, grau -- und die Richtung entscheidet, wo grün liegt."""
    higher = an.KPIS["otif_rate"]      # höher ist besser
    lower = an.KPIS["complaint_rate_lines"]        # niedriger ist besser
    minimum = dataset.min_denominator
    assert an.traffic_light(higher, 0.96, 1000, minimum) == "green"
    assert an.traffic_light(higher, 0.94, 1000, minimum) == "yellow"
    assert an.traffic_light(higher, 0.90, 1000, minimum) == "red"
    assert an.traffic_light(higher, None, 1000, minimum) == "grey"
    assert an.traffic_light(lower, 0.010, 1000, minimum) == "green"
    assert an.traffic_light(lower, 0.013, 1000, minimum) == "yellow"
    assert an.traffic_light(lower, 0.018, 1000, minimum) == "red"


def test_trend_reports_no_comparison_when_the_data_is_too_short(dataset):
    kpi = an.KPIS["otif_rate"]
    short = [{"week": week, "value": 0.95} for week in range(1, 5)]
    assert an.trend(kpi, short)["label"] == "kein Vergleich möglich"


def test_trend_is_direction_aware(dataset):
    """F3: dieselbe Zahlenbewegung heißt je nach Richtung 'besser' oder 'schlechter'."""
    rising = ([{"week": week, "value": 0.90} for week in range(1, 5)]
              + [{"week": week, "value": 0.96} for week in range(5, 9)])
    assert an.trend(an.KPIS["otif_rate"], rising)["label"] == "besser"
    assert an.trend(an.KPIS["complaint_rate_lines"], rising)["label"] == "schlechter"


# --------------------------------------------------------------------------- #
# 4. AK-03.4: der Vertriebsprozess ist widerspruchsfrei zu den Kennzahlen
# --------------------------------------------------------------------------- #

def test_stages_three_and_four_add_up_to_the_order_lead_time(metrics):
    stages = ["stage3_order_entry_h", "stage4_production_shipping_h"]
    total = sum(metrics["kpis"][stage]["value"] for stage in stages)
    assert total == pytest.approx(metrics["kpis"]["order_lead_time_d"]["value"] * 24,
                                  rel=1e-9)


def test_stage_targets_add_up_to_the_order_lead_time_target():
    """OP-9: auch die Zielwerte und Warnschwellen müssen sich summieren."""
    stages = ["stage3_order_entry_h", "stage4_production_shipping_h"]
    assert sum(an.KPIS[stage].target for stage in stages) == pytest.approx(
        an.KPIS["order_lead_time_d"].target * 24)
    assert sum(an.KPIS[stage].warning for stage in stages) == pytest.approx(
        an.KPIS["order_lead_time_d"].warning * 24)


def test_stage_one_is_the_quote_lead_time(metrics):
    assert metrics["kpis"]["stage1_inquiry_to_quote_h"]["value"] == pytest.approx(
        metrics["kpis"]["quote_lead_time_h"]["value"], rel=1e-9)
    assert an.KPIS["stage1_inquiry_to_quote_h"].target == an.KPIS["quote_lead_time_h"].target


def test_stage_five_is_the_complaint_processing_time_in_hours(metrics):
    assert metrics["kpis"]["stage5_complaint_h"]["value"] == pytest.approx(
        metrics["kpis"]["complaint_processing_time_d"]["value"] * 24, rel=1e-9)


# --------------------------------------------------------------------------- #
# 5. Festlegung F4: die Auftragsstichprobe speist keine Kennzahl
# --------------------------------------------------------------------------- #

def test_the_order_sample_appears_in_no_executable_line():
    """F4: Die Auftragsstichprobe darf nur im Kommentar vorkommen, nie im Code.

    Geprüft wird der Syntaxbaum, nicht der Rohtext: Jede Zeichenkette und jeder
    Name im ausführbaren Teil der beiden Module wird angesehen. Docstrings sind
    ausgenommen -- dort steht ausdrücklich, warum die Tabelle nicht benutzt wird.
    """
    import ast

    for name in ("analysis.py", "compute_metrics.py"):
        tree = ast.parse((ROOT / "data" / name).read_text(encoding="utf-8"))
        docstrings = {
            ast.get_docstring(node, clean=False)
            for node in ast.walk(tree)
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef))
        }
        assert docstrings, name
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value in docstrings:
                    continue
                assert "orders_sample" not in node.value, (
                    f"{name}: 'orders_sample' steht im ausführbaren Code (F4)")
            elif isinstance(node, ast.Name):
                assert "orders_sample" not in node.id, name


def test_analysis_never_reads_the_order_sample(dataset):
    """Härter als eine Quelltextprüfung: der Block wird gar nicht geladen."""
    assert not hasattr(dataset, "orders")
    assert "orders_sample" not in {table.name for table in
                                   (dataset.facts, dataset.assortment,
                                    dataset.capacity, dataset.articles)}


# --------------------------------------------------------------------------- #
# 6. Beide Tabellen müssen dieselbe Reklamationsmenge zeigen
# --------------------------------------------------------------------------- #

def test_assortment_and_facts_agree_on_lines_and_complaints(raw, dataset):
    """Kennzahlenkatalog 7.2: je Periode dieselbe Summe in beiden Tabellen."""
    facts = raw["facts_weekly"]
    facts_index = {name: position for position, name in enumerate(facts["columns"])}
    assortment = raw["assortment_periods"]
    assortment_index = {name: position
                        for position, name in enumerate(assortment["columns"])}

    for field in ("lines_shipped", "lines_complained"):
        by_period_facts: dict[int, float] = {}
        for row in facts["rows"]:
            period = dataset.period_of_week(row[facts_index["week"]])
            by_period_facts[period] = by_period_facts.get(period, 0.0) + row[facts_index[field]]
        by_period_assortment: dict[int, float] = {}
        for row in assortment["rows"]:
            period = row[assortment_index["period"]]
            by_period_assortment[period] = (by_period_assortment.get(period, 0.0)
                                            + row[assortment_index[field]])
        assert by_period_facts == pytest.approx(by_period_assortment), field


# --------------------------------------------------------------------------- #
# 7. Filtermatrix und Vertrag A12
# --------------------------------------------------------------------------- #

def test_metrics_file_has_every_block_of_the_contract(metrics):
    for block in ("meta", "dimensions", "kpis", "breakdowns", "findings", "measures",
                  "scenario", "decision_paper", "report", "case_study"):
        assert block in metrics, f"Block '{block}' fehlt (Vertrag A12)"


def test_every_kpi_entry_has_the_contracted_fields(metrics):
    required = {"value", "text", "unit", "target", "target_text", "warning",
                "direction", "department", "status", "trend", "series"}
    for key, entry in metrics["kpis"].items():
        missing = sorted(required - set(entry))
        assert not missing, f"'{key}': Felder fehlen: {missing}"
        assert set(entry["trend"]) >= {"delta", "text", "label"}, key
        assert entry["series"], key


def test_no_breakdown_on_a_level_the_filter_matrix_forbids(metrics):
    """Abschnitt 6 des Katalogs: lieber 'nicht auswertbar' als eine falsche Zahl."""
    for key, block in metrics["breakdowns"].items():
        allowed = cm.EVALUABLE[key]
        for name, level in cm.BREAKDOWN_LEVELS:
            if name in block:
                assert level in allowed, f"'{key}' darf nicht nach {level} aufgeteilt werden"


def test_capacity_is_planned_for_every_sales_partner(dataset, metrics):
    """Jeder Vertriebspartner hat eine Angebotskapazität; das Szenario rechnet für alle."""
    planned = set(dataset.capacity.distinct("partner"))
    assert planned == set(metrics["dimensions"]["partners"])
    assert set(metrics["scenario"]["base_case"]["per_partner"]) == planned


def test_scenario_reference_cases_cover_the_required_grid(metrics):
    cases = metrics["scenario"]["reference_cases"]
    for volume in (0.0, 0.20, 0.40):
        for expansion in (False, True):
            matching = [case for case in cases
                        if case["volume_increase"] == pytest.approx(volume)
                        and case["expansion"] is expansion]
            assert matching, f"Stützstelle fehlt: {volume}, Erweiterung {expansion}"


def test_scenario_at_zero_growth_equals_the_measured_utilization(raw, dataset, metrics):
    """AK-14.4: bei 0 % Mehrvolumen zeigt das Modell die Istauslastung."""
    base = an.scenario(dataset, 0.0, False)
    for partner, block in base["per_partner"].items():
        measured = (hand_sum(raw, "capacity_weekly", "quotes_processed", {"partner": partner})
                    / hand_sum(raw, "capacity_weekly", "capacity_quotes_contracted",
                               {"partner": partner}))
        modelled = (sum(point["units"] for point in block["weeks"])
                    / sum(point["capacity"] for point in block["weeks"]))
        assert modelled == pytest.approx(measured, rel=1e-6), partner


def test_scenario_expansion_never_increases_the_bottlenecks(dataset):
    """Eine eigene Tochtergesellschaft darf das Ergebnis der Partner nicht verschlechtern."""
    for volume in an.SCENARIO_VOLUME_STEPS:
        without = an.scenario(dataset, volume, False)
        with_expansion = an.scenario(dataset, volume, True, 1)
        for partner in without["per_partner"]:
            assert (with_expansion["per_partner"][partner]["bottleneck_week_count"]
                    <= without["per_partner"][partner]["bottleneck_week_count"]), (
                f"{partner} bei {volume}")


def test_decision_matrix_is_three_by_four_with_short_reasons(metrics):
    """AK-17.3 und OP-17: zwölf Felder, jedes mit Einstufung und kurzem Satz."""
    evaluation = metrics["decision_paper"]["evaluation"]
    assert len(evaluation["rows"]) == 3
    for row in evaluation["rows"]:
        assert len(row["cells"]) == 4, row["option"]
        for key, cell in row["cells"].items():
            assert cell["rating"] in {"gering", "mittel", "hoch"}, (row["option"], key)
            assert cell["reason"].strip(), (row["option"], key)
            assert len(cell["reason"]) <= cm.MATRIX_REASON_LIMIT, (
                f"{row['option']}/{key}: {len(cell['reason'])} Zeichen")


def test_decision_paper_has_the_seven_sections(metrics):
    for section in ("head", "situation", "options", "evaluation", "recommendation",
                    "escalation_trigger", "next_steps"):
        assert section in metrics["decision_paper"], section
    assert len(metrics["decision_paper"]["options"]) == 3
    assert len(metrics["decision_paper"]["situation"]["sentences"]) == 3
    assert 3 <= len(metrics["decision_paper"]["next_steps"]) <= 5
    for step in metrics["decision_paper"]["next_steps"]:
        assert step["owner"] and step["due_week_text"]


def test_report_has_the_six_sections(metrics):
    for section in ("header", "situation", "kpi_table", "top_actions",
                    "measures_status", "recommendation"):
        assert section in metrics["report"], section
    assert len(metrics["report"]["situation"]["sentences"]) == 3


def test_efficiency_estimate_uses_the_documented_parameters(dataset, metrics):
    """AK-10.2 und AK-10.4: Menge × Minuten ÷ 60, Parameter aus dem Datensatz."""
    block = metrics["efficiency"]
    assert len(block["positions"]) == 2
    for position in block["positions"]:
        expected = position["quantity_per_week"] * position["minutes_per_case"] / 60.0
        assert position["hours_per_week"] == pytest.approx(expected, rel=1e-6)
    assert block["positions"][0]["minutes_per_case"] == dataset.parameters[
        "minutes_per_delivery_inquiry"]
    assert block["positions"][1]["minutes_per_case"] == dataset.parameters[
        "minutes_per_complaint"]


def test_completed_measure_compares_two_separated_windows(dataset, metrics):
    """Entscheidung DE-4: Störungsfenster gegen den Zeitraum danach, nie das Jahresmittel."""
    evaluation = metrics["measures"][1]["evaluation"]
    before = evaluation["before_window"]
    after = evaluation["after_window"]
    assert after["week_from"] == before["week_to"] + 1
    assert after["week_to"] == dataset.weeks[-1]

    kpi = an.KPIS["otif_rate"]
    filters = {"market": {"PL"}}
    expected_before, _ = an.window_value(dataset, kpi, before["week_from"],
                                         before["week_to"], filters)
    expected_after, _ = an.window_value(dataset, kpi, after["week_from"],
                                        after["week_to"], filters)
    assert evaluation["before_value"] == pytest.approx(expected_before, rel=1e-9)
    assert evaluation["after_value"] == pytest.approx(expected_after, rel=1e-9)
    assert evaluation["after_value"] > kpi.target > evaluation["before_value"]
    assert evaluation["after_text"] == fmt.percent(expected_after, 1)
    assert evaluation["year_value"] < evaluation["after_value"], (
        "Das Jahresmittel trägt die behobene Störung mit sich -- genau deshalb "
        "ist es nicht die Vergleichsbasis")
