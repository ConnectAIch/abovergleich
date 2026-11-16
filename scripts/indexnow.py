#!/usr/bin/env python3
"""Geänderte Seiten per IndexNow melden (Bing, Yandex, Seznam, Naver).

    python3 scripts/indexnow.py --von <sha> --bis <sha> [--dry-run]
    python3 scripts/indexnow.py --alle [--dry-run]

Läuft automatisch nach jedem erfolgreichen Production-Deploy auf Vercel
(.github/workflows/indexnow.yml), mit dem vorherigen und dem neuen Deploy als
--von und --bis. Gemeldet wird nur, wessen Inhalt sich geändert hat, gemessen
mit demselben Fingerabdruck wie lastmod in der Sitemap (inhalt.py): ein
Neubau, der nur Prüfsummen an CSS/JS ändert, meldet nichts. Wer bei jedem
Deploy die ganze Sitemap schickt, bekommt 429 und gilt als Spam.

Warum es zählt: ChatGPTs Suche liest den Bing-Index, und Bing kommt sonst erst
beim nächsten Besuch des Crawlers vorbei. Google nutzt IndexNow nicht, dort
reicht die Sitemap mit echtem lastmod.

--alle schickt die ganze Sitemap, nur für den Notfall (z.B. neuer Schlüssel).
Der Schlüssel liegt als <KEY>.txt im Root der Website.

Antworten: 200 angenommen, 202 Schlüssel wird noch geprüft, 403 Schlüssel
falsch, 422 URL passt nicht zum Host, 429 zu viel.
"""
import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import inhalt  # noqa: E402

ROOT = inhalt.ROOT
HOST = "abovergleich.com"
SITE = f"https://{HOST}"
ENDPUNKT = "https://api.indexnow.org/indexnow"
MAX = 10000


def schluessel():
    for f in ROOT.glob("*.txt"):
        if re.fullmatch(r"[0-9a-f]{32}", f.stem) and f.read_text().strip() == f.stem:
            return f.stem
    return None


def sitemap_urls():
    return re.findall(r"<loc>([^<]+)</loc>", (ROOT / "sitemap.xml").read_text(encoding="utf-8"))


def geaendert(von, bis):
    """URLs aus der Sitemap, deren Inhalt sich zwischen zwei Commits geändert hat."""
    namen = subprocess.run(["git", "diff", "--name-only", "--diff-filter=AMR", f"{von}..{bis}", "--", "*index.html"],
                           cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    in_sitemap = set(sitemap_urls())
    g = inhalt._Git()
    raus = []
    for rel in namen:
        url = SITE + inhalt.datei_zu_url(rel)
        if url not in in_sitemap:
            continue
        alt, neu = g.show(von, rel), g.show(bis, rel)
        if neu is None:
            continue
        if alt is None or inhalt.fingerabdruck(alt) != inhalt.fingerabdruck(neu):
            raus.append(url)
    return raus


def melden(urls, key):
    body = json.dumps({"host": HOST, "key": key, "keyLocation": f"{SITE}/{key}.txt",
                       "urlList": urls[:MAX]}).encode()
    req = urllib.request.Request(ENDPUNKT, data=body, headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status
    except urllib.error.HTTPError as err:
        return err.code


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--von")
    ap.add_argument("--bis", default="HEAD")
    ap.add_argument("--alle", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    key = schluessel()
    if not key:
        print("✗ Kein IndexNow-Schlüssel (<32 hex>.txt) im Root.", file=sys.stderr)
        return 2
    if args.alle:
        urls = sitemap_urls()
    elif args.von:
        urls = geaendert(args.von, args.bis)
    else:
        ap.error("--von <sha> oder --alle")

    if not urls:
        print("Kein Seiteninhalt geändert, nichts zu melden.")
        return 0
    print(f"{len(urls)} Seite(n):")
    for u in urls[:20]:
        print("   " + u)
    if len(urls) > 20:
        print(f"   … und {len(urls) - 20} weitere")
    if args.dry_run:
        print("(dry-run, nichts gesendet)")
        return 0

    code = melden(urls, key)
    text = {200: "angenommen", 202: "angenommen, Schlüssel wird geprüft", 400: "fehlerhafte Anfrage",
            403: "Schlüssel ungültig", 422: "URL passt nicht zum Host", 429: "zu viele Anfragen"}.get(code, "unbekannt")
    if code in (200, 202):
        print(f"✓ IndexNow: HTTP {code} ({text}), {len(urls)} URLs gemeldet.")
        return 0
    print(f"✗ IndexNow: HTTP {code} ({text})", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
