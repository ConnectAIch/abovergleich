#!/usr/bin/env python3
"""Eine Navigation für alle Seiten. build_kk_pages.py setzt sie in die
generierten Seiten ein und schreibt sie am Ende auch in die statischen Seiten
(Startseite, Blog, Methode, Hausrat, Rechtliches). Vorher hatten die
Unterseiten nur Logo und «Zurück», die richtige Navigation gab es nur auf der
Startseite."""
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
LINKS = [
    ("/#kk-rechner", "Prämienrechner"),
    ("/krankenkassen-rating/", "Rating"),
    ("/krankenkasse/", "Kantone"),
    ("/kasse/", "Kassen"),
    ("/krankenkasse-kuendigen/", "Kündigen"),
    ("/blog/", "Ratgeber"),
    ("https://handyabo.com/", "Handy-Abo"),
]
STATIC = ["index.html", "methode/index.html", "hausratversicherung/index.html", "impressum/index.html",
          "datenschutz/index.html", "kontakt/index.html", "blog/index.html"]


def nav_html(path="/"):
    def cls(href):
        here = href.startswith("/") and href not in ("/#kk-rechner",) and path.startswith(href)
        return "nav-link active" if here else "nav-link"
    links = "\n    ".join(f'<a href="{h}" class="{cls(h)}">{t}</a>' for h, t in LINKS)
    return f"""<nav>
  <a href="/" class="logo">abo<span>vergleich</span>.com</a>
  <div class="nav-right" id="nav-menu" onclick="if(event.target.closest('a'))this.classList.remove('open')">
    {links}
    <a href="/#kk-rechner" class="nav-cta">Prämien vergleichen</a>
  </div>
  <button class="nav-burger" id="nav-burger" onclick="document.getElementById('nav-menu').classList.toggle('open');this.classList.toggle('open')" aria-label="Menü">
    <span></span><span></span><span></span>
  </button>
</nav>"""


def apply_static():
    files = [ROOT / f for f in STATIC] + sorted(ROOT.glob("blog/*/index.html"))
    for f in files:
        if not f.exists():
            continue
        rel = "/" + str(f.parent.relative_to(ROOT)).replace(".", "") + "/"
        rel = "/" if rel == "//" else rel
        s = f.read_text(encoding="utf-8")
        new, n = re.subn(r"<nav>.*?</nav>", lambda _: nav_html(rel), s, count=1, flags=re.S)
        if n and new != s:
            f.write_text(new, encoding="utf-8")


if __name__ == "__main__":
    apply_static()
