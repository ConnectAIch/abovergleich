import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

// Wechsel-Wecker: Anmeldung mit Double Opt-in, Bestätigung, Abmeldung.
// Der jährliche Versand läuft in der Funktion wechsel-wecker.
//
//   GET                  { enabled }  (Versand eingerichtet?)
//   POST {email, ...}    Anmeldung, schickt Bestätigungsmail
//   GET ?confirm=<token> bestätigt, leitet auf abovergleich.com zurück
//   GET ?stop=<token>    meldet ab, leitet auf abovergleich.com zurück
//
// Secrets: RESEND_API_KEY, optional WECKER_FROM
// (Standard «abovergleich.com <hello@handyabo.com>», Domain bei Resend verifiziert).

const SITE = 'https://abovergleich.com';
const SELF = 'https://zexpmaegqsayleaohiip.supabase.co/functions/v1/wecker';

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
};
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { ...corsHeaders, 'Content-Type': 'application/json' } });
const back = (state: string) => Response.redirect(`${SITE}/?wecker=${state}#kk-rechner`, 302);

const hits = new Map<string, number[]>();
function limited(ip: string): boolean {
  const now = Date.now();
  const recent = (hits.get(ip) || []).filter(t => now - t < 3_600_000);
  recent.push(now);
  hits.set(ip, recent);
  return recent.length > 6;
}

async function sendMail(to: string, subject: string, html: string, stopUrl?: string): Promise<boolean> {
  const key = Deno.env.get('RESEND_API_KEY');
  if (!key) return false;
  const headers: Record<string, string> = {};
  if (stopUrl) {
    headers['List-Unsubscribe'] = `<${stopUrl}>`;
    headers['List-Unsubscribe-Post'] = 'List-Unsubscribe=One-Click';
  }
  const res = await fetch('https://api.resend.com/emails', {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${key}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      from: Deno.env.get('WECKER_FROM') || 'abovergleich.com <hello@handyabo.com>',
      reply_to: 'hello@handyabo.com',
      to: [to], subject, html, headers,
    }),
  });
  // Resends Fehlertext enthält keinen Schlüssel, nur den Grund (Domain, Absender, Limit)
  if (!res.ok) console.error('resend', res.status, (await res.text()).slice(0, 300));
  return res.ok;
}

function confirmMail(confirmUrl: string): string {
  return `<!DOCTYPE html><html lang="de"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;background:#fafaf9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#1c1917;">
<div style="max-width:520px;margin:0 auto;padding:36px 20px;">
  <div style="font-weight:800;font-size:20px;margin-bottom:24px;">abo<span style="color:#a68600;">vergleich</span>.com</div>
  <div style="background:#fff;border:1px solid rgba(0,0,0,0.08);border-radius:14px;padding:28px;">
    <h1 style="font-size:20px;margin:0 0 12px;">Bitte bestätige deinen Wechsel-Wecker</h1>
    <p style="font-size:15px;line-height:1.6;color:#44403c;margin:0 0 20px;">Du hast auf abovergleich.com den Wechsel-Wecker eingeschaltet. Jedes Jahr Ende September, wenn das BAG die neuen Prämien veröffentlicht, schicken wir dir deinen persönlichen Vergleich. Rechtzeitig vor der Kündigungsfrist am 30. November.</p>
    <a href="${confirmUrl}" style="display:inline-block;background:#fed001;color:#1c1917;padding:13px 24px;border-radius:10px;font-weight:700;text-decoration:none;">E-Mail bestätigen</a>
    <p style="font-size:13px;line-height:1.6;color:#78716c;margin:20px 0 0;">Warst das nicht du? Dann ignoriere diese Mail. Ohne Bestätigung löschen wir die Angaben nach 30 Tagen.</p>
  </div>
</div></body></html>`;
}

Deno.serve(async (req: Request) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders });
  const url = new URL(req.url);
  const supabase = createClient(Deno.env.get('SUPABASE_URL')!, Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!);
  const uuid = /^[0-9a-f-]{36}$/i;

  if (req.method === 'GET') {
    const confirm = url.searchParams.get('confirm');
    const stop = url.searchParams.get('stop');
    if (confirm) {
      if (!uuid.test(confirm)) return back('ungueltig');
      const { data } = await supabase.from('kk_wecker').update({ confirmed_at: new Date().toISOString() })
        .eq('token', confirm).is('unsubscribed_at', null).select('id');
      return back(data && data.length ? 'bestaetigt' : 'ungueltig');
    }
    if (stop) {
      if (!uuid.test(stop)) return back('ungueltig');
      await supabase.from('kk_wecker').update({ unsubscribed_at: new Date().toISOString() })
        .eq('token', stop).is('unsubscribed_at', null);
      return back('abgemeldet');
    }
    return json({ enabled: Boolean(Deno.env.get('RESEND_API_KEY')) });
  }

  if (req.method !== 'POST') return json({ error: 'method' }, 405);
  // Abmeldung mit einem Klick aus dem Mailprogramm (RFC 8058): POST auf den Abmeldelink
  const stopPost = url.searchParams.get('stop');
  if (stopPost) {
    if (uuid.test(stopPost)) {
      await supabase.from('kk_wecker').update({ unsubscribed_at: new Date().toISOString() })
        .eq('token', stopPost).is('unsubscribed_at', null);
    }
    return json({ ok: true });
  }
  if (!Deno.env.get('RESEND_API_KEY')) return json({ error: 'not_configured' }, 503);
  const ip = (req.headers.get('x-forwarded-for') || '').split(',')[0].trim() || 'unknown';
  if (limited(ip)) return json({ error: 'Zu viele Versuche. Bitte später nochmals.' }, 429);

  try {
    const b = await req.json();
    const email = String(b.email || '').trim().toLowerCase();
    const plz = parseInt(b.plz), jahrgang = parseInt(b.jahrgang), franchise = parseInt(b.franchise);
    if (!/^[^\s@]+@[^\s@]+\.[a-z]{2,}$/i.test(email) || email.length > 200) return json({ error: 'Bitte eine gültige E-Mail-Adresse eingeben.' }, 400);
    if (!(plz >= 1000 && plz <= 9699) || !(jahrgang >= 1920 && jahrgang <= 2030) || ![300, 500, 1000, 1500, 2000, 2500].includes(franchise)) {
      return json({ error: 'Bitte zuerst den Rechner ausfüllen.' }, 400);
    }
    const row = {
      email, plz, jahrgang, franchise,
      accident_included: b.accident_included === true || b.accident_included === 'true',
      current_insurer_id: parseInt(b.current_insurer_id) || null,
      paid_monthly: Number(b.paid_monthly) > 0 ? Number(b.paid_monthly) : null,
    };

    // Aufräumen: unbestätigte Anmeldungen älter als 30 Tage
    await supabase.from('kk_wecker').delete().is('confirmed_at', null)
      .lt('created_at', new Date(Date.now() - 30 * 86_400_000).toISOString());

    const { data: existing } = await supabase.from('kk_wecker').select('id, token, confirmed_at')
      .ilike('email', email).is('unsubscribed_at', null).limit(1);
    let token: string;
    if (existing && existing.length) {
      token = existing[0].token;
      await supabase.from('kk_wecker').update(row).eq('id', existing[0].id);
      if (existing[0].confirmed_at) return json({ ok: true, already: true });
    } else {
      const { data, error } = await supabase.from('kk_wecker').insert(row).select('token').single();
      if (error || !data) return json({ error: 'Anmeldung nicht möglich. Bitte später nochmals.' }, 500);
      token = data.token;
    }
    const sent = await sendMail(email, 'Bitte bestätige deinen Wechsel-Wecker', confirmMail(`${SELF}?confirm=${token}`));
    if (!sent) return json({ error: 'Die Bestätigungsmail konnte nicht verschickt werden.' }, 502);
    return json({ ok: true });
  } catch {
    return json({ error: 'Anmeldung nicht möglich. Bitte später nochmals.' }, 500);
  }
});
