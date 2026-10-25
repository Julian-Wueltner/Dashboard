"""Zeigt, warum die Erkennungsregel so streng ist, wie sie ist.

    python tools/zeige_fehlalarme.py

Das Skript laesst vier Regelfassungen auf denselben **Kontrolldatensatz** laufen --
auf Daten also, in die absichtlich kein einziges Problem eingebaut wurde. Was eine
Regel dort meldet, ist per Definition ein Fehlalarm.

Warum es das gibt
-----------------
Im Interview-Briefing steht der Satz: "Auf einem Kontrolldatensatz ohne eingebaute
Probleme findet die automatische Analyse null Auffaelligkeiten. Ein roher
Schwellenwertscan meldet auf genau denselben Daten 31 Auffaelligkeiten -- alles
Fehlalarme."

Das ist die staerkste Aussage ueber die Analyse. Dieses Skript macht sie
vorfuehrbar: Es rechnet die Zahlen in wenigen Sekunden neu aus, auf Wunsch vor
den Augen des Gespraechspartners.

Die vier Stufen entsprechen den Bedingungen der Erkennungsregel.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data"))

CONTROL = ROOT / "data" / "dataset_control.json"

import analysis as an  # noqa: E402


def kontrolldatensatz() -> Path:
    """Erzeugt den Kontrolldatensatz, falls er fehlt (er steht in .gitignore)."""
    if CONTROL.exists():
        return CONTROL
    print("Kontrolldatensatz wird erzeugt ...")
    subprocess.run(
        [sys.executable, str(ROOT / "data" / "generate_data.py"),
         "--no-anomalies", "--quiet", "--out", str(CONTROL)],
        cwd=ROOT, check=True, capture_output=True,
    )
    return CONTROL


def zaehle(dataset, *, zscore: bool, mindestabweichung: bool,
           zielwert: bool, vergleichsgruppe: bool) -> int:
    """Zaehlt die Befunde unter einer bestimmten Regelfassung.

    Die vier Schalter bilden die vier Bedingungen der Regel ab. Sie werden hier
    nicht nachgebaut, sondern an die echte Erkennung in ``data/analysis.py``
    durchgereicht -- sonst wuerde das Skript etwas anderes messen als das Tool.
    """
    return len(an.scan_weekly(dataset, rule={
        "use_zscore": zscore,
        "use_min_effect": mindestabweichung,
        "use_target": zielwert,
        "use_peer_group": vergleichsgruppe,
    }))


STUFEN = [
    ("1. Nur z-Wert ab 2,5, zwei Wochen in Folge",
     dict(zscore=True, mindestabweichung=False, zielwert=False, vergleichsgruppe=False),
     "Der naive Ansatz: alles melden, was statistisch aus der Reihe faellt."),
    ("2. + fachliche Mindestabweichung",
     dict(zscore=True, mindestabweichung=True, zielwert=False, vergleichsgruppe=False),
     "Kleine Ausschlaege verschwinden, Saisonbewegungen bleiben."),
    ("3. + Vergleich gegen das uebrige Geschaeft derselben Woche (OP-A2)",
     dict(zscore=True, mindestabweichung=True, zielwert=False, vergleichsgruppe=True),
     "Was alle gleichzeitig trifft, ist der Kalender und keine Auffaelligkeit."),
    ("4. + Verletzung des vereinbarten Zielwerts (OP-A1) -- geltende Regel",
     dict(zscore=True, mindestabweichung=True, zielwert=True, vergleichsgruppe=True),
     "Gemeldet wird nur, was auffaellig, relevant gross und ausserhalb des Vereinbarten ist."),
]


def main() -> int:
    pfad = kontrolldatensatz()
    dataset = an.load_dataset(pfad)

    print()
    print("Fehlalarme auf dem Kontrolldatensatz")
    print("=" * 74)
    print("Der Kontrolldatensatz enthaelt dasselbe Rauschen wie der Echtdatensatz,")
    print("aber kein einziges eingebautes Problem. Jeder Befund ist ein Fehlalarm.")
    print()

    for titel, schalter, erklaerung in STUFEN:
        treffer = zaehle(dataset, **schalter)
        print(f"{treffer:4d} Fehlalarme   {titel}")
        print(f"                {erklaerung}")
        print()

    print("=" * 74)
    echt = an.load_dataset(ROOT / "data" / "dataset.json")
    gefunden = zaehle(echt, **STUFEN[-1][1])
    print(f"Zur Gegenprobe: Dieselbe Regel findet im Echtdatensatz {gefunden} Auffaelligkeiten.")
    print("Eine Regel, die nichts meldet, waere ebenso wertlos wie eine, die alles meldet.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
