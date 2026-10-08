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
# Frist-Leiste unten am Bildschirm: build_kk_pages.py setzt FRIST_ISO. Läuft
# site_nav allein (ohne Frist), bleibt eine vorhandene Leiste unverändert.
# Nicht auf der Kündigungsseite selbst (dort steht die Frist gross) und nicht
# auf Seiten ohne Bezug zur Krankenkasse.
FRIST_ISO = None
FRIST_SKIP = {"kuendigen", "hausrat", "impressum", "datenschutz", "kontakt"}
FRIST_TXT = {
    "de": ("Kündigen nur bis {d}.", "Bis dann muss die Kündigung bei deiner Kasse eingetroffen sein, sonst bleibst du ein weiteres Jahr.",
           "Kündigung erstellen", "Noch {n} Tage.", "Heute ist der letzte Tag.", "Schliessen"),
    "fr": ("Résilier jusqu’au {d} seulement.", "La résiliation doit être parvenue à votre caisse à cette date, sinon vous y restez une année de plus.",
           "Créer la résiliation", "Encore {n} jours.", "C’est le dernier jour.", "Fermer"),
    "en": ("Cancel by {d} only.", "Your cancellation must have reached your insurer by then, or you stay another year.",
           "Create cancellation", "{n} days left.", "Today is the last day.", "Close"),
}
FRIST_RE = re.compile(r"\n*<!-- frist -->.*?<!-- /frist -->", re.S)


def frist_html(path):
    """Leiste mit der Kündigungsfrist, leer wo sie nicht hingehört. Sie ist
    zuerst versteckt; das Skript zeigt sie nur bis zur Frist und nur, wenn
    sie in diesem Fenster nicht weggeklickt wurde."""
    if not FRIST_ISO:
        return ""
    key, _ = i18n.route_of(path)
    lang = i18n.lang_of(path)
    # auch nicht auf Unterseiten der Kündigung (PDF-Abholseite aus der Mail)
    if key in FRIST_SKIP or path.startswith(i18n.url("kuendigen", lang)):
        return ""
    head, body, cta, left, last, close = FRIST_TXT[lang]
    d = i18n.date_long(FRIST_ISO, lang).rsplit(" ", 1)[0]
    return f"""<!-- frist -->
<div class="frist-bar" id="frist-bar" data-frist="{FRIST_ISO}" hidden>
  <p><strong>{head.format(d=d)}</strong> {body} <span id="frist-left"></span></p>
  <a href="{i18n.url("kuendigen", lang)}" class="frist-cta">{cta} &rarr;</a>
  <button type="button" class="frist-x" aria-label="{close}">&times;</button>
</div>
<script>(function () {{
  var b = document.getElementById('frist-bar'), k = 'frist-' + b.dataset.frist;
  var n = Math.floor((new Date(b.dataset.frist + 'T23:59:59') - new Date()) / 864e5);
  try {{ if (n < 0 || sessionStorage.getItem(k)) return; }} catch (e) {{ if (n < 0) return; }}
  document.getElementById('frist-left').textContent = n === 0 ? {last!r} : {left!r}.replace('{{n}}', n);
  b.hidden = false;
  document.body.style.paddingBottom = b.offsetHeight + 'px';
  b.querySelector('.frist-x').onclick = function () {{
    b.hidden = true; document.body.style.paddingBottom = '';
    try {{ sessionStorage.setItem(k, '1'); }} catch (e) {{}}
  }};
}})();</script>
<!-- /frist -->"""


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
        if n and FRIST_ISO:
            new = FRIST_RE.sub("", new)
            bar = frist_html(rel)
            if bar:
                new = new.replace("</nav>", "</nav>\n" + bar, 1)
        if n and new != s:
            f.write_text(new, encoding="utf-8")


if __name__ == "__main__":
    apply_static()
