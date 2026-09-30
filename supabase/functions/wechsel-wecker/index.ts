import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

// Jährlicher Versand des Wechsel-Weckers. Einmal pro Jahr nach dem Import der
// neuen Prämien von Hand auslösen (Ende September):
//
//   POST { "year": 2028, "dry_run": true }      zuerst trocken
//   POST { "year": 2028 }                        dann scharf
//   Header: Authorization: Bearer <WECKER_TRIGGER_KEY>
//
// Empfänger: kk_wecker, bestätigt, nicht abgemeldet, für das Jahr noch nicht
// benachrichtigt. Versand über Resend (RESEND_API_KEY, optional WECKER_FROM).

const SITE = 'https://abovergleich.com';
const WECKER = 'https://zexpmaegqsayleaohiip.supabase.co/functions/v1/wecker';
// Rückverteilung Umweltabgaben pro Monat, gleich wie get-cheapest-premiums
const ENV_REFUND: Record<number, number> = { 2026: 5.15, 2027: 4.75 };
const MODEL: Record<string, string> = {
  standard: 'Standard', family_doctor: 'Hausarzt', hmo: 'HMO', telmed: 'Telmed', diverse: 'Alternativ', apotheke: 'Apotheke',
};

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
};
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { ...corsHeaders, 'Content-Type': 'application/json' } });

type Offer = { insurer_id: number; insurer_name: string; premium: number; model_type: string; tariff: string; tariff_name: string };
type Sub = { id: string; email: string; plz: number; jahrgang: number; franchise: number; accident_included: boolean;
             current_insurer_id: number | null; paid_monthly: number | null; token: string };

const chf = (v: number, d = 2) => v.toLocaleString('de-CH', { minimumFractionDigits: d, maximumFractionDigits: d });
const label = (o: Offer) => o.model_type === 'standard' ? 'Standard (freie Arztwahl)' : `${MODEL[o.model_type] || o.model_type} · ${o.tariff_name}`;
const ageClass = (year: number, born: number) => { const a = year - born; return a <= 18 ? 'AKL-KIN' : a <= 25 ? 'AKL-JUG' : 'AKL-ERW'; };

async function sendMail(to: string, subject: string, html: string, stopUrl: string): Promise<boolean> {
  const key = Deno.env.get('RESEND_API_KEY');
  if (!key) return false;
  const res = await fetch('https://api.resend.com/emails', {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${key}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      from: Deno.env.get('WECKER_FROM') || 'abovergleich.com <hello@handyabo.com>',
      reply_to: 'hello@handyabo.com',
      to: [to], subject, html,
      headers: { 'List-Unsubscribe': `<${stopUrl}>`, 'List-Unsubscribe-Post': 'List-Unsubscribe=One-Click' },
    }),
  });
  return res.ok;
}

function mail(year: number, own: Offer | null, ownPrev: number | null, best: Offer, save: number, sub: Sub, stopUrl: string): string {
  const refund = ENV_REFUND[year] ?? 0;
  const ownBlock = own ? `
    <div style="background:#f5f5f4;border-radius:12px;padding:18px;margin-bottom:14px;">
      <div style="font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:#78716c;">Deine Kasse ${year}</div>
      <div style="font-size:17px;font-weight:700;margin-top:4px;">${own.insurer_name}</div>
      <div style="font-size:13px;color:#78716c;">${label(own)}</div>
      <div style="font-size:22px;font-weight:800;margin-top:6px;">CHF ${chf(own.premium)} / Monat</div>
      <div style="font-size:13px;color:#44403c;">Auf der Rechnung CHF ${chf(own.premium - refund)} nach Abzug Umweltabgabe${ownPrev ? `, ${year - 1}: CHF ${chf(ownPrev)}` : ''}</div>
    </div>` : '';
  const verdict = own && save < 12
    ? `<p style="font-size:15px;line-height:1.6;">Gute Nachricht: Du bist bereits bei der günstigsten Kasse für dein Profil. Ein Wechsel lohnt sich dieses Jahr nicht.</p>`
    : `<div style="background:rgba(254,208,1,0.1);border:1px solid rgba(254,208,1,0.4);border-radius:12px;padding:18px;margin-bottom:14px;">
      <div style="font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:#7a6200;">Günstigste Kasse ${year}</div>
      <div style="font-size:17px;font-weight:700;margin-top:4px;">${best.insurer_name}</div>
      <div style="font-size:13px;color:#78716c;">${label(best)}</div>
      <div style="font-size:22px;font-weight:800;margin-top:6px;">CHF ${chf(best.premium)} / Monat</div>
      ${own ? `<div style="font-size:14px;font-weight:700;color:#15803d;margin-top:6px;">Du sparst CHF ${chf(save, 0)} pro Jahr</div>` : ''}
    </div>`;
  const q = `?kasse=${sub.current_insurer_id || ''}#kk-rechner`;
  return `<!DOCTYPE html><html lang="de"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;background:#fafaf9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#1c1917;">
<div style="max-width:540px;margin:0 auto;padding:36px 20px;">
  <div style="font-weight:800;font-size:20px;margin-bottom:24px;">abo<span style="color:#a68600;">vergleich</span>.com</div>
  <div style="background:#fff;border:1px solid rgba(0,0,0,0.08);border-radius:14px;padding:26px;">
    <h1 style="font-size:20px;margin:0 0 6px;">Die Prämien ${year} sind da</h1>
    <p style="font-size:14px;color:#78716c;margin:0 0 18px;">PLZ ${sub.plz} · Jahrgang ${sub.jahrgang} · Franchise CHF ${chf(sub.franchise, 0)} · ${sub.accident_included ? 'mit' : 'ohne'} Unfall</p>
    ${ownBlock}${verdict}
    <a href="${SITE}/${q}" style="display:inline-block;background:#fed001;color:#1c1917;padding:13px 22px;border-radius:10px;font-weight:700;text-decoration:none;margin:4px 8px 4px 0;">Alle Kassen vergleichen</a>
    <a href="${SITE}/krankenkasse-kuendigen/${sub.current_insurer_id ? `?kasse=${sub.current_insurer_id}` : ''}" style="display:inline-block;color:#7a6200;font-weight:700;text-decoration:none;margin:4px 0;">Kündigungsbrief erstellen &rarr;</a>
    <p style="font-size:13px;line-height:1.6;color:#78716c;margin:18px 0 0;">Die Kündigung muss bis am 30. November bei deiner Kasse eingetroffen sein. Die Leistungen der Grundversicherung sind bei allen Kassen gleich.</p>
  </div>
  <p style="font-size:12px;color:#a8a29e;line-height:1.6;text-align:center;margin-top:20px;">Du bekommst diese Mail, weil du den Wechsel-Wecker auf abovergleich.com bestätigt hast. <a href="${stopUrl}" style="color:#a8a29e;">Abmelden</a></p>
</div></body></html>`;
}

Deno.serve(async (req: Request) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders });
  const triggerKey = Deno.env.get('WECKER_TRIGGER_KEY');
  if (!triggerKey || req.headers.get('authorization') !== `Bearer ${triggerKey}`) return json({ error: 'Unauthorized' }, 401);

  let year = new Date().getFullYear() + 1, dryRun = false, limit = 0;
  try { const b = await req.json(); if (b.year) year = b.year; if (b.dry_run) dryRun = true; if (b.limit) limit = b.limit; } catch { /* leer */ }

  const supabase = createClient(Deno.env.get('SUPABASE_URL')!, Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!);
  const { count } = await supabase.from('premiums').select('id', { count: 'exact', head: true }).eq('year', year);
  if (!count) return json({ error: `Keine Prämien für ${year} in der Datenbank` }, 409);

  let q = supabase.from('kk_wecker').select('*').not('confirmed_at', 'is', null).is('unsubscribed_at', null)
    .or(`last_notified_year.is.null,last_notified_year.lt.${year}`);
  if (limit) q = q.limit(limit);
  const { data: subs, error } = await q;
  if (error) return json({ error: error.message }, 500);

  const results: { email: string; status: string; save?: number }[] = [];
  for (const sub of (subs || []) as Sub[]) {
    try {
      const { data: plzData } = await supabase.from('plz_regions').select('canton, region').eq('plz', sub.plz).limit(1);
      if (!plzData?.length) { results.push({ email: sub.email, status: 'skipped: PLZ' }); continue; }
      const { canton, region } = plzData[0];
      const fetchOffers = (y: number) => {
        const ac = ageClass(y, sub.jahrgang);
        let qq = supabase.from('premiums').select('insurer_id, insurer_name, premium, model_type, tariff, tariff_name')
          .eq('year', y).eq('canton', canton).eq('region', `PR-REG CH${region}`).eq('age_class', ac)
          .eq('franchise', sub.franchise).eq('accident_included', sub.accident_included).order('premium').limit(1000);
        if (ac === 'AKL-KIN') qq = qq.eq('age_subgroup', 'K1');
        return qq;
      };
      const [{ data: cur }, { data: prev }] = await Promise.all([fetchOffers(year), fetchOffers(year - 1)]);
      const offers = ((cur || []) as Offer[]).map(o => ({ ...o, premium: Number(o.premium) }));
      if (!offers.length) { results.push({ email: sub.email, status: 'skipped: keine Prämien' }); continue; }
      const best = offers[0];

      // eigene Kasse: Tarif über den Rechnungsbetrag erkennen, sonst Standardmodell
      let own: Offer | null = null, ownPrev: number | null = null;
      if (sub.current_insurer_id) {
        const mine = offers.filter(o => o.insurer_id === sub.current_insurer_id);
        const prevMine = ((prev || []) as Offer[]).filter(o => o.insurer_id === sub.current_insurer_id);
        if (sub.paid_monthly) {
          const hit = prevMine.find(p => Math.abs(Number(p.premium) - (ENV_REFUND[year - 1] ?? 0) - Number(sub.paid_monthly)) < 0.06
            || Math.abs(Number(p.premium) - Number(sub.paid_monthly)) < 0.06);
          if (hit) { own = mine.find(o => o.tariff.toLowerCase() === hit.tariff.toLowerCase()) || null; ownPrev = Number(hit.premium); }
        }
        if (!own) {
          own = mine.find(o => o.model_type === 'standard') || mine[mine.length - 1] || null;
          const p = own && prevMine.find(x => x.tariff.toLowerCase() === own!.tariff.toLowerCase());
          ownPrev = p ? Number(p.premium) : null;
        }
      }
      const save = own ? (own.premium - best.premium) * 12 : 0;
      const stopUrl = `${WECKER}?stop=${sub.token}`;
      const subject = own && save >= 12
        ? `Prämien ${year}: Du kannst CHF ${chf(save, 0)} pro Jahr sparen`
        : `Prämien ${year}: dein persönlicher Vergleich`;

      if (dryRun) { results.push({ email: sub.email, status: 'dry_run', save: Math.round(save) }); continue; }
      const ok = await sendMail(sub.email, subject, mail(year, own, ownPrev, best, save, sub, stopUrl), stopUrl);
      if (ok) await supabase.from('kk_wecker').update({ last_notified_year: year }).eq('id', sub.id);
      results.push({ email: sub.email, status: ok ? 'sent' : 'failed', save: Math.round(save) });
    } catch (err) {
      results.push({ email: sub.email, status: `error: ${(err as Error).message}` });
    }
  }
  return json({ year, dry_run: dryRun, total: results.length, sent: results.filter(r => r.status === 'sent').length, results });
});
