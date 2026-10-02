#!/usr/bin/env python3
"""Prüft, dass die statischen Seiten in allen drei Sprachen zusammenpassen.

Die generierten Seiten (Kantone, Kassen, Rating, Kündigung) entstehen aus
einer Quelle und können nicht auseinanderlaufen. Die statischen Seiten
(Startseite, Blog, Methode, Hausrat, Rechtliches) liegen je Sprache als
eigene Datei. Ändert jemand die deutsche Seite und vergisst die
Übersetzungen, fällt das hier auf:

  - jede Seite aus i18n.STATIC gibt es in allen Sprachen
  - gleiche Struktur: gleiche Zahl an <h2>, <table>, <details> und dieselben ids
  - lang-Attribut, canonical und hreflang stimmen
  - interne Links bleiben in der eigenen Sprache
  - keine Gedankenstriche (— oder « – ») im sichtbaren Text
  - Warnung, wenn die deutsche Datei in git jünger ist als eine Übersetzung

    python3 scripts/check_i18n.py            # alles prüfen, Exit 1 bei Fehlern
    python3 scripts/check_i18n.py --staged   # nur, was gerade committet wird
"""
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import i18n  # noqa: E402

ROOT = Path(__file__).parent.parent
SITE = "https://abovergleich.com"


def visible(s):
    s = re.sub(r"<script.*?</script>|<style.*?</style>|<nav>.*?</nav>", "", s, flags=re.S)
    return re.sub(r"<[^>]+>", " ", s)


def shape(s):
    body = re.sub(r"<script.*?</script>|<style.*?</style>|<nav>.*?</nav>", "", s, flags=re.S)
    return {
        "h2": len(re.findall(r"<h2[\s>]", body)),
        "table": len(re.findall(r"<table[\s>]", body)),
        "details": len(re.findall(r"<details[\s>]", body)),
        "ids": sorted(set(re.findall(r'\sid="([^"]+)"', body))),
    }


def last_commit(path):
    r = subprocess.run(["git", "log", "-1", "--format=%ct", "--", path], cwd=ROOT, capture_output=True, text=True)
    return int(r.stdout.strip() or 0)


def staged():
    r = subprocess.run(["git", "diff", "--cached", "--name-only"], cwd=ROOT, capture_output=True, text=True)
    return set(r.stdout.split())


def main():
    only = staged() if "--staged" in sys.argv else None
    errors, warnings = [], []
    for key in i18n.STATIC:
        files = {l: i18n.file_for(key, l) for l in i18n.LANGS}
        if only is not None and not (set(files.values()) & only):
            continue
        src = {}
        for l, f in files.items():
            p = ROOT / f
            if not p.exists():
                errors.append(f"{key}: {f} fehlt")
                continue
            src[l] = p.read_text(encoding="utf-8")
        if "de" not in src:
            continue
        ref = shape(src["de"])
        for l, s in src.items():
            f = files[l]
            url = SITE + i18n.url(key, l)
            if not re.search(rf'<html lang="{l}"', s):
                errors.append(f"{f}: <html lang=\"{l}\"> fehlt")
            if f'<link rel="canonical" href="{url}">' not in s and key not in ("impressum", "datenschutz", "kontakt"):
                errors.append(f"{f}: canonical zeigt nicht auf {url}")
            for ll in i18n.LANGS:
                if f'hreflang="{i18n.HREFLANG[ll]}" href="{SITE}{i18n.url(key, ll)}"' not in s:
                    errors.append(f"{f}: hreflang {ll} fehlt oder zeigt falsch")
            if l != "de":
                sh = shape(s)
                for k in ("h2", "table", "details"):
                    if sh[k] != ref[k]:
                        errors.append(f"{f}: {sh[k]} <{k}>, Deutsch hat {ref[k]}")
                missing = set(ref["ids"]) - set(sh["ids"])
                if missing:
                    errors.append(f"{f}: ids fehlen gegenüber Deutsch: {', '.join(sorted(missing))}")
                body = re.sub(r"<nav>.*?</nav>", "", s, flags=re.S)
                for h in re.findall(r'href="(/[^"]*)"', body):
                    if not h.startswith(f"/{l}/") and not re.match(r"/(styles|js|favicon|apple-touch|og-image|_vercel)", h) \
                            and h not in (i18n.url(key, "de"),) and not h.startswith(("/impressum/", "/datenschutz/")):
                        errors.append(f"{f}: Link auf andere Sprache {h}")
                if last_commit(files["de"]) > last_commit(f) > 0:
                    warnings.append(f"{f}: Deutsch ({files['de']}) ist neuer, Übersetzung nachziehen?")
            dash = re.findall(r".{0,30}(?:—| – ).{0,30}", visible(s))
            if dash and l != "de":
                errors.append(f"{f}: Gedankenstrich im Text: {dash[0].strip()!r}")
    for w in warnings:
        print("!", w)
    for e in errors:
        print("✗", e)
    if errors:
        sys.exit(1)
    print(f"✓ i18n: {len(i18n.STATIC)} statische Seiten in {len(i18n.LANGS)} Sprachen stimmen überein")


if __name__ == "__main__":
    main()
