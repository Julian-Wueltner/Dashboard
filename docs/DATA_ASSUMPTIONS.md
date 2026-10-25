# Datenannahmen — International Sales Cockpit

> Demo mit fiktiven Daten · eigene Initiative · erstellt mit KI-Unterstützung

| | |
|---|---|
| **Dokument** | `docs/DATA_ASSUMPTIONS.md` — Herleitung jedes Werts im Datensatz |
| **Gilt für** | `data/generate_data.py`, `data/dataset.json`, `data/dataset_control.json` |
| **Mitgeltend** | `docs/KPI_DEFINITIONS.md` (Abschnitt 7) |

**Alle Zahlen dieses Dokuments sind begründete Annahmen, keine Branchenwerte aus einer Quelle.** Der
Datensatz ist vollständig synthetisch. Was hier steht, ist die Herleitung — warum ein Wert plausibel ist und
was er im Modell bewirkt. Jeder Wert steht als benannte Konstante im Kopf von `data/generate_data.py`.

---

## 1. Grundsätze der Modellierung

| Grundsatz | Umsetzung | Begründung |
|---|---|---|
| Nur additive Messgrößen | Keine Quote, kein Mittelwert im Datensatz | Nur so liefern Cockpit-Filter und Python-Auswertung bei jeder Filterkombination denselben Wert. |
| Reproduzierbarkeit | Seed 42; jede Zufallsziehung nutzt eine eigene `random.Random`-Instanz, abgeleitet aus dem Inhalt der Zeile (`rng_for`) | Zwei Läufe erzeugen bytegleiche Dateien, und `--no-anomalies` behält exakt dasselbe Rauschen. |
| Eingepflanzte Effekte als Multiplikatoren nach dem Rauschen | Jede Auffälligkeit wirkt deterministisch auf die bereits gezogenen Werte | Der Kontrolldatensatz unterscheidet sich vom Echtdatensatz nur durch die fünf Effekte. |
| Nur Standardbibliothek | `random`, `json`, `hashlib`, `argparse`, `pathlib` | Der Generator läuft auf jedem Rechner mit Python ohne Installation. |
| Zeilen-Arrays | Jede Tabelle als `{"columns": [...], "rows": [[...]]}` | Halbiert die Dateigröße gegenüber wiederholten Feldnamen. |
| Ausschließlich fiktive Namen | Tochtergesellschaft 1–3, Vertretung 4–6, Artikel `MOD-xxxx` | Kein reales Unternehmen, keine Marke; ein Test prüft es maschinell. |

---

## 2. Unternehmen, Märkte und Vertriebsstruktur

Ein fiktiver Hersteller modularer Metallkomponenten für den Anlagenbau verkauft an Industriekunden in zehn
europäischen Märkten. Das Geschäft ist Angebotsgeschäft: Anfrage, technisch geklärtes Angebot, Entscheidung
des Kunden, Auftrag, Fertigung, Versand.

| Parameter | Wert | Begründung |
|---|---|---|
| Betrachtungszeitraum | 52 Kalenderwochen | Ein volles Jahr zeigt Sommerloch und Jahresendgeschäft. |
| Grundvolumen | 4.000 Anfragen je Woche vor Saisonfaktor | Ergibt rund 208.000 Anfragen, 57.000 gewonnene Aufträge und 270 Mio. € Umsatz im Jahr — ein mittelgroßer Komponentenhersteller. |
| Marktanteile | DE 30 % · FR 12 % · IT 10 % · GB 10 % · PL 8 % · NL 8 % · SE 8 % · NO 6 % · DK 5 % · FI 3 % | Heimatmarkt DE führt; die nordischen Märkte sind klein, aber groß genug, dass eine Auffälligkeit statistisch trägt. |
| Vertriebspartner | DE: Tochtergesellschaft 1 · FR, IT: Tochtergesellschaft 2 · GB, PL: Tochtergesellschaft 3 · SE: Vertretung 4 · NO, DK: Vertretung 5 · NL, FI: Vertretung 6 | Eigene Gesellschaften in den großen Märkten; NL und Skandinavien laufen über Handelsvertretungen — der Ausgangspunkt des Wachstumsszenarios. |
| Vertriebswege | Tochtergesellschaftsmärkte: 82 % Tochter, 18 % Direkt · Vertretungsmärkte: 72 % Vertretung, 28 % Direkt | Direktgeschäft ab Werk gibt es überall, in Vertretungsmärkten mehr, weil Großkunden dort häufiger direkt bestellen. |
| Schlüsselkunden | 4.000, nach Marktanteil verteilt | Grundlage des Aktivitätsgrads. |

Ergebnis im Datensatz: 1.040 Zeilen Faktentabelle (52 Wochen × 20 Kombinationen aus Markt und Vertriebsweg),
520 Zeilen Sortiment (13 Perioden × 40 Artikel), 312 Zeilen Kapazität, 3.000 Einzelaufträge.

---

## 3. Saisonalität

Industrielle Nachfrage: schwacher Januar (Faktor 0,70 in KW 1, Anlauf bis KW 5), stabile Monate bis Juni,
Sommerloch KW 28–32 (Tiefpunkt 0,70 in KW 30), Erholung ab KW 33, Jahresendgeschäft KW 45–50 (bis 1,24),
ruhige letzte zwei Wochen. Dazu ein gemeinsames Wochenrauschen von rund 2,5 %.

Weil Saison alle Märkte zugleich trifft, vergleicht die Erkennung jede Einheit gegen das übrige Geschäft
derselben Woche — sonst würde das Sommerloch in jedem Markt als Auffälligkeit gemeldet.

---

## 4. Angebots- und Auftragsprozess

| Messgröße | Annahme | Begründung |
|---|---|---|
| Angebotsquote | 93 % (Tochter) · 91 % (Vertretung) · 89 % (Direkt) der Anfragen | Ein Teil der Anfragen ist nicht lieferbar oder wird zurückgezogen. |
| Entscheidungsquote | 94 % der Angebote | Ein Rest bleibt offen. |
| Angebotserfolgsquote | 32,5 % (Tochter) · 34,5 % (Vertretung) · 29 % (Direkt), Marktfaktor SE 1,03 | Vertretungen kennen ihre Kunden eng; Direktangebote sind häufiger Preisvergleiche. SE startet damit bei rund 34 %. |
| Versandquote | 98,6 % der Aufträge | Ein kleiner Rest liegt am Jahresende noch in der Fertigung. |
| Positionen je Auftrag | 6,5 | Industrieaufträge bündeln mehrere Komponenten. |
| Stufe 1 Anfrage → Angebot | 20,0 / 21,5 / 23,0 Stunden | Der Innendienst der Tochter ist am nächsten am Kunden. |
| Stufe 2 Angebot → Auftrag | 195–220 Stunden | Rund neun Tage Entscheidungszeit beim Kunden. |
| Stufe 3 Auftragserfassung | 8–11 Stunden | Technische Prüfung und Terminbestätigung. |
| Stufe 4 Fertigung und Versand | 170–190 Stunden je Markt | Entfernung zum Werk und Exportabwicklung. |
| Stufe 5 After-Sales | 96–104 Stunden je Reklamation | Rund vier Tage bis zum Abschluss. |

---

## 5. Liefertreue, Reklamationen und Service

| Messgröße | Annahme |
|---|---|
| Liefertreue (OTIF) | 95,1–96,2 % je Markt |
| Reklamationsquote | 1,0 % der Positionen, Marktfaktor 0,95–1,06 |
| Produktgruppen | Standardmodule (55 % der Positionen, 10 Artikel, Faktor 0,92) · Formteile (15 %, 8 Artikel, 1,10) · Verbindungselemente (15 %, 9 Artikel, 0,85) · Sonderanfertigungen (5 %, 6 Artikel, 2,30) · Zubehör (10 %, 7 Artikel, 0,95) |
| Artikelnummern | `MOD-` mit Nummernkreis je Gruppe: Formteile 1040–1047, Standardmodule 2010–2019, Verbindungselemente 3020–3028, Sonderanfertigungen 4030–4035, Zubehör 5050–5056 |
| Reklamationsgründe | Maßabweichung, Oberfläche/Beschichtung, Materialfehler, Transportschaden, Falschlieferung, sonstiger Grund — Anteile je Produktgruppe |
| Lieferterminanfragen | 8,8 / 9,8 / 10,6 je 100 Aufträge, Marktfaktor 0,95–1,08 |
| Aktivitätsgrad | 92,0 % (Tochter) · 90,5 % (Vertretung) · 89,0 % (Direkt) der Schlüsselkunden je Woche |

**Die Falle im Sortiment.** Sonderanfertigungen werden mit Faktor 2,30 generell mehr als doppelt so oft
reklamiert wie der Durchschnitt — ein Gruppeneffekt, kein Fehler. Ein Vergleich gegen den
Gesamtdurchschnitt würde jede Sonderanfertigung melden; die Erkennung vergleicht deshalb gegen die übrigen
Artikel derselben Gruppe. Ein Test hält beides fest.

---

## 6. Umsatz, Deckungsbeitrag und Kosten

| Messgröße | Annahme | Begründung |
|---|---|---|
| Umsatz je Auftrag | 4.800 € × Preisniveau des Markts (PL 0,86 bis NO 1,12) | Mittlere Industrieaufträge; Preisniveau folgt dem Lohn- und Wettbewerbsniveau. |
| Deckungsbeitragsquote | 26,2 % (Tochter) · 25,2 % (Vertretung, nach Provision) · 27,5 % (Direkt) | Ergibt rund 1.250 € je Auftrag gegen den Zielwert 1.150 €. |
| Vorjahresumsatz | Planpfad derselben Zeile ohne Auffälligkeiten ÷ Wachstum des Markts (FI 0,98 bis PL 1,06) | Ein Vorjahr ändert sich nicht, weil dieses Jahr ein Wettbewerber auftritt. |
| Kosten je Reklamation | 185 € | Prüfung, Ersatz, Fracht. |
| Kosten je Lieferterminanfrage | 9,40 € | Rund zehn Minuten Kundenservice. |

---

## 7. Angebotskapazität je Vertriebspartner

Jeder Partner plant seine Angebotskapazität auf Basis des Forecasts (Lauf ohne Auffälligkeiten) mit einer
Planauslastung von 80 %, gerundet auf zehn Angebote, plus 15 % zubuchbare Zusatzkapazität. Weil der
Forecast das Wachstum in NO nicht kennt, läuft Vertretung 5 ab Sommer über die Engpassschwelle von 92 %.

Wachstumsszenario: Eine eigene Tochtergesellschaft in Skandinavien übernähme ab dem gewählten Quartal 50 %
der Angebote von Vertretung 4 und 5 und brächte eine Kapazität von 680 Angeboten je Woche mit (80 % der
gemeinsamen Kapazität beider Vertretungen). Einmalkosten 1,4 Mio. €, laufend 0,95 Mio. € je Jahr — Annahmen
für die Entscheidungsvorlage, keine Kalkulation.

---

## 8. Parameterblock `parameters`

| Parameter | Wert | Verwendung |
|---|---|---|
| `minutes_per_delivery_inquiry` | 9 | Effizienzpotenzial |
| `minutes_per_complaint` | 95 | Effizienzpotenzial |
| `price_concession_share` | 0,05 | Kosten von Option A |
| `subsidiary_capacity_quotes_per_week` | 680 | Szenario |
| `subsidiary_volume_share` | 0,50 | Szenario |
| `subsidiary_source_partners` | `partner_4`, `partner_5` | Szenario |
| `subsidiary_setup_cost_eur` / `_running_cost_eur_per_year` | 1.400.000 / 950.000 | Option B |
| `min_denominator` / `min_denominator_item` | 50 / 30 | Mindeststichprobe |
| `baseline_weeks` / `zscore_threshold` / `consecutive_weeks` | 8 / 2,5 / 2 | Erkennungsregel |

---

## 9. Die eingepflanzten Auffälligkeiten

### 9.1 Angebotserfolgsquote Markt SE (laufend)

Ab KW 32 tritt ein lokaler Wettbewerber auf. Die Erfolgsquote in SE fällt von rund 34 % auf 23,5 % (KW 32),
21,5 % (KW 33) und bleibt danach bei 21 %. Betroffen ist Vertretung 4, verantwortlich der Vertrieb.

### 9.2 Folgeeffekt Angebotsdurchlaufzeit Markt SE (laufend)

Ab KW 33 werden mehr Angebote nachverhandelt: +10 Stunden (KW 33), +15 (KW 34), danach +19 auf rund
41 Stunden. Ein zeitlicher Zusammenhang zu 9.1, kein Ursachennachweis.

### 9.3 Reklamationen Formteil MOD-1042 (laufend)

Ab KW 37 (Periode 10) liegt die Reklamationsneigung des Artikels bei 3,9 % gegenüber rund 1,1 % bei den
übrigen Formteilen; 64 % der Reklamationen nennen eine Maßabweichung. Verantwortlich: Qualität.

### 9.4 Wachstumsengpass Markt NO (laufend)

Die Nachfrage in NO wächst ab KW 20 um 2,5 % je Woche bis auf das 1,45-fache. Die Vertretung verliert ab
KW 30 langsam den Kontakt zu ihren Schlüsselkunden (−0,2 Punkte je Woche), ab KW 41 fällt der Aktivitätsgrad
auf 78,5 %, 77 % und dann 76 %; zugleich steigt die Angebotsdurchlaufzeit um 6, 8 und dann 9,5 Stunden über
den Zielwert. Verantwortlich: Partnermanagement.

### 9.5 Liefertreue Markt PL (behoben)

KW 5–13 liegt die Liefertreue in PL bei 85–87 %; eine Maßnahme ist ab KW 14 wirksam, danach 96,1 %. Die
abgeschlossene Maßnahme vergleicht diese beiden Fenster.

---

## 10. Kontrolldatensatz

`python data/generate_data.py --no-anomalies --out data/dataset_control.json` erzeugt dasselbe Rauschen ohne
die fünf Effekte. Die Erkennung meldet dort keinen einzigen Befund — weder im Wochen- noch im
Artikel-Scanner. `tools/zeige_fehlalarme.py` zeigt, wie viele Fehlalarme jede weggelassene Bedingung der
Regel kosten würde.

---

## 11. Grenzen dieser Daten

- Die Werte sind plausibel konstruiert, nicht gemessen; Zielwerte und Kostensätze sind Annahmen.
- Der Angebotsprozess ist vereinfacht: Entscheidungen fallen in der Woche des Angebots, gewonnene Angebote
  werden sofort Aufträge.
- Preis- und Wettbewerbseffekte sind nicht modelliert; der Wettbewerber in SE ist eine erzählte Ursache, im
  Datensatz nur als Rückgang der Erfolgsquote sichtbar.
- Die Kosten der Optionen in der Entscheidungsvorlage sind Größenordnungen für die Abwägung, keine Kalkulation.
