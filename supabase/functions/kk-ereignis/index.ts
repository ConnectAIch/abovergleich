import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

// Ereignisse aus Rechner und Kündigungs-Editor (Tabelle kk_events), ohne
// Namen, Adresse, E-Mail oder IP: PLZ, Jahrgang, Kanton und Prämienregion,
// Franchise, alte und neue Kasse, gerundete Beträge. Datenschutz 3.1 und 3.3.
// Fehler schlucken wir: das Zählen darf den Besuch nie stören.

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
};
const ok = () => new Response(null, { status: 204, headers: corsHeaders });

const EVENTS = new Set(['vergleich', 'wechsel_klick', 'kuendigung_pdf', 'kuendigung_mail', 'kuendigung_text']);
const FRANCHISEN = new Set([0, 100, 200, 300, 400, 500, 600, 1000, 1500, 2000, 2500]);
const ZUSATZ = new Set(['keine', 'behalten', 'kuendigen']);

const str = (v: unknown, max: number, re = /^[\w .|-]*$/) => {
  const s = typeof v === 'string' ? v.trim().slice(0, max) : '';
  return s && re.test(s) ? s : null;
};
const int = (v: unknown, lo: number, hi: number) => {
  const n = Math.round(Number(v));
  return Number.isFinite(n) && n >= lo && n <= hi ? n : null;
};

// Grobe Bremse gegen Fluten, nur im Speicher der Instanz
const hits = new Map<string, number[]>();
function limited(key: string) {
  const now = Date.now();
  const list = (hits.get(key) || []).filter((t) => now - t < 60_000);
  list.push(now);
  hits.set(key, list);
  return list.length > 30;
}

const supabase = createClient(Deno.env.get('SUPABASE_URL')!, Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!);

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders });
  if (req.method !== 'POST') return ok();
  const ip = (req.headers.get('x-forwarded-for') || '').split(',')[0].trim();
  if (ip && limited(ip)) return ok();
  try {
    const b = await req.json();
    if (!EVENTS.has(b.event)) return ok();
    const franchise = int(b.franchise, 0, 2500);
    const altersklasse = str(b.altersklasse, 3);
    const row = {
      event: b.event,
      plz: int(b.plz, 1000, 9699),
      jahrgang: int(b.jahrgang, 1900, 2030),
      jahr: int(b.jahr, 2025, 2040),
      canton: str(b.canton, 2, /^[A-Z]{2}$/),
      region: str(b.region, 12),
      altersklasse: altersklasse && ['KIN', 'JUG', 'ERW'].includes(altersklasse) ? altersklasse : null,
      franchise: franchise !== null && FRANCHISEN.has(franchise) ? franchise : null,
      unfall: typeof b.unfall === 'boolean' ? b.unfall : null,
      kasse_alt: int(b.kasse_alt, 1, 99999),
      kasse_neu: int(b.kasse_neu, 1, 99999),
      modell_neu: str(b.modell_neu, 20),
      // auf 10 Franken gerundet, damit der Betrag nicht auf eine Person zeigt
      praemie_bezahlt: b.praemie_bezahlt ? int(Math.round(Number(b.praemie_bezahlt) / 10) * 10, 0, 3000) : null,
      ersparnis_jahr: b.ersparnis_jahr != null ? int(Math.round(Number(b.ersparnis_jahr) / 10) * 10, -20000, 20000) : null,
      zusatz: ZUSATZ.has(b.zusatz) ? b.zusatz : null,
      kanal: str(b.kanal, 12),
      quelle: str(b.quelle, 40),
    };
    await supabase.from('kk_events').insert(row);
  } catch (_) { /* zählen ist nie wichtiger als der Besuch */ }
  return ok();
});
