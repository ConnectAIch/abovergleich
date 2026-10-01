import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

// Kündigungs-Editor, zwei Schritte:
//
// 1. POST { email, pdf, ... }  (Editor): legt das PDF im privaten Speicher ab
//    (Bucket kuendigungen, 60 Tage), speichert die E-Mail-Adresse mit den
//    Wechselangaben in kk_wecker (noch unbestätigt) und schickt eine Mail mit
//    dem Knopf «Kündigung herunterladen».
// 2. POST { action: 'abholen', t } (Seite /krankenkasse-kuendigen/pdf/): erst
//    der Klick auf der Seite bestätigt die Adresse (confirmed_at) und liefert
//    einen kurz gültigen Download-Link. Ein Mailfilter, der den Link in der
//    Mail öffnet, bestätigt also nichts.
//
// Das Häkchen im Editor (voreingestellt, abwählbar) steuert nur die Jahresmail.

const SITE = 'https://abovergleich.com';
const MAX_PDF = 2_500_000; // Base64-Zeichen, rund 1,8 MB PDF
const BUCKET = 'kuendigungen';

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
};
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { ...corsHeaders, 'Content-Type': 'application/json' } });

const hits = new Map<string, number[]>();
function limited(ip: string, max: number) {
  const now = Date.now();
  const list = (hits.get(ip) || []).filter((t) => now - t < 3_600_000);
  list.push(now);
  hits.set(ip, list);
  return list.length > max;
}

const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]!));

function mail(p: { kasse: string; deadline: string; link: string }) {
  return `<!doctype html><html><body style="margin:0;background:#fafaf9;font-family:Inter,Arial,sans-serif;color:#1c1917;">
<div style="max-width:520px;margin:0 auto;padding:28px 20px;font-size:15px;line-height:1.6;">
  <div style="font-size:20px;font-weight:800;margin-bottom:18px;">abo<span style="color:#a68600;">vergleich</span>.com</div>
  <h1 style="font-size:21px;margin:0 0 14px;">Deine Kündigung an ${esc(p.kasse)} ist bereit</h1>
  <p style="margin:0 0 20px;">Frist: bis <strong>${esc(p.deadline)}</strong> bei der Kasse.</p>
  <a href="${p.link}" style="display:inline-block;background:#fed001;color:#1c1917;font-weight:700;text-decoration:none;padding:13px 22px;border-radius:10px;">Kündigung herunterladen</a>
  <p style="font-size:12px;color:#6b6560;margin-top:24px;">Damit bestätigst du auch deine E-Mail-Adresse. Der Link gilt 60 Tage.<br><a href="${SITE}/" style="color:#a68600;">abovergleich.com</a></p>
</div></body></html>`;
}

const supabase = createClient(Deno.env.get('SUPABASE_URL')!, Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!);

// Abgelaufene PDFs löschen, nebenbei bei jedem Aufruf
async function cleanup() {
  const { data } = await supabase.from('kk_kuendigung_pdf').select('token, path')
    .lt('expires_at', new Date().toISOString()).limit(50);
  if (!data || !data.length) return;
  await supabase.storage.from(BUCKET).remove(data.map((d) => d.path));
  await supabase.from('kk_kuendigung_pdf').delete().in('token', data.map((d) => d.token));
}

async function abholen(t: string) {
  if (!/^[0-9a-f-]{36}$/i.test(t)) return json({ error: 'Dieser Link ist ungültig.' }, 400);
  const { data: doc } = await supabase.from('kk_kuendigung_pdf').select('*').eq('token', t).maybeSingle();
  if (!doc || new Date(doc.expires_at) < new Date()) {
    return json({ error: 'Dieser Link ist abgelaufen. Erstell den Brief einfach nochmals.' }, 410);
  }
  const now = new Date().toISOString();
  await supabase.from('kk_kuendigung_pdf').update({ downloaded_at: doc.downloaded_at || now, downloads: doc.downloads + 1 }).eq('token', t);
  // Bestätigt: die Person hat den Link in ihrem Postfach angeklickt
  await supabase.from('kk_wecker').update({ confirmed_at: now }).ilike('email', doc.email).is('confirmed_at', null);
  const { data: signed, error } = await supabase.storage.from(BUCKET).createSignedUrl(doc.path, 300, { download: doc.filename });
  if (error || !signed) return json({ error: 'Das PDF ist gerade nicht erreichbar. Bitte nochmals versuchen.' }, 500);
  return json({
    ok: true, url: signed.signedUrl, filename: doc.filename,
    kasse: doc.kasse, kanal: doc.kanal, ziel: doc.ziel, neu: doc.neu, neu_url: doc.neu_url, deadline: doc.deadline,
  });
}

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders });
  if (req.method !== 'POST') return json({ error: 'POST' }, 405);
  const ip = (req.headers.get('x-forwarded-for') || '').split(',')[0].trim() || 'unknown';

  try {
    const b = await req.json();
    if (b.action === 'abholen') {
      if (limited('a:' + ip, 60)) return json({ error: 'Zu viele Versuche. Bitte später nochmals.' }, 429);
      return await abholen(String(b.t || ''));
    }

    const key = Deno.env.get('RESEND_API_KEY');
    if (!key) return json({ error: 'Der Versand ist gerade nicht verfügbar. Bitte später nochmals.' }, 503);
    if (limited(ip, 8)) return json({ error: 'Zu viele Versuche. Bitte später nochmals.' }, 429);
    const email = String(b.email || '').trim().toLowerCase();
    if (!/^[^\s@]+@[^\s@]+\.[a-z]{2,}$/i.test(email) || email.length > 200) return json({ error: 'Bitte eine gültige E-Mail-Adresse eingeben.' }, 400);
    const pdf = String(b.pdf || '');
    if (!pdf || !/^[A-Za-z0-9+/=]+$/.test(pdf)) return json({ error: 'Das PDF fehlt. Bitte nochmals versuchen.' }, 400);
    if (pdf.length > MAX_PDF) return json({ error: 'Das PDF ist zu gross. Bitte die Unterschrift neu zeichnen.' }, 400);
    const filename = String(b.filename || 'Kuendigung.pdf').replace(/[^A-Za-z0-9._-]/g, '-').slice(0, 80);
    const kasse = String(b.kasse || 'deine Kasse').slice(0, 80);
    const deadline = String(b.deadline || '30. November').slice(0, 40);
    const plz = parseInt(b.plz), jahrgang = parseInt(b.jahrgang);
    const franchise = [300, 500, 1000, 1500, 2000, 2500].includes(parseInt(b.franchise)) ? parseInt(b.franchise) : 2500;
    const wecker = b.wecker === true;
    cleanup().catch(() => {});

    // E-Mail-Adresse mit den Wechselangaben (Datenschutz 3.3). Unbestätigt,
    // bis der Download-Knopf geklickt ist. Ohne Häkchen: keine Jahresmail.
    if (plz >= 1000 && plz <= 9699 && jahrgang >= 1920 && jahrgang <= 2030) {
      const now = new Date().toISOString();
      const row = {
        email, plz, jahrgang, franchise,
        accident_included: b.accident_included === true,
        current_insurer_id: parseInt(b.new_insurer_id) || parseInt(b.current_insurer_id) || null,
        new_insurer_id: parseInt(b.new_insurer_id) || null,
        paid_monthly: Number(b.paid_monthly) > 0 ? Number(b.paid_monthly) : null,
        source: 'kuendigung', consent_at: wecker ? now : null, unsubscribed_at: wecker ? null : now,
      };
      const { data: existing } = await supabase.from('kk_wecker').select('id').ilike('email', email)
        .order('created_at', { ascending: false }).limit(1);
      if (existing && existing.length) await supabase.from('kk_wecker').update(row).eq('id', existing[0].id);
      else await supabase.from('kk_wecker').insert(row);
    }

    // PDF ablegen, Abhol-Link erzeugen
    const path = `${new Date().toISOString().slice(0, 10)}/${crypto.randomUUID()}.pdf`;
    const bytes = Uint8Array.from(atob(pdf), (c) => c.charCodeAt(0));
    const up = await supabase.storage.from(BUCKET).upload(path, bytes, { contentType: 'application/pdf' });
    if (up.error) { console.error('upload', up.error); return json({ error: 'Speichern nicht möglich. Bitte nochmals versuchen.' }, 500); }
    const { data: doc, error: docErr } = await supabase.from('kk_kuendigung_pdf').insert({
      email, path, filename, kasse, deadline,
      kanal: String(b.kanal || 'post').slice(0, 12), ziel: String(b.ziel || '').slice(0, 120),
      neu: String(b.neu || '').slice(0, 80) || null, neu_url: /^https:\/\//.test(String(b.neu_url || '')) ? String(b.neu_url).slice(0, 300) : null,
    }).select('token').single();
    if (docErr || !doc) { console.error('doc', docErr); return json({ error: 'Speichern nicht möglich. Bitte nochmals versuchen.' }, 500); }

    const res = await fetch('https://api.resend.com/emails', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${key}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        from: Deno.env.get('WECKER_FROM') || 'abovergleich.com <wecker@abovergleich.com>',
        reply_to: 'hello@handyabo.com',
        to: [email],
        subject: `Deine Kündigung an ${kasse}`,
        html: mail({ kasse, deadline, link: `${SITE}/krankenkasse-kuendigen/pdf/?t=${doc.token}` }),
      }),
    });
    if (!res.ok) {
      console.error('resend', res.status, await res.text());
      return json({ error: 'Die Mail konnte nicht verschickt werden. Bitte nochmals versuchen.' }, 502);
    }
    return json({ ok: true, wecker });
  } catch (err) {
    console.error(err);
    return json({ error: 'Versand nicht möglich. Bitte nochmals versuchen.' }, 500);
  }
});
