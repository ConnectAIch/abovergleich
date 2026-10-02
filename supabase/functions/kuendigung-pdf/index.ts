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
// 3. POST { action: 'erinnern' } (täglich, GitHub Action): höchstens je eine
//    Erinnerung «noch nicht abgeholt» (nach 2 Tagen), «schon angemeldet?»
//    (3 Tage nach dem Abholen) und «Kündigung bestätigt?» (ab 10. Dezember).
//    Idempotent: jede Erinnerung geht pro Brief genau einmal raus.
// 4. POST { action: 'antwort', t, frage, a } (Abholseite): Antwort speichern.
//
// Das Häkchen im Editor (voreingestellt, abwählbar) steuert nur die Jahresmail.
//
// Sprachen: Die Seite schickt lang (de, fr, en) mit. Mails, Erinnerungen und
// Fehlermeldungen kommen in dieser Sprache, die Links führen auf die
// Abholseite derselben Sprache. Gespeichert in kk_kuendigung_pdf.lang.

const SITE = 'https://abovergleich.com';
type Lang = 'de' | 'fr' | 'en';
const LANGS = ['de', 'fr', 'en'];
const lng = (v: unknown): Lang => (LANGS.includes(String(v)) ? String(v) : 'de') as Lang;
const PICKUP: Record<Lang, string> = { de: '/krankenkasse-kuendigen/pdf/', fr: '/fr/resilier-caisse-maladie/pdf/', en: '/en/cancel-health-insurance/pdf/' };
const HOME: Record<Lang, string> = { de: '/', fr: '/fr/', en: '/en/' };

// Texte in drei Sprachen; {k} = Kasse, {n} = neue Kasse, {d} = Frist
const TX: Record<string, Record<Lang, string>> = {
  bad_link: { de: 'Dieser Link ist ungültig.', fr: 'Ce lien n’est pas valable.', en: 'This link is not valid.' },
  expired: { de: 'Dieser Link ist abgelaufen. Erstell den Brief einfach nochmals.', fr: 'Ce lien a expiré. Recréez simplement la lettre.', en: 'This link has expired. Just create the letter again.' },
  unavailable: { de: 'Das PDF ist gerade nicht erreichbar. Bitte nochmals versuchen.', fr: 'Le PDF n’est pas disponible pour le moment. Veuillez réessayer.', en: 'The PDF is not available right now. Please try again.' },
  gone: { de: 'Diesen Brief gibt es nicht mehr.', fr: 'Cette lettre n’existe plus.', en: 'This letter no longer exists.' },
  unknown_q: { de: 'Unbekannte Frage.', fr: 'Question inconnue.', en: 'Unknown question.' },
  rate: { de: 'Zu viele Versuche. Bitte später nochmals.', fr: 'Trop de tentatives. Veuillez réessayer plus tard.', en: 'Too many attempts. Please try again later.' },
  off: { de: 'Der Versand ist gerade nicht verfügbar. Bitte später nochmals.', fr: 'L’envoi n’est pas disponible pour le moment. Veuillez réessayer plus tard.', en: 'Sending is not available right now. Please try again later.' },
  email: { de: 'Bitte eine gültige E-Mail-Adresse eingeben.', fr: 'Veuillez saisir une adresse e-mail valable.', en: 'Please enter a valid email address.' },
  no_pdf: { de: 'Das PDF fehlt. Bitte nochmals versuchen.', fr: 'Le PDF manque. Veuillez réessayer.', en: 'The PDF is missing. Please try again.' },
  big_pdf: { de: 'Das PDF ist zu gross. Bitte die Unterschrift neu zeichnen.', fr: 'Le PDF est trop volumineux. Veuillez refaire la signature.', en: 'The PDF is too large. Please redraw your signature.' },
  store: { de: 'Speichern nicht möglich. Bitte nochmals versuchen.', fr: 'Enregistrement impossible. Veuillez réessayer.', en: 'Could not save. Please try again.' },
  mail_fail: { de: 'Die Mail konnte nicht verschickt werden. Bitte nochmals versuchen.', fr: 'L’e-mail n’a pas pu être envoyé. Veuillez réessayer.', en: 'The email could not be sent. Please try again.' },
  fail: { de: 'Versand nicht möglich. Bitte nochmals versuchen.', fr: 'Envoi impossible. Veuillez réessayer.', en: 'Sending failed. Please try again.' },
  your_kasse: { de: 'deine Kasse', fr: 'votre caisse', en: 'your insurer' },
  s_ready: { de: 'Deine Kündigung an {k}', fr: 'Votre résiliation pour {k}', en: 'Your cancellation to {k}' },
  h_ready: { de: 'Deine Kündigung an {k} ist bereit', fr: 'Votre résiliation pour {k} est prête', en: 'Your cancellation to {k} is ready' },
  p_ready: { de: 'Frist: bis <strong>{d}</strong> bei der Kasse. Nach dem Klick zeigen wir dir die nächsten Schritte.',
             fr: 'Délai : elle doit parvenir à la caisse au plus tard le <strong>{d}</strong>. Après le clic, nous vous montrons les prochaines étapes.',
             en: 'Deadline: it must reach the insurer by <strong>{d}</strong>. After the click we show you the next steps.' },
  b_download: { de: 'Kündigung herunterladen', fr: 'Télécharger la résiliation', en: 'Download your cancellation' },
  f_ready: { de: 'Damit bestätigst du auch deine E-Mail-Adresse. Der Link gilt 60 Tage.', fr: 'Cela confirme aussi votre adresse e-mail. Le lien est valable 60 jours.', en: 'This also confirms your email address. The link is valid for 60 days.' },
  stop: { de: 'Keine Erinnerungen mehr', fr: 'Ne plus recevoir de rappels', en: 'No more reminders' },
  s_wait: { de: 'Deine Kündigung an {k} wartet noch', fr: 'Votre résiliation pour {k} vous attend', en: 'Your cancellation to {k} is still waiting' },
  p_wait: { de: 'Sie muss bis <strong>{d}</strong> bei der Kasse sein.', fr: 'Elle doit parvenir à la caisse au plus tard le <strong>{d}</strong>.', en: 'It must reach the insurer by <strong>{d}</strong>.' },
  s_reg_n: { de: 'Schon bei {n} angemeldet?', fr: 'Déjà inscrit chez {n} ?', en: 'Signed up with {n} yet?' },
  s_reg: { de: 'Schon bei der neuen Kasse angemeldet?', fr: 'Déjà inscrit auprès de la nouvelle caisse ?', en: 'Signed up with your new insurer yet?' },
  p_reg: { de: 'Ohne Anmeldung bleibst du bei {k}. Online dauert sie etwa 10 Minuten.', fr: 'Sans inscription, vous restez chez {k}. En ligne, cela prend environ 10 minutes.', en: 'Without signing up you stay with {k}. It takes about 10 minutes online.' },
  yes_done: { de: 'Ja, erledigt', fr: 'Oui, c’est fait', en: 'Yes, done' },
  not_yet: { de: 'Noch nicht', fr: 'Pas encore', en: 'Not yet' },
  s_conf: { de: 'Hat {k} deine Kündigung bestätigt?', fr: '{k} a-t-elle confirmé votre résiliation ?', en: 'Has {k} confirmed your cancellation?' },
  p_conf: { de: 'Meist kommt bis Mitte Dezember ein Brief oder eine Mail. Fehlt die Bestätigung, lohnt sich ein Anruf.', fr: 'Une lettre ou un e-mail arrive généralement d’ici mi-décembre. Sans confirmation, un appel vaut la peine.', en: 'A letter or email usually arrives by mid-December. If there is no confirmation, it is worth a call.' },
  yes_conf: { de: 'Ja, bestätigt', fr: 'Oui, confirmée', en: 'Yes, confirmed' },
  nothing: { de: 'Noch nichts', fr: 'Toujours rien', en: 'Nothing yet' },
};
const tx = (k: string, l: Lang, v: Record<string, string> = {}) =>
  (TX[k][l] || TX[k].de).replace(/\{(\w)\}/g, (_, x) => v[x] ?? '');
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

function mail(p: { kasse: string; deadline: string; link: string; lang: Lang }) {
  const l = p.lang;
  return `<!doctype html><html lang="${l}"><body style="margin:0;background:#fafaf9;font-family:Inter,Arial,sans-serif;color:#1c1917;">
<div style="max-width:520px;margin:0 auto;padding:28px 20px;font-size:15px;line-height:1.6;">
  <div style="font-size:20px;font-weight:800;margin-bottom:18px;">abo<span style="color:#a68600;">vergleich</span>.com</div>
  <h1 style="font-size:21px;margin:0 0 14px;">${tx('h_ready', l, { k: esc(p.kasse) })}</h1>
  <p style="margin:0 0 20px;">${tx('p_ready', l, { d: esc(p.deadline) })}</p>
  <a href="${p.link}" style="display:inline-block;background:#fed001;color:#1c1917;font-weight:700;text-decoration:none;padding:13px 22px;border-radius:10px;">${tx('b_download', l)}</a>
  <p style="font-size:12px;color:#6b6560;margin-top:24px;">${tx('f_ready', l)}<br><a href="${SITE}${HOME[l]}" style="color:#a68600;">abovergleich.com</a></p>
</div></body></html>`;
}

const supabase = createClient(Deno.env.get('SUPABASE_URL')!, Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!);

// Abgelaufene PDFs löschen. Die Zeile bleibt (ohne Datei) für die
// Erinnerungen und wird erst nach 400 Tagen entfernt.
async function cleanup() {
  const { data } = await supabase.from('kk_kuendigung_pdf').select('token, path')
    .lt('expires_at', new Date().toISOString()).not('path', 'is', null).limit(50);
  if (data && data.length) {
    await supabase.storage.from(BUCKET).remove(data.map((d) => d.path));
    await supabase.from('kk_kuendigung_pdf').update({ path: null }).in('token', data.map((d) => d.token));
  }
  await supabase.from('kk_kuendigung_pdf').delete().lt('created_at', new Date(Date.now() - 400 * 86_400_000).toISOString());
}

async function abholen(t: string, l: Lang) {
  if (!/^[0-9a-f-]{36}$/i.test(t)) return json({ error: tx('bad_link', l) }, 400);
  const { data: doc } = await supabase.from('kk_kuendigung_pdf').select('*').eq('token', t).maybeSingle();
  if (!doc || !doc.path || new Date(doc.expires_at) < new Date()) {
    return json({ error: tx('expired', l) }, 410);
  }
  const now = new Date().toISOString();
  await supabase.from('kk_kuendigung_pdf').update({ downloaded_at: doc.downloaded_at || now, downloads: doc.downloads + 1 }).eq('token', t);
  // Bestätigt: die Person hat den Link in ihrem Postfach angeklickt
  await supabase.from('kk_wecker').update({ confirmed_at: now }).ilike('email', doc.email).is('confirmed_at', null);
  const { data: signed, error } = await supabase.storage.from(BUCKET).createSignedUrl(doc.path, 300, { download: doc.filename });
  if (error || !signed) return json({ error: tx('unavailable', l) }, 500);
  return json({
    ok: true, url: signed.signedUrl, filename: doc.filename,
    kasse: doc.kasse, kanal: doc.kanal, ziel: doc.ziel, neu: doc.neu, neu_url: doc.neu_url, deadline: doc.deadline, signiert: doc.signiert,
  });
}

// ── Erinnerungen ────────────────────────────────────────────────────────
const page = (t: string, extra = '', l: Lang = 'de') => `${SITE}${PICKUP[l]}?t=${t}${extra}`;

function frame(title: string, inner: string, t: string, l: Lang = 'de') {
  return `<!doctype html><html lang="${l}"><body style="margin:0;background:#fafaf9;font-family:Inter,Arial,sans-serif;color:#1c1917;">
<div style="max-width:520px;margin:0 auto;padding:28px 20px;font-size:15px;line-height:1.6;">
  <div style="font-size:20px;font-weight:800;margin-bottom:18px;">abo<span style="color:#a68600;">vergleich</span>.com</div>
  <h1 style="font-size:21px;margin:0 0 14px;">${title}</h1>
  ${inner}
  <p style="font-size:12px;color:#6b6560;margin-top:24px;"><a href="${page(t, '&frage=stopp', l)}" style="color:#6b6560;">${tx('stop', l)}</a> · <a href="${SITE}${HOME[l]}" style="color:#a68600;">abovergleich.com</a></p>
</div></body></html>`;
}
const btn = (href: string, label: string, primary = true) =>
  `<a href="${href}" style="display:inline-block;background:${primary ? '#fed001' : '#f0efed'};color:#1c1917;font-weight:700;text-decoration:none;padding:12px 20px;border-radius:10px;margin:0 8px 8px 0;">${label}</a>`;

async function send(key: string, to: string, subject: string, html: string) {
  const res = await fetch('https://api.resend.com/emails', {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${key}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ from: Deno.env.get('WECKER_FROM') || 'abovergleich.com <wecker@abovergleich.com>',
      reply_to: 'hello@handyabo.com', to: [to], subject, html }),
  });
  if (!res.ok) console.error('resend', res.status, await res.text());
  return res.ok;
}

async function erinnern(key: string) {
  const now = new Date(), iso = now.toISOString();
  const day = 86_400_000, out = { abholen: 0, anmeldung: 0, bestaetigung: 0 };
  const base = () => supabase.from('kk_kuendigung_pdf').select('*').eq('keine_erinnerung', false).limit(100);

  // a) zwei Tage nicht abgeholt, Datei noch da
  const { data: a } = await base().is('downloaded_at', null).is('erinnert_abholen_at', null).not('path', 'is', null)
    .lt('created_at', new Date(now.getTime() - 2 * day).toISOString()).gt('expires_at', iso);
  for (const d of a || []) {
    const l = lng(d.lang);
    const ok = await send(key, d.email, tx('s_wait', l, { k: d.kasse }), frame(tx('s_wait', l, { k: esc(d.kasse) }),
      `<p style="margin:0 0 20px;">${tx('p_wait', l, { d: esc(d.deadline || '30. November') })}</p>${btn(page(d.token, '', l), tx('b_download', l))}`, d.token, l));
    if (ok) { await supabase.from('kk_kuendigung_pdf').update({ erinnert_abholen_at: iso }).eq('token', d.token); out.abholen++; }
  }

  // b) drei Tage nach dem Abholen: schon bei der neuen Kasse angemeldet?
  const { data: b } = await base().not('downloaded_at', 'is', null).is('erinnert_anmeldung_at', null).is('angemeldet', null)
    .lt('downloaded_at', new Date(now.getTime() - 3 * day).toISOString());
  for (const d of b || []) {
    const l = lng(d.lang);
    const subj = (v: (s: string) => string) => d.neu ? tx('s_reg_n', l, { n: v(d.neu) }) : tx('s_reg', l);
    const ok = await send(key, d.email, subj((s) => s), frame(subj(esc),
      `<p style="margin:0 0 18px;">${tx('p_reg', l, { k: esc(d.kasse) })}</p>
       ${btn(page(d.token, '&frage=anmeldung&a=ja', l), tx('yes_done', l))}${btn(page(d.token, '&frage=anmeldung&a=nein', l), tx('not_yet', l), false)}`, d.token, l));
    if (ok) { await supabase.from('kk_kuendigung_pdf').update({ erinnert_anmeldung_at: iso }).eq('token', d.token); out.anmeldung++; }
  }

  // c) ab 10. Dezember: Kündigung bestätigt? Nur Briefe aus dieser Saison.
  const y = now.getUTCFullYear();
  if (now >= new Date(Date.UTC(y, 11, 10))) {
    const { data: c } = await base().not('downloaded_at', 'is', null).is('erinnert_bestaetigung_at', null).is('bestaetigt', null)
      .gt('created_at', new Date(Date.UTC(y, 7, 1)).toISOString());
    for (const d of c || []) {
      const l = lng(d.lang);
      const ok = await send(key, d.email, tx('s_conf', l, { k: d.kasse }), frame(tx('s_conf', l, { k: esc(d.kasse) }),
        `<p style="margin:0 0 18px;">${tx('p_conf', l)}</p>
         ${btn(page(d.token, '&frage=bestaetigung&a=ja', l), tx('yes_conf', l))}${btn(page(d.token, '&frage=bestaetigung&a=nein', l), tx('nothing', l), false)}`, d.token, l));
      if (ok) { await supabase.from('kk_kuendigung_pdf').update({ erinnert_bestaetigung_at: iso }).eq('token', d.token); out.bestaetigung++; }
    }
  }
  return json({ ok: true, ...out });
}

async function antwort(t: string, frage: string, a: string, l: Lang) {
  if (!/^[0-9a-f-]{36}$/i.test(t)) return json({ error: tx('bad_link', l) }, 400);
  const { data: d } = await supabase.from('kk_kuendigung_pdf').select('token, kasse, neu, neu_url, deadline').eq('token', t).maybeSingle();
  if (!d) return json({ error: tx('gone', l) }, 410);
  const now = new Date().toISOString();
  const upd: Record<string, unknown> = { antwort_at: now };
  if (frage === 'anmeldung') upd.angemeldet = a === 'ja';
  else if (frage === 'bestaetigung') upd.bestaetigt = a === 'ja';
  else if (frage === 'stopp') upd.keine_erinnerung = true;
  else return json({ error: tx('unknown_q', l) }, 400);
  await supabase.from('kk_kuendigung_pdf').update(upd).eq('token', t);
  return json({ ok: true, kasse: d.kasse, neu: d.neu, neu_url: d.neu_url, deadline: d.deadline });
}

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders });
  if (req.method !== 'POST') return json({ error: 'POST' }, 405);
  const ip = (req.headers.get('x-forwarded-for') || '').split(',')[0].trim() || 'unknown';

  try {
    const b = await req.json();
    const l = lng(b.lang);
    if (b.action === 'erinnern') {
      const key = Deno.env.get('RESEND_API_KEY');
      if (!key) return json({ error: 'not_configured' }, 503);
      if (limited('e:' + ip, 6)) return json({ error: 'rate' }, 429);
      await cleanup();
      return await erinnern(key);
    }
    if (b.action === 'antwort') {
      if (limited('w:' + ip, 60)) return json({ error: tx('rate', l) }, 429);
      return await antwort(String(b.t || ''), String(b.frage || ''), String(b.a || ''), l);
    }
    if (b.action === 'abholen') {
      if (limited('a:' + ip, 60)) return json({ error: tx('rate', l) }, 429);
      return await abholen(String(b.t || ''), l);
    }

    const key = Deno.env.get('RESEND_API_KEY');
    if (!key) return json({ error: tx('off', l) }, 503);
    if (limited(ip, 8)) return json({ error: tx('rate', l) }, 429);
    const email = String(b.email || '').trim().toLowerCase();
    if (!/^[^\s@]+@[^\s@]+\.[a-z]{2,}$/i.test(email) || email.length > 200) return json({ error: tx('email', l) }, 400);
    const pdf = String(b.pdf || '');
    if (!pdf || !/^[A-Za-z0-9+/=]+$/.test(pdf)) return json({ error: tx('no_pdf', l) }, 400);
    if (pdf.length > MAX_PDF) return json({ error: tx('big_pdf', l) }, 400);
    const filename = String(b.filename || 'Kuendigung.pdf').replace(/[^A-Za-z0-9._-]/g, '-').slice(0, 80);
    const kasse = String(b.kasse || tx('your_kasse', l)).slice(0, 80);
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
        source: 'kuendigung', consent_at: wecker ? now : null, unsubscribed_at: wecker ? null : now, lang: l,
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
    if (up.error) { console.error('upload', up.error); return json({ error: tx('store', l) }, 500); }
    const { data: doc, error: docErr } = await supabase.from('kk_kuendigung_pdf').insert({
      email, path, filename, kasse, deadline, signiert: b.signiert === true, lang: l,
      kanal: String(b.kanal || 'post').slice(0, 12), ziel: String(b.ziel || '').slice(0, 120),
      neu: String(b.neu || '').slice(0, 80) || null, neu_url: /^https:\/\//.test(String(b.neu_url || '')) ? String(b.neu_url).slice(0, 300) : null,
    }).select('token').single();
    if (docErr || !doc) { console.error('doc', docErr); return json({ error: tx('store', l) }, 500); }

    const res = await fetch('https://api.resend.com/emails', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${key}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        from: Deno.env.get('WECKER_FROM') || 'abovergleich.com <wecker@abovergleich.com>',
        reply_to: 'hello@handyabo.com',
        to: [email],
        subject: tx('s_ready', l, { k: kasse }),
        html: mail({ kasse, deadline, link: page(doc.token, '', l), lang: l }),
      }),
    });
    if (!res.ok) {
      console.error('resend', res.status, await res.text());
      return json({ error: tx('mail_fail', l) }, 502);
    }
    return json({ ok: true, wecker });
  } catch (err) {
    console.error(err);
    return json({ error: tx('fail', 'de') }, 500);
  }
});
