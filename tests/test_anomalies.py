"""Die Erkennungsregel: findet sie alles Echte -- und sonst nichts?

Eine automatische Analyse wird an zwei Fragen gemessen, und nur an diesen:

1. **Findet sie, was da ist?** Der Datensatz enthält fünf eingepflanzte
   Abweichungen. Jede muss mit der richtigen Einheit und einer plausiblen
   Startwoche in der Liste stehen.
2. **Meldet sie, was nicht da ist?** Derselbe Generator erzeugt mit
   ``--no-anomalies`` einen Kontrolldatensatz, der nur das natürliche Rauschen
   enthält. Dort muss die Liste **leer** sein (AK-07.5). Ein einziger Treffer
   dort ist ein Fehlalarm, und ein Fehlalarm kostet eine automatische Analyse
   ihre Glaubwürdigkeit schneller, als zehn richtige Befunde sie aufbauen.

Dazu kommt die Falle, die der Datensatz absichtlich stellt: Alle
Sonderanfertigungen werden überdurchschnittlich oft reklamiert. Das ist ein
Gruppeneffekt, kein Fehler. Eine Regel, die einen Artikel gegen einen globalen
Mittelwert hält, meldet dort sechs Fehlalarme -- deshalb prüft ein eigener Test,
dass keiner entsteht.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data"))

import analysis as an  # noqa: E402
import compute_metrics as cm  # noqa: E402
import formatting as fmt  # noqa: E402

DATASET = ROOT / "data" / "dataset.json"
CONTROL = ROOT / "data" / "dataset_control.json"
GENERATOR = ROOT / "data" / "generate_data.py"
METRICS = ROOT / "data" / "metrics.json"


# --------------------------------------------------------------------------- #
# Datensätze
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def dataset() -> an.Dataset:
    if not DATASET.exists():
        pytest.skip("data/dataset.json existiert noch nicht")
    return an.load_dataset(DATASET)


@pytest.fixture(scope="module")
def control() -> an.Dataset:
    """Der Kontrolldatensatz -- bei Bedarf frisch erzeugt.

    Er steht in ``.gitignore``, weil er jederzeit reproduzierbar ist: derselbe
    Generator, derselbe Seed, nur ohne die eingepflanzten Abweichungen.
    """
    if not CONTROL.exists():
        if not GENERATOR.exists():
            pytest.skip("data/generate_data.py existiert noch nicht")
        subprocess.run(
            [sys.executable, str(GENERATOR), "--no-anomalies", "--out", str(CONTROL)],
            check=True, cwd=str(ROOT), stdout=subprocess.DEVNULL,
        )
    return an.load_dataset(CONTROL)


@pytest.fixture(scope="module")
def metrics() -> dict:
    if not METRICS.exists():
        pytest.skip("data/metrics.json existiert noch nicht")
    return json.loads(METRICS.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def findings(metrics) -> list[dict]:
    return metrics["findings"]


def by_kpi(findings: list[dict], kpi: str) -> dict:
    matching = [entry for entry in findings if entry["kpi"] == kpi]
    assert matching, f"Kein Befund zur Kennzahl '{kpi}'"
    return matching[0]


# --------------------------------------------------------------------------- #
# 1. Alle fünf eingepflanzten Abweichungen werden gefunden
# --------------------------------------------------------------------------- #

#: Vom Program Lead verifizierte Sollwerte (Abnahmeprotokoll Phase 2).
#: kpi · erwartete Einheit · zulässiges Fenster für die Startwoche · Status
EXPECTED_EVENTS = [
    ("quote_win_rate", {"market": "SE", "partner": "partner_4"}, (32, 33), "laufend"),
    ("quote_lead_time_h", {"market": "SE"}, (33, 34), "laufend"),
    ("complaint_rate_items", {"article_id": "MOD-1042", "product_group": "Formteile"},
     (33, 41), "laufend"),
    ("partner_activity_rate", {"market": "NO"}, (40, 42), "laufend"),
    ("otif_rate", {"market": "PL"}, (5, 7), "behoben"),
]


@pytest.mark.parametrize(("kpi", "entity", "window", "status"), EXPECTED_EVENTS,
                         ids=[entry[0] for entry in EXPECTED_EVENTS])
def test_every_planted_deviation_is_found(findings, kpi, entity, window, status):
    finding = by_kpi(findings, kpi)
    for key, value in entity.items():
        assert finding["entity"].get(key) == value, (
            f"'{kpi}': erwartet {key}={value}, gefunden {finding['entity']}")
    assert window[0] <= finding["start_week"] <= window[1], (
        f"'{kpi}': Startwoche {finding['start_week']} liegt außerhalb von "
        f"KW {window[0]} bis {window[1]}")
    assert finding["status"] == status, kpi


def test_exactly_the_five_cases_are_reported(findings):
    """AK-07.2: die fünf Fälle -- und keine sechste Zeile, die niemand erklärt."""
    assert len(findings) == 5, (
        "Erwartet werden genau fünf Fälle:\n"
        + "\n".join(f"{entry['id']} {entry['kpi']} {entry['entity_label']}"
                    for entry in findings))


def test_the_win_rate_case_shows_the_verified_magnitude(findings):
    """Angebotserfolgsquote SE: rund 34 % vor dem Einbruch, rund 21 % danach."""
    finding = by_kpi(findings, "quote_win_rate")
    assert finding["strength"]["baseline"] == pytest.approx(0.337, abs=0.015)
    assert finding["strength"]["current"] == pytest.approx(0.212, abs=0.015)
    assert finding["strength"]["zscore"] >= 2.5


def test_the_lead_time_case_shows_the_verified_magnitude(findings):
    """Angebotsdurchlaufzeit SE: rund 22 vor, rund 39 Stunden danach."""
    finding = by_kpi(findings, "quote_lead_time_h")
    assert finding["strength"]["baseline"] == pytest.approx(22.0, abs=1.5)
    assert finding["strength"]["current"] == pytest.approx(39.4, abs=3.0)


def test_the_article_case_shows_the_verified_magnitude(findings):
    """MOD-1042: 1,96 % im Jahr gegen 0,96 bis 1,14 % der übrigen Formteile."""
    finding = by_kpi(findings, "complaint_rate_items")
    strength = finding["strength"]
    assert strength["year_value"] == pytest.approx(0.0196, abs=0.001)
    year_rates = {article: rate for article, rate in strength["year_by_article"].items()
                  if article != "MOD-1042"}
    assert min(year_rates.values()) == pytest.approx(0.0096, abs=0.001)
    assert max(year_rates.values()) == pytest.approx(0.0114, abs=0.001)
    assert strength["current"] == pytest.approx(0.039, abs=0.004)
    assert strength["top_reason"] == "complaint_lines_reason_dimension"


def test_the_growth_case_reaches_the_verified_peak(findings, metrics):
    """Markt NO: Aktivitätsgrad von rund 88 % auf rund 76 %, Kapazität über 100 %."""
    finding = by_kpi(findings, "partner_activity_rate")
    assert finding["strength"]["baseline"] == pytest.approx(0.88, abs=0.02)
    assert finding["strength"]["current"] == pytest.approx(0.76, abs=0.02)
    assert finding["impact"]["weeks_over_warning"] == 12
    assert [entry["kpi"] for entry in finding["evidence"]] == ["quote_lead_time_h"]
    peak = metrics["scenario"]["base_case"]["per_partner"]["partner_5"]["max_utilization"]
    assert peak == pytest.approx(1.056, abs=0.01)


def test_the_otif_case_is_reported_as_resolved(findings, dataset):
    """Die behobene Abweichung trägt den Status 'behoben' und ein Ende."""
    finding = by_kpi(findings, "otif_rate")
    assert finding["status"] == "behoben"
    assert finding["end_week"] == 13
    assert finding["resolved_from_week"] == 14
    assert finding["strength"]["current"] == pytest.approx(0.866, abs=0.01)


def test_the_swedish_agency_stays_unremarkable_on_activity(findings):
    """Gegenprobe: Die Vertretung in SE verliert Aufträge, nicht den Kundenkontakt."""
    activity = [entry for entry in findings if entry["kpi"] == "partner_activity_rate"]
    assert all(entry["entity"].get("market") != "SE" for entry in activity)


def test_the_problem_is_local_not_global(dataset):
    """Gegenprobe: die Angebotserfolgsquote bricht nur in einem Markt ein."""
    kpi = an.KPIS["quote_win_rate"]
    for market in ("DE", "FR", "IT", "GB", "PL", "NL", "NO", "DK", "FI"):
        value, _ = an.window_value(dataset, kpi, 32, 52, {"market": {market}})
        assert value > 0.28, f"{market} sollte im Rahmen bleiben, ist aber bei {value}"


# --------------------------------------------------------------------------- #
# 2. Kein einziger Fehlalarm auf dem Kontrolldatensatz (AK-07.5)
# --------------------------------------------------------------------------- #

def test_no_alarm_on_the_control_dataset_weekly_scan(control):
    hits = an.scan_weekly(control)
    assert hits == [], (
        "Fehlalarm im Wochen-Scanner auf dem Kontrolldatensatz:\n"
        + "\n".join(f"{entry.kpi_key} {entry.scope} {entry.entity} "
                    f"ab KW {entry.start}" for entry in hits))


def test_no_alarm_on_the_control_dataset_item_scan(control):
    hits = an.scan_item_level(control)
    assert hits == [], (
        "Fehlalarm im Artikel-Scanner auf dem Kontrolldatensatz:\n"
        + "\n".join(f"{entry.article_id} Perioden {entry.periods}"
                    for entry in hits))


def test_the_control_dataset_still_contains_noise(control):
    """Ein Kontrolldatensatz ohne Rauschen würde nichts beweisen.

    Die Angebotserfolgsquote in SE schwankt auch dort deutlich. Läge sie flach,
    wäre der Nullbefund oben nur die Aussage 'eine Gerade ist unauffällig'.
    """
    kpi = an.KPIS["quote_win_rate"]
    points = [point["value"] for point in an.series_of(control, kpi, {"market": {"SE"}})
              if point["value"] is not None]
    assert max(points) - min(points) > 0.02, (
        "Der Kontrolldatensatz enthält zu wenig Rauschen für eine aussagekräftige Probe")


def test_the_control_dataset_has_no_planted_event(control):
    """Zur Sicherheit: die fünf Signale sind im Kontrolldatensatz wirklich weg."""
    win, _ = an.window_value(control, an.KPIS["quote_win_rate"], 35, 52, {"market": {"SE"}})
    assert win > 0.30
    lead, _ = an.window_value(control, an.KPIS["quote_lead_time_h"], 35, 52, {"market": {"SE"}})
    assert lead < 26.0
    activity, _ = an.window_value(control, an.KPIS["partner_activity_rate"], 41, 52,
                                  {"market": {"NO"}})
    assert activity > 0.85
    otif, _ = an.window_value(control, an.KPIS["otif_rate"], 5, 13, {"market": {"PL"}})
    assert otif > 0.93
    profile = an.item_year_profile(control, "complaint_rate_items", "Formteile", "MOD-1042")
    assert profile["value"] < 0.015


# --------------------------------------------------------------------------- #
# 3. Die Falle: Sonderanfertigungen werden generell häufiger reklamiert
# --------------------------------------------------------------------------- #

SPECIAL = "Sonderanfertigungen"


def _global_item_rate(dataset) -> float:
    table = dataset.assortment
    complained = sum(table.at(row, "lines_complained") for row in table.rows)
    shipped = sum(table.at(row, "lines_shipped") for row in table.rows)
    return complained / shipped


def test_the_special_order_pattern_is_not_reported(dataset, findings):
    """Der Effekt ist im Datensatz da -- und darf trotzdem nicht gemeldet werden."""
    special = [article for article, group in dataset.article_group.items()
               if group == SPECIAL]
    assert special, "Im Datensatz gibt es keine Sonderanfertigungen"

    global_rate = _global_item_rate(dataset)
    elevated = []
    for article in special:
        profile = an.item_year_profile(dataset, "complaint_rate_items", SPECIAL, article)
        if profile["value"] and profile["value"] > global_rate:
            elevated.append((article, profile["value"]))
    assert len(elevated) >= 4, (
        "Der Gruppeneffekt ist im Datensatz nicht mehr vorhanden -- "
        "dann prüft dieser Test nichts mehr")

    reported = [entry for entry in findings
                if entry["entity"].get("product_group") == SPECIAL]
    assert not reported, (
        "Sonderanfertigungen werden generell häufiger reklamiert. Das ist ein "
        "Gruppeneffekt und kein Befund:\n" + "\n".join(entry["entity_label"] for entry in reported))


def test_a_global_average_would_produce_exactly_this_false_alarm(dataset):
    """Begründung der Regel: der naive Vergleich meldet die Falle.

    Dieser Test rechnet den *falschen* Vergleich absichtlich nach und hält fest,
    dass er mindestens vier Sonderanfertigungen melden würde. Damit ist belegt,
    warum gegen die übrigen Artikel derselben Produktgruppe verglichen wird und
    nicht gegen einen Gesamtdurchschnitt.
    """
    global_rate = _global_item_rate(dataset)
    minimum = an.KPIS["complaint_rate_items"].min_effect
    naive_hits = []
    for article, group in dataset.article_group.items():
        if group != SPECIAL:
            continue
        profile = an.item_year_profile(dataset, "complaint_rate_items", group, article)
        if profile["value"] and profile["value"] - global_rate >= minimum:
            naive_hits.append(article)
    assert len(naive_hits) >= 4, (
        "Der naive Vergleich gegen den Gesamtdurchschnitt müsste hier Fehlalarme "
        "erzeugen -- sonst belegt der Test die Regel nicht")


# --------------------------------------------------------------------------- #
# 4. Verbesserungen lösen keinen Alarm aus (Richtungsbewusstsein)
# --------------------------------------------------------------------------- #

def _flat_series(value: float, weeks: int = 20, noise: float = 0.001) -> dict:
    return {week: value + (noise if week % 2 else -noise)
            for week in range(1, weeks + 1)}


def test_an_improvement_never_triggers_an_alarm():
    """Entscheidung A6: richtungsbewusst -- eine Verbesserung ist kein Befund."""
    kpi = an.KPIS["otif_rate"]
    times = list(range(1, 21))
    values = _flat_series(0.94)
    for week in range(11, 21):
        values[week] = 0.995                       # deutlich besser als die Basis
    denominators = {week: 5000 for week in times}
    runs = an.detect(kpi, times, values, denominators, {},
                     baseline_weeks=8, zscore_threshold=2.5, consecutive=2,
                     min_denominator=50, use_peers=False)
    assert runs == [], "Eine Verbesserung darf keinen Alarm auslösen"


def test_the_same_jump_downwards_does_trigger_an_alarm():
    """Gegenprobe: derselbe Sprung nach unten muss gemeldet werden."""
    kpi = an.KPIS["otif_rate"]
    times = list(range(1, 21))
    values = _flat_series(0.96)
    for week in range(11, 21):
        values[week] = 0.90
    denominators = {week: 5000 for week in times}
    runs = an.detect(kpi, times, values, denominators, {},
                     baseline_weeks=8, zscore_threshold=2.5, consecutive=2,
                     min_denominator=50, use_peers=False)
    assert runs and runs[0][0].week == 11


def test_a_single_outlier_week_is_not_enough():
    """Zwei-Wochen-Regel: ein Ausreißer allein ist noch kein Befund."""
    kpi = an.KPIS["otif_rate"]
    times = list(range(1, 21))
    values = _flat_series(0.96)
    values[12] = 0.88
    denominators = {week: 5000 for week in times}
    runs = an.detect(kpi, times, values, denominators, {},
                     baseline_weeks=8, zscore_threshold=2.5, consecutive=2,
                     min_denominator=50, use_peers=False)
    assert runs == []


def test_a_deviation_inside_the_agreed_corridor_is_not_a_finding():
    """Statistisch klar, fachlich folgenlos: kein Befund.

    Die Liefertreue fällt von 99,5 % auf 96 % -- ein riesiger z-Wert, weil die
    Reihe vorher fast rauschfrei war. Der Wert liegt aber weiter über dem
    vereinbarten Zielwert von 95 %. Es gibt nichts zu tun.
    """
    kpi = an.KPIS["otif_rate"]
    times = list(range(1, 21))
    values = {week: 0.995 for week in times}
    for week in range(11, 21):
        values[week] = 0.96
    denominators = {week: 5000 for week in times}
    runs = an.detect(kpi, times, values, denominators, {},
                     baseline_weeks=8, zscore_threshold=2.5, consecutive=2,
                     min_denominator=50, use_peers=False)
    assert runs == []


def test_a_cell_below_the_minimum_sample_is_not_scored():
    """AK-07.6 und Festlegung F2: zu kleiner Nenner, keine Bewertung."""
    kpi = an.KPIS["otif_rate"]
    times = list(range(1, 21))
    values = _flat_series(0.96)
    for week in range(11, 21):
        values[week] = 0.80
    denominators = {week: 5000 if week <= 10 else 10 for week in times}
    runs = an.detect(kpi, times, values, denominators, {},
                     baseline_weeks=8, zscore_threshold=2.5, consecutive=2,
                     min_denominator=50, use_peers=False)
    assert runs == []


def test_the_baseline_is_frozen_while_a_deviation_runs():
    """Entscheidung A6: ohne Einfrieren wandert die Basis mit und frisst den Befund.

    Eine Verschlechterung, die zehn Wochen lang anhält, muss zehn Wochen lang
    auffällig bleiben. Zieht die Basis nach, ist sie nach acht Wochen auf dem
    neuen Niveau und der Befund verschwindet von selbst.
    """
    kpi = an.KPIS["otif_rate"]
    times = list(range(1, 31))
    values = _flat_series(0.96, weeks=30)
    for week in range(11, 31):
        values[week] = 0.86
    denominators = {week: 5000 for week in times}
    runs = an.detect(kpi, times, values, denominators, {},
                     baseline_weeks=8, zscore_threshold=2.5, consecutive=2,
                     min_denominator=50, use_peers=False)
    assert runs, "Die Abweichung wurde gar nicht erkannt"
    assert runs[0][0].week == 11
    assert runs[0][-1].week == 30, (
        "Der Befund endet vorzeitig -- die Vergleichsbasis ist mitgewandert")
    assert all(flag.baseline == pytest.approx(runs[0][0].baseline)
               for flag in runs[0]), "Die eingefrorene Basis hat sich verändert"


def test_a_common_seasonal_movement_is_not_a_finding():
    """Was alle gleichzeitig trifft, ist Saison und kein Befund.

    Steigt die Reklamationsquote im Jahresendgeschäft überall gleichermaßen, darf
    kein einzelner Markt dafür gemeldet werden. Genau diese Bereinigung leistet der
    Vergleich gegen die Vergleichsgruppe derselben Woche.
    """
    kpi = an.KPIS["complaint_rate_lines"]
    times = list(range(1, 21))
    # Etwas Rauschen, sonst ist die Streuung der Vergleichsbasis exakt null und
    # der Test prüfte einen Sonderfall statt der Regel.
    values = {week: 0.010 + (0.0002 if week % 2 else -0.0002) for week in times}
    peers = {week: 0.010 for week in times}
    for week in range(11, 21):
        values[week] += 0.004
        peers[week] += 0.004
    denominators = {week: 5000 for week in times}
    runs = an.detect(kpi, times, values, denominators, peers,
                     baseline_weeks=8, zscore_threshold=2.5, consecutive=2,
                     min_denominator=50, use_peers=True)
    assert runs == []

    # Zieht nur eine Einheit davon, bleibt der Befund erhalten.
    for week in range(11, 21):
        values[week] += 0.005
    runs = an.detect(kpi, times, values, denominators, peers,
                     baseline_weeks=8, zscore_threshold=2.5, consecutive=2,
                     min_denominator=50, use_peers=True)
    assert runs and runs[0][0].week == 11


# --------------------------------------------------------------------------- #
# 5. Folgeeffekt (US-09)
# --------------------------------------------------------------------------- #

def test_the_lead_time_increase_is_linked_to_the_win_rate_case(findings):
    """AK-09.1: derselbe Markt, Beginn höchstens zwei Wochen später."""
    win = by_kpi(findings, "quote_win_rate")
    lead = by_kpi(findings, "quote_lead_time_h")
    assert lead["follow_up_of"] == win["id"], (
        "Der Anstieg der Angebotsdurchlaufzeit ist nicht mit dem Erfolgsquotenfall verknüpft")
    assert lead["entity"]["market"] == win["entity"]["market"]
    offset = lead["start_week"] - win["start_week"]
    assert 0 <= offset <= 2
    assert lead["follow_up_offset_weeks"] == offset
    assert win["follow_ups"] == [lead["id"]]


def test_the_follow_up_text_rules_out_a_causal_claim(findings):
    """AK-09.3: ausdrücklich zeitlicher Zusammenhang, kein Ursachennachweis."""
    lead = by_kpi(findings, "quote_lead_time_h")
    text = lead["follow_up_text"]
    assert an.NO_CAUSALITY in text
    assert an.GENERATED_MARK in text
    assert "mutmaßlich" in text.lower()


def test_cases_in_different_markets_are_never_linked(findings):
    for finding in findings:
        if not finding["follow_up_of"]:
            continue
        reference = next(entry for entry in findings
                         if entry["id"] == finding["follow_up_of"])
        assert finding["entity"]["market"] == reference["entity"]["market"]


def test_a_case_without_a_market_is_never_a_follow_up(findings):
    for finding in findings:
        if not finding["entity"].get("market"):
            assert finding["follow_up_of"] is None, finding["id"]


# --------------------------------------------------------------------------- #
# 6. Form und Inhalt jedes Befunds (AK-07.1, AK-07.3, AK-07.4)
# --------------------------------------------------------------------------- #

def test_every_finding_carries_the_eight_required_fields(findings):
    for finding in findings:
        assert re.fullmatch(r"F-\d{2}", finding["id"]), finding["id"]
        assert finding["kpi"] in an.KPIS, finding["id"]
        assert finding["entity_label"], finding["id"]
        assert isinstance(finding["start_week"], int), finding["id"]
        assert finding["strength"]["deviation_text"], finding["id"]
        assert finding["strength"]["zscore_text"], finding["id"]
        assert (finding["impact"]["euro"] is not None
                or finding["impact"]["quantity_text"]), finding["id"]
        assert finding["department"], finding["id"]
        assert finding["proposed_action"], finding["id"]
        assert finding["status"] in {"laufend", "behoben"}, finding["id"]
        assert finding["severity"] in {"gering", "mittel", "hoch"}, finding["id"]


def test_every_explanation_is_marked_as_generated_and_never_says_it_is_intelligent(findings):
    """AK-07.3 und Festlegung F5. Regelbasiertes heißt 'automatische Analyse'."""
    # Das Kürzel steht hier bewusst als Zeichenkette in Anführungszeichen: Die
    # Regelprüfung in tests/test_rules.py unterscheidet zwischen Erwähnung und
    # Verwendung, und eine Erwähnung ist das Gegenteil einer Behauptung.
    term = "KI"
    forbidden = re.compile(rf"(?<![\w-]){term}(?![\w-])")
    for finding in findings:
        assert an.GENERATED_MARK in finding["explanation"], finding["id"]
        assert not forbidden.search(finding["explanation"]), finding["id"]
        assert "künstliche Intelligenz" not in finding["explanation"].lower(), finding["id"]


def test_findings_are_sorted_by_estimated_impact(findings):
    """AK-07.4: in der Voreinstellung steht die größte Wirkung oben."""
    euros = [finding["impact"]["euro"] or 0.0 for finding in findings]
    assert euros == sorted(euros, reverse=True)


def test_every_impact_chain_is_complete_and_recomputable(findings):
    """Jeder Parameter und jede Zwischengröße liegt offen (US-07)."""
    for finding in findings:
        chain = finding["impact"]["chain"]
        assert len(chain) >= 4, finding["id"]
        for step in chain:
            assert step["label"] and step["value"] and step["source"], finding["id"]
        assert finding["impact"]["method"], finding["id"]
        if finding["impact"]["euro"] is None:
            assert finding["impact"]["note"], (
                f"{finding['id']}: ohne Eurobetrag braucht es eine Begründung")


def test_the_impact_of_the_win_rate_case_recomputes_from_the_dataset(dataset, findings):
    """Stichprobe: die Kette wird von Hand nachgerechnet, Schritt für Schritt."""
    finding = by_kpi(findings, "quote_win_rate")
    start, end = finding["start_week"], finding["end_week"]
    filters = {"market": {"SE"}, "partner": {"partner_4"}}

    decided = an.field_sum(dataset, "facts_weekly", "quotes_decided", filters, start, end)
    lost = round(decided * (finding["strength"]["baseline"] - finding["strength"]["current"]))
    margin = round(an.derived_rate(dataset, "contribution_margin_eur", "orders_shipped",
                                   {"market": {"SE"}}), 2)

    chain = {step["label"]: step["value"] for step in finding["impact"]["chain"]}
    assert chain["Entschiedene Angebote im Zeitraum"] == fmt.count(decided)
    assert chain["Zusätzlich verlorene Angebote"] == fmt.count(lost)
    assert chain["Deckungsbeitrag je Auftrag im Markt"] == fmt.euro(margin)
    assert chain["Geschätzte Wirkung"] == finding["impact"]["euro_text"]
    assert finding["impact"]["euro"] == pytest.approx(lost * margin, abs=0.005)


def test_no_impact_is_counted_twice(findings):
    """Ursache und Folgeeffekt dürfen dieselbe Summe nicht zweimal ausweisen."""
    for finding in findings:
        if finding["follow_up_of"]:
            assert finding["impact"]["euro"] is None, (
                f"{finding['id']} ist ein Folgeeffekt und darf die Kostenwirkung "
                "des auslösenden Befunds nicht erneut ausweisen")
            assert "doppelt" in finding["impact"]["note"]


def test_departments_come_from_the_catalogue(findings):
    """Rechenregel R6: genau ein Verantwortlicher je Kennzahl, keine Mehrfachzuordnung."""
    for finding in findings:
        assert finding["department"] == an.KPIS[finding["kpi"]].department


def test_every_finding_has_a_series_for_the_detail_chart(findings):
    """AK-08.1: die Detailgrafik braucht den Verlauf und die Vergleichsbasis."""
    for finding in findings:
        # 52 Wochenpunkte, bei der Artikelanalyse ein Punkt je Periode.
        assert len(finding["series"]) >= 10, finding["id"]
        assert finding["baseline_window"]["text"], finding["id"]


# --------------------------------------------------------------------------- #
# 7. Die Regel selbst benutzt die Parameter aus dem Datensatz
# --------------------------------------------------------------------------- #

def test_the_rule_uses_the_parameters_from_the_dataset(dataset, metrics):
    rule = metrics["meta"]["detection_rule"]
    assert rule["baseline_weeks"] == dataset.parameters["baseline_weeks"]
    assert rule["zscore_threshold"] == dataset.parameters["zscore_threshold"]
    assert rule["consecutive_weeks"] == dataset.parameters["consecutive_weeks"]
    assert rule["min_denominator"] == dataset.parameters["min_denominator"]
    assert rule["min_denominator_item"] == dataset.parameters["min_denominator_item"]


def test_the_minimum_effect_is_documented_for_every_scanned_kpi(metrics):
    """Die fachliche Mindestabweichung ist eine Festlegung -- sie gehört offengelegt."""
    documented = metrics["meta"]["detection_rule"]["min_effect"]
    for kpi_key, _ in an.SCAN_PLAN:
        assert documented.get(kpi_key), kpi_key
        assert documented[kpi_key] > 0, kpi_key


def test_the_stage_metrics_are_not_scanned_separately():
    """Sonst stünde derselbe Sachverhalt zweimal in der Liste."""
    scanned = {kpi for kpi, _ in an.SCAN_PLAN}
    assert not scanned & set(an.STAGE_KEYS)


def test_the_scan_plan_only_uses_levels_the_filter_matrix_allows():
    for kpi_key, scope in an.SCAN_PLAN:
        for column in an.SCOPE_COLUMNS[scope]:
            assert column in cm.EVALUABLE[kpi_key], (
                f"'{kpi_key}' wird auf der Ebene '{column}' überwacht, ist dort aber "
                "laut Filtermatrix nicht auswertbar")


# --------------------------------------------------------------------------- #
# 8. QA-1 bis QA-3: ein Fenster, ein Rechenweg, eine Beginnwoche
# --------------------------------------------------------------------------- #

def test_the_reported_value_is_a_quotient_of_sums(dataset, findings):
    """Entscheidung QA-1: Anzeigewert und Vergleichsbasis auf demselben Rechenweg.

    Vorher war die Vergleichsbasis ein Quotient aus Summen und der Istwert das
    Mittel der Wochenquoten. Die ausgewiesene Abweichung war damit die Differenz
    zweier verschieden gerechneter Größen -- und die Befundkarte widersprach der
    Partner-Scorecard, die denselben Ausschnitt korrekt aggregiert.
    """
    for finding in findings:
        if finding["entity"]["scope"] == "article":
            continue  # eigene Prüfung unten, Vergleich gegen die übrigen Artikel
        kpi = an.KPIS[finding["kpi"]]
        filters = {column: {value} for column, value in finding["entity"].items()
                   if column in an.DIMENSION_COLUMN}
        window = finding["strength"]["current_window"]
        expected, _ = an.window_value(dataset, kpi, window["week_from"],
                                      window["week_to"], filters)
        assert finding["strength"]["current_reported"] == pytest.approx(expected, rel=1e-9), (
            f"{finding['id']}: gemeldeter Istwert ist kein Quotient aus Summen")
        assert finding["strength"]["current"] == finding["strength"]["current_reported"]

        base = finding["strength"]["baseline_window"]
        expected_baseline, _ = an.window_value(dataset, kpi, base["week_from"],
                                               base["week_to"], filters)
        assert finding["strength"]["baseline"] == pytest.approx(expected_baseline, rel=1e-9), (
            f"{finding['id']}: Vergleichsbasis ist kein Quotient aus Summen")


def test_the_reported_value_differs_from_the_weekly_mean(findings):
    """Der Unterschied ist messbar -- sonst wäre die Korrektur folgenlos.

    Wäre das Mittel der Wochenquoten identisch mit dem Quotienten aus Summen,
    hätte QA-1 nichts beanstandet und dieser Test nichts zu zeigen.
    """
    differing = [finding["id"] for finding in findings
                 if finding["strength"].get("current_weekly_mean") is not None
                 and finding["strength"]["current_weekly_mean"]
                 != pytest.approx(finding["strength"]["current_reported"], abs=1e-12)]
    assert differing, (
        "Kein Befund zeigt einen Unterschied zwischen Wochenmittel und Quotient "
        "aus Summen -- dann prüft dieser Test nichts")


def test_the_item_peer_value_is_a_quotient_of_sums(dataset, findings):
    """Dieselbe Regel für die Artikelanalyse: auch der Vergleichswert ist ein Quotient."""
    finding = by_kpi(findings, "complaint_rate_items")
    kpi = an.KPIS["complaint_rate_items"]
    periods = list(range(finding["start_period"], finding["end_period"] + 1))
    profile = an.item_window_profile(dataset, kpi.key, finding["entity"]["product_group"],
                                     finding["entity"]["article_id"], periods)
    assert finding["strength"]["current_reported"] == pytest.approx(profile["value"], rel=1e-9)
    assert finding["strength"]["baseline"] == pytest.approx(profile["peer_value"], rel=1e-9)


def test_the_deviation_is_the_difference_of_the_two_reported_values(findings):
    """Die ausgewiesene Abweichung muss aus den ausgewiesenen Werten entstehen."""
    for finding in findings:
        kpi = an.KPIS[finding["kpi"]]
        strength = finding["strength"]
        expected = kpi.worsening(strength["current_reported"] - strength["baseline"])
        assert strength["deviation"] == pytest.approx(expected, rel=1e-9), finding["id"]
        assert strength["deviation_text"] == kpi.delta_text(
            strength["current_reported"] - strength["baseline"]), finding["id"]


def test_the_stated_start_week_matches_the_stated_windows(findings):
    """Entscheidung QA-2: eine Beginnwoche, und die Fenster gehören zu ihr.

    Früher nannte ein Befund die Beginnwoche des Falls, zeigte aber die Werte des
    Laufs der Leitkennzahl, der eine Woche später begann. Der Satz "seit KW 32 von A
    auf B" mischte damit zwei Zeiträume.
    """
    for finding in findings:
        start = finding["start_week"]
        current = finding["strength"]["current_window"]
        base = finding["strength"]["baseline_window"]
        assert current["week_from"] == start, finding["id"]
        assert current["week_to"] == finding["end_week"], finding["id"]
        if base["week_from"] is not None:
            assert base["week_to"] == start - 1, (
                f"{finding['id']}: Basisfenster endet nicht unmittelbar vor der "
                f"genannten Beginnwoche")


def test_the_z_value_belongs_to_the_stated_start_week(findings):
    """Ein z-Wert ohne seine Woche ist eine Zahl ohne Bezug."""
    for finding in findings:
        strength = finding["strength"]
        if finding["entity"]["scope"] == "article":
            assert strength["zscore_period"] == finding["start_period"], finding["id"]
        else:
            assert strength["zscore_week"] == finding["start_week"], finding["id"]
        assert strength["zscore_max"] >= strength["zscore"], finding["id"]


def test_the_case_start_is_the_earliest_of_its_metrics(findings):
    """Der Fall beginnt, wenn seine erste Kennzahl auffällig wird -- nicht später."""
    for finding in findings:
        starts = [finding["lead_kpi_start_week"]]
        starts += [entry["start_week"] for entry in finding["evidence"]]
        assert finding["start_week"] == min(starts), finding["id"]
        assert finding["start_week_source"], finding["id"]


def test_every_euro_chain_multiplies_out_to_the_cent(findings):
    """Eine Rechenkette, die sich nicht nachrechnen lässt, ist Dekoration.

    Menge × Satz je Vorgang muss genau den ausgewiesenen Betrag ergeben. Deshalb sind
    abgeleitete Mengen ganze Vorgänge und Sätze auf Cent gerundet -- beides
    nach der Division, nicht davor (Rechenregel R5).
    """
    def number(text: str) -> float:
        return float(text.split()[0].replace(".", "").replace(",", "."))

    for finding in findings:
        if finding["impact"]["euro"] is None:
            continue
        chain = finding["impact"]["chain"]
        rate_at = next(position for position, step in enumerate(chain)
                       if step["label"].startswith(("Kosten je", "Deckungsbeitrag je")))
        quantity = number(chain[rate_at - 1]["value"])
        rate = number(chain[rate_at]["value"])
        total = number(chain[-1]["value"])
        assert chain[-1]["label"] == "Geschätzte Wirkung", finding["id"]
        assert quantity * rate == pytest.approx(total, abs=0.005), (
            f"{finding['id']}: {quantity} x {rate} ergibt {quantity * rate:.2f}, "
            f"ausgewiesen sind {total:.2f}")
        assert finding["impact"]["rounding_note"], finding["id"]


def test_the_wording_separates_series_from_findings(metrics, findings):
    """Entscheidung QA-6: auffällige Zeitreihen sind nicht gemeldete Auffälligkeiten."""
    rule = metrics["meta"]["detection_rule"]
    assert rule["flagged_series"] > rule["reported_findings"], (
        "Ohne Unterschied braucht es die Unterscheidung nicht")
    assert rule["reported_findings"] == len(findings)
    assert rule["flagged_series_weekly"] + rule["flagged_series_item"] == rule["flagged_series"]
    assert "Zeitreihen" in rule["wording"] and "Fälle" in rule["wording"]
