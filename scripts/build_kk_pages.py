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

YEAR = 2027
PREV = YEAR - 1
DEADLINE = "30. November 2026"   # Kündigung Grundversicherung, Eingang bei der Kasse
PUBLISHED = "2026-09-30"

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

MODEL_LABEL = {
    "standard": "Standard", "family_doctor": "Hausarzt", "hmo": "HMO",
    "telmed": "Telmed", "diverse": "Alternativ", "apotheke": "Apotheke",
}

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
        return "neu"
    s = f"{v:+.1f}" if sign else f"{v:.1f}"
    return s.replace("-", "−") + " %"


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


def page(path, title, description, body, jsonld):
    url = f"{SITE}{path}"
    if len(description) > 160 or len(title) > 70:
        print(f"! {path}: Titel {len(title)} / Beschreibung {len(description)} Zeichen, Google kürzt ab")
    ld = "\n".join(f'<script type="application/ld+json">\n{json.dumps(x, ensure_ascii=False, indent=1)}\n</script>' for x in jsonld)
    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<!-- generiert von scripts/build_kk_pages.py, nicht von Hand bearbeiten -->
<title>{e(title)}</title>
<meta name="description" content="{e(description)}">
<link rel="canonical" href="{url}">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<link rel="alternate icon" href="/favicon.ico">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<meta name="robots" content="index, follow">
<meta property="og:type" content="article">
<meta property="og:url" content="{url}">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(description)}">
<meta property="og:site_name" content="abovergleich.com">
<meta property="og:locale" content="de_CH">
<meta property="og:image" content="{SITE}/og-image.png">
<meta name="twitter:card" content="summary_large_image">
{ld}
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Inter:wght@300;400;500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/styles/shared.css">
<style>{PAGE_CSS}</style>
</head>
<body>

{site_nav.nav_html(path)}

<article class="article kk-page">
{body}
</article>

<footer>
  <div class="footer-inner">
    <div class="footer-logo">abo<span>vergleich</span>.com</div>
    <div class="footer-note">Unabh&auml;ngiger Vergleich f&uuml;r die Schweiz. Pr&auml;mien: Bundesamt f&uuml;r Gesundheit (BAG).</div>
    <div class="footer-links">
      <a href="/krankenkasse/">Kantone</a>
      <a href="/kasse/">Kassen</a>
      <a href="/krankenkasse-kuendigen/">K&uuml;ndigen</a>
      <a href="/krankenkassenpraemien-{YEAR}/">Pr&auml;mien {YEAR}</a>
      <a href="/krankenkassen-rating/">Rating</a>
      <a href="/methode/">Methode</a>
      <a href="/impressum/">Impressum</a>
      <a href="/datenschutz/">Datenschutz</a>
    </div>
  </div>
</footer>

{ANALYTICS}
</body>
</html>
"""


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
    head = "<tr><th>#</th><th>Kasse</th><th class=\"num\">Prämie / Mt.</th>" \
           f"<th class=\"num\">vs. {PREV}</th></tr>"
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
        return "ganzer Kanton"
    label = f"Prämienregion {reg[-1]}"
    gem = REGION_GEMEINDEN.get((canton, reg), [])
    if 0 < len(gem) <= 3:
        label += f" ({', '.join(gem)})"
    return label


# ── Seiten ─────────────────────────────────────────────────────────────────

def canton_page(c, cur, prev_idx, cantons, insurers_c, regions):
    name, slug = CANTONS[c]
    path = f"/krankenkasse/{slug}/"
    rows_c = [r for r in cur if r["canton"] == c]
    regs = sorted({r["region"] for r in rows_c})
    info = cantons[c]
    main = main_region(rows_c, c)

    any_2500 = ranking(rows_c, c, main, 2500, prev_idx)
    std_300 = ranking(rows_c, c, main, 300, prev_idx, standard_only=True, n=40)
    cheapest = any_2500[0]
    spread = (std_300[-1]["premium"] - std_300[0]["premium"]) * 12 if len(std_300) > 1 else 0
    where = f"in der {region_label(main, len(regs), c)}" if len(regs) > 1 else "im ganzen Kanton"

    title = f"Günstigste Krankenkasse {name} {YEAR}: Prämien im Vergleich"
    if len(title) > 65:
        title = f"Krankenkasse {name} {YEAR}: die günstigsten Prämien"
    desc = (f"Krankenkasse {name} {YEAR}: ab CHF {chf(cheapest['premium'])} ({cheapest['insurer']}, Franchise 2'500), "
            f"Prämien im Schnitt {pct(info['change_pct'])}. Alle Kassen, BAG-Daten, Preistreue-Rating.")

    parts = [crumbs_html([("Krankenkassen-Vergleich", "/"), ("Kantone", "/krankenkasse/"), (name, path)])]
    parts.append(f'<div class="article-badge">Prämien {YEAR}</div>')
    parts.append(f"<h1>Krankenkasse {e(name)}: die günstigsten Prämien {YEAR}</h1>")
    parts.append(f'<div class="article-meta">Offizielle Prämien des BAG für {YEAR} · Stand {date.fromisoformat(PUBLISHED).strftime("%d.%m.%Y")}</div>')
    parts.append(
        f'<p class="kk-lead">Die günstigste Grundversicherung für Erwachsene im Kanton {e(name)} kostet {YEAR} '
        f'<strong>CHF {chf(cheapest["premium"])} pro Monat</strong> ({e(cheapest["insurer"])}, {MODEL_LABEL[cheapest["model"]]}, '
        f'Franchise 2\'500, {where}). Die Leistungen sind bei allen Kassen gesetzlich gleich, du zahlst nur einen anderen Preis.</p>')
    parts.append(f"""<div class="kk-facts">
  <div class="kk-fact"><div class="kk-fact-val">{pct(info['change_pct'])}</div><div class="kk-fact-label">Prämienveränderung {e(name)} {PREV} auf {YEAR} (Standardmodell, Franchise 300)</div></div>
  <div class="kk-fact"><div class="kk-fact-val">CHF {chf(info['avg_standard'], 0)}</div><div class="kk-fact-label">Durchschnittliche Standardprämie pro Monat, Franchise 300</div></div>
  <div class="kk-fact"><div class="kk-fact-val">CHF {chf(spread, 0)}</div><div class="kk-fact-label">pro Jahr zwischen teuerster und günstigster Kasse, gleiches Modell und gleiche Franchise</div></div>
</div>""")
    parts.append(f'<a class="kk-cta" href="/#kk-rechner">Deine Prämie mit PLZ berechnen &rarr;</a>')

    parts.append(f"<h2>Die 10 günstigsten Krankenkassen im Kanton {e(name)} {YEAR}</h2>")
    parts.append(f"<p>Erwachsene ab 26, Franchise CHF 2'500, mit Unfalldeckung, {where}. Pro Kasse der günstigste Tarif. "
                 f"Die Veränderung vergleicht denselben Tarif mit {PREV}.</p>")
    parts.append(rank_table(any_2500))

    parts.append(f"<h2>Standardmodell mit freier Arztwahl</h2>")
    parts.append(f"<p>Wer keine Einschränkung bei der Arztwahl will: die günstigsten Kassen im Standardmodell, "
                 f"Franchise CHF 300, {where}.</p>")
    parts.append(rank_table(std_300[:10], show_model=False))

    if len(regs) > 1:
        parts.append(f"<h2>Prämienregionen im Kanton {e(name)}</h2>")
        parts.append(f"<p>Der Kanton {e(name)} ist in {len(regs)} Prämienregionen aufgeteilt. Die Tabellen oben gelten für "
                     f"{region_label(main, len(regs), c)}. In den anderen Regionen ist die günstigste Kasse:</p><ul>")
        for reg in regs:
            if reg == main:
                continue
            best = ranking(rows_c, c, reg, 2500, prev_idx, n=1)[0]
            parts.append(f"<li><strong>{region_label(reg, len(regs), c)}:</strong> {e(best['insurer'])} "
                         f"({MODEL_LABEL[best['model']]}), CHF {chf(best['premium'])} pro Monat</li>")
        parts.append("</ul>")
        for reg in regs:
            gem = regions.get(c, {}).get(reg)
            if gem:
                parts.append(f'<details class="kk-gemeinden"><summary>Gemeinden in {region_label(reg, len(regs))} ({len(gem)})</summary>'
                             f'<p>{e(", ".join(gem))}</p></details>')

    parts.append(rating_canton_block(c, main))

    ranked = sorted(insurers_c, key=lambda x: x["change"])
    if len(ranked) >= 4:
        parts.append(f"<h2>So stark schlägt jede Kasse im Kanton {e(name)} auf</h2>")
        parts.append(f"<p>Veränderung der Standardprämie von {PREV} auf {YEAR}, Franchise 300, Erwachsene, Mittel über die Prämienregionen. Wer am wenigsten aufschlägt, steht oben. "
                     f"Durchschnitt im Kanton: <strong>{pct(info['change_pct'])}</strong>.</p>")
        rows_html = "".join(
            f'<tr><td><strong>{e(x["name"])}</strong></td><td class="num">CHF {chf(x["premium"], 0)}</td>'
            f'<td class="num {"kk-up" if x["change"] > 0 else "kk-down"}">{pct(x["change"])}</td></tr>'
            for x in ranked)
        parts.append(f'<div class="kk-table-wrap"><table class="kk-table"><thead><tr><th>Kasse</th>'
                     f'<th class="num">Ø Standard {YEAR}</th><th class="num">vs. {PREV}</th></tr></thead>'
                     f'<tbody>{rows_html}</tbody></table></div>')

    qa = [
        (f"Welche Krankenkasse ist {YEAR} im Kanton {name} am günstigsten?",
         f"Für Erwachsene mit Franchise 2'500 und Unfalldeckung ist {cheapest['insurer']} "
         f"({MODEL_LABEL[cheapest['model']]}) mit CHF {chf(cheapest['premium'])} pro Monat am günstigsten, {where}. "
         f"Im Standardmodell mit Franchise 300 ist es {std_300[0]['insurer']} mit CHF {chf(std_300[0]['premium'])}."),
        (f"Wie stark steigen die Krankenkassenprämien {YEAR} im Kanton {name}?",
         f"Die Standardprämie für Erwachsene mit Franchise 300 steigt im Kanton {name} im Schnitt um "
         f"{pct(info['change_pct'])}, gewichtet nach Versichertenzahl der Kassen. Schweizweit steigt die mittlere "
         f"Prämie laut BAG um {BAG_OFFICIAL['change_pct']:.1f} Prozent."),
        (f"Bis wann kann ich die Krankenkasse für {YEAR} wechseln?",
         f"Die Kündigung der Grundversicherung muss bis am {DEADLINE} bei deiner Kasse eingetroffen sein. "
         f"Die neue Kasse muss dich ohne Gesundheitsfragen aufnehmen, der Wechsel gilt ab 1. Januar {YEAR}."),
    ]
    parts.append('<div class="kk-faq"><h2>Häufige Fragen</h2>')
    for q, a in qa:
        parts.append(f"<h3>{e(q)}</h3><p>{e(a)}</p>")
    parts.append("</div>")
    parts.append(f'<p class="kk-note">Quelle: Bundesamt für Gesundheit (BAG), Prämien {YEAR} und {PREV} '
                 f'(<a href="https://opendata.swiss/de/dataset/health-insurance-premiums">opendata.swiss</a>). '
                 f'Angaben ohne Gewähr. So rechnen wir: <a href="/krankenkassenpraemien-{YEAR}/#methode">Methode</a>. '
                 f'Alle Kantone: <a href="/krankenkasse/">Übersicht</a>.</p>')

    jsonld = [breadcrumb([("Krankenkassen-Vergleich", "/"), ("Kantone", "/krankenkasse/"), (name, path)]), faq(qa)]
    return path, page(path, title, desc, "\n".join(parts), jsonld)


def hub_page(cantons, cheapest_by_canton):
    path = "/krankenkasse/"
    title = f"Günstigste Krankenkasse {YEAR} nach Kanton: alle 26 Kantone"
    desc = (f"Krankenkassenprämien {YEAR} für alle 26 Kantone: günstigste Kasse, durchschnittliche Standardprämie "
            f"und Veränderung zu {PREV}. Offizielle BAG-Daten.")
    rows = []
    for c, (name, slug) in sorted(CANTONS.items(), key=lambda x: x[1][0]):
        ch = cheapest_by_canton[c]
        reg = (RATING or {}).get("regions", {}).get(f"{c}|{MAIN_REGION.get(c)}", {})
        top = max(reg.items(), key=lambda x: x[1]["note"] or 0, default=None)
        durable = (f'{e(INSURER_NAMES[str(top[0])])}<span class="sub">Note {note_fmt(top[1]["note"])}</span>' if top else "–")
        rows.append(
            f'<tr><td><a href="/krankenkasse/{slug}/"><strong>{e(name)}</strong></a></td>'
            f'<td>{e(ch["insurer"])}<span class="sub">CHF {chf(ch["premium"])}, Franchise 2\'500</span></td>'
            f'<td>{durable}</td>'
            f'<td class="num">CHF {chf(cantons[c]["avg_standard"], 0)}</td>'
            f'<td class="num kk-up">{pct(cantons[c]["change_pct"])}</td></tr>')
    body = [
        crumbs_html([("Krankenkassen-Vergleich", "/"), ("Kantone", path)]),
        f'<div class="article-badge">Prämien {YEAR}</div>',
        f"<h1>Günstigste Krankenkasse {YEAR} in jedem Kanton</h1>",
        f'<div class="article-meta">Offizielle Prämien des BAG · alle 26 Kantone</div>',
        f"<p class=\"kk-lead\">Wie teuer die Grundversicherung ist, hängt vor allem vom Wohnort ab. "
        f"Hier siehst du für jeden Kanton die günstigste Kasse {YEAR}, die durchschnittliche Standardprämie und wie stark sie steigt.</p>",
        f'<a class="kk-cta" href="/#kk-rechner">Prämie für deine PLZ berechnen &rarr;</a>',
        f'<div class="kk-table-wrap"><table class="kk-table"><thead><tr><th>Kanton</th><th>Günstigste Kasse</th><th>Dauerhaft günstig</th>'
        f'<th class="num">Ø Standard</th><th class="num">vs. {PREV}</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>',
        f'<p class="kk-note">Günstigste Kasse: Erwachsene, Franchise 2\'500, mit Unfall, alle Modelle, Hauptregion des Kantons. '
        f'Dauerhaft günstig: beste Note im <a href="{RATING_PATH}">Preistreue-Rating</a> in der Hauptregion. '
        f'Ø Standard und Veränderung: Standardmodell, Franchise 300, gewichtet nach Versichertenzahl. '
        f'Details zur Rechnung: <a href="/krankenkassenpraemien-{YEAR}/#methode">Methode</a>.</p>',
    ]
    jsonld = [breadcrumb([("Krankenkassen-Vergleich", "/"), ("Kantone", path)])]
    return path, page(path, title, desc, "\n".join(body), jsonld)


def report_page(cantons, insurers, nat, model_counts, jojo):
    path = f"/krankenkassenpraemien-{YEAR}/"
    by_change = sorted(cantons.items(), key=lambda x: -x[1]["change_pct"])
    big = sorted([x for x in insurers.values() if x["bestand"] >= MIN_BESTAND_RANKING], key=lambda x: x["change_pct"])
    title = f"Krankenkassenprämien {YEAR}: So stark steigen sie in deinem Kanton"
    desc = (f"Prämien {YEAR}: +{BAG_OFFICIAL['change_pct']:.1f}% im Schnitt (BAG). Unsere Auswertung aller Kassen und "
            f"Kantone: wer am stärksten aufschlägt, wer günstig bleibt, und bis wann du wechseln kannst.")
    hi, lo = by_change[0], by_change[-1]
    canton_rows = "".join(
        f'<tr><td><a href="/krankenkasse/{CANTONS[c][1]}/">{e(CANTONS[c][0])}</a></td>'
        f'<td class="num">CHF {chf(v["avg_standard"], 0)}</td><td class="num kk-up">{pct(v["change_pct"])}</td></tr>'
        for c, v in by_change)
    ins_rows = "".join(
        f'<tr><td><strong>{e(x["name"])}</strong><span class="sub">{x["cantons"]} Kantone, '
        f'{chf(x["bestand"] / 1000, 0)}k Versicherte</span></td>'
        f'<td class="num {"kk-up" if x["change_pct"] > 0 else "kk-down"}">{pct(x["change_pct"])}</td></tr>'
        for x in big)
    models = "".join(f"<li><strong>{MODEL_LABEL[m]}:</strong> {n} Kantone</li>"
                     for m, n in sorted(model_counts.items(), key=lambda x: -x[1]))
    qa = [
        (f"Wie stark steigen die Krankenkassenprämien {YEAR}?",
         f"Die mittlere Prämie steigt laut BAG um {BAG_OFFICIAL['change_pct']:.1f} Prozent. Erwachsene zahlen im Schnitt "
         f"CHF {chf(BAG_OFFICIAL['adult_mean'])} pro Monat, CHF {chf(BAG_OFFICIAL['adult_delta'])} mehr als {PREV}."),
        (f"In welchem Kanton steigen die Prämien {YEAR} am stärksten?",
         f"Laut BAG im Kanton {CANTONS[BAG_OFFICIAL['max_canton'][0]][0]} (+{BAG_OFFICIAL['max_canton'][1]:.1f}%), am "
         f"schwächsten in {CANTONS[BAG_OFFICIAL['min_canton'][0]][0]} (+{BAG_OFFICIAL['min_canton'][1]:.1f}%). "
         f"Im Standardmodell mit Franchise 300 steigt die Prämie nach unserer Auswertung in {CANTONS[hi[0]][0]} am stärksten "
         f"({pct(hi[1]['change_pct'])}) und in {CANTONS[lo[0]][0]} am wenigsten ({pct(lo[1]['change_pct'])})."),
        (f"Bis wann muss ich die Krankenkasse kündigen?",
         f"Die Kündigung der Grundversicherung muss bis am {DEADLINE} bei der Kasse eingetroffen sein. "
         f"Die neue Kasse gilt dann ab 1. Januar {YEAR}."),
    ]
    body = [
        crumbs_html([("Krankenkassen-Vergleich", "/"), (f"Prämien {YEAR}", path)]),
        f'<div class="article-badge">Auswertung</div>',
        f"<h1>Krankenkassenprämien {YEAR}: wer wie stark aufschlägt</h1>",
        f'<div class="article-meta">Veröffentlicht {date.fromisoformat(PUBLISHED).strftime("%d.%m.%Y")} · Daten: BAG, Prämien {PREV} und {YEAR}</div>',
        f"<p class=\"kk-lead\">Die Krankenkassenprämien steigen {YEAR} erneut. Die mittlere Prämie legt laut Bundesamt für Gesundheit um "
        f"<strong>{BAG_OFFICIAL['change_pct']:.1f} Prozent</strong> zu (<a href=\"{BAG_OFFICIAL['source_url']}\">SRF</a>). "
        f"Wir haben die Prämien aller Kassen in allen Kantonen verglichen: Der Durchschnitt verdeckt, wie unterschiedlich die Kassen aufschlagen.</p>",
        f"""<div class="kk-facts">
  <div class="kk-fact"><div class="kk-fact-val">+{BAG_OFFICIAL['change_pct']:.1f}&#8239;%</div><div class="kk-fact-label">mittlere Prämie {YEAR} laut BAG</div></div>
  <div class="kk-fact"><div class="kk-fact-val">{pct(nat)}</div><div class="kk-fact-label">Standardmodell, Franchise 300, unsere Auswertung</div></div>
  <div class="kk-fact"><div class="kk-fact-val">{DEADLINE.replace(' 2026', '')}</div><div class="kk-fact-label">Kündigung muss bei der Kasse sein</div></div>
</div>""",
        f'<a class="kk-cta" href="/#kk-rechner">Jetzt deine Prämie {YEAR} vergleichen &rarr;</a>',
        f"<h2>Prämienveränderung {YEAR} nach Kanton</h2>",
        f"<p>Durchschnittliche Standardprämie für Erwachsene, Franchise 300, mit Unfall, gewichtet nach Versichertenzahl der Kassen. "
        f"Ein Klick auf den Kanton zeigt die günstigsten Kassen.</p>",
        f'<div class="kk-table-wrap"><table class="kk-table"><thead><tr><th>Kanton</th><th class="num">Ø Standard {YEAR}</th>'
        f'<th class="num">vs. {PREV}</th></tr></thead><tbody>{canton_rows}</tbody></table></div>',
        f"<h2>Prämienveränderung {YEAR} nach Kasse</h2>",
        f"<p>Veränderung der Standardprämie, Franchise 300, über alle Kantone gewichtet nach Versichertenzahl. "
        f"Aufgeführt sind Kassen mit mindestens {chf(MIN_BESTAND_RANKING, 0)} Versicherten. Wer am wenigsten aufschlägt, steht oben.</p>",
        f'<div class="kk-table-wrap"><table class="kk-table"><thead><tr><th>Kasse</th><th class="num">vs. {PREV}</th></tr></thead>'
        f'<tbody>{ins_rows}</tbody></table></div>',
        *jojo_html(jojo),
        f"<h2>Welches Modell ist {YEAR} am günstigsten?</h2>",
        f"<p>In wie vielen Kantonen stellt welches Modell die günstigste Prämie (Erwachsene, Franchise 300, Hauptregion)? "
        f"Das BAG teilt die Modelle ab {YEAR} neu ein: Alternativ steht für flexible Modelle, bei denen du zwischen Hausarzt, "
        f"Telmed und Apotheke wählst.</p><ul>{models}</ul>",
        '<div class="kk-faq"><h2>Häufige Fragen</h2>',
        *[f"<h3>{e(q)}</h3><p>{e(a)}</p>" for q, a in qa],
        "</div>",
        '<h2 id="methode">So rechnen wir</h2>',
        f"<p>Grundlage sind die Prämiendaten des BAG für {PREV} und {YEAR} "
        f"(<a href=\"https://opendata.swiss/de/dataset/health-insurance-premiums\">opendata.swiss</a>) und der Versichertenbestand je Kasse und Kanton. "
        f"Als Referenz nehmen wir Erwachsene ab 26, Franchise 300, mit Unfalldeckung, Standardmodell. Die Veränderung je Kasse "
        f"und Kanton ist der Mittelwert über die Prämienregionen. Durchschnitte über mehrere Kassen gewichten wir mit der Zahl "
        f"der Versicherten. Das BAG rechnet über alle Modelle und Franchisen, daher weichen unsere Werte leicht ab.</p>",
        f"<p>Veränderungen einzelner Tarife vergleichen denselben Tarif einer Kasse in beiden Jahren. "
        f"Ist ein Tarif neu, steht «neu». Die Namen der Kassen stammen aus dem "
        f"<a href=\"https://www.bag.admin.ch/de/verzeichnisse-der-zugelassenen-kranken-und-rueckversicherer\">Verzeichnis der zugelassenen Krankenversicherer</a>.</p>",
    ]
    jsonld = [breadcrumb([("Krankenkassen-Vergleich", "/"), (f"Prämien {YEAR}", path)]), faq(qa), {
        "@context": "https://schema.org", "@type": "Article",
        "headline": title, "datePublished": PUBLISHED, "dateModified": date.today().isoformat(),
        "author": {"@type": "Organization", "name": "abovergleich.com"},
        "publisher": {"@type": "Organization", "name": "abovergleich.com"},
        "mainEntityOfPage": f"{SITE}{path}", "inLanguage": "de-CH",
    }]
    return path, page(path, title, desc, "\n".join(body), jsonld)


def jojo_html(jojo):
    cur = jojo.get(f"{PREV}-{YEAR}")
    if not cur:
        return []
    prev = jojo.get(f"{YEAR - 2}-{PREV}")
    rows = "".join(
        f'<tr><td><a href="/krankenkasse/{CANTONS[x["canton"]][1]}/">{e(CANTONS[x["canton"]][0])}</a>'
        f'<span class="sub">{"Region " + x["region"][-1] if x["region"][-1] != "0" else "ganzer Kanton"}</span></td>'
        f'<td><strong>{e(x["insurer"])}</strong><span class="sub">{MODEL_LABEL[x["model"]]} · {e(x["tariff"])}</span></td>'
        f'<td class="num">CHF {chf(x["before"])}<span class="sub">→ CHF {chf(x["after"])}</span></td>'
        f'<td class="num kk-up">{pct(x["change"])}<span class="sub">Markt {pct(x["market"])}</span></td>'
        f'<td class="num">{x["rank_after"]} / {x["n_after"]}</td></tr>'
        for x in cur["rows"][:10])
    prev_txt = (f" Im Jahr davor war es gleich: Die Sieger von {YEAR - 2} stiegen um {pct(prev['winner_change'])}, "
                f"der Markt um {pct(prev['market_change'])}." if prev else "")
    return [
        f'<h2 id="vorjahressieger">Der günstigste Tarif vom letzten Jahr schlägt am stärksten auf</h2>',
        f"<p>Wir haben in jeder Prämienregion den günstigsten Tarif von {PREV} genommen und geschaut, was er {YEAR} kostet "
        f"(Erwachsene, Franchise 2'500, ohne Unfall). Ergebnis über {cur['regions']} Regionen: Der Vorjahressieger steigt im Schnitt um "
        f"<strong>{pct(cur['winner_change'])}</strong>, der Median aller Tarife in derselben Region um {pct(cur['market_change'])}. "
        f"Nur in {cur['still_first']} von {cur['regions']} Regionen ist er noch der günstigste, in {cur['out_of_top5']} fällt er aus den Top 5.{prev_txt}</p>",
        f"<p>Wer einmal zur günstigsten Kasse wechselt und dann bleibt, verliert den Vorsprung also oft schon im nächsten Jahr. "
        f"Es lohnt sich, jedes Jahr neu zu vergleichen. Oft reicht auch ein anderes Modell bei der eigenen Kasse: "
        f"Der Wechsel vom Standardmodell ins günstigste andere Modell derselben Kasse spart im Median "
        f"<strong>CHF {chf(jojo['model_switch_median'], 0)} pro Jahr</strong>.</p>",
        f'<p>Die zehn stärksten Aufschläge bei Vorjahressiegern:</p>',
        f'<div class="kk-table-wrap"><table class="kk-table"><thead><tr><th>Region</th><th>Sieger {PREV}</th>'
        f'<th class="num">Prämie</th><th class="num">{YEAR}</th><th class="num">Rang {YEAR}</th></tr></thead><tbody>{rows}</tbody></table></div>',
        f'<p class="kk-note">Regionen, in denen der Siegertarif {YEAR} nicht mehr angeboten wird oder umbenannt wurde, sind nicht mitgezählt.</p>',
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

    def pc(v, ref):
        cls = "var(--red)" if v > ref else "var(--green)"
        return f'<span style="color:{cls};font-weight:600;">{pct(v)}</span>'

    td = 'style="text-align:right;padding:9px 12px;white-space:nowrap;"'
    kas = "".join(
        f'<tr style="border-bottom:1px solid var(--border);"><td style="padding:9px 12px;font-weight:600;">{kasse_link(x["id"])}</td>'
        f'<td {td}><strong style="font-size:15px;">{note_fmt(x["note"])}</strong></td>'
        f'<td {td}>{pc(x["prev"], nat_prev)}</td><td {td}>{pc(x["cur"], nat)}</td>'
        f'<td {td}>{pc(x["tot"], tot_all)}</td>'
        f'<td {td}><a href="/kasse/{KASSE_SLUG[x["id"]]}/" style="color:var(--accent-dark);font-weight:600;">Analyse &rarr;</a></td></tr>'
        if x["id"] in KASSE_SLUG else
        f'<td {td}>{pc(x["tot"], tot_all)}</td><td></td></tr>' for x in big)

    def cli(c, v):
        return (f'<div><a href="/krankenkasse/{CANTONS[c][1]}/" style="color:var(--text);"><strong>{e(CANTONS[c][0])}</strong></a> '
                f'<span style="color:var(--muted);font-weight:600;">{pct(v["change_pct"])}</span></div>')

    canton_links = "".join(
        f'<a href="/krankenkasse/{slug}/" style="color:var(--accent-dark);">{e(name)}</a>'
        for name, slug in sorted(CANTONS.values()))
    trs = "".join(
        f'<tr style="border-bottom:1px solid var(--border);"><td style="padding:10px 12px;font-weight:600;">{kasse_link(i)}</td>'
        f'<td style="text-align:center;padding:10px 12px;">{top3_prev2.get(i, 0)} / 26</td>'
        f'<td style="text-align:center;padding:10px 12px;">{top3_prev.get(i, 0)} / 26</td>'
        f'<td style="text-align:center;padding:10px 12px;">{top3_cur.get(i, 0)} / 26</td></tr>' for i in cons)

    example = ""
    rows = ((jojo or {}).get(f"{PREV}-{YEAR}") or {}).get("rows") or []
    if rows:
        x = rows[0]
        chg = f"{x['change']:.1f}".replace(".", ",")
        example = (f"Ein Beispiel aus {e(CANTONS[x['canton']][0])}: {e(x['insurer'])} war {PREV} die günstigste Kasse. "
                   f"{YEAR} kostet derselbe Tarif <strong>{chg} Prozent mehr</strong>, die Kasse ist nur noch auf Platz {x['rank_after']}.")
    card = 'style="background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:28px;margin-bottom:20px;"'
    col = 'style="font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin-bottom:10px;"'
    return f"""<!-- INSIGHTS:START (generiert von scripts/build_kk_pages.py) -->
<section class="insights-section" style="padding:80px 40px;background:var(--bg);">
  <div style="max-width:900px;margin:0 auto;">
    <div class="section-label">Datenanalyse</div>
    <h2 class="section-headline" style="margin-bottom:8px;">Die Billigste von heute ist oft die Teuerste von morgen</h2>
    <p style="color:var(--text2);font-size:17px;line-height:1.6;margin-bottom:10px;">{example}</p>
    <p style="color:var(--muted);margin-bottom:32px;">Wer jedes Jahr zur Billigsten wechselt, landet oft genau dort. Unser <a href="/krankenkassen-rating/" style="color:var(--accent-dark);">Preistreue-Rating</a> zeigt, welche Kassen seit {(RATING or {}).get("years", [Y0])[0]} günstig bleiben.</p>

    <div {card}>
      <h3 style="font-size:18px;font-weight:700;margin-bottom:6px;">Preistreue-Rating {YEAR} und Anstieg pro Kasse</h3>
      <div style="font-size:14px;color:var(--muted);margin-bottom:16px;">Note von 0 bis 10 aus Preis, Konstanz, Treue, Rabatt-Treue, Tarif-Bestand und Reserven. Daneben der Anstieg der Standardprämie, Schnitt aller Kassen {pct(nat_prev)} im {PREV} und {pct(nat)} im {YEAR}. Rot heisst über dem Schnitt. <strong style="color:var(--text);">Klick auf eine Kasse für die ganze Analyse:</strong> Note mit allen Teilnoten, Prämien in jedem Kanton, Modelle und Kündigungsweg.</div>
      <div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;font-size:14px;">
        <thead><tr style="border-bottom:1px solid var(--border2);"><th style="text-align:left;padding:8px 12px;">Kasse</th><th style="text-align:right;padding:8px 12px;">Note</th><th style="text-align:right;padding:8px 12px;">{PREV}</th><th style="text-align:right;padding:8px 12px;">{YEAR}</th><th style="text-align:right;padding:8px 12px;">Seit {Y0}</th><th></th></tr></thead>
        <tbody>{kas}</tbody>
      </table></div>
      <div style="font-size:12px;color:var(--muted);margin-top:10px;">Kassen mit mindestens {MIN_BESTAND_RANKING // 1000}'000 Versicherten, sortiert nach Note. In deiner Region kann die Reihenfolge anders sein, siehe Kantone unten. <a href="/krankenkassen-rating/" style="color:var(--accent-dark);">So rechnen wir &rarr;</a></div>
    </div>

    <div {card}>
      <h3 style="font-size:18px;font-weight:700;margin-bottom:6px;">Nach Kanton</h3>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:20px;font-size:15px;line-height:2;">
        <div><div {col}>Stärkster Anstieg</div>{"".join(cli(c, v) for c, v in by_change[:3])}</div>
        <div><div {col}>Schwächster Anstieg</div>{"".join(cli(c, v) for c, v in by_change[-3:][::-1])}</div>
      </div>
      <div style="margin-top:18px;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);">Dauerhaft günstig in deinem Kanton</div>
      <div style="display:flex;flex-wrap:wrap;gap:6px 14px;margin-top:8px;font-size:14px;">{canton_links}</div>
    </div>


    <div style="font-size:12px;color:var(--muted);text-align:center;">Quelle: BAG · Erwachsene, Franchise 300, mit Unfall · <a href="/krankenkassenpraemien-{YEAR}/" style="color:var(--accent-dark);">Ganze Auswertung {YEAR}</a> · <a href="/krankenkassen-rating/" style="color:var(--accent-dark);">Preistreue-Rating</a> · <a href="/kasse/" style="color:var(--accent-dark);">Alle Kassen</a> · <a href="/krankenkasse-kuendigen/" style="color:var(--accent-dark);">Kündigen bis {DEADLINE}</a></div>
  </div>
</section>
<!-- INSIGHTS:END -->"""



# ── Preistreue-Rating ──────────────────────────────────────────────────────

RATING = None   # wird in main() aus build_rating.compute() gefüllt
MAIN_REGION = {}  # Kanton -> Hauptregion, in main() gefüllt
AWARDS = []       # Preistreue-Award, in main() aus build_awards.compute() gefüllt
AWARD_PATH = "/krankenkassen-rating/award/"
RATING_PATH = "/krankenkassen-rating/"

# Aufschlüsselung der Verwaltungskosten (scripts/extract_verwaltung.py)
_VD = DATA / "verwaltung_detail.json"
VDET = json.loads(_VD.read_text(encoding="utf-8"))["kassen"] if _VD.exists() else {}


def vdet(i):
    """Letztes Jahr der BAG-Aufschlüsselung einer Kasse: (Jahr, Werte) oder (None, None)."""
    d = VDET.get(str(i)) or {}
    y = max(d, default=None)
    return (y, d[y]) if y else (None, None)


GRUPPE_HINWEIS = ("ohne eigenes Personal: die Verwaltung wird als Gebühr bei einer Konzern- oder Partnerfirma "
                  "eingekauft, wie sie sich auf die Konzernkassen verteilt, bestimmt der Konzern")


def note_fmt(v):
    return f"{v:.1f}".replace(".", ",") if v is not None else "–"


def bar(v):
    w = 0 if v is None else max(2, v * 10)
    return f'<span class="kk-bar"><span style="width:{w:.0f}%"></span></span>'


def rating_canton_block(c, main):
    """Die 5 Kassen mit der besten Note in der Hauptregion des Kantons."""
    if not RATING:
        return ""
    reg = RATING["regions"].get(f"{c}|{main}", {})
    best = sorted(((i, v) for i, v in reg.items() if v["note"] is not None), key=lambda x: -x[1]["note"])[:5]
    if not best:
        return ""
    n_years = len(RATING["years"])
    rows = "".join(
        f'<tr><td>{kasse_link(i)}</td><td class="num"><strong>{note_fmt(v["note"])}</strong></td>'
        f'<td class="num">{v["top5"][-1][0]} von {v["top5"][-1][1]}</td></tr>' for i, v in best)
    return (f"<h2>Dauerhaft günstig im Kanton {e(CANTONS[c][0])}</h2>"
            f"<p>Nicht nur dieses Jahr günstig, sondern über die Jahre: die fünf Kassen mit der besten Note im "
            f"<a href=\"{RATING_PATH}\">Preistreue-Rating</a>, gerechnet für die Hauptregion des Kantons. "
            f"Die letzte Spalte zeigt, in wie vielen Jahren seit {RATING['years'][0]} die Kasse hier unter den 5 günstigsten war (Franchise 2'500).</p>"
            f'<div class="kk-table-wrap"><table class="kk-table"><thead><tr><th>Kasse</th><th class="num">Note</th>'
            f'<th class="num">Jahre unter den 5 günstigsten</th></tr></thead><tbody>{rows}</tbody></table></div>')


def rating_kasse_card(i):
    if not RATING or i not in RATING["national"]:
        return ""
    n = RATING["national"][i]
    rows = "".join(f'<div class="kk-rrow"><span>{e(RATING["labels"][k])}</span>{bar(n["parts"][k])}'
                   f'<span class="num">{note_fmt(n["parts"][k])}</span></div>' for k in RATING["weights"])
    adm = RATING["verwaltung"]["kassen"].get(str(i), {})
    mk = RATING["verwaltung"]["markt_verwaltung"]
    last = max(adm, default=None)
    first = min(adm, default=None)
    adm_html = ""
    if last:
        v, m = adm[last]["verwaltung"], mk[last]
        vy, vd = vdet(i)
        det = (f' {vy}: Werbung CHF {vd["werbung"]:.0f}, Provisionen an Vermittler CHF {vd["provisionen"]:.0f}.'
               + (' Die Kasse hat kein eigenes Personal und kauft ihre Verwaltung als Gebühr bei einer Konzern- oder Partnerfirma ein.'
                  if vd["ohne_personal"] else "")) if vd else ""
        adm_html = (f'<p class="kk-rnote">Verwaltungskosten {last}: <strong>CHF {v:.0f}</strong> pro versicherte Person '
                    f'(Schnitt aller Kassen CHF {m:.0f})'
                    + (f', {first}: CHF {adm[first]["verwaltung"]:.0f}' if first != last else "") + f'.{det} Quelle: BAG.</p>')
    hint = " Regionalkasse: die Note stützt sich auf wenige Regionen." if n["regional"] else ""
    vn = n.get("varianten") or {}
    var_html = ('<div class="kk-rvar">' + " · ".join(
        f'{e(v["label"])} <strong>{note_fmt(vn.get(v["key"]))}</strong>' for v in RATING.get("varianten", [])) + "</div>") if vn else ""
    return (f'<div class="kk-rating"><div class="kk-rating-head"><div><div class="kk-rating-label">Preistreue-Rating {YEAR}</div>'
            f'<div class="kk-rating-sub">Ist {e(n["name"])} dauerhaft günstig? Aus den BAG-Prämien seit {RATING["years"][0]}.{hint}</div></div>'
            f'<div class="kk-rating-note">{note_fmt(n["note"])}<span>/10</span></div></div>{var_html}{rows}{adm_html}'
            f'{award_strip(i)}<a href="{RATING_PATH}">So rechnen wir &rarr;</a></div>')


def rating_page(r):
    path = RATING_PATH
    nat = r["national"]
    big = sorted((i for i in nat if not nat[i]["regional"] and nat[i]["note"] is not None), key=lambda i: -nat[i]["note"])
    small = sorted((i for i in nat if nat[i]["regional"] and nat[i]["note"] is not None), key=lambda i: -nat[i]["note"])
    keys = list(r["weights"])
    y0 = r["years"][0]

    def table(ids, rank=True):
        short = {"preis": "Preis", "konstanz": "Konstanz", "treue": "Treue", "rabatt": "Rabatt",
                 "tarife": "Tarife", "solvenz": "Reserven"}
        head = "".join(f'<th class="num" title="{e(r["labels"][k])}">{short[k]}</th>' for k in keys)
        body = "".join(
            f'<tr>{"<td>" + str(n + 1) + "</td>" if rank else ""}<td>{kasse_link(i)}</td>'
            f'<td class="num"><strong>{note_fmt(nat[i]["note"])}</strong></td>'
            + "".join(f'<td class="num">{note_fmt(nat[i]["parts"][k])}</td>' for k in keys) + "</tr>"
            for n, i in enumerate(ids))
        return (f'<div class="kk-table-wrap"><table class="kk-table kk-rtable"><thead><tr>{"<th>#</th>" if rank else ""}<th>Kasse</th>'
                f'<th class="num">Note</th>{head}</tr></thead><tbody>{body}</tbody></table></div>')

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
    cantons = "".join(f'<a href="/krankenkasse/{slug}/">{e(nm)}</a>' for nm, slug in sorted(CANTONS.values()))

    method = [
        ("preis", "Preis heute", "Position des günstigsten Tarifs der Kasse unter allen Kassen der Prämienregion, "
         f"{YEAR}. Unter den günstigsten 20 % = 10 Punkte, ab 80 % = 0."),
        ("konstanz", "Konstanz", f"In wie vielen Jahren seit {y0} war die Kasse in der Region unter den 5 günstigsten? "
         "Ab 30 % der Jahre = 10 Punkte."),
        ("treue", "Treue", "Wie stark stieg der günstigste Tarif der Kasse, wenn man in ihm blieb, verglichen mit dem Median "
         "aller Tarife der Region? Mittel über alle Jahre. 0,3 Punkte pro Jahr unter dem Markt = 10, 1,5 Punkte darüber = 0."),
        ("rabatt", "Rabatt-Treue", f"Behalten neue Modelle ihren Rabatt gegenüber dem Standardmodell derselben Kasse? "
         "Gemessen an denselben Tarifen vom Startjahr bis heute. Kein Verlust = 10, 2 Punkte Verlust pro Jahr = 0. "
         "Kassen ohne neue Modelle seit 2021 werden hier nicht bewertet."),
        ("tarife", "Tarif-Bestand", "Anteil der Tarife, die im Folgejahr unter gleichem Tarifcode weiterlaufen. "
         "100 % = 10 Punkte, 80 % = 0. Wer Tarife streicht oder umbenennt, zwingt Versicherte zum Wechseln."),
        ("solvenz", "Finanzpolster", "Solvenzquote laut BAG per 1. Januar 2026: vorhandene Reserven im Verhältnis zur "
         "gesetzlichen Mindesthöhe. 200 % = 10 Punkte, 100 % = 0. Knappe Reserven gehen oft höheren Aufschlägen voraus."),
    ]
    meth_rows = "".join(f'<tr><td><strong>{e(t)}</strong></td><td class="num">{int(r["weights"][k] * 100)} %</td><td>{e(d)}</td></tr>'
                        for k, t, d in method)
    qa = [
        ("Welche Krankenkasse ist dauerhaft günstig?",
         f"Laut unserem Preistreue-Rating {YEAR} schneiden {top[0]['name']}, {top[1]['name']} und {top[2]['name']} am besten ab. "
         "Sie sind heute günstig und waren es auch in den Jahren davor. Welche Kasse in deiner Region vorne liegt, zeigt die Seite deines Kantons."),
        ("Warum ist die günstigste Kasse von heute oft nicht die beste Wahl?",
         "Manche Kassen sind ein Jahr günstig und schlagen danach überdurchschnittlich auf. Neue Sparmodelle starten mit viel Rabatt "
         "und verlieren ihn in den Folgejahren. Wer nicht jedes Jahr wechseln will, fährt mit einer konstant günstigen Kasse besser."),
        ("Fliessen Kundenbewertungen ins Rating ein?",
         "Nein. Das Rating stützt sich nur auf harte Zahlen des Bundesamts für Gesundheit: Prämien seit "
         f"{y0}, Solvenzquoten und Aufsichtsdaten. Jede Zahl lässt sich nachrechnen."),
        ("Bezahlen Kassen für eine gute Note?",
         "Nein. abovergleich.com nimmt keine Provisionen von Krankenkassen. Die Note entsteht aus einer festen Formel, die hier offengelegt ist."),
    ]
    vkeys = [v["key"] for v in r["varianten"]]
    vhead = "".join(f'<th class="num">{e(v["label"].replace("Franchise ", "F "))}</th>' for v in r["varianten"])
    var_table = (f'<div class="kk-table-wrap"><table class="kk-table kk-rtable"><thead><tr><th>Kasse</th><th class="num">Gesamt</th>{vhead}</tr></thead><tbody>'
                 + "".join(f'<tr><td>{kasse_link(i)}</td><td class="num"><strong>{note_fmt(nat[i]["note"])}</strong></td>'
                           + "".join(f'<td class="num">{note_fmt(nat[i]["varianten"].get(k))}</td>' for k in vkeys) + "</tr>" for i in big)
                 + "</tbody></table></div>")
    wtxt = ", ".join(f'{v["label"]} {round(v["gewicht"] * 100)} %' for v in r["varianten"])
    body = f"""{crumbs_html([("Krankenkassen-Vergleich", "/"), ("Rating", path)])}
<div class="article-badge">Preistreue-Rating {YEAR}</div>
<h1>Krankenkassen-Rating {YEAR}: Welche Kasse ist dauerhaft günstig?</h1>
<div class="article-meta">Aus den BAG-Prämien {y0} bis {YEAR} · nur harte Zahlen, keine Bewertungen</div>
<p class="kk-lead">Die günstigste Kasse von heute ist nicht automatisch eine gute Wahl. Manche sind ein Jahr günstig und schlagen danach kräftig auf, andere streichen Tarife und zwingen dich zum Wechseln. Unser Rating zeigt, welche Kassen <strong>über die Jahre</strong> günstig bleiben.</p>
<div class="kk-facts">
  <div class="kk-fact"><div class="kk-fact-val">{e(top[0]['name'])}</div><div class="kk-fact-label">beste Note {YEAR}: {note_fmt(top[0]['note'])} von 10</div></div>
  <div class="kk-fact"><div class="kk-fact-val">{len(r['years'])} Jahre</div><div class="kk-fact-label">Prämiendaten des BAG, {y0} bis {YEAR}, in jeder Prämienregion</div></div>
  {f'<div class="kk-fact"><div class="kk-fact-val">{str(koh["start"]).replace(".", ",")} % &rarr; {str(koh["heute"]).replace(".", ",")} %</div><div class="kk-fact-label">Rabatt der {koh["jahr"]} eingeführten Sparmodelle gegenüber Standard, damals und heute</div></div>' if koh else ''}
</div>
<a class="kk-cta" href="/#kk-rechner">Die Note deiner Kasse im Rechner sehen &rarr;</a>

<h2>Das Rating {YEAR}</h2>
<p>Note von 0 bis 10, gewichtet aus sechs Teilnoten. Kassen mit mindestens 50'000 Versicherten, über alle Prämienregionen gerechnet. In deiner Region kann die Reihenfolge anders aussehen, siehe unten.</p>
{table(big)}

<h2>Je nach Situation: mit oder ohne Unfall, Franchise 300 oder 2'500</h2>
<p>Die Kassen rechnen den Unfallzuschlag und die Franchisen unterschiedlich. Deshalb gibt es vier Einzelnoten. Die Gesamtnote oben gewichtet sie danach, wie viele Erwachsene welche Variante haben (BAG: rund 56 % ohne Unfalldeckung über die Kasse; Franchise 300 etwas häufiger als 2'500). Im Rechner siehst du die Note für deine Situation.</p>
{var_table}

<h2>Preistreue-Award {YEAR}</h2>
<p>Aus dem Rating vergeben wir jedes Jahr Auszeichnungen: Gesamtwertung, Kategorien wie «Dauerhaft günstig» oder «Solideste Reserven», und die preistreueste Kasse in jedem Kanton. Kassen können das Badge frei verwenden.</p>
<div class="kk-awardrow">{"".join(f'<a href="{AWARD_PATH}#{a["id"]}"><img src="{award_badge_url(a["id"], "-quer")}" alt="{e(a["alt"])}" width="248" height="72" loading="lazy"></a>' for a in AWARDS if a["group"] == "Gesamtwertung")}</div>
<p><a href="{AWARD_PATH}">Alle Auszeichnungen und Badges &rarr;</a></p>

<h2>Regionalkassen</h2>
<p>Kleinere Kassen, die nur in einem Teil der Schweiz tätig sind. Ihre Noten stützen sich auf wenige Regionen und sind deshalb separat aufgeführt.</p>
{table(small, rank=False)}

<h2>Das Rating in deiner Region</h2>
<p>Preise und Konstanz unterscheiden sich stark zwischen den Regionen. Eine Kasse, die im Aargau vorne liegt, kann in Genf teuer sein. Auf jeder Kantonsseite steht, welche Kassen dort dauerhaft günstig sind:</p>
<div class="kk-cantonlinks">{cantons}</div>

<h2>Die Sparmodell-Falle</h2>
<p>Neue Sparmodelle dürfen ohne Kostenzahlen aus fünf Jahren bis zu 20 % unter dem Standardmodell starten (Art. 101 KVV). Danach muss der Rabatt aus echten Kosten belegt sein. In den Daten sieht man, was das heisst:</p>
<div class="kk-table-wrap"><table class="kk-table"><thead><tr><th>Neue Modelle ab</th><th class="num">Rabatt im Startjahr</th><th class="num">Rabatt {YEAR}</th><th class="num">Tarife × Regionen</th></tr></thead><tbody>
{"".join(f'<tr><td>{k["jahr"]}</td><td class="num">{str(k["start"]).replace(".", ",")} %</td><td class="num">{str(k["heute"]).replace(".", ",")} %</td><td class="num">{k["tarife"]}</td></tr>' for k in r["kohorten"])}
<tr><td>Modelle, die es {y0} schon gab</td><td class="num">{str(alte["start"]).replace(".", ",")} %</td><td class="num">{str(alte["heute"]).replace(".", ",")} %</td><td class="num"></td></tr>
</tbody></table></div>
<p>Rabatt gegenüber dem Standardmodell derselben Kasse, Franchise 2'500, Median. Dieselben Tarife vom Startjahr bis {YEAR} verfolgt. Wer in ein neues Modell wechselt und bleibt, zahlt also Jahr für Jahr etwas mehr als beim Standard. Die Teilnote «Rabatt-Treue» misst, wie stark das bei jeder Kasse passiert.</p>

<h2>Verwaltungskosten: wer viel für sich selbst ausgibt</h2>
<p>Das BAG veröffentlicht für jede Kasse, was sie pro versicherte Person für die Verwaltung der Grundversicherung ausgibt: Löhne, Informatik, Werbung und Provisionen. Werbung und Provisionen an Vermittler weist es separat aus. Die Zahl fliesst nicht in die Note ein, weil sie schon im Preis steckt, aber sie zeigt, wo Prämiengeld hängen bleibt. Schnitt aller Kassen {a1}: <strong>CHF {mk[a1]:.0f}</strong>.</p>
<div class="kk-table-wrap"><table class="kk-table"><thead><tr><th>Kasse</th><th class="num">{a0}</th><th class="num">{a1}</th><th class="num">Veränderung</th><th class="num">Werbung {vjahr}</th><th class="num">Provisionen {vjahr}</th></tr></thead><tbody>{adm_html}</tbody></table></div>
<p class="kk-note">Pro versicherte Person und Jahr, nur Grundversicherung. Gesamtkosten aus den Aufsichtsdaten des BAG, Werbung und Provisionen aus der BAG-Auswertung der Verwaltungskosten. ¹ {GRUPPE_HINWEIS}. Der Gesamtbetrag ist trotzdem vergleichbar.</p>

<h2>So rechnen wir</h2>
<div class="kk-table-wrap"><table class="kk-table"><thead><tr><th>Teilnote</th><th class="num">Gewicht</th><th>Was sie misst</th></tr></thead><tbody>{meth_rows}</tbody></table></div>
<p>Grundlage sind die Prämien aller Kassen {y0} bis {YEAR} für Erwachsene, je mit und ohne Unfalldeckung und mit Franchise 300 und 2'500. Daraus entstehen vier Einzelnoten; die Gesamtnote gewichtet sie nach dem Bestand laut BAG ({wtxt}). Tarife, die eine Kasse umbenennt, verfolgen wir über den Namen weiter. Fehlt eine Teilnote, verteilt sich ihr Gewicht auf die übrigen. Die Formel gilt für alle Kassen gleich, und keine Kasse bezahlt uns etwas.</p>

<div class="kk-faq"><h2>Häufige Fragen</h2>{"".join(f"<h3>{e(q)}</h3><p>{e(a)}</p>" for q, a in qa)}</div>
<p class="kk-note">Quellen: BAG, Prämien der obligatorischen Krankenversicherung {y0} bis {YEAR} (opendata.swiss); BAG über priminfo.admin.ch, Solvenzquoten per 1.1.2026; BAG, Aufsichtsdaten OKP; KVV Art. 101. Angaben ohne Gewähr.</p>"""
    jsonld = [breadcrumb([("Krankenkassen-Vergleich", "/"), ("Rating", path)]), faq(qa),
              {"@context": "https://schema.org", "@type": "Article", "headline": f"Krankenkassen-Rating {YEAR}: Welche Kasse ist dauerhaft günstig?",
               "datePublished": f"{YEAR - 1}-10-01", "dateModified": date.today().isoformat(),
               "author": {"@type": "Organization", "name": "abovergleich.com"},
               "publisher": {"@type": "Organization", "name": "abovergleich.com", "url": SITE}, "mainEntityOfPage": f"{SITE}{path}"}]
    return path, page(path, f"Krankenkassen-Rating {YEAR}: Welche Kasse ist dauerhaft günstig?",
                      f"Preistreue-Rating aller Krankenkassen aus den BAG-Prämien {y0} bis {YEAR}: Preis, Konstanz, Treue, Tarife und Reserven. "
                      f"{top[0]['name']} schneidet am besten ab.", body, jsonld)


AWARD_CSS = """
  article.kk-page:has(.award-page) { max-width: 980px; }
  .award-page .rules { list-style:none; padding:0; display:grid; gap:10px; margin:16px 0 0; }
  .award-page .rules li { position:relative; padding-left:26px; color:var(--text2); }
  .award-page .rules li::before { content:"✓"; position:absolute; left:0; color:var(--green); font-weight:700; }
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
    btn.disabled = true; btn.textContent = 'einen Moment';
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


def award_badge_url(aid, suffix=""):
    return f"{AWARD_PATH}badge/{aid}{suffix}.svg"


def write_award_badges():
    # Badges früherer Sieger dieser Edition entfernen (Rating neu gerechnet).
    # Ab der Vergabe-Mitteilung an die Kassen nicht mehr löschen, sondern einfrieren.
    folder = ROOT / AWARD_PATH.strip("/") / "badge"
    keep = {f"{a['id']}{suffix}.svg" for a in AWARDS for suffix, _, _ in build_awards.VARIANTS}
    for f in folder.glob("*.svg") if folder.exists() else []:
        if f.name not in keep:
            f.unlink()
    for a in AWARDS:
        for suffix, fn, dark in build_awards.VARIANTS:
            target = ROOT / AWARD_PATH.strip("/") / "badge" / f"{a['id']}{suffix}.svg"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(fn(a, YEAR, dark), encoding="utf-8")


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
    imgs = "".join(f'<a href="{AWARD_PATH}#{a["id"]}"><img src="{award_badge_url(a["id"], "-quer")}" alt="{e(a["alt"])}" width="248" height="72" loading="lazy"></a>' for a in show[:3])
    more = (f'<div class="kk-rnote">Dazu Sieger in {len(kant)} {"Kanton" if len(kant) == 1 else "Kantonen"}. '
            f'<a href="{AWARD_PATH}">Alle Auszeichnungen</a></div>') if kant else ""
    return f'<div class="kk-awardrow">{imgs}</div>{more}'


def award_page():
    path = AWARD_PATH
    groups = []
    for g in ("Gesamtwertung", "Kategorien", "Kantone"):
        items = [a for a in AWARDS if a["group"] == g]
        if not items:
            continue
        cards = []
        for a in items:
            n = (RATING or {}).get("national", {}).get(a["insurer"], {})
            cards.append(f"""<div class="win" id="{a['id']}">
  <img src="{award_badge_url(a['id'])}" alt="{e(a['alt'])}" width="240" height="384" loading="lazy">
  <div>
    <h3>{kasse_link(a['insurer'], a['name'])}</h3>
    <p class="meta">{e(a['headline'])} · {e(a['fact'])}</p>
    <div class="variants">
      <a href="{award_badge_url(a['id'])}">Hoch hell</a><a href="{award_badge_url(a['id'], '-dunkel')}">Hoch dunkel</a>
      <a href="{award_badge_url(a['id'], '-quer')}">Quer hell</a><a href="{award_badge_url(a['id'], '-quer-dunkel')}">Quer dunkel</a>
    </div>
    <div class="variants pngrow"><span class="pnglbl">Als PNG:</span>
      <button type="button" data-svg="{award_badge_url(a['id'])}" data-w="240" data-h="384" data-name="{a['id']}-hoch">Hoch</button>
      <button type="button" data-svg="{award_badge_url(a['id'], '-quer')}" data-w="375" data-h="109" data-name="{a['id']}-quer">Quer</button>
    </div>
    <div class="snippet"><code>{e(f'<a href="{a["link"]}">' + chr(10) + f'  <img src="{SITE}{award_badge_url(a["id"])}"' + chr(10) + f'       alt="{a["alt"]}"' + chr(10) + '       width="240" height="384" loading="lazy">' + chr(10) + '</a>')}</code></div>
    <p class="baustein-lbl">Textbaustein zum Übernehmen</p>
    <blockquote class="baustein">{e(a['pressText'])}</blockquote>
  </div>
</div>""")
        groups.append(f'<div class="grouphead">{e(g)}</div>' + "".join(cards))
    n_awards = len(AWARDS)
    y0 = RATING["years"][0]
    body = f"""<div class="award-page">
{crumbs_html([("Krankenkassen-Vergleich", "/"), ("Rating", RATING_PATH), ("Award", path)])}
<div class="article-badge">Edition {YEAR}</div>
<h1>abovergleich Preistreue-Award {YEAR}</h1>
<p class="kk-lead">{n_awards} Auszeichnungen für Krankenkassen, die dauerhaft günstig bleiben. Vergeben allein aus den Prämiendaten des Bundes seit {y0}. Keine Jury, keine Einreichung, keine Gebühr.</p>

<h2>Wofür ausgezeichnet wird</h2>
<p>Grundlage ist das <a href="{RATING_PATH}">Preistreue-Rating</a>: Preis heute, wie oft eine Kasse seit {y0} in ihrer Region unter den fünf günstigsten war, wie stark sie aufschlägt, ob neue Sparmodelle ihren Rabatt halten, wie oft sie Tarife streicht und wie gut ihre Reserven sind. Die <strong>Gesamtwertung</strong> zeichnet die drei besten Noten aus, die <strong>Kategorien</strong> den Besten in je einem Teilaspekt, und in jedem <strong>Kanton</strong> die Kasse mit der besten Note in der Hauptregion, Regionalkassen eingeschlossen.</p>

<h2>Die Regeln</h2>
<ul class="rules">
  <li>Die Auswahl folgt allein der Zahl. Es gibt keine Jury, keine Einreichung und keinen Weg, einen Award zu beeinflussen.</li>
  <li>Der Award kostet nichts und ist an nichts gekoppelt. Ob eine Kasse das Badge einbindet oder verlinkt, ändert weder Note noch Reihenfolge auf abovergleich.com.</li>
  <li>Ein Link ist keine Bedingung. Der Einbindungscode enthält ihn, weil eine Auszeichnung ohne Beleg wenig wert ist. Wer das Badge ohne Link nutzt, darf das.</li>
  <li>Die Edition ist ein Stichtag: die Prämien {YEAR}. Das Badge {YEAR} behält seine Aussage, auch wenn sich die Note im nächsten Jahr ändert.</li>
  <li>Gesamtwertung und Kategorien: Kassen mit mindestens 50'000 Versicherten. Bei Gleichstand gewinnen alle. Die Note rechnen wir für vier Situationen (mit oder ohne Unfall, Franchise 300 oder 2'500) und gewichten sie nach dem Bestand laut BAG.</li>
  <li>«Schlankste Verwaltung»: die gesamten Verwaltungskosten pro versicherte Person laut BAG, letztes verfügbares Jahr, auch was eine Kasse bei einer Konzernfirma einkauft.</li>
</ul>

{"".join(groups)}

<div class="cta-box"><h3>Zahl falsch? Sag es uns.</h3><p>Wenn ein Wert nicht stimmt, korrigieren wir ihn und rechnen die Edition neu. Schreib an hello@handyabo.com.</p><a href="mailto:hello@handyabo.com">Mail schreiben &rarr;</a></div>
</div>
{AWARD_PNG_JS}"""
    jsonld = [breadcrumb([("Krankenkassen-Vergleich", "/"), ("Rating", RATING_PATH), ("Award", path)])]
    winner = AWARDS[0]["name"] if AWARDS else ""
    html_out = page(path, f"Preistreue-Award {YEAR}: die preistreuesten Krankenkassen",
                    f"{n_awards} Auszeichnungen für Krankenkassen, die dauerhaft günstig bleiben, allein aus BAG-Prämien seit {y0}. Sieger {YEAR}: {winner}.",
                    body, jsonld)
    return path, html_out.replace("</style>", AWARD_CSS + "</style>", 1)


# ── Kassenseiten und Kündigung ─────────────────────────────────────────────

KASSE_SLUG = {}   # wird in main() gefüllt: BAG-Nummer -> Slug


def slugify(name):
    s = name.lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("è", "e"), ("é", "e"), ("’", ""), ("'", "")):
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def kasse_link(i, text=None):
    text = e(text or INSURER_NAMES[str(i)])
    return f'<a class="kasse-link" href="/kasse/{KASSE_SLUG[i]}/">{text}</a>' if i in KASSE_SLUG else text


def people(n):
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}".replace(".", ",") + " Mio."
    return chf(round(n, -3), 0)


def address_lines(kv, i):
    d = kv.get(i, {})
    return [d.get("name") or INSURER_NAMES[str(i)]] + d.get("address", [])


def kasse_page(i, cur, by_canton_cur, prev_idx, insurers, ic, top3_cur, kv, nu):
    name = INSURER_NAMES[str(i)]
    path = f"/kasse/{KASSE_SLUG[i]}/"
    own = [r for r in cur if r["insurer_id"] == i]
    cants = sorted({r["canton"] for r in own} & set(CANTONS), key=lambda c: CANTONS[c][0])
    info = insurers.get(i)

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
                         f'{("<span class=sub>" + MODEL_LABEL[best["model"]] + " · Platz " + str(pos) + " von " + str(len(rk)) + "</span>") if best else ""}</td>')
        if pos25 == 1:
            first_in.append(c)
        if pos25 and pos25 <= 3:
            top3_in += 1
        rows.append(f'<tr><td><a href="/krankenkasse/{CANTONS[c][1]}/">{e(CANTONS[c][0])}</a></td>{"".join(cells)}</tr>')

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
    rel = ""
    if chg is not None:
        rel = ("weniger als" if chg < BAG_OFFICIAL["change_pct"] else "mehr als")
    t3 = top3_cur.get(i, 0)
    group = (kv.get(i) or {}).get("group")
    group_name = group.split(" (")[0] if group else None
    siblings = [j for j in KASSE_SLUG if j != i and ((kv.get(j) or {}).get("group") or "").split(" (")[0] == group_name] if group_name else []

    title = f"{name} Prämien {YEAR}: Erhöhung, Modelle und Rating"
    desc = (f"{name} {YEAR}: Standardprämie {pct(chg)} gegenüber {PREV}. Alle Kantone und Modelle, "
            f"Preistreue-Note und Kündigungsadresse. Offizielle BAG-Daten.") if chg is not None else \
           (f"{name} {YEAR}: Prämien in allen Kantonen, Modelle, Preistreue-Note und Kündigungsadresse. BAG-Daten.")

    p = [crumbs_html([("Krankenkassen-Vergleich", "/"), ("Kassen", "/kasse/"), (name, path)])]
    p.append(f'<div class="article-badge">Prämien {YEAR}</div>')
    p.append(f"<h1>{e(name)} Prämien {YEAR}</h1>")
    p.append(f'<div class="article-meta">Offizielle Prämien des BAG · {len(cants)} {"Kanton" if len(cants) == 1 else "Kantone"}'
             f'{" · rund " + people(info["bestand"]) + " Versicherte" if info and info["bestand"] >= 1000 else ""}</div>')
    if chg is not None:
        tip_chg = ('<span class="tip" tabindex="0" aria-label="Info">i<span>Standardmodell, Erwachsene, Franchise 300, mit Unfall. '
                   'Schnitt über alle Kantone, gewichtet nach Versicherten. Der Schnitt aller Kassen ist die mittlere Prämie laut BAG.</span></span>')
        verb = (f"im Schnitt <strong>{pct(chg, sign=False)}</strong> teurer" if chg >= 0
                else f"im Schnitt <strong>{pct(-chg, sign=False)}</strong> günstiger")
        p.append(f'<p class="kk-lead">{e(name)} wird {YEAR} {verb}. '
                 f'Alle Kassen zusammen: {pct(BAG_OFFICIAL["change_pct"])}.{tip_chg}</p>')
    facts = []
    if chg is not None:
        facts.append((pct(chg), f"gegenüber {PREV}"))
    facts.append((f"{top3_in} von {len(cants)}", 'Kantonen unter den 3 günstigsten<span class="tip" tabindex="0" aria-label="Info">i<span>'
                  'Günstigstes Angebot, Erwachsene ohne Unfall, Franchise 2\'500, Region 1 jedes Kantons.</span></span>'))
    if gap and gap > 0:
        facts.append((f"CHF {chf(gap, 0)}", f'pro Jahr weniger mit einem Sparmodell bei {e(name)}<span class="tip" tabindex="0" aria-label="Info">i<span>'
                      'Hausarzt, HMO oder Telmed statt Standardmodell, gleiche Leistungen. Median über alle Regionen, Franchise 2\'500, ohne Unfall.</span></span>'))
    p.append('<div class="kk-facts">' + "".join(
        f'<div class="kk-fact"><div class="kk-fact-val">{v}</div><div class="kk-fact-label">{l}</div></div>' for v, l in facts) + "</div>")
    p.append(f'<a class="kk-cta" href="/?kasse={i}#kk-rechner">Mit deiner {e(name)}-Rechnung vergleichen &rarr;</a>')
    p.append(rating_kasse_card(i))

    p.append(f"<h2>{e(name)} {YEAR} in jedem Kanton</h2>")
    tip_reg = ('<span class="tip" tabindex="0" aria-label="Info">i<span>Viele Kantone haben zwei oder drei Prämienregionen. '
               'Wir zeigen Region 1, meist die Städte. Auf dem Land ist es oft etwas günstiger. Deine genaue Prämie zeigt der Rechner.</span></span>')
    tip_platz = ('<span class="tip" tabindex="0" aria-label="Info">i<span>Das günstigste Angebot von ' + e(name) +
                 ' im Kanton, meist ein Sparmodell (Hausarzt, HMO, Telmed, gleiche Leistungen). Platz unter allen Kassen: 1 heisst, niemand ist günstiger.</span></span>')
    p.append(f"<p>Beispiel: <strong>Erwachsene Person ohne Unfalldeckung</strong> (über den Arbeitgeber versichert), günstigstes Angebot pro Monat.{tip_reg}{tip_platz}</p>")
    p.append(f'<div class="kk-table-wrap"><table class="kk-table"><thead><tr><th>Kanton</th><th class="num">Franchise 300</th>'
             f'<th class="num">Franchise 2\'500</th></tr></thead>'
             f'<tbody>{"".join(rows)}</tbody></table></div>')
    if first_in:
        p.append(f"<p>Am günstigsten von allen Kassen ist {e(name)} {YEAR} in: "
                 + ", ".join(f'<a href="/krankenkasse/{CANTONS[c][1]}/">{e(CANTONS[c][0])}</a>' for c in first_in) + ".</p>")

    if model_html:
        p.append(f"<h2>Modelle von {e(name)}</h2>")
        p.append(f"<p>Neben dem Standardmodell mit freier Arztwahl bietet {e(name)} {YEAR} diese Tarife an "
                 f"(nicht jeder in jedem Kanton). Die Leistungen sind in allen Modellen gleich, nur die erste Anlaufstelle unterscheidet sich.</p>")
        p.append(f"<ul>{model_html}</ul>")

    if siblings:
        p.append(f"<h2>Gruppe {e(group_name)}</h2>")
        p.append(f"<p>{e(name)} gehört zur Gruppe {e(group_name)}. Weitere Kassen der Gruppe mit eigenen Prämien: "
                 + ", ".join(kasse_link(j) for j in sorted(siblings, key=lambda j: INSURER_NAMES[str(j)])) + ".</p>")

    addr = address_lines(kv, i)
    p.append(f"<h2>{e(name)} kündigen</h2>")
    p.append(f"<p>Die Kündigung der Grundversicherung muss bis am <strong>{DEADLINE}</strong> bei {e(name)} eingetroffen sein, "
             f"der Poststempel zählt nicht. Adresse laut BAG-Verzeichnis der zugelassenen Krankenversicherer:</p>")
    p.append(f'<blockquote>{"<br>".join(e(l) for l in addr)}</blockquote>')
    p.append(f'<p><a href="/krankenkasse-kuendigen/?kasse={i}">Kündigungsbrief an {e(name)} erstellen</a>, fertig zum Ausdrucken.</p>')

    qa = []
    if chg is not None:
        qa.append((f"Wie stark steigen die Prämien von {name} {YEAR}?",
                   f"Die Standardprämie für Erwachsene mit Franchise 300 steigt bei {name} im Schnitt um {pct(chg)}, gewichtet nach "
                   f"Versicherten je Kanton. Laut BAG steigt die mittlere Prämie aller Kassen um {BAG_OFFICIAL['change_pct']:.1f} Prozent."))
    qa.append((f"Ist {name} günstig?",
               f"Für Erwachsene ohne Unfalldeckung mit Franchise 2'500 gehört {name} {YEAR} in {top3_in} von {len(cants)} Kantonen zu den drei günstigsten Kassen"
               + (f" und ist in {len(first_in)} {'Kanton' if len(first_in) == 1 else 'Kantonen'} die günstigste überhaupt." if first_in else ".")
               + " Wie günstig es für dich ist, hängt von Wohnort, Franchise und Modell ab."))
    qa.append((f"Bis wann kann ich {name} kündigen?",
               f"Die Kündigung muss bis am {DEADLINE} bei {name} eingetroffen sein, dann wechselst du auf den 1. Januar {YEAR}. "
               f"Adresse: {', '.join(addr)}."))
    p.append('<div class="kk-faq"><h2>Häufige Fragen</h2>' + "".join(f"<h3>{e(q)}</h3><p>{e(a)}</p>" for q, a in qa) + "</div>")
    p.append(f'<p class="kk-note">Quelle: Bundesamt für Gesundheit (BAG), Prämien {YEAR} und {PREV}; Versichertenbestand {YEAR - 2}. '
             f'Angaben ohne Gewähr. <a href="/kasse/">Alle Kassen</a> · <a href="/krankenkassenpraemien-{YEAR}/#methode">Methode</a></p>')
    return path, page(path, title, desc, "\n".join(p),
                      [breadcrumb([("Krankenkassen-Vergleich", "/"), ("Kassen", "/kasse/"), (name, path)]), faq(qa)])


def kasse_hub(insurers, top3_cur):
    path = "/kasse/"
    nat = (RATING or {}).get("national", {})
    regio = ' <span class="sub">Regionalkasse</span>'
    ids = sorted(KASSE_SLUG, key=lambda i: (nat.get(i, {}).get("regional", True), -(nat.get(i, {}).get("note") or 0)))
    rows = "".join(
        f'<tr><td>{kasse_link(i)}{regio if nat.get(i, {}).get("regional") else ""}</td>'
        f'<td class="num"><strong>{note_fmt(nat.get(i, {}).get("note"))}</strong></td>'
        f'<td class="num">{people(insurers[i]["bestand"]) if i in insurers and insurers[i]["bestand"] >= 1000 else "–"}</td>'
        f'<td class="num {"kk-up" if i in insurers and insurers[i]["change_pct"] > 0 else ""}">{pct(insurers[i]["change_pct"]) if i in insurers else "–"}</td>'
        f'</tr>' for i in ids)
    body = [
        crumbs_html([("Krankenkassen-Vergleich", "/"), ("Kassen", path)]),
        f'<div class="article-badge">Prämien {YEAR}</div>',
        f"<h1>Alle Krankenkassen: Prämien {YEAR} im Vergleich</h1>",
        f'<div class="article-meta">{len(ids)} Kassen mit Grundversicherung · Offizielle BAG-Daten</div>',
        f'<p class="kk-lead">Welche Kasse dauerhaft günstig ist und wie stark sie {YEAR} aufschlägt. '
        f'Ein Klick auf die Kasse zeigt alle Kantone, Modelle und die Kündigungsadresse.</p>',
        f'<div class="kk-table-wrap"><table class="kk-table"><thead><tr><th>Kasse</th><th class="num">Preistreue</th><th class="num">Versicherte</th>'
        f'<th class="num">vs. {PREV}</th></tr></thead><tbody>{rows}</tbody></table></div>',
        f'<p class="kk-note">Preistreue: Note von 0 bis 10 aus dem <a href="{RATING_PATH}">Preistreue-Rating</a>, sortiert nach Note, Regionalkassen am Schluss. '
        f'Veränderung: Standardmodell, Franchise 300, gewichtet nach Versicherten je Kanton. '
        f'Versicherte: Durchschnittsbestand {YEAR - 2} laut BAG.</p>',
    ]
    return path, page(path, f"Alle Krankenkassen {YEAR}: Prämienerhöhung je Kasse im Vergleich",
                      f"Alle {len(ids)} Krankenkassen mit Grundversicherung {YEAR}: Prämienveränderung, Versicherte und wo sie günstig sind. Offizielle BAG-Daten.",
                      "\n".join(body), [breadcrumb([("Krankenkassen-Vergleich", "/"), ("Kassen", path)])])


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
  @media (max-width:640px) { .kd-form { grid-template-columns:1fr; } #kd-brief { padding:20px; } }
  @media print {
    body * { visibility:hidden; }
    #kd-brief, #kd-brief * { visibility:visible; }
    #kd-brief { position:absolute; left:0; top:0; width:100%; border:none; padding:0; margin:0; font-size:12pt; }
  }
"""


def kuendigen_page(kv):
    path = "/krankenkasse-kuendigen/"
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
            "url": f"https://www.{x['web']}" if x.get("web") else None,
        }

    stand = ".".join(str(int(t)) for t in reversed(kan_doc["stand"].split("-")))
    data = [{"id": i, "name": INSURER_NAMES[str(i)], "address": address_lines(kv, i), **weg(i)} for i in ids]
    end = f"31. Dezember {PREV}"
    deadline_iso = f"{PREV}-11-30"
    kd_data = json.dumps({"kassen": data, "end": end, "start": f"1. Januar {YEAR}", "deadline": deadline_iso, "deadline_text": DEADLINE,
                          "stand": stand}, ensure_ascii=False).replace("</", "<\\/")

    def weg_cell(i):
        w = weg(i)
        if w["mail"]:
            return e(w["mail"]) + (" *" if w["own"] else "")
        if w["portal"]:
            return e(w["portal"])
        return "Post"
    addr_rows = "".join(f'<tr><td>{kasse_link(i)}</td><td>{e(", ".join(address_lines(kv, i)))}</td><td>{weg_cell(i)}</td></tr>' for i in ids)
    n_mail = sum(1 for i in ids if weg(i)["mail"] or weg(i)["portal"])
    qa = [
        (f"Bis wann muss ich die Krankenkasse kündigen?",
         f"Die Kündigung der Grundversicherung muss bis am {DEADLINE} bei der Kasse eingetroffen sein. "
         f"Massgebend ist das Datum, an dem die Kasse den Brief erhält, nicht der Poststempel. Der Wechsel gilt ab 1. Januar {YEAR}."),
        ("Muss ich per Einschreiben kündigen?",
         "Nein. Das Gesetz schreibt keine Form vor, entscheidend ist, dass die Kündigung rechtzeitig ankommt. "
         f"{n_mail} von {len(ids)} Kassen nehmen sie laut eigener Website auch per Mail an, die Tabelle unten zeigt welche. "
         "Per Post ist das Einschreiben der sicherste Beweis, per Mail die Eingangsbestätigung der Kasse."),
        ("Kann die neue Krankenkasse mich ablehnen?",
         "Nein. In der Grundversicherung muss jede Kasse in ihrem Tätigkeitsgebiet alle Personen aufnehmen, ohne Gesundheitsfragen. "
         "Bei Zusatzversicherungen ist das anders."),
        ("Was passiert mit meiner Zusatzversicherung?",
         "Nichts, wenn du sie nicht selbst kündigst. Die Zusatzversicherung kann bei der bisherigen Kasse bleiben, auch wenn du "
         "die Grundversicherung wechselst. Für sie gelten eigene Fristen im Vertrag. Ein Wechsel lohnt sich selten: Die neue Kasse "
         "darf Gesundheitsfragen stellen und Vorbehalte machen. Berater empfehlen ihn trotzdem oft, weil sie dafür Provision erhalten."),
        ("Kann ich auch auf Ende Juni wechseln?",
         "Nur im Standardmodell mit Franchise 300. Dann muss die Kündigung bis 31. März eintreffen, der Wechsel gilt ab 1. Juli."),
    ]
    body = f"""{crumbs_html([("Krankenkassen-Vergleich", "/"), ("Krankenkasse kündigen", path)])}
<div class="article-badge">Frist {DEADLINE}</div>
<h1>Krankenkasse kündigen: bis {DEADLINE.replace(' ' + str(PREV), '')}, mit Vorlage</h1>
<div class="article-meta">Grundversicherung auf den 1. Januar {YEAR} wechseln · Brief in 2 Minuten</div>
<p class="kk-lead">Die Kündigung der Grundversicherung muss bis am <strong>{DEADLINE}</strong> bei deiner Kasse <strong>eingetroffen</strong> sein. Der Poststempel zählt nicht. <span id="kd-left"></span></p>
<div id="wechsel" class="kd-wechsel" hidden></div>
<div class="kd-ctas"><a class="kk-cta" href="#vorlage">Kündigung jetzt erstellen &darr;</a><a class="kd-cta-sec" id="kd-compare" href="/#kk-rechner">Zuerst vergleichen: lohnt sich der Wechsel? &rarr;</a></div>

<h2>So wechselst du in vier Schritten</h2>
<ol>
<li><strong>Neue Kasse wählen</strong> und dort für den 1. Januar {YEAR} anmelden. Sie muss dich ohne Gesundheitsfragen aufnehmen.</li>
<li><strong>Bisherige Kasse kündigen, direkt hier:</strong> Im <a href="#vorlage">Kündigungs-Editor</a> wählst du deine Kasse, gibst Name und Adresse ein und unterschreibst mit Maus oder Finger. Den fertigen Brief mit der richtigen Adresse schicken wir dir als PDF per Mail.</li>
<li><strong>Abschicken:</strong> per Mail, wenn deine Kasse das annimmt (steht beim Brief), sonst per Post, spätestens eine Woche vor dem {DEADLINE}. Ein Einschreiben ist nicht Pflicht, beweist aber den Eingang.</li>
<li><strong>Bestätigung abwarten.</strong> Die neue Kasse bestätigt dir und der alten Kasse schriftlich, dass du bei ihr versichert bist. Bis dahin bleibt die alte Versicherung bestehen, du bist also nie ohne Schutz.</li>
</ol>
<a class="kk-cta" href="#vorlage">Zum Kündigungs-Editor &darr;</a>
<p>Wichtig: Wer bis 31. Dezember noch offene Prämien oder Kostenbeteiligungen bei der bisherigen Kasse hat, kann nicht wechseln. Offene Rechnungen vorher bezahlen.</p>

<h2 id="vorlage">Kündigungsbrief erstellen</h2>
<p>Kasse wählen, Angaben eintragen, unterschreiben. Du bekommst das PDF sofort und als Kopie per Mail. Abschicken an die Kasse tust du selbst.</p>
<div class="kd-form">
  <div class="full"><label for="kd-kasse">Deine bisherige Kasse</label><select id="kd-kasse"></select></div>
  <div><label for="kd-name">Vorname und Name</label><input id="kd-name" autocomplete="name"></div>
  <div><label for="kd-birth">Geburtsdatum</label><input id="kd-birth" autocomplete="bday" inputmode="numeric" placeholder="12.03.1985"></div>
  <div><label for="kd-street">Strasse und Nr.</label><input id="kd-street" autocomplete="address-line1"></div>
  <div class="kd-plzort"><div><label for="kd-plz">PLZ</label><input id="kd-plz" autocomplete="postal-code" inputmode="numeric" maxlength="4" placeholder="8004"></div><div><label for="kd-ort">Ort</label><input id="kd-ort" autocomplete="address-level2" placeholder="Zürich"></div></div>
  <div><label for="kd-email">E-Mail</label><input id="kd-email" type="email" autocomplete="email" placeholder="du@beispiel.ch"><div class="kd-hint">Dorthin schicken wir dir das PDF als Kopie.</div></div>
  <div><label for="kd-nr">Versicherten-Nr. <span style="text-transform:none;font-weight:400;">(optional)</span></label><input id="kd-nr"><div class="kd-hint">Steht auf der Versichertenkarte.</div></div>
  <div class="full"><label for="kd-more">Kinder im selben Brief <span style="text-transform:none;font-weight:400;">(optional, eine Person pro Zeile, mit Geburtsdatum)</span></label><textarea id="kd-more" rows="2" placeholder="Anna Muster, 12.03.2015"></textarea><div class="kd-hint">Erwachsene kündigen je selbst, mit eigenem Brief und eigener Unterschrift. Das verlangen mehrere Kassen.</div></div>
  <fieldset class="kd-zusatz full"><legend>Zusatzversicherung bei dieser Kasse <span class="tip" tabindex="0" aria-label="Info">i<span>Eine Zusatzversicherung zu wechseln lohnt sich selten. Die neue Kasse darf Gesundheitsfragen stellen, Vorbehalte machen oder dich ablehnen, und mit dem Alter wird der Einstieg teurer. Berater drängen trotzdem oft dazu, weil sie dafür bis zu 16 Monatsprämien Provision erhalten. <a href="/blog/provisionen-zusatzversicherung/">Mehr dazu</a></span></span></legend>
    <label class="kd-check"><input type="radio" name="kd-zusatz" value="keine"> Habe ich nicht</label>
    <label class="kd-check"><input type="radio" name="kd-zusatz" value="behalten" checked> Behalten, nur die Grundversicherung kündigen <span class="kd-reco">empfohlen</span></label>
    <label class="kd-check"><input type="radio" name="kd-zusatz" value="kuendigen"> Auch kündigen</label>
    <div class="kd-warn" id="kd-zusatz-warn" hidden><strong>Gut überlegen.</strong> Eine Zusatzversicherung zu wechseln lohnt sich selten. Die neue Kasse darf Gesundheitsfragen stellen, Vorbehalte machen oder dich ablehnen, und mit dem Alter wird der Einstieg teurer. Berater drängen trotzdem oft dazu, weil sie dafür bis zu 16 Monatsprämien Provision erhalten. Zudem gelten eigene Fristen, oft drei Monate auf Ende Jahr. Dann ist es für {YEAR} schon zu spät und die Kündigung gilt erst auf den nächstmöglichen Termin. Kündige die Zusatzversicherung erst, wenn die neue schriftlich zugesagt hat. <a href="/blog/provisionen-zusatzversicherung/">Warum Berater zum Wechsel drängen</a></div>
  </fieldset>
</div>
<div class="kd-sign">
  <label for="kd-pad">Unterschrift</label>
  <canvas id="kd-pad" aria-label="Hier unterschreiben"></canvas>
  <div class="kd-sign-row"><span id="kd-pad-hint"></span><button type="button" id="kd-pad-clear" class="kd-link">Neu zeichnen</button></div>
</div>
<div id="kd-kanal" class="kd-kanal"></div>
<label class="kd-consent"><input type="checkbox" id="kd-wecker" checked> <span>Nächstes Jahr die besten Kassen für mich ins Postfach (1 Mail im Jahr)</span></label>
<div class="kd-actions"><button id="kd-send">PDF per Mail zuschicken</button><button id="kd-mail" class="sec" hidden>Mail an die Kasse vorbereiten</button><button id="kd-copy" class="sec">Text kopieren</button></div>
<div class="kd-terms">Mit dem Versand akzeptierst du unseren <a href="/datenschutz/#kuendigung" target="_blank">Datenschutz</a>: Wir speichern deine E-Mail-Adresse und die Angaben zum Wechsel, den Brief nur 60 Tage zum Abholen.</div>
<div id="kd-msg" class="kd-msg" role="status"></div>
<div id="kd-done" class="kd-done" hidden></div>
<div class="kd-preview-label">Vorschau</div>
<div id="kd-brief"></div>

<h2>Sonderfälle</h2>
<ul>
<li><strong>Nur das Modell oder die Franchise ändern, bei derselben Kasse:</strong> geht ebenfalls auf den 1. Januar. Die Frist steht in den Bedingungen deiner Kasse; sicher bist du, wenn du bis {DEADLINE} meldest.</li>
<li><strong>Kündigung auf Ende Juni:</strong> nur im Standardmodell mit Franchise 300, Eingang bis 31. März.</li>
<li><strong>Umzug ins Ausland oder Tod:</strong> die Versicherung endet ohne Frist mit dem Wegzug beziehungsweise dem Todestag.</li>
</ul>

<h2>Adressen aller Krankenkassen</h2>
<p>Adressen laut BAG-Verzeichnis der zugelassenen Krankenversicherer. Manche Kassen nennen auf ihrer Website zusätzlich eine eigene Adresse für Kündigungen, beide sind gültig. Die Spalte «Kündigung» zeigt, ob die Kasse auf ihrer Website ausdrücklich eine Kündigung der Grundversicherung per Mail annimmt (Stand {stand}). «Post» heisst: sie sagt nichts dazu oder verlangt einen Brief.</p>
<div class="kk-table-wrap"><table class="kk-table"><thead><tr><th>Kasse</th><th>Adresse</th><th>Kündigung</th></tr></thead><tbody>{addr_rows}</tbody></table></div>
<p class="kk-note">* Nur von der Mail-Adresse, die die Kasse von dir kennt.</p>

<div class="kk-faq"><h2>Häufige Fragen</h2>{"".join(f"<h3>{e(q)}</h3><p>{e(a)}</p>" for q, a in qa)}</div>
<p class="kk-note">Quellen: Bundesamt für Gesundheit (<a href="https://www.bag.admin.ch/de/praemien-und-kosten-antworten-auf-haeufige-fragen">Fragen zu Prämien und Wechsel</a>), <a href="https://www.bag.admin.ch/de/verzeichnisse-der-zugelassenen-kranken-und-rueckversicherer">Verzeichnis der zugelassenen Krankenversicherer</a>. Angaben ohne Gewähr.</p>

<script id="kd-data" type="application/json">{kd_data}</script>
<script src="/js/combobox.js"></script>
<script src="/js/kuendigung.js"></script>"""
    html_out = page(path, f"Krankenkasse kündigen {PREV}: Frist {DEADLINE.replace(' ' + str(PREV), '')}, Vorlage und Adressen",
                    f"Grundversicherung kündigen: bis {DEADLINE} muss die Kündigung bei der Kasse sein. Kostenlose Vorlage, Adressen aller Kassen, Schritt für Schritt.",
                    body, [breadcrumb([("Krankenkassen-Vergleich", "/"), ("Krankenkasse kündigen", path)]), faq(qa)])
    return path, html_out.replace("</style>", KUENDIGEN_CSS + "</style>", 1)



def pickup_page():
    """Abholseite für das Kündigungs-PDF aus der Mail. Erst der Klick auf den
    Knopf bestätigt die E-Mail-Adresse (Mailfilter öffnen Links, klicken aber
    keine Knöpfe). Nicht in der Sitemap, noindex."""
    path = "/krankenkasse-kuendigen/pdf/"
    body = f"""{crumbs_html([("Krankenkassen-Vergleich", "/"), ("Krankenkasse kündigen", "/krankenkasse-kuendigen/"), ("Dein PDF", path)])}
<h1>Deine Kündigung</h1>
<div id="kp">
  <p class="kk-lead">Ein Klick, und du hast dein PDF. Damit bestätigst du auch deine E-Mail-Adresse.</p>
  <button class="kk-cta kp-btn" id="kp-go">PDF herunterladen</button>
</div>
<div id="kp-msg" class="kk-note" role="status"></div>
<script>
(function () {{
  var API = 'https://zexpmaegqsayleaohiip.supabase.co/functions/v1/kuendigung-pdf';
  var t = new URLSearchParams(location.search).get('t') || '';
  var box = document.getElementById('kp'), msg = document.getElementById('kp-msg');
  var esc = function (s) {{ return String(s || '').replace(/[&<>"]/g, function (c) {{ return {{ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }}[c]; }}); }};
  if (!t) {{ box.innerHTML = '<p class="kk-lead">Dieser Link ist unvollständig. Öffne ihn direkt aus der Mail.</p>'; return; }}
  function go(btn) {{
    btn.disabled = true; btn.textContent = 'Einen Moment…'; msg.textContent = '';
    fetch(API, {{ method: 'POST', headers: {{ 'Content-Type': 'application/json' }}, body: JSON.stringify({{ action: 'abholen', t: t }}) }})
      .then(function (r) {{ return r.json(); }})
      .then(function (d) {{
        if (!d.ok) {{ msg.textContent = d.error || 'Das hat nicht geklappt.'; btn.disabled = false; btn.textContent = 'PDF herunterladen'; return; }}
        var weg = d.kanal === 'mail'
          ? 'Schick das PDF als Anhang an <a href="mailto:' + esc(d.ziel) + '">' + esc(d.ziel) + '</a>, von der Mail-Adresse, die ' + esc(d.kasse) + ' von dir kennt.' + (d.signiert ? '' : ' Im PDF fehlt die Unterschrift: ausdrucken, unterschreiben, einscannen, oder neu erstellen mit Unterschrift.')
          : d.kanal === 'portal' ? 'Lade das PDF in ' + esc(d.ziel) + ' hoch oder schick es per Post.'
          : 'Druck das PDF aus und schick es per Post an ' + esc(d.kasse) + '.' + (d.signiert ? '' : ' Vorher von Hand unterschreiben, im PDF fehlt die Unterschrift.');
        var neu = (d.neu
          ? '<strong>Bei ' + esc(d.neu) + ' anmelden</strong>, online in etwa 10 Minuten.' + (d.neu_url ? ' <a href="' + esc(d.neu_url) + '?utm_source=abovergleich.com&utm_medium=affiliate&utm_campaign=kk-wechsel" target="_blank" rel="noopener sponsored">Zu ' + esc(d.neu) + ' &rarr;</a>' : '')
          : '<strong>Bei der neuen Kasse anmelden</strong>, online in etwa 10 Minuten. <a href="/#kk-rechner">Günstigste Kasse finden &rarr;</a>') +
          '<ul class="kp-list"><li>Beginn: 1. Januar</li><li>AHV-Nummer (756…, steht auf deiner Versichertenkarte)</li>' +
          '<li>Franchise und Modell, das du gewählt hast</li><li>beim Hausarzt- oder HMO-Modell: deine Praxis</li></ul>' +
          'Gesundheitsfragen gibt es in der Grundversicherung keine. Fragt das Formular danach, geht es um eine Zusatzversicherung, die du nicht abschliessen musst.';
        box.innerHTML = '<p class="kk-lead"><strong>E-Mail-Adresse bestätigt.</strong> Dein PDF wird heruntergeladen. <a href="' + esc(d.url) + '">Nicht gestartet?</a></p>' +
          '<h2>So geht es weiter</h2><ol>' +
          '<li><strong>Abschicken:</strong> ' + weg + ' Eintreffen muss die Kündigung bis ' + esc(d.deadline) + '.</li>' +
          '<li>' + neu + ' Spätestens bis Ende Dezember, am besten gleich jetzt.</li>' +
          '<li><strong>Bestätigung abwarten.</strong> Die neue Kasse meldet der alten, dass du bei ihr versichert bist. Bis dahin bleibst du bei der alten versichert.</li></ol>';
        location.href = d.url;
      }})
      .catch(function () {{ msg.textContent = 'Keine Verbindung. Bitte nochmals versuchen.'; btn.disabled = false; btn.textContent = 'PDF herunterladen'; }});
  }}
  document.getElementById('kp-go').onclick = function () {{ go(this); }};

  // Antworten aus den Erinnerungsmails: ?frage=anmeldung|bestaetigung|stopp&a=ja|nein
  var frage = new URLSearchParams(location.search).get('frage'), a = new URLSearchParams(location.search).get('a') || '';
  if (frage) {{
    document.querySelector('h1').textContent = 'Danke für deine Antwort';
    box.innerHTML = '<p class="kk-lead">Einen Moment…</p>';
    fetch(API, {{ method: 'POST', headers: {{ 'Content-Type': 'application/json' }}, body: JSON.stringify({{ action: 'antwort', t: t, frage: frage, a: a }}) }})
      .then(function (r) {{ return r.json(); }})
      .then(function (d) {{
        if (!d.ok) {{ box.innerHTML = '<p class="kk-lead">' + esc(d.error || 'Das hat nicht geklappt.') + '</p>'; return; }}
        var neu = d.neu ? esc(d.neu) : 'der neuen Kasse';
        var html = {{
          'anmeldung|ja': '<p class="kk-lead"><strong>Super.</strong> Jetzt fehlt nur noch die Bestätigung: Die neue Kasse meldet sich bei ' + esc(d.kasse) + '. Wir fragen Mitte Dezember nach, ob alles geklappt hat.</p>',
          'anmeldung|nein': '<p class="kk-lead">Kein Problem, das geht online in etwa 10 Minuten.</p><ul class="kp-list"><li>Beginn: 1. Januar</li><li>AHV-Nummer (756…, steht auf deiner Versichertenkarte)</li><li>Franchise und Modell</li><li>beim Hausarzt- oder HMO-Modell: deine Praxis</li></ul>' +
            (d.neu_url ? '<a class="kk-cta" href="' + esc(d.neu_url) + '?utm_source=abovergleich.com&utm_medium=affiliate&utm_campaign=kk-wechsel" target="_blank" rel="noopener sponsored">Zu ' + neu + ' &rarr;</a>' : '<a class="kk-cta" href="/#kk-rechner">Günstigste Kasse finden &rarr;</a>'),
          'bestaetigung|ja': '<p class="kk-lead"><strong>Perfekt, dein Wechsel ist durch.</strong> Ab 1. Januar bist du bei ' + neu + ' versichert.</p>',
          'bestaetigung|nein': '<p class="kk-lead">Ruf ' + esc(d.kasse) + ' an und frag nach, ob die Kündigung angekommen ist. Hast du sie per Mail geschickt, ist deine gesendete Mail der Beweis, per Einschreiben der Beleg der Post. Und frag bei ' + neu + ' nach, ob die Anmeldung durch ist: Erst wenn die neue Kasse sich bei der alten meldet, endet die alte Versicherung.</p>',
          'stopp|': '<p class="kk-lead">Erledigt, du bekommst zu diesem Brief keine Erinnerungen mehr.</p>'
        }}[frage + '|' + (frage === 'stopp' ? '' : a)] || '<p class="kk-lead">Gespeichert.</p>';
        box.innerHTML = html;
      }})
      .catch(function () {{ box.innerHTML = '<p class="kk-lead">Keine Verbindung. Bitte Link nochmals öffnen.</p>'; }});
  }}
}})();
</script>"""
    html_out = page(path, "Deine Kündigung herunterladen", "Kündigungsbrief für die Grundversicherung herunterladen.", body, [])
    html_out = html_out.replace('<meta name="robots" content="index, follow">', '<meta name="robots" content="noindex, nofollow">', 1)
    return path, html_out.replace("</style>", "  .kp-btn { border:none; cursor:pointer; font-family:inherit; font-size:16px; }\n  .kp-btn:disabled { opacity:.6; }\n  .kp-list { margin:8px 0 8px 18px; }\n  .kp-list li { margin:2px 0; }\n</style>", 1)


def write_sitemap(paths):
    today = date.today().isoformat()
    static = [("/", "1.0"), ("/hausratversicherung/", "0.9"), ("/methode/", "0.6"),
              ("/blog/beste-franchise-schweiz/", "0.7"), ("/blog/hmo-telmed-hausarzt-erklaert/", "0.7"),
              ("/blog/unfallversicherung-schweiz-ausland/", "0.7"), ("/blog/provisionen-zusatzversicherung/", "0.7"),
              ("/blog/krankenkasse-mit-26/", "0.7"),
              ("/blog/", "0.6")]
    items = [(p, pr) for p, pr in static] + [(p, "0.8") for p in paths]
    body = "\n".join(f"  <url>\n    <loc>{SITE}{p}</loc>\n    <lastmod>{today}</lastmod>\n    <priority>{pr}</priority>\n  </url>"
                     for p, pr in items)
    (ROOT / "sitemap.xml").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?>\n<!-- generiert von scripts/build_kk_pages.py -->\n'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{body}\n</urlset>\n', encoding="utf-8")


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
- [Krankenkasse kündigen]({SITE}/krankenkasse-kuendigen/): Frist {DEADLINE}, Kündigungs-Editor mit Unterschrift und PDF, Kündigungsweg (Mail oder Post) und Adresse jeder Kasse laut BAG.
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

## Schwesterseite

- [Handy-Abo Vergleich](https://handyabo.com/)
- [Internet-Abo Vergleich](https://handyabo.com/internet/)

## Datenquellen

- Prämien: Bundesamt für Gesundheit (BAG), opendata.swiss, Prämienjahre {PREV} und {YEAR}
- Kassennamen: BAG-Verzeichnis der zugelassenen Krankenversicherer
- Aktualisierung: jährlich Ende September nach Veröffentlichung der neuen Prämien
- Kündigung Grundversicherung: bis {DEADLINE} bei der Kasse eingetroffen

## Kontakt

- E-Mail: hello@handyabo.com
""", encoding="utf-8")


def bust_assets():
    """Hängt an geteilte CSS/JS-Dateien eine Prüfsumme (?v=…), auf allen Seiten.
    Ändert sich die Datei, ändert sich die URL, und Browser laden sie neu."""
    import hashlib
    assets = {}
    for rel in ("styles/shared.css", "js/combobox.js", "js/kuendigung.js", "rating-daten.json"):
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

    paths, cheapest = [], {}
    for c in CANTONS:
        ins_c = [{"name": INSURER_NAMES[str(i)], "premium": sum(p for p, _ in v) / len(v),
                  "change": sum(x for _, x in v) / len(v) * 100}
                 for (cc, i), v in ic.items() if cc == c]
        path, content = canton_page(c, by_canton_cur[c], prev_idx, cantons, ins_c, regions)
        write(path, content)
        paths.append(path)
        MAIN_REGION[c] = main_region(by_canton_cur[c], c)
        cheapest[c] = ranking(by_canton_cur[c], c, MAIN_REGION[c], 2500, prev_idx, n=1)[0]

    global AWARDS
    adm = RATING["verwaltung"]["kassen"]
    adm_cost = {int(k): v[max(v)]["verwaltung"] for k, v in adm.items() if v}
    AWARDS = build_awards.compute(RATING, YEAR, CANTONS, MAIN_REGION, adm_cost)
    write_award_badges()

    jojo = jojo_analysis()
    model_counts = defaultdict(int)
    for c in CANTONS:
        reg = main_region(by_canton_cur[c], c)
        best = min((r for r in by_canton_cur[c] if r["region"] == reg and r["franchise"] == 300), key=lambda r: r["premium"])
        model_counts[best["model_type"]] += 1

    top3_cur = top3_counts(cur, by_canton_cur)
    for i in KASSE_SLUG:
        path, content = kasse_page(i, cur, by_canton_cur, prev_idx, insurers, ic, top3_cur, kv, nu)
        write(path, content)
        paths.append(path)

    for fn in (lambda: hub_page(cantons, cheapest), lambda: report_page(cantons, insurers, nat, model_counts, jojo),
               lambda: kasse_hub(insurers, top3_cur), lambda: kuendigen_page(kv), lambda: rating_page(RATING), award_page):
        path, content = fn()
        write(path, content)
        paths.insert(0, path)

    path, content = pickup_page()   # nicht in die Sitemap
    write(path, content)

    # Startseite: Insights-Block ersetzen
    idx = ROOT / "index.html"
    s = idx.read_text(encoding="utf-8")
    prev2 = load_year(YEAR - 2)
    by_canton_prev2 = defaultdict(list)
    for r in prev2:
        by_canton_prev2[r["canton"]].append(r)
    _, ins_prev, nat_prev = analyse(prev, prev2, bestand)
    block = insights_block(cantons, insurers, nat,
                           top3_counts(prev, by_canton_prev), top3_counts(cur, by_canton_cur),
                           ins_prev, nat_prev, top3_counts(prev2, by_canton_prev2), jojo)
    new, n = re.subn(r"<!-- INSIGHTS:START.*?<!-- INSIGHTS:END -->", lambda _: block, s, flags=re.S)
    if n != 1:
        sys.exit("Insights-Marker in index.html nicht gefunden")
    n_insurers = len({r["insurer_id"] for r in cur})
    new = re.sub(r'(class="[^"]*insurer-count[^"]*">)\d+(<)', rf"\g<1>{n_insurers}\g<2>", new)
    new = re.sub(r'href="/krankenkassenpraemien-\d{4}/" class="nav-link">Prämien \d{4}',
                 f'href="/krankenkassenpraemien-{YEAR}/" class="nav-link">Prämien {YEAR}', new)
    idx.write_text(new, encoding="utf-8")

    meth = ROOT / "methode" / "index.html"
    ms = meth.read_text(encoding="utf-8")
    meth.write_text(re.sub(r'(class="[^"]*insurer-count[^"]*">)\d+(<)', rf"\g<1>{n_insurers}\g<2>", ms), encoding="utf-8")
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

    write_sitemap(paths)
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
