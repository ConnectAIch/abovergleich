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

def load_year(year):
    names = {int(k): v for k, v in INSURER_NAMES.items()}
    rows = build_rows(year, names)
    # nur Erwachsene mit Unfall, das ist die Referenz für alle Tabellen
    return [r for r in rows if r["age_class"] == "AKL-ERW" and r["accident_included"]]


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

<nav>
  <a href="/" class="logo">abo<span>vergleich</span>.com</a>
  <a href="/#kk-rechner" class="nav-back">Prämienrechner &rarr;</a>
</nav>

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
    desc = (f"Krankenkasse {name} {YEAR}: günstigste Grundversicherung ab CHF {chf(cheapest['premium'])} "
            f"({cheapest['insurer']}, Franchise 2'500). Prämien steigen im Schnitt {pct(info['change_pct'])}. "
            f"Offizielle BAG-Daten, alle Kassen.")

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
        rows.append(
            f'<tr><td><a href="/krankenkasse/{slug}/"><strong>{e(name)}</strong></a></td>'
            f'<td>{e(ch["insurer"])}<span class="sub">CHF {chf(ch["premium"])}, Franchise 2\'500</span></td>'
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
        f'<div class="kk-table-wrap"><table class="kk-table"><thead><tr><th>Kanton</th><th>Günstigste Kasse</th>'
        f'<th class="num">Ø Standard</th><th class="num">vs. {PREV}</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>',
        f'<p class="kk-note">Günstigste Kasse: Erwachsene, Franchise 2\'500, mit Unfall, alle Modelle, Hauptregion des Kantons. '
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


def insights_block(cantons, insurers, nat, top3_prev, top3_cur):
    big = sorted([x for x in insurers.values() if x["bestand"] >= MIN_BESTAND_RANKING], key=lambda x: x["change_pct"])
    lo, hi = big[:3], big[-3:][::-1]
    by_change = sorted(cantons.items(), key=lambda x: -x[1]["change_pct"])
    cons = sorted(set(top3_prev) | set(top3_cur), key=lambda i: -(top3_prev.get(i, 0) + top3_cur.get(i, 0)))[:5]

    def li(x):
        cls = "var(--red)" if x["change_pct"] > nat else "var(--green)"
        return f'<div><strong>{e(x["name"])}</strong> <span style="color:{cls};font-weight:600;">{pct(x["change_pct"])}</span></div>'

    def cli(c, v):
        return (f'<div><a href="/krankenkasse/{CANTONS[c][1]}/" style="color:var(--text);"><strong>{e(CANTONS[c][0])}</strong></a> '
                f'<span style="color:var(--muted);font-weight:600;">{pct(v["change_pct"])}</span></div>')

    canton_links = "".join(
        f'<a href="/krankenkasse/{slug}/" style="color:var(--accent-dark);">{e(name)}</a>'
        for name, slug in sorted(CANTONS.values()))
    trs = "".join(
        f'<tr style="border-bottom:1px solid var(--border);"><td style="padding:10px 12px;font-weight:600;">{kasse_link(i)}</td>'
        f'<td style="text-align:center;padding:10px 12px;">{top3_prev.get(i, 0)} / 26</td>'
        f'<td style="text-align:center;padding:10px 12px;">{top3_cur.get(i, 0)} / 26</td></tr>' for i in cons)

    card = 'style="background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:28px;margin-bottom:20px;"'
    col = 'style="font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin-bottom:10px;"'
    return f"""<!-- INSIGHTS:START (generiert von scripts/build_kk_pages.py) -->
<section class="insights-section" style="padding:80px 40px;background:var(--bg);">
  <div style="max-width:900px;margin:0 auto;">
    <div class="section-label">Datenanalyse</div>
    <h2 class="section-headline" style="margin-bottom:8px;">Krankenkassenprämien {PREV} vs. {YEAR}</h2>
    <p style="color:var(--muted);margin-bottom:32px;">Laut BAG steigt die mittlere Prämie {YEAR} um {BAG_OFFICIAL['change_pct']:.1f}&#8239;%. Unsere Auswertung aller Kassen und Kantone zeigt, wie unterschiedlich aufgeschlagen wird.</p>

    <div {card}>
      <h3 style="font-size:18px;font-weight:700;margin-bottom:6px;">Prämienveränderung pro Kasse (Standardmodell)</h3>
      <div style="font-size:14px;color:var(--muted);margin-bottom:18px;">Durchschnitt, gewichtet nach Versicherten: <strong style="color:var(--text);">{pct(nat)}</strong></div>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:20px;font-size:15px;line-height:2;">
        <div><div {col}>Am wenigsten</div>{"".join(li(x) for x in lo)}</div>
        <div><div {col}>Am meisten</div>{"".join(li(x) for x in hi)}</div>
      </div>
    </div>

    <div {card}>
      <h3 style="font-size:18px;font-weight:700;margin-bottom:6px;">Nach Kanton</h3>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:20px;font-size:15px;line-height:2;">
        <div><div {col}>Stärkster Anstieg</div>{"".join(cli(c, v) for c, v in by_change[:3])}</div>
        <div><div {col}>Schwächster Anstieg</div>{"".join(cli(c, v) for c, v in by_change[-3:][::-1])}</div>
      </div>
      <div style="margin-top:18px;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);">Günstigste Krankenkasse {YEAR} in deinem Kanton</div>
      <div style="display:flex;flex-wrap:wrap;gap:6px 14px;margin-top:8px;font-size:14px;">{canton_links}</div>
    </div>

    <div {card}>
      <h3 style="font-size:18px;font-weight:700;margin-bottom:6px;">Wer ist konstant günstig?</h3>
      <p style="font-size:14px;color:var(--muted);margin-bottom:14px;">In wie vielen Kantonen gehört die Kasse zu den 3 günstigsten im Standardmodell?</p>
      <div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;font-size:14px;">
        <thead><tr style="border-bottom:1px solid var(--border2);"><th style="text-align:left;padding:8px 12px;">Kasse</th><th style="padding:8px 12px;">{PREV}</th><th style="padding:8px 12px;">{YEAR}</th></tr></thead>
        <tbody>{trs}</tbody>
      </table></div>
    </div>

    <div style="font-size:12px;color:var(--muted);text-align:center;">Quelle: BAG · Erwachsene, Franchise 300, mit Unfall · <a href="/krankenkassenpraemien-{YEAR}/" style="color:var(--accent-dark);">Ganze Auswertung {YEAR}</a> · <a href="/kasse/" style="color:var(--accent-dark);">Alle Kassen</a> · <a href="/krankenkasse-kuendigen/" style="color:var(--accent-dark);">Kündigen bis {DEADLINE}</a></div>
  </div>
</section>
<!-- INSIGHTS:END -->"""



# ── Kassenseiten und Kündigung ─────────────────────────────────────────────

KASSE_SLUG = {}   # wird in main() gefüllt: BAG-Nummer -> Slug


def slugify(name):
    s = name.lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("è", "e"), ("é", "e"), ("’", ""), ("'", "")):
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def kasse_link(i, text=None):
    text = e(text or INSURER_NAMES[str(i)])
    return f'<a href="/kasse/{KASSE_SLUG[i]}/">{text}</a>' if i in KASSE_SLUG else text


def people(n):
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}".replace(".", ",") + " Mio."
    return chf(round(n, -3), 0)


def address_lines(kv, i):
    d = kv.get(i, {})
    return [d.get("name") or INSURER_NAMES[str(i)]] + d.get("address", [])


def kasse_page(i, cur, by_canton_cur, prev_idx, insurers, ic, top3_cur, kv):
    name = INSURER_NAMES[str(i)]
    path = f"/kasse/{KASSE_SLUG[i]}/"
    own = [r for r in cur if r["insurer_id"] == i]
    cants = sorted({r["canton"] for r in own} & set(CANTONS), key=lambda c: CANTONS[c][0])
    info = insurers.get(i)

    rows, first_in = [], []
    for c in cants:
        main = main_region(by_canton_cur[c], c)
        rk = ranking(by_canton_cur[c], c, main, 2500, prev_idx, n=999)
        pos = next((n for n, x in enumerate(rk, 1) if x["insurer_id"] == i), None)
        v = ic.get((c, i))
        chg = sum(x for _, x in v) / len(v) * 100 if v else None
        lvl = sum(p for p, _ in v) / len(v) if v else None
        if pos == 1:
            first_in.append(c)
        best = rk[pos - 1] if pos else None
        rows.append(
            f'<tr><td><a href="/krankenkasse/{CANTONS[c][1]}/">{e(CANTONS[c][0])}</a></td>'
            f'<td class="num">{"CHF " + chf(lvl, 0) if lvl else "–"}</td>'
            f'<td class="num {"kk-up" if (chg or 0) > 0 else "kk-down"}">{pct(chg) if chg is not None else "–"}</td>'
            f'<td>{("CHF " + chf(best["premium"])) if best else "–"}'
            f'{("<span class=sub>" + MODEL_LABEL[best["model"]] + " · " + e(best["tariff"]) + "</span>") if best else ""}</td>'
            f'<td class="num">{f"{pos} / {len(rk)}" if pos else "–"}</td></tr>')

    # Modellwechsel innerhalb der Kasse: Standard gegen günstigstes anderes Modell
    by_reg = defaultdict(list)
    for r in own:
        if r["franchise"] == 2500:
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

    title = f"{name} Prämien {YEAR}: Erhöhung je Kanton und günstigere Modelle"
    desc = (f"{name} {YEAR}: Standardprämie im Schnitt {pct(chg)} gegenüber {PREV}. "
            f"Alle Kantone, alle Modelle, Vergleich mit den anderen Kassen und Kündigungsadresse. Offizielle BAG-Daten.") if chg is not None else \
           (f"{name} {YEAR}: Prämien in allen Kantonen, Modelle und Vergleich mit den anderen Kassen. Offizielle BAG-Daten.")

    p = [crumbs_html([("Krankenkassen-Vergleich", "/"), ("Kassen", "/kasse/"), (name, path)])]
    p.append(f'<div class="article-badge">Prämien {YEAR}</div>')
    p.append(f"<h1>{e(name)} Prämien {YEAR}</h1>")
    p.append(f'<div class="article-meta">Offizielle Prämien des BAG · {len(cants)} {"Kanton" if len(cants) == 1 else "Kantone"}'
             f'{" · rund " + people(info["bestand"]) + " Versicherte" if info and info["bestand"] >= 1000 else ""}</div>')
    if chg is not None:
        p.append(f'<p class="kk-lead">{e(name)} erhöht die Prämie im Standardmodell {YEAR} im Schnitt um <strong>{pct(chg)}</strong> '
                 f'(Erwachsene, Franchise 300, gewichtet nach Versicherten je Kanton). Das ist {rel} die {BAG_OFFICIAL["change_pct"]:.1f}&#8239;%, '
                 f'um die laut BAG die mittlere Prämie über alle Kassen steigt.</p>')
    facts = []
    if chg is not None:
        facts.append((pct(chg), f"Standardprämie {YEAR} gegenüber {PREV}"))
    facts.append((f"{t3} von 26", "Kantonen, in denen die Kasse zu den 3 günstigsten im Standardmodell gehört"))
    if gap and gap > 0:
        facts.append((f"CHF {chf(gap, 0)}", f"pro Jahr spart im Median, wer bei {e(name)} vom Standard- ins günstigste andere Modell wechselt"))
    p.append('<div class="kk-facts">' + "".join(
        f'<div class="kk-fact"><div class="kk-fact-val">{v}</div><div class="kk-fact-label">{l}</div></div>' for v, l in facts) + "</div>")
    p.append(f'<a class="kk-cta" href="/?kasse={i}#kk-rechner">Mit deiner {e(name)}-Rechnung vergleichen &rarr;</a>')

    p.append(f"<h2>{e(name)} {YEAR} in jedem Kanton</h2>")
    p.append(f"<p>Ø Standard und Veränderung: Standardmodell, Franchise 300, mit Unfall, Mittel über die Prämienregionen. "
             f"Günstigster Tarif und Rang: Franchise 2'500, mit Unfall, alle Modelle, Hauptregion des Kantons, Rang unter allen Kassen.</p>")
    p.append(f'<div class="kk-table-wrap"><table class="kk-table"><thead><tr><th>Kanton</th><th class="num">Ø Standard</th>'
             f'<th class="num">vs. {PREV}</th><th>Günstigster Tarif</th><th class="num">Rang</th></tr></thead>'
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
               f"{name} gehört {YEAR} in {t3} von 26 Kantonen zu den drei günstigsten Kassen im Standardmodell"
               + (f" und ist in {len(first_in)} {'Kanton' if len(first_in) == 1 else 'Kantonen'} die günstigste Kasse überhaupt (Franchise 2'500)." if first_in else ".")
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
    ids = sorted(KASSE_SLUG, key=lambda i: INSURER_NAMES[str(i)].lower())
    rows = "".join(
        f'<tr><td>{kasse_link(i)}</td>'
        f'<td class="num">{people(insurers[i]["bestand"]) if i in insurers and insurers[i]["bestand"] >= 1000 else "–"}</td>'
        f'<td class="num {"kk-up" if i in insurers and insurers[i]["change_pct"] > 0 else ""}">{pct(insurers[i]["change_pct"]) if i in insurers else "–"}</td>'
        f'<td class="num">{top3_cur.get(i, 0)}</td></tr>' for i in ids)
    body = [
        crumbs_html([("Krankenkassen-Vergleich", "/"), ("Kassen", path)]),
        f'<div class="article-badge">Prämien {YEAR}</div>',
        f"<h1>Alle Krankenkassen: Prämien {YEAR} im Vergleich</h1>",
        f'<div class="article-meta">{len(ids)} Kassen mit Grundversicherung · Offizielle BAG-Daten</div>',
        f'<p class="kk-lead">Wie stark jede Kasse {YEAR} aufschlägt und wo sie zu den günstigsten gehört. '
        f'Ein Klick auf die Kasse zeigt alle Kantone, Modelle und die Kündigungsadresse.</p>',
        f'<div class="kk-table-wrap"><table class="kk-table"><thead><tr><th>Kasse</th><th class="num">Versicherte</th>'
        f'<th class="num">vs. {PREV}</th><th class="num">Top 3 in Kantonen</th></tr></thead><tbody>{rows}</tbody></table></div>',
        f'<p class="kk-note">Veränderung: Standardmodell, Franchise 300, gewichtet nach Versicherten je Kanton. '
        f'Top 3: in wie vielen der 26 Kantone die Kasse zu den drei günstigsten im Standardmodell gehört. '
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
  #kd-brief { background:#fff; color:#111; border:1px solid var(--border2); border-radius:8px; padding:32px 36px; font-family:Arial,Helvetica,sans-serif; font-size:14px; line-height:1.55; white-space:pre-wrap; margin:12px 0; }
  .kd-actions { display:flex; gap:10px; flex-wrap:wrap; }
  .kd-actions button { background:var(--accent); color:var(--text); border:none; border-radius:10px; padding:12px 18px; font-weight:700; cursor:pointer; font-family:inherit; }
  .kd-actions button.sec { background:var(--surface2); }
  .kd-days { font-family:'Plus Jakarta Sans',sans-serif; font-size:28px; font-weight:800; }
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
    data = [{"id": i, "name": INSURER_NAMES[str(i)], "address": address_lines(kv, i)} for i in ids]
    end = f"31. Dezember {PREV}"
    deadline_iso = f"{PREV}-11-30"
    addr_rows = "".join(f'<tr><td>{kasse_link(i)}</td><td>{e(", ".join(address_lines(kv, i)))}</td></tr>' for i in ids)
    qa = [
        (f"Bis wann muss ich die Krankenkasse kündigen?",
         f"Die Kündigung der Grundversicherung muss bis am {DEADLINE} bei der Kasse eingetroffen sein. "
         f"Massgebend ist das Datum, an dem die Kasse den Brief erhält, nicht der Poststempel. Der Wechsel gilt ab 1. Januar {YEAR}."),
        ("Muss ich per Einschreiben kündigen?",
         "Nicht zwingend, aber empfohlen. Mit dem Einschreiben kannst du beweisen, dass die Kündigung rechtzeitig angekommen ist."),
        ("Kann die neue Krankenkasse mich ablehnen?",
         "Nein. In der Grundversicherung muss jede Kasse in ihrem Tätigkeitsgebiet alle Personen aufnehmen, ohne Gesundheitsfragen. "
         "Bei Zusatzversicherungen ist das anders."),
        ("Was passiert mit meiner Zusatzversicherung?",
         "Nichts, wenn du sie nicht selbst kündigst. Die Zusatzversicherung kann bei der bisherigen Kasse bleiben, auch wenn du "
         "die Grundversicherung wechselst. Für sie gelten eigene Fristen im Vertrag."),
        ("Kann ich auch auf Ende Juni wechseln?",
         "Nur im Standardmodell mit Franchise 300. Dann muss die Kündigung bis 31. März eintreffen, der Wechsel gilt ab 1. Juli."),
    ]
    body = f"""{crumbs_html([("Krankenkassen-Vergleich", "/"), ("Krankenkasse kündigen", path)])}
<div class="article-badge">Frist {DEADLINE}</div>
<h1>Krankenkasse kündigen: bis {DEADLINE.replace(' ' + str(PREV), '')}, mit Vorlage</h1>
<div class="article-meta">Grundversicherung auf den 1. Januar {YEAR} wechseln · Brief in 2 Minuten</div>
<p class="kk-lead">Die Kündigung der Grundversicherung muss bis am <strong>{DEADLINE}</strong> bei deiner Kasse <strong>eingetroffen</strong> sein. Der Poststempel zählt nicht. <span id="kd-left"></span></p>
<a class="kk-cta" href="/#kk-rechner">Zuerst vergleichen: lohnt sich der Wechsel? &rarr;</a>

<h2>So wechselst du in vier Schritten</h2>
<ol>
<li><strong>Neue Kasse wählen</strong> und dort für den 1. Januar {YEAR} anmelden. Sie muss dich ohne Gesundheitsfragen aufnehmen.</li>
<li><strong>Bisherige Kasse kündigen</strong>, mit dem Brief unten. Unterschreiben nicht vergessen.</li>
<li><strong>Per Einschreiben schicken</strong>, spätestens eine Woche vor dem {DEADLINE}.</li>
<li><strong>Bestätigung abwarten.</strong> Die neue Kasse bestätigt dir und der alten Kasse schriftlich, dass du bei ihr versichert bist. Bis dahin bleibt die alte Versicherung bestehen, du bist also nie ohne Schutz.</li>
</ol>
<p>Wichtig: Wer bis 31. Dezember noch offene Prämien oder Kostenbeteiligungen bei der bisherigen Kasse hat, kann nicht wechseln. Offene Rechnungen vorher bezahlen.</p>

<h2 id="vorlage">Kündigungsbrief erstellen</h2>
<p>Der Brief entsteht nur in deinem Browser. Wir speichern und versenden nichts.</p>
<div class="kd-form">
  <div class="full"><label for="kd-kasse">Deine bisherige Kasse</label><select id="kd-kasse"></select></div>
  <div><label for="kd-name">Vorname und Name</label><input id="kd-name" autocomplete="name"></div>
  <div><label for="kd-nr">Versicherten-Nr. <span style="text-transform:none;font-weight:400;">(optional)</span></label><input id="kd-nr"></div>
  <div><label for="kd-street">Strasse und Nr.</label><input id="kd-street" autocomplete="street-address"></div>
  <div><label for="kd-city">PLZ und Ort</label><input id="kd-city" autocomplete="address-level2" placeholder="8004 Zürich"></div>
  <div class="full"><label for="kd-more">Weitere versicherte Personen im selben Brief <span style="text-transform:none;font-weight:400;">(optional, eine pro Zeile, mit Geburtsdatum)</span></label><textarea id="kd-more" rows="2" placeholder="Anna Muster, 12.03.2015"></textarea></div>
  <label class="kd-check full"><input type="checkbox" id="kd-zusatz" checked> Zusatzversicherungen behalten (nur die Grundversicherung kündigen)</label>
</div>
<div id="kd-brief"></div>
<div class="kd-actions"><button id="kd-print">Drucken oder als PDF speichern</button><button id="kd-copy" class="sec">Text kopieren</button></div>

<h2>Sonderfälle</h2>
<ul>
<li><strong>Nur das Modell oder die Franchise ändern, bei derselben Kasse:</strong> geht ebenfalls auf den 1. Januar. Die Frist steht in den Bedingungen deiner Kasse; sicher bist du, wenn du bis {DEADLINE} meldest.</li>
<li><strong>Kündigung auf Ende Juni:</strong> nur im Standardmodell mit Franchise 300, Eingang bis 31. März.</li>
<li><strong>Umzug ins Ausland oder Tod:</strong> die Versicherung endet ohne Frist mit dem Wegzug beziehungsweise dem Todestag.</li>
</ul>

<h2>Adressen aller Krankenkassen</h2>
<p>Laut BAG-Verzeichnis der zugelassenen Krankenversicherer. Manche Kassen nennen auf ihrer Website zusätzlich eine eigene Adresse für Kündigungen, beide sind gültig.</p>
<div class="kk-table-wrap"><table class="kk-table"><thead><tr><th>Kasse</th><th>Adresse</th></tr></thead><tbody>{addr_rows}</tbody></table></div>

<div class="kk-faq"><h2>Häufige Fragen</h2>{"".join(f"<h3>{e(q)}</h3><p>{e(a)}</p>" for q, a in qa)}</div>
<p class="kk-note">Quellen: Bundesamt für Gesundheit (<a href="https://www.bag.admin.ch/de/praemien-und-kosten-antworten-auf-haeufige-fragen">Fragen zu Prämien und Wechsel</a>), <a href="https://www.bag.admin.ch/de/verzeichnisse-der-zugelassenen-kranken-und-rueckversicherer">Verzeichnis der zugelassenen Krankenversicherer</a>. Angaben ohne Gewähr.</p>

<script src="/js/combobox.js"></script>
<script>
(function () {{
  var KASSEN = {json.dumps(data, ensure_ascii=False)};
  var END = {json.dumps(end)}, DEADLINE = new Date({json.dumps(deadline_iso)} + 'T23:59:59');
  var $ = function (id) {{ return document.getElementById(id); }};
  var sel = $('kd-kasse');
  sel.add(new Option('Bitte wählen', ''));
  KASSEN.forEach(function (k) {{ sel.add(new Option(k.name, k.id)); }});
  var q = new URLSearchParams(location.search).get('kasse');
  if (q) sel.value = q;
  // Aus dem Rechner (hochgeladene Rechnung), nur für dieses Browserfenster gespeichert
  try {{
    var pf = JSON.parse(sessionStorage.getItem('kd-prefill') || 'null');
    if (pf) {{
      if (!q && pf.kasse) sel.value = String(pf.kasse);
      ['name', 'street', 'city', 'nr'].forEach(function (k) {{ if (pf[k] && !$('kd-' + k).value) $('kd-' + k).value = pf[k]; }});
    }}
  }} catch (e) {{}}

  if (window.Combobox) Combobox.enhance(sel, {{ search: true, placeholder: 'Kasse suchen…' }});
  var days = Math.floor((DEADLINE - new Date()) / 86400000);
  if (days >= 0) $('kd-left').textContent = days === 0 ? 'Heute ist der letzte Tag.' : 'Noch ' + days + ' Tage.';

  function today() {{
    return new Date().toLocaleDateString('de-CH', {{ day: 'numeric', month: 'long', year: 'numeric' }});
  }}
  function render() {{
    var k = KASSEN.find(function (x) {{ return String(x.id) === sel.value; }});
    var name = $('kd-name').value.trim() || 'Vorname Name';
    var street = $('kd-street').value.trim() || 'Strasse Nr.';
    var city = $('kd-city').value.trim() || 'PLZ Ort';
    var ort = city.replace(/^\\d{{4}}\\s*/, '') || 'Ort';
    var more = $('kd-more').value.split('\\n').map(function (s) {{ return s.trim(); }}).filter(Boolean);
    var lines = [name, street, city, '', ''];
    lines = lines.concat(k ? k.address : ['Name der Krankenkasse', 'Adresse']);
    lines.push('', '', ort + ', ' + today(), '', '');
    lines.push('Kündigung der obligatorischen Krankenpflegeversicherung (Grundversicherung)');
    if ($('kd-nr').value.trim()) lines.push('Versicherten-Nr. ' + $('kd-nr').value.trim());
    lines.push('', 'Sehr geehrte Damen und Herren', '');
    lines.push((more.length ? 'Hiermit kündige ich die obligatorische Krankenpflegeversicherung nach KVG für mich und die folgenden Personen' :
      'Hiermit kündige ich meine obligatorische Krankenpflegeversicherung nach KVG') + ' fristgerecht auf den ' + END + (more.length ? ':' : '.'));
    more.forEach(function (m) {{ lines.push('- ' + m); }});
    if ($('kd-zusatz').checked) lines.push('', 'Die Zusatzversicherungen sind von dieser Kündigung nicht betroffen und laufen weiter.');
    lines.push('', 'Bitte bestätigen Sie mir den Eingang der Kündigung schriftlich.', '', 'Freundliche Grüsse', '', '', '', name);
    $('kd-brief').textContent = lines.join('\\n');
  }}
  ['kd-kasse', 'kd-name', 'kd-nr', 'kd-street', 'kd-city', 'kd-more', 'kd-zusatz'].forEach(function (id) {{
    $(id).addEventListener('input', render); $(id).addEventListener('change', render);
  }});
  $('kd-print').onclick = function () {{ render(); window.print(); }};
  $('kd-copy').onclick = function () {{
    render();
    var t = $('kd-brief').textContent;
    (navigator.clipboard ? navigator.clipboard.writeText(t) : Promise.reject()).then(
      function () {{ $('kd-copy').textContent = 'Kopiert'; }},
      function () {{ $('kd-copy').textContent = 'Bitte markieren und kopieren'; }});
  }};
  render();
}})();
</script>"""
    html_out = page(path, f"Krankenkasse kündigen {PREV}: Frist {DEADLINE.replace(' ' + str(PREV), '')}, Vorlage und Adressen",
                    f"Grundversicherung kündigen: bis {DEADLINE} muss die Kündigung bei der Kasse sein. Kostenlose Vorlage, Adressen aller Kassen, Schritt für Schritt.",
                    body, [breadcrumb([("Krankenkassen-Vergleich", "/"), ("Krankenkasse kündigen", path)]), faq(qa)])
    return path, html_out.replace("</style>", KUENDIGEN_CSS + "</style>", 1)



def write_sitemap(paths):
    today = date.today().isoformat()
    static = [("/", "1.0"), ("/hausratversicherung/", "0.9"), ("/methode/", "0.6"),
              ("/blog/beste-franchise-schweiz/", "0.7"), ("/blog/hmo-telmed-hausarzt-erklaert/", "0.7"),
              ("/blog/unfallversicherung-schweiz-ausland/", "0.7")]
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
- [Krankenkasse kündigen]({SITE}/krankenkasse-kuendigen/): Frist {DEADLINE}, Vorlage im Browser, Adressen aller Kassen laut BAG.
- [Hausrat & Haftpflicht]({SITE}/hausratversicherung/): Bedarfsrechner und Anbieter-Vergleich.
- [Unsere Methode]({SITE}/methode/): Wie wir vergleichen und warum wir keine Telefonnummern verlangen.

## Kantone

{kantone}

## Ratgeber

- [HMO, Telmed oder Hausarzt? Alle Modelle erklärt]({SITE}/blog/hmo-telmed-hausarzt-erklaert/)
- [Welche Franchise ist die beste?]({SITE}/blog/beste-franchise-schweiz/)
- [Unfallversicherung Schweiz & Ausland]({SITE}/blog/unfallversicherung-schweiz-ausland/)

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
    for rel in ("styles/shared.css", "js/combobox.js"):
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

    paths, cheapest = [], {}
    for c in CANTONS:
        ins_c = [{"name": INSURER_NAMES[str(i)], "premium": sum(p for p, _ in v) / len(v),
                  "change": sum(x for _, x in v) / len(v) * 100}
                 for (cc, i), v in ic.items() if cc == c]
        path, content = canton_page(c, by_canton_cur[c], prev_idx, cantons, ins_c, regions)
        write(path, content)
        paths.append(path)
        cheapest[c] = ranking(by_canton_cur[c], c, main_region(by_canton_cur[c], c), 2500, prev_idx, n=1)[0]

    jojo = jojo_analysis()
    model_counts = defaultdict(int)
    for c in CANTONS:
        reg = main_region(by_canton_cur[c], c)
        best = min((r for r in by_canton_cur[c] if r["region"] == reg and r["franchise"] == 300), key=lambda r: r["premium"])
        model_counts[best["model_type"]] += 1

    top3_cur = top3_counts(cur, by_canton_cur)
    for i in KASSE_SLUG:
        path, content = kasse_page(i, cur, by_canton_cur, prev_idx, insurers, ic, top3_cur, kv)
        write(path, content)
        paths.append(path)

    for fn in (lambda: hub_page(cantons, cheapest), lambda: report_page(cantons, insurers, nat, model_counts, jojo),
               lambda: kasse_hub(insurers, top3_cur), lambda: kuendigen_page(kv)):
        path, content = fn()
        write(path, content)
        paths.insert(0, path)

    # Startseite: Insights-Block ersetzen
    idx = ROOT / "index.html"
    s = idx.read_text(encoding="utf-8")
    block = insights_block(cantons, insurers, nat,
                           top3_counts(prev, by_canton_prev), top3_counts(cur, by_canton_cur))
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
        "vorjahressieger": {k: ({kk: vv for kk, vv in v.items() if kk != "rows"} if isinstance(v, dict) else v) for k, v in jojo.items()},
        "cantons": {c: {k: round(v, 2) for k, v in d.items()} for c, d in cantons.items()},
        "insurers": {str(i): {**d, "change_pct": round(d["change_pct"], 2), "bestand": round(d["bestand"])}
                     for i, d in insurers.items()},
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    write_sitemap(paths)
    bust_assets()
    print(f"✓ {len(paths)} Seiten, national {nat:+.2f}% (Standard F300), "
          f"Kantone {min(v['change_pct'] for v in cantons.values()):+.1f} bis {max(v['change_pct'] for v in cantons.values()):+.1f}%")


if __name__ == "__main__":
    main()
