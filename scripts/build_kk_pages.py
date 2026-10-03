#!/usr/bin/env python3
"""
Krankenkassen-Seiten aus den BAG-Prämiendaten erzeugen.

    python3 build_kk_pages.py

Liest scripts/data/praemien_{VORJAHR,JAHR}.csv und versichertenbestand_{JAHR}.csv
und schreibt:

  - /krankenkasse/<kanton>/index.html      26 Kantonsseiten
  - /krankenkasse/index.html               Übersicht aller Kantone
  - /krankenkassenpraemien-<JAHR>/         Auswertung Prämienveränderung
  - index.html                             Insights-Block zwischen den Markern
  - premium-insights.json, sitemap.xml

Jedes Jahr Ende September: neue CSVs laden (premium_analysis.py --download,
Versichertenbestand von opendata.bagnet.ch), JAHR unten anheben, laufen lassen.

Kennzahlen, die wir selbst rechnen, beziehen sich immer auf dieselbe
Referenz wie beim BAG-Vergleichswert: Erwachsene, Franchise 300, mit Unfall,
Standardmodell (freie Arztwahl). Durchschnitte über Kassen sind mit dem
Versichertenbestand je Kasse und Kanton gewichtet, Prämienregionen innerhalb
eines Kantons zählen gleich. Die offizielle BAG-Zahl rechnet über alle
Modelle und Franchisen und liegt deshalb etwas anders.
"""

import csv
import html
import json
import os
import re
import statistics as st
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from import_premiums import build_rows, load_env, read_csv  # noqa: E402
from premium_analysis import INSURER_NAMES  # noqa: E402
import kv_verzeichnis  # noqa: E402
import site_nav  # noqa: E402
import build_awards  # noqa: E402
import i18n  # noqa: E402
from i18n import L  # noqa: E402

YEAR = 2027
PREV = YEAR - 1
DEADLINE_ISO = f"{PREV}-11-30"   # Kündigung Grundversicherung, Eingang bei der Kasse
PUBLISHED = "2026-09-30"


def deadline(short=False):
    """«30. November 2026», mit short=True ohne Jahr, in der aktuellen Sprache."""
    t = i18n.date_long(DEADLINE_ISO)
    return t.rsplit(" ", 1)[0] if short else t

# Offizielle BAG-Werte zur Einordnung, Medienmitteilung vom 29.09.2026
BAG_OFFICIAL = {
    "change_pct": 5.0,
    "adult_mean": 487.60,
    "adult_delta": 22.80,
    "max_canton": ("JU", 6.6),
    "min_canton": ("GL", 3.0),
    "source_url": "https://www.srf.ch/news/schweiz/erneuter-anstieg-krankenkassenpraemien-steigen-2027-um-5-prozent",
}

ROOT = Path(__file__).parent.parent
DATA = Path(__file__).parent / "data"
SITE = "https://abovergleich.com"

CANTONS = {
    "AG": ("Aargau", "aargau"), "AI": ("Appenzell Innerrhoden", "appenzell-innerrhoden"),
    "AR": ("Appenzell Ausserrhoden", "appenzell-ausserrhoden"), "BE": ("Bern", "bern"),
    "BL": ("Basel-Landschaft", "basel-landschaft"), "BS": ("Basel-Stadt", "basel-stadt"),
    "FR": ("Freiburg", "freiburg"), "GE": ("Genf", "genf"), "GL": ("Glarus", "glarus"),
    "GR": ("Graubünden", "graubuenden"), "JU": ("Jura", "jura"), "LU": ("Luzern", "luzern"),
    "NE": ("Neuenburg", "neuenburg"), "NW": ("Nidwalden", "nidwalden"),
    "OW": ("Obwalden", "obwalden"), "SG": ("St. Gallen", "st-gallen"),
    "SH": ("Schaffhausen", "schaffhausen"), "SO": ("Solothurn", "solothurn"),
    "SZ": ("Schwyz", "schwyz"), "TG": ("Thurgau", "thurgau"), "TI": ("Tessin", "tessin"),
    "UR": ("Uri", "uri"), "VD": ("Waadt", "waadt"), "VS": ("Wallis", "wallis"),
    "ZG": ("Zug", "zug"), "ZH": ("Zürich", "zuerich"),
}

_MODEL_LABEL = {
    "standard": ("Standard", "Standard", "Standard"), "family_doctor": ("Hausarzt", "Médecin de famille", "Family doctor"),
    "hmo": ("HMO", "HMO", "HMO"), "telmed": ("Telmed", "Telmed", "Telmed"),
    "diverse": ("Alternativ", "Alternatif", "Alternative"), "apotheke": ("Apotheke", "Pharmacie", "Pharmacy"),
}


class _ModelLabel(dict):
    """MODEL_LABEL[m] in der aktuellen Sprache."""
    def __getitem__(self, m):
        return L(*_MODEL_LABEL[m])

    def get(self, m, default=None):
        return self[m] if m in _MODEL_LABEL else default


MODEL_LABEL = _ModelLabel()


def cname(c):
    """Kantonsname in der aktuellen Sprache."""
    return CANTONS[c][0] if i18n.LANG == "de" else i18n.CANTON_I18N[c][i18n.LANG][0]


def canton_url(c):
    slug = CANTONS[c][1] if i18n.LANG == "de" else i18n.CANTON_I18N[c][i18n.LANG][1]
    return f"{i18n.url('cantons')}{slug}/"


def im_kanton(c):
    """«im Kanton Zürich» / «dans le canton de Zurich» / «in the canton of Zurich»."""
    n = cname(c)
    if i18n.LANG == "fr":
        if c in i18n.FR_DANS:
            return i18n.FR_DANS[c]
        return f"dans le canton de {n}"
    return L(f"im Kanton {n}", "", f"in the canton of {n}")


def sorted_cantons():
    """(Code, Name, URL) alphabetisch nach dem Namen in der aktuellen Sprache."""
    return sorted(((c, cname(c), canton_url(c)) for c in CANTONS), key=lambda x: x[1])

MIN_BESTAND_RANKING = 50_000   # Kassen-Rankings: nur Kassen mit so vielen Versicherten


# ── Daten ──────────────────────────────────────────────────────────────────

def load_year(year, accident=True):
    names = {int(k): v for k, v in INSURER_NAMES.items()}
    # ältere Jahre enthalten Kassen, die es nicht mehr gibt (fusioniert, aufgelöst)
    for r in read_csv(DATA / f"praemien_{year}.csv"):
        names.setdefault(int(r["Versicherer"].lstrip("0")), f"Nr. {r['Versicherer'].lstrip('0')}")
    rows = build_rows(year, names)
    # Erwachsene mit Unfall ist die BAG-Referenz für Anstiege und Rankings.
    # Ohne Unfall (die Mehrheit der Erwachsenen) für die Beispielperson der Kassenseiten.
    return [r for r in rows if r["age_class"] == "AKL-ERW" and r["accident_included"] == accident]


def load_bestand():
    out = defaultdict(float)
    with open(DATA / f"versichertenbestand_{YEAR}.csv", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            out[(int(r["Versicherer"]), r["Kanton"])] += float(r["Durchschnittsbestand"])
    return out


def load_regions():
    """Kanton -> Region -> sortierte Gemeinden, aus plz_regions."""
    load_env()
    from supabase import create_client
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    rows, start = [], 0
    while True:
        chunk = (sb.table("plz_regions").select("canton,region,municipality")
                 .range(start, start + 999).execute().data)
        rows += chunk
        if len(chunk) < 1000:
            break
        start += 1000
    out = defaultdict(lambda: defaultdict(set))
    for r in rows:
        if r["municipality"]:
            out[r["canton"]][f"PR-REG CH{r['region']}"].add(r["municipality"])
    return {c: {k: sorted(v) for k, v in regs.items()} for c, regs in out.items()}


def index_rows(rows):
    """(canton, region, insurer, tariff, franchise) -> row. Tarifcode klein
    geschrieben, Swica schreibt denselben Tarif 2026 «CASA» und 2027 «Casa»."""
    return {(r["canton"], r["region"], r["insurer_id"], r["tariff"].lower(), r["franchise"]): r for r in rows}


def tariff_match(prev_idx, r, franchise):
    """Vorjahresprämie desselben Tarifs. Einige Tarifcodes wurden umbenannt,
    z.B. 'Santé (HMO)' hiess vorher 'HMO'."""
    base = (r["canton"], r["region"], r["insurer_id"])
    cands = [r["tariff"].lower()]
    m = re.match(r"^(.*?)\s*\((.*)\)\s*$", r["tariff"].lower())
    if m:
        cands += [m.group(2), m.group(1)]
    for c in cands:
        hit = prev_idx.get(base + (c, franchise))
        if hit:
            return hit["premium"]
    return None


def standard_premiums(rows, franchise=300):
    """(canton, region, insurer) -> Standardprämie"""
    return {(r["canton"], r["region"], r["insurer_id"]): r["premium"]
            for r in rows if r["model_type"] == "standard" and r["franchise"] == franchise}


def wmean(pairs):
    tw = sum(w for _, w in pairs)
    return sum(v * w for v, w in pairs) / tw if tw else None


# ── Auswertung ─────────────────────────────────────────────────────────────

def analyse(cur, prev, bestand):
    s_cur, s_prev = standard_premiums(cur), standard_premiums(prev)

    # je Kasse und Kanton: mittlere Standardprämie über die Regionen
    per_ic = defaultdict(lambda: {"cur": [], "prev": []})
    for (c, reg, i), p in s_cur.items():
        per_ic[(i, c)]["cur"].append(p)
        if (c, reg, i) in s_prev:
            per_ic[(i, c)]["prev"].append(s_prev[(c, reg, i)])
    level = {}
    change = {}
    for (i, c), v in per_ic.items():
        level[(i, c)] = sum(v["cur"]) / len(v["cur"])
        pairs = [(s_cur[(c, reg, i)] / s_prev[(c, reg, i)] - 1)
                 for (cc, reg, ii) in s_cur if ii == i and cc == c and (c, reg, i) in s_prev]
        if pairs:
            change[(i, c)] = sum(pairs) / len(pairs) * 100

    cantons = {}
    for c in CANTONS:
        w_level = [(level[(i, cc)], bestand.get((i, c), 0)) for (i, cc) in level if cc == c]
        w_change = [(change[(i, cc)], bestand.get((i, c), 0)) for (i, cc) in change if cc == c]
        cantons[c] = {
            "avg_standard": wmean(w_level),
            "change_pct": wmean(w_change),
        }

    insurers = {}
    for i in {i for (i, _) in change}:
        pairs = [(change[(ii, c)], bestand.get((i, c), 0)) for (ii, c) in change if ii == i]
        tot = sum(bestand.get((i, c), 0) for c in CANTONS)
        insurers[i] = {
            "name": INSURER_NAMES[str(i)],
            "change_pct": wmean(pairs) if tot else sum(p for p, _ in pairs) / len(pairs),
            "bestand": tot,
            "cantons": len(pairs),
        }
    nat = wmean([(change[k], bestand.get(k, 0)) for k in change])
    return cantons, insurers, nat


def main_region(rows, canton):
    regs = sorted({r["region"] for r in rows if r["canton"] == canton})
    return regs[0] if len(regs) == 1 else ("PR-REG CH1" if "PR-REG CH1" in regs else regs[0])


def top3_counts(rows, year_rows_by_canton):
    out = defaultdict(int)
    for c in CANTONS:
        reg = main_region(year_rows_by_canton[c], c)
        best = {}
        for r in year_rows_by_canton[c]:
            if r["region"] == reg and r["model_type"] == "standard" and r["franchise"] == 300:
                best[r["insurer_id"]] = min(best.get(r["insurer_id"], 9e9), r["premium"])
        for i, _ in sorted(best.items(), key=lambda x: x[1])[:3]:
            out[i] += 1
    return out


def ranking(rows, canton, region, franchise, prev_idx, standard_only=False, n=10):
    """Günstigster Tarif je Kasse, sortiert nach Prämie."""
    best = {}
    for r in rows:
        if r["canton"] != canton or r["region"] != region or r["franchise"] != franchise:
            continue
        if standard_only and r["model_type"] != "standard":
            continue
        cur = best.get(r["insurer_id"])
        if cur is None or r["premium"] < cur["premium"]:
            best[r["insurer_id"]] = r
    out = []
    for r in sorted(best.values(), key=lambda x: x["premium"])[:n]:
        before = tariff_match(prev_idx, r, franchise)
        out.append({
            "insurer_id": r["insurer_id"], "insurer": r["insurer_name"], "model": r["model_type"],
            "tariff": r["tariff_name"], "premium": r["premium"],
            "change": (r["premium"] / before - 1) * 100 if before else None,
        })
    return out


def _cands(t):
    t = t.lower()
    m = re.match(r"^(.*?)\s*\((.*)\)\s*$", t)
    return [t] + ([m.group(2), m.group(1)] if m else [])


def _regions(rows, franchise, accident):
    out = defaultdict(dict)
    for r in rows:
        if r["franchise"] == franchise and r["accident_included"] == accident:
            out[(r["canton"], r["region"])][(r["insurer_id"], r["tariff"].lower())] = r
    return out


def _find(reg, r):
    for c in _cands(r["tariff"]):
        hit = reg.get((r["insurer_id"], c))
        if hit:
            return hit
    return None


def _ranked(reg):
    best = {}
    for (i, _), r in reg.items():
        if i not in best or r["premium"] < best[i]["premium"]:
            best[i] = r
    return sorted(best.values(), key=lambda r: r["premium"])


def jojo_analysis():
    """Wie entwickelt sich der günstigste Tarif des Vorjahres? Pro Prämienregion
    der günstigste Tarif (Erwachsene, Franchise 2'500, ohne Unfall, alle Modelle)
    und derselbe Tarif ein Jahr später, verglichen mit dem Median aller Tarife
    der Region. Regionen, in denen der Tarif wegfällt, zählen nicht."""
    years = [y for y in (YEAR - 2, PREV, YEAR) if (DATA / f"praemien_{y}.csv").exists()]
    names = {}
    for y in years:
        for r in read_csv(DATA / f"praemien_{y}.csv"):
            i = r["Versicherer"].lstrip("0")
            names[int(i)] = INSURER_NAMES.get(i, f"Nr. {i}")
    idx = {y: _regions([r for r in build_rows(y, names) if r["age_class"] == "AKL-ERW"], 2500, False) for y in years}

    def step(y0, y1):
        res = []
        for k, reg in idx[y0].items():
            if k not in idx[y1]:
                continue
            win = _ranked(reg)[0]
            nxt = _find(idx[y1][k], win)
            chs = [_find(idx[y1][k], r)["premium"] / r["premium"] - 1 for r in reg.values() if _find(idx[y1][k], r)]
            if not nxt or not chs:
                continue
            pos = sum(1 for x in _ranked(idx[y1][k]) if x["premium"] < nxt["premium"]) + 1
            res.append({"canton": k[0], "region": k[1], "insurer": win["insurer_name"], "tariff": win["tariff_name"],
                        "model": win["model_type"], "before": win["premium"], "after": nxt["premium"],
                        "change": (nxt["premium"] / win["premium"] - 1) * 100, "market": st.median(chs) * 100,
                        "rank_after": pos, "n_after": len(_ranked(idx[y1][k]))})
        return res

    out = {}
    for y0, y1 in [(PREV, YEAR), (YEAR - 2, PREV)]:
        if y0 in idx and y1 in idx:
            r = step(y0, y1)
            out[f"{y0}-{y1}"] = {
                "regions": len(r),
                "winner_change": st.mean(x["change"] for x in r),
                "market_change": st.mean(x["market"] for x in r),
                "still_first": sum(1 for x in r if x["rank_after"] == 1),
                "out_of_top5": sum(1 for x in r if x["rank_after"] > 5),
                "rows": sorted(r, key=lambda x: -x["change"]),
            }
    # gleiche Kasse, anderes Modell: Standard gegen das günstigste andere Modell
    gaps = []
    for reg in idx[YEAR].values():
        by = defaultdict(list)
        for (i, _), r in reg.items():
            by[i].append(r)
        for rs in by.values():
            std = [r["premium"] for r in rs if r["model_type"] == "standard"]
            oth = [r["premium"] for r in rs if r["model_type"] != "standard"]
            if std and oth:
                gaps.append((min(std) - min(oth)) * 12)
    out["model_switch_median"] = st.median(gaps)
    return out


# ── HTML-Helfer ────────────────────────────────────────────────────────────

def chf(v, dec=2):
    s = f"{v:,.{dec}f}".replace(",", "'")
    return s


def pct(v, sign=True):
    if v is None:
        return L("neu", "nouveau", "new")
    s = f"{v:+.1f}" if sign else f"{v:.1f}"
    if i18n.LANG == "fr":
        s = s.replace(".", ",")
    return s.replace("-", "−") + ("%" if i18n.LANG == "en" else " %")


def e(s):
    return html.escape(str(s), quote=True)


PAGE_CSS = """
  .kk-rating { background:var(--surface); border:1px solid var(--border2); border-radius:14px; padding:20px 22px; margin:20px 0; }
  .kk-rating-head { display:flex; justify-content:space-between; gap:16px; align-items:flex-start; margin-bottom:12px; }
  .kk-rating-label { font-size:12px; font-weight:700; text-transform:uppercase; letter-spacing:.05em; color:var(--muted); }
  .kk-rating-sub { font-size:13px; color:var(--muted); margin-top:4px; }
  .kk-rating-note { font-family:'Plus Jakarta Sans',sans-serif; font-size:40px; font-weight:800; line-height:1; color:var(--text); white-space:nowrap; }
  .kk-rating-note span { font-size:16px; color:var(--muted); font-weight:600; }
  .kk-rrow { display:grid; grid-template-columns:120px 1fr 36px; gap:10px; align-items:center; font-size:14px; padding:4px 0; }
  .kk-bar { display:block; height:8px; background:var(--surface2); border-radius:4px; overflow:hidden; }
  .kk-bar span { display:block; height:100%; background:var(--accent); border-radius:4px; }
  .kk-rnote { font-size:13px; color:var(--muted); margin:12px 0 8px; }
  .kk-rvar { font-size:13px; color:var(--muted); margin:-4px 0 14px; line-height:1.7; }
  .kk-rvar strong { color:var(--text); }
  .kk-rating > a { color:var(--accent-dark); font-weight:600; font-size:14px; }
  .kk-rtable td, .kk-rtable th { white-space:nowrap; padding-left:8px; padding-right:8px; font-size:14px; }
  .kk-rtable td:nth-child(n+4), .kk-rtable th:nth-child(n+4) { color:var(--muted); }
  .kk-cantonlinks { display:flex; flex-wrap:wrap; gap:6px 14px; font-size:14px; margin-bottom:12px; }
  .kk-cantonlinks a { color:var(--accent-dark); }
  .kk-canton-award { display:flex; align-items:center; gap:16px; flex-wrap:wrap; background:var(--surface); border:1px solid var(--border); border-radius:14px; padding:14px 18px; margin:14px 0 8px; }
  .kk-canton-award img { height:72px; width:auto; display:block; }
  .kk-canton-award p { margin:0; font-size:15px; flex:1 1 220px; }
  .kk-awardrow { display:flex; flex-wrap:wrap; gap:10px; margin:14px 0 6px; }
  .kk-awardrow img { height:72px; width:auto; display:block; }
  .kk-page { max-width: 820px; }
  .kk-lead { font-size: 18px !important; }
  .kk-facts { display:grid; grid-template-columns:repeat(3,1fr); gap:14px; margin:28px 0 8px; }
  .kk-fact { background:var(--surface); border:1px solid var(--border); border-radius:12px; padding:18px; }
  .kk-fact-val { font-family:'Plus Jakarta Sans',sans-serif; font-size:24px; font-weight:800; letter-spacing:-.5px; color:var(--text); }
  .kk-fact-label { font-size:13px; color:var(--muted); margin-top:4px; line-height:1.4; }
  .kk-table-wrap { overflow-x:auto; margin:16px 0 8px; -webkit-overflow-scrolling:touch; }
  .kk-table { width:100%; border-collapse:collapse; font-size:14px; min-width:520px; }
  .kk-table th { text-align:left; font-size:12px; font-weight:600; color:var(--muted); text-transform:uppercase; letter-spacing:.04em; padding:8px 10px; border-bottom:1px solid var(--border2); }
  .kk-table td { padding:10px; border-bottom:1px solid var(--border); color:var(--text2); vertical-align:top; }
  .kk-table td.num, .kk-table th.num { text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }
  .kk-table .sub { display:block; font-size:12px; color:var(--muted); }
  .kk-up { color:var(--red, #dc2626); }
  .kk-down { color:var(--green); }
  .kk-note { font-size:13px !important; color:var(--muted) !important; line-height:1.6 !important; }
  .kk-cta { display:inline-block; background:var(--accent); color:var(--text) !important; font-weight:700; text-decoration:none !important; padding:12px 22px; border-radius:10px; margin:8px 0 24px; }
  .kk-canton-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(170px,1fr)); gap:8px; margin:16px 0 24px; }
  .kk-canton-grid a { display:block; background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:10px 12px; text-decoration:none !important; color:var(--text) !important; font-size:14px; }
  .kk-canton-grid a span { display:block; font-size:12px; color:var(--muted); }
  .kk-crumbs { font-size:13px; color:var(--muted); margin-bottom:14px; }
  .kk-crumbs a { color:var(--muted) !important; }
  details.kk-gemeinden { margin:8px 0 20px; font-size:14px; color:var(--text2); }
  details.kk-gemeinden summary { cursor:pointer; color:var(--accent-dark); }
  details.kk-gemeinden p { font-size:13px !important; line-height:1.7 !important; margin-top:8px; }
  .kk-faq h3 { margin-top:24px; }
  @media (max-width:768px) { .kk-facts { grid-template-columns:1fr; } }
"""

ANALYTICS = """<script>
  window.va = window.va || function () { (window.vaq = window.vaq || []).push(arguments); };
  window.si = window.si || function () { (window.siq = window.siq || []).push(arguments); };
</script>
<script defer src="/_vercel/insights/script.js"></script>
<script defer src="/_vercel/speed-insights/script.js"></script>"""


def page(path, title, description, body, jsonld, alts=None):
    """alts: {Sprache: Pfad} derselben Seite, für hreflang und die Sprachwahl."""
    url = f"{SITE}{path}"
    lang = i18n.LANG
    if len(description) > 160 or len(title) > 70:
        print(f"! {path}: Titel {len(title)} / Beschreibung {len(description)} Zeichen, Google kürzt ab")
    ld = "\n".join(f'<script type="application/ld+json">\n{json.dumps(x, ensure_ascii=False, indent=1)}\n</script>' for x in jsonld)
    alt_links = (site_nav.hreflang_html(alts) + "\n") if alts else ""
    u = i18n.url
    footer_links = "\n      ".join(f'<a href="{h}">{t}</a>' for h, t in [
        (u("cantons"), L("Kantone", "Cantons", "Cantons")),
        (u("kassen"), L("Kassen", "Caisses", "Insurers")),
        (u("kuendigen"), L("K&uuml;ndigen", "R&eacute;silier", "Cancel")),
        (u("report"), L(f"Pr&auml;mien {YEAR}", f"Primes {YEAR}", f"Premiums {YEAR}")),
        (u("rating"), L("Rating", "Constance des primes", "Rating")),
        (u("methode"), L("Methode", "M&eacute;thode", "Methodology")),
        (u("impressum"), L("Impressum", "Mentions l&eacute;gales", "Imprint")),
        (u("datenschutz"), L("Datenschutz", "Protection des donn&eacute;es", "Privacy")),
    ])
    note = L("Unabh&auml;ngiger Vergleich f&uuml;r die Schweiz. Pr&auml;mien: Bundesamt f&uuml;r Gesundheit (BAG).",
             "Comparatif ind&eacute;pendant pour la Suisse. Primes&nbsp;: Office f&eacute;d&eacute;ral de la sant&eacute; publique (OFSP).",
             "Independent comparison for Switzerland. Premiums: Federal Office of Public Health (FOPH).")
    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<!-- generiert von scripts/build_kk_pages.py, nicht von Hand bearbeiten -->
<title>{e(title)}</title>
<meta name="description" content="{e(description)}">
<link rel="canonical" href="{url}">
{alt_links}<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<link rel="alternate icon" href="/favicon.ico">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<meta name="robots" content="index, follow">
<meta property="og:type" content="article">
<meta property="og:url" content="{url}">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(description)}">
<meta property="og:site_name" content="abovergleich.com">
<meta property="og:locale" content="{i18n.OG_LOCALE[lang]}">
<meta property="og:image" content="{SITE}/og-image.png">
<meta name="twitter:card" content="summary_large_image">
{ld}
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Inter:wght@300;400;500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/styles/shared.css">
<style>{PAGE_CSS}</style>
</head>
<body>

{site_nav.nav_html(path, alts)}

<article class="article kk-page">
{body}
</article>

<footer>
  <div class="footer-inner">
    <div class="footer-logo">abo<span>vergleich</span>.com</div>
    <div class="footer-note">{note}</div>
    <div class="footer-links">
      {footer_links}
    </div>
  </div>
</footer>

{ANALYTICS}
</body>
</html>
"""


def alts_of(fn):
    """{Sprache: Pfad} aus einer Funktion, die den Pfad in der aktuellen Sprache liefert."""
    return i18n.each_lang(fn)


def home_crumb():
    return (L("Krankenkassen-Vergleich", "Comparatif caisses-maladie", "Health insurance comparison"), i18n.url("home"))


def breadcrumb(items):
    return {
        "@context": "https://schema.org", "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": n + 1, "name": name, "item": f"{SITE}{path}"}
            for n, (name, path) in enumerate(items)
        ],
    }


def faq(pairs):
    return {
        "@context": "https://schema.org", "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in pairs
        ],
    }


def crumbs_html(items):
    parts = [f'<a href="{p}">{e(n)}</a>' for n, p in items[:-1]] + [e(items[-1][0])]
    return f'<div class="kk-crumbs">{" &rsaquo; ".join(parts)}</div>'


def rank_table(rows, show_model=True):
    head = (f"<tr><th>#</th><th>{L('Kasse', 'Caisse', 'Insurer')}</th><th class=\"num\">{L('Prämie / Mt.', 'Prime / mois', 'Premium / month')}</th>"
            f"<th class=\"num\">vs. {PREV}</th></tr>")
    body = []
    for n, r in enumerate(rows, 1):
        cls = "kk-up" if (r["change"] or 0) > 0 else "kk-down"
        sub = f'<span class="sub">{MODEL_LABEL[r["model"]]} · {e(r["tariff"])}</span>' if show_model else ""
        body.append(
            f'<tr><td>{n}</td><td><strong>{kasse_link(r["insurer_id"], r["insurer"])}</strong>{sub}</td>'
            f'<td class="num">CHF {chf(r["premium"])}</td>'
            f'<td class="num {cls if r["change"] is not None else ""}">{pct(r["change"])}</td></tr>')
    return f'<div class="kk-table-wrap"><table class="kk-table"><thead>{head}</thead><tbody>{"".join(body)}</tbody></table></div>'


REGION_GEMEINDEN = {}   # wird in main() gefüllt: (canton, region) -> Gemeinden


def region_label(reg, n_regions, canton=None):
    if n_regions == 1:
        return L("ganzer Kanton", "tout le canton", "whole canton")
    label = L(f"Prämienregion {reg[-1]}", f"région de primes {reg[-1]}", f"premium region {reg[-1]}")
    gem = REGION_GEMEINDEN.get((canton, reg), [])
    if 0 < len(gem) <= 3:
        label += f" ({', '.join(gem)})"
    return label


# ── Seiten ─────────────────────────────────────────────────────────────────

def canton_page(c, cur, prev_idx, cantons, insurers_c, regions):
    name = cname(c)
    path = canton_url(c)
    rows_c = [r for r in cur if r["canton"] == c]
    regs = sorted({r["region"] for r in rows_c})
    info = cantons[c]
    main = main_region(rows_c, c)
    ik = im_kanton(c)

    any_2500 = ranking(rows_c, c, main, 2500, prev_idx)
    std_300 = ranking(rows_c, c, main, 300, prev_idx, standard_only=True, n=40)
    cheapest = any_2500[0]
    spread = (std_300[-1]["premium"] - std_300[0]["premium"]) * 12 if len(std_300) > 1 else 0
    if len(regs) > 1:
        where = L(f"in der {region_label(main, len(regs), c)}", f"dans la {region_label(main, len(regs), c)}",
                  f"in {region_label(main, len(regs), c)}")
    else:
        where = L("im ganzen Kanton", "dans tout le canton", "across the whole canton")

    title = L(f"Günstigste Krankenkasse {name} {YEAR}: Prämien im Vergleich",
              f"Caisse-maladie {name} {YEAR} : les primes les moins chères",
              f"Cheapest health insurance {name} {YEAR}: premiums compared")
    if len(title) > 65:
        title = L(f"Krankenkasse {name} {YEAR}: die günstigsten Prämien",
                  f"Caisse-maladie {name} {YEAR} : les primes les moins chères",
                  f"Health insurance {name} {YEAR}: cheapest premiums")
    desc = L(f"Krankenkasse {name} {YEAR}: ab CHF {chf(cheapest['premium'])} ({cheapest['insurer']}, Franchise 2'500), "
             f"Prämien im Schnitt {pct(info['change_pct'])}. Alle Kassen, BAG-Daten, Preistreue-Rating.",
             f"Caisse-maladie {name} {YEAR} : dès CHF {chf(cheapest['premium'])} ({cheapest['insurer']}, franchise 2'500), "
             f"primes en moyenne {pct(info['change_pct'])}. Toutes les caisses, données OFSP.",
             f"Health insurance {name} {YEAR}: from CHF {chf(cheapest['premium'])} ({cheapest['insurer']}, deductible 2'500), "
             f"premiums {pct(info['change_pct'])} on average. All insurers, FOPH data.")

    crumbs = [home_crumb(), (L("Kantone", "Cantons", "Cantons"), i18n.url("cantons")), (name, path)]
    parts = [crumbs_html(crumbs)]
    parts.append(f'<div class="article-badge">{L("Prämien", "Primes", "Premiums")} {YEAR}</div>')
    parts.append(L(f"<h1>Krankenkasse {e(name)}: die günstigsten Prämien {YEAR}</h1>",
                   f"<h1>Caisse-maladie {e(name)} : les primes les moins chères {YEAR}</h1>",
                   f"<h1>Health insurance {e(name)}: the cheapest premiums {YEAR}</h1>"))
    parts.append(f'<div class="article-meta">{L(f"Offizielle Prämien des BAG für {YEAR}", f"Primes officielles de l’OFSP pour {YEAR}", f"Official FOPH premiums for {YEAR}")}'
                 f' · {L("Stand", "État au", "As of")} {i18n.date_short(PUBLISHED)}</div>')
    ch_txt = f'{e(cheapest["insurer"])}, {MODEL_LABEL[cheapest["model"]]}'
    parts.append(L(
        f'<p class="kk-lead">Die günstigste Grundversicherung für Erwachsene im Kanton {e(name)} kostet {YEAR} '
        f'<strong>CHF {chf(cheapest["premium"])} pro Monat</strong> ({ch_txt}, '
        f'Franchise 2\'500, {where}). Die Leistungen sind bei allen Kassen gesetzlich gleich, du zahlst nur einen anderen Preis.</p>',
        f'<p class="kk-lead">L’assurance de base la moins chère pour les adultes {e(ik)} coûte en {YEAR} '
        f'<strong>CHF {chf(cheapest["premium"])} par mois</strong> ({ch_txt}, '
        f'franchise 2\'500, {where}). Les prestations sont fixées par la loi et identiques dans toutes les caisses : seul le prix change.</p>',
        f'<p class="kk-lead">The cheapest basic health insurance for adults {e(ik)} costs '
        f'<strong>CHF {chf(cheapest["premium"])} per month</strong> in {YEAR} ({ch_txt}, '
        f'deductible 2\'500, {where}). Benefits are set by law and identical at every insurer, you only pay a different price.</p>'))
    lbl1 = L(f"Prämienveränderung {e(name)} {PREV} auf {YEAR} (Standardmodell, Franchise 300)",
             f"Évolution des primes {e(name)} de {PREV} à {YEAR} (modèle standard, franchise 300)",
             f"Premium change {e(name)} {PREV} to {YEAR} (standard model, deductible 300)")
    lbl2 = L("Durchschnittliche Standardprämie pro Monat, Franchise 300",
             "Prime standard moyenne par mois, franchise 300",
             "Average standard premium per month, deductible 300")
    lbl3 = L("pro Jahr zwischen teuerster und günstigster Kasse, gleiches Modell und gleiche Franchise",
             "par an entre la caisse la plus chère et la moins chère, même modèle et même franchise",
             "per year between the most expensive and the cheapest insurer, same model and deductible")
    parts.append(f"""<div class="kk-facts">
  <div class="kk-fact"><div class="kk-fact-val">{pct(info['change_pct'])}</div><div class="kk-fact-label">{lbl1}</div></div>
  <div class="kk-fact"><div class="kk-fact-val">CHF {chf(info['avg_standard'], 0)}</div><div class="kk-fact-label">{lbl2}</div></div>
  <div class="kk-fact"><div class="kk-fact-val">CHF {chf(spread, 0)}</div><div class="kk-fact-label">{lbl3}</div></div>
</div>""")
    parts.append(f'<a class="kk-cta" href="{i18n.url("home")}#kk-rechner">'
                 f'{L("Deine Prämie mit PLZ berechnen", "Calculer votre prime avec votre NPA", "Calculate your premium by postcode")} &rarr;</a>')

    parts.append(L(f"<h2>Die 10 günstigsten Krankenkassen im Kanton {e(name)} {YEAR}</h2>",
                   f"<h2>Les 10 caisses-maladie les moins chères {e(ik)} en {YEAR}</h2>",
                   f"<h2>The 10 cheapest health insurers {e(ik)} {YEAR}</h2>"))
    parts.append(L(f"<p>Erwachsene ab 26, Franchise CHF 2'500, mit Unfalldeckung, {where}. Pro Kasse der günstigste Tarif. "
                   f"Die Veränderung vergleicht denselben Tarif mit {PREV}.</p>",
                   f"<p>Adultes dès 26 ans, franchise CHF 2'500, avec couverture accidents, {where}. Pour chaque caisse, le tarif le moins cher. "
                   f"L’évolution compare le même tarif avec {PREV}.</p>",
                   f"<p>Adults aged 26 and over, deductible CHF 2'500, with accident cover, {where}. The cheapest tariff of each insurer. "
                   f"The change compares the same tariff with {PREV}.</p>"))
    parts.append(rank_table(any_2500))

    parts.append(L("<h2>Standardmodell mit freier Arztwahl</h2>", "<h2>Modèle standard avec libre choix du médecin</h2>",
                   "<h2>Standard model with free choice of doctor</h2>"))
    parts.append(L(f"<p>Wer keine Einschränkung bei der Arztwahl will: die günstigsten Kassen im Standardmodell, "
                   f"Franchise CHF 300, {where}.</p>",
                   f"<p>Pour qui ne veut aucune restriction dans le choix du médecin : les caisses les moins chères en modèle standard, "
                   f"franchise CHF 300, {where}.</p>",
                   f"<p>If you want no restriction on your choice of doctor: the cheapest insurers in the standard model, "
                   f"deductible CHF 300, {where}.</p>"))
    parts.append(rank_table(std_300[:10], show_model=False))

    if len(regs) > 1:
        parts.append(L(f"<h2>Prämienregionen im Kanton {e(name)}</h2>", f"<h2>Régions de primes {e(ik)}</h2>",
                       f"<h2>Premium regions {e(ik)}</h2>"))
        ml = region_label(main, len(regs), c)
        parts.append(L(f"<p>Der Kanton {e(name)} ist in {len(regs)} Prämienregionen aufgeteilt. Die Tabellen oben gelten für "
                       f"{ml}. In den anderen Regionen ist die günstigste Kasse:</p><ul>",
                       f"<p>Le canton est divisé en {len(regs)} régions de primes. Les tableaux ci-dessus valent pour la "
                       f"{ml}. Dans les autres régions, la caisse la moins chère est :</p><ul>",
                       f"<p>The canton is divided into {len(regs)} premium regions. The tables above apply to "
                       f"{ml}. In the other regions, the cheapest insurer is:</p><ul>"))
        for reg in regs:
            if reg == main:
                continue
            best = ranking(rows_c, c, reg, 2500, prev_idx, n=1)[0]
            parts.append(f"<li><strong>{region_label(reg, len(regs), c)}:</strong> {e(best['insurer'])} "
                         f"({MODEL_LABEL[best['model']]}), CHF {chf(best['premium'])} {L('pro Monat', 'par mois', 'per month')}</li>")
        parts.append("</ul>")
        for reg in regs:
            gem = regions.get(c, {}).get(reg)
            if gem:
                parts.append(f'<details class="kk-gemeinden"><summary>{L("Gemeinden in", "Communes de la", "Municipalities in")} {region_label(reg, len(regs))} ({len(gem)})</summary>'
                             f'<p>{e(", ".join(gem))}</p></details>')

    parts.append(rating_canton_block(c, main))
    parts.append(vorjahr_block(c))

    ranked = sorted(insurers_c, key=lambda x: x["change"])
    if len(ranked) >= 4:
        parts.append(L(f"<h2>So stark schlägt jede Kasse im Kanton {e(name)} auf</h2>",
                       f"<h2>La hausse de chaque caisse {e(ik)}</h2>",
                       f"<h2>How much each insurer raises premiums {e(ik)}</h2>"))
        parts.append(L(f"<p>Veränderung der Standardprämie von {PREV} auf {YEAR}, Franchise 300, Erwachsene, Mittel über die Prämienregionen. Wer am wenigsten aufschlägt, steht oben. "
                       f"Durchschnitt im Kanton: <strong>{pct(info['change_pct'])}</strong>.</p>",
                       f"<p>Évolution de la prime standard de {PREV} à {YEAR}, franchise 300, adultes, moyenne des régions de primes. La caisse qui augmente le moins figure en tête. "
                       f"Moyenne du canton : <strong>{pct(info['change_pct'])}</strong>.</p>",
                       f"<p>Change in the standard premium from {PREV} to {YEAR}, deductible 300, adults, average across premium regions. The smallest increase is at the top. "
                       f"Canton average: <strong>{pct(info['change_pct'])}</strong>.</p>"))
        rows_html = "".join(
            f'<tr><td><strong>{e(x["name"])}</strong></td><td class="num">CHF {chf(x["premium"], 0)}</td>'
            f'<td class="num {"kk-up" if x["change"] > 0 else "kk-down"}">{pct(x["change"])}</td></tr>'
            for x in ranked)
        parts.append(f'<div class="kk-table-wrap"><table class="kk-table"><thead><tr><th>{L("Kasse", "Caisse", "Insurer")}</th>'
                     f'<th class="num">Ø Standard {YEAR}</th><th class="num">vs. {PREV}</th></tr></thead>'
                     f'<tbody>{rows_html}</tbody></table></div>')

    qa = [
        (L(f"Welche Krankenkasse ist {YEAR} im Kanton {name} am günstigsten?",
           f"Quelle est la caisse-maladie la moins chère {ik} en {YEAR} ?",
           f"Which health insurer is cheapest {ik} in {YEAR}?"),
         L(f"Für Erwachsene mit Franchise 2'500 und Unfalldeckung ist {cheapest['insurer']} "
           f"({MODEL_LABEL[cheapest['model']]}) mit CHF {chf(cheapest['premium'])} pro Monat am günstigsten, {where}. "
           f"Im Standardmodell mit Franchise 300 ist es {std_300[0]['insurer']} mit CHF {chf(std_300[0]['premium'])}.",
           f"Pour les adultes avec une franchise de 2'500 et la couverture accidents, {cheapest['insurer']} "
           f"({MODEL_LABEL[cheapest['model']]}) est la moins chère avec CHF {chf(cheapest['premium'])} par mois, {where}. "
           f"En modèle standard avec franchise 300, c’est {std_300[0]['insurer']} avec CHF {chf(std_300[0]['premium'])}.",
           f"For adults with a 2'500 deductible and accident cover, {cheapest['insurer']} "
           f"({MODEL_LABEL[cheapest['model']]}) is the cheapest at CHF {chf(cheapest['premium'])} per month, {where}. "
           f"In the standard model with a 300 deductible it is {std_300[0]['insurer']} at CHF {chf(std_300[0]['premium'])}.")),
        (L(f"Wie stark steigen die Krankenkassenprämien {YEAR} im Kanton {name}?",
           f"De combien les primes augmentent-elles en {YEAR} {ik} ?",
           f"How much are health insurance premiums rising in {YEAR} {ik}?"),
         L(f"Die Standardprämie für Erwachsene mit Franchise 300 steigt im Kanton {name} im Schnitt um "
           f"{pct(info['change_pct'])}, gewichtet nach Versichertenzahl der Kassen. Schweizweit steigt die mittlere "
           f"Prämie laut BAG um {BAG_OFFICIAL['change_pct']:.1f} Prozent.",
           f"La prime standard des adultes avec franchise 300 augmente en moyenne de {pct(info['change_pct'])} {ik}, "
           f"pondérée selon le nombre d’assurés des caisses. Pour toute la Suisse, la prime moyenne augmente de "
           f"{i18n.dec(BAG_OFFICIAL['change_pct'])} % selon l’OFSP.",
           f"The standard premium for adults with a 300 deductible rises by {pct(info['change_pct'])} on average {ik}, "
           f"weighted by each insurer’s number of insured persons. Across Switzerland, the average premium rises by "
           f"{i18n.dec(BAG_OFFICIAL['change_pct'])}% according to the FOPH.")),
        (L(f"Bis wann kann ich die Krankenkasse für {YEAR} wechseln?",
           f"Jusqu’à quand puis-je changer de caisse-maladie pour {YEAR} ?",
           f"When is the deadline to switch health insurer for {YEAR}?"),
         L(f"Die Kündigung der Grundversicherung muss bis am {deadline()} bei deiner Kasse eingetroffen sein. "
           f"Die neue Kasse muss dich ohne Gesundheitsfragen aufnehmen, der Wechsel gilt ab 1. Januar {YEAR}.",
           f"La résiliation de l’assurance de base doit parvenir à votre caisse au plus tard le {deadline()}. "
           f"La nouvelle caisse doit vous accepter sans questions de santé, le changement prend effet le 1er janvier {YEAR}.",
           f"Your cancellation of basic insurance must reach your insurer by {deadline()}. "
           f"The new insurer must accept you without health questions, and the switch takes effect on 1 January {YEAR}.")),
    ]
    parts.append(f'<div class="kk-faq"><h2>{L("Häufige Fragen", "Questions fréquentes", "Frequently asked questions")}</h2>')
    for q, a in qa:
        parts.append(f"<h3>{e(q)}</h3><p>{e(a)}</p>")
    parts.append("</div>")
    rep = i18n.url("report")
    parts.append(L(
        f'<p class="kk-note">Quelle: Bundesamt für Gesundheit (BAG), Prämien {YEAR} und {PREV} '
        f'(<a href="https://opendata.swiss/de/dataset/health-insurance-premiums">opendata.swiss</a>). '
        f'Angaben ohne Gewähr. So rechnen wir: <a href="{rep}#methode">Methode</a>. '
        f'Alle Kantone: <a href="{i18n.url("cantons")}">Übersicht</a>.</p>',
        f'<p class="kk-note">Source : Office fédéral de la santé publique (OFSP), primes {YEAR} et {PREV} '
        f'(<a href="https://opendata.swiss/fr/dataset/health-insurance-premiums">opendata.swiss</a>). '
        f'Sans garantie. Notre calcul : <a href="{rep}#methode">méthode</a>. '
        f'Tous les cantons : <a href="{i18n.url("cantons")}">vue d’ensemble</a>.</p>',
        f'<p class="kk-note">Source: Federal Office of Public Health (FOPH), premiums {YEAR} and {PREV} '
        f'(<a href="https://opendata.swiss/en/dataset/health-insurance-premiums">opendata.swiss</a>). '
        f'No liability for accuracy. How we calculate: <a href="{rep}#methode">methodology</a>. '
        f'All cantons: <a href="{i18n.url("cantons")}">overview</a>.</p>'))

    jsonld = [breadcrumb(crumbs), faq(qa)]
    return path, page(path, title, desc, "\n".join(parts), jsonld, alts_of(lambda: canton_url(c)))


def hub_page(cantons, cheapest_by_canton):
    path = i18n.url("cantons")
    title = L(f"Günstigste Krankenkasse {YEAR} nach Kanton: alle 26 Kantone",
              f"Caisse-maladie la moins chère {YEAR} par canton : les 26 cantons",
              f"Cheapest health insurer {YEAR} by canton: all 26 cantons")
    desc = L(f"Krankenkassenprämien {YEAR} für alle 26 Kantone: günstigste Kasse, durchschnittliche Standardprämie "
             f"und Veränderung zu {PREV}. Offizielle BAG-Daten.",
             f"Primes d’assurance-maladie {YEAR} pour les 26 cantons : caisse la moins chère, prime standard moyenne "
             f"et évolution par rapport à {PREV}. Données officielles de l’OFSP.",
             f"Health insurance premiums {YEAR} for all 26 cantons: cheapest insurer, average standard premium "
             f"and change since {PREV}. Official FOPH data.")
    rows = []
    for c, name, curl in sorted_cantons():
        ch = cheapest_by_canton[c]
        reg = (RATING or {}).get("regions", {}).get(f"{c}|{MAIN_REGION.get(c)}", {})
        top = max(reg.items(), key=lambda x: x[1]["note"] or 0, default=None)
        durable = (f'{e(INSURER_NAMES[str(top[0])])}<span class="sub">{L("Note", "Note", "Score")} {note_fmt(top[1]["note"])}</span>' if top else "–")
        rows.append(
            f'<tr><td><a href="{curl}"><strong>{e(name)}</strong></a></td>'
            f'<td>{e(ch["insurer"])}<span class="sub">CHF {chf(ch["premium"])}, {L("Franchise", "franchise", "deductible")} 2\'500</span></td>'
            f'<td>{durable}</td>'
            f'<td class="num">CHF {chf(cantons[c]["avg_standard"], 0)}</td>'
            f'<td class="num kk-up">{pct(cantons[c]["change_pct"])}</td></tr>')
    crumbs = [home_crumb(), (L("Kantone", "Cantons", "Cantons"), path)]
    calc = f'{i18n.url("home")}#kk-rechner'
    rep = i18n.url("report")
    body = [
        crumbs_html(crumbs),
        f'<div class="article-badge">{L("Prämien", "Primes", "Premiums")} {YEAR}</div>',
        L(f"<h1>Günstigste Krankenkasse {YEAR} in jedem Kanton</h1>",
          f"<h1>La caisse-maladie la moins chère {YEAR} dans chaque canton</h1>",
          f"<h1>The cheapest health insurer {YEAR} in every canton</h1>"),
        L('<div class="article-meta">Offizielle Prämien des BAG · alle 26 Kantone</div>',
          '<div class="article-meta">Primes officielles de l’OFSP · les 26 cantons</div>',
          '<div class="article-meta">Official FOPH premiums · all 26 cantons</div>'),
        L(f"<p class=\"kk-lead\">Wie teuer die Grundversicherung ist, hängt vor allem vom Wohnort ab. "
          f"Hier siehst du für jeden Kanton die günstigste Kasse {YEAR}, die durchschnittliche Standardprämie und wie stark sie steigt.</p>",
          f"<p class=\"kk-lead\">Le prix de l’assurance de base dépend surtout du lieu de domicile. "
          f"Voici pour chaque canton la caisse la moins chère en {YEAR}, la prime standard moyenne et sa hausse.</p>",
          f"<p class=\"kk-lead\">What you pay for basic health insurance depends mostly on where you live. "
          f"Here you can see the cheapest insurer {YEAR} in each canton, the average standard premium and how much it rises.</p>"),
        f'<a class="kk-cta" href="{calc}">{L("Prämie für deine PLZ berechnen", "Calculer la prime pour votre NPA", "Calculate the premium for your postcode")} &rarr;</a>',
        f'<div class="kk-table-wrap"><table class="kk-table"><thead><tr><th>{L("Kanton", "Canton", "Canton")}</th>'
        f'<th>{L("Günstigste Kasse", "Caisse la moins chère", "Cheapest insurer")}</th><th>{L("Dauerhaft günstig", "Durablement avantageuse", "Consistently cheap")}</th>'
        f'<th class="num">Ø Standard</th><th class="num">vs. {PREV}</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>',
        L(f'<p class="kk-note">Günstigste Kasse: Erwachsene, Franchise 2\'500, mit Unfall, alle Modelle, Hauptregion des Kantons. '
          f'Dauerhaft günstig: beste Note im <a href="{RATING_PATH}">Preistreue-Rating</a> in der Hauptregion. '
          f'Ø Standard und Veränderung: Standardmodell, Franchise 300, gewichtet nach Versichertenzahl. '
          f'Details zur Rechnung: <a href="{rep}#methode">Methode</a>.</p>',
          f'<p class="kk-note">Caisse la moins chère : adultes, franchise 2\'500, avec accidents, tous les modèles, région principale du canton. '
          f'Durablement avantageuse : meilleure note de la <a href="{i18n.url("rating")}">notation Constance des primes</a> dans la région principale. '
          f'Ø standard et évolution : modèle standard, franchise 300, pondéré selon le nombre d’assurés. '
          f'Détails du calcul : <a href="{rep}#methode">méthode</a>.</p>',
          f'<p class="kk-note">Cheapest insurer: adults, deductible 2\'500, with accident cover, all models, main region of the canton. '
          f'Consistently cheap: best score in the <a href="{i18n.url("rating")}">Price Consistency Rating</a> in the main region. '
          f'Ø standard and change: standard model, deductible 300, weighted by number of insured persons. '
          f'Calculation details: <a href="{rep}#methode">methodology</a>.</p>'),
    ]
    jsonld = [breadcrumb(crumbs)]
    return path, page(path, title, desc, "\n".join(body), jsonld, dict(i18n.ROUTES["cantons"]))


def report_page(cantons, insurers, nat, model_counts, jojo):
    path = i18n.url("report")
    by_change = sorted(cantons.items(), key=lambda x: -x[1]["change_pct"])
    big = sorted([x for x in insurers.values() if x["bestand"] >= MIN_BESTAND_RANKING], key=lambda x: x["change_pct"])
    bag = BAG_OFFICIAL["change_pct"]
    bag_t = i18n.dec(bag)
    title = L(f"Krankenkassenprämien {YEAR}: So stark steigen sie in deinem Kanton",
              f"Primes d’assurance-maladie {YEAR} : la hausse dans votre canton",
              f"Health insurance premiums {YEAR}: how much they rise in your canton")
    desc = L(f"Prämien {YEAR}: +{bag:.1f}% im Schnitt (BAG). Unsere Auswertung aller Kassen und "
             f"Kantone: wer am stärksten aufschlägt, wer günstig bleibt, und bis wann du wechseln kannst.",
             f"Primes {YEAR} : +{bag_t} % en moyenne (OFSP). Notre analyse de toutes les caisses et de tous les cantons : "
             f"qui augmente le plus, qui reste avantageux et jusqu’à quand changer.",
             f"Premiums {YEAR}: +{bag_t}% on average (FOPH). Our analysis of all insurers and cantons: "
             f"who raises most, who stays cheap, and the deadline to switch.")
    hi, lo = by_change[0], by_change[-1]
    canton_rows = "".join(
        f'<tr><td><a href="{canton_url(c)}">{e(cname(c))}</a></td>'
        f'<td class="num">CHF {chf(v["avg_standard"], 0)}</td><td class="num kk-up">{pct(v["change_pct"])}</td></tr>'
        for c, v in by_change)
    ins_rows = "".join(
        f'<tr><td><strong>{e(x["name"])}</strong><span class="sub">{x["cantons"]} {L("Kantone", "cantons", "cantons")}, '
        f'{chf(x["bestand"] / 1000, 0)}k {L("Versicherte", "assurés", "insured")}</span></td>'
        f'<td class="num {"kk-up" if x["change_pct"] > 0 else "kk-down"}">{pct(x["change_pct"])}</td></tr>'
        for x in big)
    models = "".join(f"<li><strong>{MODEL_LABEL[m]}:</strong> {n} {L('Kantone', 'cantons', 'cantons')}</li>"
                     for m, n in sorted(model_counts.items(), key=lambda x: -x[1]))
    mx, mn = BAG_OFFICIAL["max_canton"], BAG_OFFICIAL["min_canton"]
    qa = [
        (L(f"Wie stark steigen die Krankenkassenprämien {YEAR}?", f"De combien les primes augmentent-elles en {YEAR} ?",
           f"How much are health insurance premiums rising in {YEAR}?"),
         L(f"Die mittlere Prämie steigt laut BAG um {bag:.1f} Prozent. Erwachsene zahlen im Schnitt "
           f"CHF {chf(BAG_OFFICIAL['adult_mean'])} pro Monat, CHF {chf(BAG_OFFICIAL['adult_delta'])} mehr als {PREV}.",
           f"Selon l’OFSP, la prime moyenne augmente de {bag_t} %. Les adultes paient en moyenne "
           f"CHF {chf(BAG_OFFICIAL['adult_mean'])} par mois, soit CHF {chf(BAG_OFFICIAL['adult_delta'])} de plus qu’en {PREV}.",
           f"According to the FOPH, the average premium rises by {bag_t}%. Adults pay CHF {chf(BAG_OFFICIAL['adult_mean'])} "
           f"per month on average, CHF {chf(BAG_OFFICIAL['adult_delta'])} more than in {PREV}.")),
        (L(f"In welchem Kanton steigen die Prämien {YEAR} am stärksten?", f"Dans quel canton les primes augmentent-elles le plus en {YEAR} ?",
           f"In which canton are premiums rising most in {YEAR}?"),
         L(f"Laut BAG im Kanton {CANTONS[mx[0]][0]} (+{mx[1]:.1f}%), am "
           f"schwächsten in {CANTONS[mn[0]][0]} (+{mn[1]:.1f}%). "
           f"Im Standardmodell mit Franchise 300 steigt die Prämie nach unserer Auswertung in {CANTONS[hi[0]][0]} am stärksten "
           f"({pct(hi[1]['change_pct'])}) und in {CANTONS[lo[0]][0]} am wenigsten ({pct(lo[1]['change_pct'])}).",
           f"Selon l’OFSP, {im_kanton(mx[0])} (+{i18n.dec(mx[1])} %), et le moins {im_kanton(mn[0])} (+{i18n.dec(mn[1])} %). "
           f"En modèle standard avec franchise 300, notre analyse montre la plus forte hausse {im_kanton(hi[0])} "
           f"({pct(hi[1]['change_pct'])}) et la plus faible {im_kanton(lo[0])} ({pct(lo[1]['change_pct'])}).",
           f"According to the FOPH, {im_kanton(mx[0])} (+{i18n.dec(mx[1])}%), and least {im_kanton(mn[0])} (+{i18n.dec(mn[1])}%). "
           f"In the standard model with a 300 deductible, our analysis shows the largest rise {im_kanton(hi[0])} "
           f"({pct(hi[1]['change_pct'])}) and the smallest {im_kanton(lo[0])} ({pct(lo[1]['change_pct'])}).")),
        (L("Bis wann muss ich die Krankenkasse kündigen?", "Jusqu’à quand dois-je résilier ma caisse-maladie ?",
           "What is the deadline to cancel my health insurance?"),
         L(f"Die Kündigung der Grundversicherung muss bis am {deadline()} bei der Kasse eingetroffen sein. "
           f"Die neue Kasse gilt dann ab 1. Januar {YEAR}.",
           f"La résiliation de l’assurance de base doit parvenir à la caisse au plus tard le {deadline()}. "
           f"La nouvelle caisse vous assure alors dès le 1er janvier {YEAR}.",
           f"Your cancellation of basic insurance must reach the insurer by {deadline()}. "
           f"The new insurer then covers you from 1 January {YEAR}.")),
    ]
    crumbs = [home_crumb(), (L(f"Prämien {YEAR}", f"Primes {YEAR}", f"Premiums {YEAR}"), path)]
    calc = f'{i18n.url("home")}#kk-rechner'
    insurer = L("Kasse", "Caisse", "Insurer")
    od = L("de", "fr", "en")
    body = [
        crumbs_html(crumbs),
        f'<div class="article-badge">{L("Auswertung", "Analyse", "Analysis")}</div>',
        L(f"<h1>Krankenkassenprämien {YEAR}: wer wie stark aufschlägt</h1>",
          f"<h1>Primes d’assurance-maladie {YEAR} : qui augmente de combien</h1>",
          f"<h1>Health insurance premiums {YEAR}: who raises them by how much</h1>"),
        L(f'<div class="article-meta">Veröffentlicht {i18n.date_short(PUBLISHED)} · Daten: BAG, Prämien {PREV} und {YEAR}</div>',
          f'<div class="article-meta">Publié le {i18n.date_short(PUBLISHED)} · Données : OFSP, primes {PREV} et {YEAR}</div>',
          f'<div class="article-meta">Published {i18n.date_short(PUBLISHED)} · Data: FOPH, premiums {PREV} and {YEAR}</div>'),
        L(f"<p class=\"kk-lead\">Die Krankenkassenprämien steigen {YEAR} erneut. Die mittlere Prämie legt laut Bundesamt für Gesundheit um "
          f"<strong>{bag:.1f} Prozent</strong> zu (<a href=\"{BAG_OFFICIAL['source_url']}\">SRF</a>). "
          f"Wir haben die Prämien aller Kassen in allen Kantonen verglichen: Der Durchschnitt verdeckt, wie unterschiedlich die Kassen aufschlagen.</p>",
          f"<p class=\"kk-lead\">Les primes d’assurance-maladie augmentent encore en {YEAR}. Selon l’Office fédéral de la santé publique, la prime moyenne progresse de "
          f"<strong>{bag_t} %</strong> (<a href=\"{BAG_OFFICIAL['source_url']}\">SRF</a>). "
          f"Nous avons comparé les primes de toutes les caisses dans tous les cantons : la moyenne cache de grandes différences entre les caisses.</p>",
          f"<p class=\"kk-lead\">Health insurance premiums are rising again in {YEAR}. According to the Federal Office of Public Health, the average premium goes up by "
          f"<strong>{bag_t}%</strong> (<a href=\"{BAG_OFFICIAL['source_url']}\">SRF</a>). "
          f"We compared the premiums of every insurer in every canton: the average hides how differently insurers raise their prices.</p>"),
        f"""<div class="kk-facts">
  <div class="kk-fact"><div class="kk-fact-val">+{bag_t}&#8239;%</div><div class="kk-fact-label">{L(f"mittlere Prämie {YEAR} laut BAG", f"prime moyenne {YEAR} selon l’OFSP", f"average premium {YEAR} according to the FOPH")}</div></div>
  <div class="kk-fact"><div class="kk-fact-val">{pct(nat)}</div><div class="kk-fact-label">{L("Standardmodell, Franchise 300, unsere Auswertung", "modèle standard, franchise 300, notre analyse", "standard model, deductible 300, our analysis")}</div></div>
  <div class="kk-fact"><div class="kk-fact-val">{deadline(short=True)}</div><div class="kk-fact-label">{L("Kündigung muss bei der Kasse sein", "la résiliation doit être parvenue à la caisse", "cancellation must reach the insurer")}</div></div>
</div>""",
        f'<a class="kk-cta" href="{calc}">{L(f"Jetzt deine Prämie {YEAR} vergleichen", f"Comparer votre prime {YEAR}", f"Compare your {YEAR} premium now")} &rarr;</a>',
        L(f"<h2>Prämienveränderung {YEAR} nach Kanton</h2>", f"<h2>Évolution des primes {YEAR} par canton</h2>", f"<h2>Premium change {YEAR} by canton</h2>"),
        L("<p>Durchschnittliche Standardprämie für Erwachsene, Franchise 300, mit Unfall, gewichtet nach Versichertenzahl der Kassen. "
          "Ein Klick auf den Kanton zeigt die günstigsten Kassen.</p>",
          "<p>Prime standard moyenne des adultes, franchise 300, avec accidents, pondérée selon le nombre d’assurés des caisses. "
          "Un clic sur le canton affiche les caisses les moins chères.</p>",
          "<p>Average standard premium for adults, deductible 300, with accident cover, weighted by each insurer’s number of insured persons. "
          "Click a canton to see the cheapest insurers.</p>"),
        f'<div class="kk-table-wrap"><table class="kk-table"><thead><tr><th>{L("Kanton", "Canton", "Canton")}</th><th class="num">Ø Standard {YEAR}</th>'
        f'<th class="num">vs. {PREV}</th></tr></thead><tbody>{canton_rows}</tbody></table></div>',
        L(f"<h2>Prämienveränderung {YEAR} nach Kasse</h2>", f"<h2>Évolution des primes {YEAR} par caisse</h2>", f"<h2>Premium change {YEAR} by insurer</h2>"),
        L(f"<p>Veränderung der Standardprämie, Franchise 300, über alle Kantone gewichtet nach Versichertenzahl. "
          f"Aufgeführt sind Kassen mit mindestens {chf(MIN_BESTAND_RANKING, 0)} Versicherten. Wer am wenigsten aufschlägt, steht oben.</p>",
          f"<p>Évolution de la prime standard, franchise 300, sur tous les cantons, pondérée selon le nombre d’assurés. "
          f"Seules les caisses d’au moins {chf(MIN_BESTAND_RANKING, 0)} assurés figurent ici. La plus faible hausse est en tête.</p>",
          f"<p>Change in the standard premium, deductible 300, across all cantons weighted by number of insured persons. "
          f"Listed are insurers with at least {chf(MIN_BESTAND_RANKING, 0)} insured persons. The smallest increase is at the top.</p>"),
        f'<div class="kk-table-wrap"><table class="kk-table"><thead><tr><th>{insurer}</th><th class="num">vs. {PREV}</th></tr></thead>'
        f'<tbody>{ins_rows}</tbody></table></div>',
        *jojo_html(jojo),
        L(f"<h2>Welches Modell ist {YEAR} am günstigsten?</h2>", f"<h2>Quel modèle est le moins cher en {YEAR} ?</h2>",
          f"<h2>Which model is cheapest in {YEAR}?</h2>"),
        L(f"<p>In wie vielen Kantonen stellt welches Modell die günstigste Prämie (Erwachsene, Franchise 300, Hauptregion)? "
          f"Das BAG teilt die Modelle ab {YEAR} neu ein: Alternativ steht für flexible Modelle, bei denen du zwischen Hausarzt, "
          f"Telmed und Apotheke wählst.</p><ul>{models}</ul>",
          f"<p>Dans combien de cantons chaque modèle offre-t-il la prime la moins chère (adultes, franchise 300, région principale) ? "
          f"Dès {YEAR}, l’OFSP classe les modèles autrement : « alternatif » désigne les modèles flexibles où vous choisissez entre "
          f"médecin de famille, Telmed et pharmacie.</p><ul>{models}</ul>",
          f"<p>In how many cantons does each model offer the cheapest premium (adults, deductible 300, main region)? "
          f"From {YEAR} the FOPH groups models differently: alternative stands for flexible models where you choose between "
          f"family doctor, Telmed and pharmacy.</p><ul>{models}</ul>"),
        f'<div class="kk-faq"><h2>{L("Häufige Fragen", "Questions fréquentes", "Frequently asked questions")}</h2>',
        *[f"<h3>{e(q)}</h3><p>{e(a)}</p>" for q, a in qa],
        "</div>",
        f'<h2 id="methode">{L("So rechnen wir", "Notre méthode de calcul", "How we calculate")}</h2>',
        L(f"<p>Grundlage sind die Prämiendaten des BAG für {PREV} und {YEAR} "
          f"(<a href=\"https://opendata.swiss/de/dataset/health-insurance-premiums\">opendata.swiss</a>) und der Versichertenbestand je Kasse und Kanton. "
          f"Als Referenz nehmen wir Erwachsene ab 26, Franchise 300, mit Unfalldeckung, Standardmodell. Die Veränderung je Kasse "
          f"und Kanton ist der Mittelwert über die Prämienregionen. Durchschnitte über mehrere Kassen gewichten wir mit der Zahl "
          f"der Versicherten. Das BAG rechnet über alle Modelle und Franchisen, daher weichen unsere Werte leicht ab.</p>",
          f"<p>Nous nous basons sur les données de primes de l’OFSP pour {PREV} et {YEAR} "
          f"(<a href=\"https://opendata.swiss/fr/dataset/health-insurance-premiums\">opendata.swiss</a>) et sur l’effectif des assurés par caisse et par canton. "
          f"La référence est un adulte dès 26 ans, franchise 300, avec couverture accidents, modèle standard. L’évolution par caisse "
          f"et par canton est la moyenne des régions de primes. Les moyennes sur plusieurs caisses sont pondérées selon le nombre "
          f"d’assurés. L’OFSP calcule sur tous les modèles et toutes les franchises, d’où de légers écarts avec nos valeurs.</p>",
          f"<p>We use the FOPH premium data for {PREV} and {YEAR} "
          f"(<a href=\"https://opendata.swiss/en/dataset/health-insurance-premiums\">opendata.swiss</a>) and the number of insured persons per insurer and canton. "
          f"Our reference is an adult aged 26 or over, deductible 300, with accident cover, standard model. The change per insurer "
          f"and canton is the mean across premium regions. Averages across several insurers are weighted by number of "
          f"insured persons. The FOPH calculates across all models and deductibles, so our figures differ slightly.</p>"),
        L(f"<p>Veränderungen einzelner Tarife vergleichen denselben Tarif einer Kasse in beiden Jahren. "
          f"Ist ein Tarif neu, steht «neu». Die Namen der Kassen stammen aus dem "
          f"<a href=\"https://www.bag.admin.ch/de/verzeichnisse-der-zugelassenen-kranken-und-rueckversicherer\">Verzeichnis der zugelassenen Krankenversicherer</a>.</p>",
          f"<p>L’évolution d’un tarif compare le même tarif d’une caisse sur les deux années. "
          f"Un tarif nouveau est signalé « nouveau ». Les noms des caisses proviennent de la "
          f"<a href=\"https://www.bag.admin.ch/fr/verzeichnisse-der-zugelassenen-kranken-und-rueckversicherer\">liste des assureurs-maladie autorisés</a>.</p>",
          f"<p>Changes in individual tariffs compare the same tariff of an insurer in both years. "
          f"A new tariff is marked “new”. Insurer names come from the FOPH "
          f"<a href=\"https://www.bag.admin.ch/en/verzeichnisse-der-zugelassenen-kranken-und-rueckversicherer\">list of licensed health insurers</a>.</p>"),
    ]
    jsonld = [breadcrumb(crumbs), faq(qa), {
        "@context": "https://schema.org", "@type": "Article",
        "headline": title, "datePublished": PUBLISHED, "dateModified": date.today().isoformat(),
        "author": {"@type": "Organization", "name": "abovergleich.com"},
        "publisher": {"@type": "Organization", "name": "abovergleich.com"},
        "mainEntityOfPage": f"{SITE}{path}", "inLanguage": i18n.HREFLANG[i18n.LANG],
    }]
    return path, page(path, title, desc, "\n".join(body), jsonld, dict(i18n.ROUTES["report"]))


def jojo_html(jojo):
    cur = jojo.get(f"{PREV}-{YEAR}")
    if not cur:
        return []
    prev = jojo.get(f"{YEAR - 2}-{PREV}")
    whole = L("ganzer Kanton", "tout le canton", "whole canton")
    rows = "".join(
        f'<tr><td><a href="{canton_url(x["canton"])}">{e(cname(x["canton"]))}</a>'
        f'<span class="sub">{L("Region", "Région", "Region") + " " + x["region"][-1] if x["region"][-1] != "0" else whole}</span></td>'
        f'<td><strong>{e(x["insurer"])}</strong><span class="sub">{MODEL_LABEL[x["model"]]} · {e(x["tariff"])}</span></td>'
        f'<td class="num">CHF {chf(x["before"])}<span class="sub">→ CHF {chf(x["after"])}</span></td>'
        f'<td class="num kk-up">{pct(x["change"])}<span class="sub">{L("Markt", "Marché", "Market")} {pct(x["market"])}</span></td>'
        f'<td class="num">{x["rank_after"]} / {x["n_after"]}</td></tr>'
        for x in cur["rows"][:10])
    prev_txt = L(f" Im Jahr davor war es gleich: Die Sieger von {YEAR - 2} stiegen um {pct(prev['winner_change'])}, "
                 f"der Markt um {pct(prev['market_change'])}.",
                 f" L’année précédente, c’était pareil : les moins chères de {YEAR - 2} ont augmenté de {pct(prev['winner_change'])}, "
                 f"le marché de {pct(prev['market_change'])}.",
                 f" The year before was the same: the {YEAR - 2} winners rose by {pct(prev['winner_change'])}, "
                 f"the market by {pct(prev['market_change'])}.") if prev else ""
    gap = chf(jojo['model_switch_median'], 0)
    return [
        L('<h2 id="vorjahressieger">Der günstigste Tarif vom letzten Jahr schlägt am stärksten auf</h2>',
          '<h2 id="vorjahressieger">Le tarif le moins cher de l’an dernier augmente le plus</h2>',
          '<h2 id="vorjahressieger">Last year’s cheapest tariff rises the most</h2>'),
        L(f"<p>Wir haben in jeder Prämienregion den günstigsten Tarif von {PREV} genommen und geschaut, was er {YEAR} kostet "
          f"(Erwachsene, Franchise 2'500, ohne Unfall). Ergebnis über {cur['regions']} Regionen: Der Vorjahressieger steigt im Schnitt um "
          f"<strong>{pct(cur['winner_change'])}</strong>, der Median aller Tarife in derselben Region um {pct(cur['market_change'])}. "
          f"Nur in {cur['still_first']} von {cur['regions']} Regionen ist er noch der günstigste, in {cur['out_of_top5']} fällt er aus den Top 5.{prev_txt}</p>",
          f"<p>Dans chaque région de primes, nous avons pris le tarif le moins cher de {PREV} et regardé ce qu’il coûte en {YEAR} "
          f"(adultes, franchise 2'500, sans accidents). Résultat sur {cur['regions']} régions : la moins chère de l’an dernier augmente en moyenne de "
          f"<strong>{pct(cur['winner_change'])}</strong>, la médiane de tous les tarifs de la même région de {pct(cur['market_change'])}. "
          f"Elle n’est plus la moins chère que dans {cur['still_first']} régions sur {cur['regions']}, et sort du top 5 dans {cur['out_of_top5']}.{prev_txt}</p>",
          f"<p>In every premium region we took the cheapest tariff of {PREV} and checked what it costs in {YEAR} "
          f"(adults, deductible 2'500, without accident cover). Result across {cur['regions']} regions: last year’s cheapest rises by "
          f"<strong>{pct(cur['winner_change'])}</strong> on average, the median of all tariffs in the same region by {pct(cur['market_change'])}. "
          f"It is still the cheapest in only {cur['still_first']} of {cur['regions']} regions, and drops out of the top 5 in {cur['out_of_top5']}.{prev_txt}</p>"),
        L(f"<p>Wer einmal zur günstigsten Kasse wechselt und dann bleibt, verliert den Vorsprung also oft schon im nächsten Jahr. "
          f"Es lohnt sich, jedes Jahr neu zu vergleichen. Oft reicht auch ein anderes Modell bei der eigenen Kasse: "
          f"Der Wechsel vom Standardmodell ins günstigste andere Modell derselben Kasse spart im Median "
          f"<strong>CHF {gap} pro Jahr</strong>.</p>",
          f"<p>Qui change une fois pour la caisse la moins chère puis y reste perd donc souvent son avantage dès l’année suivante. "
          f"Comparer chaque année en vaut la peine. Souvent, un autre modèle auprès de votre propre caisse suffit : "
          f"passer du modèle standard au modèle le moins cher de la même caisse fait économiser en médiane "
          f"<strong>CHF {gap} par an</strong>.</p>",
          f"<p>So if you switch to the cheapest insurer once and then stay, you often lose the advantage the very next year. "
          f"It pays to compare every year. Often a different model with your current insurer is enough: "
          f"moving from the standard model to the cheapest other model of the same insurer saves a median of "
          f"<strong>CHF {gap} per year</strong>.</p>"),
        L('<p>Die zehn stärksten Aufschläge bei Vorjahressiegern:</p>', '<p>Les dix plus fortes hausses chez les moins chères de l’an dernier :</p>',
          '<p>The ten largest increases among last year’s cheapest:</p>'),
        f'<div class="kk-table-wrap"><table class="kk-table"><thead><tr><th>Region</th><th>{L("Sieger", "La moins chère", "Cheapest")} {PREV}</th>'
        f'<th class="num">{L("Prämie", "Prime", "Premium")}</th><th class="num">{YEAR}</th><th class="num">{L("Rang", "Rang", "Rank")} {YEAR}</th></tr></thead><tbody>{rows}</tbody></table></div>',
        L(f'<p class="kk-note">Regionen, in denen der Siegertarif {YEAR} nicht mehr angeboten wird oder umbenannt wurde, sind nicht mitgezählt.</p>',
          f'<p class="kk-note">Les régions où ce tarif n’est plus proposé en {YEAR} ou a été renommé ne sont pas comptées.</p>',
          f'<p class="kk-note">Regions where the winning tariff is no longer offered in {YEAR} or was renamed are not counted.</p>'),
    ]


def insights_block(cantons, insurers, nat, top3_prev, top3_cur, ins_prev, nat_prev, top3_prev2, jojo=None):
    """Startseite. Ein Jahr allein täuscht: wer im Vorjahr tief blieb, holt oft
    nach. Darum pro Kasse beide Anstiege und die Summe über zwei Jahre."""
    Y0 = YEAR - 2
    big = []
    for i, x in insurers.items():
        a = ins_prev.get(i, {}).get("change_pct")
        if x["bestand"] < MIN_BESTAND_RANKING or a is None:
            continue
        tot = ((1 + a / 100) * (1 + x["change_pct"] / 100) - 1) * 100
        note = (RATING or {}).get("national", {}).get(i, {}).get("note")
        big.append({"id": i, "prev": a, "cur": x["change_pct"], "tot": tot, "note": note})
    big.sort(key=lambda x: (-(x["note"] or 0), x["tot"]))
    tot_all = ((1 + nat_prev / 100) * (1 + nat / 100) - 1) * 100
    by_change = sorted(cantons.items(), key=lambda x: -x[1]["change_pct"])
    cons = sorted(set(top3_prev2) | set(top3_prev) | set(top3_cur),
                  key=lambda i: -(top3_prev2.get(i, 0) + top3_prev.get(i, 0) + top3_cur.get(i, 0)))[:6]
    u = i18n.url

    def pc(v, ref):
        cls = "var(--red)" if v > ref else "var(--green)"
        return f'<span style="color:{cls};font-weight:600;">{pct(v)}</span>'

    td = 'style="text-align:right;padding:9px 12px;white-space:nowrap;"'
    ana = L("Analyse", "Analyse", "Analysis")
    kas = "".join(
        f'<tr style="border-bottom:1px solid var(--border);"><td style="padding:9px 12px;font-weight:600;">{kasse_link(x["id"])}</td>'
        f'<td {td}><strong style="font-size:15px;">{note_fmt(x["note"])}</strong></td>'
        f'<td {td}>{pc(x["prev"], nat_prev)}</td><td {td}>{pc(x["cur"], nat)}</td>'
        f'<td {td}>{pc(x["tot"], tot_all)}</td>'
        f'<td {td}><a href="{kasse_url(x["id"])}" style="color:var(--accent-dark);font-weight:600;">{ana} &rarr;</a></td></tr>'
        if x["id"] in KASSE_SLUG else
        f'<td {td}>{pc(x["tot"], tot_all)}</td><td></td></tr>' for x in big)

    def cli(c, v):
        return (f'<div><a href="{canton_url(c)}" style="color:var(--text);"><strong>{e(cname(c))}</strong></a> '
                f'<span style="color:var(--muted);font-weight:600;">{pct(v["change_pct"])}</span></div>')

    canton_links = "".join(
        f'<a href="{curl}" style="color:var(--accent-dark);">{e(name)}</a>'
        for c, name, curl in sorted_cantons())

    example = ""
    rows = ((jojo or {}).get(f"{PREV}-{YEAR}") or {}).get("rows") or []
    if rows:
        x = rows[0]
        chg = i18n.dec(x["change"])
        example = L(f"Ein Beispiel aus {e(cname(x['canton']))}: {e(x['insurer'])} war {PREV} die günstigste Kasse. "
                    f"{YEAR} kostet derselbe Tarif <strong>{chg} Prozent mehr</strong>, die Kasse ist nur noch auf Platz {x['rank_after']}.",
                    f"Un exemple {e(im_kanton(x['canton']))} : {e(x['insurer'])} était la caisse la moins chère en {PREV}. "
                    f"En {YEAR}, le même tarif coûte <strong>{chg} % de plus</strong> et la caisse n’est plus qu’au rang {x['rank_after']}.",
                    f"An example from {e(cname(x['canton']))}: {e(x['insurer'])} was the cheapest insurer in {PREV}. "
                    f"In {YEAR} the same tariff costs <strong>{chg}% more</strong>, and the insurer is down to rank {x['rank_after']}.")
    card = 'style="background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:28px;margin-bottom:20px;"'
    col = 'style="font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin-bottom:10px;"'
    y_first = (RATING or {}).get("years", [Y0])[0]
    ac = 'style="color:var(--accent-dark);"'
    rating_name = L("Preistreue-Rating", "notation Constance des primes", "Price Consistency Rating")
    return f"""<!-- INSIGHTS:START (generiert von scripts/build_kk_pages.py) -->
<section class="insights-section" style="padding:80px 40px;background:var(--bg);">
  <div style="max-width:900px;margin:0 auto;">
    <div class="section-label">{L("Datenanalyse", "Analyse des données", "Data analysis")}</div>
    <h2 class="section-headline" style="margin-bottom:8px;">{L("Die Billigste von heute ist oft die Teuerste von morgen", "La moins chère d’aujourd’hui est souvent la plus chère de demain", "Today’s cheapest is often tomorrow’s most expensive")}</h2>
    <p style="color:var(--text2);font-size:17px;line-height:1.6;margin-bottom:10px;">{example}</p>
    <p style="color:var(--muted);margin-bottom:32px;">{L(f'Wer jedes Jahr zur Billigsten wechselt, landet oft genau dort. Unser <a href="{u("rating")}" {ac}>Preistreue-Rating</a> zeigt, welche Kassen seit {y_first} günstig bleiben.',
        f'Qui change chaque année pour la moins chère finit souvent exactement là. Notre <a href="{u("rating")}" {ac}>notation Constance des primes</a> montre quelles caisses restent avantageuses depuis {y_first}.',
        f'Switching to the cheapest every year often lands you right there. Our <a href="{u("rating")}" {ac}>Price Consistency Rating</a> shows which insurers have stayed cheap since {y_first}.')}</p>

    <div {card}>
      <h3 style="font-size:18px;font-weight:700;margin-bottom:6px;">{L(f"Preistreue-Rating {YEAR} und Anstieg pro Kasse", f"Constance des primes {YEAR} et hausse par caisse", f"Price Consistency Rating {YEAR} and increase per insurer")}</h3>
      <div style="font-size:14px;color:var(--muted);margin-bottom:16px;">{L(
        f'Note 0 bis 10: je höher, desto länger bleibt die Kasse günstig. Daneben der Prämienanstieg, <span style="color:var(--red);">rot</span> heisst über dem Schnitt ({pct(nat)} im {YEAR}). <strong style="color:var(--text);">Klick auf eine Kasse für die ganze Analyse.</strong>',
        f'Note de 0 à 10 : plus elle est élevée, plus la caisse reste longtemps avantageuse. À côté, la hausse des primes, en <span style="color:var(--red);">rouge</span> au-dessus de la moyenne ({pct(nat)} en {YEAR}). <strong style="color:var(--text);">Cliquez sur une caisse pour l’analyse complète.</strong>',
        f'Score 0 to 10: the higher, the longer the insurer stays cheap. Next to it the premium increase, <span style="color:var(--red);">red</span> means above average ({pct(nat)} in {YEAR}). <strong style="color:var(--text);">Click an insurer for the full analysis.</strong>')}</div>
      <div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;font-size:14px;">
        <thead><tr style="border-bottom:1px solid var(--border2);"><th style="text-align:left;padding:8px 12px;">{L("Kasse", "Caisse", "Insurer")}</th><th style="text-align:right;padding:8px 12px;">{L("Note", "Note", "Score")}</th><th style="text-align:right;padding:8px 12px;">{PREV}</th><th style="text-align:right;padding:8px 12px;">{YEAR}</th><th style="text-align:right;padding:8px 12px;">{L("Seit", "Depuis", "Since")} {Y0}</th><th></th></tr></thead>
        <tbody>{kas}</tbody>
      </table></div>
      <div style="font-size:12px;color:var(--muted);margin-top:10px;">{L(
        f"Kassen mit mindestens {MIN_BESTAND_RANKING // 1000}'000 Versicherten, sortiert nach Note. In deiner Region kann die Reihenfolge anders sein, siehe Kantone unten.",
        f"Caisses d’au moins {MIN_BESTAND_RANKING // 1000}'000 assurés, triées par note. Dans votre région, l’ordre peut être différent, voir les cantons ci-dessous.",
        f"Insurers with at least {MIN_BESTAND_RANKING // 1000}'000 insured persons, sorted by score. The order may differ in your region, see the cantons below.")} <a href="{u("rating")}" {ac}>{L("So rechnen wir", "Notre méthode", "How we calculate")} &rarr;</a></div>
    </div>

    <div {card}>
      <h3 style="font-size:18px;font-weight:700;margin-bottom:6px;">{L("Nach Kanton", "Par canton", "By canton")}</h3>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:20px;font-size:15px;line-height:2;">
        <div><div {col}>{L("Stärkster Anstieg", "Plus forte hausse", "Largest increase")}</div>{"".join(cli(c, v) for c, v in by_change[:3])}</div>
        <div><div {col}>{L("Schwächster Anstieg", "Plus faible hausse", "Smallest increase")}</div>{"".join(cli(c, v) for c, v in by_change[-3:][::-1])}</div>
      </div>
      <div style="margin-top:18px;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);">{L("Dauerhaft günstig in deinem Kanton", "Durablement avantageuses dans votre canton", "Consistently cheap in your canton")}</div>
      <div style="display:flex;flex-wrap:wrap;gap:6px 14px;margin-top:8px;font-size:14px;">{canton_links}</div>
    </div>


    <div style="font-size:12px;color:var(--muted);text-align:center;">{L("Quelle: BAG · Erwachsene, Franchise 300, mit Unfall", "Source : OFSP · adultes, franchise 300, avec accidents", "Source: FOPH · adults, deductible 300, with accident cover")} · <a href="{u("report")}" {ac}>{L(f"Ganze Auswertung {YEAR}", f"Analyse complète {YEAR}", f"Full analysis {YEAR}")}</a> · <a href="{u("rating")}" {ac}>{rating_name[0].upper() + rating_name[1:]}</a> · <a href="{u("kassen")}" {ac}>{L("Alle Kassen", "Toutes les caisses", "All insurers")}</a> · <a href="{u("kuendigen")}" {ac}>{L(f"Kündigen bis {deadline()}", f"Résilier d’ici au {deadline()}", f"Cancel by {deadline()}")}</a></div>
  </div>
</section>
<!-- INSIGHTS:END -->"""


# ── Preistreue-Rating ──────────────────────────────────────────────────────

RATING = None   # wird in main() aus build_rating.compute() gefüllt
MAIN_REGION = {}  # Kanton -> Hauptregion, in main() gefüllt
AWARDS = []       # Preistreue-Award, in main() aus build_awards.compute() gefüllt
AWARD_PATH = "/krankenkassen-rating/award/"
RATING_PATH = "/krankenkassen-rating/"

# Teilnoten und Varianten des Ratings in drei Sprachen (build_rating kennt nur Deutsch)
PART_LABEL = {
    "preis": ("Preis heute", "Prix actuel", "Price today"),
    "konstanz": ("Konstanz", "Constance", "Consistency"),
    "treue": ("Treue", "Fidélité", "Loyalty"),
    "rabatt": ("Rabatt-Treue", "Rabais durable", "Discount retention"),
    "tarife": ("Tarif-Bestand", "Pérennité des tarifs", "Tariff continuity"),
    "solvenz": ("Finanzpolster", "Réserves", "Reserves"),
}


def part_label(k):
    return L(*PART_LABEL[k])


def variant_label(key):
    """'ohne-2500' -> 'Ohne Unfall, Franchise 2'500' in der aktuellen Sprache."""
    acc, fr = key.split("-")
    fr_t = "2'500" if fr == "2500" else fr
    if acc == "mit":
        return L(f"Mit Unfall, Franchise {fr_t}", f"Avec accidents, franchise {fr_t}", f"With accident cover, deductible {fr_t}")
    return L(f"Ohne Unfall, Franchise {fr_t}", f"Sans accidents, franchise {fr_t}", f"Without accident cover, deductible {fr_t}")


def rating_name(cap=True):
    n = L("Preistreue-Rating", "notation Constance des primes", "Price Consistency Rating")
    return n[0].upper() + n[1:] if cap else n


def award_name():
    return L("Preistreue-Award", "Prix Constance des primes", "Price Consistency Award")


# Aufschlüsselung der Verwaltungskosten (scripts/extract_verwaltung.py)
_VD = DATA / "verwaltung_detail.json"
VDET = json.loads(_VD.read_text(encoding="utf-8"))["kassen"] if _VD.exists() else {}


def vdet(i):
    """Letztes Jahr der BAG-Aufschlüsselung einer Kasse: (Jahr, Werte) oder (None, None)."""
    d = VDET.get(str(i)) or {}
    y = max(d, default=None)
    return (y, d[y]) if y else (None, None)


def gruppe_hinweis():
    return L("ohne eigenes Personal: die Verwaltung wird als Gebühr bei einer Konzern- oder Partnerfirma "
             "eingekauft, wie sie sich auf die Konzernkassen verteilt, bestimmt der Konzern",
             "sans personnel propre : l’administration est achetée sous forme de frais à une société du groupe ou partenaire, "
             "et c’est le groupe qui décide comment elle se répartit entre ses caisses",
             "no staff of its own: administration is bought in as a fee from a group or partner company, "
             "and the group decides how it is split among its insurers")


def note_fmt(v):
    return i18n.dec(v) if v is not None else "–"


def bar(v):
    w = 0 if v is None else max(2, v * 10)
    return f'<span class="kk-bar"><span style="width:{w:.0f}%"></span></span>'


HOME = {}   # Regionalkasse -> Stammgebiet: {"canton", "region", "note", "anteil"}


def set_home(bestand):
    """Stammgebiet einer Regionalkasse: der Kanton mit den meisten Versicherten.
    Dort zählt ihre Note, nicht der Schnitt über Regionen, in denen sie kaum
    Kunden hat."""
    per = defaultdict(dict)
    for (i, c), v in bestand.items():
        per[i][c] = per[i].get(c, 0) + v
    for i, n in RATING["national"].items():
        if not n["regional"] or not per.get(i):
            continue
        c = max(per[i], key=per[i].get)
        regs = {k.split("|")[1]: m[i]["note"] for k, m in RATING["regions"].items()
                if k.startswith(c + "|") and i in m and m[i]["note"] is not None}
        if not regs:
            continue
        reg = MAIN_REGION.get(c) if MAIN_REGION.get(c) in regs else max(regs, key=regs.get)
        HOME[i] = {"canton": c, "region": reg, "note": regs[reg], "anteil": per[i][c] / sum(per[i].values())}


def canton_award(c):
    return next((a for a in AWARDS if a["group"] == "Kantone" and a["id"].startswith(f"kanton-{CANTONS[c][1]}-")), None)


JOJO_ROWS = []   # Vorjahressieger je Region, in main() vor den Kantonsseiten gefüllt


def vorjahr_block(c):
    """Der günstigste Tarif des Vorjahres in jeder Region des Kantons und was
    er heute kostet. Gleiche Rechnung wie in der Auswertung und im Pressetext:
    Erwachsene, Franchise 2'500, ohne Unfall."""
    rows = sorted((x for x in JOJO_ROWS if x["canton"] == c), key=lambda x: x["region"])
    if not rows:
        return ""
    def lab(x):
        return L("ganzer Kanton", "tout le canton", "whole canton") if x["region"].endswith("0") else f"{L('Region', 'Région', 'Region')} {x['region'][-1]}"
    of = L("von", "sur", "of")
    trs = "".join(
        f'<tr><td>{lab(x)}</td><td>{e(x["insurer"])}<span class="sub">{e(MODEL_LABEL.get(x["model"], x["model"]))} · {e(x["tariff"])}</span></td>'
        f'<td class="num">CHF {chf(x["before"])}</td><td class="num">CHF {chf(x["after"])}</td>'
        f'<td class="num {"kk-up" if x["change"] > x["market"] else "kk-down"}">{pct(x["change"])}<span class="sub">{L("Markt", "Marché", "Market")} {pct(x["market"])}</span></td>'
        f'<td class="num">{x["rank_after"]}{L(".", "er" if x["rank_after"] == 1 else "e", "")} {of} {x["n_after"]}</td></tr>' for x in rows)
    still = sum(1 for x in rows if x["rank_after"] == 1)
    if still == len(rows):
        lead = L(f"Der günstigste Tarif vom letzten Jahr ist auch {YEAR} noch der günstigste.",
                 f"Le tarif le moins cher de l’an dernier l’est encore en {YEAR}.",
                 f"Last year’s cheapest tariff is still the cheapest in {YEAR}.")
    else:
        lead = L("Wer letztes Jahr zur günstigsten Kasse gewechselt hat, sollte dieses Jahr wieder vergleichen.",
                 "Si vous avez choisi la caisse la moins chère l’an dernier, comparez à nouveau cette année.",
                 "If you switched to the cheapest insurer last year, compare again this year.")
    multi = len(rows) > 1
    return (L("<h2>Letztes Jahr die Günstigste, und heute?</h2>", "<h2>La moins chère l’an dernier, et aujourd’hui ?</h2>",
              "<h2>Cheapest last year, and now?</h2>")
            + L(f"<p>Der günstigste Tarif {PREV} in {'jeder Prämienregion' if multi else 'der Prämienregion'} des Kantons und was derselbe Tarif {YEAR} kostet. "
                f"Erwachsene, Franchise 2'500, ohne Unfall, pro Monat. {lead}</p>",
                f"<p>Le tarif le moins cher de {PREV} dans {'chaque région de primes' if multi else 'la région de primes'} du canton, et ce que coûte le même tarif en {YEAR}. "
                f"Adultes, franchise 2'500, sans accidents, par mois. {lead}</p>",
                f"<p>The cheapest tariff of {PREV} in {'each premium region' if multi else 'the premium region'} of the canton and what the same tariff costs in {YEAR}. "
                f"Adults, deductible 2'500, without accident cover, per month. {lead}</p>")
            + f'<div class="kk-table-wrap"><table class="kk-table"><thead><tr><th>Region</th><th>{L("Sieger", "La moins chère", "Cheapest")} {PREV}</th><th class="num">{PREV}</th>'
            f'<th class="num">{YEAR}</th><th class="num">{L("Veränderung", "Évolution", "Change")}</th><th class="num">{L("Rang", "Rang", "Rank")} {YEAR}</th></tr></thead><tbody>{trs}</tbody></table></div>')


def award_url(aid, lang=None):
    return f"{i18n.url('award', lang)}#{aid}"


def rating_canton_block(c, main):
    """Die 5 Kassen mit der besten Note in der Hauptregion des Kantons."""
    if not RATING:
        return ""
    reg = RATING["regions"].get(f"{c}|{main}", {})
    best = sorted(((i, v) for i, v in reg.items() if v["note"] is not None), key=lambda x: -x[1]["note"])[:5]
    if not best:
        return ""
    of = L("von", "sur", "of")
    rows = "".join(
        f'<tr><td>{kasse_link(i)}{"<span class=sub>" + L("Regionalkasse", "Caisse régionale", "Regional insurer") + "</span>" if RATING["national"].get(i, {}).get("regional") else ""}</td>'
        f'<td class="num"><strong>{note_fmt(v["note"])}</strong></td>'
        f'<td class="num">{v["top5"][-1][0]} {of} {v["top5"][-1][1]}</td></tr>' for i, v in best)
    aw = canton_award(c)
    if aw:
        loc = award_loc(aw)
        award = (f'<div class="kk-canton-award"><a href="{award_url(aw["id"])}"><img src="{award_badge_url(aw["id"], "-quer")}" '
                 f'alt="{e(loc["alt"])}" width="248" height="72" loading="lazy"></a><p>'
                 + L(f'<strong>{e(aw["name"])}</strong> ist die preistreueste Krankenkasse im Kanton {e(cname(c))} {YEAR}.',
                     f'<strong>{e(aw["name"])}</strong> est la caisse-maladie aux primes les plus constantes {e(im_kanton(c))} en {YEAR}.',
                     f'<strong>{e(aw["name"])}</strong> is the most price-consistent health insurer {e(im_kanton(c))} in {YEAR}.')
                 + '</p></div>')
    else:
        award = ""
    y0 = RATING['years'][0]
    rl = f'<a href="{i18n.url("rating")}">{rating_name(cap=i18n.LANG != "fr")}</a>'
    return (L(f"<h2>Dauerhaft günstig im Kanton {e(cname(c))}</h2>", f"<h2>Durablement avantageuses {e(im_kanton(c))}</h2>",
              f"<h2>Consistently cheap {e(im_kanton(c))}</h2>")
            + L(f"<p>Nicht nur dieses Jahr günstig, sondern über die Jahre: die fünf Kassen mit der besten Note im "
                f"{rl}, gerechnet für die Hauptregion des Kantons. "
                f"Die letzte Spalte zeigt, in wie vielen Jahren seit {y0} die Kasse hier unter den 5 günstigsten war (Franchise 2'500).</p>",
                f"<p>Pas seulement cette année, mais sur la durée : les cinq caisses les mieux notées dans la "
                f"{rl}, calculée pour la région principale du canton. "
                f"La dernière colonne indique pendant combien d’années depuis {y0} la caisse a figuré ici parmi les 5 moins chères (franchise 2'500).</p>",
                f"<p>Not just cheap this year, but over the years: the five insurers with the best score in the "
                f"{rl}, calculated for the canton’s main region. "
                f"The last column shows in how many years since {y0} the insurer was among the 5 cheapest here (deductible 2'500).</p>")
            + f'<div class="kk-table-wrap"><table class="kk-table"><thead><tr><th>{L("Kasse", "Caisse", "Insurer")}</th><th class="num">{L("Note", "Note", "Score")}</th>'
            f'<th class="num">{L("Jahre unter den 5 günstigsten", "Années parmi les 5 moins chères", "Years among the 5 cheapest")}</th></tr></thead><tbody>{rows}</tbody></table></div>{award}')


def rating_kasse_card(i):
    if not RATING or i not in RATING["national"]:
        return ""
    n = RATING["national"][i]
    parts = dict(n["parts"])
    home = HOME.get(i)
    if home:   # Regionalkasse: Preis und Konstanz aus dem Stammgebiet
        hr = RATING["regions"][f"{home['canton']}|{home['region']}"][i]
        parts.update({k: hr.get(k) if hr.get(k) is not None else parts[k] for k in ("preis", "konstanz")})
    rows = "".join(f'<div class="kk-rrow"><span>{e(part_label(k))}</span>{bar(parts[k])}'
                   f'<span class="num">{note_fmt(parts[k])}</span></div>' for k in RATING["weights"])
    adm = RATING["verwaltung"]["kassen"].get(str(i), {})
    mk = RATING["verwaltung"]["markt_verwaltung"]
    last = max(adm, default=None)
    first = min(adm, default=None)
    adm_html = ""
    if last:
        v, m = adm[last]["verwaltung"], mk[last]
        vy, vd = vdet(i)
        if vd:
            det = L(f' {vy}: Werbung CHF {vd["werbung"]:.0f}, Provisionen an Vermittler CHF {vd["provisionen"]:.0f}.',
                    f' {vy} : publicité CHF {vd["werbung"]:.0f}, commissions aux intermédiaires CHF {vd["provisionen"]:.0f}.',
                    f' {vy}: advertising CHF {vd["werbung"]:.0f}, broker commissions CHF {vd["provisionen"]:.0f}.')
            if vd["ohne_personal"]:
                det += L(' Die Kasse hat kein eigenes Personal und kauft ihre Verwaltung als Gebühr bei einer Konzern- oder Partnerfirma ein.',
                         ' La caisse n’a pas de personnel propre et achète son administration sous forme de frais à une société du groupe ou partenaire.',
                         ' The insurer has no staff of its own and buys in its administration as a fee from a group or partner company.')
        else:
            det = ""
        since = (f', {first}: CHF {adm[first]["verwaltung"]:.0f}' if first != last else "")
        adm_html = L(f'<p class="kk-rnote">Verwaltungskosten {last}: <strong>CHF {v:.0f}</strong> pro versicherte Person '
                     f'(Schnitt aller Kassen CHF {m:.0f}){since}.{det} Quelle: BAG. <a href="{i18n.url(BLOG_VERWALTUNG_KEY)}">Alle Kassen im Vergleich</a></p>',
                     f'<p class="kk-rnote">Frais administratifs {last} : <strong>CHF {v:.0f}</strong> par assuré '
                     f'(moyenne de toutes les caisses CHF {m:.0f}){since}.{det} Source : OFSP. <a href="{i18n.url(BLOG_VERWALTUNG_KEY)}">Toutes les caisses comparées</a></p>',
                     f'<p class="kk-rnote">Administrative costs {last}: <strong>CHF {v:.0f}</strong> per insured person '
                     f'(average of all insurers CHF {m:.0f}){since}.{det} Source: FOPH. <a href="{i18n.url(BLOG_VERWALTUNG_KEY)}">All insurers compared</a></p>')
    hint = ""
    big_note, label = n["note"], f"{rating_name()} {YEAR}"
    if home:
        hc = home['canton']
        big_note = home["note"]
        label = f"{rating_name()} {YEAR} · {L('Kanton', 'Canton', 'Canton')} {e(cname(hc))}"
        hint = L(f" Regionalkasse: die Note gilt im Kanton {e(cname(hc))}, wo sie die meisten Versicherten hat. "
                 f"Über alle {n['regionen']} Regionen gerechnet, auch wo sie kaum Kunden hat: {note_fmt(n['note'])}.",
                 f" Caisse régionale : la note vaut {e(im_kanton(hc))}, où elle compte le plus d’assurés. "
                 f"Calculée sur les {n['regionen']} régions, y compris là où elle n’a presque pas de clients : {note_fmt(n['note'])}.",
                 f" Regional insurer: the score applies {e(im_kanton(hc))}, where it has the most insured persons. "
                 f"Calculated across all {n['regionen']} regions, including where it has hardly any customers: {note_fmt(n['note'])}.")
    elif n["regional"]:
        hint = L(" Regionalkasse: die Note stützt sich auf wenige Regionen.", " Caisse régionale : la note repose sur peu de régions.",
                 " Regional insurer: the score is based on few regions.")
    vn = n.get("varianten") or {}
    var_html = ('<div class="kk-rvar">' + " · ".join(
        f'{e(variant_label(v["key"]))} <strong>{note_fmt(vn.get(v["key"]))}</strong>' for v in RATING.get("varianten", [])) + "</div>") if vn else ""
    y0 = RATING["years"][0]
    sub = L(f'Ist {e(n["name"])} dauerhaft günstig? Aus den BAG-Prämien seit {y0}.',
            f'{e(n["name"])} est-elle durablement avantageuse ? D’après les primes de l’OFSP depuis {y0}.',
            f'Is {e(n["name"])} consistently cheap? Based on FOPH premiums since {y0}.')
    return (f'<div class="kk-rating"><div class="kk-rating-head"><div><div class="kk-rating-label">{label}</div>'
            f'<div class="kk-rating-sub">{sub}{hint}</div></div>'
            f'<div class="kk-rating-note">{note_fmt(big_note)}<span>/10</span></div></div>{"" if home else var_html}{rows}{adm_html}'
            f'{award_strip(i)}<a href="{i18n.url("rating")}">{L("So rechnen wir", "Notre méthode", "How we calculate")} &rarr;</a></div>')


def rating_page(r):
    path = i18n.url("rating")
    nat = r["national"]
    big = sorted((i for i in nat if not nat[i]["regional"] and nat[i]["note"] is not None), key=lambda i: -nat[i]["note"])
    small = sorted((i for i in nat if nat[i]["regional"] and nat[i]["note"] is not None), key=lambda i: -nat[i]["note"])
    keys = list(r["weights"])
    y0 = r["years"][0]
    insurer = L("Kasse", "Caisse", "Insurer")
    note_h = L("Note", "Note", "Score")

    def table(ids, rank=True):
        short = {"preis": ("Preis", "Prix", "Price"), "konstanz": ("Konstanz", "Constance", "Consistency"),
                 "treue": ("Treue", "Fidélité", "Loyalty"), "rabatt": ("Rabatt", "Rabais", "Discount"),
                 "tarife": ("Tarife", "Tarifs", "Tariffs"), "solvenz": ("Reserven", "Réserves", "Reserves")}
        head = "".join(f'<th class="num" title="{e(part_label(k))}">{L(*short[k])}</th>' for k in keys)
        body = "".join(
            f'<tr>{"<td>" + str(n + 1) + "</td>" if rank else ""}<td>{kasse_link(i)}</td>'
            f'<td class="num"><strong>{note_fmt(nat[i]["note"])}</strong></td>'
            + "".join(f'<td class="num">{note_fmt(nat[i]["parts"][k])}</td>' for k in keys) + "</tr>"
            for n, i in enumerate(ids))
        return (f'<div class="kk-table-wrap"><table class="kk-table kk-rtable"><thead><tr>{"<th>#</th>" if rank else ""}<th>{insurer}</th>'
                f'<th class="num">{note_h}</th>{head}</tr></thead><tbody>{body}</tbody></table></div>')

    small_h = sorted(small, key=lambda i: -(HOME[i]["note"] if i in HOME else nat[i]["note"] or 0))
    reg_table = (f'<div class="kk-table-wrap"><table class="kk-table"><thead><tr><th>{insurer}</th><th>{L("Stammgebiet", "Région d’origine", "Home region")}</th>'
                 f'<th class="num">{L("Note dort", "Note sur place", "Score there")}</th><th class="num">{L("Alle Regionen", "Toutes les régions", "All regions")}</th></tr></thead><tbody>'
                 + "".join(f'<tr><td>{kasse_link(i)}</td><td>{e(cname(HOME[i]["canton"])) if i in HOME else "–"}</td>'
                           f'<td class="num"><strong>{note_fmt(HOME[i]["note"] if i in HOME else None)}</strong></td>'
                           f'<td class="num">{note_fmt(nat[i]["note"])}</td></tr>' for i in small_h)
                 + "</tbody></table></div>")
    top = [nat[i] for i in big[:3]]
    koh = r["kohorten"][0] if r["kohorten"] else None
    alte = r["alte_modelle"]
    # Verwaltungskosten: grössere Kassen, erstes und letztes Jahr
    adm, mk = r["verwaltung"]["kassen"], r["verwaltung"]["markt_verwaltung"]
    ay = sorted(mk)
    a0, a1 = ay[0], ay[-1]
    adm_rows = []
    for i in big:
        d = adm.get(str(i), {})
        if a1 in d and a0 in d:
            adm_rows.append((d[a1]["verwaltung"], i, d[a0]["verwaltung"]))
    adm_rows.sort()
    def adm_extra(i):
        y, d = vdet(i)
        if not d:
            return '<td class="num">–</td><td class="num">–</td>'
        return f'<td class="num">CHF {d["werbung"]:.0f}</td><td class="num">CHF {d["provisionen"]:.0f}</td>'
    vjahr = max((y for y, _ in (vdet(i) for i in big) if y), default="")
    adm_html = "".join(
        f'<tr><td>{kasse_link(i)}{"&nbsp;¹" if (vdet(i)[1] or {}).get("ohne_personal") else ""}</td><td class="num">CHF {v0:.0f}</td><td class="num"><strong>CHF {v1:.0f}</strong></td>'
        f'<td class="num">{pct((v1 / v0 - 1) * 100, sign=True)}</td>{adm_extra(i)}</tr>' for v1, i, v0 in adm_rows)
    cantons = "".join(f'<a href="{curl}">{e(nm)}</a>' for c, nm, curl in sorted_cantons())
    pc = lambda x: i18n.dec(x) if i18n.LANG != "de" else str(x).replace(".", ",")

    method = [
        ("preis", L("Position des günstigsten Tarifs der Kasse unter allen Kassen der Prämienregion, "
                    f"{YEAR}. Unter den günstigsten 20 % = 10 Punkte, ab 80 % = 0.",
                    f"Position du tarif le moins cher de la caisse parmi toutes les caisses de la région de primes, {YEAR}. "
                    "Parmi les 20 % les moins chères = 10 points, dès 80 % = 0.",
                    f"Position of the insurer’s cheapest tariff among all insurers in the premium region, {YEAR}. "
                    "Among the cheapest 20% = 10 points, from 80% = 0.")),
        ("konstanz", L(f"In wie vielen Jahren seit {y0} war die Kasse in der Region unter den 5 günstigsten? "
                       "Ab 30 % der Jahre = 10 Punkte.",
                       f"Pendant combien d’années depuis {y0} la caisse a-t-elle figuré parmi les 5 moins chères de la région ? "
                       "Dès 30 % des années = 10 points.",
                       f"In how many years since {y0} was the insurer among the 5 cheapest in the region? "
                       "From 30% of years = 10 points.")),
        ("treue", L("Wie stark stieg der günstigste Tarif der Kasse, wenn man in ihm blieb, verglichen mit dem Median "
                    "aller Tarife der Region? Mittel über alle Jahre. 0,3 Punkte pro Jahr unter dem Markt = 10, 1,5 Punkte darüber = 0.",
                    "De combien le tarif le moins cher de la caisse a-t-il augmenté pour qui y est resté, comparé à la médiane "
                    "de tous les tarifs de la région ? Moyenne sur toutes les années. 0,3 point par an sous le marché = 10, 1,5 point au-dessus = 0.",
                    "How much did the insurer’s cheapest tariff rise for those who stayed in it, compared with the median "
                    "of all tariffs in the region? Average over all years. 0.3 points a year below market = 10, 1.5 points above = 0.")),
        ("rabatt", L("Behalten neue Modelle ihren Rabatt gegenüber dem Standardmodell derselben Kasse? "
                     "Gemessen an denselben Tarifen vom Startjahr bis heute. Kein Verlust = 10, 2 Punkte Verlust pro Jahr = 0. "
                     "Kassen ohne neue Modelle seit 2021 werden hier nicht bewertet.",
                     "Les nouveaux modèles conservent-ils leur rabais par rapport au modèle standard de la même caisse ? "
                     "Mesuré sur les mêmes tarifs de l’année de lancement à aujourd’hui. Aucune perte = 10, 2 points de perte par an = 0. "
                     "Les caisses sans nouveau modèle depuis 2021 ne sont pas notées ici.",
                     "Do new models keep their discount compared with the same insurer’s standard model? "
                     "Measured on the same tariffs from launch year to today. No loss = 10, 2 points lost per year = 0. "
                     "Insurers without new models since 2021 are not scored here.")),
        ("tarife", L("Anteil der Tarife, die im Folgejahr unter gleichem Tarifcode weiterlaufen. "
                     "100 % = 10 Punkte, 80 % = 0. Wer Tarife streicht oder umbenennt, zwingt Versicherte zum Wechseln.",
                     "Part des tarifs qui continuent l’année suivante sous le même code. "
                     "100 % = 10 points, 80 % = 0. Supprimer ou renommer des tarifs oblige les assurés à changer.",
                     "Share of tariffs that continue the following year under the same tariff code. "
                     "100% = 10 points, 80% = 0. Dropping or renaming tariffs forces customers to switch.")),
        ("solvenz", L("Solvenzquote laut BAG per 1. Januar 2026: vorhandene Reserven im Verhältnis zur "
                      "gesetzlichen Mindesthöhe. 200 % = 10 Punkte, 100 % = 0. Knappe Reserven gehen oft höheren Aufschlägen voraus.",
                      "Taux de solvabilité selon l’OFSP au 1er janvier 2026 : réserves disponibles par rapport au minimum "
                      "légal. 200 % = 10 points, 100 % = 0. Des réserves serrées précèdent souvent de plus fortes hausses.",
                      "Solvency ratio according to the FOPH as of 1 January 2026: available reserves relative to the legal "
                      "minimum. 200% = 10 points, 100% = 0. Thin reserves often come before larger increases.")),
    ]
    meth_rows = "".join(f'<tr><td><strong>{e(part_label(k))}</strong></td><td class="num">{int(r["weights"][k] * 100)}{"%" if i18n.LANG == "en" else " %"}</td><td>{e(d)}</td></tr>'
                        for k, d in method)
    rn = rating_name()
    qa = [
        (L("Welche Krankenkasse ist dauerhaft günstig?", "Quelle caisse-maladie est durablement avantageuse ?", "Which health insurer is consistently cheap?"),
         L(f"Laut unserem Preistreue-Rating {YEAR} schneiden {top[0]['name']}, {top[1]['name']} und {top[2]['name']} am besten ab. "
           "Sie sind heute günstig und waren es auch in den Jahren davor. Welche Kasse in deiner Region vorne liegt, zeigt die Seite deines Kantons.",
           f"Selon notre notation Constance des primes {YEAR}, {top[0]['name']}, {top[1]['name']} et {top[2]['name']} obtiennent les meilleurs résultats. "
           "Elles sont avantageuses aujourd’hui et l’étaient aussi les années précédentes. La page de votre canton montre quelle caisse est en tête dans votre région.",
           f"According to our Price Consistency Rating {YEAR}, {top[0]['name']}, {top[1]['name']} and {top[2]['name']} come out best. "
           "They are cheap today and were in previous years too. Your canton’s page shows which insurer leads in your region.")),
        (L("Warum ist die günstigste Kasse von heute oft nicht die beste Wahl?", "Pourquoi la caisse la moins chère aujourd’hui n’est-elle souvent pas le meilleur choix ?",
           "Why is today’s cheapest insurer often not the best choice?"),
         L("Manche Kassen sind ein Jahr günstig und schlagen danach überdurchschnittlich auf. Neue Sparmodelle starten mit viel Rabatt "
           "und verlieren ihn in den Folgejahren. Wer nicht jedes Jahr wechseln will, fährt mit einer konstant günstigen Kasse besser.",
           "Certaines caisses sont avantageuses une année puis augmentent plus que la moyenne. Les nouveaux modèles alternatifs démarrent avec un gros rabais "
           "et le perdent les années suivantes. Si vous ne voulez pas changer chaque année, une caisse constamment avantageuse est le meilleur choix.",
           "Some insurers are cheap for one year and then raise prices more than average. New savings models start with a big discount "
           "and lose it in the following years. If you don’t want to switch every year, a consistently cheap insurer serves you better.")),
        (L("Fliessen Kundenbewertungen ins Rating ein?", "Les avis de clients entrent-ils dans la notation ?", "Do customer reviews count in the rating?"),
         L("Nein. Das Rating stützt sich nur auf harte Zahlen des Bundesamts für Gesundheit: Prämien seit "
           f"{y0}, Solvenzquoten und Aufsichtsdaten. Jede Zahl lässt sich nachrechnen.",
           "Non. La notation repose uniquement sur des chiffres de l’Office fédéral de la santé publique : primes depuis "
           f"{y0}, taux de solvabilité et données de surveillance. Chaque chiffre peut être vérifié.",
           "No. The rating relies only on hard figures from the Federal Office of Public Health: premiums since "
           f"{y0}, solvency ratios and supervisory data. Every number can be recalculated.")),
        (L("Bezahlen Kassen für eine gute Note?", "Les caisses paient-elles pour une bonne note ?", "Do insurers pay for a good score?"),
         L("Nein. abovergleich.com nimmt keine Provisionen von Krankenkassen. Die Note entsteht aus einer festen Formel, die hier offengelegt ist.",
           "Non. abovergleich.com ne perçoit aucune commission des caisses-maladie. La note résulte d’une formule fixe, publiée ici.",
           "No. abovergleich.com takes no commissions from health insurers. The score comes from a fixed formula, published here.")),
    ]
    vkeys = [v["key"] for v in r["varianten"]]
    vhead = "".join(f'<th class="num">{e(variant_label(v["key"]).replace("Franchise ", "F ").replace("franchise ", "F ").replace("deductible ", "D "))}</th>' for v in r["varianten"])
    var_table = (f'<div class="kk-table-wrap"><table class="kk-table kk-rtable"><thead><tr><th>{insurer}</th><th class="num">{L("Gesamt", "Total", "Overall")}</th>{vhead}</tr></thead><tbody>'
                 + "".join(f'<tr><td>{kasse_link(i)}</td><td class="num"><strong>{note_fmt(nat[i]["note"])}</strong></td>'
                           + "".join(f'<td class="num">{note_fmt(nat[i]["varianten"].get(k))}</td>' for k in vkeys) + "</tr>" for i in big)
                 + "</tbody></table></div>")
    wtxt = ", ".join(f'{variant_label(v["key"])} {round(v["gewicht"] * 100)}{"%" if i18n.LANG == "en" else " %"}' for v in r["varianten"])
    gw = [a for a in AWARDS if a["group"] == "Gesamtwertung"]
    award_row = "".join(f'<a href="{award_url(a["id"])}"><img src="{award_badge_url(a["id"], "-quer")}" alt="{e(award_loc(a)["alt"])}" width="248" height="72" loading="lazy"></a>' for a in gw)
    blog_v = i18n.url(BLOG_VERWALTUNG_KEY)
    blog_a = f'<a href="{blog_v}">'
    calc = f'{i18n.url("home")}#kk-rechner'
    P = "%" if i18n.LANG == "en" else " %"
    kohtxt = ""
    if koh:
        kj = koh["jahr"]
        kohtxt = (f'<div class="kk-fact"><div class="kk-fact-val">{pc(koh["start"])}{P} &rarr; {pc(koh["heute"])}{P}</div>'
                  f'<div class="kk-fact-label">' + L(f"Rabatt der {kj} eingeführten Sparmodelle gegenüber Standard, damals und heute",
                                                     f"rabais des modèles alternatifs lancés en {kj} par rapport au standard, alors et aujourd’hui",
                                                     f"discount of the savings models launched in {kj} versus standard, then and now") + '</div></div>')
    koh_rows = "".join(f'<tr><td>{k["jahr"]}</td><td class="num">{pc(k["start"])}{P}</td><td class="num">{pc(k["heute"])}{P}</td><td class="num">{k["tarife"]}</td></tr>' for k in r["kohorten"])
    T = lambda de, fr, en: L(de, fr, en)
    body = f"""{crumbs_html([home_crumb(), ("Rating" if i18n.LANG != "fr" else "Constance des primes", path)])}
<div class="article-badge">{rn} {YEAR}</div>
<h1>{T(f"Krankenkassen-Rating {YEAR}: Welche Kasse ist dauerhaft günstig?", f"Constance des primes {YEAR} : quelle caisse-maladie reste avantageuse ?", f"Health insurance rating {YEAR}: which insurer stays cheap?")}</h1>
<div class="article-meta">{T(f"Aus den BAG-Prämien {y0} bis {YEAR} · nur harte Zahlen, keine Bewertungen", f"D’après les primes de l’OFSP de {y0} à {YEAR} · uniquement des chiffres, aucun avis", f"From FOPH premiums {y0} to {YEAR} · hard numbers only, no reviews")}</div>
<p class="kk-lead">{T("Die günstigste Kasse von heute ist nicht automatisch eine gute Wahl. Manche sind ein Jahr günstig und schlagen danach kräftig auf, andere streichen Tarife und zwingen dich zum Wechseln. Unser Rating zeigt, welche Kassen <strong>über die Jahre</strong> günstig bleiben.",
  "La caisse la moins chère aujourd’hui n’est pas forcément un bon choix. Certaines sont avantageuses une année puis augmentent fortement, d’autres suppriment des tarifs et vous obligent à changer. Notre notation montre quelles caisses restent avantageuses <strong>au fil des ans</strong>.",
  "Today’s cheapest insurer is not automatically a good choice. Some are cheap for a year and then raise prices sharply, others drop tariffs and force you to switch. Our rating shows which insurers stay cheap <strong>over the years</strong>.")}</p>
<div class="kk-facts">
  <div class="kk-fact"><div class="kk-fact-val">{e(top[0]['name'])}</div><div class="kk-fact-label">{T(f"beste Note {YEAR}: {note_fmt(top[0]['note'])} von 10", f"meilleure note {YEAR} : {note_fmt(top[0]['note'])} sur 10", f"best score {YEAR}: {note_fmt(top[0]['note'])} out of 10")}</div></div>
  <div class="kk-fact"><div class="kk-fact-val">{len(r['years'])} {T("Jahre", "ans", "years")}</div><div class="kk-fact-label">{T(f"Prämiendaten des BAG, {y0} bis {YEAR}, in jeder Prämienregion", f"données de primes de l’OFSP, {y0} à {YEAR}, dans chaque région de primes", f"FOPH premium data, {y0} to {YEAR}, in every premium region")}</div></div>
  {kohtxt}
</div>
<a class="kk-cta" href="{calc}">{T("Die Note deiner Kasse im Rechner sehen", "Voir la note de votre caisse dans le calculateur", "See your insurer’s score in the calculator")} &rarr;</a>

<h2>{T(f"Das Rating {YEAR}", f"La notation {YEAR}", f"The rating {YEAR}")}</h2>
<p>{T("Note von 0 bis 10, gewichtet aus sechs Teilnoten. Kassen mit mindestens 50'000 Versicherten, über alle Prämienregionen gerechnet. In deiner Region kann die Reihenfolge anders aussehen, siehe unten.",
  "Note de 0 à 10, pondérée à partir de six notes partielles. Caisses d’au moins 50'000 assurés, calculée sur toutes les régions de primes. Dans votre région, l’ordre peut être différent, voir plus bas.",
  "Score from 0 to 10, weighted from six component scores. Insurers with at least 50'000 insured persons, calculated across all premium regions. The order may look different in your region, see below.")}</p>
{table(big)}

<h2>{T("Je nach Situation: mit oder ohne Unfall, Franchise 300 oder 2'500", "Selon votre situation : avec ou sans accidents, franchise 300 ou 2'500", "Depending on your situation: with or without accident cover, deductible 300 or 2'500")}</h2>
<p>{T("Die Kassen rechnen den Unfallzuschlag und die Franchisen unterschiedlich. Deshalb gibt es vier Einzelnoten. Die Gesamtnote oben gewichtet sie danach, wie viele Erwachsene welche Variante haben (BAG: rund 56 % ohne Unfalldeckung über die Kasse; Franchise 300 etwas häufiger als 2'500). Im Rechner siehst du die Note für deine Situation.",
  "Les caisses calculent différemment le supplément accidents et les franchises. Il y a donc quatre notes distinctes. La note globale ci-dessus les pondère selon le nombre d’adultes dans chaque cas (OFSP : environ 56 % sans couverture accidents auprès de la caisse ; franchise 300 un peu plus fréquente que 2'500). Le calculateur affiche la note correspondant à votre situation.",
  "Insurers price accident cover and deductibles differently. That is why there are four separate scores. The overall score above weights them by how many adults have each option (FOPH: around 56% without accident cover through the insurer; deductible 300 slightly more common than 2'500). The calculator shows the score for your situation.")}</p>
{var_table}

<h2>{award_name()} {YEAR}</h2>
<p>{T("Aus dem Rating vergeben wir jedes Jahr Auszeichnungen: Gesamtwertung, Kategorien wie «Dauerhaft günstig» oder «Solideste Reserven», und die preistreueste Kasse in jedem Kanton. Kassen können das Badge frei verwenden.",
  "Chaque année, nous décernons des distinctions issues de la notation : classement général, catégories comme « Durablement avantageuse » ou « Réserves les plus solides », et la caisse aux primes les plus constantes dans chaque canton. Les caisses peuvent utiliser le badge librement.",
  "Every year we give awards based on the rating: an overall ranking, categories such as “Consistently cheap” or “Strongest reserves”, and the most price-consistent insurer in every canton. Insurers may use the badge freely.")}</p>
<div class="kk-awardrow">{award_row}</div>
<p><a href="{i18n.url("award")}">{T("Alle Auszeichnungen und Badges", "Toutes les distinctions et badges", "All awards and badges")} &rarr;</a></p>

<h2>{T("Regionalkassen", "Caisses régionales", "Regional insurers")}</h2>
<p>{T("Kleinere Kassen mit unter 50'000 Versicherten. Gemessen werden sie dort, wo sie zu Hause sind: im Kanton mit den meisten Versicherten. Über alle Regionen gerechnet wären sie oft schlechter, weil sie ausserhalb ihres Gebiets kaum Kunden haben und dort selten günstig sind.",
  "Petites caisses de moins de 50'000 assurés. Elles sont évaluées là où elles sont chez elles : dans le canton où elles comptent le plus d’assurés. Calculées sur toutes les régions, elles s’en sortiraient souvent moins bien, car hors de leur territoire elles n’ont presque pas de clients et y sont rarement avantageuses.",
  "Smaller insurers with fewer than 50'000 insured persons. They are measured where they are at home: in the canton where they have the most insured persons. Calculated across all regions they would often look worse, because outside their area they have hardly any customers and are rarely cheap there.")}</p>
{reg_table}

<h2>{T("Das Rating in deiner Region", "La notation dans votre région", "The rating in your region")}</h2>
<p>{T("Preise und Konstanz unterscheiden sich stark zwischen den Regionen. Eine Kasse, die im Aargau vorne liegt, kann in Genf teuer sein. Auf jeder Kantonsseite steht, welche Kassen dort dauerhaft günstig sind:",
  "Les prix et la constance varient fortement d’une région à l’autre. Une caisse en tête en Argovie peut être chère à Genève. Chaque page cantonale indique les caisses durablement avantageuses sur place :",
  "Prices and consistency vary a lot between regions. An insurer that leads in Aargau can be expensive in Geneva. Each canton page shows which insurers are consistently cheap there:")}</p>
<div class="kk-cantonlinks">{cantons}</div>

<h2>{T("Die Sparmodell-Falle", "Le piège des modèles alternatifs", "The savings model trap")}</h2>
<p>{T("Neue Sparmodelle dürfen ohne Kostenzahlen aus fünf Jahren bis zu 20 % unter dem Standardmodell starten (Art. 101 KVV). Danach muss der Rabatt aus echten Kosten belegt sein. In den Daten sieht man, was das heisst:",
  "Sans données de coûts sur cinq ans, les nouveaux modèles alternatifs peuvent démarrer jusqu’à 20 % sous le modèle standard (art. 101 OAMal). Ensuite, le rabais doit être justifié par des coûts réels. Les données montrent ce que cela signifie :",
  "Without five years of cost data, new savings models may start up to 20% below the standard model (Art. 101 KVV). After that, the discount must be backed by real costs. The data show what that means:")}</p>
<div class="kk-table-wrap"><table class="kk-table"><thead><tr><th>{T("Neue Modelle ab", "Nouveaux modèles dès", "New models from")}</th><th class="num">{T("Rabatt im Startjahr", "Rabais l’année du lancement", "Discount in launch year")}</th><th class="num">{T("Rabatt", "Rabais", "Discount")} {YEAR}</th><th class="num">{T("Tarife × Regionen", "Tarifs × régions", "Tariffs × regions")}</th></tr></thead><tbody>
{koh_rows}
<tr><td>{T(f"Modelle, die es {y0} schon gab", f"Modèles qui existaient déjà en {y0}", f"Models that already existed in {y0}")}</td><td class="num">{pc(alte["start"])}{P}</td><td class="num">{pc(alte["heute"])}{P}</td><td class="num"></td></tr>
</tbody></table></div>
<p>{T(f"Rabatt gegenüber dem Standardmodell derselben Kasse, Franchise 2'500, Median. Dieselben Tarife vom Startjahr bis {YEAR} verfolgt. Wer in ein neues Modell wechselt und bleibt, zahlt also Jahr für Jahr etwas mehr als beim Standard. Die Teilnote «Rabatt-Treue» misst, wie stark das bei jeder Kasse passiert.",
  f"Rabais par rapport au modèle standard de la même caisse, franchise 2'500, médiane. Les mêmes tarifs suivis de l’année de lancement à {YEAR}. Qui passe à un nouveau modèle et y reste paie donc chaque année un peu plus par rapport au standard. La note partielle « Rabais durable » mesure l’ampleur de ce phénomène dans chaque caisse.",
  f"Discount versus the same insurer’s standard model, deductible 2'500, median. The same tariffs tracked from launch year to {YEAR}. So if you switch to a new model and stay, you pay a little more each year relative to standard. The “Discount retention” component measures how strongly this happens at each insurer.")}</p>

<h2>{T("Verwaltungskosten: wer viel für sich selbst ausgibt", "Frais administratifs : qui dépense beaucoup pour lui-même", "Administrative costs: who spends a lot on itself")}</h2>
<p>{T(f"Das BAG veröffentlicht für jede Kasse, was sie pro versicherte Person für die Verwaltung der Grundversicherung ausgibt: Löhne, Informatik, Werbung und Provisionen. Werbung und Provisionen an Vermittler weist es separat aus. Die Zahl fliesst nicht in die Note ein, weil sie schon im Preis steckt, aber sie zeigt, wo Prämiengeld hängen bleibt. Schnitt aller Kassen {a1}: <strong>CHF {mk[a1]:.0f}</strong>. {blog_a}Mehr dazu: was jede Kasse für Werbung und Vermittler ausgibt &rarr;</a>",
  f"L’OFSP publie pour chaque caisse ce qu’elle dépense par assuré pour administrer l’assurance de base : salaires, informatique, publicité et commissions. La publicité et les commissions aux intermédiaires sont indiquées séparément. Ce chiffre n’entre pas dans la note, car il est déjà compris dans le prix, mais il montre où reste l’argent des primes. Moyenne de toutes les caisses {a1} : <strong>CHF {mk[a1]:.0f}</strong>. {blog_a}En savoir plus : ce que chaque caisse dépense en publicité et en intermédiaires &rarr;</a>",
  f"The FOPH publishes, for every insurer, what it spends per insured person on administering basic insurance: salaries, IT, advertising and commissions. Advertising and broker commissions are shown separately. The figure does not count towards the score because it is already in the price, but it shows where premium money stays. Average of all insurers {a1}: <strong>CHF {mk[a1]:.0f}</strong>. {blog_a}More: what each insurer spends on advertising and brokers &rarr;</a>")}</p>
<div class="kk-table-wrap"><table class="kk-table"><thead><tr><th>{insurer}</th><th class="num">{a0}</th><th class="num">{a1}</th><th class="num">{T("Veränderung", "Évolution", "Change")}</th><th class="num">{T("Werbung", "Publicité", "Advertising")} {vjahr}</th><th class="num">{T("Provisionen", "Commissions", "Commissions")} {vjahr}</th></tr></thead><tbody>{adm_html}</tbody></table></div>
<p class="kk-note">{T(f"Pro versicherte Person und Jahr, nur Grundversicherung. Gesamtkosten aus den Aufsichtsdaten des BAG, Werbung und Provisionen aus der BAG-Auswertung der Verwaltungskosten. ¹ {gruppe_hinweis()}. Der Gesamtbetrag ist trotzdem vergleichbar.",
  f"Par assuré et par an, assurance de base uniquement. Coûts totaux selon les données de surveillance de l’OFSP, publicité et commissions selon l’analyse des frais administratifs de l’OFSP. ¹ {gruppe_hinweis()}. Le montant total reste comparable.",
  f"Per insured person and year, basic insurance only. Total costs from FOPH supervisory data, advertising and commissions from the FOPH analysis of administrative costs. ¹ {gruppe_hinweis()}. The total is still comparable.")}</p>

<h2>{T("So rechnen wir", "Notre méthode de calcul", "How we calculate")}</h2>
<div class="kk-table-wrap"><table class="kk-table"><thead><tr><th>{T("Teilnote", "Note partielle", "Component")}</th><th class="num">{T("Gewicht", "Poids", "Weight")}</th><th>{T("Was sie misst", "Ce qu’elle mesure", "What it measures")}</th></tr></thead><tbody>{meth_rows}</tbody></table></div>
<p>{T(f"Grundlage sind die Prämien aller Kassen {y0} bis {YEAR} für Erwachsene, je mit und ohne Unfalldeckung und mit Franchise 300 und 2'500. Daraus entstehen vier Einzelnoten; die Gesamtnote gewichtet sie nach dem Bestand laut BAG ({wtxt}). Tarife, die eine Kasse umbenennt, verfolgen wir über den Namen weiter. Fehlt eine Teilnote, verteilt sich ihr Gewicht auf die übrigen. Die Formel gilt für alle Kassen gleich, und keine Kasse bezahlt uns etwas.",
  f"La base, ce sont les primes de toutes les caisses de {y0} à {YEAR} pour les adultes, avec et sans couverture accidents, et avec franchise 300 et 2'500. On obtient quatre notes distinctes ; la note globale les pondère selon l’effectif d’après l’OFSP ({wtxt}). Les tarifs renommés par une caisse sont suivis par leur nom. S’il manque une note partielle, son poids est réparti sur les autres. La formule est la même pour toutes les caisses, et aucune caisse ne nous paie quoi que ce soit.",
  f"We use the premiums of all insurers from {y0} to {YEAR} for adults, with and without accident cover and with deductibles of 300 and 2'500. This gives four separate scores; the overall score weights them by FOPH enrolment figures ({wtxt}). Tariffs an insurer renames are followed by name. If a component is missing, its weight is spread over the others. The formula is the same for every insurer, and no insurer pays us anything.")}</p>

<div class="kk-faq"><h2>{T("Häufige Fragen", "Questions fréquentes", "Frequently asked questions")}</h2>{"".join(f"<h3>{e(q)}</h3><p>{e(a)}</p>" for q, a in qa)}</div>
<p class="kk-note">{T(f"Quellen: BAG, Prämien der obligatorischen Krankenversicherung {y0} bis {YEAR} (opendata.swiss); BAG über priminfo.admin.ch, Solvenzquoten per 1.1.2026; BAG, Aufsichtsdaten OKP; KVV Art. 101. Angaben ohne Gewähr.",
  f"Sources : OFSP, primes de l’assurance obligatoire des soins {y0} à {YEAR} (opendata.swiss) ; OFSP via priminfo.admin.ch, taux de solvabilité au 1.1.2026 ; OFSP, données de surveillance AOS ; OAMal art. 101. Sans garantie.",
  f"Sources: FOPH, compulsory health insurance premiums {y0} to {YEAR} (opendata.swiss); FOPH via priminfo.admin.ch, solvency ratios as of 1 January 2026; FOPH supervisory data; KVV Art. 101. No liability for accuracy.")}</p>"""
    h1 = T(f"Krankenkassen-Rating {YEAR}: Welche Kasse ist dauerhaft günstig?", f"Constance des primes {YEAR} : quelle caisse-maladie reste avantageuse ?",
           f"Health insurance rating {YEAR}: which insurer stays cheap?")
    jsonld = [breadcrumb([home_crumb(), ("Rating" if i18n.LANG != "fr" else "Constance des primes", path)]), faq(qa),
              {"@context": "https://schema.org", "@type": "Article", "headline": h1,
               "datePublished": f"{YEAR - 1}-10-01", "dateModified": date.today().isoformat(),
               "author": {"@type": "Organization", "name": "abovergleich.com"},
               "publisher": {"@type": "Organization", "name": "abovergleich.com", "url": SITE}, "mainEntityOfPage": f"{SITE}{path}"}]
    desc = T(f"Preistreue-Rating aller Krankenkassen aus den BAG-Prämien {y0} bis {YEAR}: Preis, Konstanz, Treue, Tarife und Reserven. "
             f"{top[0]['name']} schneidet am besten ab.",
             f"Notation Constance des primes de toutes les caisses-maladie, d’après les primes de l’OFSP {y0} à {YEAR} : prix, constance, tarifs, réserves. "
             f"{top[0]['name']} arrive en tête.",
             f"Price Consistency Rating of all Swiss health insurers from FOPH premiums {y0} to {YEAR}: price, consistency, tariffs and reserves. "
             f"{top[0]['name']} comes out best.")
    if i18n.LANG != "de":
        jsonld[2]["inLanguage"] = i18n.HREFLANG[i18n.LANG]
    return path, page(path, h1, desc, body, jsonld, dict(i18n.ROUTES["rating"]))


AWARD_CSS = """
  article.kk-page:has(.award-page) { max-width: 980px; }
  .award-page .rules { list-style:none; padding:0; display:grid; gap:10px; margin:16px 0 0; }
  .award-page .rules li { position:relative; padding-left:26px; color:var(--text2); }
  .award-page .rules li::before { content:"✓"; position:absolute; left:0; color:var(--green); font-weight:700; }
  .award-fold { border:1px solid var(--border2); border-radius:12px; padding:12px 16px; margin:14px 0; }
  .award-fold summary { cursor:pointer; font-weight:700; font-family:'Plus Jakarta Sans',sans-serif; font-size:17px; }
  .award-fold[open] summary { margin-bottom: 8px; }
  .award-cantons td.num, .award-cantons th.num { text-align:right; }
  .grouphead { font-family:'Plus Jakarta Sans',sans-serif; font-size:14px; font-weight:700; letter-spacing:.12em; text-transform:uppercase; color:var(--muted); margin:38px 0 14px; padding-bottom:9px; border-bottom:1px solid var(--border); }
  .win { background:var(--surface); border:1px solid var(--border); border-radius:14px; padding:22px; margin-bottom:18px; display:grid; grid-template-columns:240px 1fr; gap:24px; align-items:start; }
  .win > * { min-width:0; }
  .win img { display:block; max-width:100%; height:auto; }
  .win h3 { font-size:22px; margin:0 0 6px; }
  .win .meta { font-size:15px; color:var(--muted); margin-bottom:14px; }
  .variants { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:10px; }
  .variants a, .pngrow button { font:inherit; font-size:14px; background:none; border:1px solid var(--border2); border-radius:100px; padding:5px 13px; color:var(--text2); text-decoration:none; cursor:pointer; }
  .pngrow { align-items:center; }
  .pnglbl { font-size:13px; color:var(--muted); }
  .pngrow button:hover, .variants a:hover { border-color:var(--accent-dark); color:var(--accent-dark); }
  .snippet { background:var(--surface2); border:1px solid var(--border); border-radius:10px; padding:12px 14px; overflow-x:auto; }
  .snippet code { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:13px; line-height:1.7; color:var(--text2); white-space:pre; }
  .baustein-lbl { font-size:14px; font-weight:600; color:var(--muted); margin:14px 0 6px; }
  .baustein { background:var(--surface2); border-left:3px solid var(--accent); border-radius:0 8px 8px 0; padding:12px 16px; color:var(--text2); font-size:15px; line-height:1.65; margin:0; }
  .kk-awardrow { display:flex; flex-wrap:wrap; gap:10px; margin:14px 0 6px; }
  .kk-awardrow img { height:72px; width:auto; }
  @media (max-width:760px) { .win { grid-template-columns:1fr; } .win img { max-width:220px; } }
"""

AWARD_PNG_JS = """<script>
/* PNG im Browser erzeugen, nicht im Build: die Badges nutzen Georgia und
   Helvetica, die hat der Browser, ein Rasterer im Build nicht. */
document.querySelectorAll('.pngrow button').forEach(function (btn) {
  btn.addEventListener('click', function () {
    var w = +btn.dataset.w, h = +btn.dataset.h, scale = 3, label = btn.textContent;
    btn.disabled = true; btn.textContent = btn.dataset.wait || 'einen Moment';
    fetch(btn.dataset.svg).then(function (r) { return r.text(); }).then(function (svg) {
      var img = new Image();
      img.onload = function () {
        var c = document.createElement('canvas'); c.width = w * scale; c.height = h * scale;
        c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
        c.toBlob(function (blob) {
          var a = document.createElement('a'); a.href = URL.createObjectURL(blob);
          a.download = btn.dataset.name + '@3x.png'; document.body.appendChild(a); a.click(); a.remove();
          btn.disabled = false; btn.textContent = label;
        }, 'image/png');
      };
      img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
    }).catch(function () { btn.disabled = false; btn.textContent = label; });
  });
});
</script>"""


def award_loc(a):
    """Award mit den Texten der aktuellen Sprache."""
    return build_awards.loc(a, i18n.LANG)


def award_badge_url(aid, suffix=""):
    return f"{i18n.url('award')}badge/{aid}{suffix}.svg"


def write_award_badges():
    """Badges je Sprache. Die deutschen Badges der Edition sind seit der
    Mitteilung an die Kassen (02.10.2026) eingefroren: hier nicht mehr löschen,
    nur noch schreiben, wenn sich am Inhalt nichts ändert (siehe main)."""
    for lang in i18n.LANGS:
        folder = ROOT / i18n.url("award", lang).strip("/") / "badge"
        keep = {f"{a['id']}{suffix}.svg" for a in AWARDS for suffix, _, _ in build_awards.VARIANTS}
        for f in folder.glob("*.svg") if folder.exists() else []:
            if f.name not in keep:
                f.unlink()
        for a in AWARDS:
            la = build_awards.loc(a, lang)
            for suffix, fn, dark in build_awards.VARIANTS:
                target = folder / f"{a['id']}{suffix}.svg"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(fn(la, YEAR, dark), encoding="utf-8")


def award_strip(i):
    """Quer-Badges einer Kasse, für ihre Kassenseite."""
    mine = [a for a in AWARDS if a["insurer"] == i]
    if not mine:
        return ""
    # Gesamtwertung und Kategorien als Badge, Kantonssiege nur gezählt
    show = [a for a in mine if a["group"] != "Kantone"]
    kant = [a for a in mine if a["group"] == "Kantone"]
    if not show:
        show, kant = kant[:1], kant[1:]
    imgs = "".join(f'<a href="{award_url(a["id"])}"><img src="{award_badge_url(a["id"], "-quer")}" alt="{e(award_loc(a)["alt"])}" width="248" height="72" loading="lazy"></a>' for a in show[:3])
    n = len(kant)
    more = (f'<div class="kk-rnote">'
            + L(f'Dazu Sieger in {n} {"Kanton" if n == 1 else "Kantonen"}. ', f'Également en tête dans {n} canton{"" if n == 1 else "s"}. ',
                f'Also top in {n} canton{"" if n == 1 else "s"}. ')
            + f'<a href="{i18n.url("award")}">{L("Alle Auszeichnungen", "Toutes les distinctions", "All awards")}</a></div>') if kant else ""
    return f'<div class="kk-awardrow">{imgs}</div>{more}'


GROUP_LABEL = {"Gesamtwertung": ("Gesamtwertung", "Classement général", "Overall ranking"),
               "Kategorien": ("Kategorien", "Catégories", "Categories"),
               "Kantone": ("Kantone", "Cantons", "Cantons")}


def award_page():
    path = i18n.url("award")
    groups = []
    T = L
    for g in ("Gesamtwertung", "Kategorien", "Kantone"):
        items = [a for a in AWARDS if a["group"] == g]
        if not items:
            continue
        cards = []
        for a in items:
            la = award_loc(a)
            snippet = (f'<a href="{la["link"]}">' + chr(10) + f'  <img src="{SITE}{award_badge_url(a["id"])}"' + chr(10)
                       + f'       alt="{la["alt"]}"' + chr(10) + '       width="240" height="384" loading="lazy">' + chr(10) + '</a>')
            cards.append(f"""<div class="win" id="{a['id']}">
  <img src="{award_badge_url(a['id'])}" alt="{e(la['alt'])}" width="240" height="384" loading="lazy">
  <div>
    <h3>{kasse_link(a['insurer'], a['name'])}</h3>
    <p class="meta">{e(la['headline'])} · {e(la['fact'])}</p>
    <div class="variants">
      <a href="{award_badge_url(a['id'])}">{T("Hochformat hell", "Portrait clair", "Portrait light")}</a><a href="{award_badge_url(a['id'], '-dunkel')}">{T("Hochformat dunkel", "Portrait sombre", "Portrait dark")}</a>
      <a href="{award_badge_url(a['id'], '-quer')}">{T("Querformat hell", "Paysage clair", "Landscape light")}</a><a href="{award_badge_url(a['id'], '-quer-dunkel')}">{T("Querformat dunkel", "Paysage sombre", "Landscape dark")}</a>
    </div>
    <div class="variants pngrow"><span class="pnglbl">{T("Als PNG:", "En PNG :", "As PNG:")}</span>
      <button type="button" data-svg="{award_badge_url(a['id'])}" data-w="240" data-h="384" data-name="{a['id']}-hoch"{"" if i18n.LANG == "de" else ' data-wait="' + T("", "un instant", "one moment") + '"'}>{T("Hochformat", "Portrait", "Portrait")}</button>
      <button type="button" data-svg="{award_badge_url(a['id'], '-quer')}" data-w="375" data-h="109" data-name="{a['id']}-quer"{"" if i18n.LANG == "de" else ' data-wait="' + T("", "un instant", "one moment") + '"'}>{T("Querformat", "Paysage", "Landscape")}</button>
    </div>
    <div class="snippet"><code>{e(snippet)}</code></div>
    <p class="baustein-lbl">{T("Textbaustein zum Übernehmen", "Texte à reprendre", "Text you can use")}</p>
    <blockquote class="baustein">{e(la['pressText'])}</blockquote>
  </div>
</div>""")
        groups.append(f'<div class="grouphead">{e(L(*GROUP_LABEL[g]))}</div>' + "".join(cards))
    n_awards = len(AWARDS)
    y0 = RATING["years"][0]
    an = award_name()
    rl = f'<a href="{i18n.url("rating")}">{rating_name(cap=i18n.LANG != "fr")}</a>'
    crumbs = [home_crumb(), ("Rating" if i18n.LANG != "fr" else "Constance des primes", i18n.url("rating")),
              (L("Award", "Prix", "Award"), path)]

    # Der Artikel: wer gewonnen hat, in Sätzen und zwei kurzen Tabellen. Die
    # Badges und Textbausteine für die Kassen stehen eingeklappt darunter.
    ges = sorted((x for x in AWARDS if x["group"] == "Gesamtwertung"), key=lambda x: x["rank"])
    kat = [x for x in AWARDS if x["group"] == "Kategorien"]
    kan = sorted((x for x in AWARDS if x["group"] == "Kantone"), key=lambda x: cname(x["_canton"]))
    def nl(x):
        return kasse_link(x["insurer"], x["name"])
    def nt(x):
        return i18n.dec(x["_note"], 1)
    ges_txt = ""
    if len(ges) >= 3:
        ges_txt = T(f"<strong>{nl(ges[0])}</strong> ist die preistreueste Krankenkasse {YEAR}, Note {nt(ges[0])} von 10. Dahinter {nl(ges[1])} ({nt(ges[1])}) und {nl(ges[2])} ({nt(ges[2])}).",
                    f"<strong>{nl(ges[0])}</strong> est la caisse-maladie la plus constante {YEAR}, note {nt(ges[0])} sur 10. Suivent {nl(ges[1])} ({nt(ges[1])}) et {nl(ges[2])} ({nt(ges[2])}).",
                    f"<strong>{nl(ges[0])}</strong> is the most price-consistent health insurer of {YEAR}, score {nt(ges[0])} out of 10. Next come {nl(ges[1])} ({nt(ges[1])}) and {nl(ges[2])} ({nt(ges[2])}).")
    kat_rows = "".join(f'<tr><td>{e(award_loc(x)["category"])}</td><td>{nl(x)}</td><td>{e(award_loc(x)["fact"])}</td></tr>' for x in kat)
    kan_rows = "".join(f'<tr><td><a href="{canton_url(x["_canton"])}">{e(cname(x["_canton"]))}</a></td><td>{nl(x)}</td><td class="num">{nt(x)}</td></tr>' for x in kan)
    body = f"""<div class="award-page">
{crumbs_html(crumbs)}
<div class="article-badge">{T("Edition", "Édition", "Edition")} {YEAR}</div>
<h1>abovergleich {an} {YEAR}</h1>
<p class="kk-lead">{T(f"{n_awards} Auszeichnungen für Krankenkassen, die dauerhaft günstig bleiben. Vergeben allein aus den Prämiendaten des Bundes seit {y0}. Keine Jury, keine Einreichung, keine Gebühr.",
  f"{n_awards} distinctions pour des caisses-maladie qui restent durablement avantageuses. Décernées uniquement à partir des données de primes de la Confédération depuis {y0}. Pas de jury, pas de candidature, pas de frais.",
  f"{n_awards} awards for health insurers that stay cheap over time. Given solely on the basis of federal premium data since {y0}. No jury, no entry, no fee.")}</p>

<h2>{T(f"Die Gewinner {YEAR}", f"Les lauréates {YEAR}", f"The {YEAR} winners")}</h2>
<p>{ges_txt} {T(f"Grundlage ist das {rl}: Preis heute, wie oft eine Kasse seit {y0} in ihrer Region unter den fünf günstigsten war, wie stark sie aufschlägt, ob neue Sparmodelle ihren Rabatt halten, wie oft sie Tarife streicht und wie gut ihre Reserven sind.",
  f"La base est la {rl} : prix actuel, fréquence à laquelle une caisse a figuré depuis {y0} parmi les cinq moins chères de sa région, ampleur de ses hausses, maintien du rabais des nouveaux modèles alternatifs, fréquence des suppressions de tarifs et solidité des réserves.",
  f"It is based on the {rl}: price today, how often an insurer has been among the five cheapest in its region since {y0}, how much it raises prices, whether new savings models keep their discount, how often it drops tariffs and how strong its reserves are.")}</p>

<h3>{T("Kategorien", "Catégories", "Categories")}</h3>
<p>{T("Je Teilaspekt die beste Kasse mit mindestens 50'000 Versicherten. Bei Gleichstand gewinnen alle.", "La meilleure caisse d’au moins 50'000 assurés pour chaque aspect. En cas d’égalité, toutes gagnent.", "The best insurer with at least 50'000 insured persons in each aspect. In a tie, all win.")}</p>
<div class="kk-table-wrap"><table class="kk-table"><thead><tr><th>{T("Kategorie", "Catégorie", "Category")}</th><th>{T("Kasse", "Caisse", "Insurer")}</th><th>{T("Wert", "Valeur", "Value")}</th></tr></thead><tbody>{kat_rows}</tbody></table></div>

<h3>{T("Kantone", "Cantons", "Cantons")}</h3>
<p>{T("Die Kasse mit der besten Note in der Hauptregion jedes Kantons, Regionalkassen eingeschlossen. Klick auf den Kanton für alle Prämien dort.", "La caisse la mieux notée dans la région principale de chaque canton, caisses régionales comprises. Cliquez sur le canton pour toutes les primes.", "The insurer with the best score in each canton’s main region, regional insurers included. Click the canton for all premiums there.")}</p>
<div class="kk-table-wrap"><table class="kk-table award-cantons"><thead><tr><th>{T("Kanton", "Canton", "Canton")}</th><th>{T("Kasse", "Caisse", "Insurer")}</th><th class="num">{T("Note", "Note", "Score")}</th></tr></thead><tbody>{kan_rows}</tbody></table></div>

<details class="award-fold" id="regeln"><summary>{T("Die Regeln", "Les règles", "The rules")}</summary>
<ul class="rules">
  <li>{T("Die Auswahl folgt allein der Zahl. Es gibt keine Jury, keine Einreichung und keinen Weg, einen Award zu beeinflussen.", "La sélection suit uniquement les chiffres. Il n’y a ni jury, ni candidature, ni moyen d’influencer une distinction.", "Selection follows the numbers alone. There is no jury, no entry and no way to influence an award.")}</li>
  <li>{T("Der Award kostet nichts und ist an nichts gekoppelt. Ob eine Kasse das Badge einbindet oder verlinkt, ändert weder Note noch Reihenfolge auf abovergleich.com.", "La distinction est gratuite et sans condition. Qu’une caisse intègre le badge ou crée un lien ne change ni la note ni le classement sur abovergleich.com.", "The award costs nothing and comes with no strings. Whether an insurer uses or links the badge changes neither its score nor its ranking on abovergleich.com.")}</li>
  <li>{T("Ein Link ist keine Bedingung. Der Einbindungscode enthält ihn, weil eine Auszeichnung ohne Beleg wenig wert ist. Wer das Badge ohne Link nutzt, darf das.", "Un lien n’est pas obligatoire. Le code d’intégration en contient un, car une distinction sans preuve vaut peu. Utiliser le badge sans lien est permis.", "A link is not required. The embed code includes one because an award without evidence is worth little. Using the badge without a link is allowed.")}</li>
  <li>{T(f"Die Edition ist ein Stichtag: die Prämien {YEAR}. Das Badge {YEAR} behält seine Aussage, auch wenn sich die Note im nächsten Jahr ändert.", f"L’édition correspond à une date de référence : les primes {YEAR}. Le badge {YEAR} reste valable même si la note change l’année suivante.", f"Each edition has a cut-off: the {YEAR} premiums. The {YEAR} badge keeps its meaning even if the score changes next year.")}</li>
  <li>{T("Gesamtwertung und Kategorien: Kassen mit mindestens 50'000 Versicherten. Bei Gleichstand gewinnen alle. Die Note rechnen wir für vier Situationen (mit oder ohne Unfall, Franchise 300 oder 2'500) und gewichten sie nach dem Bestand laut BAG.", "Classement général et catégories : caisses d’au moins 50'000 assurés. En cas d’égalité, toutes gagnent. La note est calculée pour quatre situations (avec ou sans accidents, franchise 300 ou 2'500) et pondérée selon l’effectif d’après l’OFSP.", "Overall ranking and categories: insurers with at least 50'000 insured persons. In a tie, all win. The score is calculated for four situations (with or without accident cover, deductible 300 or 2'500) and weighted by FOPH enrolment figures.")}</li>
  <li>{T("«Schlankste Verwaltung»: die gesamten Verwaltungskosten pro versicherte Person laut BAG, letztes verfügbares Jahr, auch was eine Kasse bei einer Konzernfirma einkauft.", "« Administration la plus légère » : l’ensemble des frais administratifs par assuré selon l’OFSP, dernière année disponible, y compris ce qu’une caisse achète à une société de son groupe.", "“Leanest administration”: total administrative costs per insured person according to the FOPH, latest available year, including what an insurer buys in from a group company.")}</li>
</ul>
</details>

<details class="award-fold" id="badges"><summary>{T("Badges, Einbindungscode und Textbausteine für Kassen", "Badges, code d’intégration et textes pour les caisses", "Badges, embed code and text for insurers")}</summary>
<p class="kk-note">{T("Jede Auszeichnung als Badge in vier Varianten (SVG oder PNG), dazu der Einbindungscode und ein Satz zum Übernehmen. Kostenlos, ohne Bedingungen.", "Chaque distinction sous forme de badge en quatre variantes (SVG ou PNG), avec le code d’intégration et une phrase à reprendre. Gratuit, sans conditions.", "Every award as a badge in four variants (SVG or PNG), plus the embed code and a sentence you can use. Free, no conditions.")}</p>
{"".join(groups)}
</details>

<div class="cta-box"><h3>{T("Zahl falsch? Sag es uns.", "Un chiffre est faux ? Dites-le-nous.", "Wrong number? Tell us.")}</h3><p>{T("Wenn ein Wert nicht stimmt, korrigieren wir ihn und rechnen die Edition neu. Schreib an hello@handyabo.com.", "Si une valeur est inexacte, nous la corrigeons et recalculons l’édition. Écrivez à hello@handyabo.com.", "If a value is wrong, we correct it and recalculate the edition. Write to hello@handyabo.com.")}</p><a href="mailto:hello@handyabo.com">{T("Mail schreiben", "Écrire un e-mail", "Send an email")} &rarr;</a></div>
</div>
{AWARD_PNG_JS}
<script>
(function () {{
  function openFor() {{
    var id = location.hash.slice(1), el = id && document.getElementById(id);
    if (!el) return;
    var d = el.closest('details');
    if (d && !d.open) {{ d.open = true; el.scrollIntoView(); }}
  }}
  openFor();
  window.addEventListener('hashchange', openFor);
}})();
</script>"""
    jsonld = [breadcrumb(crumbs)]
    winner = AWARDS[0]["name"] if AWARDS else ""
    html_out = page(path, T(f"Preistreue-Award {YEAR}: die preistreuesten Krankenkassen", f"Prix Constance des primes {YEAR} : les caisses-maladie lauréates",
                            f"Price Consistency Award {YEAR}: the winning health insurers"),
                    T(f"{n_awards} Auszeichnungen für Krankenkassen, die dauerhaft günstig bleiben, allein aus BAG-Prämien seit {y0}. Sieger {YEAR}: {winner}.",
                      f"{n_awards} distinctions pour des caisses-maladie durablement avantageuses, uniquement d’après les primes de l’OFSP depuis {y0}. Lauréate {YEAR} : {winner}.",
                      f"{n_awards} awards for health insurers that stay cheap over time, based solely on FOPH premiums since {y0}. Winner {YEAR}: {winner}."),
                    body, jsonld, dict(i18n.ROUTES["award"]))
    return path, html_out.replace("</style>", AWARD_CSS + "</style>", 1)


# ── Kassenseiten und Kündigung ─────────────────────────────────────────────

KASSE_SLUG = {}   # wird in main() gefüllt: BAG-Nummer -> Slug


def slugify(name):
    s = name.lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("è", "e"), ("é", "e"), ("’", ""), ("'", "")):
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def kasse_url(i):
    return f"{i18n.url('kassen')}{KASSE_SLUG[i]}/"


def kasse_link(i, text=None):
    text = e(text or INSURER_NAMES[str(i)])
    return f'<a class="kasse-link" href="{kasse_url(i)}">{text}</a>' if i in KASSE_SLUG else text


def people(n):
    if n >= 1_000_000:
        return i18n.dec(n / 1_000_000) + L(" Mio.", " mio", "m")
    return chf(round(n, -3), 0)


def address_lines(kv, i):
    d = kv.get(i, {})
    return [d.get("name") or INSURER_NAMES[str(i)]] + d.get("address", [])


def tip(text):
    return f'<span class="tip" tabindex="0" aria-label="Info">i<span>{text}</span></span>'


def kasse_page(i, cur, by_canton_cur, prev_idx, insurers, ic, top3_cur, kv, nu):
    name = INSURER_NAMES[str(i)]
    path = kasse_url(i)
    own = [r for r in cur if r["insurer_id"] == i]
    cants = sorted({r["canton"] for r in own} & set(CANTONS), key=lambda c: cname(c))
    info = insurers.get(i)
    of = L("von", "sur", "of")

    # Beispielperson wie die Mehrheit: Erwachsene ohne Unfalldeckung (über den
    # Arbeitgeber versichert), Prämienregion 1. Die zwei häufigsten Franchisen
    # nebeneinander: 300 (45 % der Erwachsenen) und 2'500 (38 %), BAG KVSTAT T 7.16.
    by_c, idx_prev = nu["by_canton"], nu["prev_idx"]
    rows, first_in, top3_in = [], [], 0
    for c in cants:
        reg = main_region(by_c[c], c)
        cells, pos25 = [], None
        for fr in (300, 2500):
            rk = ranking(by_c[c], c, reg, fr, idx_prev, n=999)
            pos = next((n for n, x in enumerate(rk, 1) if x["insurer_id"] == i), None)
            best = rk[pos - 1] if pos else None
            if fr == 2500:
                pos25 = pos
            cells.append(f'<td class="num">{("CHF " + chf(best["premium"])) if best else "–"}'
                         f'{("<span class=sub>" + MODEL_LABEL[best["model"]] + " · " + L("Platz", "Rang", "Rank") + " " + str(pos) + " " + of + " " + str(len(rk)) + "</span>") if best else ""}</td>')
        if pos25 == 1:
            first_in.append(c)
        if pos25 and pos25 <= 3:
            top3_in += 1
        rows.append(f'<tr><td><a href="{canton_url(c)}">{e(cname(c))}</a></td>{"".join(cells)}</tr>')

    # Modellwechsel innerhalb der Kasse: Standard gegen günstigstes anderes Modell
    by_reg = defaultdict(list)
    for r in nu["rows"]:
        if r["insurer_id"] == i and r["franchise"] == 2500:
            by_reg[(r["canton"], r["region"])].append(r)
    gaps = []
    for rs in by_reg.values():
        std = [r["premium"] for r in rs if r["model_type"] == "standard"]
        oth = [r["premium"] for r in rs if r["model_type"] != "standard"]
        if std and oth:
            gaps.append((min(std) - min(oth)) * 12)
    gap = st.median(gaps) if gaps else None

    models = defaultdict(set)
    for r in own:
        if r["model_type"] != "standard":
            models[r["model_type"]].add(r["tariff_name"])
    model_html = "".join(f"<li><strong>{MODEL_LABEL[m]}:</strong> {e(', '.join(sorted(t)))}</li>"
                         for m, t in sorted(models.items(), key=lambda x: MODEL_LABEL[x[0]]))

    chg = info["change_pct"] if info else None
    t3 = top3_cur.get(i, 0)
    group = (kv.get(i) or {}).get("group")
    group_name = group.split(" (")[0] if group else None
    siblings = [j for j in KASSE_SLUG if j != i and ((kv.get(j) or {}).get("group") or "").split(" (")[0] == group_name] if group_name else []

    title = L(f"{name} Prämien {YEAR}: Erhöhung, Modelle und Rating", f"{name} primes {YEAR} : hausse, modèles et notation",
              f"{name} premiums {YEAR}: increase, models and rating")
    if chg is not None:
        desc = L(f"{name} {YEAR}: Standardprämie {pct(chg)} gegenüber {PREV}. Alle Kantone und Modelle, "
                 f"Preistreue-Note und Kündigungsadresse. Offizielle BAG-Daten.",
                 f"{name} {YEAR} : prime standard {pct(chg)} par rapport à {PREV}. Tous les cantons et modèles, "
                 f"note de constance et adresse de résiliation. Données de l’OFSP.",
                 f"{name} {YEAR}: standard premium {pct(chg)} versus {PREV}. All cantons and models, "
                 f"price consistency score and cancellation address. Official FOPH data.")
    else:
        desc = L(f"{name} {YEAR}: Prämien in allen Kantonen, Modelle, Preistreue-Note und Kündigungsadresse. BAG-Daten.",
                 f"{name} {YEAR} : primes dans tous les cantons, modèles, note de constance et adresse de résiliation. Données OFSP.",
                 f"{name} {YEAR}: premiums in all cantons, models, price consistency score and cancellation address. FOPH data.")

    crumbs = [home_crumb(), (L("Kassen", "Caisses", "Insurers"), i18n.url("kassen")), (name, path)]
    p = [crumbs_html(crumbs)]
    p.append(f'<div class="article-badge">{L("Prämien", "Primes", "Premiums")} {YEAR}</div>')
    p.append(f"<h1>{e(name)} {L('Prämien', 'primes', 'premiums')} {YEAR}</h1>")
    nc = len(cants)
    meta = L(f'Offizielle Prämien des BAG · {nc} {"Kanton" if nc == 1 else "Kantone"}',
             f'Primes officielles de l’OFSP · {nc} canton{"" if nc == 1 else "s"}',
             f'Official FOPH premiums · {nc} canton{"" if nc == 1 else "s"}')
    if info and info["bestand"] >= 1000:
        meta += L(f" · rund {people(info['bestand'])} Versicherte", f" · environ {people(info['bestand'])} assurés",
                  f" · around {people(info['bestand'])} insured")
    p.append(f'<div class="article-meta">{meta}</div>')
    if chg is not None:
        tip_chg = tip(L("Standardmodell, Erwachsene, Franchise 300, mit Unfall. "
                        "Schnitt über alle Kantone, gewichtet nach Versicherten. Der Schnitt aller Kassen ist die mittlere Prämie laut BAG.",
                        "Modèle standard, adultes, franchise 300, avec accidents. "
                        "Moyenne de tous les cantons, pondérée selon les assurés. La moyenne de toutes les caisses est la prime moyenne selon l’OFSP.",
                        "Standard model, adults, deductible 300, with accident cover. "
                        "Average across all cantons, weighted by insured persons. The all-insurer average is the FOPH mean premium."))
        if chg >= 0:
            verb = L(f"im Schnitt <strong>{pct(chg, sign=False)}</strong> teurer", f"en moyenne <strong>{pct(chg, sign=False)}</strong> plus chère",
                     f"<strong>{pct(chg, sign=False)}</strong> more expensive on average")
        else:
            verb = L(f"im Schnitt <strong>{pct(-chg, sign=False)}</strong> günstiger", f"en moyenne <strong>{pct(-chg, sign=False)}</strong> moins chère",
                     f"<strong>{pct(-chg, sign=False)}</strong> cheaper on average")
        allk = pct(BAG_OFFICIAL["change_pct"])
        p.append(L(f'<p class="kk-lead">{e(name)} wird {YEAR} {verb}. Alle Kassen zusammen: {allk}.{tip_chg}</p>',
                   f'<p class="kk-lead">En {YEAR}, {e(name)} devient {verb}. Toutes caisses confondues : {allk}.{tip_chg}</p>',
                   f'<p class="kk-lead">In {YEAR}, {e(name)} becomes {verb}. All insurers together: {allk}.{tip_chg}</p>'))
    facts = []
    if chg is not None:
        facts.append((pct(chg), L(f"gegenüber {PREV}", f"par rapport à {PREV}", f"versus {PREV}")))
    tip_top3 = tip(L("Günstigstes Angebot, Erwachsene ohne Unfall, Franchise 2'500, Region 1 jedes Kantons.",
                     "Offre la moins chère, adultes sans accidents, franchise 2'500, région 1 de chaque canton.",
                     "Cheapest offer, adults without accident cover, deductible 2'500, region 1 of each canton."))
    facts.append((f"{top3_in} {of} {nc}", L("Kantonen unter den 3 günstigsten", "cantons parmi les 3 moins chères", "cantons among the 3 cheapest") + tip_top3))
    if gap and gap > 0:
        tip_gap = tip(L("Hausarzt, HMO oder Telmed statt Standardmodell, gleiche Leistungen. Median über alle Regionen, Franchise 2'500, ohne Unfall.",
                        "Médecin de famille, HMO ou Telmed au lieu du modèle standard, mêmes prestations. Médiane de toutes les régions, franchise 2'500, sans accidents.",
                        "Family doctor, HMO or Telmed instead of the standard model, same benefits. Median across all regions, deductible 2'500, without accident cover."))
        facts.append((f"CHF {chf(gap, 0)}", L(f"pro Jahr weniger mit einem Sparmodell bei {e(name)}", f"de moins par an avec un modèle alternatif chez {e(name)}",
                                              f"less per year with a savings model at {e(name)}") + tip_gap))
    p.append('<div class="kk-facts">' + "".join(
        f'<div class="kk-fact"><div class="kk-fact-val">{v}</div><div class="kk-fact-label">{l}</div></div>' for v, l in facts) + "</div>")
    p.append(f'<a class="kk-cta" href="{i18n.url("home")}?kasse={i}#kk-rechner">'
             + L(f"Mit deiner {e(name)}-Rechnung vergleichen", f"Comparer avec votre facture {e(name)}", f"Compare with your {e(name)} bill") + " &rarr;</a>")
    p.append(rating_kasse_card(i))

    p.append(L(f"<h2>{e(name)} {YEAR} in jedem Kanton</h2>", f"<h2>{e(name)} {YEAR} dans chaque canton</h2>", f"<h2>{e(name)} {YEAR} in every canton</h2>"))
    tip_reg = tip(L("Viele Kantone haben zwei oder drei Prämienregionen. "
                    "Wir zeigen Region 1, meist die Städte. Auf dem Land ist es oft etwas günstiger. Deine genaue Prämie zeigt der Rechner.",
                    "De nombreux cantons ont deux ou trois régions de primes. "
                    "Nous montrons la région 1, généralement les villes. À la campagne, c’est souvent un peu moins cher. Le calculateur affiche votre prime exacte.",
                    "Many cantons have two or three premium regions. "
                    "We show region 1, usually the cities. In rural areas it is often a little cheaper. The calculator shows your exact premium."))
    tip_platz = tip(L(f"Das günstigste Angebot von {e(name)} im Kanton, meist ein Sparmodell (Hausarzt, HMO, Telmed, gleiche Leistungen). Platz unter allen Kassen: 1 heisst, niemand ist günstiger.",
                      f"L’offre la moins chère de {e(name)} dans le canton, le plus souvent un modèle alternatif (médecin de famille, HMO, Telmed, mêmes prestations). Rang parmi toutes les caisses : 1 signifie que personne n’est moins cher.",
                      f"The cheapest offer from {e(name)} in the canton, usually a savings model (family doctor, HMO, Telmed, same benefits). Rank among all insurers: 1 means nobody is cheaper."))
    p.append(L(f"<p>Beispiel: <strong>Erwachsene Person ohne Unfalldeckung</strong> (über den Arbeitgeber versichert), günstigstes Angebot pro Monat.{tip_reg}{tip_platz}</p>",
               f"<p>Exemple : <strong>adulte sans couverture accidents</strong> (assuré par l’employeur), offre la moins chère par mois.{tip_reg}{tip_platz}</p>",
               f"<p>Example: <strong>adult without accident cover</strong> (insured through the employer), cheapest offer per month.{tip_reg}{tip_platz}</p>"))
    fw = L("Franchise", "Franchise", "Deductible")
    p.append(f'<div class="kk-table-wrap"><table class="kk-table"><thead><tr><th>{L("Kanton", "Canton", "Canton")}</th><th class="num">{fw} 300</th>'
             f'<th class="num">{fw} 2\'500</th></tr></thead>'
             f'<tbody>{"".join(rows)}</tbody></table></div>')
    if first_in:
        links = ", ".join(f'<a href="{canton_url(c)}">{e(cname(c))}</a>' for c in first_in)
        p.append(L(f"<p>Am günstigsten von allen Kassen ist {e(name)} {YEAR} in: {links}.</p>",
                   f"<p>En {YEAR}, {e(name)} est la moins chère de toutes les caisses dans : {links}.</p>",
                   f"<p>In {YEAR}, {e(name)} is the cheapest of all insurers in: {links}.</p>"))

    if model_html:
        p.append(L(f"<h2>Modelle von {e(name)}</h2>", f"<h2>Modèles de {e(name)}</h2>", f"<h2>{e(name)} models</h2>"))
        p.append(L(f"<p>Neben dem Standardmodell mit freier Arztwahl bietet {e(name)} {YEAR} diese Tarife an "
                   f"(nicht jeder in jedem Kanton). Die Leistungen sind in allen Modellen gleich, nur die erste Anlaufstelle unterscheidet sich.</p>",
                   f"<p>Outre le modèle standard avec libre choix du médecin, {e(name)} propose en {YEAR} ces tarifs "
                   f"(pas tous dans chaque canton). Les prestations sont les mêmes dans tous les modèles, seul le premier interlocuteur change.</p>",
                   f"<p>Besides the standard model with free choice of doctor, {e(name)} offers these tariffs in {YEAR} "
                   f"(not every one in every canton). Benefits are the same in all models, only your first point of contact differs.</p>"))
        p.append(f"<ul>{model_html}</ul>")

    if siblings:
        sib = ", ".join(kasse_link(j) for j in sorted(siblings, key=lambda j: INSURER_NAMES[str(j)]))
        p.append(L(f"<h2>Gruppe {e(group_name)}</h2>", f"<h2>Groupe {e(group_name)}</h2>", f"<h2>{e(group_name)} group</h2>"))
        p.append(L(f"<p>{e(name)} gehört zur Gruppe {e(group_name)}. Weitere Kassen der Gruppe mit eigenen Prämien: {sib}.</p>",
                   f"<p>{e(name)} fait partie du groupe {e(group_name)}. Autres caisses du groupe avec leurs propres primes : {sib}.</p>",
                   f"<p>{e(name)} belongs to the {e(group_name)} group. Other insurers in the group with their own premiums: {sib}.</p>"))

    addr = address_lines(kv, i)
    p.append(L(f"<h2>{e(name)} kündigen</h2>", f"<h2>Résilier {e(name)}</h2>", f"<h2>Cancel {e(name)}</h2>"))
    p.append(L(f"<p>Die Kündigung der Grundversicherung muss bis am <strong>{deadline()}</strong> bei {e(name)} eingetroffen sein, "
               f"der Poststempel zählt nicht. Adresse laut BAG-Verzeichnis der zugelassenen Krankenversicherer:</p>",
               f"<p>La résiliation de l’assurance de base doit parvenir à {e(name)} au plus tard le <strong>{deadline()}</strong>, "
               f"le cachet de la poste ne compte pas. Adresse selon la liste de l’OFSP des assureurs-maladie autorisés :</p>",
               f"<p>Your cancellation of basic insurance must reach {e(name)} by <strong>{deadline()}</strong>; "
               f"the postmark does not count. Address according to the FOPH list of licensed health insurers:</p>"))
    p.append(f'<blockquote>{"<br>".join(e(l) for l in addr)}</blockquote>')
    kd = f'{i18n.url("kuendigen")}?kasse={i}'
    p.append(L(f'<p><a href="{kd}">Kündigungsbrief an {e(name)} erstellen</a>, fertig zum Ausdrucken.</p>',
               f'<p><a href="{kd}">Créer la lettre de résiliation pour {e(name)}</a>, prête à imprimer.</p>',
               f'<p><a href="{kd}">Create a cancellation letter to {e(name)}</a>, ready to print.</p>'))

    qa = []
    if chg is not None:
        qa.append((L(f"Wie stark steigen die Prämien von {name} {YEAR}?", f"De combien les primes de {name} augmentent-elles en {YEAR} ?",
                     f"How much are {name} premiums rising in {YEAR}?"),
                   L(f"Die Standardprämie für Erwachsene mit Franchise 300 steigt bei {name} im Schnitt um {pct(chg)}, gewichtet nach "
                     f"Versicherten je Kanton. Laut BAG steigt die mittlere Prämie aller Kassen um {BAG_OFFICIAL['change_pct']:.1f} Prozent.",
                     f"La prime standard des adultes avec franchise 300 augmente chez {name} de {pct(chg)} en moyenne, pondérée selon "
                     f"les assurés par canton. Selon l’OFSP, la prime moyenne de toutes les caisses augmente de {i18n.dec(BAG_OFFICIAL['change_pct'])} %.",
                     f"The standard premium for adults with a 300 deductible rises at {name} by {pct(chg)} on average, weighted by "
                     f"insured persons per canton. According to the FOPH, the average premium of all insurers rises by {i18n.dec(BAG_OFFICIAL['change_pct'])}%.")))
    nf = len(first_in)
    qa.append((L(f"Ist {name} günstig?", f"{name} est-elle avantageuse ?", f"Is {name} cheap?"),
               L(f"Für Erwachsene ohne Unfalldeckung mit Franchise 2'500 gehört {name} {YEAR} in {top3_in} von {nc} Kantonen zu den drei günstigsten Kassen"
                 + (f" und ist in {nf} {'Kanton' if nf == 1 else 'Kantonen'} die günstigste überhaupt." if first_in else ".")
                 + " Wie günstig es für dich ist, hängt von Wohnort, Franchise und Modell ab.",
                 f"Pour les adultes sans couverture accidents avec franchise 2'500, {name} figure en {YEAR} parmi les trois caisses les moins chères dans {top3_in} cantons sur {nc}"
                 + (f" et elle est la moins chère de toutes dans {nf} canton{'' if nf == 1 else 's'}." if first_in else ".")
                 + " Ce qu’elle vous coûte dépend de votre domicile, de votre franchise et du modèle.",
                 f"For adults without accident cover and a 2'500 deductible, {name} is among the three cheapest insurers in {top3_in} of {nc} cantons in {YEAR}"
                 + (f" and the cheapest of all in {nf} canton{'' if nf == 1 else 's'}." if first_in else ".")
                 + " How cheap it is for you depends on where you live, your deductible and the model.")))
    qa.append((L(f"Bis wann kann ich {name} kündigen?", f"Jusqu’à quand puis-je résilier {name} ?", f"When is the deadline to cancel {name}?"),
               L(f"Die Kündigung muss bis am {deadline()} bei {name} eingetroffen sein, dann wechselst du auf den 1. Januar {YEAR}. "
                 f"Adresse: {', '.join(addr)}.",
                 f"La résiliation doit parvenir à {name} au plus tard le {deadline()}, vous changez alors au 1er janvier {YEAR}. "
                 f"Adresse : {', '.join(addr)}.",
                 f"Your cancellation must reach {name} by {deadline()}; you then switch on 1 January {YEAR}. "
                 f"Address: {', '.join(addr)}.")))
    p.append(f'<div class="kk-faq"><h2>{L("Häufige Fragen", "Questions fréquentes", "Frequently asked questions")}</h2>' + "".join(f"<h3>{e(q)}</h3><p>{e(a)}</p>" for q, a in qa) + "</div>")
    rep = i18n.url("report")
    p.append(L(f'<p class="kk-note">Quelle: Bundesamt für Gesundheit (BAG), Prämien {YEAR} und {PREV}; Versichertenbestand {YEAR - 2}. '
               f'Angaben ohne Gewähr. <a href="{i18n.url("kassen")}">Alle Kassen</a> · <a href="{rep}#methode">Methode</a></p>',
               f'<p class="kk-note">Source : Office fédéral de la santé publique (OFSP), primes {YEAR} et {PREV} ; effectif des assurés {YEAR - 2}. '
               f'Sans garantie. <a href="{i18n.url("kassen")}">Toutes les caisses</a> · <a href="{rep}#methode">Méthode</a></p>',
               f'<p class="kk-note">Source: Federal Office of Public Health (FOPH), premiums {YEAR} and {PREV}; insured persons {YEAR - 2}. '
               f'No liability for accuracy. <a href="{i18n.url("kassen")}">All insurers</a> · <a href="{rep}#methode">Methodology</a></p>'))
    return path, page(path, title, desc, "\n".join(p), [breadcrumb(crumbs), faq(qa)], alts_of(lambda: kasse_url(i)))


def kasse_hub(insurers, top3_cur):
    path = i18n.url("kassen")
    nat = (RATING or {}).get("national", {})
    rk = L("Regionalkasse", "Caisse régionale", "Regional insurer")
    def regio(i):
        h = HOME.get(i)
        if h:
            return ' <span class="sub">' + L(f"Regionalkasse, Note im Kanton {e(cname(h['canton']))}",
                                              f"Caisse régionale, note {e(im_kanton(h['canton']))}",
                                              f"Regional insurer, score {e(im_kanton(h['canton']))}") + '</span>'
        return f' <span class="sub">{rk}</span>'
    shown = lambda i: (HOME[i]["note"] if i in HOME else nat.get(i, {}).get("note"))
    ids = sorted(KASSE_SLUG, key=lambda i: (nat.get(i, {}).get("regional", True), -(shown(i) or 0)))
    rows = "".join(
        f'<tr><td>{kasse_link(i)}{regio(i) if nat.get(i, {}).get("regional") else ""}</td>'
        f'<td class="num"><strong>{note_fmt(shown(i))}</strong></td>'
        f'<td class="num">{people(insurers[i]["bestand"]) if i in insurers and insurers[i]["bestand"] >= 1000 else "–"}</td>'
        f'<td class="num {"kk-up" if i in insurers and insurers[i]["change_pct"] > 0 else ""}">{pct(insurers[i]["change_pct"]) if i in insurers else "–"}</td>'
        f'</tr>' for i in ids)
    crumbs = [home_crumb(), (L("Kassen", "Caisses", "Insurers"), path)]
    rl = f'<a href="{i18n.url("rating")}">{rating_name(cap=i18n.LANG != "fr")}</a>'
    body = [
        crumbs_html(crumbs),
        f'<div class="article-badge">{L("Prämien", "Primes", "Premiums")} {YEAR}</div>',
        L(f"<h1>Alle Krankenkassen: Prämien {YEAR} im Vergleich</h1>", f"<h1>Toutes les caisses-maladie : primes {YEAR} comparées</h1>",
          f"<h1>All health insurers: {YEAR} premiums compared</h1>"),
        L(f'<div class="article-meta">{len(ids)} Kassen mit Grundversicherung · Offizielle BAG-Daten</div>',
          f'<div class="article-meta">{len(ids)} caisses proposant l’assurance de base · Données officielles de l’OFSP</div>',
          f'<div class="article-meta">{len(ids)} insurers offering basic insurance · Official FOPH data</div>'),
        L(f'<p class="kk-lead">Welche Kasse dauerhaft günstig ist und wie stark sie {YEAR} aufschlägt. '
          f'Ein Klick auf die Kasse zeigt alle Kantone, Modelle und die Kündigungsadresse.</p>',
          f'<p class="kk-lead">Quelle caisse est durablement avantageuse et de combien elle augmente en {YEAR}. '
          f'Un clic sur la caisse affiche tous les cantons, les modèles et l’adresse de résiliation.</p>',
          f'<p class="kk-lead">Which insurer is consistently cheap and how much it raises premiums in {YEAR}. '
          f'Click an insurer to see all cantons, models and the cancellation address.</p>'),
        f'<div class="kk-table-wrap"><table class="kk-table"><thead><tr><th>{L("Kasse", "Caisse", "Insurer")}</th><th class="num">{L("Preistreue", "Constance", "Consistency")}</th>'
        f'<th class="num">{L("Versicherte", "Assurés", "Insured")}</th><th class="num">vs. {PREV}</th></tr></thead><tbody>{rows}</tbody></table></div>',
        L(f'<p class="kk-note">Preistreue: Note von 0 bis 10 aus dem {rl}, sortiert nach Note, Regionalkassen am Schluss. '
          f'Veränderung: Standardmodell, Franchise 300, gewichtet nach Versicherten je Kanton. '
          f'Versicherte: Durchschnittsbestand {YEAR - 2} laut BAG.</p>',
          f'<p class="kk-note">Constance : note de 0 à 10 issue de la {rl}, triée par note, caisses régionales à la fin. '
          f'Évolution : modèle standard, franchise 300, pondérée selon les assurés par canton. '
          f'Assurés : effectif moyen {YEAR - 2} selon l’OFSP.</p>',
          f'<p class="kk-note">Consistency: score from 0 to 10 from the {rl}, sorted by score, regional insurers last. '
          f'Change: standard model, deductible 300, weighted by insured persons per canton. '
          f'Insured: average number in {YEAR - 2} according to the FOPH.</p>'),
    ]
    return path, page(path, L(f"Alle Krankenkassen {YEAR}: Prämienerhöhung je Kasse im Vergleich",
                              f"Toutes les caisses-maladie {YEAR} : hausse des primes par caisse",
                              f"All health insurers {YEAR}: premium increase per insurer"),
                      L(f"Alle {len(ids)} Krankenkassen mit Grundversicherung {YEAR}: Prämienveränderung, Versicherte und wo sie günstig sind. Offizielle BAG-Daten.",
                        f"Les {len(ids)} caisses-maladie de l’assurance de base {YEAR} : évolution des primes, assurés et où elles sont avantageuses. Données OFSP.",
                        f"All {len(ids)} health insurers offering basic insurance {YEAR}: premium change, insured persons and where they are cheap. FOPH data."),
                      "\n".join(body), [breadcrumb(crumbs)], dict(i18n.ROUTES["kassen"]))


KUENDIGEN_CSS = """
  .kd-form { display:grid; grid-template-columns:1fr 1fr; gap:12px; margin:16px 0; }
  .kd-form label { display:block; font-size:12px; font-weight:600; color:var(--muted); text-transform:uppercase; letter-spacing:.04em; margin-bottom:4px; }
  .kd-form input, .kd-form select, .kd-form textarea { width:100%; box-sizing:border-box; padding:10px 12px; border:1px solid var(--border2); border-radius:8px; font:inherit; font-size:15px; background:var(--surface); color:var(--text); }
  .kd-form .full { grid-column:1 / -1; }
  .kd-check { display:flex; gap:8px; align-items:flex-start; font-size:14px; color:var(--text2); }
  .kd-check input { width:auto; margin-top:4px; }
  .kd-zusatz { border:0; padding:0; margin:0; display:flex; flex-direction:column; gap:8px; }
  .kd-zusatz legend { font-size:12px; font-weight:700; text-transform:uppercase; letter-spacing:.05em; color:var(--muted); margin-bottom:8px; }
  .kd-form .kd-zusatz .kd-check { text-transform:none; letter-spacing:0; font-size:15px; font-weight:500; color:var(--text); margin:0; }
  .kd-reco { font-size:11px; font-weight:700; color:var(--green); background:rgba(22,163,74,.1); border-radius:999px; padding:1px 8px; margin-left:4px; white-space:nowrap; }
  .kd-warn { font-size:14px; line-height:1.5; color:var(--text2); background:rgba(234,88,12,.07); border-left:3px solid var(--orange); border-radius:8px; padding:12px 14px; }
  .kd-warn a { color:var(--accent-dark); }
  .kd-plzort { display:grid; grid-template-columns:110px 1fr; gap:10px; }
  .kd-form .kd-invalid { border-color:var(--orange); background:rgba(234,88,12,.05); }
  .kd-send { background:var(--surface); border:2px solid var(--accent); border-radius:14px; padding:18px 20px; margin:18px 0 12px; }
  .kd-send-title { font-family:'Plus Jakarta Sans',sans-serif; font-weight:800; font-size:18px; margin-bottom:4px; }
  .kd-send p { font-size:14px; color:var(--text2); margin:0 0 12px; }
  .kd-send-row { display:flex; gap:10px; flex-wrap:wrap; margin-bottom:8px; }
  .kd-send-row input { flex:1 1 220px; min-width:0; box-sizing:border-box; padding:12px; border:1px solid var(--border2); border-radius:8px; font:inherit; font-size:16px; background:var(--surface); color:var(--text); }
  .kd-send-row button { flex:0 0 auto; background:var(--accent); color:var(--text); border:none; border-radius:10px; padding:12px 20px; font-weight:700; cursor:pointer; font-family:inherit; font-size:15px; }
  .kd-send-row button:disabled { opacity:.6; cursor:default; }
  .kd-send .kd-hint a { color:var(--accent-dark); }
  .kd-consent { display:flex; gap:10px; align-items:flex-start; font-size:13px; line-height:1.5; color:var(--text2); margin:4px 0 8px; cursor:pointer; }
  .kd-consent input { width:18px; height:18px; margin-top:2px; flex:0 0 auto; accent-color:var(--accent-dark); }
  .kd-consent a { color:var(--accent-dark); }
  .kd-done { display:flex; gap:14px; align-items:flex-start; background:rgba(22,163,74,.08); border:2px solid var(--green); border-radius:14px; padding:18px 20px; margin:14px 0; }
  .kd-done-icon { flex:0 0 36px; height:36px; border-radius:50%; background:var(--green); color:#fff; font-size:20px; font-weight:800; display:flex; align-items:center; justify-content:center; }
  .kd-done strong { display:block; font-family:'Plus Jakarta Sans',sans-serif; font-size:19px; margin-bottom:4px; }
  .kd-done p { margin:0; font-size:15px; line-height:1.5; color:var(--text2); }
  .kd-terms { font-size:12px; color:var(--muted); margin:8px 0 0; }
  .kd-terms a { color:var(--muted); }
  .kd-ctas { display:flex; flex-wrap:wrap; align-items:center; gap:8px 20px; margin:8px 0 24px; }
  .kd-ctas .kk-cta { margin:0; }
  .kd-cta-sec { color:var(--accent-dark) !important; font-weight:600; }
  #kd-brief { background:#fff; color:#111; border:1px solid var(--border2); border-radius:8px; padding:32px 36px; font-family:Arial,Helvetica,sans-serif; font-size:14px; line-height:1.55; white-space:pre-wrap; margin:12px 0; }
  .kd-actions { display:flex; gap:10px; flex-wrap:wrap; }
  .kd-actions button { background:var(--accent); color:var(--text); border:none; border-radius:10px; padding:12px 18px; font-weight:700; cursor:pointer; font-family:inherit; }
  .kd-actions button.sec { background:var(--surface2); }
  .kd-days { font-family:'Plus Jakarta Sans',sans-serif; font-size:28px; font-weight:800; }
  .kd-hint { font-size:12px; color:var(--muted); margin-top:4px; }
  .kd-sign { margin:8px 0 4px; }
  .kd-sign label { display:block; font-size:12px; font-weight:600; color:var(--muted); text-transform:uppercase; letter-spacing:.04em; margin-bottom:4px; }
  #kd-pad { display:block; width:100%; height:140px; touch-action:none; background:#fff; border:1px dashed var(--border2); border-radius:8px; cursor:crosshair; }
  .kd-sign-row { display:flex; justify-content:space-between; align-items:center; font-size:13px; color:var(--muted); margin-top:6px; }
  .kd-link { background:none; border:none; padding:0; font:inherit; font-weight:600; color:var(--accent-dark); cursor:pointer; }
  .kd-link:disabled { color:var(--muted); cursor:default; opacity:.6; }
  .kd-sig-img { display:block; height:52px; width:auto; margin:2px 0; }
  .kd-kanal { background:var(--surface); border:1px solid var(--border2); border-left:4px solid var(--accent); border-radius:10px; padding:14px 16px; font-size:14px; line-height:1.6; margin:12px 0; }
  .kd-kanal:empty { display:none; }
  .kd-kanal a { color:var(--accent-dark); font-weight:600; }
  .kd-src { font-size:12px; color:var(--muted); margin-top:6px; }
  .kd-src a { color:var(--muted) !important; font-weight:400 !important; }
  .kd-actions button[hidden] { display:none; }
  .kd-actions button:disabled { opacity:.6; cursor:default; }
  .kd-msg { font-size:13px; color:var(--text2); margin-top:8px; min-height:1em; }
  .kd-wechsel[hidden], .kk-cta[hidden] { display:none !important; }
  .kd-wechsel { background:var(--surface); border:2px solid var(--accent); border-radius:14px; padding:18px 20px; margin:18px 0; font-size:15px; line-height:1.6; }
  .kd-wechsel h2 { font-size:19px; margin:0 0 8px; }
  .kd-wechsel ol { margin:0; padding-left:20px; }
  .kd-wechsel li { margin:8px 0; }
  .kd-wechsel a { color:var(--accent-dark); font-weight:700; }
  .kd-wechsel .kd-go { display:inline-block; margin-top:6px; background:var(--accent); color:var(--text); padding:9px 16px; border-radius:10px; text-decoration:none; }
  .kd-preview-label { font-size:12px; font-weight:600; color:var(--muted); text-transform:uppercase; letter-spacing:.04em; margin-top:18px; }
  .kd-intro { font-size:15px; color:var(--text2); margin:0 0 6px; }
  .kd-compare { display:inline-block; margin-left:6px; color:var(--accent-dark) !important; font-weight:600; font-size:14px; }
  .kd-compare[hidden] { display:none; }
  .kd-lbl-note { text-transform:none; letter-spacing:0; font-weight:400; color:var(--muted); }
  .kd-stepper { list-style:none; display:flex; gap:8px; flex-wrap:wrap; margin:6px 0 18px; padding:0; }
  .kd-stepper[hidden] { display:none; }
  .kd-stepper li { display:flex; align-items:center; gap:8px; font-size:14px; font-weight:600; color:var(--muted); background:var(--surface2); border-radius:999px; padding:7px 14px 7px 8px; }
  .kd-stepper li b { width:22px; height:22px; border-radius:50%; background:var(--border2); color:var(--text); font-size:12px; display:inline-flex; align-items:center; justify-content:center; }
  .kd-stepper li.on { color:var(--text); background:var(--surface); border:2px solid var(--accent); padding:5px 12px 5px 6px; }
  .kd-stepper li.on b { background:var(--accent); }
  .kd-stepper li.ok b { background:var(--green); color:#fff; }
  .kd-more { border:1px dashed var(--border2); border-radius:10px; padding:10px 14px; }
  .kd-more summary { cursor:pointer; font-size:13px; font-weight:600; color:var(--text2); }
  .kd-more summary .kd-lbl-note { font-weight:400; }
  .kd-more-grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-top:12px; }
  .kd-more-grid .full { grid-column:1 / -1; }
  .kd-preview { margin:18px 0 8px; }
  .kd-preview summary { cursor:pointer; font-size:13px; font-weight:600; color:var(--accent-dark); }
  .kd-actions { align-items:center; }
  .kd-actions button.kd-link { background:none; padding:12px 6px; font-weight:600; color:var(--accent-dark); }
  .kd-done { display:block; }
  .kd-done-head { display:flex; gap:14px; align-items:flex-start; }
  .kd-done-small { display:block; font-size:13px; color:var(--muted); margin-top:4px; }
  .kd-nx-h { font-family:'Plus Jakarta Sans',sans-serif; font-weight:800; font-size:16px; margin:16px 0 8px; }
  .kd-nx { margin:0; padding-left:22px; }
  .kd-nx li { margin:0 0 14px; font-size:15px; }
  .kd-nx li::marker { font-weight:700; }
  .kd-nx-sub { font-size:14px; color:var(--text2); line-height:1.5; margin-top:6px; }
  .kd-done .kd-go { display:inline-block; background:var(--accent); color:var(--text); padding:11px 18px; border-radius:10px; text-decoration:none; font-weight:700; }
  .kd-done .kd-go.sec { background:var(--surface); border:2px solid var(--accent); padding:9px 16px; }
  .kd-nx strong { display:inline; font-family:inherit; font-size:15px; margin:0; }
  .kd-addr { display:inline-block; font-size:16px; word-break:break-all; margin:4px 4px 4px 0; }
  .kd-done .kd-copy-addr { border:none; cursor:pointer; font:inherit; font-weight:700; padding:7px 14px; font-size:14px; }
  .kd-done .kd-nx-sub a { color:var(--accent-dark); }
  @media (max-width:640px) { .kd-form, .kd-more-grid { grid-template-columns:1fr; } #kd-brief { padding:20px; } }
  @media print {
    body * { visibility:hidden; }
    #kd-brief, #kd-brief * { visibility:visible; }
    #kd-brief { position:absolute; left:0; top:0; width:100%; border:none; padding:0; margin:0; font-size:12pt; }
  }
"""


def kuendigen_page(kv):
    path = i18n.url("kuendigen")
    ids = sorted(KASSE_SLUG, key=lambda i: INSURER_NAMES[str(i)].lower())
    # Kündigungswege je Kasse, recherchiert auf den Seiten der Kassen selbst
    kan_doc = json.loads((DATA / "kuendigung_kanaele.json").read_text(encoding="utf-8"))
    kan = {x["id"]: x for x in kan_doc["kassen"]}

    def weg(i):
        x = kan.get(i, {})
        ok = x.get("email_accepted") == "ja"
        return {
            "mail": x.get("cancel_email") if ok else None,
            "own": bool(x.get("sender_must_be_on_file")) if ok else False,
            # Mail erlaubt, aber keine Adresse: dann bleibt das Kundenportal (Swica)
            "portal": x.get("online_channel") if ok and not x.get("cancel_email") else None,
            "post_only": x.get("email_accepted") == "nein",
            "src": (x.get("sources") or [None])[0],
            # Anmeldung: direkt in den Prämienrechner der Kasse, in der Sprache
            # der Seite, sonst deutsch. Geprüft am signup_stand.
            "url": ((x.get("signup") or {}).get(i18n.LANG) or (x.get("signup") or {}).get("de")
                    or (f"https://www.{x['web']}" if x.get("web") else None)),
            # Ohne Online-Anmeldung (nur Formular oder PDF) kein «10 Minuten online»
            "online": x.get("signup_online", True),
            # Parameter, mit denen der Rechner der Kasse PLZ/Geburtsdatum übernimmt
            "prefill": x.get("signup_prefill"),
        }

    stand = i18n.date_short(kan_doc["stand"]) if i18n.LANG == "en" else ".".join(str(int(t)) for t in reversed(kan_doc["stand"].split("-")))
    data = [{"id": i, "name": INSURER_NAMES[str(i)], "address": address_lines(kv, i), **weg(i)} for i in ids]
    end = i18n.date_long(f"{PREV}-12-31")
    deadline_iso = f"{PREV}-11-30"
    kd_data = json.dumps({"kassen": data, "end": end, "end_iso": f"{PREV}-12-31", "start": i18n.date_long(f"{YEAR}-01-01"),
                          "deadline": deadline_iso, "deadline_text": deadline(), "stand": stand,
                          "lang": i18n.LANG, "calc": f'{i18n.url("home")}#kk-rechner',
                          "privacy": f'{i18n.url("datenschutz")}#kuendigung'}, ensure_ascii=False).replace("</", "<\\/")

    post = L("Post", "Poste", "Post")
    def weg_cell(i):
        w = weg(i)
        if w["mail"]:
            return e(w["mail"]) + (" *" if w["own"] else "")
        if w["portal"]:
            return e(w["portal"])
        return post
    addr_rows = "".join(f'<tr><td>{kasse_link(i)}</td><td>{e(", ".join(address_lines(kv, i)))}</td><td>{weg_cell(i)}</td></tr>' for i in ids)
    n_mail = sum(1 for i in ids if weg(i)["mail"] or weg(i)["portal"])
    dl, dls = deadline(), deadline(short=True)
    qa = [
        (L("Bis wann muss ich die Krankenkasse kündigen?", "Jusqu’à quand dois-je résilier ma caisse-maladie ?", "What is the deadline to cancel my health insurance?"),
         L(f"Die Kündigung der Grundversicherung muss bis am {dl} bei der Kasse eingetroffen sein. "
           f"Massgebend ist das Datum, an dem die Kasse den Brief erhält, nicht der Poststempel. Der Wechsel gilt ab 1. Januar {YEAR}.",
           f"La résiliation de l’assurance de base doit parvenir à la caisse au plus tard le {dl}. "
           f"C’est la date de réception par la caisse qui compte, pas le cachet de la poste. Le changement prend effet le 1er janvier {YEAR}.",
           f"Your cancellation of basic insurance must reach the insurer by {dl}. "
           f"What counts is the date the insurer receives the letter, not the postmark. The switch takes effect on 1 January {YEAR}.")),
        (L("Muss ich per Einschreiben kündigen?", "Dois-je résilier par lettre recommandée ?", "Do I have to cancel by registered mail?"),
         L("Nein. Das Gesetz schreibt keine Form vor, entscheidend ist, dass die Kündigung rechtzeitig ankommt. "
           f"{n_mail} von {len(ids)} Kassen nehmen sie laut eigener Website auch per Mail an, die Tabelle unten zeigt welche. "
           "Per Post ist das Einschreiben der sicherste Beweis, per Mail die Eingangsbestätigung der Kasse.",
           "Non. La loi n’impose aucune forme, l’essentiel est que la résiliation arrive à temps. "
           f"Selon leur site, {n_mail} caisses sur {len(ids)} l’acceptent aussi par e-mail, le tableau ci-dessous indique lesquelles. "
           "Par la poste, le recommandé est la preuve la plus sûre ; par e-mail, c’est la confirmation de réception de la caisse.",
           "No. The law prescribes no form; what matters is that the cancellation arrives on time. "
           f"According to their own websites, {n_mail} of {len(ids)} insurers also accept it by email; the table below shows which. "
           "By post, registered mail is the safest proof; by email, the insurer’s confirmation of receipt.")),
        (L("Kann die neue Krankenkasse mich ablehnen?", "La nouvelle caisse-maladie peut-elle me refuser ?", "Can the new health insurer refuse me?"),
         L("Nein. In der Grundversicherung muss jede Kasse in ihrem Tätigkeitsgebiet alle Personen aufnehmen, ohne Gesundheitsfragen. "
           "Bei Zusatzversicherungen ist das anders.",
           "Non. Dans l’assurance de base, chaque caisse doit accepter toute personne dans sa zone d’activité, sans questions de santé. "
           "Pour les assurances complémentaires, c’est différent.",
           "No. In basic insurance, every insurer must accept everyone in its area of operation, without health questions. "
           "Supplementary insurance is different.")),
        (L("Was passiert mit meiner Zusatzversicherung?", "Qu’advient-il de mon assurance complémentaire ?", "What happens to my supplementary insurance?"),
         L("Nichts, wenn du sie nicht selbst kündigst. Die Zusatzversicherung kann bei der bisherigen Kasse bleiben, auch wenn du "
           "die Grundversicherung wechselst. Für sie gelten eigene Fristen im Vertrag. Ein Wechsel lohnt sich selten: Die neue Kasse "
           "darf Gesundheitsfragen stellen und Vorbehalte machen. Berater empfehlen ihn trotzdem oft, weil sie dafür Provision erhalten.",
           "Rien, si vous ne la résiliez pas vous-même. L’assurance complémentaire peut rester auprès de votre caisse actuelle, même si vous "
           "changez d’assurance de base. Elle a ses propres délais, fixés dans le contrat. Changer en vaut rarement la peine : la nouvelle caisse "
           "peut poser des questions de santé et émettre des réserves. Les conseillers le recommandent pourtant souvent, car ils touchent une commission.",
           "Nothing, unless you cancel it yourself. Supplementary insurance can stay with your current insurer even if you "
           "switch basic insurance. It has its own notice periods in the contract. Switching it rarely pays off: the new insurer "
           "may ask health questions and impose exclusions. Advisers still often recommend it, because they earn a commission.")),
        (L("Kann ich auch auf Ende Juni wechseln?", "Puis-je aussi changer pour fin juin ?", "Can I also switch at the end of June?"),
         L("Nur im Standardmodell mit Franchise 300. Dann muss die Kündigung bis 31. März eintreffen, der Wechsel gilt ab 1. Juli.",
           "Seulement en modèle standard avec franchise 300. La résiliation doit alors parvenir au plus tard le 31 mars, le changement prend effet le 1er juillet.",
           "Only in the standard model with a 300 deductible. The cancellation must then arrive by 31 March, and the switch takes effect on 1 July.")),
    ]
    crumb_name = L("Krankenkasse kündigen", "Résilier sa caisse-maladie", "Cancel health insurance")
    crumbs = [home_crumb(), (crumb_name, path)]
    calc = f'{i18n.url("home")}#kk-rechner'
    prov = i18n.url("blog/provisionen-zusatzversicherung")
    T = L
    zus_tip = T("Eine Zusatzversicherung zu wechseln lohnt sich selten. Die neue Kasse darf Gesundheitsfragen stellen, Vorbehalte machen oder dich ablehnen, und mit dem Alter wird der Einstieg teurer. Berater drängen trotzdem oft dazu, weil sie dafür bis zu 16 Monatsprämien Provision erhalten.",
                "Changer d’assurance complémentaire en vaut rarement la peine. La nouvelle caisse peut poser des questions de santé, émettre des réserves ou vous refuser, et l’entrée coûte plus cher avec l’âge. Les conseillers poussent pourtant souvent au changement, car ils touchent jusqu’à 16 primes mensuelles de commission.",
                "Switching supplementary insurance rarely pays off. The new insurer may ask health questions, impose exclusions or refuse you, and joining gets more expensive with age. Advisers still often push for it, because they earn up to 16 monthly premiums in commission.")
    more_lbl = T("Weitere Angaben", "Autres indications", "More details")
    body = f"""{crumbs_html(crumbs)}
<div class="article-badge">{T("Frist", "Délai", "Deadline")} {dl}</div>
<h1>{T(f"Krankenkasse kündigen: bis {dls}, mit Vorlage", f"Résilier sa caisse-maladie : d’ici au {dls}, avec modèle", f"Cancel your health insurance: by {dls}, with template")}</h1>
<div class="article-meta">{T(f"Grundversicherung auf den 1. Januar {YEAR} wechseln · Brief in 2 Minuten", f"Changer d’assurance de base au 1er janvier {YEAR} · lettre en 2 minutes", f"Switch basic insurance on 1 January {YEAR} · letter in 2 minutes")}</div>
<p class="kk-lead">{T(f"Bis <strong>{dl}</strong> muss die Kündigung bei deiner Kasse <strong>eingetroffen</strong> sein.",
  f"La résiliation doit être <strong>parvenue</strong> à votre caisse au plus tard le <strong>{dl}</strong>.",
  f"Your cancellation must have <strong>reached</strong> your insurer by <strong>{dl}</strong>.")} <span id="kd-left"></span></p>
<ol id="wechsel" class="kd-stepper" hidden></ol>

<h2 id="vorlage">{T("Kündigungsbrief erstellen", "Créer la lettre de résiliation", "Create your cancellation letter")}</h2>
<p class="kd-intro">{T("Ausfüllen, unterschreiben, fertig. Das PDF kommt per Mail, abschicken an die Kasse tust du selbst.",
  "Remplir, signer, terminé. Le PDF arrive par e-mail, c’est vous qui l’envoyez à la caisse.",
  "Fill in, sign, done. The PDF arrives by email; you send it to the insurer yourself.")}
  {tip(T("Wir schicken nie selbst an die Kasse: Mehrere Kassen nehmen eine Kündigung per Mail nur vom Absender an, den sie von dir kennen.", "Nous n’envoyons jamais nous-mêmes à la caisse : plusieurs caisses n’acceptent une résiliation par e-mail que depuis l’adresse qu’elles connaissent.", "We never send to the insurer ourselves: several insurers only accept an emailed cancellation from the address they have on file for you."))}
  <a id="kd-compare" class="kd-compare" href="{calc}">{T("Noch keine neue Kasse? Zuerst vergleichen", "Pas encore de nouvelle caisse ? Comparez d’abord", "No new insurer yet? Compare first")} &rarr;</a></p>
<div class="kd-form">
  <div class="full"><label for="kd-kasse">{T("Deine bisherige Kasse", "Votre caisse actuelle", "Your current insurer")}</label><select id="kd-kasse"></select></div>
  <div><label for="kd-name">{T("Vorname und Name", "Prénom et nom", "First and last name")}</label><input id="kd-name" autocomplete="name"></div>
  <div><label for="kd-birth">{T("Geburtsdatum", "Date de naissance", "Date of birth")}</label><input id="kd-birth" autocomplete="bday" inputmode="numeric" placeholder="12.03.1985"></div>
  <div><label for="kd-street">{T("Strasse und Nr.", "Rue et n°", "Street and no.")}</label><input id="kd-street" autocomplete="address-line1"></div>
  <div class="kd-plzort"><div><label for="kd-plz">{T("PLZ", "NPA", "Postcode")}</label><input id="kd-plz" autocomplete="postal-code" inputmode="numeric" maxlength="4" placeholder="{T("8004", "1003", "8004")}"></div><div><label for="kd-ort">{T("Ort", "Localité", "Town")}</label><input id="kd-ort" autocomplete="address-level2" placeholder="{T("Zürich", "Lausanne", "Zurich")}"></div></div>
  <div class="full"><label for="kd-email">{T("E-Mail", "E-mail", "Email")} <span class="kd-lbl-note">{T("dorthin kommt das PDF", "le PDF y est envoyé", "the PDF goes here")}</span></label><input id="kd-email" type="email" autocomplete="email" placeholder="{T("du@beispiel.ch", "vous@exemple.ch", "you@example.ch")}"></div>
  <fieldset class="kd-zusatz full"><legend>{T("Zusatzversicherung bei dieser Kasse", "Assurance complémentaire auprès de cette caisse", "Supplementary insurance with this insurer")} {tip(zus_tip + f' <a href="{prov}">' + T("Mehr dazu", "En savoir plus", "More") + '</a>')}</legend>
    <label class="kd-check"><input type="radio" name="kd-zusatz" value="behalten" checked> {T("Behalten, nur die Grundversicherung kündigen", "La garder, ne résilier que l’assurance de base", "Keep it, cancel basic insurance only")} <span class="kd-reco">{T("empfohlen", "recommandé", "recommended")}</span></label>
    <label class="kd-check"><input type="radio" name="kd-zusatz" value="kuendigen"> {T("Auch kündigen", "La résilier aussi", "Cancel it too")}</label>
    <div class="kd-warn" id="kd-zusatz-warn" hidden>{T(f'<strong>Gut überlegen.</strong> Die neue Kasse darf Gesundheitsfragen stellen und dich ablehnen, und die Zusatzversicherung hat eigene Fristen, oft drei Monate. Kündige sie erst, wenn die neue schriftlich zugesagt hat. <a href="{prov}">Warum Berater zum Wechsel drängen</a>',
      f'<strong>Réfléchissez bien.</strong> La nouvelle caisse peut poser des questions de santé et vous refuser, et l’assurance complémentaire a ses propres délais, souvent trois mois. Ne la résiliez que lorsque la nouvelle vous a accepté par écrit. <a href="{prov}">Pourquoi les conseillers poussent au changement</a>',
      f'<strong>Think twice.</strong> The new insurer may ask health questions and refuse you, and supplementary insurance has its own notice periods, often three months. Only cancel it once the new insurer has accepted you in writing. <a href="{prov}">Why advisers push you to switch</a>')}</div>
  </fieldset>
  <details class="kd-more full"><summary>{more_lbl} <span class="kd-lbl-note">{T("Versicherten-Nr., Kinder, Sprache des Briefs", "n° d’assuré, enfants, langue de la lettre", "policy no., children, letter language")}</span></summary>
    <div class="kd-more-grid">
      <div><label for="kd-nr">{T("Versicherten-Nr.", "N° d’assuré", "Policy no.")} <span class="kd-lbl-note">{T("steht auf der Karte", "sur la carte d’assuré", "on your insurance card")}</span></label><input id="kd-nr"></div>
      <div><label for="kd-lang">{T("Sprache des Briefs", "Langue de la lettre", "Letter language")}</label><select id="kd-lang"><option value="de">{T("Deutsch", "Allemand", "German")}</option><option value="fr">{T("Französisch", "Français", "French")}</option></select></div>
      <div class="full"><label for="kd-more">{T("Kinder im selben Brief", "Enfants dans la même lettre", "Children in the same letter")} <span class="kd-lbl-note">{T("eine Person pro Zeile, mit Geburtsdatum", "une personne par ligne, avec date de naissance", "one person per line, with date of birth")}</span></label><textarea id="kd-more" rows="2" placeholder="{T("Anna Muster, 12.03.2015", "Anne Exemple, 12.03.2015", "Anna Muster, 12.03.2015")}"></textarea><div class="kd-hint">{T("Erwachsene kündigen je selbst, mit eigenem Brief und eigener Unterschrift.", "Les adultes résilient chacun pour soi, avec leur propre lettre et leur propre signature.", "Adults each cancel for themselves, with their own letter and signature.")}</div></div>
    </div>
  </details>
</div>
<div class="kd-sign">
  <label for="kd-pad">{T("Unterschrift", "Signature", "Signature")}</label>
  <canvas id="kd-pad" aria-label="{T("Hier unterschreiben", "Signez ici", "Sign here")}"></canvas>
  <div class="kd-sign-row"><span id="kd-pad-hint"></span><button type="button" id="kd-pad-clear" class="kd-link">{T("Neu zeichnen", "Recommencer", "Redraw")}</button></div>
</div>
<div id="kd-kanal" class="kd-kanal"></div>
<label class="kd-consent"><input type="checkbox" id="kd-wecker" checked> <span>{T("Nächstes Jahr die besten Kassen für mich ins Postfach (1 Mail im Jahr)", "L’an prochain, recevoir les meilleures caisses pour moi par e-mail (1 e-mail par an)", "Next year, send me the best insurers for me by email (1 email a year)")}</span></label>
<div class="kd-actions"><button id="kd-send">{T("Kündigung erstellen", "Créer la résiliation", "Create cancellation")}</button><button id="kd-copy" class="kd-link">{T("Nur Text kopieren", "Copier le texte seulement", "Copy text only")}</button></div>
<div class="kd-terms">{T(f'Mit dem Versand akzeptierst du unseren <a href="{i18n.url("datenschutz")}#kuendigung" target="_blank">Datenschutz</a>: Wir speichern deine E-Mail-Adresse und die Angaben zum Wechsel, den Brief nur 60 Tage zum Abholen.',
  f'En envoyant, vous acceptez notre <a href="{i18n.url("datenschutz")}#kuendigung" target="_blank">politique de confidentialité</a> : nous enregistrons votre adresse e-mail et les données du changement, la lettre seulement 60 jours pour le téléchargement.',
  f'By sending, you accept our <a href="{i18n.url("datenschutz")}#kuendigung" target="_blank">privacy policy</a>: we store your email address and the details of the switch, and the letter for 60 days only so you can download it.')}</div>
<div id="kd-msg" class="kd-msg" role="status"></div>
<div id="kd-done" class="kd-done" hidden></div>
<details class="kd-preview"><summary>{T("Brief ansehen", "Voir la lettre", "View the letter")}</summary><div id="kd-brief"></div></details>

<h2>{T("So läuft der Wechsel", "Comment se passe le changement", "How the switch works")}</h2>
<ol>
<li>{T(f"<strong>Kündigung abschicken:</strong> per Mail, wenn deine Kasse das annimmt (steht beim Brief), sonst per Post. Eingetroffen bis {dl}, der Poststempel zählt nicht.",
  f"<strong>Envoyer la résiliation :</strong> par e-mail si votre caisse l’accepte (indiqué avec la lettre), sinon par la poste. Reçue au plus tard le {dl}, le cachet de la poste ne compte pas.",
  f"<strong>Send the cancellation:</strong> by email if your insurer accepts that (shown with the letter), otherwise by post. Received by {dl}; the postmark does not count.")}</li>
<li>{T(f"<strong>Bei der neuen Kasse anmelden</strong>, für den 1. Januar {YEAR}. Online in etwa 10 Minuten, ohne Gesundheitsfragen. Sie muss dich nehmen.",
  f"<strong>S’inscrire auprès de la nouvelle caisse</strong>, pour le 1er janvier {YEAR}. En ligne en 10 minutes environ, sans questions de santé. Elle doit vous accepter.",
  f"<strong>Sign up with your new insurer</strong> for 1 January {YEAR}. Online in about 10 minutes, no health questions. It must accept you.")}</li>
<li>{T("<strong>Bestätigung abwarten.</strong> Die neue Kasse meldet der alten, dass du bei ihr versichert bist. Bis dahin bleibst du bei der alten versichert, du bist nie ohne Schutz.",
  "<strong>Attendre la confirmation.</strong> La nouvelle caisse informe l’ancienne que vous êtes assuré chez elle. D’ici là, vous restez assuré auprès de l’ancienne, jamais sans couverture.",
  "<strong>Wait for confirmation.</strong> The new insurer tells the old one that you are insured with it. Until then you stay insured with the old one, never without cover.")}</li>
</ol>
<p>{T("Wichtig: Wer bis 31. Dezember noch offene Prämien oder Kostenbeteiligungen bei der bisherigen Kasse hat, kann nicht wechseln. Offene Rechnungen vorher bezahlen.",
  "Important : si vous avez encore des primes ou des participations aux coûts impayées auprès de votre caisse actuelle au 31 décembre, vous ne pouvez pas changer. Réglez d’abord les factures ouvertes.",
  "Important: if you still have unpaid premiums or cost-sharing with your current insurer on 31 December, you cannot switch. Pay any open bills first.")}</p>

<h2>{T("Sonderfälle", "Cas particuliers", "Special cases")}</h2>
<ul>
<li>{T(f"<strong>Nur das Modell oder die Franchise ändern, bei derselben Kasse:</strong> geht ebenfalls auf den 1. Januar. Die Frist steht in den Bedingungen deiner Kasse; sicher bist du, wenn du bis {dl} meldest.",
  f"<strong>Changer seulement de modèle ou de franchise, dans la même caisse :</strong> c’est aussi possible au 1er janvier. Le délai figure dans les conditions de votre caisse ; vous êtes sûr de respecter le délai en l’annonçant d’ici au {dl}.",
  f"<strong>Only changing model or deductible with the same insurer:</strong> also possible from 1 January. The deadline is in your insurer’s terms; you are safe if you notify them by {dl}.")}</li>
<li>{T("<strong>Kündigung auf Ende Juni:</strong> nur im Standardmodell mit Franchise 300, Eingang bis 31. März.",
  "<strong>Résiliation pour fin juin :</strong> seulement en modèle standard avec franchise 300, réception au plus tard le 31 mars.",
  "<strong>Cancelling for the end of June:</strong> only in the standard model with a 300 deductible, received by 31 March.")}</li>
<li>{T("<strong>Umzug ins Ausland oder Tod:</strong> die Versicherung endet ohne Frist mit dem Wegzug beziehungsweise dem Todestag.",
  "<strong>Départ à l’étranger ou décès :</strong> l’assurance prend fin sans délai au départ ou au jour du décès.",
  "<strong>Moving abroad or death:</strong> the insurance ends without notice on the day you leave or the day of death.")}</li>
</ul>

<h2>{T("Adressen aller Krankenkassen", "Adresses de toutes les caisses-maladie", "Addresses of all health insurers")}</h2>
<p>{T(f"Adressen laut BAG-Verzeichnis der zugelassenen Krankenversicherer. Manche Kassen nennen auf ihrer Website zusätzlich eine eigene Adresse für Kündigungen, beide sind gültig. Die Spalte «Kündigung» zeigt, ob die Kasse auf ihrer Website ausdrücklich eine Kündigung der Grundversicherung per Mail annimmt (Stand {stand}). «Post» heisst: sie sagt nichts dazu oder verlangt einen Brief.",
  f"Adresses selon la liste de l’OFSP des assureurs-maladie autorisés. Certaines caisses indiquent en plus sur leur site une adresse propre pour les résiliations ; les deux sont valables. La colonne « Résiliation » indique si la caisse accepte expressément sur son site une résiliation de l’assurance de base par e-mail (état au {stand}). « Poste » signifie : elle ne dit rien à ce sujet ou exige une lettre.",
  f"Addresses according to the FOPH list of licensed health insurers. Some insurers also give their own address for cancellations on their website; both are valid. The “Cancellation” column shows whether the insurer explicitly accepts cancellation of basic insurance by email on its website (as of {stand}). “Post” means it says nothing about it or requires a letter.")}</p>
<div class="kk-table-wrap"><table class="kk-table"><thead><tr><th>{T("Kasse", "Caisse", "Insurer")}</th><th>{T("Adresse", "Adresse", "Address")}</th><th>{T("Kündigung", "Résiliation", "Cancellation")}</th></tr></thead><tbody>{addr_rows}</tbody></table></div>
<p class="kk-note">{T("* Nur von der Mail-Adresse, die die Kasse von dir kennt.", "* Uniquement depuis l’adresse e-mail que la caisse connaît.", "* Only from the email address the insurer has on file for you.")}</p>

<div class="kk-faq"><h2>{T("Häufige Fragen", "Questions fréquentes", "Frequently asked questions")}</h2>{"".join(f"<h3>{e(q)}</h3><p>{e(a)}</p>" for q, a in qa)}</div>
<p class="kk-note">{T('Quellen: Bundesamt für Gesundheit (<a href="https://www.bag.admin.ch/de/praemien-und-kosten-antworten-auf-haeufige-fragen">Fragen zu Prämien und Wechsel</a>), <a href="https://www.bag.admin.ch/de/verzeichnisse-der-zugelassenen-kranken-und-rueckversicherer">Verzeichnis der zugelassenen Krankenversicherer</a>. Angaben ohne Gewähr.',
  'Sources : Office fédéral de la santé publique (<a href="https://www.bag.admin.ch/fr/praemien-und-kosten-antworten-auf-haeufige-fragen">questions sur les primes et le changement</a>), <a href="https://www.bag.admin.ch/fr/verzeichnisse-der-zugelassenen-kranken-und-rueckversicherer">liste des assureurs-maladie autorisés</a>. Sans garantie.',
  'Sources: Federal Office of Public Health (<a href="https://www.bag.admin.ch/en/praemien-und-kosten-antworten-auf-haeufige-fragen">questions on premiums and switching</a>), <a href="https://www.bag.admin.ch/en/verzeichnisse-der-zugelassenen-kranken-und-rueckversicherer">list of licensed health insurers</a>. No liability for accuracy.')}</p>

<script id="kd-data" type="application/json">{kd_data}</script>
<script src="/js/combobox.js"></script>
<script src="/js/kuendigung.js"></script>"""
    html_out = page(path, T(f"Krankenkasse kündigen {PREV}: Frist {dls}, Vorlage und Adressen",
                            f"Résilier sa caisse-maladie {PREV} : délai {dls}, modèle et adresses",
                            f"Cancel health insurance {PREV}: deadline {dls}, template and addresses"),
                    T(f"Grundversicherung kündigen: bis {dl} muss die Kündigung bei der Kasse sein. Kostenlose Vorlage, Adressen aller Kassen, Schritt für Schritt.",
                      f"Résilier l’assurance de base : la résiliation doit parvenir à la caisse d’ici au {dl}. Modèle gratuit, adresses de toutes les caisses.",
                      f"Cancel basic health insurance: your cancellation must reach the insurer by {dl}. Free template, addresses of all insurers, step by step."),
                    body, [breadcrumb(crumbs), faq(qa)], dict(i18n.ROUTES["kuendigen"]))
    return path, html_out.replace("</style>", KUENDIGEN_CSS + "</style>", 1)



def pickup_page():
    """Abholseite für das Kündigungs-PDF aus der Mail. Erst der Klick auf den
    Knopf bestätigt die E-Mail-Adresse (Mailfilter öffnen Links, klicken aber
    keine Knöpfe). Nicht in der Sitemap, noindex. Die Texte im Skript kommen
    als JSON in der Sprache der Seite."""
    path = f'{i18n.url("kuendigen")}pdf/'
    calc = f'{i18n.url("home")}#kk-rechner'
    T = L
    S = {
        "incomplete": T("Dieser Link ist unvollständig. Öffne ihn direkt aus der Mail.", "Ce lien est incomplet. Ouvrez-le directement depuis l’e-mail.", "This link is incomplete. Open it directly from the email."),
        "wait": T("Einen Moment…", "Un instant…", "One moment…"),
        "fail": T("Das hat nicht geklappt.", "Cela n’a pas fonctionné.", "That didn’t work."),
        "btn": T("PDF herunterladen", "Télécharger le PDF", "Download PDF"),
        "w_mail": T("<strong>Weiterleiten:</strong> unsere Mail «Kündigung Grundversicherung» an {z}. Text und PDF sind schon drin. Von der Adresse, die {k} von dir kennt.", "<strong>Transférer :</strong> notre e-mail « Résiliation assurance de base » à {z}. Le texte et le PDF y sont déjà. Depuis l’adresse que {k} connaît.", "<strong>Forward</strong> our email “Kündigung Grundversicherung” to {z}. Text and PDF are already in it. From the address {k} has on file for you."),
        "w_nosig_mail": T(" Im PDF fehlt die Unterschrift: ausdrucken, unterschreiben, einscannen.", " La signature manque dans le PDF : imprimez, signez, scannez.", " The PDF has no signature: print, sign and scan it."),
        "w_portal": T("<strong>Abschicken:</strong> das PDF in {z} hochladen oder per Post an {k}.", "<strong>Envoyer :</strong> téléverser le PDF dans {z} ou l’envoyer par la poste à {k}.", "<strong>Send it:</strong> upload the PDF to {z} or post it to {k}."),
        "w_post": T("<strong>Abschicken:</strong> ausdrucken und per Post an {k}.", "<strong>Envoyer :</strong> imprimer et envoyer par la poste à {k}.", "<strong>Send it:</strong> print it and post it to {k}."),
        "w_nosig_post": T(" Vorher von Hand unterschreiben.", " Signez-le d’abord à la main.", " Sign it by hand first."),
        "m_open": T("Oder neue Mail an {k} öffnen", "Ou ouvrir un nouvel e-mail à {k}", "Or open a new email to {k}"),
        "m_subject": T("Kündigung Grundversicherung", "Résiliation assurance de base", "Kündigung Grundversicherung"),
        "m_body_de": "Sehr geehrte Damen und Herren\n\nIm Anhang sende ich Ihnen meine unterschriebene Kündigung der Grundversicherung auf den {e}.\n\nBitte bestätigen Sie mir den Eingang.\n\nFreundliche Grüsse",
        "m_body_fr": "Madame, Monsieur,\n\nVous trouverez en pièce jointe ma résiliation signée de l’assurance de base pour le {e}.\n\nJe vous prie de bien vouloir m’en confirmer la réception.\n\nMeilleures salutations",
        "end_de": i18n.date_long(f"{PREV}-12-31", "de"), "end_fr": i18n.date_long(f"{PREV}-12-31", "fr"),
        "neu_named": T("<strong>Bei {n} anmelden</strong>, online in etwa 10 Minuten, ohne Gesundheitsfragen. AHV-Nummer bereithalten.", "<strong>S’inscrire chez {n}</strong>, en ligne en 10 minutes environ, sans questions de santé. Numéro AVS sous la main.", "<strong>Sign up with {n}</strong>, online in about 10 minutes, no health questions. Have your AHV number ready."),
        "go": T("Zu {n}", "Vers {n}", "Go to {n}"),
        "neu_form": T("<strong>Bei {n} anmelden.</strong> {n} hat keine Online-Anmeldung: Offerte anfordern oder Beitrittsformular ausfüllen.", "<strong>S’inscrire chez {n}.</strong> {n} n’a pas d’inscription en ligne : demandez une offre ou remplissez le formulaire d’adhésion.", "<strong>Sign up with {n}.</strong> {n} has no online sign-up: request an offer or fill in the membership form."),
        "ids": {INSURER_NAMES[str(i)]: i for i in KASSE_SLUG},
        "offline": [INSURER_NAMES[str(x["id"])] for x in json.loads((DATA / "kuendigung_kanaele.json").read_text(encoding="utf-8"))["kassen"] if x.get("signup_online") is False],
        "neu_any": T("<strong>Bei der neuen Kasse anmelden</strong>, online in etwa 10 Minuten, ohne Gesundheitsfragen.", "<strong>S’inscrire auprès de la nouvelle caisse</strong>, en ligne en 10 minutes environ, sans questions de santé.", "<strong>Sign up with the new insurer</strong>, online in about 10 minutes, no health questions."),
        "find": T("Günstigste Kasse finden", "Trouver la caisse la moins chère", "Find the cheapest insurer"),
        "list_short": T("<li>Beginn: 1. Januar</li><li>AHV-Nummer (756…, steht auf deiner Versichertenkarte)</li><li>Franchise und Modell</li><li>beim Hausarzt- oder HMO-Modell: deine Praxis</li>",
                        "<li>Début : 1er janvier</li><li>numéro AVS (756…, sur votre carte d’assuré)</li><li>franchise et modèle</li><li>pour le modèle médecin de famille ou HMO : votre cabinet</li>",
                        "<li>Start: 1 January</li><li>AHV number (756…, on your insurance card)</li><li>deductible and model</li><li>for the family doctor or HMO model: your practice</li>"),
        "ok": T("<strong>E-Mail-Adresse bestätigt.</strong> Dein PDF wird heruntergeladen.", "<strong>Adresse e-mail confirmée.</strong> Votre PDF est en cours de téléchargement.", "<strong>Email address confirmed.</strong> Your PDF is downloading."),
        "notstarted": T("Nicht gestartet?", "Le téléchargement n’a pas démarré ?", "Didn’t start?"),
        "next": T("So geht es weiter", "La suite", "What happens next"),
        "arrive": T(" Eintreffen bis {d}.", " Doit parvenir d’ici au {d}.", " Must arrive by {d}."),
        "confirm": T("<strong>Bestätigung abwarten.</strong> {n} meldet {k}, dass du dort versichert bist. Bis dahin bleibst du bei {k}.",
                     "<strong>Attendre la confirmation.</strong> {n} informe {k} que vous êtes assuré chez elle. D’ici là, vous restez chez {k}.",
                     "<strong>Wait for confirmation.</strong> {n} tells {k} that you are insured there. Until then you stay with {k}."),
        "nonet": T("Keine Verbindung. Bitte nochmals versuchen.", "Pas de connexion. Veuillez réessayer.", "No connection. Please try again."),
        "thanks": T("Danke für deine Antwort", "Merci pour votre réponse", "Thanks for your answer"),
        "the_new": T("der neuen Kasse", "la nouvelle caisse", "the new insurer"),
        "a_yes": T("<strong>Super.</strong> Jetzt fehlt nur noch die Bestätigung: Die neue Kasse meldet sich bei {k}. Wir fragen Mitte Dezember nach, ob alles geklappt hat.",
                   "<strong>Parfait.</strong> Il ne manque plus que la confirmation : la nouvelle caisse informera {k}. Nous vous demanderons mi-décembre si tout a fonctionné.",
                   "<strong>Great.</strong> Now only the confirmation is missing: the new insurer will contact {k}. We’ll check in mid-December whether everything worked."),
        "a_no": T("Kein Problem, das geht online in etwa 10 Minuten.", "Pas de problème, cela se fait en ligne en 10 minutes environ.", "No problem, it takes about 10 minutes online."),
        "b_yes": T("<strong>Perfekt, dein Wechsel ist durch.</strong> Ab 1. Januar bist du bei {n} versichert.", "<strong>Parfait, votre changement est fait.</strong> Dès le 1er janvier, vous êtes assuré chez {n}.", "<strong>Perfect, your switch is done.</strong> From 1 January you are insured with {n}."),
        "b_no": T("Ruf {k} an und frag nach, ob die Kündigung angekommen ist. Hast du sie per Mail geschickt, ist deine gesendete Mail der Beweis, per Einschreiben der Beleg der Post. Und frag bei {n} nach, ob die Anmeldung durch ist: Erst wenn die neue Kasse sich bei der alten meldet, endet die alte Versicherung.",
                  "Appelez {k} et demandez si la résiliation est arrivée. Si vous l’avez envoyée par e-mail, votre e-mail envoyé fait office de preuve ; par recommandé, le récépissé de la poste. Demandez aussi à {n} si l’inscription est faite : l’ancienne assurance ne prend fin que lorsque la nouvelle caisse informe l’ancienne.",
                  "Call {k} and ask whether the cancellation arrived. If you sent it by email, your sent email is the proof; by registered mail, the post office receipt. Also ask {n} whether your sign-up went through: the old insurance only ends once the new insurer informs the old one."),
        "stop": T("Erledigt, du bekommst zu diesem Brief keine Erinnerungen mehr.", "C’est fait, vous ne recevrez plus de rappels pour cette lettre.", "Done, you won’t get any more reminders about this letter."),
        "saved": T("Gespeichert.", "Enregistré.", "Saved."),
        "reopen": T("Keine Verbindung. Bitte Link nochmals öffnen.", "Pas de connexion. Veuillez rouvrir le lien.", "No connection. Please open the link again."),
        "calc": calc,
        "lang": i18n.LANG,
    }
    s_json = json.dumps(S, ensure_ascii=False).replace("</", "<\\/")
    crumbs = [home_crumb(), (T("Krankenkasse kündigen", "Résilier sa caisse-maladie", "Cancel health insurance"), i18n.url("kuendigen")),
              (T("Dein PDF", "Votre PDF", "Your PDF"), path)]
    body = f"""{crumbs_html(crumbs)}
<h1>{T("Deine Kündigung", "Votre résiliation", "Your cancellation")}</h1>
<div id="kp">
  <p class="kk-lead">{T("Ein Klick, und du hast dein PDF. Damit bestätigst du auch deine E-Mail-Adresse.", "Un clic et vous avez votre PDF. Cela confirme aussi votre adresse e-mail.", "One click and you have your PDF. This also confirms your email address.")}</p>
  <button class="kk-cta kp-btn" id="kp-go">{S["btn"]}</button>
</div>
<div id="kp-msg" class="kk-note" role="status"></div>
<script>
(function () {{
  var S = {s_json};
  var f = function (s, v) {{ return s.replace(/\{{(\w)\}}/g, function (_, x) {{ return v[x] != null ? v[x] : ''; }}); }};
  var API = 'https://zexpmaegqsayleaohiip.supabase.co/functions/v1/kuendigung-pdf';
  var t = new URLSearchParams(location.search).get('t') || '';
  var box = document.getElementById('kp'), msg = document.getElementById('kp-msg');
  // UTM anhängen, auch wenn der Link schon ? oder # enthält
  var utm = function (u) {{ var h = u.indexOf('#'), a = h < 0 ? u : u.slice(0, h), z = h < 0 ? '' : u.slice(h);
    return a + (a.indexOf('?') < 0 ? '?' : '&') + 'utm_source=abovergleich.com&utm_medium=affiliate&utm_campaign=kk-wechsel' + z; }};
  var esc = function (s) {{ return String(s || '').replace(/[&<>"]/g, function (c) {{ return {{ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }}[c]; }}); }};
  if (!t) {{ box.innerHTML = '<p class="kk-lead">' + S.incomplete + '</p>'; return; }}
  function go(btn) {{
    btn.disabled = true; btn.textContent = S.wait; msg.textContent = '';
    fetch(API, {{ method: 'POST', headers: {{ 'Content-Type': 'application/json' }}, body: JSON.stringify({{ action: 'abholen', t: t, lang: S.lang }}) }})
      .then(function (r) {{ return r.json(); }})
      .then(function (d) {{
        if (!d.ok) {{ msg.textContent = d.error || S.fail; btn.disabled = false; btn.textContent = S.btn; return; }}
        var LB = S.lang === 'fr' ? 'fr' : 'de';
        var mailto = 'mailto:' + encodeURIComponent(d.ziel || '') + '?subject=' + encodeURIComponent(S.m_subject) +
          '&body=' + encodeURIComponent(f(S['m_body_' + LB], {{ e: S['end_' + LB] }}));
        var weg = d.kanal === 'mail'
          ? f(S.w_mail, {{ z: '<a href="mailto:' + esc(d.ziel) + '">' + esc(d.ziel) + '</a>', k: esc(d.kasse) }}) + (d.signiert ? '' : S.w_nosig_mail) + f(S.arrive, {{ d: esc(d.deadline) }}) +
            '<br><a class="kk-cta kp-cta" href="' + mailto + '">' + f(S.m_open, {{ k: esc(d.kasse) }}) + ' &rarr;</a>'
          : d.kanal === 'portal' ? f(S.w_portal, {{ z: esc(d.ziel), k: esc(d.kasse) }}) + f(S.arrive, {{ d: esc(d.deadline) }})
          : f(S.w_post, {{ k: esc(d.kasse) }}) + (d.signiert ? '' : S.w_nosig_post) + f(S.arrive, {{ d: esc(d.deadline) }});
        var neuUrl = d.neu_url ? esc(utm(d.neu_url)) : null;
        var neu = (d.neu
          ? f(S.offline.indexOf(d.neu) >= 0 ? S.neu_form : S.neu_named, {{ n: esc(d.neu) }}) + (neuUrl ? '<br><a class="kk-cta kp-cta" href="' + neuUrl + '" target="_blank" rel="noopener sponsored">' + f(S.go, {{ n: esc(d.neu) }}) + ' &rarr;</a>' : '')
          : S.neu_any + '<br><a class="kk-cta kp-cta" href="' + S.calc + '">' + S.find + ' &rarr;</a>');
        box.innerHTML = '<p class="kk-lead">' + S.ok + ' <a href="' + esc(d.url) + '">' + S.notstarted + '</a></p>' +
          '<h2>' + S.next + '</h2><ol class="kp-steps">' +
          '<li>' + weg + '</li>' +
          '<li>' + neu + '</li>' +
          '<li>' + f(S.confirm, {{ n: d.neu ? esc(d.neu) : S.the_new, k: esc(d.kasse) }}) + '</li></ol>';
        // Statistik ohne Personendaten: welcher Knopf, welche Kassen
        Array.prototype.forEach.call(box.querySelectorAll('a.kp-cta'), function (a) {{
          a.addEventListener('click', function () {{
            var ev = /^mailto:/.test(a.href) ? 'kuendigung_mail' : a.href.indexOf(S.calc) >= 0 ? null : 'anmeldung_klick';
            if (!ev) return;
            try {{ fetch('https://zexpmaegqsayleaohiip.supabase.co/functions/v1/kk-ereignis', {{ method: 'POST', keepalive: true,
              headers: {{ 'Content-Type': 'application/json' }}, body: JSON.stringify({{ event: ev, quelle: 'abholseite',
              kasse_alt: S.ids[d.kasse] || null, kasse_neu: S.ids[d.neu] || null, kanal: d.kanal }}) }}).catch(function () {{}}); }} catch (e) {{}}
          }});
        }});
        location.href = d.url;
      }})
      .catch(function () {{ msg.textContent = S.nonet; btn.disabled = false; btn.textContent = S.btn; }});
  }}
  document.getElementById('kp-go').onclick = function () {{ go(this); }};

  // Antworten aus den Erinnerungsmails: ?frage=anmeldung|bestaetigung|stopp&a=ja|nein
  var frage = new URLSearchParams(location.search).get('frage'), a = new URLSearchParams(location.search).get('a') || '';
  if (frage) {{
    document.querySelector('h1').textContent = S.thanks;
    box.innerHTML = '<p class="kk-lead">' + S.wait + '</p>';
    fetch(API, {{ method: 'POST', headers: {{ 'Content-Type': 'application/json' }}, body: JSON.stringify({{ action: 'antwort', t: t, frage: frage, a: a, lang: S.lang }}) }})
      .then(function (r) {{ return r.json(); }})
      .then(function (d) {{
        if (!d.ok) {{ box.innerHTML = '<p class="kk-lead">' + esc(d.error || S.fail) + '</p>'; return; }}
        var neu = d.neu ? esc(d.neu) : S.the_new;
        var html = {{
          'anmeldung|ja': '<p class="kk-lead">' + f(S.a_yes, {{ k: esc(d.kasse) }}) + '</p>',
          'anmeldung|nein': '<p class="kk-lead">' + S.a_no + '</p><ul class="kp-list">' + S.list_short + '</ul>' +
            (d.neu_url ? '<a class="kk-cta" href="' + esc(utm(d.neu_url)) + '" target="_blank" rel="noopener sponsored">' + f(S.go, {{ n: neu }}) + ' &rarr;</a>' : '<a class="kk-cta" href="' + S.calc + '">' + S.find + ' &rarr;</a>'),
          'bestaetigung|ja': '<p class="kk-lead">' + f(S.b_yes, {{ n: neu }}) + '</p>',
          'bestaetigung|nein': '<p class="kk-lead">' + f(S.b_no, {{ k: esc(d.kasse), n: neu }}) + '</p>',
          'stopp|': '<p class="kk-lead">' + S.stop + '</p>'
        }}[frage + '|' + (frage === 'stopp' ? '' : a)] || '<p class="kk-lead">' + S.saved + '</p>';
        box.innerHTML = html;
      }})
      .catch(function () {{ box.innerHTML = '<p class="kk-lead">' + S.reopen + '</p>'; }});
  }}
}})();
</script>"""
    html_out = page(path, T("Deine Kündigung herunterladen", "Télécharger votre résiliation", "Download your cancellation"),
                    T("Kündigungsbrief für die Grundversicherung herunterladen.", "Télécharger la lettre de résiliation de l’assurance de base.", "Download the cancellation letter for basic insurance."),
                    body, [], alts_of(lambda: f'{i18n.url("kuendigen")}pdf/'))
    html_out = html_out.replace('<meta name="robots" content="index, follow">', '<meta name="robots" content="noindex, nofollow">', 1)
    return path, html_out.replace("</style>", "  .kp-btn { border:none; cursor:pointer; font-family:inherit; font-size:16px; }\n  .kp-btn:disabled { opacity:.6; }\n  .kp-list { margin:8px 0 8px 18px; }\n  .kp-list li { margin:2px 0; }\n  .kp-steps li { margin:0 0 14px; }\n  .kp-cta { margin:8px 0 0; font-size:15px; }\n</style>", 1)


# Werbung und Provisionen aller Kassen in der Grundversicherung, Mio. CHF.
# Summe aus der BAG-Auswertung Verwaltungskosten (Jahresrechnung definitiv,
# OKP CH), mit fusionierten Kassen zusammengezählt wie in der BAG-Pivot.
# Deckt sich mit moneyland (Okt. 2024) und Handelszeitung (Sept. 2025).
MARKT_WERBUNG = {2020: 60.3, 2021: 62.4, 2022: 72.6, 2023: 80.0, 2024: 73.3, 2025: 74.1}
MARKT_PROVISIONEN = {2020: 60.4, 2021: 48.1, 2022: 48.4, 2023: 59.0, 2024: 49.9, 2025: 32.6}
BLOG_VERWALTUNG = "/blog/verwaltungskosten-krankenkassen/"
BLOG_VERWALTUNG_KEY = "blog/verwaltungskosten-krankenkassen"


def blog_verwaltung_page():
    """Blog: Verwaltungskosten, Werbung und Provisionen je Kasse. Jede Zahl
    kommt aus den BAG-Dateien, nichts ist von Hand übertragen."""
    path = i18n.url(BLOG_VERWALTUNG_KEY)
    nat = RATING["national"]
    adm = RATING["verwaltung"]["kassen"]
    mk = RATING["verwaltung"]["markt_verwaltung"]
    big = [i for i in nat if not nat[i]["regional"] and nat[i]["note"] is not None and adm.get(str(i))]
    last = max(mk)
    first = min(mk)
    def v(i, y=None):
        d = adm[str(i)]
        return d.get(y or max(d), {}).get("verwaltung")
    rows = sorted(big, key=lambda i: v(i, last) or 999)
    vj = max((vdet(i)[0] for i in big if vdet(i)[0]), default="")
    tot_n = sum(adm[str(i)][last]["bestand"] for i in adm if last in adm[str(i)])
    tot_p = sum(adm[str(i)][last]["bestand"] * adm[str(i)][last]["praemie"] for i in adm if last in adm[str(i)])
    share = mk[last] / (tot_p / tot_n) * 100
    lo, hi = rows[0], rows[-1]
    wb = max(big, key=lambda i: (vdet(i)[1] or {}).get("werbung", 0))
    pv = max(big, key=lambda i: (vdet(i)[1] or {}).get("provisionen", 0))
    def prov_years(i):
        d = VDET.get(str(i)) or {}
        ys = sorted(d)[-2:]
        return [d[y]["provisionen"] for y in ys] if len(ys) == 2 else None
    # «praktisch keine Provisionen» nur bei zwei Jahren in Folge unter CHF 2 und eigenem Personal,
    # sonst kann eine Umbuchung in den Betriebsaufwand dahinterstecken
    pv0 = [i for i in big if prov_years(i) and max(prov_years(i)) < 2 and not (vdet(i)[1] or {}).get("ohne_personal")]
    fus = [i for i in big if adm[str(i)][last].get("bestand", 0) < 50_000]
    grow = sorted((i for i in big if v(i, first)), key=lambda i: v(i, last) / v(i, first))
    sol = lambda i: nat[i]["raw"].get("solvenz")
    thin = [i for i in big if (v(i, last) or 0) > mk[last] and (sol(i) or 999) < 130]
    flag = lambda i: (vdet(i)[1] or {}).get("ohne_personal")
    ch = lambda a, b: f"{(b / a - 1) * 100:+.0f}".replace("-", "−") + "&#8239;%"
    nm = lambda i: e(nat[i]["name"])
    T = L
    AND = T(" und ", " et ", " and ")

    trs = "".join(
        f'<tr><td>{kasse_link(i)}{"&nbsp;¹" if flag(i) else ""}{"&nbsp;²" if i in fus else ""}</td><td class="num"><strong>CHF {v(i, last):.0f}</strong></td>'
        f'<td class="num">{ch(v(i, first), v(i, last)) if v(i, first) else "–"}</td>'
        f'<td class="num">{("CHF " + format((vdet(i)[1] or {}).get("werbung", 0), ".0f")) if vdet(i)[1] else "–"}</td>'
        f'<td class="num">{("CHF " + format((vdet(i)[1] or {}).get("provisionen", 0), ".0f")) if vdet(i)[1] else "–"}</td>'
        f'<td class="num">{(format(sol(i), ".0f") + "&#8239;%") if sol(i) else "–"}</td>'
        f'<td class="num">{note_fmt(nat[i]["note"])}</td></tr>' for i in rows)
    mrows = "".join(f'<tr><td>{y}</td><td class="num">{MARKT_WERBUNG[y]:.1f}</td><td class="num">{MARKT_PROVISIONEN[y]:.1f}</td></tr>'
                    for y in sorted(MARKT_WERBUNG))
    if i18n.LANG != "en":
        mrows = mrows.replace(".", ",")
    title = T("Verwaltungskosten der Krankenkassen: was jede Kasse ausgibt", "Frais administratifs des caisses-maladie : ce que dépense chaque caisse",
              "Health insurers’ administrative costs: what each insurer spends")
    desc = T("Verwaltung, Werbung und Vermittler-Provisionen je Krankenkasse in der Grundversicherung, "
             "mit Reserven und Preistreue-Note. Alle Zahlen vom BAG.",
             "Administration, publicité et commissions aux intermédiaires par caisse-maladie dans l’assurance de base, "
             "avec réserves et note de constance. Tous les chiffres de l’OFSP.",
             "Administration, advertising and broker commissions per health insurer in basic insurance, "
             "with reserves and price consistency score. All figures from the FOPH.")
    short = T("Verwaltungskosten", "Frais administratifs", "Administrative costs")
    crumbs = [home_crumb(), (T("Ratgeber", "Guide", "Guide"), i18n.url("blog")), (short, path)]
    rl = f'<a href="{i18n.url("rating")}">{rating_name(cap=i18n.LANG != "fr")}</a>'
    wbv, pvv = vdet(wb)[1]["werbung"], vdet(pv)[1]["provisionen"]
    if pv0:
        names = AND.join([", ".join(nm(i) for i in pv0[:-1]), nm(pv0[-1])] if len(pv0) > 1 else [nm(pv0[0])])
        pv0_txt = T(f"Praktisch keine Provisionen, zwei Jahre in Folge unter CHF 2 pro Kopf, zahlen {names}.",
                    f"Pratiquement aucune commission, moins de CHF 2 par assuré deux années de suite : {names}.",
                    f"Practically no commissions, under CHF 2 per head two years running: {names}.")
    else:
        pv0_txt = ""
    up = ", ".join(f"{nm(i)} ({ch(v(i, first), v(i, last))})" for i in grow[::-1][:3])
    down = ", ".join(f"{nm(i)} ({ch(v(i, first), v(i, last))})" for i in grow[:3] if v(i, last) < v(i, first)) or T("nur wenige", "peu de caisses", "only a few")
    if thin:
        thin_txt = T("Überdurchschnittliche Verwaltungskosten bei einer Solvenzquote unter 130&#8239;% haben " + ", ".join(nm(i) for i in thin) + ". Das heisst nicht, dass etwas falsch läuft, aber hier bleibt am wenigsten Spielraum.",
                     "Des frais administratifs supérieurs à la moyenne avec un taux de solvabilité inférieur à 130&#8239;% : " + ", ".join(nm(i) for i in thin) + ". Cela ne signifie pas que quelque chose ne va pas, mais c’est là que la marge est la plus faible.",
                     "Above-average administrative costs with a solvency ratio below 130&#8239;%: " + ", ".join(nm(i) for i in thin) + ". That does not mean anything is wrong, but this is where there is least room for manoeuvre.")
    else:
        thin_txt = T("Keine grosse Kasse kombiniert hohe Verwaltungskosten mit knappen Reserven.", "Aucune grande caisse ne cumule des frais administratifs élevés et des réserves serrées.",
                     "No large insurer combines high administrative costs with thin reserves.")
    fus_txt = T(" ² Die Zahlen stammen aus einer Zeit, als die Kasse noch unter 50'000 Versicherte hatte. Seither ist sie gewachsen oder hat mit einer anderen Kasse fusioniert.",
                " ² Les chiffres datent d’une époque où la caisse comptait moins de 50'000 assurés. Depuis, elle a grandi ou fusionné avec une autre caisse.",
                " ² The figures date from a time when the insurer had fewer than 50'000 insured persons. It has since grown or merged with another insurer.") if fus else ""
    P = "&#8239;%"
    body = f"""{crumbs_html(crumbs)}
<div class="article-badge">{T("Hintergrund", "Contexte", "Background")}</div>
<h1>{T("Was die Krankenkassen für Verwaltung, Werbung und Vermittler ausgeben", "Ce que les caisses-maladie dépensent pour l’administration, la publicité et les intermédiaires", "What health insurers spend on administration, advertising and brokers")}</h1>
<div class="article-meta">{T("Grundversicherung · Zahlen des BAG · Lesezeit: 4 Min.", "Assurance de base · chiffres de l’OFSP · lecture : 4 min", "Basic insurance · FOPH figures · reading time: 4 min")}</div>
<p class="kk-lead">{T(f"Im Schnitt kostet die Verwaltung der Grundversicherung <strong>CHF {mk[last]:.0f} pro versicherte Person und Jahr</strong> ({last}), rund {share:.0f}{P} der Prämie. Dahinter stecken grosse Unterschiede: von CHF {v(lo, last):.0f} bei {nm(lo)} bis CHF {v(hi, last):.0f} bei {nm(hi)}. Für Werbung gaben alle Kassen zusammen {vj} CHF {MARKT_WERBUNG[int(vj)]:.0f} Mio. aus, für Provisionen an Vermittler CHF {MARKT_PROVISIONEN[int(vj)]:.0f} Mio.",
  f"En moyenne, l’administration de l’assurance de base coûte <strong>CHF {mk[last]:.0f} par assuré et par an</strong> ({last}), soit environ {share:.0f}{P} de la prime. Les écarts sont importants : de CHF {v(lo, last):.0f} chez {nm(lo)} à CHF {v(hi, last):.0f} chez {nm(hi)}. En {vj}, l’ensemble des caisses a dépensé CHF {MARKT_WERBUNG[int(vj)]:.0f} mio en publicité et CHF {MARKT_PROVISIONEN[int(vj)]:.0f} mio en commissions aux intermédiaires.",
  f"On average, administering basic insurance costs <strong>CHF {mk[last]:.0f} per insured person per year</strong> ({last}), around {share:.0f}{P} of the premium. Behind that are big differences: from CHF {v(lo, last):.0f} at {nm(lo)} to CHF {v(hi, last):.0f} at {nm(hi)}. In {vj}, all insurers together spent CHF {MARKT_WERBUNG[int(vj)]:.0f}m on advertising and CHF {MARKT_PROVISIONEN[int(vj)]:.0f}m on broker commissions.")}</p>

<h2>{T("Verwaltungskosten je Kasse", "Frais administratifs par caisse", "Administrative costs per insurer")}</h2>
<p>{T(f"Kassen mit mindestens 50'000 Versicherten, pro versicherte Person und Jahr. Verwaltung {last} mit Veränderung seit {first}, Werbung und Provisionen {vj}, dazu die Solvenzquote (Reserven im Verhältnis zum gesetzlichen Minimum) und die Note im {rl}.",
  f"Caisses d’au moins 50'000 assurés, par assuré et par an. Administration {last} avec évolution depuis {first}, publicité et commissions {vj}, ainsi que le taux de solvabilité (réserves par rapport au minimum légal) et la note de la {rl}.",
  f"Insurers with at least 50'000 insured persons, per insured person per year. Administration {last} with change since {first}, advertising and commissions {vj}, plus the solvency ratio (reserves relative to the legal minimum) and the score in the {rl}.")}</p>
<div class="kk-table-wrap"><table class="kk-table"><thead><tr><th>{T("Kasse", "Caisse", "Insurer")}</th><th class="num">{T("Verwaltung", "Administration", "Administration")} {last}</th><th class="num">{T("seit", "depuis", "since")} {first}</th><th class="num">{T("Werbung", "Publicité", "Advertising")} {vj}</th><th class="num">{T("Provisionen", "Commissions", "Commissions")} {vj}</th><th class="num">{T("Solvenz", "Solvabilité", "Solvency")}</th><th class="num">{T("Preistreue", "Constance", "Consistency")}</th></tr></thead><tbody>{trs}</tbody></table></div>
<p class="kk-note">{T("¹ Ohne eigenes Personal: Die Kasse kauft ihre Verwaltung als Gebühr bei einer Konzern- oder Partnerfirma ein. Der Gesamtbetrag ist vergleichbar, wie er sich auf die Kassen eines Konzerns verteilt, bestimmt aber der Konzern.",
  "¹ Sans personnel propre : la caisse achète son administration sous forme de frais à une société du groupe ou partenaire. Le montant total est comparable, mais c’est le groupe qui décide de sa répartition entre ses caisses.",
  "¹ No staff of its own: the insurer buys in its administration as a fee from a group or partner company. The total is comparable, but the group decides how it is split among its insurers.")}{fus_txt}</p>

<h2>{T("Werbung und Vermittler", "Publicité et intermédiaires", "Advertising and brokers")}</h2>
<p>{T(f"Am meisten pro Kopf für Werbung gibt {nm(wb)} aus: CHF {wbv:.0f} pro versicherte Person ({vj}). Bei den Provisionen an Vermittler liegt {nm(pv)} vorne, mit CHF {pvv:.0f} pro Kopf. {pv0_txt}",
  f"C’est {nm(wb)} qui dépense le plus en publicité par assuré : CHF {wbv:.0f} par assuré ({vj}). Pour les commissions aux intermédiaires, {nm(pv)} est en tête avec CHF {pvv:.0f} par assuré. {pv0_txt}",
  f"{nm(wb)} spends the most on advertising per head: CHF {wbv:.0f} per insured person ({vj}). For broker commissions {nm(pv)} leads, with CHF {pvv:.0f} per head. {pv0_txt}")}</p>
<p>{T("In der Grundversicherung ist die Provision gedeckelt: höchstens CHF 70 pro Abschluss, seit 1. September 2024 verbindlich für alle Kassen. Das zeigt sich in den Zahlen:",
  "Dans l’assurance de base, la commission est plafonnée : CHF 70 au maximum par contrat, obligatoire pour toutes les caisses depuis le 1er septembre 2024. Cela se voit dans les chiffres :",
  "In basic insurance, commission is capped: at most CHF 70 per policy, binding on all insurers since 1 September 2024. This shows in the figures:")}</p>
<div class="kk-table-wrap"><table class="kk-table" style="min-width:0;"><thead><tr><th>{T("Jahr", "Année", "Year")}</th><th class="num">{T("Werbung, Mio. CHF", "Publicité, mio CHF", "Advertising, CHF m")}</th><th class="num">{T("Provisionen, Mio. CHF", "Commissions, mio CHF", "Commissions, CHF m")}</th></tr></thead><tbody>{mrows}</tbody></table></div>
<p>{T(f'Bei der Zusatzversicherung ist das anders, dort sind bis zu 16 Monatsprämien Provision erlaubt. Mehr dazu: <a href="{i18n.url("blog/provisionen-zusatzversicherung")}">Warum dein Berater dir die Zusatzversicherung verkaufen will</a>.',
  f'Pour l’assurance complémentaire, c’est différent : jusqu’à 16 primes mensuelles de commission sont autorisées. En savoir plus : <a href="{i18n.url("blog/provisionen-zusatzversicherung")}">pourquoi votre conseiller veut vous vendre une assurance complémentaire</a>.',
  f'Supplementary insurance is different: commissions of up to 16 monthly premiums are allowed there. More: <a href="{i18n.url("blog/provisionen-zusatzversicherung")}">why your adviser wants to sell you supplementary insurance</a>.')}</p>

<h2>{T(f"Wer seit {first} zulegt und wer spart", f"Qui augmente depuis {first} et qui économise", f"Who has grown since {first} and who saves")}</h2>
<p>{T(f"Den stärksten Anstieg der Verwaltungskosten pro Kopf haben {up}. Gesenkt haben sie {down}. Der Schnitt aller Kassen stieg von CHF {mk[first]:.0f} auf CHF {mk[last]:.0f}.",
  f"Les plus fortes hausses des frais administratifs par assuré : {up}. Les ont réduits : {down}. La moyenne de toutes les caisses est passée de CHF {mk[first]:.0f} à CHF {mk[last]:.0f}.",
  f"The largest increases in administrative costs per head: {up}. Reduced them: {down}. The average of all insurers rose from CHF {mk[first]:.0f} to CHF {mk[last]:.0f}.")}</p>

<h2>{T("Verwaltung und Reserven zusammen", "Administration et réserves ensemble", "Administration and reserves together")}</h2>
<p>{T(f"Die Reserven sind das Polster, mit dem eine Kasse teure Jahre abfedert, ohne gleich die Prämien zu erhöhen. {thin_txt} Die Reserven fliessen mit 10{P} in die Preistreue-Note ein, die Verwaltungskosten nicht, weil sie schon im Preis stecken.",
  f"Les réserves sont le coussin qui permet à une caisse d’amortir les années coûteuses sans augmenter aussitôt les primes. {thin_txt} Les réserves comptent pour 10{P} dans la note de constance, les frais administratifs non, car ils sont déjà compris dans le prix.",
  f"Reserves are the cushion an insurer uses to absorb expensive years without raising premiums straight away. {thin_txt} Reserves count for 10{P} of the price consistency score; administrative costs do not, because they are already in the price.")}</p>

<h2>{T("Was heisst das für dich?", "Qu’est-ce que cela signifie pour vous ?", "What does this mean for you?")}</h2>
<p>{T(f"Die Verwaltung macht nur einen kleinen Teil der Prämie aus, rund {share:.0f}{P}. Zwischen der schlanksten und der teuersten grossen Kasse liegen CHF {v(hi, last) - v(lo, last):.0f} im Jahr. Beim Prämienvergleich sind die Unterschiede meist viel grösser. Entscheidend bleibt, was du bezahlst und ob die Kasse über die Jahre günstig bleibt.",
  f"L’administration ne représente qu’une petite part de la prime, environ {share:.0f}{P}. Entre la grande caisse la plus légère et la plus chère, l’écart est de CHF {v(hi, last) - v(lo, last):.0f} par an. En comparant les primes, les différences sont généralement bien plus grandes. Ce qui compte, c’est ce que vous payez et si la caisse reste avantageuse au fil des ans.",
  f"Administration is only a small part of the premium, around {share:.0f}{P}. Between the leanest and the most expensive large insurer the gap is CHF {v(hi, last) - v(lo, last):.0f} a year. Premium differences are usually much bigger. What matters is what you pay and whether the insurer stays cheap over the years.")}</p>
<a class="kk-cta" href="{i18n.url("home")}#kk-rechner">{T("Prämien vergleichen", "Comparer les primes", "Compare premiums")} &rarr;</a>

<p class="kk-note">{T(f"Quellen: BAG, Aufsichtsdaten der obligatorischen Krankenpflegeversicherung (Verwaltungsaufwand je versicherte Person, {first} bis {last}); BAG, Auswertungen Verwaltungskosten (Werbeaufwand und Provisionen, Jahresrechnung definitiv {vj}); BAG über priminfo.admin.ch, Solvenzquoten per 1.1.2026. Werbung und Provisionen umfassen nur die Grundversicherung.",
  f"Sources : OFSP, données de surveillance de l’assurance obligatoire des soins (frais administratifs par assuré, {first} à {last}) ; OFSP, analyses des frais administratifs (publicité et commissions, comptes annuels définitifs {vj}) ; OFSP via priminfo.admin.ch, taux de solvabilité au 1.1.2026. La publicité et les commissions ne concernent que l’assurance de base.",
  f"Sources: FOPH, supervisory data on compulsory health insurance (administrative costs per insured person, {first} to {last}); FOPH, analyses of administrative costs (advertising and commissions, final annual accounts {vj}); FOPH via priminfo.admin.ch, solvency ratios as of 1 January 2026. Advertising and commissions cover basic insurance only.")}</p>"""
    return path, page(path, title, desc, body, [breadcrumb(crumbs)], dict(i18n.ROUTES[BLOG_VERWALTUNG_KEY]))


def write_sitemap(groups):
    """groups: Liste von ({Sprache: Pfad}, Priorität). Jede URL nennt ihre
    Gegenstücke in den anderen Sprachen (xhtml:link), wie Google es für
    mehrsprachige Seiten empfiehlt."""
    today = date.today().isoformat()
    static_pr = {"home": "1.0", "hausrat": "0.9", "methode": "0.6", "blog": "0.6"}
    items = []
    for key in i18n.STATIC:
        if key in ("impressum", "datenschutz", "kontakt"):
            continue   # bewusst nicht in der Sitemap
        alts = {l: i18n.url(key, l) for l in i18n.LANGS if (ROOT / i18n.file_for(key, l)).exists()}
        items.append((alts, static_pr.get(key, "0.7")))
    items += groups
    out = []
    for alts, pr in items:
        links = "".join(f'\n    <xhtml:link rel="alternate" hreflang="{i18n.HREFLANG[l]}" href="{SITE}{p}"/>' for l, p in alts.items())
        if len(alts) > 1 and "de" in alts:
            links += f'\n    <xhtml:link rel="alternate" hreflang="x-default" href="{SITE}{alts["de"]}"/>'
        for l, p in alts.items():
            out.append(f"  <url>\n    <loc>{SITE}{p}</loc>\n    <lastmod>{today}</lastmod>\n    <priority>{pr}</priority>"
                       f"{links if len(alts) > 1 else ''}\n  </url>")
    (ROOT / "sitemap.xml").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?>\n<!-- generiert von scripts/build_kk_pages.py -->\n'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">\n'
        + "\n".join(out) + '\n</urlset>\n', encoding="utf-8")


def write_llms(n_insurers, nat):
    kantone = "\n".join(f"- [Krankenkasse {name}]({SITE}/krankenkasse/{slug}/)"
                         for name, slug in sorted(CANTONS.values()))
    (ROOT / "llms.txt").write_text(f"""# abovergleich.com

> Unabhängiger Krankenkassen-Vergleich für die Schweiz, basierend auf den offiziellen Prämiendaten des Bundesamts für Gesundheit (BAG). Dazu Hausrat und Haftpflicht; Handy- und Internet-Abos auf der Schwesterseite handyabo.com.

<!-- generiert von scripts/build_kk_pages.py -->

## Über uns

abovergleich.com hilft beim Sparen auf der Grundversicherung. Die Leistungen sind bei allen Kassen gesetzlich gleich, nur der Preis unterscheidet sich.

- Keine Broker, keine Anrufe, keine Weitergabe von Nutzerdaten
- Alle {n_insurers} Kassen mit Grundversicherung {YEAR}, alle 26 Kantone, alle Prämienregionen
- Prämien {YEAR} und {PREV} nebeneinander: Veränderung je Kasse, Tarif und Kanton

## Hauptseiten

- [Krankenkassen-Vergleich {YEAR}]({SITE}/): Prämienrechner nach PLZ, Jahrgang, Franchise und Unfalldeckung. Vergleich mit der eigenen Kasse inklusive Veränderung zum Vorjahr.
- [Krankenkassenprämien {YEAR}]({SITE}/krankenkassenpraemien-{YEAR}/): Auswertung, wie stark jede Kasse und jeder Kanton aufschlägt. BAG: +{BAG_OFFICIAL['change_pct']:.1f}% mittlere Prämie; Standardmodell nach unserer Auswertung {nat:+.1f}%.
- [Günstigste Krankenkasse nach Kanton]({SITE}/krankenkasse/): Übersicht aller 26 Kantone.
- [Alle Krankenkassen {YEAR}]({SITE}/kasse/): Prämienveränderung je Kasse, Seite pro Kasse mit Kantonen, Modellen und Kündigungsadresse.
- [Preistreue-Rating {YEAR}]({SITE}/krankenkassen-rating/): Note 0 bis 10 je Kasse aus BAG-Prämien seit 2020: Preis, Konstanz unter den günstigsten, Aufschläge, Rabatt-Treue neuer Sparmodelle, Tarif-Bestand, Reserven.
- [Preistreue-Award {YEAR}]({SITE}/krankenkassen-rating/award/): Gesamtsieger, Kategoriensieger und Sieger je Kanton, mit Regeln.
- [Verwaltungskosten der Krankenkassen]({SITE}{BLOG_VERWALTUNG}): Verwaltung, Werbung und Vermittler-Provisionen je Kasse (BAG), mit Reserven und Preistreue-Note.
- [Krankenkasse kündigen]({SITE}/krankenkasse-kuendigen/): Frist {deadline()}, Kündigungs-Editor mit Unterschrift und PDF, Kündigungsweg (Mail oder Post) und Adresse jeder Kasse laut BAG.
- [Hausrat & Haftpflicht]({SITE}/hausratversicherung/): Bedarfsrechner und Anbieter-Vergleich.
- [Unsere Methode]({SITE}/methode/): Wie wir vergleichen und warum wir keine Telefonnummern verlangen.

## Kantone

{kantone}

## Ratgeber

- [HMO, Telmed oder Hausarzt? Alle Modelle erklärt]({SITE}/blog/hmo-telmed-hausarzt-erklaert/)
- [Welche Franchise ist die beste?]({SITE}/blog/beste-franchise-schweiz/)
- [Unfallversicherung Schweiz & Ausland]({SITE}/blog/unfallversicherung-schweiz-ausland/)
- [Warum dein Berater dir die Zusatzversicherung verkaufen will]({SITE}/blog/provisionen-zusatzversicherung/)
- [Krankenkasse mit 26: Warum die Prämie so stark steigt]({SITE}/blog/krankenkasse-mit-26/)
- [Krankenkassen-Rating: Welche Kasse ist dauerhaft günstig?]({SITE}/krankenkassen-rating/)

## En français

- [Comparatif des caisses-maladie {YEAR}]({SITE}/fr/): calculateur de primes par NPA, année de naissance, franchise et couverture accidents.
- [Primes {YEAR} par canton]({SITE}/fr/caisse-maladie/) · [Toutes les caisses]({SITE}/fr/caisses/) · [Analyse des primes {YEAR}]({SITE}/fr/primes-caisse-maladie-{YEAR}/)
- [Notation Constance des primes {YEAR}]({SITE}/fr/constance-des-primes/) et [Prix Constance des primes {YEAR}]({SITE}/fr/constance-des-primes/prix/)
- [Résilier sa caisse-maladie]({SITE}/fr/resilier-caisse-maladie/): délai, lettre de résiliation en français avec signature, adresses de toutes les caisses.

## In English

- [Swiss health insurance comparison {YEAR}]({SITE}/en/): premium calculator by postcode, year of birth, deductible and accident cover.
- [Premiums {YEAR} by canton]({SITE}/en/health-insurance/) · [All insurers]({SITE}/en/insurers/) · [Premium analysis {YEAR}]({SITE}/en/health-insurance-premiums-{YEAR}/)
- [Price Consistency Rating {YEAR}]({SITE}/en/health-insurance-rating/) and [Price Consistency Award {YEAR}]({SITE}/en/health-insurance-rating/award/)
- [Cancel Swiss health insurance]({SITE}/en/cancel-health-insurance/): deadline, cancellation letter in German or French, addresses of all insurers.

## Schwesterseite

- [Handy-Abo Vergleich](https://handyabo.com/)
- [Internet-Abo Vergleich](https://handyabo.com/internet/)

## Datenquellen

- Prämien: Bundesamt für Gesundheit (BAG), opendata.swiss, Prämienjahre {PREV} und {YEAR}
- Kassennamen: BAG-Verzeichnis der zugelassenen Krankenversicherer
- Aktualisierung: jährlich Ende September nach Veröffentlichung der neuen Prämien
- Kündigung Grundversicherung: bis {deadline()} bei der Kasse eingetroffen

## Kontakt

- E-Mail: hello@handyabo.com
""", encoding="utf-8")


def bust_assets():
    """Hängt an geteilte CSS/JS-Dateien eine Prüfsumme (?v=…), auf allen Seiten.
    Ändert sich die Datei, ändert sich die URL, und Browser laden sie neu."""
    import hashlib
    assets = {}
    for rel in ("styles/shared.css", "js/combobox.js", "js/kuendigung.js", "js/rechner.js", "rating-daten.json",
                "favicon.svg", "favicon.ico", "apple-touch-icon.png"):
        f = ROOT / rel
        if f.exists():
            assets["/" + rel] = hashlib.md5(f.read_bytes()).hexdigest()[:8]
    for page_file in ROOT.glob("**/index.html"):
        if any(part in ("scripts", "supabase", "docs", "node_modules") for part in page_file.parts):
            continue
        t = page_file.read_text(encoding="utf-8")
        new = t
        for url, h in assets.items():
            new = re.sub(re.escape(url) + r'(\?v=[0-9a-f]+)?"', f'{url}?v={h}"', new)
        if new != t:
            page_file.write_text(new, encoding="utf-8")


def write(path, content):
    target = ROOT / path.strip("/") / "index.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def main():
    cur, prev = load_year(YEAR), load_year(PREV)
    # ohne Unfall: Beispielperson der Kassenseiten
    nu_rows = load_year(YEAR, accident=False)
    nu = {"rows": nu_rows, "prev_idx": index_rows(load_year(PREV, accident=False)), "by_canton": defaultdict(list)}
    for r in nu_rows:
        nu["by_canton"][r["canton"]].append(r)
    bestand = load_bestand()
    regions = load_regions()
    for c, regs in regions.items():
        for reg, gem in regs.items():
            REGION_GEMEINDEN[(c, reg)] = gem
    prev_idx = index_rows(prev)
    cantons, insurers, nat = analyse(cur, prev, bestand)
    kv = kv_verzeichnis.load()
    for i in sorted({r["insurer_id"] for r in cur}):
        KASSE_SLUG[i] = slugify(INSURER_NAMES[str(i)])

    by_canton_cur, by_canton_prev = defaultdict(list), defaultdict(list)
    for r in cur:
        by_canton_cur[r["canton"]].append(r)
    for r in prev:
        by_canton_prev[r["canton"]].append(r)

    # Kasse x Kanton für die Kantonsseiten
    s_cur, s_prev = standard_premiums(cur), standard_premiums(prev)
    ic = defaultdict(list)
    for (c, reg, i), p in s_cur.items():
        if (c, reg, i) in s_prev:
            ic[(c, i)].append((p, p / s_prev[(c, reg, i)] - 1))

    global RATING
    import build_rating
    RATING = build_rating.compute_all()
    client = build_rating.client_json(RATING)
    client["slug"] = {str(i): s for i, s in KASSE_SLUG.items()}   # Rechner verlinkt jede Kasse auf ihre Analyse
    (ROOT / "rating-daten.json").write_text(json.dumps(client, ensure_ascii=False,
                                                       separators=(",", ":")), encoding="utf-8")

    for c in CANTONS:
        MAIN_REGION[c] = main_region(by_canton_cur[c], c)
    global AWARDS
    adm = RATING["verwaltung"]["kassen"]
    adm_cost = {int(k): v[max(v)]["verwaltung"] for k, v in adm.items() if v}
    AWARDS = build_awards.compute(RATING, YEAR, CANTONS, MAIN_REGION, adm_cost)
    write_award_badges()
    set_home(bestand)
    jojo = jojo_analysis()
    JOJO_ROWS[:] = (jojo.get(f"{PREV}-{YEAR}") or {}).get("rows") or []

    # Daten, die nicht von der Sprache abhängen
    cheapest, ins_by_c = {}, {}
    for c in CANTONS:
        ins_by_c[c] = [{"name": INSURER_NAMES[str(i)], "premium": sum(p for p, _ in v) / len(v),
                        "change": sum(x for _, x in v) / len(v) * 100}
                       for (cc, i), v in ic.items() if cc == c]
        cheapest[c] = ranking(by_canton_cur[c], c, MAIN_REGION[c], 2500, prev_idx, n=1)[0]
    model_counts = defaultdict(int)
    for c in CANTONS:
        reg = main_region(by_canton_cur[c], c)
        best = min((r for r in by_canton_cur[c] if r["region"] == reg and r["franchise"] == 300), key=lambda r: r["premium"])
        model_counts[best["model_type"]] += 1
    top3_cur = top3_counts(cur, by_canton_cur)
    prev2 = load_year(YEAR - 2)
    by_canton_prev2 = defaultdict(list)
    for r in prev2:
        by_canton_prev2[r["canton"]].append(r)
    _, ins_prev, nat_prev = analyse(prev, prev2, bestand)
    top3_prev, top3_prev2 = top3_counts(prev, by_canton_prev), top3_counts(prev2, by_canton_prev2)
    n_insurers = len({r["insurer_id"] for r in cur})

    groups = {}   # Schlüssel -> {Sprache: Pfad}, für die Sitemap
    def add(key, lang, path, pr="0.8"):
        groups.setdefault(key, ({}, pr))[0][lang] = path

    for lang in i18n.LANGS:
        i18n.set_lang(lang)
        for c in CANTONS:
            path, content = canton_page(c, by_canton_cur[c], prev_idx, cantons, ins_by_c[c], regions)
            write(path, content)
            add(("canton", c), lang, path)
        for i in KASSE_SLUG:
            path, content = kasse_page(i, cur, by_canton_cur, prev_idx, insurers, ic, top3_cur, kv, nu)
            write(path, content)
            add(("kasse", i), lang, path)
        for key, fn in (("cantons", lambda: hub_page(cantons, cheapest)),
                        ("report", lambda: report_page(cantons, insurers, nat, model_counts, jojo)),
                        ("kassen", lambda: kasse_hub(insurers, top3_cur)), ("kuendigen", lambda: kuendigen_page(kv)),
                        ("rating", lambda: rating_page(RATING)), ("award", award_page), ("blogv", blog_verwaltung_page)):
            path, content = fn()
            write(path, content)
            add(key, lang, path)
        path, content = pickup_page()   # nicht in die Sitemap
        write(path, content)

        # Startseite der Sprache: Insights-Block ersetzen
        idx = ROOT / i18n.file_for("home", lang)
        if idx.exists():
            s_idx = idx.read_text(encoding="utf-8")
            block = insights_block(cantons, insurers, nat, top3_prev, top3_cur, ins_prev, nat_prev, top3_prev2, jojo)
            new, n = re.subn(r"<!-- INSIGHTS:START.*?<!-- INSIGHTS:END -->", lambda _: block, s_idx, flags=re.S)
            if n != 1:
                sys.exit(f"Insights-Marker in {idx} nicht gefunden")
            new = re.sub(r'(class="[^"]*insurer-count[^"]*">)\d+(<)', rf"\g<1>{n_insurers}\g<2>", new)
            idx.write_text(new, encoding="utf-8")
        meth = ROOT / i18n.file_for("methode", lang)
        if meth.exists():
            ms = meth.read_text(encoding="utf-8")
            meth.write_text(re.sub(r'(class="[^"]*insurer-count[^"]*">)\d+(<)', rf"\g<1>{n_insurers}\g<2>", ms), encoding="utf-8")
    i18n.set_lang("de")
    write_llms(n_insurers, nat)

    (ROOT / "premium-insights.json").write_text(json.dumps({
        "generated": date.today().isoformat(), "data_year": YEAR, "previous_year": PREV,
        "bag_official": BAG_OFFICIAL, "national_change_standard_pct": round(nat, 2),
        "national_change_standard_pct_prev": round(nat_prev, 2),
        "vorjahressieger": {k: ({kk: vv for kk, vv in v.items() if kk != "rows"} if isinstance(v, dict) else v) for k, v in jojo.items()},
        "cantons": {c: {k: round(v, 2) for k, v in d.items()} for c, d in cantons.items()},
        "insurers": {str(i): {**d, "change_pct": round(d["change_pct"], 2), "bestand": round(d["bestand"]),
                              "change_pct_prev": round(ins_prev[i]["change_pct"], 2) if i in ins_prev else None}
                     for i, d in insurers.items()},
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    paths = [p for alts, _ in groups.values() for p in alts.values()]
    write_sitemap(list(groups.values()))
    site_nav.apply_static()
    try:
        import sync_handyabo
        sync_handyabo.apply()
    except (Exception, SystemExit) as err:  # handyabo nicht erreichbar: Kacheln bleiben wie sie sind
        print(f"! handyabo-Zahlen nicht aktualisiert: {err}")
    bust_assets()
    print(f"✓ {len(paths)} Seiten, national {nat:+.2f}% (Standard F300), "
          f"Kantone {min(v['change_pct'] for v in cantons.values()):+.1f} bis {max(v['change_pct'] for v in cantons.values()):+.1f}%")


if __name__ == "__main__":
    main()
