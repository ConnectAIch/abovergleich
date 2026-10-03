# Backlog abovergleich.com

Zurückgestellt, nicht vergessen. Neueste Einträge oben. Wer etwas davon
anfängt, streicht es hier und verweist auf den Commit.

## Sanitas und Co.: Attribution der Anmeldungen (offen seit 03.10.2026)

Heute hängt an jedem Link zur neuen Kasse nur `utm_source=abovergleich.com`.
Das sieht die Kasse in ihrer Analytics, mehr nicht. Damit eine Kasse weiss,
dass ein Abschluss von uns kommt, braucht es einen Vermittlervertrag (seit
1.9.2024 Branchenvereinbarung, höchstens CHF 70 pro Abschluss in der
Grundversicherung, Beratungsprotokoll, kein Telefonverkauf) und von der
Kasse einen Partner-Parameter oder eine eigene Landingpage. Erster Schritt:
Sanitas Vertrieb anschreiben, danach Concordia, KPT, Assura (die häufigsten
«neu»-Kassen im Rechner, siehe kk_events). Entscheid bei Matthias.

## Anmelde-Links: alle 32 Kassen geprüft (03.10.2026)

«Zu <Kasse>» führt bei jeder Kasse direkt in ihren Prämienrechner, in der
Sprache der Seite, sonst deutsch. Daten: Feld `signup` je Kasse in
`scripts/data/kuendigung_kanaele.json`, Stand `signup_stand`. Jedes Jahr im
September nachprüfen, die Rechner ziehen gern um.

- **Ohne Online-Anmeldung:** curaulta (Kontaktformular), KK Wädenswil (nur
  PDF), vita surselva (Offertformular). Feld `signup_online: false`, der
  Text verspricht dort keine «10 Minuten online».
- **Gemeinsame Rechner:** Avenir, Mutuel, Philos teilen den Groupe-Mutuel-
  Rechner, die Kasse wählt man im 3. Schritt. sana24 und Galenos laufen
  über den Visana-Rechner. Kein Parameter gefunden, der die Marke vorwählt.
- **Nur deutsch:** die BBT-Portale (bbtp.ch) der kleinen Kassen, SLKK.
  Kein Englisch bei Agrisano, Assura, Atupri.

### Vorbelegung per URL: eingebaut für CSS und ÖKK (03.10.2026)

Im Browser getestet: CSS übernimmt `plz` und `geburtsdatum` (dd.mm.jjjj),
mit `gender=m|w` springt der Rechner gleich zu den Prämien. Gilt nur, wenn
der Browser noch keine CSS-Sitzung hat. ÖKK übernimmt nur `Geburtsdatum`.
Groupe Mutuel (npa/dateNaissance) und Aquilana (birthday/postcode) ignorieren
die Parameter trotz Code, Swica/EGK/Sympany brauchen interne Orts-IDs.
Franchise und Modell geht bei keiner Kasse.

Umsetzung: Feld `signup_prefill` je Kasse, nur der Link im Fertig-Kasten des
Editors. Mail und Abholseite bekommen den Link ohne Personendaten, sonst
läge das Geburtsdatum in der Datenbank. Datenschutz 3.3 nennt es.

## BCC an uns beim Mailversand an die Kasse: nein (entschieden 03.10.2026)

Der mailto-Link setzt kein BCC. Der Brief enthält Name, Adresse,
Geburtsdatum und Versichertennummer; der Datenschutz verspricht nur die
60-Tage-Ablage. Ob die Kündigung durch ist, fragt die Erinnerung
«Hat die Kasse bestätigt?» ab, das reicht als Messung.

## Rechnungsfoto auslesen (zurückgestellt 30.09.2026)

Der Kunde lädt Foto oder PDF seiner Prämienrechnung hoch, der Rechner füllt
PLZ, Jahrgang, Franchise, Unfall, Kasse und Betrag selbst aus.

- **Stand:** gebaut und deployt. Die Edge Function `read-invoice` nutzt Gemini auf Vertex AI (europe-west1), und `index.html` enthält die Upload-Box. Die Box bleibt ausgeblendet, solange die Funktion `enabled: false` meldet.
- **Es fehlt nur:** das Secret `GCP_SERVICE_ACCOUNT_JSON` in Supabase, also ein Service-Account mit der Rolle «Vertex AI User». Im Google-Cloud-Projekt vorher ein Budget-Alarm setzen, zum Beispiel CHF 20 im Monat.
- **Warum zurückgestellt:** Der Rechner funktioniert ohne Foto. Mit dem Betrag «Du zahlst heute» erkennt er den Tarif auch so.
- **Datenschutz 3.2** beschreibt die Funktion schon, der Text kann bleiben.

## Einschreiben per Knopfdruck (Pingen)

Für Kassen ohne Mailweg. Pingen verschickt echte Einschreiben per API, etwa
CHF 6 bis 8 pro Brief. Kostenpflichtig, Entscheid bei Matthias. Seit dem
30.09.2026 schlägt die Seite ohnehin Brief oder Mail vor, das Einschreiben ist
nur Empfehlung.

## Nachfass-Mail vor der Kündigungsfrist

Um den 20. November: «Hast du die Bestätigung deiner Kasse? Sonst jetzt per
Post nachschicken.» Braucht eine freiwillige Mail-Angabe auf der
Kündigungsseite und einen Versand über Resend, wie beim Wecker.

## Rückfrage bei grossen Kassen zum Mailweg

CSS, Visana/sana24, KPT und Assura sagen auf ihren Seiten nichts dazu, ob sie
eine Kündigung der Grundversicherung per Mail annehmen. Ein Ja von CSS allein
hebt die Abdeckung von 58 % auf rund 75 % der Versicherten. Die Daten stehen
in `scripts/data/kuendigung_kanaele.json` und werden jedes Jahr vor Oktober
neu geprüft.

## Hausrat-Seite: Zahlen belegen

«Bis 63 % Preisunterschied» und «Ab CHF 150/Jahr» passen nicht zur eigenen
Tabelle, dort reicht die Spanne von CHF 150 bis 300. Entweder aus der
Tabelle ableiten oder mit Quelle belegen.
