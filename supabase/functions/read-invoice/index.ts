import "jsr:@supabase/functions-js/edge-runtime.d.ts";

// Liest eine Prämienrechnung oder Police (Foto oder PDF) mit Gemini auf
// Google Vertex AI (Region europe-west1, wie connectai-platform) und gibt die
// Felder zurück, die der Rechner braucht. Das Dokument wird nur für diese eine
// Anfrage übermittelt; hier wird nichts gespeichert und nichts geloggt.
// Bank- und Kontodaten werden bewusst nicht abgefragt.
//
// Secrets (Supabase → Edge Functions → Secrets):
//   GCP_SERVICE_ACCOUNT_JSON  Service-Account mit Rolle «Vertex AI User» (ganzes JSON)
//   GCP_REGION                optional, Standard europe-west1
//   GEMINI_MODEL              optional, Standard gemini-2.5-flash
// Ohne Service-Account meldet GET { enabled: false } und der Knopf im Rechner
// bleibt ausgeblendet.

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
};

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { ...corsHeaders, 'Content-Type': 'application/json' } });

const MAX_BYTES = 6 * 1024 * 1024;
const IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp'];

// Einfacher Schutz gegen Missbrauch pro Instanz. Das eigentliche Kostendach
// ist das Budget im Google-Cloud-Projekt.
const hits = new Map<string, number[]>();
function limited(ip: string): boolean {
  const now = Date.now();
  const recent = (hits.get(ip) || []).filter(t => now - t < 3_600_000);
  recent.push(now);
  hits.set(ip, recent);
  return recent.length > 12;
}

const S = (type: string, extra: Record<string, unknown> = {}) => ({ type, nullable: true, ...extra });

// Vertex-Schema (OpenAPI-Teilmenge): Typen gross, nullable statt null-Union
const SCHEMA = {
  type: 'OBJECT',
  required: ['is_health_insurance_document', 'persons'],
  properties: {
    is_health_insurance_document: { type: 'BOOLEAN' },
    insurer: S('STRING'),
    persons: {
      type: 'ARRAY',
      items: {
        type: 'OBJECT',
        properties: {
          name: S('STRING'),
          birth_year: S('INTEGER'),
          basic_premium_monthly: S('NUMBER'),
        },
      },
    },
    franchise: S('INTEGER'),
    accident_included: S('BOOLEAN'),
    tariff_name: S('STRING'),
    policyholder_name: S('STRING'),
    street: S('STRING'),
    postal_code: S('STRING'),
    city: S('STRING'),
    insured_number: S('STRING'),
    premium_year: S('INTEGER'),
  },
};

const PROMPT = `Das Dokument ist eine Prämienrechnung oder Police einer Schweizer Krankenkasse. Lies diese Felder aus und antworte nur mit JSON:

- insurer: Name der Krankenkasse, wie er auf dem Dokument steht.
- persons: je versicherte Person name, birth_year (falls angegeben) und basic_premium_monthly, die Monatsprämie der Grundversicherung (OKP/KVG, obligatorische Krankenpflegeversicherung). Ohne Zusatzversicherungen (VVG). Deckt ein Betrag mehrere Monate ab, teile ihn auf einen Monat herunter. Steht die Umweltabgabe als eigene Zeile, nimm den Betrag vor diesem Abzug.
- franchise: Jahresfranchise in CHF, falls angegeben.
- accident_included: true, wenn die Unfalldeckung eingeschlossen ist, false, wenn sie ausgeschlossen ist, sonst null.
- tariff_name: Modell oder Tarif der Grundversicherung (z.B. Hausarzt, Telmed, HMO, Standard), wie angegeben.
- policyholder_name, street, postal_code, city: Adresse des Empfängers.
- insured_number: Versicherten- oder Kundennummer.
- premium_year: Jahr, für das die Prämie gilt.
- is_health_insurance_document: false, wenn das Dokument keine Rechnung oder Police einer Krankenkasse ist.

Setze null, wo etwas nicht auf dem Dokument steht. Rate nicht. Bank- und Kontodaten (IBAN, Kontonummern, Zahlungsreferenzen) gehören nicht in die Antwort.`;

// ── Google-Zugriffstoken aus dem Service-Account (JWT-Bearer) ─────────────
let cachedToken: { token: string; exp: number } | null = null;

const b64url = (data: ArrayBuffer | string) => {
  const bytes = typeof data === 'string' ? new TextEncoder().encode(data) : new Uint8Array(data);
  let s = '';
  bytes.forEach(b => s += String.fromCharCode(b));
  return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
};

async function accessToken(sa: { client_email: string; private_key: string }): Promise<string> {
  const now = Math.floor(Date.now() / 1000);
  if (cachedToken && cachedToken.exp - 60 > now) return cachedToken.token;
  const header = b64url(JSON.stringify({ alg: 'RS256', typ: 'JWT' }));
  const claims = b64url(JSON.stringify({
    iss: sa.client_email, scope: 'https://www.googleapis.com/auth/cloud-platform',
    aud: 'https://oauth2.googleapis.com/token', iat: now, exp: now + 3600,
  }));
  const pem = sa.private_key.replace(/-----[^-]+-----/g, '').replace(/\s+/g, '');
  const der = Uint8Array.from(atob(pem), c => c.charCodeAt(0));
  const key = await crypto.subtle.importKey('pkcs8', der, { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' }, false, ['sign']);
  const sig = await crypto.subtle.sign('RSASSA-PKCS1-v1_5', key, new TextEncoder().encode(`${header}.${claims}`));
  const res = await fetch('https://oauth2.googleapis.com/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ grant_type: 'urn:ietf:params:oauth:grant-type:jwt-bearer', assertion: `${header}.${claims}.${b64url(sig)}` }),
  });
  if (!res.ok) throw new Error('google_auth');
  const t = await res.json();
  cachedToken = { token: t.access_token, exp: now + (t.expires_in || 3600) };
  return t.access_token;
}

function serviceAccount() {
  const raw = Deno.env.get('GCP_SERVICE_ACCOUNT_JSON');
  if (!raw) return null;
  try { return JSON.parse(raw); } catch { return null; }
}

async function gemini(sa: { project_id: string; client_email: string; private_key: string }, part: unknown, withSchema: boolean) {
  const region = Deno.env.get('GCP_REGION') || 'europe-west1';
  const model = Deno.env.get('GEMINI_MODEL') || 'gemini-2.5-flash';
  const url = `https://${region}-aiplatform.googleapis.com/v1/projects/${sa.project_id}/locations/${region}/publishers/google/models/${model}:generateContent`;
  const generationConfig: Record<string, unknown> = { responseMimeType: 'application/json', temperature: 0 };
  if (withSchema) generationConfig.responseSchema = SCHEMA;
  return fetch(url, {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${await accessToken(sa)}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ contents: [{ role: 'user', parts: [part, { text: PROMPT }] }], generationConfig }),
  });
}

Deno.serve(async (req: Request) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders });

  const sa = serviceAccount();
  if (req.method === 'GET') return json({ enabled: Boolean(sa) });
  if (!sa) return json({ error: 'not_configured' }, 503);

  const ip = (req.headers.get('x-forwarded-for') || '').split(',')[0].trim() || 'unknown';
  if (limited(ip)) return json({ error: 'Zu viele Versuche. Bitte später nochmals.' }, 429);

  try {
    const { data, media_type } = await req.json();
    if (typeof data !== 'string' || !data) return json({ error: 'Keine Datei erhalten.' }, 400);
    if (data.length * 0.75 > MAX_BYTES) return json({ error: 'Datei zu gross (max. 6 MB).' }, 413);
    const isPdf = media_type === 'application/pdf';
    if (!isPdf && !IMAGE_TYPES.includes(media_type)) return json({ error: 'Nur Fotos oder PDF.' }, 415);

    const part = { inlineData: { mimeType: media_type, data } };
    let res = await gemini(sa, part, true);
    // Lehnt das Modell das Schema ab, ohne Schema nochmals; der Prompt verlangt JSON
    if (res.status === 400) res = await gemini(sa, part, false);
    if (res.status === 429) return json({ error: 'Gerade ausgelastet. Bitte in einer Minute nochmals.' }, 429);
    if (!res.ok) return json({ error: 'Texterkennung nicht erreichbar.' }, 502);

    const out = await res.json();
    const text = out?.candidates?.[0]?.content?.parts?.map((p: { text?: string }) => p.text || '').join('') || '';
    const result = JSON.parse(text.replace(/^```(json)?\s*|\s*```$/g, ''));
    if (!result.is_health_insurance_document) {
      return json({ error: 'Das sieht nicht nach einer Rechnung oder Police einer Krankenkasse aus.' }, 422);
    }
    return json(result);
  } catch (err) {
    if (err instanceof Error && err.message === 'google_auth') return json({ error: 'Texterkennung nicht erreichbar.' }, 502);
    return json({ error: 'Das Dokument konnte nicht gelesen werden.' }, 500);
  }
});
