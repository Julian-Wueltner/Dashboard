"""Erzeugt ``data/metrics.json`` aus ``data/dataset.json``.

``data/metrics.json`` ist die einzige Zahlenquelle für Cockpit, Management-Report
und Case Study (Entscheidung A3). Der Aufbau ist der verbindliche Vertrag aus
Entscheidung A12: ``meta``, ``dimensions``, ``kpis``, ``breakdowns``, ``findings``,
``measures``, ``scenario``, ``decision_paper``, ``report``, ``case_study``.

Jede Zeichenkette in dieser Datei entsteht in ``data/formatting.py`` (A11). Im
Quelltext steht keine gerundete Zahl als Text -- nur Feldnamen, Zeitfenster und
Vorlagen.

Aufruf:  python data/compute_metrics.py [--dataset PFAD] [--out PFAD]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import analysis as an  # noqa: E402
import formatting as fmt  # noqa: E402

ROOT = HERE.parent

# --------------------------------------------------------------------------- #
# Filtermatrix (docs/KPI_DEFINITIONS.md Abschnitt 6)
# --------------------------------------------------------------------------- #

#: Auf welcher Ebene eine Kennzahl ausgewertet werden darf. Was hier fehlt, zeigt
#: das Cockpit als "auf dieser Filterebene nicht auswertbar" (AK-02.5).
EVALUABLE: dict[str, set[str]] = {
    "quote_lead_time_h": {"market", "channel", "partner"},
    "quote_win_rate": {"market", "channel", "partner"},
    "order_lead_time_d": {"market", "channel", "partner"},
    "otif_rate": {"market", "channel", "partner"},
    "complaint_rate_lines": {"market", "channel", "partner"},
    "complaint_processing_time_d": {"market", "channel", "partner"},
    "delivery_inquiries_per_100_orders": {"market", "channel", "partner"},
    "contribution_margin_per_order_eur": {"market", "channel", "partner"},
    "revenue_index": {"market", "channel", "partner"},
    "partner_activity_rate": {"market", "channel", "partner"},
    "complaint_rate_items": {"product_group", "article"},
    "stage1_inquiry_to_quote_h": {"market", "channel", "partner"},
    "stage2_quote_to_order_h": {"market", "channel", "partner"},
    "stage3_order_entry_h": {"market", "channel", "partner"},
    "stage4_production_shipping_h": {"market", "channel", "partner"},
    "stage5_complaint_h": {"market", "channel", "partner"},
}

BREAKDOWN_LEVELS = [
    ("by_market", "market"),
    ("by_channel", "channel"),
    ("by_partner", "partner"),
]

PARTNER_NAME = dict(an.PARTNER_LABEL)
CHANNEL_NAME = dict(an.CHANNEL_LABEL)


def dimension_label(level: str, value: str) -> str:
    if level == "partner":
        return PARTNER_NAME.get(value, value)
    if level == "channel":
        return CHANNEL_NAME.get(value, value)
    return str(value)


# --------------------------------------------------------------------------- #
# Kennzahlenblock
# --------------------------------------------------------------------------- #

def build_series(dataset: an.Dataset, kpi: an.Kpi) -> list[dict]:
    """Zeitreihe einer Kennzahl.

    Kennzahlen aus ``assortment_periods`` haben Vier-Wochen-Perioden als
    Zeitachse (Entscheidung OP-1). Damit sie im selben Diagramm liegen wie die
    Wochenreihen, trägt jeder Punkt die Woche, mit der seine Periode endet.
    """
    points = an.series_of(dataset, kpi)
    if kpi.table != "assortment_periods":
        return [{"week": point["week"], "value": _round(point["value"])} for point in points]
    result = []
    for point in points:
        first, last = dataset.weeks_of_period(point["week"])
        result.append({"week": last, "period": point["week"], "week_from": first,
                       "week_to": last, "value": _round(point["value"])})
    return result


def _round(value, digits: int | None = None):
    """Rohwerte bleiben unverändert.

    Eine Rundung auf wenige Nachkommastellen scheint harmlos, kostet aber genau
    die Genauigkeit, mit der der JavaScript-Rechenkern gegen diese Datei geprüft
    wird (Toleranz 1e-9 relativ). Bei der Reklamationsquote von rund 0,01
    reichen acht Nachkommastellen dafür nicht. Gerundet wird deshalb nur der
    *Text* -- und der entsteht in data/formatting.py.
    """
    if value is None:
        return None
    return value if digits is None else round(value, digits)


def build_kpis(dataset: an.Dataset) -> dict:
    kpis: dict[str, dict] = {}
    for key, kpi in an.KPIS.items():
        value, denominator = an.kpi_value(dataset, kpi)
        minimum = (dataset.min_denominator_item if kpi.table == "assortment_periods"
                   else dataset.min_denominator)
        status = an.traffic_light(kpi, value, denominator, minimum)
        points = build_series(dataset, kpi)
        entry = {
            "label": kpi.label,
            "value": _round(value),
            "text": kpi.text(value) if value is not None else "zu wenig Daten",
            "unit": kpi.unit,
            "decimals": kpi.decimals,
            "target": kpi.target,
            "target_text": kpi.text(kpi.target),
            "warning": kpi.warning,
            "warning_text": kpi.text(kpi.warning),
            "direction": kpi.direction,
            "department": kpi.department,
            "status": status,
            "status_label": an.TRAFFIC_LIGHT_LABEL[status],
            "trend": an.trend(kpi, points),
            "series": points,
            "denominator": _round(denominator),
            "min_denominator": minimum,
            "source_table": kpi.table,
            "evaluable_levels": sorted(EVALUABLE.get(key, set())),
        }
        if key in an.STAGE_OWNER:
            entry["stage_owner"] = an.STAGE_OWNER[key]
        kpis[key] = entry
    return kpis


def build_breakdowns(dataset: an.Dataset) -> dict:
    """Je Kennzahl die Aufteilung auf die Ebenen, auf denen sie auswertbar ist."""
    breakdowns: dict[str, dict] = {}
    for key, kpi in an.KPIS.items():
        levels = EVALUABLE.get(key, set())
        block: dict[str, dict] = {}
        for name, level in BREAKDOWN_LEVELS:
            if level not in levels:
                continue
            column = an.DIMENSION_COLUMN[level]
            table = an.table_for(dataset, kpi)
            if not table.has(column):
                continue
            entries: dict[str, dict] = {}
            for value in table.distinct(column):
                result, denominator = an.kpi_value(dataset, kpi, {column: {value}})
                status = an.traffic_light(kpi, result, denominator, dataset.min_denominator)
                entries[str(value)] = {
                    "label": dimension_label(level, value),
                    "value": _round(result),
                    "text": kpi.text(result) if result is not None else "zu wenig Daten",
                    "status": status,
                    "status_label": an.TRAFFIC_LIGHT_LABEL[status],
                    "denominator": _round(denominator),
                }
            block[name] = entries
        if kpi.table == "assortment_periods":
            block["by_product_group"] = _assortment_breakdown(dataset, kpi, "product_group")
            block["by_article"] = _assortment_breakdown(dataset, kpi, "article")
        if block:
            breakdowns[key] = block
    return breakdowns


def _assortment_breakdown(dataset: an.Dataset, kpi: an.Kpi, level: str) -> dict:
    table = dataset.assortment
    groups: dict[str, list[float]] = {}
    for row in table.rows:
        if level == "product_group":
            key = table.at(row, "product_group")
        else:
            key = str(table.at(row, "article_id"))
        entry = groups.setdefault(key, [0.0, 0.0])
        entry[0] += sum(row[table.position(name)] for name in kpi.numerator)
        entry[1] += sum(row[table.position(name)] for name in kpi.denominator)
    result = {}
    for key in sorted(groups):
        numerator, denominator = groups[key]
        value = kpi.compute(numerator, denominator)
        status = an.traffic_light(kpi, value, denominator, dataset.min_denominator_item)
        result[key] = {
            "label": key if level == "product_group" else f"Artikel {key}",
            "value": _round(value),
            "text": kpi.text(value) if value is not None else "zu wenig Daten",
            "status": status,
            "status_label": an.TRAFFIC_LIGHT_LABEL[status],
            "denominator": _round(denominator),
        }
    return result


# --------------------------------------------------------------------------- #
# Auffälligkeiten mit Wirkungsschätzung
# --------------------------------------------------------------------------- #

#: Wie viele Zeitreihen die Regel als auffällig bewertet hat und wie viele Fälle
#: daraus gemeldet werden. Die beiden Zahlen unterscheiden sich, weil mehrere
#: Kennzahlen derselben Einheit ein Fall sind (Entscheidung QA-6: "auffällige
#: Zeitreihen" gegenüber "gemeldete Auffälligkeiten").
SERIES_COUNTS: dict[str, int] = {}


def build_findings(dataset: an.Dataset) -> list[dict]:
    last_week = dataset.weeks[-1]
    weekly = an.scan_weekly(dataset)
    cases = an.consolidate(weekly)
    item_cases = an.scan_item_level(dataset)
    SERIES_COUNTS["flagged_series_weekly"] = len(weekly)
    SERIES_COUNTS["flagged_series_item"] = len(item_cases)
    SERIES_COUNTS["flagged_series"] = len(weekly) + len(item_cases)
    SERIES_COUNTS["reported_findings"] = len(cases) + len(item_cases)

    # Kostensätze, aus additiven Feldern des Datensatzes abgeleitet -- keine
    # Annahme, keine Hochrechnung (Abgrenzungspunkt 8). Auf Cent gerundet, und
    # zwar *nach* der Division (Rechenregel R5): Ein Kostensatz je Vorgang ist ein
    # Geldbetrag, und nur mit dem ausgewiesenen Betrag lässt sich die Rechenkette
    # mit dem Taschenrechner nachvollziehen. Menge × Satz trifft den Betrag dann
    # auf den Cent.
    cost_per_complaint = round(
        an.derived_rate(dataset, "complaint_cost_eur", "complaints_closed"), 2)

    findings: list[dict] = []
    for case in cases:
        findings.append(_weekly_finding(dataset, case, last_week))
    for item in item_cases:
        findings.append(_item_finding(dataset, item, cost_per_complaint))

    findings.sort(key=lambda entry: (-(entry["impact"]["euro"] or 0.0),
                                     entry["start_week"]))
    for position, finding in enumerate(findings, start=1):
        finding["id"] = f"F-{position:02d}"

    _link_follow_ups(findings)
    return findings


def _weekly_finding(dataset: an.Dataset, case: dict, last_week: int) -> dict:
    lead: an.RawFinding = case["lead"]
    kpi = an.KPIS[lead.kpi_key]
    scope, entity = case["scope"], case["entity"]
    label = an.entity_label(scope, entity)
    filters = {column: {value}
               for column, value in zip(an.SCOPE_COLUMNS[scope], entity)}

    # Entscheidung QA-2: Der Fall nennt **eine** Beginnwoche -- die früheste, in
    # der eine seiner Kennzahlen auffällig wurde. Alle angezeigten Werte werden
    # über genau dieses Fenster gerechnet, damit der Satz "seit KW x von A auf B"
    # nicht zwei verschiedene Zeiträume vermischt.
    start, end = case["start"], case["end"]
    resolved = end < last_week
    window = (max(dataset.weeks[0], start - dataset.baseline_weeks), start - 1)

    # Entscheidung QA-1: Vergleichsbasis **und** Istwert sind Quotienten aus
    # Summen über ihr Fenster (Rechenregel R1). Damit stimmt die Befundkarte mit
    # jeder gefilterten Ansicht des Cockpits überein. Das Mittel der
    # Wochenquoten bleibt als Bezugsgröße des z-Werts erhalten, wird aber nicht
    # angezeigt.
    baseline, _ = an.window_value(dataset, kpi, window[0], window[1], filters)
    current, denominator = an.window_value(dataset, kpi, start, end, filters)
    weekly_mean = lead.current_value

    impact = _impact_for(dataset, lead.kpi_key, filters, start, end, baseline, current)

    evidence = []
    for item in case["evidence"]:
        other = an.KPIS[item.kpi_key]
        other_window = (max(dataset.weeks[0], item.start - dataset.baseline_weeks),
                        item.start - 1)
        other_baseline, _ = an.window_value(dataset, other, other_window[0],
                                            other_window[1], filters)
        other_current, _ = an.window_value(dataset, other, item.start, item.end, filters)
        evidence.append({
            "kpi": item.kpi_key,
            "label": other.label,
            "start_week": item.start,
            "start_week_text": fmt.week(item.start),
            "period_text": fmt.week_range(item.start, item.end),
            "baseline_window_text": fmt.week_range(other_window[0], other_window[1]),
            "baseline_text": other.text(other_baseline),
            "current_text": other.text(other_current),
            "zscore": round(item.flags[item.start].zscore, 2),
            "zscore_text": fmt.number(item.flags[item.start].zscore, 1),
        })

    # Der z-Wert gehört zu der Woche, die der Befund als Beginn nennt. Beginnt der
    # Fall vor dem Lauf der Leitkennzahl, liegt deren z-Wert für diese Woche in
    # der Spur vor -- sie war dort statistisch auffällig, hat aber die fachliche
    # Mindestabweichung noch nicht erreicht.
    if start in lead.zscores:
        zscore, zscore_week = lead.zscores[start], start
    else:
        zscore, zscore_week = lead.flags[lead.start].zscore, lead.start
    zscore_max = max(flag.zscore for flag in lead.flags.values())
    deviation = kpi.worsening(current - baseline)
    severity = an.severity_of(kpi, current, resolved)
    extra = ""
    if evidence:
        names = " und ".join(an.KPIS[item.kpi_key].subject for item in case["evidence"])
        extra = f"Im selben Zeitraum weicht auch {names} ab."
    after_value = None
    if resolved:
        after_value, _ = an.window_value(dataset, kpi, end + 1, last_week, filters)

    return {
        "id": "",
        "kpi": lead.kpi_key,
        "kpi_label": kpi.label,
        "unit": kpi.unit,
        "entity": _entity_block(scope, entity, label),
        "entity_label": label,
        "start_week": start,
        "start_week_text": fmt.week(start),
        "end_week": end,
        "end_week_text": fmt.week(end),
        "period_text": fmt.week_range(start, end),
        "lead_kpi_start_week": lead.start,
        "lead_kpi_start_week_text": fmt.week(lead.start),
        "start_week_source": (kpi.label if lead.start == start else
                              next((an.KPIS[item.kpi_key].label
                                    for item in case["evidence"]
                                    if item.start == start), kpi.label)),
        "strength": _strength(kpi, baseline, current, deviation, zscore,
                              window, denominator, start, end,
                              weekly_mean, zscore_week, zscore_max),
        "impact": impact,
        "department": kpi.department,
        "explanation": an.explanation_text(kpi, label, start, baseline, current,
                                           zscore, extra,
                                           end_week=end if resolved else None,
                                           after=after_value),
        "proposed_action": an.PROPOSED_ACTIONS.get(lead.kpi_key, ""),
        "severity": severity,
        "status": "behoben" if resolved else "laufend",
        "resolved_from_week": end + 1 if resolved else None,
        "resolved_from_week_text": fmt.week(end + 1) if resolved else None,
        "evidence": evidence,
        "series": [{"week": point["week"], "value": _round(point["value"])}
                   for point in lead.series],
        "baseline_window": {"week_from": window[0], "week_to": window[1],
                            "text": fmt.week_range(window[0], window[1])},
        "follow_up_of": None,
        "follow_up_text": None,
    }


def _entity_block(scope: str, entity: tuple, label: str) -> dict:
    block = {"scope": scope, "label": label}
    for column, value in zip(an.SCOPE_COLUMNS[scope], entity):
        block[column] = value
    return block


def _strength(kpi: an.Kpi, baseline: float, current: float, deviation: float,
              zscore: float, window: tuple[int, int], denominator: float,
              start: int, end: int, weekly_mean: float, zscore_week: int,
              zscore_max: float) -> dict:
    """Die Stärke eines Befunds -- jede Zahl mit dem Fenster, aus dem sie stammt.

    ``current`` und ``current_reported`` sind derselbe Wert: der Quotient aus
    Summen über das Befundfenster. Der zweite Name steht im Vertrag (QA-1) und
    macht im Datensatz sichtbar, dass hier der *gemeldete* Wert steht.
    ``current_weekly_mean`` ist das Mittel der Wochenquoten -- die Bezugsgröße
    des z-Werts, kein Anzeigewert.
    """
    return {
        "baseline": _round(baseline),
        "baseline_text": kpi.text(baseline),
        "current": _round(current),
        "current_reported": _round(current),
        "current_text": kpi.text(current),
        "current_weekly_mean": _round(weekly_mean),
        "deviation": _round(deviation),
        "deviation_text": kpi.delta_text(current - baseline),
        "zscore": round(zscore, 2),
        "zscore_text": fmt.number(zscore, 1),
        "zscore_week": zscore_week,
        "zscore_week_text": fmt.week(zscore_week),
        "zscore_max": round(zscore_max, 2),
        "zscore_max_text": fmt.number(zscore_max, 1),
        "baseline_window": {"week_from": window[0], "week_to": window[1],
                            "text": fmt.week_range(window[0], window[1])},
        "baseline_window_text": fmt.week_range(window[0], window[1]),
        "current_window": {"week_from": start, "week_to": end,
                           "text": fmt.week_range(start, end)},
        "current_window_text": fmt.week_range(start, end),
        "denominator": _round(denominator),
        "target_text": kpi.text(kpi.target),
        "warning_text": kpi.text(kpi.warning),
    }


def _countable(quantity: float) -> float:
    """Abgeleitete Mengen sind ganze Vorgaenge.

    "712,4 verlorene Angebote" gibt es nicht. Wer die ausgewiesene Menge mit dem
    ausgewiesenen Satz multipliziert, muss auf den ausgewiesenen Betrag kommen --
    sonst ist die Rechenkette nicht aufklappbar, sondern nur dekorativ. Gerundet
    wird deshalb die *Menge*, nie ein Quotient vor seiner Division (Rechenregel R5).
    """
    return float(round(quantity))


#: Hinweis an jeder Rechenkette: Der Betrag entsteht aus der gerundeten Menge und
#: dem Satz aus dem Datensatz. Der Satz selbst ist auf Cent gerundet ausgewiesen.
ROUNDING_NOTE = ("Die Menge ist auf ganze Vorgänge gerundet, der Satz je Vorgang auf Cent. "
                 "Menge × Satz ergibt genau den ausgewiesenen Betrag.")


def _market_filter(filters: dict) -> dict | None:
    return {"market": filters["market"]} if "market" in filters else None


def _impact_for(dataset: an.Dataset, kpi_key: str, filters: dict, start: int, end: int,
                baseline: float, current: float) -> dict:
    """Wirkungsschätzung mit jedem Parameter und jeder Zwischengröße.

    Grundmuster: betroffene Menge x Abweichung x Satz je Vorgang. Jeder Satz
    stammt aus additiven Feldern desselben Datensatzes, nicht aus einer Annahme
    von außen.
    """
    chain: list[dict] = []

    if kpi_key == "quote_win_rate":
        win_kpi = an.KPIS["quote_win_rate"]
        decided = an.field_sum(dataset, "facts_weekly", "quotes_decided", filters, start, end)
        lost = _countable(decided * (baseline - current))
        margin_per_order = round(an.derived_rate(dataset, "contribution_margin_eur",
                                                 "orders_shipped", _market_filter(filters)), 2)
        euro = lost * margin_per_order
        chain = [
            an.chain_step("Entschiedene Angebote im Zeitraum", fmt.count(decided),
                          "facts_weekly: quotes_decided"),
            an.chain_step("Angebotserfolgsquote Vergleichsbasis", win_kpi.text(baseline),
                          "facts_weekly: quotes_won / quotes_decided"),
            an.chain_step("Angebotserfolgsquote im Zeitraum", win_kpi.text(current),
                          "facts_weekly: quotes_won / quotes_decided"),
            an.chain_step("Zusätzlich verlorene Angebote", fmt.count(lost),
                          "Entschiedene Angebote × Abweichung der Erfolgsquote"),
            an.chain_step("Deckungsbeitrag je Auftrag im Markt", fmt.euro(margin_per_order),
                          "facts_weekly: contribution_margin_eur / orders_shipped"),
            an.chain_step("Geschätzte Wirkung", fmt.euro(euro),
                          "Zusätzlich verlorene Angebote × Deckungsbeitrag je Auftrag"),
        ]
        return _impact(euro, lost, "zusätzlich verlorene Angebote", fmt.count(lost), chain,
                       "Bewertet ist der entgangene Deckungsbeitrag. Der Umsatzindex des "
                       "Markts fällt aus demselben Grund und wird nicht erneut gezählt.")

    if kpi_key == "quote_lead_time_h":
        quotes = an.field_sum(dataset, "facts_weekly", "quotes_sent", filters, start, end)
        extra_hours = quotes * (current - baseline)
        chain = [
            an.chain_step("Versendete Angebote im Zeitraum", fmt.count(quotes),
                          "facts_weekly: quotes_sent"),
            an.chain_step("Angebotsdurchlaufzeit Vergleichsbasis", fmt.hours(baseline),
                          "facts_weekly: stage1_inquiry_to_quote_hours / quotes_sent"),
            an.chain_step("Angebotsdurchlaufzeit im Zeitraum", fmt.hours(current),
                          "facts_weekly: stage1_inquiry_to_quote_hours / quotes_sent"),
            an.chain_step("Zusätzliche Wartezeit der Kunden", fmt.hours(extra_hours),
                          "Angebote × Abweichung der Durchlaufzeit"),
        ]
        return _impact(None, extra_hours, "zusätzliche Wartezeit der Kunden",
                       fmt.hours(extra_hours), chain,
                       "Die Wartezeit erzeugt im Datensatz keinen eigenen Kostenposten; "
                       "der entgangene Deckungsbeitrag steht beim auslösenden Befund und "
                       "wird nicht doppelt gezählt.",
                       hours=extra_hours)

    if kpi_key == "partner_activity_rate":
        activity_kpi = an.KPIS["partner_activity_rate"]
        accounts = an.field_sum(dataset, "facts_weekly", "key_accounts_assigned",
                                filters, start, end)
        missed = _countable(accounts * (baseline - current))
        partners = sorted({dataset.facts.at(row, "partner")
                           for row in an.filtered_rows(dataset.facts, filters)})
        table = dataset.capacity
        weeks_over = 0
        for row in table.rows:
            if table.at(row, "partner") not in partners:
                continue
            if not (start <= table.at(row, "week") <= end):
                continue
            contracted = float(table.at(row, "capacity_quotes_contracted"))
            if contracted and (float(table.at(row, "quotes_processed")) / contracted
                               > an.SCENARIO_BOTTLENECK_THRESHOLD):
                weeks_over += 1
        chain = [
            an.chain_step("Betreute Schlüsselkunden, Summe der Wochen", fmt.count(accounts),
                          "facts_weekly: key_accounts_assigned"),
            an.chain_step("Aktivitätsgrad Vergleichsbasis", activity_kpi.text(baseline),
                          "facts_weekly: key_accounts_active / key_accounts_assigned"),
            an.chain_step("Aktivitätsgrad im Zeitraum", activity_kpi.text(current),
                          "facts_weekly: key_accounts_active / key_accounts_assigned"),
            an.chain_step("Zusätzliche Kundenwochen ohne Kontakt", fmt.count(missed),
                          "Betreute Schlüsselkunden × Abweichung des Aktivitätsgrads"),
            an.chain_step("Wochen über der Engpassschwelle der Angebotskapazität",
                          fmt.count(weeks_over),
                          "capacity_weekly: quotes_processed / capacity_quotes_contracted"),
        ]
        return _impact(None, missed, "zusätzliche Kundenwochen ohne Kontakt",
                       fmt.count(missed), chain,
                       "Die Folgen des Engpasses für Angebote und Umsatz rechnet das "
                       "Wachstumsszenario; hier steht die ausgefallene Betreuung.",
                       weeks_over=weeks_over)

    if kpi_key == "otif_rate":
        otif_kpi = an.KPIS["otif_rate"]
        delivered = an.field_sum(dataset, "facts_weekly", "orders_delivered",
                                 filters, start, end)
        late = _countable(delivered * (baseline - current))
        chain = [
            an.chain_step("Gelieferte Aufträge im Zeitraum", fmt.count(delivered),
                          "facts_weekly: orders_delivered"),
            an.chain_step("Liefertreue Vergleichsbasis", otif_kpi.text(baseline),
                          "facts_weekly: orders_otif / orders_delivered"),
            an.chain_step("Liefertreue im Zeitraum", otif_kpi.text(current),
                          "facts_weekly: orders_otif / orders_delivered"),
            an.chain_step("Zusätzlich nicht termin- und mengengerecht geliefert",
                          fmt.count(late), "Aufträge × Abweichung der Liefertreue"),
        ]
        return _impact(None, late, "zusätzlich verspätete oder unvollständige Aufträge",
                       fmt.count(late), chain,
                       "Für eine verspätete Lieferung führt der Datensatz keinen Kostensatz; "
                       "die Wirkung steht deshalb in Aufträgen.")

    return _impact(None, 0.0, "", "", chain, "")


def _impact(euro: float | None, quantity: float, quantity_unit: str,
            quantity_text: str, chain: list[dict], note: str,
            hours: float | None = None, weeks_over: int | None = None) -> dict:
    block = {
        "euro": _round(euro),
        "euro_text": fmt.euro(euro) if euro is not None else "nicht in Euro bezifferbar",
        "euro_compact": fmt.euro_thousands(euro) if euro is not None else None,
        "quantity": _round(quantity),
        "quantity_unit": quantity_unit,
        "quantity_text": quantity_text,
        "chain": chain,
        "note": note,
        "rounding_note": ROUNDING_NOTE if euro is not None else None,
        "method": "Betroffene Menge × Abweichung × Satz je Vorgang aus dem Datensatz",
    }
    if hours is not None:
        block["hours"] = _round(hours)
        block["hours_text"] = fmt.hours(hours)
    if weeks_over is not None:
        block["weeks_over_warning"] = weeks_over
    return block


#: Die sechs Reklamationsgründe des Sortiments, in der Reihenfolge des Datensatzes.
COMPLAINT_REASONS = [
    ("complaint_lines_reason_dimension", "Maßabweichung"),
    ("complaint_lines_reason_surface", "Oberfläche/Beschichtung"),
    ("complaint_lines_reason_material", "Materialfehler"),
    ("complaint_lines_reason_transport", "Transportschaden"),
    ("complaint_lines_reason_wrong_item", "Falschlieferung"),
    ("complaint_lines_reason_other", "sonstiger Grund"),
]


def _item_finding(dataset: an.Dataset, item: an.ItemFinding,
                  cost_per_complaint: float) -> dict:
    kpi = an.KPIS[item.kpi_key]
    year = an.item_year_profile(dataset, item.kpi_key, item.product_group, item.article_id)
    start_week = dataset.weeks_of_period(item.start_period)[0]
    end_week = dataset.weeks_of_period(item.end_period)[1]
    label = f"Artikel {item.article_id} ({item.product_group})"

    # Häufigster Reklamationsgrund des Artikels im Befundzeitraum.
    table = dataset.assortment
    reasons = {field: 0.0 for field, _ in COMPLAINT_REASONS}
    for row in table.rows:
        if (table.at(row, "article_id") == item.article_id
                and table.at(row, "period") in item.periods):
            for field in reasons:
                reasons[field] += table.at(row, field)
    top_field = max(reasons, key=reasons.get)
    top_label = dict(COMPLAINT_REASONS)[top_field]
    top_share = reasons[top_field] / sum(reasons.values()) if sum(reasons.values()) else 0.0

    extra = _countable(item.lines_shipped * (item.value - item.peer_value))
    euro = extra * cost_per_complaint
    chain = [
        an.chain_step("Gelieferte Positionen des Artikels im Zeitraum",
                      fmt.count(item.lines_shipped), "assortment_periods: lines_shipped"),
        an.chain_step("Reklamationsquote des Artikels", kpi.text(item.value),
                      "assortment_periods: lines_complained / lines_shipped"),
        an.chain_step("Reklamationsquote der übrigen Artikel der Produktgruppe",
                      kpi.text(item.peer_value),
                      "assortment_periods: lines_complained / lines_shipped, Artikel ausgenommen"),
        an.chain_step("Zusätzlich reklamierte Positionen", fmt.count(extra),
                      "Gelieferte Positionen × Abweichung gegenüber den übrigen Artikeln"),
        an.chain_step("Kosten je bearbeiteter Reklamation", fmt.euro(cost_per_complaint),
                      "facts_weekly: complaint_cost_eur / complaints_closed"),
        an.chain_step("Geschätzte Wirkung", fmt.euro(euro),
                      "Zusätzliche Reklamationen × Kosten je Reklamation"),
    ]
    explanation = (
        f"Für {label} liegt die Reklamationsquote im Zeitraum "
        f"{fmt.week_range(start_week, end_week)} bei {kpi.text(item.value)} gegenüber "
        f"{kpi.text(item.peer_value)} bei den übrigen Artikeln derselben Produktgruppe "
        f"(z-Wert {fmt.number(item.zscore, 1)}). Über das ganze Jahr sind es "
        f"{kpi.text(year['value'])} gegenüber {kpi.text(year['peer_low'])} bis "
        f"{kpi.text(year['peer_high'])} der übrigen Artikel. Häufigster Grund ist "
        f"„{top_label}“ mit {fmt.percent(top_share, 0)} der Reklamationen. Der Vergleich "
        f"läuft gegen die übrigen Artikel derselben Produktgruppe, nicht gegen einen "
        f"Gesamtdurchschnitt — sonst würde der Gruppeneffekt als Fehler gemeldet. "
        f"[{an.GENERATED_MARK}]"
    )
    return {
        "id": "",
        "kpi": item.kpi_key,
        "kpi_label": kpi.label,
        "unit": kpi.unit,
        "entity": {"scope": "article", "article_id": item.article_id,
                   "product_group": item.product_group, "label": label,
                   "article_label": dataset.article_label.get(item.article_id, item.article_id)},
        "entity_label": label,
        "start_week": start_week,
        "start_week_text": fmt.week(start_week),
        "end_week": end_week,
        "end_week_text": fmt.week(end_week),
        "period_text": fmt.week_range(start_week, end_week),
        "start_period": item.start_period,
        "end_period": item.end_period,
        "lead_kpi_start_week": start_week,
        "lead_kpi_start_week_text": fmt.week(start_week),
        "start_week_source": kpi.label,
        "strength": {
            "baseline": _round(item.peer_value),
            "baseline_text": kpi.text(item.peer_value),
            "current": _round(item.value),
            "current_reported": _round(item.value),
            "current_text": kpi.text(item.value),
            "deviation": _round(item.value - item.peer_value),
            "deviation_text": kpi.delta_text(item.value - item.peer_value),
            "zscore": round(item.zscore, 2),
            "zscore_text": fmt.number(item.zscore, 1),
            "zscore_period": item.start_period,
            "zscore_period_text": fmt.week_range(
                *dataset.weeks_of_period(item.start_period)),
            "zscore_max": round(item.zscore_max, 2),
            "zscore_max_text": fmt.number(item.zscore_max, 1),
            "baseline_window_text": "übrige Artikel derselben Produktgruppe",
            # Die Vergleichsbasis ist eine Gruppe, kein Zeitfenster -- deshalb
            # ohne Wochenangabe, aber mit derselben Struktur wie bei Wochenbefunden.
            "baseline_window": {"week_from": None, "week_to": None,
                                "text": "übrige Artikel derselben Produktgruppe"},
            "current_window": {"week_from": start_week, "week_to": end_week,
                               "text": fmt.week_range(start_week, end_week)},
            "current_window_text": fmt.week_range(start_week, end_week),
            "denominator": _round(item.lines_shipped),
            "target_text": kpi.text(kpi.target),
            "warning_text": kpi.text(kpi.warning),
            "year_value": _round(year["value"]),
            "year_value_text": kpi.text(year["value"]),
            "year_peer_low_text": kpi.text(year["peer_low"]),
            "year_peer_high_text": kpi.text(year["peer_high"]),
            "year_by_article": year["by_article"],
            "top_reason": top_field,
            "top_reason_label": top_label,
            "top_reason_share_text": fmt.percent(top_share, 0),
        },
        "impact": _impact(euro, extra, "zusätzlich reklamierte Positionen",
                          fmt.count(extra), chain,
                          "Bewertet mit den Bearbeitungskosten je Reklamation aus dem Datensatz."),
        "department": kpi.department,
        "explanation": explanation,
        "proposed_action": an.PROPOSED_ACTIONS["complaint_rate_items"],
        "severity": an.severity_of(kpi, item.value, False),
        "status": "laufend",
        "resolved_from_week": None,
        "resolved_from_week_text": None,
        "evidence": [],
        "series": [{"week": point["week_to"], "period": point["period"],
                    "value": _round(point["value"]),
                    "peer_value": _round(point["peer_value"])}
                   for point in item.series],
        "baseline_window": {"week_from": None, "week_to": None,
                            "text": "übrige Artikel derselben Produktgruppe"},
        "follow_up_of": None,
        "follow_up_text": None,
    }


def _link_follow_ups(findings: list[dict], window: int = 2) -> None:
    """Folgeeffekte kennzeichnen (AK-09.1): selber Markt, Beginn innerhalb von
    zwei Wochen nach einem anderen Befund."""
    with_market = [entry for entry in findings if entry["entity"].get("market")]
    for later in with_market:
        candidates = [
            earlier for earlier in with_market
            if earlier is not later
            and earlier["entity"]["market"] == later["entity"]["market"]
            and 0 <= later["start_week"] - earlier["start_week"] <= window
            and (later["start_week"] > earlier["start_week"]
                 or earlier["id"] < later["id"])
        ]
        if not candidates:
            continue
        reference = min(candidates, key=lambda entry: entry["start_week"])
        offset = later["start_week"] - reference["start_week"]
        later["follow_up_of"] = reference["id"]
        later["follow_up_text"] = an.follow_up_text(reference["id"], offset)
        later["follow_up_offset_weeks"] = offset
        reference.setdefault("follow_ups", []).append(later["id"])


# --------------------------------------------------------------------------- #
# Effizienzpotenzial (US-10)
# --------------------------------------------------------------------------- #

def build_efficiency(dataset: an.Dataset) -> dict:
    weeks = len(dataset.weeks)
    inquiries = an.field_sum(dataset, "facts_weekly", "delivery_inquiries")
    complaints = an.field_sum(dataset, "facts_weekly", "complaints_closed")
    minutes_inquiry = float(dataset.parameters.get("minutes_per_delivery_inquiry", 0.0))
    minutes_complaint = float(dataset.parameters.get("minutes_per_complaint", 0.0))
    positions = [
        {
            "label": "Lieferterminanfragen von Kunden",
            "quantity_per_week": _round(inquiries / weeks),
            "quantity_per_week_text": fmt.count(inquiries / weeks),
            "minutes_per_case": minutes_inquiry,
            "minutes_per_case_text": (f"Annahme: {fmt.number(minutes_inquiry, 0)}"
                                      f"{fmt.NNBSP}Minuten je Vorgang"),
            "hours_per_week": _round(inquiries / weeks * minutes_inquiry / 60.0),
            "hours_per_week_text": fmt.hours(inquiries / weeks * minutes_inquiry / 60.0),
            "source": "facts_weekly: delivery_inquiries · parameters: minutes_per_delivery_inquiry",
        },
        {
            "label": "Bearbeitete Reklamationspositionen",
            "quantity_per_week": _round(complaints / weeks),
            "quantity_per_week_text": fmt.count(complaints / weeks),
            "minutes_per_case": minutes_complaint,
            "minutes_per_case_text": (f"Annahme: {fmt.number(minutes_complaint, 0)}"
                                      f"{fmt.NNBSP}Minuten je Vorgang"),
            "hours_per_week": _round(complaints / weeks * minutes_complaint / 60.0),
            "hours_per_week_text": fmt.hours(complaints / weeks * minutes_complaint / 60.0),
            "source": "facts_weekly: complaints_closed · parameters: minutes_per_complaint",
        },
    ]
    total_hours = sum(position["hours_per_week"] for position in positions)
    return {
        "positions": positions,
        "total_hours_per_week": _round(total_hours),
        "total_hours_per_week_text": fmt.hours(total_hours),
        "formula": "Menge je Woche × Minuten je Vorgang ÷ 60",
        "label": "Abschätzung, keine ausgewiesene Einsparung",
        "notice": f"[{an.GENERATED_MARK}]",
    }


# --------------------------------------------------------------------------- #
# Maßnahmen (US-11 bis US-13)
# --------------------------------------------------------------------------- #

PHASES = ["Anforderung", "Konzept", "Test/Pilot", "Roll-out", "Bewertung"]


def _phase(name: str, artefact: str, gate: str, start_week: int, due_week: int,
           state: str) -> dict:
    return {
        "name": name,
        "artefact": artefact,
        "release_criterion": gate,
        "start_week": start_week,
        "start_week_text": fmt.week_planned(start_week),
        "due_week": due_week,
        "due_week_text": fmt.week_planned(due_week),
        "state": state,
    }


def build_measures(dataset: an.Dataset, findings: list[dict]) -> list[dict]:
    last_week = dataset.weeks[-1]
    win = _find(findings, "quote_win_rate")
    otif = _find(findings, "otif_rate")
    lead = _find(findings, "quote_lead_time_h")
    win_kpi = an.KPIS["quote_win_rate"]
    otif_kpi = an.KPIS["otif_rate"]

    # -- laufende Maßnahme: Angebotserfolgsquote SE ------------------------- #
    start = win["start_week"]
    running = {
        "id": "M-01",
        "title": f"Angebotserfolgsquote im Markt {win['entity']['market']} zurückgewinnen",
        "finding_id": win["id"],
        "also_affected": [lead["id"]] if lead else [],
        "also_affected_departments": [lead["department"]] if lead else [],
        "owner": "Vertriebsleitung Nordeuropa",
        "department": win["department"],
        "entity_label": win["entity_label"],
        "target_kpi": "quote_win_rate",
        "target_kpi_label": win_kpi.label,
        "target_value": win_kpi.target,
        "target_value_text": win_kpi.text(win_kpi.target),
        "current_value_text": win["strength"]["current_text"],
        "start_week": start,
        "start_week_text": fmt.week(start),
        "status": "offen",
        "current_phase": PHASES[0],
        "completed_phases": 0,
        "progress_text": f"{fmt.count(0)} von {fmt.count(len(PHASES))}",
        "phases": [
            _phase(PHASES[0],
                   "Zielkennzahl und Zielwert schriftlich festgehalten",
                   f"Zielkennzahl benannt und Zielwert {win_kpi.text(win_kpi.target)} bestätigt",
                   start + 1, start + 2, "offen"),
            _phase(PHASES[1],
                   "Drei bewertete Optionen mit Aufwand und Risiko",
                   "Optionen bewertet und eine Empfehlung ausgesprochen",
                   start + 3, start + 5, "offen"),
            _phase(PHASES[2],
                   "Zielvereinbarung und Schulung mit der Vertretung, Pilot über vier Wochen",
                   "Pilotumfang und Messzeitraum vereinbart, Messung liegt vor",
                   start + 6, start + 10, "offen"),
            _phase(PHASES[3],
                   "Zielvereinbarung in Kraft, Wochengespräch etabliert",
                   "Umfang und Termin bestätigt, alle Angebote im neuen Ablauf",
                   start + 11, start + 14, "offen"),
            _phase(PHASES[4],
                   "Vorher-nachher-Vergleich der Angebotserfolgsquote",
                   "Acht Wochen gemessen und dem Zielwert gegenübergestellt",
                   start + 15, start + 22, "offen"),
        ],
        "notice": f"[{an.GENERATED_MARK}]",
    }

    # -- abgeschlossene Maßnahme: Liefertreue PL ----------------------------- #
    # Entscheidung DE-4: Vergleichsbasis sind zwei klar abgegrenzte Fenster,
    # nicht das Jahresmittel -- das trägt die behobene Störung mit sich.
    before_from, before_to = otif["start_week"], otif["end_week"]
    after_from, after_to = otif["end_week"] + 1, last_week
    filters = {"market": {otif["entity"]["market"]}}
    before_value, _ = an.window_value(dataset, otif_kpi, before_from, before_to, filters)
    after_value, _ = an.window_value(dataset, otif_kpi, after_from, after_to, filters)
    year_value, _ = an.kpi_value(dataset, otif_kpi, filters)
    change = after_value - before_value
    effective = after_from
    relation = "über" if otif_kpi.direction == an.HIGHER else "unter"

    completed = {
        "id": "M-02",
        "title": f"Liefertreue im Markt {otif['entity']['market']} zurückführen",
        "finding_id": otif["id"],
        "also_affected": [],
        "also_affected_departments": [],
        "owner": "Auftragsabwicklung und Logistik",
        "department": otif["department"],
        "entity_label": otif["entity_label"],
        "target_kpi": "otif_rate",
        "target_kpi_label": otif_kpi.label,
        "target_value": otif_kpi.target,
        "target_value_text": otif_kpi.text(otif_kpi.target),
        "current_value_text": otif_kpi.text(after_value),
        "start_week": before_from,
        "start_week_text": fmt.week(before_from),
        "status": "abgeschlossen",
        "current_phase": PHASES[4],
        "completed_phases": 5,
        "progress_text": f"{fmt.count(5)} von {fmt.count(len(PHASES))}",
        "phases": [
            _phase(PHASES[0], "Zielkennzahl und Zielwert schriftlich festgehalten",
                   f"Zielwert {otif_kpi.text(otif_kpi.target)} bestätigt",
                   before_from + 1, before_from + 2, "erledigt"),
            _phase(PHASES[1], "Lieferausfälle ausgewertet, Versandplanung neu getaktet",
                   "Ursachenbild und neue Versandplanung abgestimmt",
                   before_from + 2, before_from + 4, "erledigt"),
            _phase(PHASES[2], "Pilot mit festen Versandtagen über zwei Wochen",
                   "Pilotumfang und Messzeitraum vereinbart, Messung liegt vor",
                   before_from + 4, before_from + 6, "erledigt"),
            _phase(PHASES[3], "Feste Versandtage für alle Aufträge des Markts",
                   "Umfang und Termin bestätigt, Umstellung abgeschlossen",
                   before_from + 6, before_to, "erledigt"),
            _phase(PHASES[4], "Vorher-nachher-Vergleich der Liefertreue",
                   "Zwei abgegrenzte Zeiträume gemessen und gegenübergestellt",
                   effective, after_to, "erledigt"),
        ],
        "evaluation": {
            "before_window": {"week_from": before_from, "week_to": before_to,
                              "text": fmt.week_range(before_from, before_to)},
            "after_window": {"week_from": after_from, "week_to": after_to,
                             "text": fmt.week_range(after_from, after_to)},
            "before_value": _round(before_value),
            "before_text": otif_kpi.text(before_value),
            "after_value": _round(after_value),
            "after_text": otif_kpi.text(after_value),
            "change": _round(change),
            "change_text": otif_kpi.delta_text(change),
            "target_value": otif_kpi.target,
            "target_text": otif_kpi.text(otif_kpi.target),
            "year_value": _round(year_value),
            "year_text": otif_kpi.text(year_value),
            "effective_week": effective,
            "effective_week_text": fmt.week(effective),
            "relation_to_target": relation,
            "after_text_with_window": (f"{otif_kpi.text(after_value)} seit "
                                       f"{fmt.week(after_from)}"),
            "window_note": (
                "Als Vergleichsbasis dient ausdrücklich der Zeitraum ab "
                f"{fmt.week(after_from)} und nicht das Jahresmittel von "
                f"{otif_kpi.text(year_value)}: Das Jahresmittel trägt die behobene "
                "Störung mit sich und würde die Wirkung verdecken."),
            "conclusion": (
                f"Die Liefertreue liegt seit {fmt.week(after_from)} bei "
                f"{otif_kpi.text(after_value)} gegenüber {otif_kpi.text(before_value)} im "
                f"Störungszeitraum {fmt.week_range(before_from, before_to)} und damit wieder "
                f"{relation} dem Zielwert von {otif_kpi.text(otif_kpi.target)}. Der Vergleich "
                f"ist zeitlich und nicht kausal; eine hochgerechnete Einsparung wird nicht "
                f"ausgewiesen. [{an.GENERATED_MARK}]"),
        },
        "notice": f"[{an.GENERATED_MARK}]",
    }
    return [running, completed]


def _find(findings: list[dict], kpi_key: str) -> dict:
    for finding in findings:
        if finding["kpi"] == kpi_key:
            return finding
    raise LookupError(f"Kein Befund zur Kennzahl '{kpi_key}' gefunden")


# --------------------------------------------------------------------------- #
# Szenario (US-14, US-15)
# --------------------------------------------------------------------------- #

DEFAULT_SCENARIO_VOLUME = 0.20
DEFAULT_SCENARIO_QUARTER = 1
#: Zielauslastung der Angebotskapazität; darüber wird es eng, über der
#: Engpassschwelle (92 %) entsteht eine Engpasswoche.
TARGET_UTILIZATION = 0.85


def build_scenario(dataset: an.Dataset) -> dict:
    base_case = an.scenario(dataset, 0.0, False)
    default_case = an.scenario(dataset, DEFAULT_SCENARIO_VOLUME, True,
                               DEFAULT_SCENARIO_QUARTER)
    default_without = an.scenario(dataset, DEFAULT_SCENARIO_VOLUME, False)

    reference_cases = [an.scenario_summary(an.scenario(dataset, step, False))
                       for step in an.SCENARIO_VOLUME_STEPS]
    for step in (0.0, 0.20, 0.40):
        for quarter in (1, 2, 3, 4):
            reference_cases.append(
                an.scenario_summary(an.scenario(dataset, step, True, quarter)))

    capacity = float(dataset.parameters.get("subsidiary_capacity_quotes_per_week", 0.0))
    share = float(dataset.parameters.get("subsidiary_volume_share", 0.0))
    sources = an.scenario_sources(dataset)
    critical = an.critical_agency(base_case, sources)
    return {
        "formula": an.SCENARIO_FORMULA,
        "formula_note": "Modellrechnung, keine Prognose (AK-14.3).",
        "bottleneck_threshold": an.SCENARIO_BOTTLENECK_THRESHOLD,
        "bottleneck_threshold_text": fmt.percent(an.SCENARIO_BOTTLENECK_THRESHOLD),
        "target_utilization": TARGET_UTILIZATION,
        "target_utilization_text": fmt.percent(TARGET_UTILIZATION),
        "volume_steps": an.SCENARIO_VOLUME_STEPS,
        "quarter_first_week": {str(key): value for key, value in an.QUARTER_FIRST_WEEK.items()},
        "subsidiary_key": an.SUBSIDIARY_KEY,
        "subsidiary_label": PARTNER_NAME.get(an.SUBSIDIARY_KEY, an.SUBSIDIARY_KEY),
        "subsidiary_capacity_quotes_per_week": capacity,
        "subsidiary_capacity_quotes_per_week_text": fmt.count(capacity),
        "subsidiary_volume_share": share,
        "subsidiary_volume_share_text": fmt.percent(share, 0),
        "subsidiary_source_partners": sources,
        "critical_partner": critical,
        "critical_partner_label": PARTNER_NAME.get(critical, critical),
        "base_case": {
            "volume_increase": 0.0,
            "per_partner": {
                partner: {
                    "weeks": block["weeks"],
                    "bottleneck_weeks": block["bottleneck_weeks"],
                    "bottleneck_week_count": block["bottleneck_week_count"],
                    "first_bottleneck_week": block["first_bottleneck_week"],
                    "max_utilization": block["max_utilization"],
                    "mean_utilization": block["mean_utilization"],
                    "label": PARTNER_NAME.get(partner, partner),
                }
                for partner, block in base_case["per_partner"].items()
            },
        },
        "default_case": {
            "volume_increase": DEFAULT_SCENARIO_VOLUME,
            "volume_increase_text": fmt.percent(DEFAULT_SCENARIO_VOLUME, 0),
            "expansion_quarter": DEFAULT_SCENARIO_QUARTER,
            "with_expansion": an.scenario_summary(default_case),
            "without_expansion": an.scenario_summary(default_without),
            "roadmap": an.roadmap_points(dataset, default_case),
        },
        "reference_cases": reference_cases,
    }


# --------------------------------------------------------------------------- #
# Entscheidungsvorlage (US-17, docs/SPEC.md Abschnitt 5)
# --------------------------------------------------------------------------- #

MATRIX_REASON_LIMIT = 110

OPTIONS = [
    {
        "id": "A",
        "title": "Preis- und Konditionsanpassung im betroffenen Markt",
        "description": ("Für neue Angebote im Markt gilt ein Nachlass von {concession_share} "
                        "auf den Listenpreis; im Befundzeitraum hätte das {concession_cost} "
                        "Deckungsbeitrag gekostet."),
        "effort_weeks": 4,
    },
    {
        "id": "B",
        "title": "Eigene Vertriebspräsenz in Skandinavien aufbauen",
        "description": ("Eine eigene Tochtergesellschaft übernimmt die Märkte der beiden "
                        "Vertretungen; einmalig {setup_cost}, laufend {running_cost} je Jahr."),
        "effort_weeks": 30,
    },
    {
        "id": "C",
        "title": "Bestehende Vertretung stärken: Zielvereinbarung und Schulung",
        "description": ("Die Vertretung erhält eine Zielvereinbarung zur Erfolgsquote, eine "
                        "Produkt- und Angebotsschulung und ein festes Wochengespräch."),
        "effort_weeks": 8,
    },
]

#: Bewertungsmatrix 3 x 4. Jeder Begründungssatz höchstens 110 Zeichen (OP-17).
MATRIX = {
    "A": {
        "kosten": ("mittel", "Der Nachlass kostet laufend Deckungsbeitrag auf jedem neuen "
                             "Auftrag im Markt."),
        "risiko": ("mittel", "Der Wettbewerber kann nachziehen; ein Nachlass lässt sich "
                             "später kaum zurücknehmen."),
        "zeit_bis_wirkung": ("gering", "Neue Konditionen gelten nach rund vier Wochen für "
                                       "jedes neue Angebot."),
        "kundenwirkung": ("mittel", "Der Preis wird wettbewerbsfähig; Angebotszeit und "
                                    "Betreuung bleiben unverändert."),
    },
    "B": {
        "kosten": ("hoch", "Gründung, Personal und Übergabe kosten einmalig und laufend "
                           "deutlich mehr als eine Vertretung."),
        "risiko": ("hoch", "Die Kunden wechseln während der Übergabe den Ansprechpartner; "
                           "Wissen der Vertretung kann verloren gehen."),
        "zeit_bis_wirkung": ("hoch", "Gründung, Einstellung und Einarbeitung brauchen rund "
                                     "dreißig Wochen."),
        "kundenwirkung": ("hoch", "Eigene Präsenz mit Technik und Innendienst vor Ort, auch "
                                  "für das Wachstum in NO."),
    },
    "C": {
        "kosten": ("gering", "Schulung und Zielvereinbarung kosten wenig; die Provision "
                             "bleibt im bestehenden Rahmen."),
        "risiko": ("gering", "Der eingespielte Partner bleibt, die Kundenbeziehungen "
                             "bleiben unverändert."),
        "zeit_bis_wirkung": ("mittel", "Rund acht Wochen, bis Zielvereinbarung und Schulung "
                                       "abgeschlossen sind."),
        "kundenwirkung": ("mittel", "Schnellere Angebote und engere Betreuung; der "
                                    "Preisabstand zum Wettbewerber bleibt."),
    },
}

MATRIX_DIMENSIONS = [
    ("kosten", "Kosten (einmalig und laufend)"),
    ("risiko", "Risiko"),
    ("zeit_bis_wirkung", "Zeit bis zur Wirkung"),
    ("kundenwirkung", "Kundenwirkung"),
]


def _option_figures(dataset: an.Dataset, finding: dict) -> dict:
    """Zahlen, mit denen die Optionen beschrieben werden -- aus dem Datensatz."""
    filters = {"market": {finding["entity"]["market"]}}
    share = float(dataset.parameters.get("price_concession_share", 0.0))
    revenue = an.field_sum(dataset, "facts_weekly", "revenue_eur", filters,
                           finding["start_week"], finding["end_week"])
    setup = float(dataset.parameters.get("subsidiary_setup_cost_eur", 0.0))
    running = float(dataset.parameters.get("subsidiary_running_cost_eur_per_year", 0.0))
    concession = revenue * share
    return {
        "concession_share": fmt.percent(share, 0),
        "concession_revenue": fmt.euro_thousands(revenue),
        "concession_cost": fmt.euro_thousands(concession),
        "concession_cost_value": concession,
        "setup_cost": fmt.euro_thousands(setup),
        "running_cost": fmt.euro_thousands(running),
    }


def build_decision_paper(dataset: an.Dataset, findings: list[dict],
                         measures: list[dict], kpis: dict) -> dict:
    win = _find(findings, "quote_win_rate")
    lead = _find(findings, "quote_lead_time_h")
    measure = measures[0]
    win_kpi = an.KPIS["quote_win_rate"]
    lead_kpi = an.KPIS["quote_lead_time_h"]
    last_week = dataset.weeks[-1]
    market = win["entity"]["market"]
    figures = _option_figures(dataset, win)

    lost = win["impact"]["quantity_text"]
    decided = next((step["value"] for step in win["impact"]["chain"]
                    if step["label"].startswith("Entschiedene Angebote")), "")

    market_phrase = f"Markt {market}"
    situation = [
        (f"Im {market_phrase} ist die Angebotserfolgsquote der Vertretung seit "
         f"{win['start_week_text']} von {win['strength']['baseline_text']} auf "
         f"{win['strength']['current_text']} gefallen; im Markt ist ein lokaler "
         f"Wettbewerber aufgetreten."),
        (f"Seit {lead['start_week_text']} steigt im selben Markt die Angebotsdurchlaufzeit von "
         f"{lead['strength']['baseline_text']} auf {lead['strength']['current_text']}, weil "
         f"mehr Angebote nachverhandelt werden — {an.NO_CAUSALITY}."),
        (f"Von {decided} entschiedenen Angeboten gingen {lost} zusätzlich verloren; der "
         f"entgangene Deckungsbeitrag liegt bei {win['impact']['euro_text']}."),
    ]

    evaluation = []
    for option in OPTIONS:
        cells = {}
        for key, label in MATRIX_DIMENSIONS:
            rating, reason = MATRIX[option["id"]][key]
            reason = " ".join(reason.split())
            if len(reason) > MATRIX_REASON_LIMIT:
                raise ValueError(
                    f"Begründungssatz zu lang ({len(reason)} Zeichen, erlaubt "
                    f"{MATRIX_REASON_LIMIT}): {reason}")
            cells[key] = {"dimension": label, "rating": rating, "reason": reason}
        evaluation.append({"option": option["id"], "cells": cells})

    recommendation = (
        f"Empfohlen wird Option C: Die Stärkung der bestehenden Vertretung wirkt in "
        f"{fmt.count(OPTIONS[2]['effort_weeks'])} Wochen bei geringstem Risiko und soll die "
        f"Angebotserfolgsquote im {market_phrase} von {win['strength']['current_text']} auf "
        f"den Zielwert {win_kpi.text(win_kpi.target)} zurückführen; die "
        f"Angebotsdurchlaufzeit soll von {lead['strength']['current_text']} auf den Zielwert "
        f"{lead_kpi.text(lead_kpi.target)} sinken. Im Befundzeitraum gingen {lost} Angebote "
        f"zusätzlich verloren, entgangen sind {win['impact']['euro_text']} Deckungsbeitrag. "
        f"Der Preis dieser Entscheidung: Option C schließt den Preisabstand zum neuen "
        f"Wettbewerber nicht und schafft keine Kapazität für das Wachstum in NO — das "
        f"leistet nur Option B."
    )

    trigger = (
        f"Bleibt die Angebotserfolgsquote im {market_phrase} acht Wochen nach Abschluss der "
        f"Zielvereinbarung unter dem Zielwert von {win_kpi.text(win_kpi.target)}, wird "
        f"Option B vorbereitet."
    )

    next_steps = []
    for phase in measure["phases"][:4]:
        next_steps.append({
            "text": f"{phase['name']}: {phase['artefact']}",
            "owner": measure["owner"],
            "due_week": phase["due_week"],
            "due_week_text": phase["due_week_text"],
        })
    next_steps.append({
        "text": "Wirkung messen und dem Zielwert gegenüberstellen",
        "owner": measure["owner"],
        "due_week": measure["phases"][4]["due_week"],
        "due_week_text": measure["phases"][4]["due_week_text"],
    })

    return {
        "head": {
            "title": f"Entscheidungsvorlage: Angebotserfolgsquote im {market_phrase}",
            "reference": (f"Maßnahme {measure['id']} „{measure['title']}“ · "
                          f"auslösende Auffälligkeit {win['id']}"),
            "decision_need": ("Zu entscheiden ist, mit welchem der drei Wege die "
                              "Angebotserfolgsquote zurück auf den Zielwert gebracht wird."),
            "as_of": fmt.week(last_week),
            "as_of_text": f"Stand: {fmt.week(last_week)}",
            "notice": an.NOTICE,
            "market": market,
        },
        "situation": {"sentences": situation, "notice": f"[{an.GENERATED_MARK}]"},
        "options": [
            {**option,
             "description": option["description"].format(**figures),
             "effort_text": f"{fmt.count(option['effort_weeks'])} Wochen"}
            for option in OPTIONS
        ],
        "figures": figures,
        "evaluation": {
            "dimensions": [{"key": key, "label": label} for key, label in MATRIX_DIMENSIONS],
            "rows": evaluation,
            "reason_limit": MATRIX_REASON_LIMIT,
        },
        "recommendation": {
            "option": "C",
            "text": recommendation,
            "expected_win_rate_from_text": win["strength"]["current_text"],
            "expected_win_rate_to_text": win_kpi.text(win_kpi.target),
            "expected_lead_time_from_text": lead["strength"]["current_text"],
            "expected_lead_time_to_text": lead_kpi.text(lead_kpi.target),
            "lost_quotes_text": lost,
            "impact_text": win["impact"]["euro_text"],
        },
        "escalation_trigger": {
            "text": trigger,
            "measure": win_kpi.label,
            "threshold_text": win_kpi.text(win_kpi.target),
            "deadline_text": f"{fmt.count(8)} Wochen nach Abschluss",
            "consequence": "Option B wird vorbereitet",
            "owner": measure["owner"],
        },
        "next_steps": next_steps,
    }


# --------------------------------------------------------------------------- #
# Management-Report (US-16)
# --------------------------------------------------------------------------- #

REPORT_KPI_ORDER = [
    "quote_win_rate", "quote_lead_time_h", "revenue_index",
    "contribution_margin_per_order_eur", "otif_rate", "order_lead_time_d",
    "complaint_rate_lines", "complaint_processing_time_d",
    "delivery_inquiries_per_100_orders", "partner_activity_rate",
]


def build_report(dataset: an.Dataset, kpis: dict, findings: list[dict],
                 measures: list[dict]) -> dict:
    last_week = dataset.weeks[-1]
    red = [key for key in REPORT_KPI_ORDER if kpis[key]["status"] == "red"]
    yellow = [key for key in REPORT_KPI_ORDER if kpis[key]["status"] == "yellow"]
    running = [finding for finding in findings if finding["status"] == "laufend"]
    top = sorted(running, key=lambda entry: -(entry["impact"]["euro"] or 0.0))[:3]
    otif_measure = measures[1]

    green = [key for key in REPORT_KPI_ORDER if kpis[key]["status"] == "green"]

    def count_phrase(number: int, singular: str, plural: str) -> str:
        return f"{fmt.count(number)} {singular if number == 1 else plural}"

    situation = [
        (f"Stand {fmt.week(last_week)} erreichen {fmt.count(len(green))} von "
         f"{count_phrase(len(REPORT_KPI_ORDER), 'Kennzahl', 'Kennzahlen')} "
         f"ihren Zielwert, "
         f"{count_phrase(len(yellow), 'liegt', 'liegen')} zwischen Zielwert und "
         f"Warnschwelle und {count_phrase(len(red), 'verfehlt', 'verfehlen')} "
         f"die Warnschwelle."),
        (f"Die automatische Analyse führt {fmt.count(len(running))} laufende "
         f"Auffälligkeiten; die größte geschätzte Wirkung trägt {top[0]['id']} "
         f"({top[0]['kpi_label']}, {top[0]['entity_label']}) mit "
         f"{top[0]['impact']['euro_text']}."),
        (f"Die Liefertreue im {otif_measure['entity_label']} liegt nach der "
         f"abgeschlossenen Maßnahme bei "
         f"{otif_measure['evaluation']['after_text_with_window']} und damit "
         f"{otif_measure['evaluation']['relation_to_target']} dem "
         f"Zielwert von {otif_measure['evaluation']['target_text']}."),
    ]

    table = []
    for key in REPORT_KPI_ORDER:
        entry = kpis[key]
        table.append({
            "kpi": key,
            "label": entry["label"],
            "value_text": entry["text"],
            "target_text": entry["target_text"],
            "status": entry["status"],
            "status_label": entry["status_label"],
            "trend_text": entry["trend"]["text"],
            "trend_label": entry["trend"]["label"],
            "department": entry["department"],
        })

    return {
        "header": {
            "title": "Management-Report Internationaler Vertrieb",
            "notice": an.NOTICE,
            "as_of_text": f"Stand: {fmt.week(last_week)}",
            "filter_text": "Auswahl: alle Märkte, alle Vertriebswege, alle Partner",
        },
        "situation": {"sentences": situation, "notice": f"[{an.GENERATED_MARK}]"},
        "kpi_table": table,
        "top_actions": [
            {
                "id": finding["id"],
                "kpi_label": finding["kpi_label"],
                "entity_label": finding["entity_label"],
                "department": finding["department"],
                "impact_text": finding["impact"]["euro_text"],
                "quantity_text": finding["impact"]["quantity_text"],
                "quantity_unit": finding["impact"]["quantity_unit"],
                "severity": finding["severity"],
                "proposed_action": finding["proposed_action"],
            }
            for finding in top
        ],
        "measures_status": [
            {
                "id": measure["id"],
                "title": measure["title"],
                "status": measure["status"],
                "current_phase": measure["current_phase"],
                "progress_text": measure["progress_text"],
                "owner": measure["owner"],
            }
            for measure in measures
        ],
        "recommendation": {
            "text": (f"Empfohlen wird Option C der Entscheidungsvorlage: die bestehende "
                     f"Vertretung mit Zielvereinbarung und Schulung stärken, mit Eskalation "
                     f"auf Option B, wenn die Angebotserfolgsquote acht Wochen nach Abschluss "
                     f"unter {kpis['quote_win_rate']['target_text']} bleibt."),
        },
    }


# --------------------------------------------------------------------------- #
# Case Study: fertige Zeichenketten für jede Textposition (A12)
# --------------------------------------------------------------------------- #

def build_case_study(dataset: an.Dataset, kpis: dict, findings: list[dict],
                     measures: list[dict], decision: dict, report: dict,
                     scenario_block: dict, efficiency: dict) -> dict:
    win = _find(findings, "quote_win_rate")
    lead = _find(findings, "quote_lead_time_h")
    article = _find(findings, "complaint_rate_items")
    growth = _find(findings, "partner_activity_rate")
    otif = _find(findings, "otif_rate")
    measure = measures[1]["evaluation"]
    last_week = dataset.weeks[-1]

    critical = scenario_block["critical_partner"]
    default = scenario_block["default_case"]
    with_expansion = default["with_expansion"]["per_partner"][critical]
    without_expansion = default["without_expansion"]["per_partner"][critical]
    base_critical = scenario_block["base_case"]["per_partner"][critical]

    market_filter = {"market": {win["entity"]["market"]}}
    revenue_index, _ = an.window_value(dataset, an.KPIS["revenue_index"],
                                       win["start_week"], win["end_week"], market_filter)
    revenue_before, _ = an.window_value(dataset, an.KPIS["revenue_index"],
                                        win["baseline_window"]["week_from"],
                                        win["baseline_window"]["week_to"], market_filter)

    def step(finding: dict, prefix: str) -> str:
        return next((entry["value"] for entry in finding["impact"]["chain"]
                     if entry["label"].startswith(prefix)), "")

    def week_or_none(week: int | None) -> str:
        return fmt.week(week) if week else "keine"

    values = {
        # -- Rahmen --------------------------------------------------------- #
        "stand_kw": fmt.week(last_week),
        "zeitraum_datensatz": fmt.week_range(dataset.weeks[0], last_week),
        "anzahl_maerkte": fmt.count(len(dataset.facts.distinct("market"))),
        "anzahl_kennzahlen": fmt.count(len(kpis)),
        "anzahl_auffaelligkeiten": fmt.count(len(findings)),
        "anzahl_laufende_auffaelligkeiten": fmt.count(
            len([entry for entry in findings if entry["status"] == "laufend"])),

        # -- Gesamtbild ----------------------------------------------------- #
        "erfolgsquote_gesamt": kpis["quote_win_rate"]["text"],
        "erfolgsquote_ziel": kpis["quote_win_rate"]["target_text"],
        "erfolgsquote_warnschwelle": kpis["quote_win_rate"]["warning_text"],
        "angebotszeit_gesamt": kpis["quote_lead_time_h"]["text"],
        "liefertreue_gesamt": kpis["otif_rate"]["text"],
        "db_je_auftrag_gesamt": kpis["contribution_margin_per_order_eur"]["text"],
        "umsatzindex_gesamt": kpis["revenue_index"]["text"],

        # -- Fall 1: Angebotserfolgsquote im betroffenen Markt -------------- #
        "fall_markt": win["entity"]["market"],
        "fall_partner": PARTNER_NAME.get(win["entity"].get("partner"), ""),
        "fall_entitaet": win["entity_label"],
        "fall_beginn_kw": win["start_week_text"],
        "erfolgsquote_vorher": win["strength"]["baseline_text"],
        "erfolgsquote_nachher": win["strength"]["current_text"],
        "erfolgsquote_abweichung": win["strength"]["deviation_text"],
        "erfolgsquote_zwert": win["strength"]["zscore_text"],
        "erfolgsquote_vergleichsbasis": win["strength"]["baseline_window_text"],
        "angebote_entschieden": step(win, "Entschiedene Angebote"),
        "angebote_verloren": win["impact"]["quantity_text"],
        "db_je_auftrag_markt": step(win, "Deckungsbeitrag je Auftrag"),
        "wirkung_fall_euro": win["impact"]["euro_text"],
        "wirkung_fall_euro_kompakt": win["impact"]["euro_compact"],
        "umsatzindex_markt_vorher": an.KPIS["revenue_index"].text(revenue_before),
        "umsatzindex_markt_nachher": an.KPIS["revenue_index"].text(revenue_index),

        # -- Fall 2: Folgeeffekt Angebotsdurchlaufzeit ---------------------- #
        "angebotszeit_beginn_kw": lead["start_week_text"],
        "angebotszeit_vorher": lead["strength"]["baseline_text"],
        "angebotszeit_nachher": lead["strength"]["current_text"],
        "angebotszeit_abweichung": lead["strength"]["deviation_text"],
        "angebotszeit_ziel": kpis["quote_lead_time_h"]["target_text"],
        "angebotszeit_versatz_wochen": fmt.count(lead.get("follow_up_offset_weeks", 0)),
        "angebotszeit_wartestunden": lead["impact"]["quantity_text"],
        "folgeeffekt_referenz": lead["follow_up_of"] or "",

        # -- Fall 3: Reklamationen eines Artikels ---------------------------- #
        "artikel_id": article["entity"]["article_id"],
        "artikel_gruppe": article["entity"]["product_group"],
        "artikel_beginn_kw": article["start_week_text"],
        "artikel_quote": article["strength"]["year_value_text"],
        "artikel_quote_zeitraum": article["strength"]["current_text"],
        "artikel_vergleich_von": article["strength"]["year_peer_low_text"],
        "artikel_vergleich_bis": article["strength"]["year_peer_high_text"],
        "artikel_vergleich_zeitraum": article["strength"]["baseline_text"],
        "artikel_abweichung": article["strength"]["deviation_text"],
        "artikel_hauptgrund": article["strength"]["top_reason_label"],
        "artikel_hauptgrund_anteil": article["strength"]["top_reason_share_text"],
        "artikel_zusatzreklamationen": article["impact"]["quantity_text"],
        "artikel_wirkung_euro": article["impact"]["euro_text"],
        "kosten_je_reklamation": step(article, "Kosten je bearbeiteter Reklamation"),

        # -- Fall 4: Wachstumsengpass ---------------------------------------- #
        "wachstum_markt": growth["entity"]["market"],
        "wachstum_beginn_kw": growth["start_week_text"],
        "aktivitaet_vorher": growth["strength"]["baseline_text"],
        "aktivitaet_nachher": growth["strength"]["current_text"],
        "aktivitaet_ziel": kpis["partner_activity_rate"]["target_text"],
        "aktivitaet_warnschwelle": kpis["partner_activity_rate"]["warning_text"],
        "wachstum_angebotszeit_nachher": (growth["evidence"][0]["current_text"]
                                          if growth["evidence"] else ""),
        "wachstum_kundenwochen_ohne_kontakt": growth["impact"]["quantity_text"],
        "wachstum_wochen_ueber_engpass": fmt.count(
            growth["impact"].get("weeks_over_warning", 0)),

        # -- Fall 5: behobene Abweichung ------------------------------------- #
        "liefertreue_markt": otif["entity"]["market"],
        "liefertreue_zeitraum_vorher": measure["before_window"]["text"],
        "liefertreue_zeitraum_nachher": measure["after_window"]["text"],
        "liefertreue_vorher": measure["before_text"],
        "liefertreue_nachher": measure["after_text"],
        "liefertreue_nachher_mit_zeitraum": measure["after_text_with_window"],
        "liefertreue_veraenderung": measure["change_text"],
        "liefertreue_ziel": measure["target_text"],
        "liefertreue_jahreswert": measure["year_text"],
        "liefertreue_wirksam_ab": measure["effective_week_text"],

        # -- Entscheidungsvorlage -------------------------------------------- #
        "option_a_titel": decision["options"][0]["title"],
        "option_a_aufwand": decision["options"][0]["effort_text"],
        "option_b_titel": decision["options"][1]["title"],
        "option_b_aufwand": decision["options"][1]["effort_text"],
        "option_c_titel": decision["options"][2]["title"],
        "option_c_aufwand": decision["options"][2]["effort_text"],
        "option_a_nachlass": decision["figures"]["concession_share"],
        "option_a_kosten": decision["figures"]["concession_cost"],
        "option_b_einmalig": decision["figures"]["setup_cost"],
        "option_b_laufend": decision["figures"]["running_cost"],
        "empfehlung_option": decision["recommendation"]["option"],
        "empfehlung_effekt_von": decision["recommendation"]["expected_win_rate_from_text"],
        "empfehlung_effekt_bis": decision["recommendation"]["expected_win_rate_to_text"],
        "empfehlung_angebotszeit_von": decision["recommendation"]["expected_lead_time_from_text"],
        "empfehlung_angebotszeit_bis": decision["recommendation"]["expected_lead_time_to_text"],
        "eskalation_frist": decision["escalation_trigger"]["deadline_text"],
        "eskalation_schwelle": decision["escalation_trigger"]["threshold_text"],

        # -- Maßnahme --------------------------------------------------------- #
        "massnahme_phasen": fmt.count(len(PHASES)),
        "massnahme_fortschritt": measures[0]["progress_text"],
        "massnahme_ziel": measures[0]["target_value_text"],

        # -- Szenario ---------------------------------------------------------- #
        "szenario_partner": scenario_block["critical_partner_label"],
        "szenario_mehrvolumen": default["volume_increase_text"],
        "szenario_engpasswochen_ohne": fmt.count(without_expansion["bottleneck_week_count"]),
        "szenario_engpasswochen_mit": fmt.count(with_expansion["bottleneck_week_count"]),
        "szenario_erste_engpasswoche_ohne": week_or_none(without_expansion["first_bottleneck_week"]),
        "szenario_erste_engpasswoche_mit": week_or_none(with_expansion["first_bottleneck_week"]),
        "szenario_erweiterung_quartal": f"Q{default['expansion_quarter']}",
        "szenario_tochter_kapazitaet": scenario_block["subsidiary_capacity_quotes_per_week_text"],
        "szenario_verlagerung_anteil": scenario_block["subsidiary_volume_share_text"],
        "szenario_engpasswochen_ist": fmt.count(base_critical["bottleneck_week_count"]),
        "szenario_erste_engpasswoche_ist": week_or_none(base_critical["first_bottleneck_week"]),
        "szenario_spitzenauslastung_ist": fmt.percent(base_critical["max_utilization"]),

        # -- Effizienzpotenzial -------------------------------------------- #
        "effizienz_stunden_je_woche": efficiency["total_hours_per_week_text"],
        "effizienz_anfragen_je_woche": efficiency["positions"][0]["quantity_per_week_text"],
        "effizienz_reklamationen_je_woche": efficiency["positions"][1]["quantity_per_week_text"],
        "effizienz_minuten_anfrage": efficiency["positions"][0]["minutes_per_case_text"],
        "effizienz_minuten_reklamation": efficiency["positions"][1]["minutes_per_case_text"],

        # -- Regelwerk der automatischen Analyse ---------------------------- #
        "regel_baseline_wochen": fmt.count(dataset.baseline_weeks),
        "regel_zschwelle": fmt.number(dataset.zscore_threshold, 1),
        "regel_folgewochen": fmt.count(dataset.consecutive_weeks),
        "regel_mindeststichprobe": fmt.count(dataset.min_denominator),
        "regel_mindeststichprobe_artikel": fmt.count(dataset.min_denominator_item),
    }
    return {key: value for key, value in values.items() if value is not None}


# --------------------------------------------------------------------------- #
# Zusammenbau
# --------------------------------------------------------------------------- #

def build_metrics(dataset: an.Dataset, dataset_path: Path) -> dict:
    kpis = build_kpis(dataset)
    findings = build_findings(dataset)
    measures = build_measures(dataset, findings)
    scenario_block = build_scenario(dataset)
    efficiency = build_efficiency(dataset)
    decision = build_decision_paper(dataset, findings, measures, kpis)
    report = build_report(dataset, kpis, findings, measures)
    case_study = build_case_study(dataset, kpis, findings, measures, decision,
                                  report, scenario_block, efficiency)

    return {
        "meta": {
            "seed": dataset.meta.get("seed"),
            "weeks": [dataset.weeks[0], dataset.weeks[-1]],
            "notice": an.NOTICE,
            "generated_from": f"data/{dataset_path.name}",
            "generated_mark": an.GENERATED_MARK,
            "assortment_grain": dataset.meta.get("assortment_grain"),
            "assortment_period_weeks": dataset.period_weeks,
            "parameters": dataset.parameters,
            "detection_rule": {
                "flagged_series_weekly": SERIES_COUNTS.get("flagged_series_weekly"),
                "flagged_series_item": SERIES_COUNTS.get("flagged_series_item"),
                "flagged_series": SERIES_COUNTS.get("flagged_series"),
                "reported_findings": SERIES_COUNTS.get("reported_findings"),
                "wording": (
                    "Die Regel bewertet einzelne Zeitreihen; gemeldet werden Fälle. "
                    "Mehrere auffällige Kennzahlen derselben Einheit sind ein Fall — "
                    "deshalb ist die Zahl der auffälligen Zeitreihen größer als die "
                    "Zahl der gemeldeten Auffälligkeiten."),
                "baseline_weeks": dataset.baseline_weeks,
                "zscore_threshold": dataset.zscore_threshold,
                "consecutive_weeks": dataset.consecutive_weeks,
                "min_denominator": dataset.min_denominator,
                "min_denominator_item": dataset.min_denominator_item,
                "min_effect": {key: kpi.min_effect for key, kpi in an.KPIS.items()},
                "description": (
                    "Gleitende Vergleichsbasis über acht Wochen, bei Beginn einer "
                    "Auffälligkeit eingefroren; geprüft wird die Abweichung gegenüber der "
                    "Vergleichsgruppe derselben Woche. Ein Befund entsteht, wenn der z-Wert "
                    "die Schwelle erreicht, die Abweichung die fachliche Mindestgröße "
                    "erreicht und der Wert den Zielwert verletzt — und das zwei Zeitpunkte "
                    "in Folge."),
            },
        },
        "dimensions": {
            "markets": dataset.facts.distinct("market"),
            "channels": dataset.facts.distinct("channel"),
            "partners": dataset.facts.distinct("partner"),
            "weeks": dataset.weeks,
            "periods": dataset.assortment.distinct("period"),
            "articles": dataset.assortment.distinct("article_id"),
            "product_groups": [group for group in (
                "Standardmodule", "Formteile", "Verbindungselemente",
                "Sonderanfertigungen", "Zubehör")
                if group in set(dataset.article_group.values())],
            "labels": {
                "partners": PARTNER_NAME,
                "channels": CHANNEL_NAME,
            },
        },
        "kpis": kpis,
        "breakdowns": build_breakdowns(dataset),
        "findings": findings,
        "efficiency": efficiency,
        "measures": measures,
        "scenario": scenario_block,
        "decision_paper": decision,
        "report": report,
        "case_study": case_study,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default=str(ROOT / "data" / "dataset.json"))
    parser.add_argument("--out", default=str(ROOT / "data" / "metrics.json"))
    arguments = parser.parse_args(argv)

    # Entscheidung P3: Die Windows-Konsole laeuft unter cp1252 und bricht sonst
    # an einem Umlaut in einer Produktgruppe ab.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):  # pragma: no cover - alte Umgebungen
            pass

    dataset_path = Path(arguments.dataset)
    output_path = Path(arguments.out)
    dataset = an.load_dataset(dataset_path)
    metrics = build_metrics(dataset, dataset_path)

    output_path.write_text(
        json.dumps(metrics, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    size_kb = output_path.stat().st_size / 1024
    print(f"{output_path.name} geschrieben: {size_kb:.1f} KB")
    print(f"Kennzahlen: {len(metrics['kpis'])} | Auffaelligkeiten: "
          f"{len(metrics['findings'])} | Massnahmen: {len(metrics['measures'])} | "
          f"Case-Study-Werte: {len(metrics['case_study'])}")
    for finding in metrics["findings"]:
        print(f"  {finding['id']} {finding['kpi']:<32} {finding['entity_label']:<28} "
              f"ab KW {finding['start_week']:>2}  {finding['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
