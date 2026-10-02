#!/usr/bin/env python3
"""Sprachen der Website: Deutsch (Standard, ohne Präfix), Französisch (/fr/)
und Englisch (/en/). Eine Stelle für URLs, Kantonsnamen und Zahlenformate,
damit Generator, Navigation, Sitemap und Prüfskript dieselben Wege kennen.

Der Generator schaltet mit set_lang() um und schreibt jeden Text als
L(de, fr, en). Die statischen Seiten (Startseite, Blog, Rechtliches) liegen
je Sprache als eigene Datei; STATIC sagt, welche Datei zu welcher gehört.
"""
LANGS = ("de", "fr", "en")
LANG = "de"

HREFLANG = {"de": "de-CH", "fr": "fr-CH", "en": "en"}
OG_LOCALE = {"de": "de_CH", "fr": "fr_CH", "en": "en_GB"}
LANG_NAME = {"de": "Deutsch", "fr": "Français", "en": "English"}


def set_lang(lang):
    global LANG
    assert lang in LANGS, lang
    LANG = lang


def L(de, fr, en):
    """Text in der aktuellen Sprache."""
    return {"de": de, "fr": fr, "en": en}[LANG]


def each_lang(fn):
    """{lang: fn()} für alle Sprachen, danach wieder die aktuelle Sprache."""
    keep = LANG
    out = {}
    for lang in LANGS:
        set_lang(lang)
        out[lang] = fn()
    set_lang(keep)
    return out


# ── URLs ────────────────────────────────────────────────────────────────────

YEAR = 2027

ROUTES = {
    "home":       {"de": "/", "fr": "/fr/", "en": "/en/"},
    "cantons":    {"de": "/krankenkasse/", "fr": "/fr/caisse-maladie/", "en": "/en/health-insurance/"},
    "kassen":     {"de": "/kasse/", "fr": "/fr/caisses/", "en": "/en/insurers/"},
    "kuendigen":  {"de": "/krankenkasse-kuendigen/", "fr": "/fr/resilier-caisse-maladie/", "en": "/en/cancel-health-insurance/"},
    "report":     {"de": f"/krankenkassenpraemien-{YEAR}/", "fr": f"/fr/primes-caisse-maladie-{YEAR}/",
                   "en": f"/en/health-insurance-premiums-{YEAR}/"},
    "rating":     {"de": "/krankenkassen-rating/", "fr": "/fr/constance-des-primes/", "en": "/en/health-insurance-rating/"},
    "award":      {"de": "/krankenkassen-rating/award/", "fr": "/fr/constance-des-primes/prix/",
                   "en": "/en/health-insurance-rating/award/"},
    "methode":    {"de": "/methode/", "fr": "/fr/methode/", "en": "/en/methodology/"},
    "blog":       {"de": "/blog/", "fr": "/fr/guide/", "en": "/en/guide/"},
    "hausrat":    {"de": "/hausratversicherung/", "fr": "/fr/assurance-menage/", "en": "/en/household-insurance/"},
    "impressum":  {"de": "/impressum/", "fr": "/fr/mentions-legales/", "en": "/en/imprint/"},
    "datenschutz": {"de": "/datenschutz/", "fr": "/fr/protection-des-donnees/", "en": "/en/privacy/"},
    "kontakt":    {"de": "/kontakt/", "fr": "/fr/contact/", "en": "/en/contact/"},
    # Blog: DE-Slug -> Slug je Sprache
    "blog/beste-franchise-schweiz":        {"de": "/blog/beste-franchise-schweiz/",
                                            "fr": "/fr/guide/meilleure-franchise-suisse/",
                                            "en": "/en/guide/best-deductible-switzerland/"},
    "blog/hmo-telmed-hausarzt-erklaert":   {"de": "/blog/hmo-telmed-hausarzt-erklaert/",
                                            "fr": "/fr/guide/hmo-telmed-medecin-de-famille/",
                                            "en": "/en/guide/hmo-telmed-family-doctor-explained/"},
    "blog/krankenkasse-mit-26":            {"de": "/blog/krankenkasse-mit-26/",
                                            "fr": "/fr/guide/caisse-maladie-a-26-ans/",
                                            "en": "/en/guide/health-insurance-at-26/"},
    "blog/provisionen-zusatzversicherung": {"de": "/blog/provisionen-zusatzversicherung/",
                                            "fr": "/fr/guide/commissions-assurance-complementaire/",
                                            "en": "/en/guide/supplementary-insurance-commissions/"},
    "blog/unfallversicherung-schweiz-ausland": {"de": "/blog/unfallversicherung-schweiz-ausland/",
                                                "fr": "/fr/guide/assurance-accidents-suisse-etranger/",
                                                "en": "/en/guide/accident-insurance-switzerland-abroad/"},
    "blog/verwaltungskosten-krankenkassen": {"de": "/blog/verwaltungskosten-krankenkassen/",
                                             "fr": "/fr/guide/frais-administratifs-caisses-maladie/",
                                             "en": "/en/guide/health-insurer-admin-costs/"},
}

# Statische Seiten, je Sprache eine Datei: Route -> wird von site_nav und
# check_i18n.py gelesen. Generierte Seiten stehen nicht hier.
STATIC = ["home", "methode", "blog", "hausrat", "impressum", "datenschutz", "kontakt",
          "blog/beste-franchise-schweiz", "blog/hmo-telmed-hausarzt-erklaert", "blog/krankenkasse-mit-26",
          "blog/provisionen-zusatzversicherung", "blog/unfallversicherung-schweiz-ausland"]


def url(key, lang=None):
    return ROUTES[key][lang or LANG]


def file_for(key, lang):
    """Pfad der index.html relativ zum Repo."""
    p = ROUTES[key][lang].strip("/")
    return f"{p}/index.html" if p else "index.html"


def route_of(path):
    """Route-Schlüssel und Sprache zu einem Pfad, oder (None, Sprache)."""
    for key, m in ROUTES.items():
        for lang, p in m.items():
            if p == path:
                return key, lang
    return None, lang_of(path)


def lang_of(path):
    if path.startswith("/fr/"):
        return "fr"
    if path.startswith("/en/"):
        return "en"
    return "de"


# ── Kantone ─────────────────────────────────────────────────────────────────

# Code -> {Sprache: (Name, Slug)}. Deutsch steht in build_kk_pages.CANTONS.
CANTON_I18N = {
    "AG": {"fr": ("Argovie", "argovie"), "en": ("Aargau", "aargau")},
    "AI": {"fr": ("Appenzell Rhodes-Intérieures", "appenzell-rhodes-interieures"), "en": ("Appenzell Innerrhoden", "appenzell-innerrhoden")},
    "AR": {"fr": ("Appenzell Rhodes-Extérieures", "appenzell-rhodes-exterieures"), "en": ("Appenzell Ausserrhoden", "appenzell-ausserrhoden")},
    "BE": {"fr": ("Berne", "berne"), "en": ("Bern", "bern")},
    "BL": {"fr": ("Bâle-Campagne", "bale-campagne"), "en": ("Basel-Landschaft", "basel-landschaft")},
    "BS": {"fr": ("Bâle-Ville", "bale-ville"), "en": ("Basel-Stadt", "basel-stadt")},
    "FR": {"fr": ("Fribourg", "fribourg"), "en": ("Fribourg", "fribourg")},
    "GE": {"fr": ("Genève", "geneve"), "en": ("Geneva", "geneva")},
    "GL": {"fr": ("Glaris", "glaris"), "en": ("Glarus", "glarus")},
    "GR": {"fr": ("Grisons", "grisons"), "en": ("Graubünden", "graubuenden")},
    "JU": {"fr": ("Jura", "jura"), "en": ("Jura", "jura")},
    "LU": {"fr": ("Lucerne", "lucerne"), "en": ("Lucerne", "lucerne")},
    "NE": {"fr": ("Neuchâtel", "neuchatel"), "en": ("Neuchâtel", "neuchatel")},
    "NW": {"fr": ("Nidwald", "nidwald"), "en": ("Nidwalden", "nidwalden")},
    "OW": {"fr": ("Obwald", "obwald"), "en": ("Obwalden", "obwalden")},
    "SG": {"fr": ("Saint-Gall", "saint-gall"), "en": ("St. Gallen", "st-gallen")},
    "SH": {"fr": ("Schaffhouse", "schaffhouse"), "en": ("Schaffhausen", "schaffhausen")},
    "SO": {"fr": ("Soleure", "soleure"), "en": ("Solothurn", "solothurn")},
    "SZ": {"fr": ("Schwyz", "schwyz"), "en": ("Schwyz", "schwyz")},
    "TG": {"fr": ("Thurgovie", "thurgovie"), "en": ("Thurgau", "thurgau")},
    "TI": {"fr": ("Tessin", "tessin"), "en": ("Ticino", "ticino")},
    "UR": {"fr": ("Uri", "uri"), "en": ("Uri", "uri")},
    "VD": {"fr": ("Vaud", "vaud"), "en": ("Vaud", "vaud")},
    "VS": {"fr": ("Valais", "valais"), "en": ("Valais", "valais")},
    "ZG": {"fr": ("Zoug", "zoug"), "en": ("Zug", "zug")},
    "ZH": {"fr": ("Zurich", "zurich"), "en": ("Zurich", "zurich")},
}

# «im Kanton X» je Sprache: FR braucht den Artikel (dans le canton de Vaud,
# du Jura, des Grisons), EN nicht.
FR_DANS = {"JU": "dans le canton du Jura", "GR": "dans le canton des Grisons", "TI": "dans le canton du Tessin",
           "VS": "dans le canton du Valais", "VD": "dans le canton de Vaud", "AG": "dans le canton d'Argovie",
           "AI": "dans le canton d'Appenzell Rhodes-Intérieures", "AR": "dans le canton d'Appenzell Rhodes-Extérieures",
           "OW": "dans le canton d'Obwald", "UR": "dans le canton d'Uri"}


# ── Zahlen und Daten ────────────────────────────────────────────────────────

MONTHS = {
    "de": ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"],
    "fr": ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"],
    "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
}


def date_long(iso, lang=None):
    """'2026-11-30' -> '30. November 2026' / '30 novembre 2026' / '30 November 2026'."""
    lang = lang or LANG
    y, m, d = (int(x) for x in iso.split("-"))
    day = f"{d}." if lang == "de" else ("1er" if lang == "fr" and d == 1 else str(d))
    return f"{day} {MONTHS[lang][m - 1]} {y}"


def date_short(iso, lang=None):
    """'2026-09-30' -> '30.09.2026' (DE/FR) / '30/09/2026' (EN)."""
    lang = lang or LANG
    y, m, d = iso.split("-")
    return f"{d}/{m}/{y}" if lang == "en" else f"{d}.{m}.{y}"


def dec(v, n=1, lang=None):
    """Dezimalzahl: Komma auf DE und FR, Punkt auf EN."""
    s = f"{v:.{n}f}"
    return s if (lang or LANG) == "en" else s.replace(".", ",")
