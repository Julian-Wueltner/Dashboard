# International Sales Cockpit

**Arbeitsprobe von Julian Wültner — Steuerung des internationalen Vertriebs eines Industrieherstellers**

> Demo mit fiktiven Daten · eigene Initiative · erstellt mit KI-Unterstützung

## In 3 Minuten ansehen

<!-- TOOL_URL:BEGIN -->
**▶ [Cockpit öffnen](https://julian-wueltner.github.io/Dashboard/)** — läuft direkt im Browser, ohne Installation
<!-- TOOL_URL:END -->

**▶ [Case Study als PDF](case-study/Case_Study_Julian_Wueltner.pdf)** — der Fall auf zwei Seiten als Management-Report

Im Cockpit oben auf **„Demo-Fall starten"** klicken: Eine geführte Tour zeigt in sechs Schritten, wie aus
einer auffälligen Kennzahl eine Entscheidungsvorlage für die Geschäftsleitung wird.

---

## Worum es geht

Ein fiktiver Hersteller von Metallkomponenten für den Anlagenbau verkauft in zehn europäische Länder — über
eigene Tochtergesellschaften, über Handelsvertretungen und direkt ab Werk. Das Cockpit zeigt auf einen Blick,
wie die Märkte und Vertriebspartner gegenüber Ziel und Vorjahr dastehen, weist selbstständig auf Probleme hin
und hilft, daraus Maßnahmen und Entscheidungen abzuleiten.

Die Arbeitsprobe zeigt damit eine vollständige Fallbearbeitung: **Problem erkennen → Ursache eingrenzen →
Optionen bewerten → Empfehlung an die Geschäftsleitung.** Alle Daten sind erfunden; es werden keine realen
Unternehmen, Marken oder Dienstleister dargestellt.

---

## Welche Aufgaben das Cockpit abdeckt

| Aufgabe im internationalen Vertrieb | Bereich im Cockpit | Was dort zu sehen ist |
|---|---|---|
| **Marktanalyse** — wie stehen die Märkte gegen Ziel und Vorjahr? | **Übersicht** | Zehn Kennzahlen mit Ampel und Trend, filterbar nach Land, Vertriebsweg, Vertriebspartner und Zeitraum. Jede Kennzahl ist einem verantwortlichen Fachbereich zugeordnet. |
| **Vertriebsprozess steuern** — wo klemmt es zwischen Anfrage und Kundendienst? | **Vertriebsprozess** | Fünf Stufen von der Anfrage bis zum After-Sales, je Stufe Bearbeitungsdauer, Zielwert und verantwortlicher Bereich; der Engpass ist hervorgehoben. |
| **Partner führen** — Tochtergesellschaften und Handelsvertretungen | **Partner-Scorecard** | Je Partner: Anteil gewonnener Angebote, Liefertreue, Ertrag je Auftrag, Aktivität und eine Gesamtampel; dazu die Auslastung jedes Partners. |
| **Handlungsfelder erkennen** | **Auffälligkeiten** | Das Cockpit meldet von selbst, was sich deutlich verschlechtert hat und wirklich relevant ist — mit geschätzter Auswirkung, wo möglich in Euro. |
| **Projekte umsetzen** — von der Planung bis zur Erfolgskontrolle | **Maßnahmen** | Aus einer Auffälligkeit wird per Klick eine Maßnahme mit Phasen, Verantwortlichem und Terminen. Eine abgeschlossene Maßnahme zeigt den **Vorher-nachher-Vergleich**. |
| **Marktaufbau planen** | **Wachstumsszenario** | Per Schieberegler mehr Volumen simulieren und prüfen, ab wann die Vertretungen an ihre Grenzen stoßen und was eine eigene Tochtergesellschaft in Skandinavien ändern würde. |
| **Entscheidungsvorlagen und Reports** | **Report & Entscheidungsvorlage** | Ein Klick erzeugt einen druckfertigen Management-Report und eine Entscheidungsvorlage mit drei bewerteten Optionen und klarer Empfehlung. |

---

## Der Fall, den die Demo erzählt

Das Cockpit findet in den Daten von selbst vier Probleme (KW = Kalenderwoche):

1. **Schweden:** Ab KW 32 gewinnt die Vertretung nur noch rund 21 % statt 34 % ihrer Angebote — ein neuer
   lokaler Wettbewerber ist aufgetreten.
2. **Schweden, eine Woche später:** Angebote brauchen rund 39 statt 22 Stunden, weil mehr nachverhandelt
   wird. Das Cockpit weist das als zeitlichen Zusammenhang aus, nicht als bewiesene Ursache.
3. **Ein bestimmtes Bauteil** wird ab KW 37 deutlich häufiger reklamiert als vergleichbare Teile, meist
   wegen Maßabweichungen.
4. **Norwegen** wächst stark; ab KW 41 kommt die dortige Vertretung nicht mehr hinterher. Daraus entsteht
   das Wachstumsszenario.

Ein fünftes Problem — unpünktliche Lieferungen nach Polen — wurde schon früher im Jahr behoben und zeigt, wie
eine abgeschlossene Maßnahme bewertet wird.

**Die Entscheidung für Schweden:** Die Vorlage vergleicht drei Wege — **A** Preise senken, **B** eine eigene
Vertriebsgesellschaft in Skandinavien gründen, **C** die bestehende Vertretung mit Zielvereinbarung und
Schulung stärken. Empfohlen wird **C**, mit einer klaren Regel: Bleibt die Erfolgsquote acht Wochen danach
unter dem Ziel, wird Option B vorbereitet.

---

## Grenzen dieser Demo

- **Erfundene Daten.** Plausibel konstruiert, aber nicht gemessen. Die Zielwerte sind begründete Annahmen.
- **Kein Ursachennachweis.** Zusammenhänge zwischen zwei Problemen werden als zeitlich, nicht als ursächlich
  ausgewiesen.
- **Keine Prognose.** Das Wachstumsszenario ist eine nachvollziehbare Modellrechnung, keine Vorhersage.
- **Nichts wird gespeichert.** Im Cockpit angelegte Maßnahmen verschwinden beim Neuladen der Seite.

## Entstehung

Julian Wültner hat Ziel, Inhalte und Entscheidungen vorgegeben, ein Team spezialisierter KI-Agenten hat die
technische Umsetzung übernommen, Julian hat geprüft und abgenommen. Die fachlichen Entscheidungen —
Kennzahlen, Zielwerte, Bewertung der Optionen und die Empfehlung — stammen von Julian.

---
---

## Für technisch Interessierte

Alles ab hier richtet sich an Leser, die nachvollziehen möchten, wie das Cockpit gebaut und geprüft ist.

### Wie die automatische Analyse arbeitet

Sie vergleicht jede Kennzahl mit den **letzten acht Wochen** (bei Beginn einer Abweichung eingefroren), mit
dem **übrigen Geschäft derselben Woche** und mit dem **vereinbarten Zielwert**. Gemeldet wird nur, was
statistisch auffällig (z-Wert ab 2,5) **und** fachlich relevant ist und den Zielwert verletzt — und das
**zwei Wochen hintereinander**. Verbesserungen lösen keinen Alarm aus, und Auswertungen unterhalb einer
Mindeststichprobe werden gar nicht erst bewertet.

Das ist bewusst **keine** künstliche Intelligenz, sondern eine offengelegte Rechenregel. Jeder Erklärungstext
im Tool ist als „automatisch erstellt" gekennzeichnet. Eine Anbindung an ein Sprachmodell ist nicht
gebaut, und es werden keine Zugangsschlüssel gespeichert.

Ob die Regel nicht einfach alles meldet, rechnet `tools/zeige_fehlalarme.py` auf einem Datensatz ohne
eingebaute Probleme vor:

```
  12 Fehlalarme   nur z-Wert ab 2,5, zwei Wochen in Folge
   0 Fehlalarme   + fachliche Mindestabweichung
   0 Fehlalarme   + Vergleich gegen das übrige Geschäft derselben Woche
   0 Fehlalarme   + Verletzung des vereinbarten Zielwerts (geltende Regel)
```

### Eine einzige Datenquelle

Jede Zahl in Tool, Report und Case Study stammt aus derselben erzeugten Datenbasis. Keine Zahl ist von Hand
in einen Text geschrieben:

```
data/generate_data.py  ->  data/dataset.json   (nur additive Messgrößen)
                             |
                             v
data/compute_metrics.py ->  data/metrics.json  (alle abgeleiteten und formatierten Zahlen)
                             |
              +--------------+--------------+
              v                             v
       data/build_app.py            case-study/build_case_study.py
   (bettet Daten in index.html)   (füllt die Platzhalter der Vorlage)
```

Der Datensatz speichert nur Größen, die man addieren darf — „entschiedene Angebote" und „davon gewonnen",
nicht „Erfolgsquote 34 %". Jede Quote entsteht erst durch Division zweier Summen. Nur so liefert jeder Filter
im Cockpit dieselbe Zahl wie die Auswertung im Report. Die Vorlage der Case Study enthält **keine einzige
Ziffer**; ein Test schlägt fehl, sobald dort eine Zahl von Hand eingetragen wird.

### Selbst bauen und prüfen

Lokal genügt es, `app/index.html` per Doppelklick zu öffnen — kein Server, kein Build. Neu bauen:

```bash
python -m pip install -r requirements.txt
python build.py                       # baut die ganze Kette und laesst danach alle Tests laufen
```

Oder Schritt für Schritt:

```bash
python data/generate_data.py          # Datensatz erzeugen (fester Seed, reproduzierbar)
python data/compute_metrics.py        # Kennzahlen und automatische Analyse berechnen
python data/build_app.py              # Daten in app/index.html einbetten
python case-study/build_case_study.py # Case Study rendern und als PDF ausgeben

python -m pytest tests/ -q            # Python-Tests
node --test "tests/js/*.test.mjs"     # Test des JavaScript-Rechenkerns
node tools/check_app.mjs             # Cockpit im Browser starten, Fehler und Ladezeit melden
node tools/check_app.mjs --offline   # dasselbe ohne Netz: Wertetabellen ersetzen die Diagramme
node tools/check_ui.mjs              # zwanzig harte Aussagen über das gerenderte Dokument
node tools/check_print.mjs           # Report und Entscheidungsvorlage: je genau eine A4-Seite
python tools/zeige_fehlalarme.py     # Fehlalarme je Stufe der Erkennungsregel
```

Voraussetzungen: Python 3.11 oder neuer, Node 18 oder neuer (nur für den JavaScript-Test), ein installierter
Chromium-Browser (Chrome oder Edge) für die PDF-Ausgabe.

### Aufbau des Repositorys

| Pfad | Inhalt |
|---|---|
| `app/index.html` | Das Cockpit — eine einzige selbstständige Datei |
| `index.html`, `.nojekyll` | Weiterleitung auf `app/` und Einstellung für GitHub Pages |
| `data/generate_data.py` | Datengenerator mit festem Seed; `--no-anomalies` erzeugt den Kontrolldatensatz |
| `data/analysis.py` | Kennzahlenformeln, automatische Analyse, Wirkungsabschätzung, Szenariomodell |
| `data/compute_metrics.py` | Erzeugt `data/metrics.json` aus `data/dataset.json` |
| `data/formatting.py` | Die einzige Formatierungsinstanz des Projekts (deutsches Zahlenformat) |
| `data/build_app.py` | Bettet Datensatz und Kennzahlen in `app/index.html` ein |
| `build.py` | Baut die gesamte Kette in der richtigen Reihenfolge und testet |
| `tools/` | Browser-, Druck- und PDF-Prüfungen, Fehlalarm-Rechnung |
| `case-study/` | Vorlage, Build-Skript, gerenderte Case Study und PDF |
| `tests/` | Berechnungen, Anomalieerkennung, Datenkonsistenz, harte Regeln, JavaScript-Rechenkern |

### Dokumentation

| Dokument | Wofür |
|---|---|
| [`docs/KPI_DEFINITIONS.md`](docs/KPI_DEFINITIONS.md) | Jede Kennzahl mit Formel, Einheit, Zielwert und Fachbereich |
| [`docs/DATA_ASSUMPTIONS.md`](docs/DATA_ASSUMPTIONS.md) | Welche Annahmen im Datensatz stecken und warum sie plausibel sind |
