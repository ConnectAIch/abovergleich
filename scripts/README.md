# Prämienanalyse — Workflow

## Jährlicher Ablauf (September)

Die BAG veröffentlicht die neuen Prämien jeweils **Ende September**. Dann:

### 1. Neue Daten herunterladen

```bash
cd scripts/

# Aktuelles Jahr von opendata.swiss laden
python3 premium_analysis.py --download-current

# Oder spezifisches Jahr
python3 premium_analysis.py --download 2027
```

Die CSV wird nach `scripts/data/praemien_YYYY.csv` gespeichert.

### 2. Analyse starten

```bash
# Vollständiger Report (Terminal-Output)
python3 premium_analysis.py --report

# Report + JSON für Website generieren
python3 premium_analysis.py --export
```

Generiert `premium-insights.json` im Projekt-Root.

### 3. Website aktualisieren

Die Insights-Sektion in `index.html` muss manuell mit den neuen Zahlen aktualisiert werden (oder automatisiert via das JSON).

### 4. In die Datenbank laden und Rechner umschalten

```bash
python3 import_premiums.py 2027 --dry-run   # zählen, Mapping prüfen
python3 import_premiums.py 2027             # schreiben
```

Vorjahre bleiben in `premiums` (für Vergleiche und Auswertungen). Welches Jahr
der Rechner zeigt, steht als `PREMIUM_YEAR` in
`supabase/functions/get-cheapest-premiums/index.ts`. Reihenfolge beachten:
die Funktion filtert nach Jahr, also erst importieren, dann `PREMIUM_YEAR`
anheben und die Funktion deployen. Die Jahreszahl im Rechner kommt aus der
Antwort der Funktion.

Ab 2027 hat das BAG die Codes im CSV umgestellt (`PR_REG_0`, `AKA_03_ERW`,
`FRA_01_E_0300`, Tariftypen `BASE/PRAXIS/FLEX/TEL_DIG/PHARM`). Das Mapping
auf unser Format steht im Kopf von `import_premiums.py`.

## Datenquellen

- **opendata.swiss**: https://opendata.swiss/en/dataset/health-insurance-premiums
- **BAG API**: https://opendata.bagnet.ch/ (CKAN, base64-encoded Pfade)
- **Archiv-ZIPs**: Enthalten Prämien-CSV ab 2025, ältere Jahre nur als XLSX
- **Aktuelles Jahr**: Immer als separate `Prämien_CH.csv` auf opendata.swiss

## Analyse-Dimensionen

1. **Prämienveränderung pro Versicherer** vs. Durchschnitt (wer erhöht mehr/weniger)
2. **Konstanz-Ranking**: Wer ist dauerhaft in Top 3 günstigste pro Kanton
3. **Modell-Rotation**: Welches Modell (Standard/HMO/Hausarzt/Alternativ) ist günstigstes
4. **Kantonsanalyse**: Günstigster Versicherer pro Kanton, Stabilität über Jahre

## Daten-Struktur

```
scripts/
  premium_analysis.py     # Haupt-Script
  README.md               # Diese Datei
  data/
    praemien_2025.csv      # BAG Prämiendaten 2025
    praemien_2026.csv      # BAG Prämiendaten 2026
    praemien_2027.csv      # BAG Prämiendaten 2027 (publiziert Ende Sept. 2026)
```

## Insurer-ID Mapping

Die BAG verwendet numerische IDs. Das Mapping ist im Script unter `INSURER_NAMES` gepflegt. Bei neuen Kassen oder Fusionen muss das Mapping aktualisiert werden.
