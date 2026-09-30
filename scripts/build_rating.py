#!/usr/bin/env python3
"""Preistreue-Rating der Krankenkassen, aus den BAG-Prämien 2020 bis heute.

Die Frage dahinter: Welche Kasse ist dauerhaft günstig, statt ein Jahr
günstig und danach teurer? Alles aus öffentlichen Daten des BAG, nichts aus
Bewertungen. Sechs Teilnoten von 0 bis 10:

  Preis heute      30 %  Position des günstigsten Tarifs der Kasse in der Region
  Konstanz         25 %  in wie vielen Jahren seit 2020 unter den 5 günstigsten
  Treue            15 %  wie stark steigt der günstige Tarif, wenn man bleibt,
                         gemessen am Markt der Region
  Rabatt-Treue     10 %  behalten neue Modelle ihren Startrabatt ggü. Standard?
  Tarif-Bestand    10 %  wie viele Tarife laufen im Folgejahr unverändert weiter?
  Finanzpolster    10 %  Solvenzquote laut BAG (Reserven / Mindestreserven)

Erwachsene mit Unfall, Franchise 300 und 2'500 gemittelt. Die Rohdaten
(scripts/data/praemien_YYYY.csv) liegen nur lokal; das Ergebnis schreibt
build_kk_pages.py auf die Seiten und nach /rating-daten.json.

    python3 build_rating.py      # Tabelle zur Kontrolle ausgeben
"""
import json
import re
import statistics as st
from collections import defaultdict

import build_kk_pages as b

FIRST = 2020
FRANCHISES = (300, 500, 1000, 1500, 2000, 2500)
MAIN_F = (300, 2500)
WEIGHTS = {"preis": .30, "konstanz": .25, "treue": .15, "rabatt": .10, "tarife": .10, "solvenz": .10}
LABELS = {"preis": "Preis heute", "konstanz": "Konstanz", "treue": "Treue", "rabatt": "Rabatt-Treue",
          "tarife": "Tarif-Bestand", "solvenz": "Finanzpolster"}
TOP_N = 5
MIN_BESTAND_NATIONAL = 50_000   # darunter: Regionalkasse, Note nur mit Hinweis

norm = lambda n: re.sub(r"\s+", " ", (n or "").lower().strip())
clip = lambda x: max(0.0, min(10.0, x))
q = st.median


def scale(key, raw):
    """Rohwert -> Teilnote 0..10. Die Grenzen stehen auch auf der Methodik-Seite."""
    if raw is None:
        return None
    return clip({
        "preis": lambda r: 10 * (0.8 - r) / 0.7,          # Position <= 10 % = 10, >= 80 % = 0
        "konstanz": lambda r: 10 * r / 0.4,               # >= 40 % der Jahre unter den 5 günstigsten = 10
        "treue": lambda r: 10 * (1.5 - r) / 2,            # <= -0.5 Pkt./Jahr ggü. Markt = 10, >= +1.5 = 0
        "rabatt": lambda r: 10 * (1 + r / 1.5),           # 0 Pkt./Jahr = 10, -1.5 = 0
        "tarife": lambda r: 10 * (r - 0.8) / 0.2,         # 100 % bleiben = 10, 80 % = 0
        "solvenz": lambda r: 10 * (r - 100) / 100,        # >= 200 % = 10, 100 % = 0
    }[key](raw))


def note(parts):
    have = {k: v for k, v in parts.items() if v is not None}
    w = sum(WEIGHTS[k] for k in have)
    return round(sum(v * WEIGHTS[k] for k, v in have.items()) / w, 1) if w else None


def compute():
    years = list(range(FIRST, b.YEAR + 1))
    rows = {y: b.load_year(y) for y in years}
    bestand = defaultdict(float)
    for (i, _c), v in b.load_bestand().items():
        bestand[i] += v
    sol = {int(k): v for k, v in json.loads((b.DATA / "solvenz_2026.json").read_text())["solvenzquote"].items()}
    ids = sorted({r["insurer_id"] for r in rows[b.YEAR]})

    # idx[y][F][(Kasse, Kanton, Region)] = {Tarifcode: Zeile}
    idx = {y: {F: defaultdict(dict) for F in FRANCHISES} for y in years}
    for y in years:
        for r in rows[y]:
            if r["franchise"] in FRANCHISES and not r["age_subgroup"]:
                idx[y][r["franchise"]][(r["insurer_id"], r["canton"], r["region"])][r["tariff"].lower()] = r

    # ── Position und Konstanz je Region ───────────────────────────────────
    pos27 = defaultdict(dict)                 # (reg, i) -> {F: Perzentil 0..1}
    top = defaultdict(lambda: defaultdict(list))  # (reg, i) -> {F: [bool je Jahr]}
    for y in years:
        for F in FRANCHISES:
            best = defaultdict(dict)
            for (i, c, rg), t in idx[y][F].items():
                best[(c, rg)][i] = min(x["premium"] for x in t.values())
            for reg, m in best.items():
                order = sorted(m, key=m.get)
                for p, i in enumerate(order):
                    top[(reg, i)][F].append(p < TOP_N)
                    if y == b.YEAR:
                        pos27[(reg, i)][F] = p / (len(order) - 1) if len(order) > 1 else 0.0

    # ── Treue und Rabatt-Treue (Franchise 300 und 2'500) ──────────────────
    def follow(t0, t1, c):
        if c in t1:
            return t1[c]
        n = norm(t0[c]["tariff_name"])
        hit = [r for r in t1.values() if norm(r["tariff_name"]) == n]
        return hit[0] if len(hit) == 1 else None

    treue = defaultdict(list)
    erosion = defaultdict(list)
    for F in MAIN_F:
        market = defaultdict(list)
        stay = []
        for y0, y1 in zip(years, years[1:]):
            for k, t0 in idx[y0][F].items():
                t1 = idx[y1][F].get(k)
                if not t1:
                    continue
                cont = {c: follow(t0, t1, c) for c in t0}
                cont = {c: p for c, p in cont.items() if p}
                if not cont:
                    continue
                ch = {c: cont[c]["premium"] / t0[c]["premium"] - 1 for c in cont}
                market[(y1, k[1], k[2])].extend(ch.values())
                w = min(cont, key=lambda c: t0[c]["premium"])   # günstigster Tarif der Kasse
                stay.append((k[0], y1, k, ch[w]))
        mkt = {kk: q(v) for kk, v in market.items()}
        per = defaultdict(lambda: defaultdict(list))
        for i, y1, k, c in stay:
            per[i][y1].append(c - mkt[(y1, k[1], k[2])])
        for i, d in per.items():
            treue[i].append(st.mean(q(v) for v in d.values()) * 100)

        def disc(y, k, c):
            t = idx[y][F].get(k, {})
            s = [r["premium"] for r in t.values() if r["model_type"] == "standard"]
            return 1 - t[c]["premium"] / s[0] if s and c in t else None
        ero = defaultdict(list)
        for co in range(FIRST + 1, b.YEAR):
            prev = {(k[0], c) for k, t in idx[co - 1][F].items() for c in t} | \
                   {(k[0], norm(r["tariff_name"])) for k, t in idx[co - 1][F].items() for r in t.values()}
            for k, t in idx[co][F].items():
                for c, r in t.items():
                    if r["model_type"] == "standard" or (k[0], c) in prev or (k[0], norm(r["tariff_name"])) in prev:
                        continue
                    if c not in idx[b.YEAR][F].get(k, {}):
                        continue
                    s0, s1 = disc(co, k, c), disc(b.YEAR, k, c)
                    if s0 is not None and s1 is not None:
                        ero[k[0]].append((s1 - s0) * 100 / (b.YEAR - co))
        for i, v in ero.items():
            erosion[i].append(q(v))

    # ── Jahrgänge neuer Modelle: Rabatt im Startjahr und heute (F2500) ───
    def disc25(y, k, c):
        t = idx[y][2500].get(k, {})
        s = [r["premium"] for r in t.values() if r["model_type"] == "standard"]
        return 1 - t[c]["premium"] / s[0] if s and c in t else None
    kohorten = []
    for co in range(FIRST + 1, b.YEAR - 2):
        prev = {(k[0], c) for k, t in idx[co - 1][2500].items() for c in t} | \
               {(k[0], norm(r["tariff_name"])) for k, t in idx[co - 1][2500].items() for r in t.values()}
        born = [(k, c) for k, t in idx[co][2500].items() for c, r in t.items()
                if r["model_type"] != "standard" and (k[0], c) not in prev and (k[0], norm(r["tariff_name"])) not in prev
                and all(c in idx[y][2500].get(k, {}) for y in range(co, b.YEAR + 1))]
        s0 = [x for x in (disc25(co, k, c) for k, c in born) if x is not None]
        s1 = [x for x in (disc25(b.YEAR, k, c) for k, c in born) if x is not None]
        if len(s0) >= 50:
            kohorten.append({"jahr": co, "start": round(q(s0) * 100, 1), "heute": round(q(s1) * 100, 1),
                             "tarife": len(born), "kassen": len({k[0] for k, _ in born})})
    alt = [(k, c) for k, t in idx[FIRST][2500].items() for c, r in t.items()
           if r["model_type"] != "standard" and all(c in idx[y][2500].get(k, {}) for y in years)]
    alte = {"start": round(q([disc25(FIRST, k, c) for k, c in alt if disc25(FIRST, k, c) is not None]) * 100, 1),
            "heute": round(q([disc25(b.YEAR, k, c) for k, c in alt if disc25(b.YEAR, k, c) is not None]) * 100, 1)}

    # ── Tarif-Bestand (Franchise 2'500) ───────────────────────────────────
    keep = defaultdict(lambda: [0, 0])
    for y0, y1 in zip(years, years[1:]):
        for k, t0 in idx[y0][2500].items():
            t1 = idx[y1][2500].get(k)
            if t1:
                for c in t0:
                    keep[k[0]][0] += c in t1
                    keep[k[0]][1] += 1

    # ── Seit wann gibt es den Tarif? (für den Hinweis «neuer Tarif») ──────
    codes = {y: defaultdict(set) for y in years}
    names = {y: defaultdict(set) for y in years}
    for y in years:
        for r in rows[y]:
            codes[y][r["insurer_id"]].add(r["tariff"].lower())
            names[y][r["insurer_id"]].add(norm(r["tariff_name"]))
    seit = defaultdict(dict)
    for r in rows[b.YEAR]:
        i, c, n = r["insurer_id"], r["tariff"].lower(), norm(r["tariff_name"])
        if c in seit[i] or r["model_type"] == "standard":
            continue
        s = b.YEAR
        for y in range(b.YEAR - 1, FIRST - 1, -1):
            if c in codes[y][i] or n in names[y][i]:
                s = y
            else:
                break
        seit[i][c] = s

    # ── National ──────────────────────────────────────────────────────────
    national = {}
    for i in ids:
        regs = [(reg, ii) for (reg, ii) in pos27 if ii == i]
        pos = [pos27[k][F] for k in regs for F in MAIN_F if F in pos27[k]]
        kon = [sum(v) / len(v) for k in regs for F in MAIN_F for v in [top[k][F]] if len(v) >= 3]
        raw = {
            "preis": q(pos) if pos else None,
            "konstanz": q(kon) if kon else None,
            "treue": st.mean(treue[i]) if treue.get(i) else None,
            "rabatt": st.mean(erosion[i]) if erosion.get(i) else None,
            "tarife": keep[i][0] / keep[i][1] if keep[i][1] else None,
            "solvenz": sol.get(i),
        }
        parts = {k: scale(k, v) for k, v in raw.items()}
        national[i] = {"name": b.INSURER_NAMES[str(i)], "note": note(parts), "parts": parts, "raw": raw,
                       "bestand": round(bestand[i]), "regional": bestand[i] < MIN_BESTAND_NATIONAL,
                       "regionen": len(regs)}

    # ── Je Region: Preis und Konstanz aus der Region, der Rest national ──
    regions = defaultdict(dict)
    for (reg, i), p in pos27.items():
        n = national[i]
        pr = [p[F] for F in MAIN_F if F in p]
        kv = [sum(top[(reg, i)][F]) / len(top[(reg, i)][F]) for F in MAIN_F if len(top[(reg, i)][F]) >= 3]
        parts = dict(n["parts"])
        parts["preis"] = scale("preis", st.mean(pr)) if pr else None
        parts["konstanz"] = scale("konstanz", st.mean(kv)) if kv else n["parts"]["konstanz"]
        regions[f"{reg[0]}|{reg[1]}"][i] = {
            "note": note(parts),
            # je Franchise: [Jahre unter den 5 günstigsten, Jahre mit Angebot]
            "top5": [[sum(top[(reg, i)][F]), len(top[(reg, i)][F])] for F in FRANCHISES],
        }

    adm = json.loads((b.DATA / "aufsichtsdaten_okp.json").read_text())
    return {"years": years, "national": national, "regions": regions, "seit": seit,
            "kohorten": kohorten, "alte_modelle": alte,
            "verwaltung": adm, "weights": WEIGHTS, "labels": LABELS}


def client_json(r):
    """Kompakte Fassung für den Rechner: Note je Region, Konstanz je Franchise, Tarif-Alter."""
    return {
        "jahr": b.YEAR, "von": FIRST, "top": TOP_N, "franchisen": list(FRANCHISES),
        "national": {str(i): {"note": n["note"], "regional": n["regional"]} for i, n in r["national"].items()},
        "regionen": {reg: {str(i): [v["note"], v["top5"]] for i, v in m.items()} for reg, m in r["regions"].items()},
        "seit": {str(i): {c: s for c, s in m.items() if s >= b.YEAR - 2} for i, m in r["seit"].items()},
    }


if __name__ == "__main__":
    r = compute()
    rows = sorted(r["national"].items(), key=lambda x: -(x[1]["note"] or 0))
    print(f"{'Kasse':24s} {'Note':>5s} " + " ".join(f"{LABELS[k][:7]:>7s}" for k in WEIGHTS))
    for i, n in rows:
        f = lambda v: f"{v:7.1f}" if v is not None else "      -"
        print(f"{n['name'][:24]:24s} {n['note'] or 0:5.1f} " + " ".join(f(n["parts"][k]) for k in WEIGHTS) +
              ("   (Regionalkasse)" if n["regional"] else ""))
    print("Kohorten:", r["kohorten"], "alte:", r["alte_modelle"])
    print(f"\n{len(r['regions'])} Regionen, JSON für den Rechner: {len(json.dumps(client_json(r))) // 1024} KB")
