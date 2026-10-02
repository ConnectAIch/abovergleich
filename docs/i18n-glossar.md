# Übersetzung abovergleich.com: Glossar und Regeln

Gilt für Französisch (`/fr/`, Romandie) und Englisch (`/en/`, Expats in der Schweiz).
URLs und Kantonsnamen stehen in `scripts/i18n.py`, nie von Hand erfinden.

## Ton

- **DE:** du. **FR:** vous (Standard für Versicherungsthemen in der Romandie). **EN:** you, britisches Englisch (insurer, organise, favour).
- Kurze, klare Sätze. Wie ein Mensch, nicht wie eine Broschüre. Keine Füllfloskeln.
- **Nie Gedankenstriche (— oder –) als Satzzeichen**, in keiner Sprache. Komma, Punkt oder Doppelpunkt. (Der Halbgeviertstrich als «leer»-Zeichen in Tabellenzellen bleibt.)
- Keine Werbebegriffe der Anbieter («lebenslang», «lifetime», «à vie»).
- Absender ist die Marke («nous», «we»), nie eine Person.
- Inhaltlich nichts dazuerfinden und nichts weglassen. Zahlen, Fristen und Quellen exakt übernehmen.
- Schweizer Kontext: Rechtsbegriffe so, wie sie das BAG/OFSP/FOPH in der jeweiligen Sprache verwendet.

## Zahlen und Daten

| | DE | FR | EN |
|---|---|---|---|
| Dezimal | 5,4 % | 5,4 % | 5.4% |
| Note | 9,1 / 10 | 9,1 / 10 | 9.1 / 10 |
| Franken | CHF 1'234.50 | CHF 1'234.50 | CHF 1'234.50 |
| Datum lang | 30. November 2026 | 30 novembre 2026 | 30 November 2026 |
| Datum kurz | 30.09.2026 | 30.09.2026 | 30/09/2026 |

Franchise «2'500» bleibt mit Apostroph in allen Sprachen.

## Begriffe

| DE | FR | EN |
|---|---|---|
| Krankenkasse | caisse-maladie (pl. caisses-maladie) | health insurer |
| Krankenkassen-Vergleich | comparatif des caisses-maladie | health insurance comparison |
| Grundversicherung | assurance de base (obligatoire) | basic health insurance (compulsory) |
| Zusatzversicherung | assurance complémentaire | supplementary insurance |
| Prämie | prime | premium |
| Prämienregion | région de primes | premium region |
| Franchise | franchise | deductible |
| Selbstbehalt | quote-part | co-payment (10% share) |
| Unfalldeckung, mit/ohne Unfall | couverture accidents, avec/sans accidents | accident cover, with/without accident cover |
| Standardmodell (freie Arztwahl) | modèle standard (libre choix du médecin) | standard model (free choice of doctor) |
| Hausarztmodell | modèle médecin de famille | family doctor model |
| HMO | HMO (cabinet de groupe) | HMO |
| Telmed | Telmed (télémédecine) | Telmed (telemedicine) |
| Alternativ (Modell) | alternatif | alternative |
| Apothekenmodell | modèle pharmacie | pharmacy model |
| Sparmodell | modèle alternatif / modèle d'économie | savings model / alternative model |
| BAG (Bundesamt für Gesundheit) | OFSP (Office fédéral de la santé publique) | FOPH (Federal Office of Public Health) |
| priminfo.admin.ch | priminfo.admin.ch | priminfo.admin.ch |
| KVG / KVV | LAMal / OAMal | Health Insurance Act (KVG) / Ordinance (KVV) |
| Versicherte | assurés | insured persons |
| Versichertenkarte | carte d'assuré | health insurance card |
| AHV-Nummer | numéro AVS | AHV number (social security number, 756…) |
| kündigen / Kündigung | résilier / résiliation | cancel / cancellation |
| Kündigungsbrief | lettre de résiliation | cancellation letter |
| Kündigungs-Editor | générateur de lettre de résiliation | cancellation letter tool |
| wechseln | changer de caisse | switch insurer |
| Einschreiben | recommandé | registered mail |
| Poststempel | cachet de la poste | postmark |
| Solvenzquote | taux de solvabilité | solvency ratio |
| Reserven | réserves | reserves |
| Verwaltungskosten | frais administratifs | administrative costs |
| Provision, Vermittler | commission, intermédiaire / courtier | commission, broker |
| Gemeinde | commune | municipality |
| Kanton | canton | canton |
| Ratgeber | Guide | Guide |
| Hausratversicherung | assurance ménage | household contents insurance |
| Privathaftpflicht | responsabilité civile privée | personal liability insurance |

## Marken unserer Instrumente

| DE | FR | EN |
|---|---|---|
| Preistreue-Rating | notation Constance des primes | Price Consistency Rating |
| Preistreue (Note) | constance des primes | price consistency |
| Preistreue-Award 2027 | Prix Constance des primes 2027 | Price Consistency Award 2027 |
| preistreueste Krankenkasse | la caisse-maladie aux primes les plus constantes | the most price-consistent health insurer |
| Dauerhaft günstig | Durablement avantageuse | Consistently cheap |
| Stabilste Prämien | Primes les plus stables | Most stable premiums |
| Fairste Sparmodelle | Modèles alternatifs les plus fiables | Fairest savings models |
| Solideste Reserven | Réserves les plus solides | Strongest reserves |
| Schlankste Verwaltung | Administration la plus légère | Leanest administration |
| Gesamtwertung | Classement général | Overall ranking |
| Teilnoten: Preis heute, Konstanz, Treue, Rabatt-Treue, Tarif-Bestand, Finanzpolster/Reserven | Prix actuel, Constance, Fidélité, Rabais durable, Pérennité des tarifs, Réserves | Price today, Consistency, Loyalty, Discount retention, Tariff continuity, Reserves |
| Vorjahressieger | la moins chère de l'an dernier | last year's cheapest |
| Regionalkasse | caisse régionale | regional insurer |

## Schwesterseite

handyabo.com (Handy- und Internet-Abos). FR: «notre site partenaire handyabo.com, comparatif d'abonnements mobile et internet». EN: «our sister site handyabo.com, for mobile and internet plans». handyabo.com hat selbst `/fr/` und `/en/`, also auf `https://handyabo.com/fr/` bzw. `/en/` verlinken.

## Technik je Seite

- `<html lang="fr">` / `lang="en"`.
- `<link rel="canonical">` auf die eigene URL der Sprache.
- hreflang-Block mit allen drei Sprachen plus `x-default` = DE:
  `<link rel="alternate" hreflang="de-CH" href="https://abovergleich.com/…">`, `fr-CH`, `en`, `x-default`.
- `og:locale` fr_CH / en_GB, `og:url` = eigene URL.
- Interne Links immer auf die Seite derselben Sprache (Routen in `scripts/i18n.py`). Wo es keine Übersetzung gibt, auf die DE-Seite.
- `<nav>…</nav>` wird von `scripts/site_nav.py` überschrieben, Inhalt egal, Tag muss da sein.
- JSON-LD übersetzen (Texte, URLs, `inLanguage`).
- Alles mit Trailing Slash.
