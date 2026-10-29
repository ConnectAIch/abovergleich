#!/usr/bin/env python3
"""Offerten-Tabelle auf der Hausrat-Seite (DE/FR/EN) aus data/hausrat_offerten.json.

    python3 scripts/build_hausrat.py

Ersetzt nur den Block zwischen <!-- OFFERTEN:START --> und <!-- OFFERTEN:END -->.
Bis 29.10.2026 standen dort geschätzte Preise («~CHF 150»), die Bing für
«Hausrat 3 Zimmer Zürich Kosten» zitierte. Jetzt stehen dort nur Offerten, die
wir selbst in den Rechnern der Versicherer geholt haben, mit Datum.
"""
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA = json.loads((Path(__file__).parent / "data" / "hausrat_offerten.json").read_text(encoding="utf-8"))
PAGES = {"de": "hausratversicherung/index.html", "fr": "fr/assurance-menage/index.html",
         "en": "en/household-insurance/index.html"}
START, END = "<!-- OFFERTEN:START -->", "<!-- OFFERTEN:END -->"
UTM = "utm_source=abovergleich.com&utm_medium=referral&utm_campaign=hausrat-vergleich"

T = {
    "de": {"th": ["Versicherer", "Hausrat + Haftpflicht / Jahr", "Selbstbehalt CHF", "Was du wissen musst", ""],
           "mt": "pro Monat", "cta": "Offerte →", "teile": "davon Hausrat {h}, Haftpflicht {p}",
           "ohne": "Ohne Haftpflicht im Rechner", "nur": "nur Hausrat"},
    "fr": {"th": ["Assureur", "Ménage + RC / an", "Franchise CHF", "À savoir", ""],
           "mt": "par mois", "cta": "Offre →", "teile": "dont ménage {h}, RC {p}",
           "ohne": "Sans RC dans le calculateur", "nur": "ménage seul"},
    "en": {"th": ["Insurer", "Contents + liability / year", "Excess CHF", "What to know", ""],
           "mt": "per month", "cta": "Quote →", "teile": "contents {h}, liability {p}",
           "ohne": "No liability in the calculator", "nur": "contents only"},
}


def chf(x, lang):
    s = f"{x:,.2f}".replace(",", "'")
    return f"CHF&nbsp;{s}"


def link(url):
    return f"{url}{'&' if '?' in url else '?'}{UTM}"


def block(lang):
    t = T[lang]
    rows = []
    for o in sorted(DATA["offerten"], key=lambda o: o["total"]):
        paket = o.get("paket_i18n", {}).get(lang, o["paket"])
        teile = ""
        if o["hausrat"] and o["haftpflicht"]:
            teile = f'<div class="compare-type">{t["teile"].format(h=chf(o["hausrat"], lang), p=chf(o["haftpflicht"], lang))}</div>'
        rows.append(f"""        <tr class="compare-row">
          <td><div class="compare-name">{o["name"]}</div><div class="compare-type">{paket}</div></td>
          <td><div class="compare-price">{chf(o["total"], lang)}</div><div class="compare-type">{chf(o["total"] / 12, lang)} {t["mt"]}</div>{teile}</td>
          <td><div class="compare-price" style="font-size:14px;">{o["sb"][lang]}</div></td>
          <td><div class="compare-features">{o["notiz"][lang]}</div></td>
          <td><a href="{link(o["url"])}" target="_blank" rel="noopener" class="compare-cta">{t["cta"]}</a></td>
        </tr>""")
    for o in DATA["ohne_haftpflicht"]:
        rows.append(f"""        <tr class="compare-row">
          <td><div class="compare-name">{o["name"]}</div><div class="compare-type">{t["ohne"]}</div></td>
          <td><div class="compare-price" style="color:var(--muted);">{chf(o["hausrat"], lang)}</div><div class="compare-type">{t["nur"]}</div></td>
          <td><div class="compare-price" style="font-size:14px;">200</div></td>
          <td><div class="compare-features">{o["notiz"][lang]}</div></td>
          <td><a href="{link(o["url"])}" target="_blank" rel="noopener" class="compare-cta">{t["cta"]}</a></td>
        </tr>""")
    th = "".join(f"<th>{h}</th>" for h in t["th"])
    return f"""{START}
    <div style="overflow-x:auto;">
    <table class="compare-table">
      <thead><tr>{th}</tr></thead>
      <tbody>
{chr(10).join(rows)}
      </tbody>
    </table>
    </div>
    {END}"""


for lang, rel in PAGES.items():
    p = ROOT / rel
    html = p.read_text(encoding="utf-8")
    a, b = html.index(START), html.index(END) + len(END)
    new = html[:a] + block(lang) + html[b:]
    if new != html:
        p.write_text(new, encoding="utf-8")
        print("geschrieben:", rel)
    else:
        print("unverändert:", rel)
