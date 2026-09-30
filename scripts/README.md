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

### 2. Versichertenbestand laden

Gewichtet die Durchschnitte. Liegt im selben BAG-Ordner wie die Prämien:
`Versichertenbestand_CH.csv` nach `scripts/data/versichertenbestand_YYYY.csv`.

### 3. Seiten erzeugen

```bash
python3 build_kk_pages.py
```

`YEAR`, `DEADLINE` und `BAG_OFFICIAL` (Medienmitteilung des BAG) oben im Script
anpassen. Erzeugt die 26 Kantonsseiten unter `/krankenkasse/`, die Auswertung
`/krankenkassenpraemien-YYYY/`, den Insights-Block der Startseite (zwischen den
`INSIGHTS`-Markern), die Kassenzahl auf Startseite und Methode, `llms.txt`,
`premium-insights.json` und `sitemap.xml`. Die Auswertung des Vorjahres bleibt
als eigene URL stehen. Die Namen der Kassen kommen aus `INSURER_NAMES` in
`premium_analysis.py` (BAG-Verzeichnis der zugelassenen Krankenversicherer).

### 4. In die Datenbank laden und Rechner umschalten

Am besten vor Schritt 3, dann stimmen Rechner und Seiten ab demselben Deploy.

```bash
python3 import_premiums.py 2027 --dry-run   # zählen, Mapping prüfen
python3 import_premiums.py 2027             # schreiben
```

In derselben Datei `ENV_REFUND` um das neue Jahr ergänzen: die Rückverteilung
der Umweltabgaben pro Person und Monat (2026: 5.15, 2027: 4.75). Die Kassen
ziehen sie auf der Rechnung ab; ohne den Wert erkennt der Rechner den Tarif
nicht, wenn jemand seinen Rechnungsbetrag eingibt. Quelle: BAFU bzw. die
Merkblätter der Kassen, meist ab September publiziert.

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
