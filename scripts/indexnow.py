#!/usr/bin/env python3
"""Alle URLs aus sitemap.xml per IndexNow melden (Bing, Yandex, Seznam, Naver).

    python3 indexnow.py

Nach jedem Deploy mit neuen oder geänderten Seiten laufen lassen, z.B. nach
build_kk_pages.py. Der Schlüssel liegt als <KEY>.txt im Root der Website.
Google nutzt IndexNow nicht, dort Sitemap in der Search Console einreichen.
"""
import json
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.parent
KEY = "8576bb7add64f6608f54ad9e408d5544"

urls = re.findall(r"<loc>([^<]+)</loc>", (ROOT / "sitemap.xml").read_text(encoding="utf-8"))
body = json.dumps({"host": "abovergleich.com", "key": KEY,
                   "keyLocation": f"https://abovergleich.com/{KEY}.txt", "urlList": urls}).encode()
req = urllib.request.Request("https://api.indexnow.org/indexnow", data=body,
                             headers={"Content-Type": "application/json; charset=utf-8"})
print(len(urls), "URLs ->", urllib.request.urlopen(req, timeout=30).status)
