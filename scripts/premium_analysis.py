#!/usr/bin/env python3
"""
Jährliche Prämienanalyse für abovergleich.com
=============================================

Dieses Script analysiert BAG-Prämiendaten über mehrere Jahre und generiert:
1. Prämienveränderung pro Versicherer vs. Durchschnitt
2. Günstigster Versicherer pro Kanton (Stabilität)
3. Modell-Rotation (welches Modell ist günstigstes pro Jahr)
4. Konstanz-Ranking (wer ist dauerhaft in Top 3)

WORKFLOW (jedes Jahr im September):
  1. Neue Prämiendaten erscheinen auf opendata.swiss (ca. Ende September)
  2. Download: python3 premium_analysis.py --download 2027
  3. Import in Supabase: python3 premium_analysis.py --import 2027
  4. Analyse starten: python3 premium_analysis.py --analyze
  5. JSON für Website generieren: python3 premium_analysis.py --export

Datenquelle: https://opendata.swiss/en/dataset/health-insurance-premiums
API: https://opendata.bagnet.ch/ (CKAN-basiert, base64-encoded Pfade)
"""

import csv
import json
import os
import sys
import subprocess
from collections import defaultdict
from base64 import b64encode
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────────────────

DATA_DIR = Path(__file__).parent / "data"
OUTPUT_DIR = Path(__file__).parent.parent  # project root for website JSON

INSURER_NAMES = {
    "8": "CSS", "32": "Concordia", "134": "Visana", "194": "Atupri",
    "246": "Aquilana", "290": "Galenos", "312": "Helsana", "343": "Intras",
    "360": "Sanitas", "376": "KPT", "455": "ÖKK", "509": "Progrès",
    "780": "Rhenusana", "820": "Sanitas", "881": "Sympany", "923": "Swica",
    "941": "Vivao Sympany", "966": "Wincare", "1040": "EGK",
    "1113": "Groupe Mutuel", "1318": "Assura", "1322": "Helsana",
    "1384": "Mutuel Assurance", "1386": "KPT", "1401": "Groupe Mutuel",
    "1479": "Helsana", "1507": "CSS", "1509": "Swica", "1535": "Assura",
    "1542": "KPT", "1555": "Groupe Mutuel", "1560": "KPT", "1562": "Assura",
    "1568": "Helsana", "1570": "Groupe Mutuel",
    "829": "Visana", "901": "Swica",
}

# Consolidate sub-brands to parent brand for cleaner analysis
BRAND_CONSOLIDATION = {
    "Intras": "CSS",
    "Progrès": "Helsana",
    "Wincare": "Sanitas",
    "Vivao Sympany": "Sympany",
    "Mutuel Assurance": "Groupe Mutuel",
}

TARIF_TO_MODEL = {
    "TAR-BASE": "standard",
    "TAR-HAM": "hausarzt",
    "TAR-HMO": "hmo",
    "TAR-DIV": "diverse",
}

MODEL_LABELS = {
    "standard": "Standard (freie Arztwahl)",
    "hausarzt": "Hausarzt",
    "hmo": "HMO",
    "diverse": "Alternativ",
}

CANTONS = [
    "AG", "AI", "AR", "BE", "BL", "BS", "FR", "GE", "GL", "GR",
    "JU", "LU", "NE", "NW", "OW", "SG", "SH", "SO", "SZ", "TG",
    "TI", "UR", "VD", "VS", "ZG", "ZH",
]


# ── Download ────────────────────────────────────────────────────────────────

def download_year(year: int):
    """Download BAG premium archive for a given year from opendata.swiss."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = DATA_DIR / f"praemien_{year}.csv"

    if csv_path.exists():
        print(f"  {csv_path} existiert bereits, überspringe Download.")
        return csv_path

    # The archive ZIPs use base64-encoded paths
    zip_path = f"/Praemien/Archiv_Praemien_{year}.zip"
    encoded = b64encode(zip_path.encode()).decode()
    url = f"https://opendata.bagnet.ch/?r=/download&path={encoded}"

    zip_file = DATA_DIR / f"archive_{year}.zip"
    print(f"  Downloading {year} from opendata.bagnet.ch...")
    subprocess.run(["curl", "-sL", "-o", str(zip_file), url], check=True)

    # Extract
    extract_dir = DATA_DIR / f"tmp_{year}"
    extract_dir.mkdir(exist_ok=True)
    subprocess.run(["unzip", "-o", str(zip_file), "-d", str(extract_dir)],
                   capture_output=True, check=True)

    # Find the premium CSV (Prämien_CH.csv)
    found = list(extract_dir.glob("*CH.csv"))
    praemien_files = [f for f in found if "mien" in f.name.lower() or "raemien" in f.name.lower()]

    if praemien_files:
        praemien_files[0].rename(csv_path)
        print(f"  ✓ Prämien-CSV gefunden: {csv_path}")
    else:
        # For years before 2025, the CSV might not be in the archive
        # Try downloading from the main opendata.swiss endpoint
        print(f"  ⚠ Keine Prämien-CSV im Archiv für {year}.")
        print(f"    Für Jahre vor 2025 sind die Prämien nur als XLSX verfügbar.")
        print(f"    Alternative: XLSX manuell zu CSV konvertieren.")

    # Cleanup
    import shutil
    shutil.rmtree(extract_dir, ignore_errors=True)
    zip_file.unlink(missing_ok=True)

    return csv_path


def download_current_year():
    """Download current year's premium data from opendata.swiss main endpoint."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    path = "/Praemien/Prämien_CH.csv"
    encoded = b64encode(path.encode()).decode()
    url = f"https://opendata.bagnet.ch/?r=/download&path={encoded}"

    csv_path = DATA_DIR / "praemien_current.csv"
    print(f"  Downloading current year from opendata.bagnet.ch...")
    subprocess.run(["curl", "-sL", "-o", str(csv_path), url], check=True)

    # Detect year from first data row
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        row = next(reader)
        year = row.get("Geschäftsjahr", row.get("Gesch\xe4ftsjahr", "unknown"))

    final_path = DATA_DIR / f"praemien_{year}.csv"
    csv_path.rename(final_path)
    print(f"  ✓ Aktuelles Jahr: {year} → {final_path}")
    return final_path


# ── Loading ─────────────────────────────────────────────────────────────────

def detect_csv_format(filepath):
    """Detect delimiter and encoding of a BAG CSV file."""
    for encoding in ["utf-8-sig", "utf-8", "latin-1", "cp1252"]:
        try:
            with open(filepath, "r", encoding=encoding) as f:
                first_line = f.readline()
                delimiter = ";" if ";" in first_line else ","
                return delimiter, encoding
        except (UnicodeDecodeError, UnicodeError):
            continue
    raise ValueError(f"Cannot detect encoding for {filepath}")


def load_premiums(filepath, filter_adults=True, filter_franchise=300,
                  filter_accident=True, consolidate_brands=False):
    """Load premium data from a BAG CSV file.

    Args:
        filepath: Path to CSV
        filter_adults: Only include AKL-ERW (adults 26+)
        filter_franchise: Filter by franchise amount (300, 500, 1000, etc.)
        filter_accident: Only include MIT-UNF (with accident coverage)
        consolidate_brands: Merge sub-brands into parent brands
    """
    delimiter, encoding = detect_csv_format(filepath)
    rows = []

    franchise_values = {f"FRA-{filter_franchise}", str(filter_franchise)}
    accident_values = {"MIT-UNF", "true", "True"}

    with open(filepath, "r", encoding=encoding) as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        for row in reader:
            if filter_adults and row.get("Altersklasse") != "AKL-ERW":
                continue
            if filter_franchise and row.get("Franchise") not in franchise_values:
                continue
            if filter_accident and row.get("Unfalleinschluss") not in accident_values:
                continue

            vid = row["Versicherer"].lstrip("0")
            name = INSURER_NAMES.get(vid, f"ID:{vid}")
            if consolidate_brands:
                name = BRAND_CONSOLIDATION.get(name, name)

            premium = float(row.get("Prämie", "0").replace(",", "."))
            model = TARIF_TO_MODEL.get(row.get("Tariftyp", ""), "unknown")
            year = int(row.get("Geschäftsjahr", row.get("Gesch\xe4ftsjahr", 0)))

            rows.append({
                "insurer_id": vid,
                "name": name,
                "premium": premium,
                "model": model,
                "region": row.get("Region", ""),
                "canton": row.get("Kanton", ""),
                "tariff_name": row.get("Tarifbezeichnung", ""),
                "year": year,
            })

    return rows


def load_all_years():
    """Load all available years from data directory."""
    all_data = {}
    for csv_file in sorted(DATA_DIR.glob("praemien_*.csv")):
        year_str = csv_file.stem.replace("praemien_", "")
        if not year_str.isdigit():
            continue
        year = int(year_str)
        data = load_premiums(csv_file)
        if data:
            all_data[year] = data
            print(f"  {year}: {len(data)} rows loaded")
    return all_data


# ── Analysis ────────────────────────────────────────────────────────────────

def analyze_premium_changes(all_data):
    """Compare premium changes per insurer across years."""
    years = sorted(all_data.keys())
    if len(years) < 2:
        print("  ⚠ Mindestens 2 Jahre nötig für Vergleich.")
        return {}

    results = {}
    for i in range(1, len(years)):
        prev_year = years[i - 1]
        curr_year = years[i]
        key = f"{prev_year}→{curr_year}"

        avg_prev = defaultdict(list)
        avg_curr = defaultdict(list)

        for r in all_data[prev_year]:
            if r["model"] == "standard":
                avg_prev[r["name"]].append(r["premium"])
        for r in all_data[curr_year]:
            if r["model"] == "standard":
                avg_curr[r["name"]].append(r["premium"])

        avg_prev = {k: sum(v) / len(v) for k, v in avg_prev.items()}
        avg_curr = {k: sum(v) / len(v) for k, v in avg_curr.items()}

        common = set(avg_prev.keys()) & set(avg_curr.keys())
        if not common:
            continue

        total_prev = sum(avg_prev[k] for k in common) / len(common)
        total_curr = sum(avg_curr[k] for k in common) / len(common)
        total_pct = ((total_curr - total_prev) / total_prev) * 100

        changes = []
        for name in common:
            p_prev = avg_prev[name]
            p_curr = avg_curr[name]
            pct = ((p_curr - p_prev) / p_prev) * 100
            changes.append({
                "name": name,
                "prev": round(p_prev, 2),
                "curr": round(p_curr, 2),
                "change_pct": round(pct, 1),
                "vs_avg": round(pct - total_pct, 1),
            })

        changes.sort(key=lambda x: x["change_pct"])
        results[key] = {
            "avg_change": round(total_pct, 1),
            "avg_prev": round(total_prev, 2),
            "avg_curr": round(total_curr, 2),
            "insurers": changes,
        }

    return results


def analyze_cheapest_per_canton(all_data):
    """Find cheapest insurer per canton across years."""
    years = sorted(all_data.keys())
    results = {}

    for year in years:
        by_canton = defaultdict(list)
        for r in all_data[year]:
            if r["model"] == "standard" and r["canton"] in CANTONS:
                by_canton[r["canton"]].append(r)

        cheapest = {}
        for canton, rows in by_canton.items():
            seen = {}
            for row in sorted(rows, key=lambda x: x["premium"]):
                if row["name"] not in seen:
                    seen[row["name"]] = row
            if seen:
                cheapest[canton] = list(seen.values())[0]

        results[year] = cheapest

    return results


def analyze_model_rotation(all_data):
    """Check which model is cheapest per canton per year."""
    years = sorted(all_data.keys())
    results = {}

    for year in years:
        by_canton = defaultdict(list)
        for r in all_data[year]:
            if r["canton"] in CANTONS:
                by_canton[r["canton"]].append(r)

        cheapest = {}
        model_counts = defaultdict(int)
        for canton, rows in by_canton.items():
            rows.sort(key=lambda x: x["premium"])
            if rows:
                cheapest[canton] = {
                    "model": rows[0]["model"],
                    "name": rows[0]["name"],
                    "premium": rows[0]["premium"],
                }
                model_counts[rows[0]["model"]] += 1

        results[year] = {
            "cheapest_per_canton": cheapest,
            "model_distribution": dict(model_counts),
        }

    return results


def analyze_consistency(all_data):
    """Which insurers are consistently in top 3 cheapest?"""
    years = sorted(all_data.keys())
    consistency = defaultdict(lambda: defaultdict(int))

    for year in years:
        by_canton = defaultdict(list)
        for r in all_data[year]:
            if r["model"] == "standard" and r["canton"] in CANTONS:
                by_canton[r["canton"]].append(r)

        for canton, rows in by_canton.items():
            seen = {}
            for row in sorted(rows, key=lambda x: x["premium"]):
                if row["name"] not in seen:
                    seen[row["name"]] = row
            for name in list(seen.keys())[:3]:
                consistency[name][year] += 1

    return dict(consistency)


# ── Export ──────────────────────────────────────────────────────────────────

def export_website_json(all_data):
    """Generate JSON for website insights section."""
    changes = analyze_premium_changes(all_data)
    consistency = analyze_consistency(all_data)
    model_rotation = analyze_model_rotation(all_data)
    years = sorted(all_data.keys())

    # Build website-ready data
    website_data = {
        "generated": str(Path(__file__).stat().st_mtime),
        "years": years,
        "premium_changes": {},
        "consistency_ranking": [],
        "model_trends": {},
    }

    # Premium changes (latest comparison)
    if changes:
        latest_key = list(changes.keys())[-1]
        latest = changes[latest_key]
        website_data["premium_changes"] = {
            "period": latest_key,
            "average_change": latest["avg_change"],
            "below_average": [i for i in latest["insurers"] if i["vs_avg"] < -1],
            "above_average": [i for i in latest["insurers"] if i["vs_avg"] > 1],
        }

    # Consistency ranking
    n_cantons = len(CANTONS)
    for name, year_counts in sorted(consistency.items(),
                                     key=lambda x: -sum(x[1].values())):
        total = sum(year_counts.values())
        if total >= 5:
            website_data["consistency_ranking"].append({
                "name": name,
                "total_top3_appearances": total,
                "per_year": {str(y): year_counts.get(y, 0) for y in years},
                "consistency_score": round(total / (len(years) * n_cantons) * 100, 1),
            })

    # Model trends
    for year in years:
        if year in model_rotation:
            website_data["model_trends"][str(year)] = model_rotation[year]["model_distribution"]

    output_path = OUTPUT_DIR / "premium-insights.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(website_data, f, ensure_ascii=False, indent=2)
    print(f"  ✓ Website-JSON exportiert: {output_path}")

    return website_data


# ── Print Report ────────────────────────────────────────────────────────────

def print_report(all_data):
    """Print full analysis report to console."""
    years = sorted(all_data.keys())
    print(f"\n{'='*80}")
    print(f"PRÄMIENANALYSE — {min(years)} bis {max(years)}")
    print(f"{'='*80}")
    print(f"Filter: Erwachsene (26+), Franchise 300, mit Unfall")
    print(f"Jahre: {', '.join(str(y) for y in years)}")

    # 1. Premium changes
    changes = analyze_premium_changes(all_data)
    for period, data in changes.items():
        print(f"\n{'─'*80}")
        print(f"PRÄMIENVERÄNDERUNG {period}")
        print(f"Durchschnitt: {data['avg_prev']:.2f} → {data['avg_curr']:.2f} ({data['avg_change']:+.1f}%)")
        print(f"\n{'Versicherer':<20} {'Vorjahr':>10} {'Aktuell':>10} {'Änderung':>10} {'vs. Ø':>8}")
        print("-" * 62)
        for ins in data["insurers"]:
            marker = "▼" if ins["vs_avg"] < -1 else ("▲" if ins["vs_avg"] > 1 else " ")
            print(f"{ins['name']:<20} {ins['prev']:>10.2f} {ins['curr']:>10.2f} "
                  f"{ins['change_pct']:>+9.1f}% {ins['vs_avg']:>+7.1f}% {marker}")

    # 2. Consistency
    print(f"\n{'─'*80}")
    print("KONSTANZ-RANKING (Top 3 pro Kanton, Standard-Modell)")
    consistency = analyze_consistency(all_data)
    sorted_cons = sorted(consistency.items(), key=lambda x: -sum(x[1].values()))
    print(f"\n{'Versicherer':<20}", end="")
    for y in years:
        print(f" {y:>6}", end="")
    print(f" {'Total':>8}")
    print("-" * (28 + 7 * len(years)))
    for name, year_counts in sorted_cons:
        total = sum(year_counts.values())
        if total < 5:
            continue
        print(f"{name:<20}", end="")
        for y in years:
            print(f" {year_counts.get(y, 0):>6}", end="")
        print(f" {total:>8}")

    # 3. Model rotation
    print(f"\n{'─'*80}")
    print("MODELL-VERTEILUNG (günstigstes Modell pro Kanton)")
    rotation = analyze_model_rotation(all_data)
    for year in years:
        dist = rotation[year]["model_distribution"]
        print(f"  {year}: {dist}")


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nUsage:")
        print("  python3 premium_analysis.py --download 2027     # Download year")
        print("  python3 premium_analysis.py --download-current  # Download current year")
        print("  python3 premium_analysis.py --analyze           # Run full analysis")
        print("  python3 premium_analysis.py --export            # Generate website JSON")
        print("  python3 premium_analysis.py --report            # Print full report")
        print("  python3 premium_analysis.py --all               # Download + analyze + export")
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "--download":
        year = int(sys.argv[2])
        download_year(year)

    elif cmd == "--download-current":
        download_current_year()

    elif cmd == "--analyze" or cmd == "--report":
        print("Loading all available years...")
        all_data = load_all_years()
        if not all_data:
            print("No data found! Run --download first.")
            sys.exit(1)
        print_report(all_data)

    elif cmd == "--export":
        print("Loading all available years...")
        all_data = load_all_years()
        if not all_data:
            print("No data found! Run --download first.")
            sys.exit(1)
        print_report(all_data)
        export_website_json(all_data)

    elif cmd == "--all":
        if len(sys.argv) > 2:
            year = int(sys.argv[2])
            download_year(year)
        download_current_year()
        print("\nLoading all available years...")
        all_data = load_all_years()
        print_report(all_data)
        export_website_json(all_data)

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
