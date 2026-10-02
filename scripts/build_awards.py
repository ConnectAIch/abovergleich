#!/usr/bin/env python3
"""Preistreue-Award: die Auszeichnungen einer Edition, abgeleitet aus dem
Preistreue-Rating (build_rating.py). Nach dem Vorbild des handyabo Telco Award.

Der Award ist der Auszug aus dem Rating, den eine Kasse freiwillig herzeigt,
und der Anlass, über den man sie anschreiben kann. Nichts wird verkauft, ein
Link ist keine Bedingung, die Auswahl folgt allein der Zahl.

Drei Gruppen:
  Gesamtwertung   die drei besten Noten (Kassen ab 50'000 Versicherten)
  Kategorien      je ein Sieger pro Teilaspekt, gleichauf gewinnen alle
  Kantone         die beste Note in der Hauptregion jedes Kantons,
                  hier zählen auch die Regionalkassen

Die Badges (SVG) zeichnet dieses Modul, die Seite baut build_kk_pages.py.
Gold, Silber und Bronze nach Rang: Gold für alle entwertet das Gold.
"""
import html
import re

import i18n

PLACE = {1: "SIEGER", 2: "ZWEITER", 3: "DRITTER"}
PLACE_TEXT = {1: "Sieger", 2: "Zweiter", 3: "Dritter"}
PLACE_I18N = {"fr": {1: "VAINQUEUR", 2: "DEUXIÈME", 3: "TROISIÈME"}, "en": {1: "WINNER", 2: "SECOND", 3: "THIRD"}}

# Kategorie-Titel und Badge-Fakt in Französisch und Englisch, Schlüssel wie in CATEGORIES
CAT_I18N = {
    "dauerhaft-guenstig": {"fr": "Durablement avantageuse", "en": "Consistently cheap"},
    "stabilste-praemien": {"fr": "Primes les plus stables", "en": "Most stable premiums"},
    "fairste-sparmodelle": {"fr": "Modèles alternatifs les plus fiables", "en": "Fairest savings models"},
    "solideste-reserven": {"fr": "Réserves les plus solides", "en": "Strongest reserves"},
    "schlankste-verwaltung": {"fr": "Administration la plus légère", "en": "Leanest administration"},
}


def fact_i18n(key, v, lang):
    d = lambda x, n=1: i18n.dec(x, n, lang)
    if key == "dauerhaft-guenstig":
        return {"fr": f"Top 5 dans {round(v * 100)} % des années", "en": f"Top 5 in {round(v * 100)}% of years"}[lang]
    if key == "stabilste-praemien":
        if v < 0:
            return {"fr": f"{d(abs(v))} pt par an sous le marché", "en": f"{d(abs(v))} pts a year below market"}[lang]
        return {"fr": f"{d(v)} pt par an au-dessus du marché", "en": f"{d(v)} pts a year above market"}[lang]
    if key == "fairste-sparmodelle":
        if v >= 0:
            return {"fr": "Rabais maintenu", "en": "Discount retained"}[lang]
        return {"fr": f"Rabais {d(v)} pt par an", "en": f"Discount {d(v)} pts a year"}[lang]
    if key == "solideste-reserven":
        return {"fr": f"Taux de solvabilité {round(v)} %", "en": f"Solvency ratio {round(v)}%"}[lang]
    if key == "schlankste-verwaltung":
        return {"fr": f"CHF {round(v)} par assuré", "en": f"CHF {round(v)} per insured person"}[lang]
    raise KeyError(key)

# Kategorie: (Schlüssel, Titel, Rohwert-Quelle, bester = max/min, Badge-Fakt)
CATEGORIES = [
    ("dauerhaft-guenstig", "Dauerhaft günstig", "Am häufigsten unter den 5 günstigsten der Region seit 2020",
     lambda n, a: n["raw"]["konstanz"], max,
     lambda v: f"Top 5 in {round(v * 100)} % der Jahre"),
    ("stabilste-praemien", "Stabilste Prämien", "Schwächster Anstieg im günstigen Tarif, verglichen mit dem Markt",
     lambda n, a: n["raw"]["treue"], min,
     lambda v: (f"{abs(v):.1f} Pkt. pro Jahr unter dem Markt" if v < 0 else f"{v:.1f} Pkt. pro Jahr über dem Markt").replace(".", ",", 1)),
    ("fairste-sparmodelle", "Fairste Sparmodelle", "Neue Sparmodelle behalten ihren Rabatt am besten",
     lambda n, a: n["raw"]["rabatt"], max,
     lambda v: "Rabatt gehalten" if v >= 0 else f"Rabatt {v:.1f} Pkt. pro Jahr".replace(".", ",")),
    ("solideste-reserven", "Solideste Reserven", "Höchste Solvenzquote laut BAG",
     lambda n, a: n["raw"]["solvenz"], max,
     lambda v: f"Solvenzquote {round(v)} %"),
    ("schlankste-verwaltung", "Schlankste Verwaltung", "Tiefste Verwaltungskosten pro versicherte Person laut BAG",
     lambda n, a: a, min,
     lambda v: f"CHF {round(v)} pro Kopf"),
]


def slug(s):
    s = s.lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("é", "e"), ("è", "e")):
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def note_txt(v):
    return f"{v:.1f}".replace(".", ",")


def press_text(group, rank, name, label, year, y0):
    """Textbaustein, den eine Kasse übernehmen kann. Nennt die Grundversicherung,
    weil das Rating nur sie bewertet."""
    if group == "Gesamtwertung":
        first = (f"{name} ist im Preistreue-Award {year} von abovergleich.com die preistreueste Krankenkasse der Schweiz in der Grundversicherung."
                 if rank == 1 else
                 f"{name} belegt im Preistreue-Award {year} von abovergleich.com Platz {rank} der Gesamtwertung in der Grundversicherung.")
    elif group == "Kantone":
        first = (f"{name} ist im Preistreue-Award {year} von abovergleich.com die preistreueste Krankenkasse im "
                 f"{label} in der Grundversicherung.")
    else:
        first = f"{name} gewinnt im Preistreue-Award {year} von abovergleich.com die Kategorie «{label}» in der Grundversicherung."
    return (first + " Das unabhängige Rating zeigt, welche Krankenkassen über die Jahre günstig bleiben, "
            f"allein aus den Prämiendaten des Bundesamts für Gesundheit seit {y0}.")


def _fit(text, size, spacing, max_w):
    """textLength-Attribut, wenn die Zeile breiter als max_w würde (grobe Schätzung)."""
    est = len(text) * (size * 0.62 + spacing)
    return f' textLength="{max_w}" lengthAdjust="spacingAndGlyphs"' if est > max_w else ""


def compute(rating, year, cantons, main_region, adm_cost):
    """rating: build_rating.compute(); cantons: {code: (Name, slug)};
    main_region: {code: Region}; adm_cost: {id: Verwaltung pro Kopf, letztes Jahr}."""
    nat = rating["national"]
    big = [i for i, n in nat.items() if not n["regional"] and n["note"] is not None]
    awards = []

    def add(group, cat_key, cat_label, headline, rank, i, fact, link, raw=None, canton=None, note=None):
        name = nat[i]["name"]
        label_for_press = cat_label
        aid = f"{cat_key}-{slug(name)}"
        awards.append({
            "id": aid, "group": group, "rank": rank, "insurer": i, "name": name,
            "place": PLACE[rank], "category": cat_label, "headline": headline, "fact": fact, "link": link,
            "alt": f"abovergleich Preistreue-Award {year}: {headline}, {name}",
            "pressText": press_text(group, rank, name, label_for_press, year, rating["years"][0]),
            "_cat": cat_key, "_raw": raw, "_canton": canton, "_note": note,
        })

    rating_url = "https://abovergleich.com/krankenkassen-rating/"
    for rank, i in enumerate(sorted(big, key=lambda i: -nat[i]["note"])[:3], 1):
        head = (f"Preistreueste Krankenkasse {year}" if rank == 1
                else f"{PLACE_TEXT[rank]} der Gesamtwertung {year}")
        add("Gesamtwertung", "gesamt", "Gesamtwertung", head, rank, i,
            f"Preistreue {note_txt(nat[i]['note'])} / 10", rating_url, note=nat[i]["note"])

    for key, label, desc, get, best, fact in CATEGORIES:
        vals = {i: get(nat[i], adm_cost.get(i)) for i in big}
        vals = {i: v for i, v in vals.items() if v is not None}
        if not vals:
            continue
        top = best(vals.values())
        # gleichauf (auf drei Stellen) gewinnen alle
        for i in sorted(i for i, v in vals.items() if round(v, 3) == round(top, 3)):
            add("Kategorien", key, label, f"Sieger «{label}» {year}", 1, i, fact(vals[i]), rating_url, raw=vals[i])

    for c, (cname, cslug) in sorted(cantons.items(), key=lambda x: x[1][0]):
        reg = rating["regions"].get(f"{c}|{main_region.get(c)}", {})
        best_i = max(reg, key=lambda i: reg[i]["note"] or 0, default=None)
        if best_i is None or best_i not in nat:
            continue
        add("Kantone", f"kanton-{cslug}", f"Kanton {cname}", f"Preistreueste Krankenkasse im Kanton {cname} {year}", 1,
            best_i, f"Preistreue {note_txt(reg[best_i]['note'])} / 10", f"https://abovergleich.com/krankenkasse/{cslug}/",
            canton=c, note=reg[best_i]["note"])
    y0 = rating["years"][0]
    for a in awards:
        a["i18n"] = {"de": {k: a[k] for k in ("place", "category", "headline", "fact", "link", "alt", "pressText")}}
        for lang in ("fr", "en"):
            a["i18n"][lang] = localize(a, lang, year, y0)
    return awards


def canton_phrase(c, lang):
    """«dans le canton de Vaud» / «in the canton of Vaud»."""
    n = i18n.CANTON_I18N[c][lang][0]
    if lang == "fr":
        return i18n.FR_DANS.get(c, f"dans le canton de {n}")
    return f"in the canton of {n}"


def localize(a, lang, year, y0):
    """Texte eines Awards auf Französisch oder Englisch."""
    name, rank, group = a["name"], a["rank"], a["group"]
    T = lambda fr, en: fr if lang == "fr" else en
    award = T("Prix Constance des primes", "Price Consistency Award")
    if group == "Gesamtwertung":
        category = T("Classement général", "Overall ranking")
        headline = (T(f"Caisse-maladie la plus constante {year}", f"Most price-consistent health insurer {year}") if rank == 1 else
                    T(f"{rank}e du classement général {year}", f"{['', 'First', 'Second', 'Third'][rank]} in the overall ranking {year}"))
        fact = T(f"Constance {i18n.dec(a['_note'], 1, lang)} / 10", f"Price consistency {i18n.dec(a['_note'], 1, lang)} / 10")
        link = f"https://abovergleich.com{i18n.url('rating', lang)}"
        first = (T(f"{name} est, dans le {award} {year} d’abovergleich.com, la caisse-maladie aux primes les plus constantes de Suisse dans l’assurance de base.",
                   f"In the abovergleich.com {award} {year}, {name} is the most price-consistent health insurer in Switzerland for basic insurance.")
                 if rank == 1 else
                 T(f"{name} se classe {rank}e du classement général du {award} {year} d’abovergleich.com dans l’assurance de base.",
                   f"{name} ranks {['', 'first', 'second', 'third'][rank]} overall in the abovergleich.com {award} {year} for basic insurance."))
    elif group == "Kantone":
        c = a["_canton"]
        ph = canton_phrase(c, lang)
        category = T(ph.replace("dans le ", "").replace("dans l’", "").capitalize(), f"Canton of {i18n.CANTON_I18N[c]['en'][0]}")
        headline = T(f"Caisse-maladie la plus constante {ph} {year}", f"Most price-consistent health insurer {ph} {year}")
        fact = T(f"Constance {i18n.dec(a['_note'], 1, lang)} / 10", f"Price consistency {i18n.dec(a['_note'], 1, lang)} / 10")
        link = f"https://abovergleich.com{i18n.url('cantons', lang)}{i18n.CANTON_I18N[c][lang][1]}/"
        first = T(f"{name} est, dans le {award} {year} d’abovergleich.com, la caisse-maladie aux primes les plus constantes {ph} dans l’assurance de base.",
                  f"In the abovergleich.com {award} {year}, {name} is the most price-consistent health insurer {ph} for basic insurance.")
    else:
        category = CAT_I18N[a["_cat"]][lang]
        headline = T(f"Vainqueur « {category} » {year}", f"Winner “{category}” {year}")
        fact = fact_i18n(a["_cat"], a["_raw"], lang)
        link = f"https://abovergleich.com{i18n.url('rating', lang)}"
        first = T(f"{name} remporte la catégorie « {category} » du {award} {year} d’abovergleich.com dans l’assurance de base.",
                  f"{name} wins the “{category}” category of the abovergleich.com {award} {year} for basic insurance.")
    press = first + T(" Cette notation indépendante montre quelles caisses-maladie restent avantageuses au fil des ans, "
                      f"uniquement sur la base des primes publiées par l’Office fédéral de la santé publique depuis {y0}.",
                      " The independent rating shows which health insurers stay cheap over the years, "
                      f"based solely on premium data from the Federal Office of Public Health since {y0}.")
    return {"place": PLACE_I18N[lang][rank], "category": category, "headline": headline, "fact": fact, "link": link,
            "alt": T(f"abovergleich {award} {year} : {headline}, {name}", f"abovergleich {award} {year}: {headline}, {name}"),
            "pressText": press}


def loc(a, lang):
    """Award mit den Texten einer Sprache (für Badges und Seite)."""
    return {**a, **a["i18n"][lang], "lang": lang}


# ── Badges ──────────────────────────────────────────────────────────────────

def _palette(rank, dark):
    if rank == 2:
        m = ("#fbfbfa", "#e3e3df", "#c6c6c0", "#a3a39c"); kante = "#83837c"
        acc = "#dcdcd6" if dark else "#6e6e68"
        ring = "rgba(220,220,214,0.38)" if dark else "rgba(110,110,104,0.42)"
        edge = "rgba(220,220,214,0.24)" if dark else "#d3d1cb"
        inner = "rgba(220,220,214,0.22)" if dark else "rgba(110,110,104,0.30)"
    elif rank == 3:
        m = ("#f7dcbd", "#dda86f", "#c2854a", "#9d6533"); kante = "#855327"
        acc = "#dda86f" if dark else "#8a5a2b"
        ring = "rgba(221,168,111,0.40)" if dark else "rgba(138,90,43,0.42)"
        edge = "rgba(221,168,111,0.24)" if dark else "#dbcdbc"
        inner = "rgba(221,168,111,0.22)" if dark else "rgba(138,90,43,0.30)"
    else:
        m = ("#ffeea6", "#fed001", "#eab900", "#c49400"); kante = "#a97f00"
        acc = "#fed001" if dark else "#a07a00"
        ring = "rgba(254,208,1,0.42)" if dark else "rgba(160,122,0,0.45)"
        edge = "rgba(254,208,1,0.26)" if dark else "#d6cebd"
        inner = "rgba(254,208,1,0.24)" if dark else "rgba(160,122,0,0.32)"
    return {
        "m": m, "kante": kante, "acc": acc, "ring": ring, "edge": edge, "inner": inner,
        "card": "#1c1917" if dark else "#ffffff", "line": "#3a342c" if dark else "#ded7c6",
        "mute": "#a89e90" if dark else "#6f6a61", "name": "#ffffff" if dark else "#1c1917",
        "gold": "#fed001" if dark else "#a07a00",
    }


def _lines(name, width=13):
    if len(name) <= width or " " not in name:
        return [name]
    words = name.split()
    best = None
    for k in range(1, len(words)):
        a, b = " ".join(words[:k]), " ".join(words[k:])
        score = max(len(a), len(b))
        if best is None or score < best[0]:
            best = (score, [a, b])
    return best[1]


BADGE_TOP = {   # (Zeile 1 klein, Zeile 2 Award) im Hochformat; Querformat: eine Zeile
    "de": ("GRUNDVERSICHERUNG", "PREISTREUE-AWARD {y}", "PREISTREUE-AWARD {y} · GRUNDVERSICHERUNG"),
    "fr": ("ASSURANCE DE BASE", "PRIX CONSTANCE DES PRIMES {y}", "CONSTANCE DES PRIMES {y} · ASSURANCE DE BASE"),
    "en": ("BASIC HEALTH INSURANCE", "PRICE CONSISTENCY AWARD {y}", "PRICE CONSISTENCY AWARD {y} · BASIC INSURANCE"),
}
# Schriftgrösse und Laufweite: (Zeile 2 Hochformat, Kopfzeile Querformat). Die
# deutschen Werte sind die der verschickten Edition und bleiben, wie sie sind.
BADGE_SIZE = {"de": ((11.5, 1.8), (8.5, 1.3)), "fr": ((9.5, 1.0), (7.5, 0.6)), "en": ((10, 1.2), (7.5, 0.6))}


def svg_hoch(a, year, dark=False):
    p = _palette(a["rank"], dark)
    e = html.escape
    t1, t2, _ = BADGE_TOP[a.get("lang", "de")]
    t2 = t2.format(y=year)
    (s2, ls2), _ = BADGE_SIZE[a.get("lang", "de")]
    lines = _lines(a["name"])
    cat = e(a["category"].upper())
    cat_size = 11 if len(cat) <= 20 else 9.5
    if len(lines) > 1:
        name_svg = (f'<text class="v" x="105" y="238" text-anchor="middle" font-size="22" fill="{p["name"]}">{e(lines[0])}</text>\n'
                    f'  <text class="v" x="105" y="264" text-anchor="middle" font-size="22" fill="{p["name"]}">{e(lines[1])}</text>')
    else:
        size = 28 if len(a["name"]) <= 10 else 23
        name_svg = f'<text class="v" x="105" y="252" text-anchor="middle" font-size="{size}" fill="{p["name"]}">{e(a["name"])}</text>'
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="240" height="384" viewBox="0 0 210 336" role="img" aria-label="{e(a['alt'])}">
  <title>{e(a['alt'])}</title>
  <style>.s{{font-family:'Helvetica Neue',Helvetica,Arial,sans-serif}}.v{{font-family:Georgia,'Times New Roman',serif}}</style>
  <defs>
    <linearGradient id="metall" x1="0.18" y1="0" x2="0.72" y2="1">
      <stop offset="0%" stop-color="{p['m'][0]}"/><stop offset="30%" stop-color="{p['m'][1]}"/>
      <stop offset="58%" stop-color="{p['m'][2]}"/><stop offset="100%" stop-color="{p['m'][3]}"/>
    </linearGradient>
    <linearGradient id="glanz" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#ffffff" stop-opacity="0.42"/><stop offset="52%" stop-color="#ffffff" stop-opacity="0"/>
    </linearGradient>
  </defs>
  <rect x="0.5" y="0.5" width="209" height="335" rx="13.5" fill="{p['card']}" stroke="{p['edge']}"/>
  <rect x="6.5" y="6.5" width="197" height="323" rx="9" fill="none" stroke="{p['inner']}"/>
  <text class="s" x="107" y="22" text-anchor="middle" font-size="9" font-weight="700" letter-spacing="2.2" fill="{p['mute']}"{_fit(t1, 9, 2.2, 186)}>{e(t1)}</text>
  <text class="s" x="106" y="40" text-anchor="middle" font-size="{s2}" font-weight="700" letter-spacing="{ls2}" fill="{p['name']}"{_fit(t2, s2, ls2, 190)}>{e(t2)}</text>
  <line x1="6.5" y1="52" x2="203.5" y2="52" stroke="{p['line']}"/>
  <line x1="30" y1="55" x2="180" y2="55" stroke="{p['line']}"/>
  <circle cx="105" cy="117" r="50.5" fill="none" stroke="{p['ring']}" stroke-width="0.9"/>
  <circle cx="105" cy="117" r="43" fill="url(#metall)"/>
  <circle cx="105" cy="117" r="43" fill="url(#glanz)"/>
  <circle cx="105" cy="117" r="42.5" fill="none" stroke="{p['kante']}" stroke-opacity="0.5" stroke-width="1"/>
  <text class="v" x="105" y="130" text-anchor="middle" font-size="38" fill="#171412">{a['rank']}</text>
  <text class="s" x="108" y="186" text-anchor="middle" font-size="12.5" font-weight="700" letter-spacing="3.8" fill="{p['acc']}">{a['place']}</text>
  <text class="s" x="106" y="205" text-anchor="middle" font-size="{cat_size}" font-weight="600" letter-spacing="1.6" fill="{p['mute']}"{_fit(cat, cat_size, 1.6, 180)}>{cat}</text>
  {name_svg}
  <line x1="30" y1="291" x2="180" y2="291" stroke="{p['line']}"/>
  <line x1="6.5" y1="294" x2="203.5" y2="294" stroke="{p['line']}"/>
  <text class="s" x="106" y="312" text-anchor="middle" font-size="8.5" font-weight="700" letter-spacing="1.2" fill="{p['mute']}">{e(a['fact'].upper())}</text>
  <text class="s" x="105" y="326" text-anchor="middle" font-size="9" font-weight="700" letter-spacing="0.2" fill="{p['gold']}">abovergleich.com</text>
</svg>
"""


def svg_quer(a, year, dark=False):
    p = _palette(a["rank"], dark)
    e = html.escape
    name_size = 22 if len(a["name"]) <= 16 else 17
    top = BADGE_TOP[a.get("lang", "de")][2].format(y=year)
    _, (st, lt) = BADGE_SIZE[a.get("lang", "de")]
    bottom = f"{a['place']} · {a['category'].upper()}"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="375" height="109" viewBox="0 0 330 96" role="img" aria-label="{e(a['alt'])}">
  <title>{e(a['alt'])}</title>
  <style>.s{{font-family:'Helvetica Neue',Helvetica,Arial,sans-serif}}.v{{font-family:Georgia,'Times New Roman',serif}}</style>
  <defs>
    <clipPath id="c"><rect x="0" y="0" width="330" height="96" rx="12"/></clipPath>
    <linearGradient id="metall" x1="0.15" y1="0" x2="0.8" y2="1">
      <stop offset="0%" stop-color="{p['m'][0]}"/><stop offset="30%" stop-color="{p['m'][1]}"/>
      <stop offset="58%" stop-color="{p['m'][2]}"/><stop offset="100%" stop-color="{p['m'][3]}"/>
    </linearGradient>
  </defs>
  <g clip-path="url(#c)">
    <rect x="0" y="0" width="330" height="96" fill="{p['card']}"/>
    <rect x="0" y="0" width="78" height="96" fill="url(#metall)"/>
  </g>
  <rect x="0.5" y="0.5" width="329" height="95" rx="11.5" fill="none" stroke="{p['edge']}"/>
  <text class="v" x="39" y="59" text-anchor="middle" font-size="34" fill="#1c1917">{a['rank']}</text>
  <text class="s" x="94" y="22" font-size="{st}" font-weight="700" letter-spacing="{lt}" fill="{p['gold']}"{_fit(top, st, lt, 224)}>{e(top)}</text>
  <text class="v" x="94" y="50" font-size="{name_size}" fill="{p['name']}">{e(a['name'])}</text>
  <text class="s" x="94" y="69" font-size="9" font-weight="600" letter-spacing="1.2"{_fit(bottom, 9, 1.2, 224)}><tspan fill="{p['acc']}">{a['place']}</tspan><tspan fill="{p['mute']}"> · {e(a['category'].upper())}</tspan></text>
  <text class="s" x="94" y="85" font-size="8.5" font-weight="700" letter-spacing="0.2" fill="{p['gold']}">abovergleich.com</text>
</svg>
"""


VARIANTS = [("", svg_hoch, False), ("-dunkel", svg_hoch, True), ("-quer", svg_quer, False), ("-quer-dunkel", svg_quer, True)]
