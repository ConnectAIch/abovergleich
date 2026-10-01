import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

// Kündigungs-Editor: schickt das im Browser erstellte PDF an die Person selbst.
// Mit dem Häkchen (voreingestellt, abwählbar) schaltet es den Wechsel-Wecker ein.
// Das PDF wird nur durchgereicht, nie gespeichert. In kk_wecker landen E-Mail,
// PLZ, Jahrgang, Franchise, alte und neue Kasse, Herkunft und Zeitpunkt der
// Einwilligung.

const SITE = 'https://abovergleich.com';
const WECKER = 'https://zexpmaegqsayleaohiip.supabase.co/functions/v1/wecker';
const MAX_PDF = 2_500_000; // Base64-Zeichen, rund 1,8 MB PDF

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
};
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { ...corsHeaders, 'Content-Type': 'application/json' } });

const hits = new Map<string, number[]>();
function limited(ip: string) {
  const now = Date.now();
  const list = (hits.get(ip) || []).filter((t) => now - t < 3_600_000);
  list.push(now);
  hits.set(ip, list);
  return list.length > 8;
}

const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]!));

function mail(p: { kasse: string; kanal: string; ziel: string; deadline: string; neu: string; stopUrl: string; wecker: boolean }) {
  const weg = p.kanal === 'mail'
    ? `Schick das PDF als Anhang an <strong>${esc(p.ziel)}</strong>, am besten von der Mail-Adresse, die ${esc(p.kasse)} von dir kennt. Die Eingangsbestätigung der Kasse ist dein Beweis, heb sie auf.`
    : p.kanal === 'portal'
      ? `${esc(p.kasse)} nimmt die Kündigung über ${esc(p.ziel)} entgegen. Lade das PDF dort hoch oder schick es per Post.`
      : `Druck das PDF aus und schick es per Post an ${esc(p.kasse)}, spätestens eine Woche vor dem ${esc(p.deadline)}. Ein Einschreiben ist nicht Pflicht, beweist aber den Eingang.`;
  return `<!doctype html><html><body style="margin:0;background:#fafaf9;font-family:Inter,Arial,sans-serif;color:#1c1917;">
<div style="max-width:560px;margin:0 auto;padding:28px 20px;">
  <div style="font-size:20px;font-weight:800;margin-bottom:18px;">abo<span style="color:#a68600;">vergleich</span>.com</div>
  <h1 style="font-size:22px;margin:0 0 12px;">Deine Kündigung an ${esc(p.kasse)}</h1>
  <p style="font-size:15px;line-height:1.6;">Im Anhang ist dein unterschriebener Brief als PDF. So geht es weiter:</p>
  <ol style="font-size:15px;line-height:1.6;padding-left:20px;">
    <li style="margin-bottom:8px;"><strong>Abschicken:</strong> ${weg}</li>
    <li style="margin-bottom:8px;"><strong>Frist:</strong> Die Kündigung muss bis am ${esc(p.deadline)} bei der Kasse <em>eingetroffen</em> sein. Der Poststempel zählt nicht.</li>
    <li style="margin-bottom:8px;"><strong>Neue Kasse:</strong> ${p.neu ? `Melde dich bei ${esc(p.neu)} für den 1. Januar an, falls noch nicht geschehen.` : 'Melde dich bei der neuen Kasse für den 1. Januar an, falls noch nicht geschehen.'} Sie muss dich ohne Gesundheitsfragen aufnehmen.</li>
    <li><strong>Bestätigung:</strong> Die neue Kasse meldet der alten, dass du versichert bist. Bis dahin bleibst du bei der alten versichert, also nie ohne Schutz.</li>
  </ol>
  ${p.wecker ? `<div style="background:#fff;border:1px solid rgba(0,0,0,.08);border-radius:12px;padding:16px 18px;margin:22px 0;font-size:14px;line-height:1.6;">
    <strong>Dein Wechsel-Wecker ist eingeschaltet.</strong> Nächstes Jahr, wenn Ende September die neuen Prämien kommen, schicken wir dir die besten Kassen für dich. Sonst nichts, keine Weitergabe an Kassen.
  </div>` : ''}
  <p style="font-size:12px;color:#6b6560;line-height:1.6;">Den Brief hast du selbst erstellt, wir haben ihn nur zugestellt und nicht gespeichert.${p.wecker ? ` Wecker nicht gewollt? <a href="${p.stopUrl}" style="color:#6b6560;">Hier abmelden</a>.` : ''}<br><a href="${SITE}/" style="color:#a68600;">abovergleich.com</a>, unabhängiger Krankenkassen-Vergleich. Von Krankenkassen nehmen wir keine Provisionen.</p>
</div></body></html>`;
}

const supabase = createClient(Deno.env.get('SUPABASE_URL')!, Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!);

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders });
  if (req.method !== 'POST') return json({ error: 'POST' }, 405);
  const key = Deno.env.get('RESEND_API_KEY');
  if (!key) return json({ error: 'Der Versand ist gerade nicht verfügbar. Lade das PDF herunter.' }, 503);
  const ip = (req.headers.get('x-forwarded-for') || '').split(',')[0].trim() || 'unknown';
  if (limited(ip)) return json({ error: 'Zu viele Versuche. Bitte später nochmals oder das PDF herunterladen.' }, 429);

  try {
    const b = await req.json();
    const email = String(b.email || '').trim().toLowerCase();
    if (!/^[^\s@]+@[^\s@]+\.[a-z]{2,}$/i.test(email) || email.length > 200) return json({ error: 'Bitte eine gültige E-Mail-Adresse eingeben.' }, 400);
    const pdf = String(b.pdf || '');
    if (!pdf || !/^[A-Za-z0-9+/=]+$/.test(pdf)) return json({ error: 'Das PDF fehlt. Bitte nochmals versuchen oder herunterladen.' }, 400);
    if (pdf.length > MAX_PDF) return json({ error: 'Das PDF ist zu gross. Lade es herunter.' }, 400);
    const filename = String(b.filename || 'Kuendigung.pdf').replace(/[^A-Za-z0-9._-]/g, '-').slice(0, 80);
    const kasse = String(b.kasse || 'deine Kasse').slice(0, 80);
    const plz = parseInt(b.plz), jahrgang = parseInt(b.jahrgang);
    const franchise = [300, 500, 1000, 1500, 2000, 2500].includes(parseInt(b.franchise)) ? parseInt(b.franchise) : 2500;

    // Wecker nur, wenn das Häkchen gesetzt ist (Voreinstellung, abwählbar),
    // und nur mit PLZ und Jahrgang. Sonst nur das PDF verschicken.
    let token: string | null = null;
    if (b.wecker === true && plz >= 1000 && plz <= 9699 && jahrgang >= 1920 && jahrgang <= 2030) {
      const now = new Date().toISOString();
      const row = {
        email, plz, jahrgang, franchise,
        accident_included: b.accident_included === true,
        current_insurer_id: parseInt(b.new_insurer_id) || parseInt(b.current_insurer_id) || null,
        new_insurer_id: parseInt(b.new_insurer_id) || null,
        paid_monthly: Number(b.paid_monthly) > 0 ? Number(b.paid_monthly) : null,
        source: 'kuendigung', consent_at: now, confirmed_at: now, unsubscribed_at: null,
      };
      const { data: existing } = await supabase.from('kk_wecker').select('id, token').ilike('email', email).limit(1);
      if (existing && existing.length) {
        token = existing[0].token;
        await supabase.from('kk_wecker').update(row).eq('id', existing[0].id);
      } else {
        const { data } = await supabase.from('kk_wecker').insert(row).select('token').single();
        token = data?.token ?? null;
      }
    }

    const html = mail({
      kasse, kanal: String(b.kanal || 'post'), ziel: String(b.ziel || '').slice(0, 120),
      deadline: String(b.deadline || '30. November').slice(0, 40), neu: String(b.neu || '').slice(0, 80),
      stopUrl: token ? `${WECKER}?stop=${token}` : `${SITE}/datenschutz/`, wecker: !!token,
    });
    const res = await fetch('https://api.resend.com/emails', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${key}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        from: Deno.env.get('WECKER_FROM') || 'abovergleich.com <wecker@abovergleich.com>',
        reply_to: 'hello@handyabo.com',
        to: [email],
        subject: `Deine Kündigung an ${kasse} (PDF)`,
        html,
        attachments: [{ filename, content: pdf }],
        headers: token ? { 'List-Unsubscribe': `<${WECKER}?stop=${token}>`, 'List-Unsubscribe-Post': 'List-Unsubscribe=One-Click' } : undefined,
      }),
    });
    if (!res.ok) {
      console.error('resend', res.status, await res.text());
      return json({ error: 'Die Mail konnte nicht verschickt werden. Lade das PDF herunter.' }, 502);
    }
    return json({ ok: true, wecker: !!token });
  } catch (err) {
    console.error(err);
    return json({ error: 'Versand nicht möglich. Lade das PDF herunter.' }, 500);
  }
});
