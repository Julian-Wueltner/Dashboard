"""Auswertungslogik des Operations-Cockpits.

Was dieses Modul leistet
------------------------
* Kennzahlen als Quotient aus additiven Summen (Rechenregel R1, Entscheidung A3)
* Auffaelligkeitserkennung nach Entscheidung A6 (gleitende, eingefrorene Baseline,
  z-Score, fachliche Mindestabweichung, Zielwertpruefung, Zwei-Wochen-Regel)
* Wirkungsschaetzung mit offengelegter Rechenkette (US-07, Abgrenzungspunkt 8)
* Wachstumsszenario als offengelegte Modellrechnung (US-14, US-15)
* regelbasierte Textbausteine, sichtbar als "automatisch erstellt" (F5)

Was dieses Modul bewusst *nicht* tut
------------------------------------
* Es rechnet nichts aus ``orders_sample``. Die Auftragsstichprobe speist keine
  Kennzahl (Festlegung F4); sie dient ausschliesslich Detailansichten.
* Es formatiert keine Zahl selbst. Jede gemeldete Zeichenkette entsteht in
  ``data/formatting.py`` (Entscheidung A11).
* Es benutzt ausser der Standardbibliothek nichts (Entscheidung A1).

Warum die Erkennung so aussieht, wie sie aussieht
-------------------------------------------------
Eine rohe z-Score-Schwelle ueber alle Zeitreihen des Datensatzes meldet auf einem
Kontrolldatensatz ohne eingepflanzte Abweichungen rund hundert Treffer -- genau der
Vorwurf, den ein Operations-Leiter einer automatischen Analyse macht. Drei
Festlegungen bringen die Zahl auf null, ohne einen der fuenf echten Faelle zu
verlieren; jede ist in einem Satz erklaerbar:

1. **Ueberwacht wird nicht jede denkbare Filterkombination**, sondern je Kennzahl
   die Ebene, auf der sie gesteuert wird (``SCAN_PLAN``). Wer hundert Ebenen
   gleichzeitig prueft, findet zwangslaeufig Zufall.
2. **Verglichen wird gegen die Vergleichsgruppe derselben Woche** (das uebrige
   Geschaeft), nicht nur gegen die eigene Vergangenheit. Damit faellt heraus, was
   alle gleichzeitig trifft -- Saison, Peak, Feiertage. Genau dieselbe Logik
   verlangt die Artikelanalyse ("ein Artikel gegen die uebrigen Artikel
   derselben Produktgruppe"); sie gilt hier fuer alle Zeitreihen.
3. **Ein Befund muss statistisch auffaellig und fachlich relevant sein und den
   vereinbarten Zielwert verletzen.** Eine Abweichung, die die Kennzahl innerhalb
   ihres vereinbarten Korridors laesst, ist kein Handlungsbedarf, egal wie klar
   sie statistisch ist.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Callable, Iterable, Sequence

import formatting as fmt

# --------------------------------------------------------------------------- #
# Konstanten
# --------------------------------------------------------------------------- #

#: Hinweiszeile nach Festlegung F6 (harte Regel 3).
NOTICE = "Demo mit fiktiven Daten · eigene Initiative · erstellt mit KI-Unterstützung"

#: Kennzeichnung erzeugter Texte nach Festlegung F5.
GENERATED_MARK = "automatisch erstellt"

#: Pflichtsatz fuer Folgeeffekte (AK-09.3).
NO_CAUSALITY = "zeitlicher Zusammenhang, kein statistischer Ursachennachweis"

#: Mindestzahl weiterer Einheiten, damit eine Vergleichsgruppe gebildet wird.
#: Bei nur einer weiteren Einheit (zwei Partner gegeneinander) waere die
#: "Vergleichsgruppe" ein einzelner Partner -- dann vergleicht man zwei
#: Einzelfaelle und nicht eine Einheit gegen den Rest.
MIN_PEER_ENTITIES = 2

#: Mindestzahl an Wochen, aus denen eine Baseline gebildet werden darf.
#: Entscheidung A6 nennt acht Wochen; am Jahresanfang gibt es weniger. Vier Wochen
#: sind die Untergrenze, unterhalb derer eine Streuung nicht mehr schaetzbar ist.
MIN_BASELINE_WEEKS = 4


# --------------------------------------------------------------------------- #
# Datenzugriff
# --------------------------------------------------------------------------- #

class Table:
    """Eine Tabelle im Zeilen-Array-Format (NFR-05) mit Zugriff ueber Feldnamen."""

    __slots__ = ("name", "columns", "rows", "_index")

    def __init__(self, name: str, block: dict) -> None:
        self.name = name
        self.columns: list[str] = list(block["columns"])
        self.rows: list[list] = block["rows"]
        self._index = {column: position for position, column in enumerate(self.columns)}

    def at(self, row: Sequence, column: str):
        return row[self._index[column]]

    def position(self, column: str) -> int:
        return self._index[column]

    def has(self, column: str) -> bool:
        return column in self._index

    def distinct(self, column: str) -> list:
        position = self._index[column]
        return sorted({row[position] for row in self.rows})


class Dataset:
    """Der geladene Datensatz mit allen Tabellen und dem Parameterblock."""

    def __init__(self, raw: dict) -> None:
        self.raw = raw
        self.meta: dict = raw.get("meta", {})
        self.parameters: dict = raw.get("parameters", {})
        self.facts = Table("facts_weekly", raw["facts_weekly"])
        self.assortment = Table("assortment_periods", raw["assortment_periods"])
        self.capacity = Table("capacity_weekly", raw["capacity_weekly"])
        self.articles = Table("articles", raw["articles"])
        self.weeks: list[int] = self.facts.distinct("week")
        self.period_weeks: int = int(self.meta.get("assortment_period_weeks", 4))
        self.article_group = {
            self.articles.at(row, "article_id"): self.articles.at(row, "product_group")
            for row in self.articles.rows
        }
        self.article_label = {
            self.articles.at(row, "article_id"): self.articles.at(row, "article_label")
            for row in self.articles.rows
        }

    # -- Parameter mit sprechenden Namen ----------------------------------- #
    @property
    def baseline_weeks(self) -> int:
        return int(self.parameters.get("baseline_weeks", 8))

    @property
    def zscore_threshold(self) -> float:
        return float(self.parameters.get("zscore_threshold", 2.5))

    @property
    def consecutive_weeks(self) -> int:
        return int(self.parameters.get("consecutive_weeks", 2))

    @property
    def min_denominator(self) -> int:
        return int(self.parameters.get("min_denominator", 50))

    @property
    def min_denominator_item(self) -> int:
        return int(self.parameters.get("min_denominator_item", 30))

    def period_of_week(self, week: int) -> int:
        return (week - 1) // self.period_weeks + 1

    def weeks_of_period(self, period: int) -> tuple[int, int]:
        first = self.period_weeks * (period - 1) + 1
        return first, first + self.period_weeks - 1


def load_dataset(path) -> Dataset:
    import json
    from pathlib import Path

    with Path(path).open("r", encoding="utf-8") as handle:
        return Dataset(json.load(handle))


# --------------------------------------------------------------------------- #
# Kennzahlenkatalog (docs/KPI_DEFINITIONS.md Abschnitt 2 bis 4)
# --------------------------------------------------------------------------- #

HIGHER = "higher_is_better"
LOWER = "lower_is_better"


@dataclass(frozen=True)
class Kpi:
    """Eine Kennzahl als Quotient aus Summen additiver Felder (Rechenregel R1)."""

    key: str
    label: str
    unit: str
    numerator: tuple[str, ...]
    denominator: tuple[str, ...]
    direction: str
    target: float
    warning: float
    department: str
    table: str = "facts_weekly"
    factor: float = 1.0
    #: Felder, die vom Zaehler abgezogen werden (Kommissioniergenauigkeit).
    numerator_minus: tuple[str, ...] = ()
    #: Fachliche Mindestabweichung, ab der eine Abweichung berichtenswert ist.
    min_effect: float = 0.0
    #: Formatierer aus data/formatting.py und seine Optionen.
    formatter: str = "percent"
    formatter_options: dict = field(default_factory=dict)
    #: Kurzer Satz fuer den Erklaerungstext.
    subject: str = ""

    def compute(self, numerator_sum: float, denominator_sum: float) -> float | None:
        if not denominator_sum:
            return None
        return numerator_sum / denominator_sum * self.factor

    def text(self, value: float) -> str:
        return fmt.render(value, self.formatter, **self.formatter_options)

    @property
    def decimals(self) -> int:
        """Anzeigegenauigkeit der Kennzahl nach Rechenregel R5.

        Eine Kennzahl hat genau **eine** Genauigkeit -- auf der Kachel, im
        Befund, im Report und in der Case Study. Stuenden dort verschiedene
        Stellenzahlen, waere jede gemeldete Zahl eine Rundungsfrage.

        Warum das nicht ueberall eine Stelle sein kann: Die Beschaedigungsquote
        liegt bei 0,49 % und ihr Zielwert bei 0,50 %. Mit einer Nachkommastelle
        stuende auf der Kachel zweimal "0,5 %" -- und die gruene Ampel waere
        nicht mehr nachvollziehbar. Deshalb fuehren Kommissioniergenauigkeit,
        Beschaedigungsquote und Fehlerquote der Auftragsuebergabe zwei Stellen.
        """
        return int(self.formatter_options.get("decimals", 1))

    def delta_text(self, delta: float) -> str:
        """Unterschied zwischen zwei Auspraegungen, in der Einheit der Kennzahl."""
        if self.unit != "%":
            return self.text(abs(delta))
        return fmt.percentage_points(delta, self.decimals)

    def is_worse(self, value: float, reference: float) -> bool:
        return value > reference if self.direction == LOWER else value < reference

    def violates_target(self, value: float) -> bool:
        return self.is_worse(value, self.target)

    def violates_warning(self, value: float) -> bool:
        return self.is_worse(value, self.warning)

    def worsening(self, delta: float) -> float:
        """Wie viel schlechter der Wert gegenueber der Vergleichsbasis ist."""
        return delta if self.direction == LOWER else -delta


def _decimals(count: int = 1) -> dict:
    """Nachkommastellen der Anzeige nach Rechenregel R5."""
    return {"decimals": count}


KPIS: dict[str, Kpi] = {}


def _register(kpi: Kpi) -> Kpi:
    KPIS[kpi.key] = kpi
    return kpi


# -- Tabelle 1: Pflichtkennzahlen ----------------------------------------- #
_register(Kpi(
    key="quote_lead_time_h",
    label="Angebotsdurchlaufzeit (Anfrage bis Angebot)",
    unit="Stunden",
    numerator=("stage1_inquiry_to_quote_hours",),
    denominator=("quotes_sent",),
    direction=LOWER, target=24.0, warning=30.0,
    department="Vertriebsinnendienst", min_effect=3.0,
    formatter="hours", formatter_options=_decimals(1),
    subject="die Angebotsdurchlaufzeit von der Anfrage bis zum Angebot",
))
_register(Kpi(
    key="quote_win_rate",
    label="Angebotserfolgsquote",
    unit="%",
    numerator=("quotes_won",),
    denominator=("quotes_decided",),
    direction=HIGHER, target=0.32, warning=0.29,
    department="Vertrieb", min_effect=0.05,
    formatter="percent", formatter_options=_decimals(1),
    subject="die Angebotserfolgsquote",
))
_register(Kpi(
    key="order_lead_time_d",
    label="Auftragsdurchlaufzeit (Auftrag bis Versand)",
    unit="Tage",
    numerator=("stage3_order_entry_hours", "stage4_production_shipping_hours"),
    denominator=("orders_shipped",),
    factor=1.0 / 24.0,
    direction=LOWER, target=9.0, warning=11.0,
    department="Auftragsabwicklung", min_effect=0.75,
    formatter="days", formatter_options=_decimals(1),
    subject="die Auftragsdurchlaufzeit vom Auftrag bis zum Versand",
))
_register(Kpi(
    key="otif_rate",
    label="Liefertreue (Termin und Menge)",
    unit="%",
    numerator=("orders_otif",),
    denominator=("orders_delivered",),
    direction=HIGHER, target=0.95, warning=0.93,
    department="Logistik", min_effect=0.03,
    formatter="percent", formatter_options=_decimals(1),
    subject="die Liefertreue",
))
_register(Kpi(
    key="complaint_rate_lines",
    label="Reklamationsquote (Positionen)",
    unit="%",
    numerator=("lines_complained",),
    denominator=("lines_shipped",),
    direction=LOWER, target=0.012, warning=0.015,
    department="Qualität", min_effect=0.004,
    formatter="percent", formatter_options=_decimals(2),
    subject="die Reklamationsquote",
))
_register(Kpi(
    key="complaint_processing_time_d",
    label="Reklamationsbearbeitungszeit",
    unit="Tage",
    numerator=("stage5_complaint_hours",),
    denominator=("complaints_closed",),
    factor=1.0 / 24.0,
    direction=LOWER, target=5.0, warning=6.0,
    department="Qualität", min_effect=0.75,
    formatter="days", formatter_options=_decimals(1),
    subject="die Reklamationsbearbeitungszeit",
))
_register(Kpi(
    key="delivery_inquiries_per_100_orders",
    label="Lieferterminanfragen je 100 Aufträge",
    unit="Anfragen je 100 Aufträge",
    numerator=("delivery_inquiries",),
    denominator=("orders_placed",),
    factor=100.0,
    direction=LOWER, target=12.0, warning=15.0,
    department="Kundenservice", min_effect=2.5,
    formatter="per_hundred", formatter_options=_decimals(1),
    subject="die Zahl der Lieferterminanfragen",
))
_register(Kpi(
    key="contribution_margin_per_order_eur",
    label="Deckungsbeitrag je Auftrag",
    unit="€",
    numerator=("contribution_margin_eur",),
    denominator=("orders_shipped",),
    direction=HIGHER, target=1150.0, warning=1050.0,
    department="Controlling", min_effect=80.0,
    formatter="euro", formatter_options={"decimals": 0},
    subject="der Deckungsbeitrag je Auftrag",
))
_register(Kpi(
    key="revenue_index",
    label="Umsatz je Markt (Index zur Vorjahresbasis)",
    unit="Index",
    numerator=("revenue_eur",),
    denominator=("revenue_prior_year_eur",),
    factor=100.0,
    direction=HIGHER, target=100.0, warning=95.0,
    department="Vertrieb", min_effect=8.0,
    formatter="index", formatter_options=_decimals(1),
    subject="der Umsatzindex zur Vorjahresbasis",
))
_register(Kpi(
    key="partner_activity_rate",
    label="Aktivitätsgrad der Vertretungen",
    unit="%",
    numerator=("key_accounts_active",),
    denominator=("key_accounts_assigned",),
    direction=HIGHER, target=0.85, warning=0.80,
    department="Partnermanagement", min_effect=0.04,
    formatter="percent", formatter_options=_decimals(1),
    subject="der Aktivitätsgrad der Vertretung",
))

# -- Tabelle 2: ergaenzende Kennzahl auf Artikelebene ---------------------- #
_register(Kpi(
    key="complaint_rate_items",
    label="Reklamationsquote je Artikel",
    unit="%",
    numerator=("lines_complained",),
    denominator=("lines_shipped",),
    direction=LOWER, target=0.012, warning=0.015,
    department="Qualität", min_effect=0.01,
    table="assortment_periods",
    formatter="percent", formatter_options=_decimals(2),
    subject="die Reklamationsquote des Artikels",
))

# -- Tabelle 3: Stufenkennzahlen des Vertriebsprozesses -------------------- #
_STAGES = [
    ("stage1_inquiry_to_quote_h", "Anfrage bis Angebot",
     "stage1_inquiry_to_quote_hours", "quotes_sent", 24.0, 30.0, "Vertriebsinnendienst", "Innendienst", 3.0),
    ("stage2_quote_to_order_h", "Angebot bis Auftrag",
     "stage2_quote_to_order_hours", "quotes_won", 240.0, 288.0, "Vertrieb", "Vertrieb", 24.0),
    ("stage3_order_entry_h", "Auftragserfassung",
     "stage3_order_entry_hours", "orders_shipped", 24.0, 48.0, "Vertriebsinnendienst", "Innendienst", 2.0),
    ("stage4_production_shipping_h", "Fertigung und Versand",
     "stage4_production_shipping_hours", "orders_shipped", 192.0, 216.0, "Auftragsabwicklung", "Werk", 12.0),
    ("stage5_complaint_h", "After-Sales",
     "stage5_complaint_hours", "complaints_closed", 120.0, 144.0, "Qualität", "Qualität", 12.0),
]

#: Verantwortlicher im Vertriebsprozess je Stufe (US-04).
STAGE_OWNER: dict[str, str] = {}

for _key, _label, _num, _den, _target, _warning, _dept, _owner, _effect in _STAGES:
    STAGE_OWNER[_key] = _owner
    _register(Kpi(
        key=_key, label=_label, unit="Stunden",
        numerator=(_num,), denominator=(_den,),
        direction=LOWER, target=_target, warning=_warning,
        department=_dept, min_effect=_effect,
        formatter="hours", formatter_options=_decimals(1),
        subject=f"die Prozessstufe „{_label}“",
    ))

#: Die Stufenkennzahlen sind eine Zerlegung von Angebots-, Auftragsdurchlaufzeit
#: und Reklamationsbearbeitungszeit. Sie werden deshalb *nicht* getrennt
#: ueberwacht -- sonst erschiene derselbe Sachverhalt zweimal in der Liste der
#: Auffaelligkeiten.
STAGE_KEYS = tuple(entry[0] for entry in _STAGES)


# --------------------------------------------------------------------------- #
# Aggregation: Quotient aus Summen (Rechenregel R1)
# --------------------------------------------------------------------------- #

#: Welche Dimension aus welcher Spalte kommt.
DIMENSION_COLUMN = {
    "market": "market",
    "channel": "channel",
    "partner": "partner",
}


def sum_fields(table: Table, rows: Iterable[Sequence], fields: Sequence[str]) -> float:
    positions = [table.position(name) for name in fields]
    return sum(row[position] for row in rows for position in positions)


def aggregate(table: Table, rows: Iterable[Sequence], kpi: Kpi) -> tuple[float, float]:
    """Zaehler- und Nennersumme einer Kennzahl ueber die uebergebenen Zeilen."""
    rows = list(rows)
    numerator = sum_fields(table, rows, kpi.numerator)
    if kpi.numerator_minus:
        numerator -= sum_fields(table, rows, kpi.numerator_minus)
    denominator = sum_fields(table, rows, kpi.denominator)
    return numerator, denominator


def table_for(dataset: Dataset, kpi: Kpi) -> Table:
    return {
        "facts_weekly": dataset.facts,
        "assortment_periods": dataset.assortment,
        "capacity_weekly": dataset.capacity,
    }[kpi.table]


def filtered_rows(table: Table, filters: dict | None) -> list[Sequence]:
    if not filters:
        return table.rows
    checks = [(table.position(column), values)
              for column, values in filters.items() if table.has(column)]
    if not checks:
        return table.rows
    return [row for row in table.rows
            if all(row[position] in values for position, values in checks)]


def kpi_value(dataset: Dataset, kpi: Kpi, filters: dict | None = None) -> tuple[float | None, float]:
    """Wert und Nenner einer Kennzahl fuer die gefilterte Auswahl."""
    table = table_for(dataset, kpi)
    numerator, denominator = aggregate(table, filtered_rows(table, filters), kpi)
    return kpi.compute(numerator, denominator), denominator


def weekly_sums(dataset: Dataset, kpi: Kpi, group: Callable[[Table, Sequence], tuple] | None = None,
                filters: dict | None = None) -> dict:
    """Zaehler- und Nennersummen je (Gruppe, Woche).

    Fuer ``assortment_periods`` tritt die Periode an die Stelle der Woche
    (Entscheidung OP-1); die Zeitachse heisst in beiden Faellen ``period``.
    """
    table = table_for(dataset, kpi)
    time_column = "week" if table.has("week") else "period"
    time_position = table.position(time_column)
    result: dict = {}
    for row in filtered_rows(table, filters):
        key = (group(table, row) if group else ("gesamt",), row[time_position])
        entry = result.setdefault(key, [0.0, 0.0])
        entry[0] += sum(row[table.position(name)] for name in kpi.numerator)
        if kpi.numerator_minus:
            entry[0] -= sum(row[table.position(name)] for name in kpi.numerator_minus)
        entry[1] += sum(row[table.position(name)] for name in kpi.denominator)
    return result


def series_of(dataset: Dataset, kpi: Kpi, filters: dict | None = None) -> list[dict]:
    """Wochenreihe einer Kennzahl als Liste ``{"week": w, "value": v}``."""
    sums = weekly_sums(dataset, kpi, filters=filters)
    points = []
    for (_, time), (numerator, denominator) in sorted(sums.items(), key=lambda item: item[0][1]):
        value = kpi.compute(numerator, denominator) if denominator >= dataset.min_denominator else None
        points.append({"week": time, "value": value})
    return points


# --------------------------------------------------------------------------- #
# Ampel (F1) und Trend (F3)
# --------------------------------------------------------------------------- #

def traffic_light(kpi: Kpi, value: float | None, denominator: float,
                  minimum: int) -> str:
    """gruen / gelb / rot / grau nach Festlegung F1 und Rechenregel R3."""
    if value is None or denominator < minimum:
        return "grey"
    if not kpi.is_worse(value, kpi.target):
        return "green"
    if kpi.is_worse(value, kpi.warning):
        return "red"
    return "yellow"


TRAFFIC_LIGHT_LABEL = {
    "green": "Ziel erreicht",
    "yellow": "beobachten",
    "red": "Handlungsbedarf",
    "grey": "zu wenig Daten",
}


def trend(kpi: Kpi, points: Sequence[dict], window: int = 4) -> dict:
    """Vergleich der letzten vier Wochen gegen die vier Wochen davor (F3)."""
    values = [point["value"] for point in points if point["value"] is not None]
    if len(values) < 2 * window:
        return {"delta": None, "text": "kein Vergleich möglich", "label": "kein Vergleich möglich"}
    recent = statistics.fmean(values[-window:])
    earlier = statistics.fmean(values[-2 * window:-window])
    delta = recent - earlier
    is_rate = kpi.unit == "%"
    if is_rate:
        unchanged = abs(delta) < 0.003
        text = fmt.percentage_points(delta)
    else:
        relative = delta / earlier if earlier else 0.0
        unchanged = abs(relative) < 0.01
        text = fmt.percent(relative, 1, signed=relative > 0)
    if unchanged:
        label = "unverändert"
    elif kpi.worsening(delta) > 0:
        label = "schlechter"
    else:
        label = "besser"
    return {"delta": delta, "text": text, "label": label}


# --------------------------------------------------------------------------- #
# Auffaelligkeitserkennung (Entscheidung A6)
# --------------------------------------------------------------------------- #

@dataclass
class WeekFlag:
    week: int
    value: float
    baseline: float
    zscore: float
    deviation: float


@dataclass
class RawFinding:
    kpi_key: str
    scope: str
    entity: tuple
    start: int
    end: int
    weeks: list[int]
    flags: dict
    series: list[dict]
    baseline_window: tuple[int, int]
    #: Vergleichsbasis als Quotient aus Summen über das Basisfenster (Regel R1).
    baseline_value: float
    #: Mittel der Wochenquoten im Befundfenster. **Nur intern**: Es ist die
    #: Bezugsgröße des z-Werts, weil der z-Wert die Streuung der Wochenwerte
    #: misst. Es darf nirgends angezeigt werden -- ein Mittel über Quoten ist
    #: keine Kennzahl (Entscheidung A3, Rechenregel R1).
    current_value: float
    #: Istwert als Quotient aus Summen über das Befundfenster. **Das** ist die
    #: Zahl für Befundkarte, Report, Entscheidungsvorlage und Case Study; sie
    #: stimmt deshalb mit jeder gefilterten Ansicht des Cockpits überein.
    current_reported: float
    denominator: float
    #: z-Wert je Zeitpunkt der Reihe, auch für nicht gemeldete Wochen. Damit kann
    #: ein Befund den z-Wert genau der Woche nennen, die er als Beginn ausweist.
    zscores: dict = field(default_factory=dict)


def _baseline(values: Sequence[float]) -> tuple[float, float]:
    return statistics.fmean(values), statistics.pstdev(values)


def detect(kpi: Kpi, times: Sequence[int], values: dict, denominators: dict,
           peers: dict, *, baseline_weeks: int, zscore_threshold: float,
           consecutive: int, min_denominator: float,
           use_peers: bool = True, use_zscore: bool = True,
           use_min_effect: bool = True, use_target: bool = True) -> list[list[WeekFlag]]:
    """Kern der Erkennungsregel A6 -- gibt die gemeldeten Läufe zurück.

    ``detect_with_trace`` liefert zusätzlich den z-Wert jedes Zeitpunkts.
    """
    runs, _ = detect_with_trace(
        kpi, times, values, denominators, peers,
        baseline_weeks=baseline_weeks, zscore_threshold=zscore_threshold,
        consecutive=consecutive, min_denominator=min_denominator,
        use_peers=use_peers, use_zscore=use_zscore,
        use_min_effect=use_min_effect, use_target=use_target)
    return runs


def detect_with_trace(kpi: Kpi, times: Sequence[int], values: dict, denominators: dict,
                      peers: dict, *, baseline_weeks: int, zscore_threshold: float,
                      consecutive: int, min_denominator: float,
                      use_peers: bool = True, use_zscore: bool = True,
                      use_min_effect: bool = True, use_target: bool = True
                      ) -> tuple[list[list[WeekFlag]], dict[int, float]]:
    """Kern der Erkennungsregel A6.

    Ablauf je Zeitpunkt:

    1. Nenner unter der Mindeststichprobe -> nicht bewertet (Regel R2).
    2. Die gepruefte Reihe ist die **Differenz zur Vergleichsgruppe derselben
       Woche**, sofern eine Vergleichsgruppe existiert. Was alle gleichzeitig
       trifft (Saison, Peak), faellt damit heraus.
    3. Vergleichsbasis sind die acht Zeitpunkte davor. Ist der Vorzeitpunkt
       bereits Teil einer laufenden Auffaelligkeit, bleibt die Basis
       **eingefroren**, damit sie nicht mitwandert und den Befund verschluckt.
    4. Ein Zeitpunkt ist auffaellig, wenn die Abweichung in die schlechtere
       Richtung zeigt, ihr z-Wert die Schwelle erreicht, sie die fachliche
       Mindestabweichung erreicht **und** der Wert den Zielwert verletzt.
    5. Gemeldet wird erst ab zwei aufeinanderfolgenden auffaelligen Zeitpunkten.

    Zweiter Rueckgabewert: der z-Wert jedes bewerteten Zeitpunkts, auch wenn er
    die fachliche Mindestabweichung verfehlt hat. Ein Befund, dessen Fall eine
    Woche vor der Leitkennzahl beginnt, kann damit den z-Wert genau seiner
    Beginnwoche nennen statt den einer anderen.
    """
    adjusted: dict = {}
    for time in times:
        value = values.get(time)
        if value is None:
            adjusted[time] = None
        elif use_peers and peers.get(time) is not None:
            adjusted[time] = value - peers[time]
        else:
            adjusted[time] = value

    flags: dict[int, WeekFlag] = {}
    trace: dict[int, float] = {}
    frozen: tuple[float, float] | None = None
    for position, time in enumerate(times):
        if adjusted[time] is None or denominators.get(time, 0) < min_denominator:
            frozen = None
            continue
        previous_flagged = position > 0 and times[position - 1] in flags
        if previous_flagged and frozen is not None:
            mean, deviation = frozen
        else:
            history = [adjusted[earlier]
                       for earlier in times[max(0, position - baseline_weeks):position]
                       if adjusted[earlier] is not None
                       and denominators.get(earlier, 0) >= min_denominator]
            if len(history) < MIN_BASELINE_WEEKS:
                frozen = None
                continue
            mean, deviation = _baseline(history)
            frozen = (mean, deviation)

        worse = kpi.worsening(adjusted[time] - mean)
        zscore = worse / deviation if deviation > 0 else 0.0
        trace[time] = zscore
        relevant = worse >= kpi.min_effect
        beyond_target = kpi.violates_target(values[time])
        # Die vier Bedingungen sind einzeln abschaltbar, damit
        # tools/zeige_fehlalarme.py vorfuehren kann, wie viele Fehlalarme jede
        # weggelassene Bedingung kostet. Im Betrieb sind alle vier aktiv.
        if (worse > 0
                and (not use_zscore or zscore >= zscore_threshold)
                and (not use_min_effect or relevant)
                and (not use_target or beyond_target)):
            flags[time] = WeekFlag(time, values[time], mean, zscore, worse)
        else:
            frozen = None

    runs: list[list[WeekFlag]] = []
    for time in sorted(flags):
        if runs and runs[-1][-1].week == time - 1:
            runs[-1].append(flags[time])
        else:
            runs.append([flags[time]])
    return [run for run in runs if len(run) >= consecutive], trace


#: Welche Kennzahl auf welcher Ebene ueberwacht wird.
#:
#: Die Auswahl folgt der Frage "wo wird diese Kennzahl gesteuert?" und der
#: Filtermatrix in docs/KPI_DEFINITIONS.md Abschnitt 6. Die Angebotserfolgsquote
#: wird bewusst **nicht** auf reiner Marktebene ueberwacht, sondern je Markt und
#: Vertriebspartner: Gesteuert wird sie im Gespraech mit dem Partner. Damit bleibt
#: auf Marktebene die laengere Angebotsdurchlaufzeit als eigener Befund sichtbar,
#: statt im Erfolgsquotenbefund desselben Markts aufzugehen. Der Umsatzindex ist
#: eine Ergebnisgroesse und wird nicht als eigene Auffaelligkeit gemeldet -- er
#: faellt zwangslaeufig, wenn Angebote verloren gehen.
SCAN_PLAN: list[tuple[str, str]] = [
    ("quote_win_rate", "market_partner"),
    ("quote_win_rate", "partner"),
    ("quote_lead_time_h", "market"),
    ("order_lead_time_d", "partner"),
    ("otif_rate", "market"),
    ("complaint_rate_lines", "partner"),
    ("complaint_processing_time_d", "partner"),
    ("delivery_inquiries_per_100_orders", "market"),
    ("contribution_margin_per_order_eur", "market"),
    ("partner_activity_rate", "market"),
]

SCOPE_COLUMNS: dict[str, tuple[str, ...]] = {
    "gesamt": (),
    "market": ("market",),
    "channel": ("channel",),
    "partner": ("partner",),
    "market_partner": ("market", "partner"),
}


def _grouper(columns: Sequence[str]):
    if not columns:
        return lambda table, row: ("gesamt",)
    return lambda table, row: tuple(row[table.position(name)] for name in columns)


def scan_weekly(dataset: Dataset, *, rule: dict | None = None) -> list[RawFinding]:
    """Alle Wochenreihen des Ueberwachungsplans pruefen."""
    results: list[RawFinding] = []
    for kpi_key, scope in SCAN_PLAN:
        kpi = KPIS[kpi_key]
        columns = SCOPE_COLUMNS[scope]
        sums = weekly_sums(dataset, kpi, group=_grouper(columns))
        entities = sorted({key[0] for key in sums})
        times = sorted({key[1] for key in sums})
        totals = {time: [0.0, 0.0] for time in times}
        for (_, time), (numerator, denominator) in sums.items():
            totals[time][0] += numerator
            totals[time][1] += denominator
        use_peers = len(entities) - 1 >= MIN_PEER_ENTITIES

        for entity in entities:
            values, denominators, peers = {}, {}, {}
            for time in times:
                numerator, denominator = sums.get((entity, time), (0.0, 0.0))
                values[time] = kpi.compute(numerator, denominator)
                denominators[time] = denominator
                peer_numerator = totals[time][0] - numerator
                peer_denominator = totals[time][1] - denominator
                peers[time] = (kpi.compute(peer_numerator, peer_denominator)
                               if peer_denominator >= dataset.min_denominator else None)
            runs, trace = detect_with_trace(
                kpi, times, values, denominators, peers,
                baseline_weeks=dataset.baseline_weeks,
                zscore_threshold=dataset.zscore_threshold,
                consecutive=dataset.consecutive_weeks,
                min_denominator=dataset.min_denominator,
                use_peers=use_peers and (rule or {}).get("use_peer_group", True),
                use_zscore=(rule or {}).get("use_zscore", True),
                use_min_effect=(rule or {}).get("use_min_effect", True),
                use_target=(rule or {}).get("use_target", True),
            )
            for run in runs:
                start, end = run[0].week, run[-1].week
                window = (max(times[0], start - dataset.baseline_weeks), start - 1)
                current = [values[time] for time in range(start, end + 1)
                           if values.get(time) is not None]
                results.append(RawFinding(
                    kpi_key=kpi_key, scope=scope, entity=entity,
                    start=start, end=end, weeks=[flag.week for flag in run],
                    flags={flag.week: flag for flag in run},
                    series=[{"week": time, "value": values[time]} for time in times],
                    baseline_window=window,
                    baseline_value=_window_value(dataset, kpi, columns, entity, window),
                    current_value=statistics.fmean(current) if current else run[0].value,
                    current_reported=_window_value(dataset, kpi, columns, entity,
                                                   (start, end)),
                    denominator=statistics.fmean(
                        [denominators[time] for time in range(start, end + 1)]),
                    zscores={time: round(value, 6) for time, value in trace.items()},
                ))
    return results


def _window_value(dataset: Dataset, kpi: Kpi, columns: Sequence[str], entity: tuple,
                  window: tuple[int, int]) -> float:
    """Kennzahl der Vergleichsbasis als Quotient aus Summen ueber das Fenster."""
    filters = {column: {value} for column, value in zip(columns, entity)}
    table = table_for(dataset, kpi)
    time_column = "week" if table.has("week") else "period"
    position = table.position(time_column)
    rows = [row for row in filtered_rows(table, filters)
            if window[0] <= row[position] <= window[1]]
    numerator, denominator = aggregate(table, rows, kpi)
    value = kpi.compute(numerator, denominator)
    return value if value is not None else 0.0


# --------------------------------------------------------------------------- #
# Artikelanalyse: ein Artikel gegen die uebrigen Artikel derselben Produktgruppe
# --------------------------------------------------------------------------- #

@dataclass
class ItemFinding:
    kpi_key: str
    product_group: str
    article_id: str
    periods: list[int]
    start_period: int
    end_period: int
    value: float
    peer_value: float
    peer_low: float
    peer_high: float
    #: z-Wert der Beginnperiode -- die Periode, die der Befund als Beginn nennt.
    zscore: float
    #: groesster z-Wert im Befundzeitraum, fuer die Einordnung der Staerke.
    zscore_max: float
    lines_shipped: float
    lines_complained: float
    peer_lines_shipped: float
    series: list[dict]


def _cell_sums(table: Table, row: Sequence, kpi: Kpi) -> tuple[float, float]:
    numerator = sum(row[table.position(name)] for name in kpi.numerator)
    denominator = sum(row[table.position(name)] for name in kpi.denominator)
    return numerator, denominator


def scan_item_level(dataset: Dataset, kpi_key: str = "complaint_rate_items") -> list[ItemFinding]:
    """Artikel je Vier-Wochen-Periode gegen die uebrigen Artikel derselben Gruppe.

    Warum nicht gegen einen globalen Mittelwert: Sonderanfertigungen werden
    generell haeufiger reklamiert als Standardmodule -- ein Gruppeneffekt, kein
    Fehler. Eine Regel, die einen Artikel gegen den Gesamtdurchschnitt haelt,
    meldet jede Sonderanfertigung. Verglichen wird deshalb gegen die **uebrigen
    Artikel derselben Produktgruppe in derselben Periode**.

    Der z-Wert ist der Standardfehler eines Anteilswerts:
    ``z = (Wert - Vergleichswert) / sqrt(p*(1-p)/n)`` mit ``p`` = Vergleichswert
    und ``n`` = gelieferte Positionen des Artikels. Die Zwei-Wochen-Regel aus A6
    wird zur Zwei-Perioden-Regel (Entscheidung OP-1).
    """
    kpi = KPIS[kpi_key] if kpi_key in KPIS else KPIS["complaint_rate_items"]
    table = dataset.assortment
    minimum = dataset.min_denominator_item

    cells: dict[tuple, list[float]] = {}
    group_totals: dict[tuple, list[float]] = {}
    for row in table.rows:
        period = table.at(row, "period")
        group = table.at(row, "product_group")
        article_id = table.at(row, "article_id")
        numerator, denominator = _cell_sums(table, row, kpi)
        cell = cells.setdefault((period, group, article_id), [0.0, 0.0])
        cell[0] += numerator
        cell[1] += denominator
        total = group_totals.setdefault((period, group), [0.0, 0.0])
        total[0] += numerator
        total[1] += denominator

    flagged: dict[tuple[str, str], list[tuple]] = {}
    for (period, group, article_id), (numerator, denominator) in sorted(cells.items()):
        if denominator < minimum:
            continue
        peer_numerator = group_totals[(period, group)][0] - numerator
        peer_denominator = group_totals[(period, group)][1] - denominator
        if peer_denominator < minimum:
            continue
        value = numerator / denominator
        peer = peer_numerator / peer_denominator
        standard_error = math.sqrt(max(peer * (1.0 - peer), 1e-9) / denominator)
        zscore = (value - peer) / standard_error
        if kpi.direction == HIGHER:
            zscore = -zscore
        worse = kpi.worsening(value - peer)
        if (zscore >= dataset.zscore_threshold and worse >= kpi.min_effect
                and kpi.violates_target(value)):
            flagged.setdefault((group, article_id), []).append(
                (period, value, peer, zscore, denominator, numerator,
                 peer_denominator, peer_numerator))

    findings: list[ItemFinding] = []
    for (group, article_id), hits in flagged.items():
        periods = [hit[0] for hit in hits]
        runs: list[list[int]] = []
        for period in periods:
            if runs and runs[-1][-1] == period - 1:
                runs[-1].append(period)
            else:
                runs.append([period])
        longest = max(runs, key=len)
        if len(longest) < dataset.consecutive_weeks:
            continue
        selected = [hit for hit in hits if hit[0] in longest]
        lines = sum(hit[4] for hit in selected)
        complaints = sum(hit[5] for hit in selected)
        peer_lines = sum(hit[6] for hit in selected)
        peer_complaints = sum(hit[7] for hit in selected)
        # Auch hier gilt Rechenregel R1: Der Vergleichswert ist der Quotient der
        # Summen ueber alle betroffenen Perioden, nicht das Mittel der
        # Periodenquoten. Sonst stehen Ist- und Vergleichswert auf zwei
        # verschiedenen Rechenwegen -- derselbe Fehler, den QA-1 beanstandet hat.
        peer_rates = [hit[2] for hit in selected]
        findings.append(ItemFinding(
            kpi_key=kpi.key, product_group=group, article_id=article_id,
            periods=longest, start_period=longest[0], end_period=longest[-1],
            value=complaints / lines if lines else 0.0,
            peer_value=peer_complaints / peer_lines if peer_lines else 0.0,
            peer_low=min(peer_rates), peer_high=max(peer_rates),
            zscore=next(hit[3] for hit in selected if hit[0] == longest[0]),
            zscore_max=max(hit[3] for hit in selected),
            lines_shipped=lines, lines_complained=complaints,
            peer_lines_shipped=peer_lines,
            series=_item_series(dataset, kpi, group, article_id),
        ))
    return findings


def item_year_profile(dataset: Dataset, kpi_key: str, group: str, article_id: str) -> dict:
    """Jahreswerte des Artikels und aller Artikel derselben Produktgruppe.

    Die Erkennung arbeitet auf Perioden; der Bericht nennt zusätzlich den
    Jahreswert, weil ein Qualitätsproblem über das Jahr beurteilt wird.
    """
    kpi = KPIS[kpi_key]
    table = dataset.assortment
    per_article: dict[str, list[float]] = {}
    for row in table.rows:
        if table.at(row, "product_group") != group:
            continue
        entry = per_article.setdefault(table.at(row, "article_id"), [0.0, 0.0])
        numerator, denominator = _cell_sums(table, row, kpi)
        entry[0] += numerator
        entry[1] += denominator
    rates = {other: numerator / denominator
             for other, (numerator, denominator) in per_article.items() if denominator}
    peers = {other: rate for other, rate in rates.items() if other != article_id}
    cell_numerator, cell_denominator = per_article.get(article_id, [0.0, 0.0])
    peer_numerator = sum(per_article[other][0] for other in peers)
    peer_denominator = sum(per_article[other][1] for other in peers)
    return {
        "value": rates.get(article_id),
        "lines_shipped": cell_denominator,
        "numerator": cell_numerator,
        "peer_value": peer_numerator / peer_denominator if peer_denominator else None,
        "peer_lines_shipped": peer_denominator,
        "peer_low": min(peers.values()) if peers else None,
        "peer_high": max(peers.values()) if peers else None,
        "by_article": {other: round(rate, 6) for other, rate in sorted(rates.items())},
    }


def item_window_profile(dataset: Dataset, kpi_key: str, group: str, article_id: str,
                        periods: Sequence[int]) -> dict:
    """Artikel und Vergleichsgruppe ueber ein Periodenfenster, mit z-Wert.

    Dieselbe Rechnung wie in ``scan_item_level``, nur ueber die uebergebenen
    Perioden: Quotient aus Summen fuer beide Seiten (Regel R1) und der z-Wert aus
    dem Standardfehler eines Anteilswerts.
    """
    kpi = KPIS[kpi_key]
    table = dataset.assortment
    selected = set(periods)
    cell = [0.0, 0.0]
    peer = [0.0, 0.0]
    for row in table.rows:
        if table.at(row, "product_group") != group:
            continue
        if table.at(row, "period") not in selected:
            continue
        numerator, denominator = _cell_sums(table, row, kpi)
        target = cell if table.at(row, "article_id") == article_id else peer
        target[0] += numerator
        target[1] += denominator
    value = cell[0] / cell[1] if cell[1] else None
    peer_value = peer[0] / peer[1] if peer[1] else None
    zscore = None
    if value is not None and peer_value is not None and cell[1]:
        standard_error = math.sqrt(max(peer_value * (1.0 - peer_value), 1e-9) / cell[1])
        zscore = (value - peer_value) / standard_error
        if kpi.direction == HIGHER:
            zscore = -zscore
    return {
        "value": value,
        "peer_value": peer_value,
        "lines_shipped": cell[1],
        "peer_lines_shipped": peer[1],
        "zscore": zscore,
    }


def _item_series(dataset: Dataset, kpi: Kpi, group: str, article_id: str) -> list[dict]:
    """Reihe des Artikels und seiner Vergleichsgruppe ueber alle Perioden."""
    table = dataset.assortment
    per_period: dict[int, list[float]] = {}
    for row in table.rows:
        if table.at(row, "product_group") != group:
            continue
        period = table.at(row, "period")
        numerator, denominator = _cell_sums(table, row, kpi)
        entry = per_period.setdefault(period, [0.0, 0.0, 0.0, 0.0])
        if table.at(row, "article_id") == article_id:
            entry[0] += numerator
            entry[1] += denominator
        else:
            entry[2] += numerator
            entry[3] += denominator
    minimum = dataset.min_denominator_item
    series = []
    for period in sorted(per_period):
        cell_numerator, cell_denominator, peer_numerator, peer_denominator = per_period[period]
        first, last = dataset.weeks_of_period(period)
        series.append({
            "period": period, "week_from": first, "week_to": last,
            "value": cell_numerator / cell_denominator if cell_denominator >= minimum else None,
            "peer_value": peer_numerator / peer_denominator if peer_denominator >= minimum else None,
        })
    return series


# --------------------------------------------------------------------------- #
# Verdichtung: derselbe Sachverhalt darf nur einmal in der Liste stehen
# --------------------------------------------------------------------------- #

def consolidate(raw: list[RawFinding], link_window: int = 2) -> list[dict]:
    """Rohbefunde zu Faellen verdichten.

    Zwei Regeln, beide in einem Satz erklaerbar:

    * **Derselbe Ausschnitt, mehrere Kennzahlen:** Beginnen Befunde derselben
      Einheit innerhalb von zwei Wochen, ist es ein Fall. Die Kennzahl mit der
      groessten Abweichung fuehrt, die uebrigen stehen als Beleg dabei.
    * **Gleicher Fall, groebere Ebene:** Ein Befund auf Partnerebene, der
      zeitlich zu einem Befund derselben Kennzahl auf Ebene Markt x Partner
      passt, ist derselbe Fall auf einer groeberen Ebene und entfaellt.
    """
    remaining = list(raw)

    # Regel 2: die gröbere Ebene entfaellt, wenn die feinere denselben Fall zeigt.
    specific = [item for item in remaining if item.scope == "market_partner"]
    kept: list[RawFinding] = []
    for item in remaining:
        if item.scope == "partner":
            covered = any(
                other.kpi_key == item.kpi_key
                and other.entity[1] == item.entity[0]
                and abs(other.start - item.start) <= link_window + 2
                for other in specific
            )
            if covered:
                continue
        kept.append(item)

    # Regel 1: gleiche Einheit, Beginn dicht beieinander -> ein Fall.
    groups: dict[tuple, list[RawFinding]] = {}
    for item in kept:
        groups.setdefault((item.scope, item.entity), []).append(item)

    cases: list[dict] = []
    for (scope, entity), items in groups.items():
        items.sort(key=lambda entry: entry.start)
        clusters: list[list[RawFinding]] = []
        for item in items:
            if clusters and item.start - clusters[-1][0].start <= link_window:
                clusters[-1].append(item)
            else:
                clusters.append([item])
        for cluster in clusters:
            lead = max(cluster, key=lambda entry: corridor_distance(
                KPIS[entry.kpi_key], entry.current_value))
            cases.append({
                "scope": scope,
                "entity": entity,
                "lead": lead,
                "evidence": [item for item in cluster if item is not lead],
                "start": min(item.start for item in cluster),
                "end": max(item.end for item in cluster),
            })
    cases.sort(key=lambda case: case["start"])
    return cases


# --------------------------------------------------------------------------- #
# Textbausteine (regelbasiert, F5)
# --------------------------------------------------------------------------- #

ENTITY_LABEL = {
    "market": "Markt {0}",
    "partner": "{0}",
    "channel": "Vertriebsweg {0}",
    "market_partner": "Markt {0}, {1}",
    "gesamt": "Gesamtgeschäft",
}

#: Neutrale Bezeichnungen der Vertriebspartner -- kein Eigenname (harte Regel 1).
PARTNER_LABEL = {
    "partner_1": "Tochtergesellschaft 1 (DE)",
    "partner_2": "Tochtergesellschaft 2 (FR, IT)",
    "partner_3": "Tochtergesellschaft 3 (GB, PL)",
    "partner_4": "Vertretung 4 (SE)",
    "partner_5": "Vertretung 5 (NO, DK)",
    "partner_6": "Vertretung 6 (NL, FI)",
    "nordic_subsidiary": "Tochtergesellschaft Skandinavien (geplant)",
}
#: Ausgeschriebene Ländernamen -- Kürzel wie "SE" versteht nicht jeder Leser.
MARKET_LABEL = {"DE": "Deutschland", "FR": "Frankreich", "IT": "Italien",
                "GB": "Großbritannien", "PL": "Polen", "NL": "Niederlande",
                "SE": "Schweden", "NO": "Norwegen", "DK": "Dänemark", "FI": "Finnland"}
CHANNEL_LABEL = {"subsidiary": "Tochtergesellschaft", "agency": "Handelsvertretung",
                 "direct": "Direktvertrieb ab Werk"}


def entity_label(scope: str, entity: tuple) -> str:
    parts = []
    for column, value in zip(SCOPE_COLUMNS.get(scope, ()), entity):
        if column == "partner":
            parts.append(PARTNER_LABEL.get(value, value))
        elif column == "channel":
            parts.append(CHANNEL_LABEL.get(value, value))
        elif column == "market":
            parts.append(MARKET_LABEL.get(value, value))
        else:
            parts.append(str(value))
    if not parts:
        return ENTITY_LABEL["gesamt"]
    return ENTITY_LABEL[scope].format(*parts)


def explanation_text(kpi: Kpi, label: str, start_week: int, baseline: float,
                     current: float, zscore: float, extra: str = "",
                     end_week: int | None = None, after: float | None = None) -> str:
    """Erklaerungssatz aus einer Vorlage (F5, AK-07.3).

    Kein Eigenname, kein Superlativ, kein Wort ueber Ursachen -- der Satz nennt
    Kennzahl, Einheit, Zeitraum, Vorher-nachher und Zielwert; der z-Wert
    steht nicht im Fließtext, sondern im Befundkopf. Ein
    behobener Fall bekommt eine eigene Fassung: "lag ... und liegt seit ...
    wieder bei ...", damit niemand ihn fuer laufend haelt.
    """
    if after is not None and end_week is not None:
        sentence = (
            f"Für {label} lag {kpi.subject} im Zeitraum "
            f"{fmt.week_range(start_week, end_week)} bei {kpi.text(current)} "
            f"gegenüber {kpi.text(baseline)} davor und liegt seit "
            f"{fmt.week(end_week + 1)} wieder bei {kpi.text(after)} "
            f"(Zielwert {kpi.text(kpi.target)})."
        )
    else:
        sentence = (
            f"Für {label} liegt {kpi.subject} seit {fmt.week(start_week)} bei "
            f"{kpi.text(current)} gegenüber {kpi.text(baseline)} in den "
            f"acht Wochen davor (Zielwert {kpi.text(kpi.target)})."
        )
    if extra:
        sentence = f"{sentence} {extra}"
    return f"{sentence} [{GENERATED_MARK}]"


def follow_up_text(reference_id: str, offset_weeks: int) -> str:
    """Hinweistext fuer einen mutmasslichen Folgeeffekt (AK-09.1, AK-09.3)."""
    if offset_weeks == 0:
        timing = "in derselben Woche"
    elif offset_weeks == 1:
        timing = "eine Woche später"
    else:
        timing = f"{fmt.count(offset_weeks)} Wochen später"
    return (
        f"Mutmaßlicher Folgeeffekt von {reference_id}: derselbe Markt, Beginn {timing} — "
        f"{NO_CAUSALITY}. [{GENERATED_MARK}]"
    )


PROPOSED_ACTIONS = {
    "quote_win_rate": "Verlorene Angebote mit der Vertretung auswerten (Preis, Lieferzeit, "
                      "Wettbewerber) und eine Zielvereinbarung mit Wochengespräch aufsetzen.",
    "quote_lead_time_h": "Angebotsfreigaben im Vertriebsinnendienst bündeln und Standardangebote "
                         "für wiederkehrende Anfragen vorbereiten.",
    "order_lead_time_d": "Fertigungsplanung und Versandtermine je Auftrag abgleichen, "
                         "Engpassaufträge priorisieren.",
    "otif_rate": "Termin- und Mengentreue je Auftrag auswerten und Liefertermine mit der "
                 "Fertigungsplanung abstimmen.",
    "complaint_rate_lines": "Reklamationsgründe je Markt auswerten und mit der Qualität "
                            "eine Abstellmaßnahme vereinbaren.",
    "complaint_rate_items": "Werkzeug und Maßhaltigkeit des Artikels prüfen, betroffene "
                            "Charge sperren und Kunden proaktiv informieren.",
    "complaint_processing_time_d": "Bearbeitungsschritte der Reklamation entzerren und "
                                   "Freigabegrenzen für Gutschriften prüfen.",
    "delivery_inquiries_per_100_orders": "Proaktive Lieferterminbestätigung einrichten und "
                                         "Terminänderungen automatisch melden.",
    "contribution_margin_per_order_eur": "Rabattstufen und Mindestauftragswerte im Markt prüfen.",
    "revenue_index": "Marktplan mit dem Partner überprüfen und Zielkunden neu priorisieren.",
    "partner_activity_rate": "Betreuung der Schlüsselkunden mit der Vertretung neu planen und "
                             "Kapazität der Vertretung an das Wachstum anpassen.",
}


def corridor_distance(kpi: Kpi, value: float) -> float:
    """Wie weit ein Wert seinen vereinbarten Korridor verlässt.

    Der Korridor ist der Abstand zwischen Zielwert und Warnschwelle. Ihn als
    Maßstab zu nehmen macht Kennzahlen unterschiedlicher Einheiten vergleichbar:
    "zwei Korridorbreiten jenseits des Ziels" bedeutet bei der Termintreue und
    bei der Durchlaufzeit dasselbe. Der z-Wert taugt dafür nicht -- er misst die
    Streuung der Reihe, nicht die fachliche Tragweite.
    """
    width = abs(kpi.warning - kpi.target)
    if width <= 0:
        return 0.0
    return kpi.worsening(value - kpi.target) / width


def severity_of(kpi: Kpi, value: float, resolved: bool) -> str:
    """Schweregrad: hoch, wenn die Warnschwelle verfehlt wird und der Fall läuft."""
    if kpi.violates_warning(value):
        return "mittel" if resolved else "hoch"
    if kpi.violates_target(value):
        return "gering" if resolved else "mittel"
    return "gering"


# --------------------------------------------------------------------------- #
# Wirkungsschaetzung
# --------------------------------------------------------------------------- #

def derived_rate(dataset: Dataset, cost_field: str, quantity_field: str,
                 filters: dict | None = None) -> float:
    """Kostensatz je Vorgang, aus dem Datensatz abgeleitet statt geschaetzt."""
    table = dataset.facts
    rows = filtered_rows(table, filters)
    cost = sum_fields(table, rows, (cost_field,))
    quantity = sum_fields(table, rows, (quantity_field,))
    return cost / quantity if quantity else 0.0


def chain_step(label: str, value_text: str, source: str) -> dict:
    """Ein Schritt der offengelegten Rechenkette."""
    return {"label": label, "value": value_text, "source": source}


# --------------------------------------------------------------------------- #
# Wachstumsszenario (US-14, US-15)
# --------------------------------------------------------------------------- #

#: Rechenregel des Szenarios -- bewusst in einer Zeile, damit der JavaScript-Kern
#: sie identisch nachbauen kann.
#:
#:   Menge(p, w)      = bearbeitete Angebote(p, w) x (1 + Mehrvolumen)
#:   ab dem gewaehlten Quartal, wenn die eigene Tochtergesellschaft aktiv ist:
#:       fuer jede Vertretung q in subsidiary_source_partners:
#:           Verlagerung = Menge(q, w) x subsidiary_volume_share
#:           Menge(q, w) -= Verlagerung ;  Menge(T, w) += Verlagerung
#:       Kapazitaet(T, w) = subsidiary_capacity_quotes_per_week
#:   Auslastung(p, w) = Menge(p, w) / Kapazitaet(p, w)
#:   Engpasswoche     = Auslastung(p, w) > Warnschwelle (92 %)
#:
#: Das ist eine Modellrechnung, keine Prognose (Abgrenzungspunkt 6).
SCENARIO_FORMULA = (
    "bearbeitete Angebote × (1 + Mehrvolumen) ÷ geplante Angebotskapazität; "
    "mit eigener Tochtergesellschaft ab dem gewählten Quartal übernimmt diese einen festen "
    "Anteil der Angebote der skandinavischen Vertretungen mit eigener Kapazität"
)

SCENARIO_BOTTLENECK_THRESHOLD = 0.92
SCENARIO_VOLUME_STEPS = [0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40]
QUARTER_FIRST_WEEK = {1: 1, 2: 14, 3: 27, 4: 40}
SUBSIDIARY_KEY = "nordic_subsidiary"


def capacity_base(dataset: Dataset) -> dict[str, dict[int, tuple[float, float, float]]]:
    """Ist-Mengen, geplante und zubuchbare Kapazitaet je Partner und Woche."""
    table = dataset.capacity
    base: dict[str, dict[int, tuple[float, float, float]]] = {}
    for row in table.rows:
        partner = table.at(row, "partner")
        week = table.at(row, "week")
        base.setdefault(partner, {})[week] = (
            float(table.at(row, "quotes_processed")),
            float(table.at(row, "capacity_quotes_contracted")),
            float(table.at(row, "capacity_quotes_flex")),
        )
    return base


def scenario_sources(dataset: Dataset) -> list[str]:
    return list(dataset.parameters.get("subsidiary_source_partners", []))


def scenario(dataset: Dataset, volume_increase: float = 0.0,
             expansion: bool = False, expansion_quarter: int = 3) -> dict:
    """Wachstumsszenario als offengelegte Modellrechnung (siehe SCENARIO_FORMULA)."""
    base = capacity_base(dataset)
    subsidiary_capacity = float(dataset.parameters.get("subsidiary_capacity_quotes_per_week", 0.0))
    shift_share = float(dataset.parameters.get("subsidiary_volume_share", 0.0))
    sources = scenario_sources(dataset)
    first_week = QUARTER_FIRST_WEEK.get(expansion_quarter, 27)
    weeks = sorted({week for block in base.values() for week in block})

    result: dict[str, dict] = {}
    for partner in sorted(base):
        result[partner] = {"weeks": [], "bottleneck_weeks": []}
    if expansion:
        result[SUBSIDIARY_KEY] = {"weeks": [], "bottleneck_weeks": []}

    for week in weeks:
        units = {partner: base[partner][week][0] * (1.0 + volume_increase)
                 for partner in base if week in base[partner]}
        capacity = {partner: base[partner][week][1]
                    for partner in base if week in base[partner]}
        flex = {partner: base[partner][week][2]
                for partner in base if week in base[partner]}
        if expansion and week >= first_week:
            shifted_total = 0.0
            for partner in sources:
                if partner in units:
                    shifted = units[partner] * shift_share
                    units[partner] -= shifted
                    shifted_total += shifted
            units[SUBSIDIARY_KEY] = shifted_total
            capacity[SUBSIDIARY_KEY] = subsidiary_capacity
            flex[SUBSIDIARY_KEY] = 0.0
        for partner in units:
            utilization = units[partner] / capacity[partner] if capacity[partner] else 0.0
            result[partner]["weeks"].append({
                "week": week,
                "units": round(units[partner], 1),
                "capacity": round(capacity[partner], 1),
                "flex": round(flex[partner], 1),
                "utilization": round(utilization, 6),
            })
            if utilization > SCENARIO_BOTTLENECK_THRESHOLD:
                result[partner]["bottleneck_weeks"].append(week)
            if units[partner] > capacity[partner] + flex[partner]:
                result[partner].setdefault("over_flex_weeks", []).append(week)

    for partner, block in result.items():
        block.setdefault("over_flex_weeks", [])
        block["over_flex_week_count"] = len(block["over_flex_weeks"])
        utilizations = [point["utilization"] for point in block["weeks"]]
        block["first_bottleneck_week"] = (block["bottleneck_weeks"][0]
                                          if block["bottleneck_weeks"] else None)
        block["bottleneck_week_count"] = len(block["bottleneck_weeks"])
        block["max_utilization"] = round(max(utilizations), 6) if utilizations else None
        block["mean_utilization"] = (round(statistics.fmean(utilizations), 6)
                                     if utilizations else None)
    return {
        "volume_increase": round(volume_increase, 4),
        "expansion": expansion,
        "expansion_quarter": expansion_quarter if expansion else None,
        "expansion_first_week": first_week if expansion else None,
        "subsidiary_capacity_quotes_per_week": subsidiary_capacity if expansion else 0.0,
        "subsidiary_volume_share": shift_share if expansion else 0.0,
        "per_partner": result,
    }


def scenario_summary(case: dict) -> dict:
    """Stuetzstelle ohne Wochenreihen -- klein genug fuer metrics.json."""
    return {
        "volume_increase": case["volume_increase"],
        "expansion": case["expansion"],
        "expansion_quarter": case["expansion_quarter"],
        "per_partner": {
            partner: {
                "bottleneck_week_count": block["bottleneck_week_count"],
                "first_bottleneck_week": block["first_bottleneck_week"],
                "max_utilization": block["max_utilization"],
                "mean_utilization": block["mean_utilization"],
                "bottleneck_weeks": block["bottleneck_weeks"],
                "over_flex_week_count": block["over_flex_week_count"],
                "over_flex_weeks": block["over_flex_weeks"],
            }
            for partner, block in case["per_partner"].items()
        },
    }


def critical_agency(case: dict, sources: Sequence[str]) -> str | None:
    """Die Vertretung mit den meisten Engpasswochen -- sie bestimmt die Roadmap."""
    candidates = [partner for partner in sources if partner in case["per_partner"]]
    if not candidates:
        return None
    return max(candidates, key=lambda partner: (
        case["per_partner"][partner]["bottleneck_week_count"],
        case["per_partner"][partner]["max_utilization"] or 0.0))


def roadmap_points(dataset: Dataset, case: dict) -> list[dict]:
    """Drei bis fuenf Roadmap-Punkte, regelbasiert aus dem Ergebnis (AK-15.3).

    Jeder Punkt nennt Quartal, Verantwortlichen und die Regel, aus der er
    entstanden ist, und traegt die Kennzeichnung nach F5.
    """
    points: list[dict] = []
    sources = scenario_sources(dataset)
    critical = critical_agency(case, sources) or "partner_5"
    other = next((partner for partner in sources if partner != critical), critical)
    block = case["per_partner"].get(critical, {})
    other_block = case["per_partner"].get(other, {})
    name = PARTNER_LABEL.get(critical, critical)
    other_name = PARTNER_LABEL.get(other, other)
    first = block.get("first_bottleneck_week")
    count = block.get("bottleneck_week_count", 0)
    over_flex = block.get("over_flex_week_count", 0)
    volume_text = fmt.percent(case["volume_increase"], 0)

    def quarter_of(week: int | None) -> str:
        if week is None:
            return "Q1"
        for quarter in (4, 3, 2, 1):
            if week >= QUARTER_FIRST_WEEK[quarter]:
                return f"Q{quarter}"
        return "Q1"

    if count:
        points.append({
            "quarter": quarter_of(first),
            "owner": "Partnermanagement",
            "text": (f"Kapazitätsgespräch mit {name} führen: bei {volume_text} "
                     f"Mehrvolumen liegen {fmt.count(count)} Wochen über der Warnschwelle, "
                     f"erstmals in {fmt.week(first)}."),
            "rule": f"Regel: mindestens eine Engpasswoche bei {name}.",
        })
        points.append({
            "quarter": quarter_of(first),
            "owner": "Partnermanagement",
            "text": (f"Zusätzliche Angebotskapazität für {fmt.count(count)} Wochen einplanen "
                     f"und den Abruf spätestens in {fmt.week(max(1, first - 4))} auslösen."),
            "rule": "Regel: Zahl der verbleibenden Engpasswochen größer als null.",
        })
    else:
        points.append({
            "quarter": "Q1",
            "owner": "Partnermanagement",
            "text": (f"Bei {volume_text} Mehrvolumen bleibt keine Engpasswoche; die "
                     f"geplante Angebotskapazität der Vertretungen trägt das Volumen."),
            "rule": "Regel: keine Engpasswoche im Ergebnis.",
        })
    if over_flex:
        points.append({
            "quarter": quarter_of(block.get("over_flex_weeks", [None])[0]),
            "owner": "Vertriebsinnendienst",
            "text": (f"In {fmt.count(over_flex)} Wochen reicht auch die zubuchbare "
                     f"Zusatzkapazität nicht; dort Angebote über den Innendienst ab Werk "
                     f"bearbeiten oder Angebotsfristen mit den Kunden abstimmen."),
            "rule": "Regel: Menge über geplanter Kapazität plus Zusatzkapazität.",
        })
    if not case["expansion"]:
        points.append({
            "quarter": "Q2",
            "owner": "Vertrieb",
            "text": ("Entscheidung über eine eigene Tochtergesellschaft in Skandinavien "
                     "vorbereiten; der Schalter zeigt die Wirkung je Startquartal."),
            "rule": "Regel: eigene Tochtergesellschaft im Szenario nicht aktiviert.",
        })
    else:
        # Auch die neue Gesellschaft kann an ihre Grenze kommen -- dann sagt es
        # die Roadmap, statt nur die Vertretungen zu betrachten.
        own = case["per_partner"].get(SUBSIDIARY_KEY, {}).get("bottleneck_week_count", 0)
        own_text = (f" Bei diesem Volumen liegt auch sie in {fmt.count(own)} Wochen über der "
                    f"Warnschwelle." if own else "")
        points.append({
            "quarter": f"Q{case['expansion_quarter']}",
            "owner": "Vertrieb",
            "text": (f"Tochtergesellschaft Skandinavien ab {fmt.week(case['expansion_first_week'])} "
                     f"mit Kapazität für {fmt.count(case['subsidiary_capacity_quotes_per_week'])} "
                     f"Angebote je Woche arbeitsfähig machen; Vorlauf für Gründung, Personal und "
                     f"Übergabe der Kundenkonten einplanen.{own_text}"),
            "rule": "Regel: eigene Tochtergesellschaft im Szenario aktiviert.",
        })
    points.append({
        "quarter": "Q3",
        "owner": "Controlling",
        "text": (f"Absatzplanung und Vertriebskapazität im selben Takt führen; die "
                 f"Modellrechnung erreicht "
                 f"{fmt.percent(block.get('max_utilization') or 0)} bei {name} und "
                 f"{fmt.percent(other_block.get('max_utilization') or 0)} bei {other_name}."),
        "rule": "Regel: Spitzenauslastung je Vertretung aus der Modellrechnung.",
    })
    for point in points:
        point["text"] = f"{point['text']} [{GENERATED_MARK}]"
    return points[:5]


# --------------------------------------------------------------------------- #
# Hilfsfunktionen fuer Zeitfenster
# --------------------------------------------------------------------------- #

def window_value(dataset: Dataset, kpi: Kpi, week_from: int, week_to: int,
                 filters: dict | None = None) -> tuple[float | None, float]:
    """Kennzahl ueber ein Wochenfenster -- Quotient aus Summen, nie ein Mittel."""
    table = table_for(dataset, kpi)
    time_column = "week" if table.has("week") else "period"
    position = table.position(time_column)
    rows = [row for row in filtered_rows(table, filters)
            if week_from <= row[position] <= week_to]
    numerator, denominator = aggregate(table, rows, kpi)
    return kpi.compute(numerator, denominator), denominator


def field_sum(dataset: Dataset, table_name: str, field_name: str,
              filters: dict | None = None, week_from: int | None = None,
              week_to: int | None = None) -> float:
    """Summe eines additiven Rohfelds ueber eine Auswahl."""
    table = {"facts_weekly": dataset.facts, "assortment_periods": dataset.assortment,
             "capacity_weekly": dataset.capacity}[table_name]
    rows = filtered_rows(table, filters)
    if week_from is not None or week_to is not None:
        time_column = "week" if table.has("week") else "period"
        position = table.position(time_column)
        low = week_from if week_from is not None else -10**9
        high = week_to if week_to is not None else 10**9
        rows = [row for row in rows if low <= row[position] <= high]
    return sum_fields(table, rows, (field_name,))
