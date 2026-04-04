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

### 4. Edge Function updaten

Die Supabase Edge Function `get-cheapest-premiums` muss mit den neuen Prämiendaten in der DB gefüttert werden. Das passiert über den bestehenden Import-Prozess.

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
    praemien_2027.csv      # (kommt September 2026)
```

## Insurer-ID Mapping

Die BAG verwendet numerische IDs. Das Mapping ist im Script unter `INSURER_NAMES` gepflegt. Bei neuen Kassen oder Fusionen muss das Mapping aktualisiert werden.
