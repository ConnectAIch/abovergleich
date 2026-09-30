"""BAG-Verzeichnis der zugelassenen Krankenversicherer lesen.

Quelle: https://www.bag.admin.ch/de/verzeichnisse-der-zugelassenen-kranken-und-rueckversicherer
Die XLSX-Fassung liegt als data/kv_verzeichnis_<stand>.xlsx. Das Blatt
«Anpassungen» überschreibt Einträge des Hauptblatts (neue Adressen).
"""
import re
from pathlib import Path

import openpyxl

DATA = Path(__file__).parent / "data"


# Die XLSX-Fassung ist bei den Groupe-Mutuel-Gesellschaften unvollständig
# (Adresse nur «Groupe Mutuel»). Werte aus der PDF-Fassung derselben Liste.
OVERRIDES = {
    343: {"name": "Avenir Krankenversicherung AG", "address": ["Rue des Cèdres 5", "1919 Martigny"]},
    1479: {"name": "Mutuel Krankenversicherung AG", "address": ["Rue des Cèdres 5", "1919 Martigny"]},
    1535: {"name": "Philos Krankenversicherung AG", "address": ["Rue des Cèdres 5", "1919 Martigny"]},
    1507: {"name": "AMB Assurances SA", "address": ["Route de Verbier 13", "1934 Le Châble"]},
    290: {"name": "CONCORDIA Schweiz. Kranken- und Unfallversicherung AG"},
}


def _first_de(cell):
    # Namen stehen DE/FR/IT untereinander. Getrennte Wörter wieder zusammenfügen:
    # «Kranken-» + «Versicherung AG», «Unfallver-» + «sicherung AG».
    raw = [l.strip() for l in str(cell or "").split("\n") if l.strip()]
    lines = []
    for l in raw:
        if lines and lines[-1].endswith("-"):
            lines[-1] = lines[-1][:-1] + l if l[:1].islower() else lines[-1] + l
        else:
            lines.append(l)
    return lines


def _address(cell):
    lines = [l.strip() for l in str(cell or "").split("\n") if l.strip()]
    out = []
    for l in lines:
        if re.match(r"^(Tel|Fax|E-Mail|Kontakt|www\.|http)", l, re.I) or "@" in l:
            break
        out.append(l)
        if re.match(r"^\d{4}\s", l):   # PLZ Ort beendet die Adresse
            break
    return out


def load(path=None):
    path = path or sorted(DATA.glob("kv_verzeichnis_*.xlsx"))[-1]
    wb = openpyxl.load_workbook(path, read_only=True)
    out = {}
    for sheet in ("Zugelassene Krankenversicherer", "Anpassungen"):
        if sheet not in wb.sheetnames:
            continue
        for row in wb[sheet].iter_rows(values_only=True):
            if not row or not str(row[0] or "").strip().isdigit():
                continue
            nr = int(str(row[0]).strip())
            addr = _address(row[3])
            # Firmenname: Adresszeilen, die mit dem Namen beginnen, gehören nicht zur Strasse
            name_lines = _first_de(row[2])
            name = name_lines[0] if name_lines else ""
            if addr and addr[0] == name:
                addr = addr[1:]
            out[nr] = {
                "name": name,
                "name_lines": name_lines,
                "address": addr,
                "group": (str(row[5]).strip() if row[5] and str(row[5]).strip() != "---" else None),
                "area": re.sub(r"\s+", " ", str(row[6] or "")).strip(),
            }
    for nr, o in OVERRIDES.items():
        if nr in out:
            out[nr].update(o)
    return out


if __name__ == "__main__":
    for nr, d in sorted(load().items()):
        print(nr, "|", " / ".join(d["name_lines"][:3]), "|", " / ".join(d["address"]), "|", d["group"], "|", d["area"][:60])
