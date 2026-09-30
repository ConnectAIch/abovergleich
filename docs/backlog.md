# Backlog abovergleich.com

Zurückgestellt, nicht vergessen. Neueste Einträge oben. Wer etwas davon
anfängt, streicht es hier und verweist auf den Commit.

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
