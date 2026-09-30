import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import Anthropic from "npm:@anthropic-ai/sdk";

// Liest eine Prämienrechnung oder Police (Foto oder PDF) und gibt die Felder
// zurück, die der Rechner braucht. Das Dokument wird nur für diese eine Anfrage
// an die Claude API geschickt; hier wird nichts gespeichert und nichts geloggt.
// Bank- und Kontodaten werden bewusst nicht abgefragt.
//
// Benötigt das Secret ANTHROPIC_API_KEY. Ohne Schlüssel meldet GET
// { enabled: false } und der Knopf im Rechner bleibt ausgeblendet.

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
};

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { ...corsHeaders, 'Content-Type': 'application/json' } });

const MAX_BYTES = 6 * 1024 * 1024;
const IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'image/gif'];

// Einfacher Schutz gegen Missbrauch pro Instanz. Das eigentliche Kostendach
// ist das Ausgabenlimit im Anthropic-Workspace.
const hits = new Map<string, number[]>();
function limited(ip: string): boolean {
  const now = Date.now();
  const recent = (hits.get(ip) || []).filter(t => now - t < 3_600_000);
  recent.push(now);
  hits.set(ip, recent);
  return recent.length > 12;
}

const nullable = (type: string) => ({ anyOf: [{ type }, { type: 'null' }] });

const SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['is_health_insurance_document', 'insurer', 'persons', 'franchise', 'accident_included',
             'tariff_name', 'policyholder_name', 'street', 'postal_code', 'city', 'insured_number', 'premium_year'],
  properties: {
    is_health_insurance_document: { type: 'boolean' },
    insurer: nullable('string'),
    persons: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['name', 'birth_year', 'basic_premium_monthly'],
        properties: {
          name: nullable('string'),
          birth_year: nullable('integer'),
          basic_premium_monthly: nullable('number'),
        },
      },
    },
    franchise: nullable('integer'),
    accident_included: nullable('boolean'),
    tariff_name: nullable('string'),
    policyholder_name: nullable('string'),
    street: nullable('string'),
    postal_code: nullable('string'),
    city: nullable('string'),
    insured_number: nullable('string'),
    premium_year: nullable('integer'),
  },
};

const PROMPT = `Das Dokument ist eine Prämienrechnung oder Police einer Schweizer Krankenkasse. Lies diese Felder aus:

- insurer: Name der Krankenkasse, wie er auf dem Dokument steht.
- persons: je versicherte Person Name, Geburtsjahr (falls angegeben) und die Monatsprämie der Grundversicherung (OKP/KVG, obligatorische Krankenpflegeversicherung). Ohne Zusatzversicherungen (VVG). Deckt ein Betrag mehrere Monate ab, teile ihn auf einen Monat herunter. Steht die Umweltabgabe als eigene Zeile, nimm den Betrag vor diesem Abzug.
- franchise: Jahresfranchise in CHF, falls angegeben.
- accident_included: true, wenn die Unfalldeckung eingeschlossen ist, false, wenn sie ausgeschlossen ist, sonst null.
- tariff_name: Modell oder Tarif der Grundversicherung (z.B. Hausarzt, Telmed, HMO, Standard), wie angegeben.
- policyholder_name, street, postal_code, city: Adresse des Empfängers.
- insured_number: Versicherten- oder Kundennummer.
- premium_year: Jahr, für das die Prämie gilt.

Setze null, wo etwas nicht auf dem Dokument steht. Rate nicht. Bank- und Kontodaten (IBAN, Kontonummern, Zahlungsreferenzen) gehören nicht in die Antwort. Ist das Dokument keine Rechnung oder Police einer Krankenkasse, setze is_health_insurance_document auf false.`;

Deno.serve(async (req: Request) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders });

  const apiKey = Deno.env.get('ANTHROPIC_API_KEY');
  if (req.method === 'GET') return json({ enabled: Boolean(apiKey) });
  if (!apiKey) return json({ error: 'not_configured' }, 503);

  const ip = (req.headers.get('x-forwarded-for') || '').split(',')[0].trim() || 'unknown';
  if (limited(ip)) return json({ error: 'Zu viele Versuche. Bitte später nochmals.' }, 429);

  try {
    const { data, media_type } = await req.json();
    if (typeof data !== 'string' || !data) return json({ error: 'Keine Datei erhalten.' }, 400);
    if (data.length * 0.75 > MAX_BYTES) return json({ error: 'Datei zu gross (max. 6 MB).' }, 413);
    const isPdf = media_type === 'application/pdf';
    if (!isPdf && !IMAGE_TYPES.includes(media_type)) return json({ error: 'Nur Fotos oder PDF.' }, 415);

    const document = isPdf
      ? { type: 'document' as const, source: { type: 'base64' as const, media_type: 'application/pdf' as const, data } }
      : { type: 'image' as const, source: { type: 'base64' as const, media_type, data } };

    const client = new Anthropic({ apiKey });
    const response = await client.beta.messages.create({
      model: 'claude-opus-5-5',
      max_tokens: 4000,
      betas: ['server-side-fallback-2026-07-01'],
      // Bei einer Ablehnung durch die Sicherheitsfilter übernimmt serverseitig
      // das von Anthropic empfohlene Ersatzmodell.
      fallbacks: 'default',
      output_config: { effort: 'low', format: { type: 'json_schema', schema: SCHEMA } },
      messages: [{ role: 'user', content: [document, { type: 'text', text: PROMPT }] }],
    } as never);

    if (response.stop_reason === 'refusal') return json({ error: 'Das Dokument konnte nicht gelesen werden.' }, 422);
    const text = response.content.find((b: { type: string }) => b.type === 'text') as { text: string } | undefined;
    if (!text) return json({ error: 'Das Dokument konnte nicht gelesen werden.' }, 422);
    const result = JSON.parse(text.text);
    if (!result.is_health_insurance_document) {
      return json({ error: 'Das sieht nicht nach einer Rechnung oder Police einer Krankenkasse aus.' }, 422);
    }
    return json(result);
  } catch (err) {
    if (err instanceof Anthropic.RateLimitError) return json({ error: 'Gerade ausgelastet. Bitte in einer Minute nochmals.' }, 429);
    if (err instanceof Anthropic.APIError) return json({ error: 'Texterkennung nicht erreichbar.' }, 502);
    return json({ error: 'Das Dokument konnte nicht gelesen werden.' }, 500);
  }
});
