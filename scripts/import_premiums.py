#!/usr/bin/env python3
"""
BAG-Prämien eines Jahres in die Supabase-Tabelle `premiums` laden.

    python3 import_premiums.py 2027 --dry-run   # nur prüfen und zählen
    python3 import_premiums.py 2027             # schreiben
    python3 import_premiums.py 2027 --replace   # Jahr vorher löschen

Liest scripts/data/praemien_YYYY.csv (siehe premium_analysis.py --download).
Ältere Jahre bleiben in der Tabelle, für Vergleiche und Auswertungen. Welches
Jahr der Rechner zeigt, steht in der Edge Function `get-cheapest-premiums`.

Das BAG hat mit den Prämien 2027 die Codes im CSV umgestellt. Wir schreiben
beide Formate in dieselbe Form wie 2026, damit Jahre direkt vergleichbar sind:

    Region          PR_REG_0      -> PR-REG CH0
    Altersklasse    AKA_03_ERW    -> AKL-ERW
    Franchise       FRA_01_E_0300 -> 300
    Unfall          MIT_UNF       -> true

Die Modelle hat das BAG 2027 neu geschnitten (BASE, PRAXIS, FLEX, TEL_DIG,
PHARM statt TAR-BASE, TAR-HAM, TAR-HMO, TAR-DIV). `tariff_type` bleibt der
BAG-Code des jeweiligen Jahres, `model_type` ist unser Schlüssel für den
Rechner. PRAXIS umfasst Hausarzt und HMO; die Zuordnung übernehmen wir aus dem
Vorjahr, wenn der Tarif dort schon existierte, sonst entscheidet der Name.

Credentials: SUPABASE_URL und SUPABASE_SERVICE_ROLE_KEY aus der Umgebung oder
aus ~/Projects/handyabo/.env (gleiches Supabase-Projekt).
"""

import csv
import os
import re
import sys
from collections import Counter
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
ENV_FALLBACK = Path.home() / "Projects" / "handyabo" / ".env"
BATCH = 5000

AGE_CLASS = {
    "AKA_01_KIN": "AKL-KIN", "AKA_02_JUG": "AKL-JUG", "AKA_03_ERW": "AKL-ERW",
    "AKL-KIN": "AKL-KIN", "AKL-JUG": "AKL-JUG", "AKL-ERW": "AKL-ERW",
}

MODEL_BY_TYPE = {
    # bis 2026
    "TAR-BASE": "standard", "TAR-HAM": "family_doctor",
    "TAR-HMO": "hmo", "TAR-DIV": "telmed",
    # ab 2027
    "BASE": "standard", "TEL_DIG": "telmed",
    "FLEX": "diverse", "PHARM": "apotheke",
}


def load_env():
    if os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_ROLE_KEY"):
        return
    if ENV_FALLBACK.exists():
        for line in ENV_FALLBACK.read_text().splitlines():
            m = re.match(r"^([A-Z_]+)=(.*)$", line.strip())
            if m:
                os.environ.setdefault(m.group(1), m.group(2).strip().strip('"'))


def norm_region(v):
    # "PR_REG_1" oder "PR-REG CH1" -> "PR-REG CH1"
    return f"PR-REG CH{v.strip()[-1]}"


def norm_franchise(v):
    # "FRA_01_E_0300" oder "FRA-300" -> 300
    return int(re.split(r"[_-]", v)[-1])


def norm_accident(v):
    return v in ("MIT_UNF", "MIT-UNF", "true", "True")


def norm_subgroup(v):
    # 2026 stand bei Erwachsenen und jungen Erwachsenen nichts, 2027 steht E1/J1
    return "" if v in ("E1", "J1") else v


def previous_models(year):
    """(Versicherer, Tarif) -> model_type aus dem Vorjahres-CSV."""
    prev = DATA_DIR / f"praemien_{year - 1}.csv"
    out = {}
    if not prev.exists():
        return out
    with open(prev, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            m = MODEL_BY_TYPE.get(r["Tariftyp"])
            if m:
                out[(r["Versicherer"].lstrip("0"), r["Tarif"])] = m
    return out


def praxis_model(insurer, tariff, name, prev):
    # Tarifcodes wurden 2027 teils umbenannt: "Santé (HMO)" hiess 2026 "HMO",
    # "Hausarztmodell 1 (NetMed 1)" hiess "Hausarztmodell 1".
    candidates = [tariff]
    m = re.match(r"^(.*?)\s*\((.*)\)\s*$", tariff)
    if m:
        candidates += [m.group(2), m.group(1)]
    for c in candidates:
        if prev.get((insurer, c)) in ("hmo", "family_doctor"):
            return prev[(insurer, c)]
    if re.search(r"\bHMO\b|Gesundheitszentrum", f"{tariff} {name}", re.I):
        return "hmo"
    return "family_doctor"


def build_rows(year, insurer_names):
    path = DATA_DIR / f"praemien_{year}.csv"
    prev = previous_models(year)
    rows, unknown = [], Counter()
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if int(r["Geschäftsjahr"]) != year:
                sys.exit(f"{path} enthält Geschäftsjahr {r['Geschäftsjahr']}, erwartet {year}")
            ins = r["Versicherer"].lstrip("0")
            ttype = r["Tariftyp"]
            if ttype == "PRAXIS":
                model = praxis_model(ins, r["Tarif"], r["Tarifbezeichnung"], prev)
            else:
                model = MODEL_BY_TYPE.get(ttype)
            if model is None:
                unknown[ttype] += 1
                continue
            name = insurer_names.get(int(ins))
            if name is None:
                unknown[f"Versicherer {ins}"] += 1
                continue
            rows.append({
                "insurer_id": int(ins),
                "insurer_name": name,
                "canton": r["Kanton"],
                "year": year,
                "region": norm_region(r["Region"]),
                "age_class": AGE_CLASS[r["Altersklasse"]],
                "accident_included": norm_accident(r["Unfalleinschluss"]),
                "tariff": r["Tarif"],
                "tariff_type": ttype,
                "age_subgroup": norm_subgroup(r["Altersuntergruppe"]),
                "franchise": norm_franchise(r["Franchise"]),
                "premium": float(r["Prämie"]),
                "tariff_name": r["Tarifbezeichnung"],
                "model_type": model,
            })
    if unknown:
        sys.exit(f"Nicht zuordenbar, bitte Mapping ergänzen: {dict(unknown)}")
    return rows


def fetch_insurer_names(sb):
    """Anzeigename je Versicherer-ID, wie ihn der Rechner bisher zeigt.

    Quelle ist der zuletzt importierte Name in `premiums`, damit sich die
    Anzeige zwischen den Jahren nicht verschiebt. Neue IDs fallen auf
    insurers.name zurück.
    """
    names = {}
    for r in sb.table("insurers").select("id,name").execute().data:
        names[r["id"]] = r["name"]
    for iid in list(names):
        q = (sb.table("premiums").select("insurer_name,year")
             .eq("insurer_id", iid).order("year", desc=True).limit(1).execute().data)
        if q:
            names[iid] = q[0]["insurer_name"]
    return names


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    year = int(args[0])
    dry = "--dry-run" in sys.argv
    replace = "--replace" in sys.argv

    load_env()
    from supabase import create_client
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])

    rows = build_rows(year, fetch_insurer_names(sb))
    print(f"{year}: {len(rows)} Zeilen, {len({r['insurer_id'] for r in rows})} Versicherer")
    print("  model_type:", dict(Counter(r["model_type"] for r in rows)))
    print("  tariff_type:", dict(Counter(r["tariff_type"] for r in rows)))

    existing = (sb.table("premiums").select("id", count="exact")
                .eq("year", year).limit(1).execute().count)
    print(f"  bereits in der DB: {existing}")
    if dry:
        return
    if existing and not replace:
        sys.exit(f"Jahr {year} ist schon da. Mit --replace neu laden.")
    if existing and replace:
        # in Portionen, ein einzelnes DELETE über 200k Zeilen läuft ins Timeout
        while True:
            ids = [r["id"] for r in sb.table("premiums").select("id")
                   .eq("year", year).limit(BATCH).execute().data]
            if not ids:
                break
            sb.table("premiums").delete().in_("id", ids).execute()
        print(f"  {existing} alte Zeilen für {year} entfernt")

    for i in range(0, len(rows), BATCH):
        sb.table("premiums").insert(rows[i:i + BATCH]).execute()
        print(f"  {min(i + BATCH, len(rows))}/{len(rows)}", end="\r")
    print()

    done = (sb.table("premiums").select("id", count="exact")
            .eq("year", year).limit(1).execute().count)
    if done != len(rows):
        sys.exit(f"Abweichung: {done} in der DB, {len(rows)} erwartet")
    print(f"✓ {done} Zeilen für {year} in `premiums`")


if __name__ == "__main__":
    main()
