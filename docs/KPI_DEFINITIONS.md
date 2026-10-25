# Kennzahlenkatalog — International Sales Cockpit

> Demo mit fiktiven Daten · eigene Initiative · erstellt mit KI-Unterstützung

| | |
|---|---|
| **Dokument** | `docs/KPI_DEFINITIONS.md` — verbindlicher Kennzahlenkatalog |
| **Gilt für** | `data/generate_data.py`, `data/dataset.json`, `data/metrics.json`, `app/index.html`, `case-study/case_study.html` |
| **Szenario** | Internationaler Vertrieb eines fiktiven Herstellers modularer Metallkomponenten für den Anlagenbau |

Die **Kürzel** sind die technischen Schlüssel. Sie werden unverändert zu den Schlüsseln in
`data/metrics.json` und im JavaScript-Rechenkern des Cockpits (englisch, `snake_case`). Maßgeblich für jeden
Zielwert ist `data/analysis.py`; ein Test prüft, dass `metrics.json` und dieser Katalog übereinstimmen.

---

## 1. Rechenregeln

**R1 — Jede Kennzahl ist ein Quotient aus Summen.** Der Datensatz speichert ausschließlich additive
Messgrößen. Eine Quote oder ein Mittelwert entsteht immer erst zur Anzeigezeit, indem Zähler und Nenner über
**alle Zeilen der aktuellen Auswahl** summiert und danach dividiert werden. Es wird nie über vorberechnete
Quoten gemittelt.

```
Kennzahl(Auswahl) = ( Σ Zählerfeld über Auswahl ) / ( Σ Nennerfeld über Auswahl )   [× Faktor]
```

Deshalb stehen im Datensatz „entschiedene Angebote" und „davon gewonnen" und nicht „Erfolgsquote 34 %".

**R2 — Mindeststichprobe.** Eine Kennzahl wird nur ausgegeben, wenn ihr Nenner in der Auswahl mindestens
**50** beträgt, auf Artikelebene mindestens **30** Positionen je Periode. Darunter zeigt das Cockpit „zu
wenig Daten" (graue Ampel, kein Zahlenwert), und die automatische Analyse bewertet die Zeitreihe nicht.

**R3 — Ampel.** grün = Zielwert erreicht · gelb = zwischen Zielwert und Warnschwelle · rot = Warnschwelle
verfehlt · grau = Mindeststichprobe unterschritten. Die Aussage steht immer in Farbe **und** Symbol **und**
Text.

**R4 — Richtung.** „höher ist besser" oder „niedriger ist besser" legt fest, auf welcher Seite des Zielwerts
grün liegt, und steuert die Beschriftung des Trends („besser"/„schlechter").

**R5 — Anzeigeformat.** Deutsches Zahlenformat. Quoten mit einer Nachkommastelle (die beiden
Reklamationsquoten mit zwei), Zeiten in Stunden und Tagen mit einer, der Deckungsbeitrag in ganzen Euro,
Kostensätze mit zwei Nachkommastellen, der Umsatzindex mit einer. Gerundet wird erst nach der Division.

**R6 — Fachbereichszuordnung.** Jede Kennzahl hat genau einen Verantwortlichen — den Bereich mit dem
stärksten Hebel. Zulässig sind: **Vertrieb**, **Vertriebsinnendienst**, **Auftragsabwicklung**,
**Logistik**, **Qualität**, **Kundenservice**, **Controlling**, **Partnermanagement** und **externer
Partner**. Eine Mehrfachzuordnung gibt es nicht.

---

## 2. Tabelle 1 — Pflichtkennzahlen (Reihenfolge der Kacheln im Modul „Übersicht")

| Nr. | Kennzahl | Kürzel | Formel | Einheit | Ziel | Warnschwelle | Richtung | Fachbereich |
|---|---|---|---|---|---|---|---|---|
| 1 | Angebotsdurchlaufzeit (Anfrage → Angebot) | `quote_lead_time_h` | Σ `stage1_inquiry_to_quote_hours` / Σ `quotes_sent` | Stunden | ≤ 24,0 | 30,0 | niedriger | Vertriebsinnendienst |
| 2 | Angebotserfolgsquote | `quote_win_rate` | Σ `quotes_won` / Σ `quotes_decided` | % | ≥ 32,0 | 29,0 | höher | Vertrieb |
| 3 | Auftragsdurchlaufzeit (Auftrag → Versand) | `order_lead_time_d` | (Σ `stage3_order_entry_hours` + Σ `stage4_production_shipping_hours`) / Σ `orders_shipped` / 24 | Tage | ≤ 9,0 | 11,0 | niedriger | Auftragsabwicklung |
| 4 | Liefertreue (Termin und Menge) | `otif_rate` | Σ `orders_otif` / Σ `orders_delivered` | % | ≥ 95,0 | 93,0 | höher | Logistik |
| 5 | Reklamationsquote (Positionen) | `complaint_rate_lines` | Σ `lines_complained` / Σ `lines_shipped` | % | ≤ 1,20 | 1,50 | niedriger | Qualität |
| 6 | Reklamationsbearbeitungszeit | `complaint_processing_time_d` | Σ `stage5_complaint_hours` / Σ `complaints_closed` / 24 | Tage | ≤ 5,0 | 6,0 | niedriger | Qualität |
| 7 | Lieferterminanfragen je 100 Aufträge | `delivery_inquiries_per_100_orders` | Σ `delivery_inquiries` / Σ `orders_placed` × 100 | Anzahl | ≤ 12,0 | 15,0 | niedriger | Kundenservice |
| 8 | Deckungsbeitrag je Auftrag | `contribution_margin_per_order_eur` | Σ `contribution_margin_eur` / Σ `orders_shipped` | € | ≥ 1.150 | 1.050 | höher | Controlling |
| 9 | Umsatz je Markt (Index zur Vorjahresbasis) | `revenue_index` | Σ `revenue_eur` / Σ `revenue_prior_year_eur` × 100 | Index | ≥ 100 | 95 | höher | Vertrieb |
| 10 | Aktivitätsgrad der Vertretungen | `partner_activity_rate` | Σ `key_accounts_active` / Σ `key_accounts_assigned` | % | ≥ 85,0 | 80,0 | höher | Partnermanagement |

---

## 3. Tabelle 2 — Ergänzende Kennzahl auf Artikelebene

| Kennzahl | Kürzel | Formel | Einheit | Ziel | Warnschwelle | Fachbereich |
|---|---|---|---|---|---|---|
| Reklamationsquote je Artikel | `complaint_rate_items` | Σ `lines_complained` / Σ `lines_shipped` in `assortment_periods` | % | ≤ 1,20 | 1,50 | Qualität |

Sie speist die Artikelanalyse: ein Artikel gegen die **übrigen Artikel derselben Produktgruppe** in derselben
Vier-Wochen-Periode.

---

## 4. Tabelle 3 — Stufenkennzahlen des Vertriebsprozesses

| Stufe | Kürzel | Formel | Ziel | Warnschwelle | Fachbereich | Verantwortlich im Modul |
|---|---|---|---|---|---|---|
| 1 Anfrage → Angebot | `stage1_inquiry_to_quote_h` | Σ `stage1_inquiry_to_quote_hours` / Σ `quotes_sent` | 24 h | 30 h | Vertriebsinnendienst | Innendienst |
| 2 Angebot → Auftrag | `stage2_quote_to_order_h` | Σ `stage2_quote_to_order_hours` / Σ `quotes_won` | 240 h | 288 h | Vertrieb | Vertrieb |
| 3 Auftragserfassung | `stage3_order_entry_h` | Σ `stage3_order_entry_hours` / Σ `orders_shipped` | 24 h | 48 h | Vertriebsinnendienst | Innendienst |
| 4 Fertigung und Versand | `stage4_production_shipping_h` | Σ `stage4_production_shipping_hours` / Σ `orders_shipped` | 192 h | 216 h | Auftragsabwicklung | Werk |
| 5 After-Sales | `stage5_complaint_h` | Σ `stage5_complaint_hours` / Σ `complaints_closed` | 120 h | 144 h | Qualität | Qualität |

Widerspruchsfreiheit (AK-03.4): Stufe 1 ist die Angebotsdurchlaufzeit; Stufe 3 + Stufe 4 ergibt die
Auftragsdurchlaufzeit in Stunden — auch bei Zielwert (24 + 192 = 216 h = 9 Tage) und Warnschwelle
(48 + 216 = 264 h = 11 Tage); Stufe 5 ist die Reklamationsbearbeitungszeit in Stunden. Die Stufen werden
deshalb nicht getrennt überwacht.

---

## 5. Erläuterungen

**Angebotsdurchlaufzeit.** Zeit von der Kundenanfrage bis zum versendeten Angebot. Im Industriegeschäft
entscheidet sie oft mit über den Zuschlag; 24 Stunden ist eine übliche interne Zusage für Standardanfragen.

**Angebotserfolgsquote.** Gewonnene Angebote je Angebot, über das der Kunde entschieden hat — nicht je
versendetem Angebot, weil offene Angebote sonst die Quote drücken. Überwacht je Markt **und** Vertriebspartner,
weil sie im Gespräch mit dem Partner gesteuert wird.

**Auftragsdurchlaufzeit.** Auftragserfassung plus Fertigung und Versand, in Tagen.

**Liefertreue (OTIF).** Anteil der gelieferten Aufträge, die termin- **und** mengengerecht angekommen sind.

**Reklamationsquote.** Reklamierte je gelieferte Auftragsposition. Auf Marktebene zu klein für eine
belastbare Überwachung in kleinen Märkten; überwacht wird sie deshalb je Vertriebspartner und auf
Artikelebene.

**Lieferterminanfragen.** Kundenanfragen zum Liefertermin je 100 Aufträge — ein Frühindikator für
Terminunsicherheit und der größte vermeidbare Aufwand im Kundenservice.

**Deckungsbeitrag je Auftrag.** Umsatz abzüglich variabler Kosten je versendetem Auftrag; bei
Handelsvertretungen nach Provision.

**Umsatzindex.** Umsatz gegen die Vorjahreswoche, Basis 100. Er ist eine Ergebnisgröße und wird nicht als
eigene Auffälligkeit gemeldet — er fällt zwangsläufig, wenn Angebote verloren gehen.

**Aktivitätsgrad der Vertretungen.** Anteil der betreuten Schlüsselkunden mit dokumentiertem
Vertriebskontakt (Anfrage, Angebot oder Auftrag) in der Woche. Die Fassung „Märkte mit
Auftragseingang je Woche" wäre bei ein bis zwei Märkten je Partner zu grob für eine statistische Prüfung;
die Kennzahl misst deshalb dasselbe auf der Ebene der Kundenkonten.

**Angebotskapazität (Szenario, keine Kachel).** Bearbeitete Angebote je geplanter Angebotskapazität des
Partners (`capacity_weekly`). Zielauslastung 85 %, Engpassschwelle 92 %. Sie ist die Rechengrundlage des
Wachstumsszenarios.

**Vertriebspartner.** Neutral bezeichnet: Tochtergesellschaft 1 (DE), Tochtergesellschaft 2 (FR, IT),
Tochtergesellschaft 3 (GB, PL), Vertretung 4 (SE), Vertretung 5 (NO, DK), Vertretung 6 (NL, FI). Das
Direktgeschäft ab Werk zählt zum Partner des jeweiligen Markts.

---

## 6. Filtermatrix — auf welcher Ebene ist welche Kennzahl auswertbar

| Kennzahl | Markt | Vertriebsweg | Vertriebspartner | Produktgruppe | Artikel |
|---|---|---|---|---|---|
| Alle zehn Pflichtkennzahlen | ja | ja | ja | — | — |
| Stufenkennzahlen 1–5 | ja | ja | ja | — | — |
| Reklamationsquote je Artikel | — | — | — | ja | ja |

Was hier fehlt, zeigt das Cockpit als „auf dieser Filterebene nicht auswertbar".

**Überwachungsplan der automatischen Analyse** (`SCAN_PLAN` in `data/analysis.py`):

| Kennzahl | Ebene |
|---|---|
| Angebotserfolgsquote | Markt × Partner, Partner |
| Angebotsdurchlaufzeit | Markt |
| Auftragsdurchlaufzeit | Partner |
| Liefertreue | Markt |
| Reklamationsquote | Partner |
| Reklamationsbearbeitungszeit | Partner |
| Lieferterminanfragen | Markt |
| Deckungsbeitrag je Auftrag | Markt |
| Aktivitätsgrad | Markt |
| Reklamationsquote je Artikel | Artikel gegen die übrigen Artikel der Produktgruppe |

---

## 7. Benötigte Rohfelder im Datensatz

### 7.1 Faktentabelle `facts_weekly`

Schlüssel: `week`, `market`, `channel` (`subsidiary`, `agency`, `direct`), `partner` (`partner_1` bis
`partner_6`). Jeder Markt hat genau einen Partner und zwei Vertriebswege (eigener Weg plus Direktgeschäft).

Messgrößen: `inquiries_received`, `quotes_sent`, `quotes_decided`, `quotes_won`, `orders_placed`,
`orders_shipped`, `orders_delivered`, `orders_otif`, `lines_shipped`, `lines_complained`,
`complaints_closed`, `delivery_inquiries`, `key_accounts_assigned`, `key_accounts_active`,
`stage1_inquiry_to_quote_hours` bis `stage5_complaint_hours`, `revenue_eur`, `revenue_prior_year_eur`,
`contribution_margin_eur`, `quote_cost_eur`, `complaint_cost_eur`, `service_cost_eur`.

Konsistenzbedingungen: gesendete ≤ eingegangene Anfragen, entschiedene ≤ gesendete Angebote, gewonnene ≤
entschiedene, versendete ≤ eingegangene Aufträge, gelieferte ≤ versendete, termintreue ≤ gelieferte,
reklamierte ≤ gelieferte Positionen, aktive ≤ betreute Schlüsselkunden; der Partner passt zum Markt.

### 7.2 Sortimenttabelle `assortment_periods`

Schlüssel: `period` (Vier-Wochen-Periode), `product_group`, `article_id`. Messgrößen: `lines_shipped`,
`lines_complained` und sechs Reklamationsgründe (`complaint_lines_reason_dimension`, `_surface`,
`_material`, `_transport`, `_wrong_item`, `_other`). Konsistenz: je Periode dieselben Positionen und
Reklamationen wie in `facts_weekly`; die Gründe summieren sich zu `lines_complained`.

### 7.3 Kapazitätstabelle `capacity_weekly`

Schlüssel: `week`, `partner`. Messgrößen: `capacity_quotes_contracted`, `capacity_quotes_flex`,
`quotes_processed` (= `quotes_sent` des Partners), `staff_hours_planned`, `staff_hours_worked`.

### 7.4 Auftragsstichprobe `orders_sample`

Rund 3.000 Einzelaufträge für Detailansichten. Sie speist **keine** Kennzahl (Festlegung F4).

### 7.5 Parameterblock `parameters`

`minutes_per_delivery_inquiry`, `minutes_per_complaint` (Effizienzpotenzial), `price_concession_share`
(Option A), `subsidiary_capacity_quotes_per_week`, `subsidiary_volume_share`,
`subsidiary_source_partners`, `subsidiary_setup_cost_eur`, `subsidiary_running_cost_eur_per_year`
(Szenario und Option B), dazu die Regelparameter `min_denominator`, `min_denominator_item`,
`baseline_weeks`, `zscore_threshold`, `consecutive_weeks`.

---

## 8. Kennzahlen, die bewusst **nicht** aufgenommen wurden

- **Pipeline-Volumen in Euro.** Ohne Abschlusswahrscheinlichkeiten je Angebot wäre das eine Scheingenauigkeit.
- **Kundenzufriedenheit.** Erfordert Befragungsdaten, die ein synthetischer Datensatz nicht glaubwürdig liefert.
- **Marktanteil.** Braucht externe Marktgrößen; der Umsatzindex beantwortet die steuerbare Teilfrage.
