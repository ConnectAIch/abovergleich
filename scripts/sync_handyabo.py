#!/usr/bin/env python3
"""Zieht Anbieterzahl und Einstiegspreis für Handy und Internet von handyabo.com
auf die Startseite (Kacheln «Handy-Abo» und «Internet-Abo»).

Quelle ist dieselbe Datei, aus der handyabo.com seine Karten baut. Gerechnet
wird wie dort in src/_data/plansMeta.js: Unlimited heisst dataGb >= 999, und es
zählt nur der Dauerpreis, nie ein Aktionspreis.

    python3 sync_handyabo.py            # liest ../../handyabo/data, sonst live
    python3 sync_handyabo.py --live     # immer von handyabo.com

Läuft auch am Ende von build_kk_pages.py mit.
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.parent
LOCAL = ROOT.parent / "handyabo" / "data"
LIVE = "https://handyabo.com/data/"


def load(name, live=False):
    f = LOCAL / name
    if not live and f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    with urllib.request.urlopen(LIVE + name, timeout=20) as r:
        return json.load(r)


def fmt(n):
    return str(int(n)) if float(n).is_integer() else f"{n:.2f}"


def figures(live=False):
    mobile, internet = load("plans.json", live), load("internet-plans.json", live)
    unl = [pl["price"] for p in mobile["providers"] for pl in p.get("plans", [])
           if (pl.get("dataGb") or 0) >= 999 and isinstance(pl.get("price"), (int, float))]
    net = [pl["price"] for p in internet["providers"] for pl in p.get("plans", [])
           if isinstance(pl.get("price"), (int, float))]
    return {
        "hb-mobile-count": str(len(mobile["providers"])),
        "hb-mobile-from": fmt(min(unl)),
        "hb-internet-count": str(len(internet["providers"])),
        "hb-internet-from": fmt(min(net)),
    }


def apply(live=False):
    vals = figures(live)
    idx = ROOT / "index.html"
    s = idx.read_text(encoding="utf-8")
    new = s
    for cls, v in vals.items():
        new, n = re.subn(rf'(<span class="{cls}">)[^<]*(</span>)', rf"\g<1>{v}\g<2>", new)
        if not n:
            sys.exit(f"Platzhalter {cls} fehlt in index.html")
    if new != s:
        idx.write_text(new, encoding="utf-8")
    print("✓ handyabo:", ", ".join(f"{k.removeprefix('hb-')} {v}" for k, v in vals.items()))


if __name__ == "__main__":
    apply(live="--live" in sys.argv)
