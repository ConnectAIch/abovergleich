#!/usr/bin/env python3
"""Verwaltungskosten der Grundversicherung je Kasse, aufgeschlüsselt nach
Personal, eingekauften Leistungen, Werbung und Provisionen.

Quelle: BAG, «Auswertungen Verwaltungskosten» (xlsx, Blatt DB_interaktiv,
Branche OKP CH, Jahresrechnung definitiv), Download unter
https://www.bag.admin.ch/de/bilanzen-und-betriebsrechnungen-krankenversicherer
nach scripts/data/Auswertungen_Verwaltungskosten.xlsx (nicht im Repo).

«eingekauft»: Personalaufwand 0. Die Kasse beschäftigt kein eigenes Personal
und bezahlt die Verwaltung als Gebühr an eine Konzern- oder Partnerfirma
(Groupe Mutuel, Assura, Vivao Sympany). Der Gesamtbetrag ist vergleichbar,
wie er sich auf die Konzernkassen verteilt, bestimmt aber der Konzern.

    python3 extract_verwaltung.py   # schreibt data/verwaltung_detail.json
"""
import json
from pathlib import Path

import openpyxl

DATA = Path(__file__).parent / "data"
COLS = {
    "personal": "Personalaufwand (Kto.50)",
    "personal_prov": "Provisionen ans eigene Personal",
    "eingekauft": "Diverser Betriebsaufwand",
    "werbung": "Werbeaufwand",
    "provisionen": "Provisionen (Kto. 517)",
}


def main():
    wb = openpyxl.load_workbook(DATA / "Auswertungen_Verwaltungskosten.xlsx", read_only=True, data_only=True)
    rows = list(wb["DB_interaktiv"].iter_rows(values_only=True))
    hdr = next(k for k, r in enumerate(rows[:15]) if r and "Jahr" in r)
    H = list(rows[hdr])
    col = {k: next(j for j, h in enumerate(H) if h and v in str(h)) for k, v in COLS.items()}
    out = {}
    for r in rows[hdr + 1:]:
        if r[6] != "OKP CH" or r[2] != "Jahresrechnung definitiv" or not r[3] or not r[7]:
            continue
        i, y, n = int(r[3]), int(r[1]), float(r[7])
        per = {k: round(-(r[j] or 0) / n, 1) for k, j in col.items()}
        out.setdefault(str(i), {})[str(y)] = {
            "versicherte": round(n),
            "personal": round(per["personal"] + per["personal_prov"], 1),
            "eingekauft": per["eingekauft"],
            "werbung": per["werbung"],
            "provisionen": round(per["provisionen"] + per["personal_prov"], 1),
            "ohne_personal": per["personal"] == 0,
        }
    (DATA / "verwaltung_detail.json").write_text(json.dumps({
        "quelle": "BAG, Auswertungen Verwaltungskosten (Jahresrechnung definitiv, OKP CH), Stand Juli 2026",
        "einheit": "CHF pro versicherte Person und Jahr", "kassen": out}, ensure_ascii=False, indent=1), encoding="utf-8")
    flag = sorted(k for k, v in out.items() if v.get(max(v), {}).get("ohne_personal"))
    print(f"{len(out)} Kassen, ohne eigenes Personal im letzten Jahr: {flag}")


if __name__ == "__main__":
    main()
