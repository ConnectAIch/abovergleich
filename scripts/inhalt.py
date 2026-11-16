#!/usr/bin/env python3
"""Wann hat sich der Inhalt einer Seite zuletzt geändert?

Der Generator schreibt bei jedem Lauf alle Seiten neu, und dabei ändert sich
vieles, das kein Inhalt ist: Prüfsummen an CSS/JS (?v=…), die Frist-Leiste,
Navigation, Fusszeile, Skripte. Bis zum 16.11.2026 trug deshalb jede URL der
Sitemap das Builddatum als lastmod, alle 222 dasselbe. Google lernt daraus,
dass lastmod hier nichts bedeutet, und ignoriert es.

Der Fingerabdruck einer Seite nimmt nur, was ein Leser sieht oder eine
Suchmaschine bewertet: Title, Description und den Body ohne Navigation,
Fusszeile, Skripte und Kommentare. Das Datum ist der älteste Commit der
jüngsten Strecke, in der dieser Fingerabdruck gleich blieb; ist die Datei
gegenüber HEAD geändert, ist es heute.

Dieselbe Funktion nutzt indexnow.py, um nach einem Push nur die Seiten zu
melden, deren Inhalt sich wirklich geändert hat.
"""
import hashlib
import re
import subprocess
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_DROP = [
    re.compile(r"<!-- frist -->.*?<!-- /frist -->", re.S),
    re.compile(r"<nav\b.*?</nav>", re.S),
    re.compile(r"<footer\b.*?</footer>", re.S),
    re.compile(r"<script\b.*?</script>", re.S),
    re.compile(r"<style\b.*?</style>", re.S),
    re.compile(r"<!--.*?-->", re.S),
    re.compile(r"\?v=[0-9a-f]+"),
]


def normalisiert(html):
    """Title, Description und Body ohne das, was sich bei jedem Build ändert."""
    title = re.search(r"<title>(.*?)</title>", html, re.S)
    desc = re.search(r'<meta name="description" content="([^"]*)"', html)
    body = re.search(r"<body\b.*?</body>", html, re.S)
    b = body.group(0) if body else html
    for rx in _DROP:
        b = rx.sub("", b)
    parts = [title.group(1) if title else "", desc.group(1) if desc else "", b]
    return re.sub(r"\s+", " ", "\n".join(parts)).strip()


def fingerabdruck(html):
    return hashlib.sha1(normalisiert(html).encode("utf-8")).hexdigest()


class _Git:
    """Ein git-cat-file-Prozess für alle Abfragen, sonst dauert es pro Datei."""

    def __init__(self):
        self.p = subprocess.Popen(["git", "cat-file", "--batch"], cwd=ROOT,
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    def show(self, rev, rel):
        self.p.stdin.write(f"{rev}:{rel}\n".encode())
        self.p.stdin.flush()
        head = self.p.stdout.readline().decode().split()
        if len(head) < 3 or head[1] != "blob":
            return None
        data = self.p.stdout.read(int(head[2]))
        self.p.stdout.read(1)
        return data.decode("utf-8", "replace")


_git = None


def datum(rel, heute=None):
    """ISO-Datum der letzten Inhaltsänderung von ROOT/rel (z.B. 'kasse/css/index.html')."""
    global _git
    heute = heute or date.today().isoformat()
    f = ROOT / rel
    if not f.exists():
        return heute
    jetzt = fingerabdruck(f.read_text(encoding="utf-8"))
    log = subprocess.run(["git", "log", "--format=%H %cs", "--", rel], cwd=ROOT,
                         capture_output=True, text=True).stdout.split("\n")
    _git = _git or _Git()
    stand = heute
    for line in filter(None, log):
        sha, d = line.split()
        alt = _git.show(sha, rel)
        if alt is None or fingerabdruck(alt) != jetzt:
            break
        stand = d
    return stand


def url_zu_datei(path):
    """'/kasse/css/' -> 'kasse/css/index.html'"""
    return (path.strip("/") + "/index.html").lstrip("/")


def datei_zu_url(rel):
    """'kasse/css/index.html' -> '/kasse/css/', 'index.html' -> '/'"""
    if not rel.endswith("index.html"):
        return None
    return "/" + rel[: -len("index.html")]


if __name__ == "__main__":
    import sys
    for rel in sys.argv[1:]:
        print(datum(rel), rel)
