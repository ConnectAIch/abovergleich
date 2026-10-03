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

## Deep-Links zur Anmeldung: Sanitas geprüft (03.10.2026)

Im Code des Sanitas-Rechners (calculator.sanitas.com) nachgesehen:

- **Keine Vorbelegung per URL.** PLZ, Geburtsdatum, Franchise und Modell
  lassen sich nicht mitgeben. Es gibt eine interne Vorbelegung (Vorname,
  Geschlecht, Geburtsdatum, Region, PLZ), die nur die eigene Website nutzt.
- **Direkt in den Rechner** geht `calculator.sanitas.com/de` (fr, en, it).
  Seit 03.10.2026 zeigt «Zu Sanitas» dorthin, Feld `signup_url` in
  `scripts/data/kuendigung_kanaele.json`. Andere Kassen bei Gelegenheit
  gleich prüfen und eintragen.
- **Partner-Route:** `calculator.sanitas.com/de/partner/123456` mit einer
  sechsstelligen Vermittlernummer. Der Abschluss läuft dann über den Kanal
  Partner und ist der Nummer zugeordnet. Die Nummer vergibt Sanitas, also
  erst mit Vermittlervertrag (siehe oben). Sobald sie da ist, nur
  `signup_url` anpassen.
- **cmpID:** Der Rechner liest `?cmpID=…` und hält ihn 7 Tage im Cookie für
  die eigene Auswertung. Ohne Absprache nur Analytics, wie UTM.

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
