#!/usr/bin/env python3
"""Eine Navigation für alle Seiten. build_kk_pages.py setzt sie in die
generierten Seiten ein und schreibt sie am Ende auch in die statischen Seiten
(Startseite, Blog, Methode, Hausrat, Rechtliches), in allen drei Sprachen.
Vorher hatten die Unterseiten nur Logo und «Zurück», die richtige Navigation
gab es nur auf der Startseite.

Die Sprachwahl verlinkt auf dieselbe Seite in der anderen Sprache. Generierte
Seiten geben ihre Gegenstücke mit (alts), statische Seiten finden sie über
i18n.STATIC."""
import re
from pathlib import Path

import i18n

ROOT = Path(__file__).parent.parent

LINKS = {
    "de": [("home", "#kk-rechner", "Prämienrechner"), ("rating", "", "Rating"), ("cantons", "", "Kantone"),
           ("kassen", "", "Kassen"), ("kuendigen", "", "Kündigen"), ("blog", "", "Ratgeber"),
           ("https://handyabo.com/", "", "Handy-Abo")],
    "fr": [("home", "#kk-rechner", "Calculateur"), ("rating", "", "Constance"), ("cantons", "", "Cantons"),
           ("kassen", "", "Caisses"), ("kuendigen", "", "Résilier"), ("blog", "", "Guide"),
           ("https://handyabo.com/fr/", "", "Abo mobile")],
    "en": [("home", "#kk-rechner", "Calculator"), ("rating", "", "Rating"), ("cantons", "", "Cantons"),
           ("kassen", "", "Insurers"), ("kuendigen", "", "Cancel"), ("blog", "", "Guide"),
           ("https://handyabo.com/en/", "", "Mobile plans")],
}
CTA = {"de": "Prämien vergleichen", "fr": "Comparer les primes", "en": "Compare premiums"}
MENU = {"de": "Menü", "fr": "Menu", "en": "Menu"}
SWITCH_LABEL = {"de": "Sprache", "fr": "Langue", "en": "Language"}


def nav_html(path="/", alts=None):
    lang = i18n.lang_of(path)
    if alts is None:
        key, _ = i18n.route_of(path)
        alts = dict(i18n.ROUTES[key]) if key else {}
    home = i18n.url("home", lang)

    def href(key, frag):
        return key if key.startswith("http") else i18n.url(key, lang) + frag

    def cls(key, frag):
        h = href(key, frag)
        here = h.startswith("/") and not frag and h != home and path.startswith(h)
        return "nav-link active" if here else "nav-link"
    links = "\n    ".join(f'<a href="{href(k, f)}" class="{cls(k, f)}">{t}</a>' for k, f, t in LINKS[lang])
    cur = ' aria-current="true"'
    switch = " ".join(
        (f'<a href="{alts.get(l) or i18n.url("home", l)}" hreflang="{i18n.HREFLANG[l]}" lang="{l}"'
         f'{cur if l == lang else ""}>{l.upper()}</a>')
        for l in i18n.LANGS)
    return f"""<nav>
  <a href="{home}" class="logo">abo<span>vergleich</span>.com</a>
  <div class="nav-right" id="nav-menu" onclick="if(event.target.closest('a'))this.classList.remove('open')">
    {links}
    <span class="nav-lang" aria-label="{SWITCH_LABEL[lang]}">{switch}</span>
    <a href="{home}#kk-rechner" class="nav-cta">{CTA[lang]}</a>
  </div>
  <button class="nav-burger" id="nav-burger" onclick="document.getElementById('nav-menu').classList.toggle('open');this.classList.toggle('open')" aria-label="{MENU[lang]}">
    <span></span><span></span><span></span>
  </button>
</nav>"""


def hreflang_html(alts):
    """<link rel="alternate"> für alle Sprachen, x-default ist Deutsch."""
    out = [f'<link rel="alternate" hreflang="{i18n.HREFLANG[l]}" href="https://abovergleich.com{alts[l]}">'
           for l in i18n.LANGS if alts.get(l)]
    if alts.get("de"):
        out.append(f'<link rel="alternate" hreflang="x-default" href="https://abovergleich.com{alts["de"]}">')
    return "\n".join(out)


def static_files():
    """(Pfad, Datei) aller statischen Seiten in allen Sprachen, die es gibt."""
    out = []
    for key in i18n.STATIC:
        for lang in i18n.LANGS:
            f = ROOT / i18n.file_for(key, lang)
            if f.exists():
                out.append((i18n.url(key, lang), f))
    return out


def apply_static():
    for rel, f in static_files():
        s = f.read_text(encoding="utf-8")
        new, n = re.subn(r"<nav>.*?</nav>", lambda _: nav_html(rel), s, count=1, flags=re.S)
        if n and new != s:
            f.write_text(new, encoding="utf-8")


if __name__ == "__main__":
    apply_static()
