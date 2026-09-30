import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
};

interface UserProfile {
  id: string;
  email: string;
  plz: string;
  jahrgang: number;
  franchise: number;
  current_insurer_id: number;
  current_model: string;
  wecker_active: boolean;
  last_notified_year: number | null;
}

interface Premium {
  insurer_name: string;
  premium: number;
  model_type: string;
  tariff_name: string;
}

// Schlüssel = premiums.insurer_name. Websites laut BAG-Verzeichnis der
// zugelassenen Krankenversicherer (1.1.2026), gleich wie im Rechner auf index.html.
const insurerUrls: Record<string, string> = {
  'AMB': 'https://www.groupemutuel.ch',
  'Agrisano': 'https://www.agrisano.ch',
  'Aquilana': 'https://www.aquilana.ch',
  'Assura': 'https://www.assura.ch',
  'Atupri': 'https://www.atupri.ch',
  'Avenir': 'https://www.groupemutuel.ch',
  'Birchmeier': 'https://www.kkbirchmeier.ch',
  'Concordia': 'https://www.concordia.ch',
  'CSS': 'https://www.css.ch',
  'curaulta': 'https://www.curaulta.ch',
  'EGK': 'https://www.egk.ch',
  'Einsiedler Krankenkasse': 'https://www.kkeinsiedeln.ch',
  'Galenos': 'https://www.galenos.ch',
  'Glarner': 'https://www.glkv.ch',
  'Helsana': 'https://www.helsana.ch',
  'KK Luzerner Hinterland': 'https://www.kklh.ch',
  'KK Steffisburg': 'https://www.kkst.ch',
  'KK Visperterminen': 'https://www.kkv.ch',
  'KK Wädenswil': 'https://www.kkwaedenswil.ch',
  'KPT': 'https://www.kpt.ch',
  'Mutuel': 'https://www.groupemutuel.ch',
  'ÖKK': 'https://www.oekk.ch',
  'Philos': 'https://www.groupemutuel.ch',
  'rhenusana': 'https://www.rhenusana.ch',
  'sana24': 'https://www.visana.ch',
  'Sanitas': 'https://www.sanitas.com',
  'SLKK': 'https://www.slkk.ch',
  'sodalis': 'https://www.sodalis.ch',
  'Sumiswalder': 'https://www.sumiswalder.ch',
  'Swica': 'https://www.swica.ch',
  'Visana': 'https://www.visana.ch',
  'vita surselva': 'https://www.vitasurselva.ch',
  'Vivao Sympany': 'https://www.sympany.ch',
};

function affiliateLink(insurerName: string): string {
  const base = insurerUrls[insurerName] || 'https://abovergleich.com';
  return `${base}?utm_source=abovergleich.com&utm_medium=affiliate&utm_campaign=wechsel-wecker`;
}

function buildEmail(user: UserProfile, currentPremium: Premium | null, cheapest: Premium, yearlyDiff: number): string {
  const currentDisplay = currentPremium
    ? `CHF ${currentPremium.premium.toFixed(2)}/Mt.`
    : 'nicht verfügbar';
  const link = affiliateLink(cheapest.insurer_name);
  const modelNames: Record<string, string> = {
    standard: 'Standard', hmo: 'HMO', telmed: 'Telmed',
    family_doctor: 'Hausarzt', diverse: 'Alternativ'
  };

  return `<!DOCTYPE html>
<html lang="de">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#fafaf9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <div style="max-width:560px;margin:0 auto;padding:40px 20px;">
    <div style="text-align:center;margin-bottom:32px;">
      <span style="font-weight:800;font-size:20px;color:#1c1917;">abo<span style="color:#a68600;">vergleich</span>.com</span>
    </div>
    <div style="background:#ffffff;border-radius:16px;padding:32px;border:1px solid rgba(0,0,0,0.06);">
      <div style="text-align:center;font-size:40px;margin-bottom:16px;">&#9200;</div>
      <h1 style="font-size:22px;font-weight:800;color:#1c1917;text-align:center;margin:0 0 8px;">Dein Wechsel-Wecker klingelt!</h1>
      <p style="font-size:15px;color:#78716c;text-align:center;line-height:1.6;margin:0 0 28px;">Die neuen Krankenkassenpr&auml;mien sind da. Wir haben f&uuml;r dich gerechnet:</p>

      <div style="background:#f5f5f4;border-radius:12px;padding:20px;margin-bottom:20px;">
        <div style="font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:0.05em;color:#78716c;margin-bottom:8px;">Deine aktuelle Kasse</div>
        <div style="font-size:18px;font-weight:700;color:#1c1917;">${currentPremium?.insurer_name || 'Unbekannt'}</div>
        <div style="font-size:24px;font-weight:800;color:#1c1917;margin-top:4px;">${currentDisplay}</div>
      </div>

      <div style="background:rgba(254,208,1,0.08);border:1px solid rgba(254,208,1,0.3);border-radius:12px;padding:20px;margin-bottom:20px;">
        <div style="font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:0.05em;color:#8a6d00;margin-bottom:8px;">G&uuml;nstigste Alternative</div>
        <div style="font-size:18px;font-weight:700;color:#1c1917;">${cheapest.insurer_name}</div>
        <div style="font-size:13px;color:#78716c;">${modelNames[cheapest.model_type] || cheapest.model_type} &middot; ${cheapest.tariff_name}</div>
        <div style="font-size:24px;font-weight:800;color:#1c1917;margin-top:4px;">CHF ${cheapest.premium.toFixed(2)}/Mt.</div>
      </div>

      ${yearlyDiff > 0 ? `<div style="text-align:center;background:#ecfdf5;border-radius:12px;padding:16px;margin-bottom:24px;">
        <div style="font-size:14px;color:#065f46;font-weight:700;">Du sparst bis zu CHF ${yearlyDiff.toFixed(0)} pro Jahr</div>
      </div>` : ''}

      <div style="text-align:center;">
        <a href="${link}" style="display:inline-block;background:#fed001;color:#1c1917;padding:14px 32px;border-radius:10px;font-weight:700;font-size:15px;text-decoration:none;">Jetzt zur ${cheapest.insurer_name} wechseln &#8594;</a>
      </div>

      <p style="font-size:13px;color:#78716c;text-align:center;margin-top:20px;line-height:1.6;">Die Grundversicherung ist bei allen Kassen <strong style="color:#1c1917;">gesetzlich identisch</strong>. Du zahlst nur f&uuml;r den Namen.</p>
    </div>

    <div style="text-align:center;margin-top:24px;">
      <p style="font-size:12px;color:#a8a29e;line-height:1.6;">Du bekommst diese Mail, weil du den Wechsel-Wecker auf abovergleich.com aktiviert hast.<br>
      <a href="https://abovergleich.com/#profil" style="color:#a8a29e;">Wecker deaktivieren</a></p>
    </div>
  </div>
</body>
</html>`;
}

async function sendEmail(to: string, subject: string, html: string): Promise<boolean> {
  const SENDGRID_API_KEY = Deno.env.get('SENDGRID_API_KEY');
  if (!SENDGRID_API_KEY) {
    console.error('SENDGRID_API_KEY not set');
    return false;
  }

  try {
    const res = await fetch('https://api.sendgrid.com/v3/mail/send', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${SENDGRID_API_KEY}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        personalizations: [{ to: [{ email: to }] }],
        from: { email: 'wecker@abovergleich.com', name: 'abovergleich.com' },
        subject,
        content: [{ type: 'text/html', value: html }],
      }),
    });
    return res.status >= 200 && res.status < 300;
  } catch (err) {
    console.error(`SendGrid error for ${to}:`, err);
    return false;
  }
}

Deno.serve(async (req: Request) => {
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders });
  }

  try {
    // Auth: require a secret trigger key
    const authHeader = req.headers.get('authorization');
    const triggerKey = Deno.env.get('WECKER_TRIGGER_KEY');

    if (triggerKey && authHeader !== `Bearer ${triggerKey}`) {
      return new Response(
        JSON.stringify({ error: 'Unauthorized' }),
        { status: 401, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }

    // Parse optional parameters
    let targetYear = new Date().getFullYear() + 1;
    let dryRun = false;
    let limitUsers = 0;

    if (req.method === 'POST') {
      try {
        const body = await req.json();
        if (body.year) targetYear = body.year;
        if (body.dry_run) dryRun = body.dry_run;
        if (body.limit) limitUsers = body.limit;
      } catch { /* no body is fine */ }
    }

    const supabase = createClient(
      Deno.env.get('SUPABASE_URL')!,
      Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!
    );

    // `premiums` enthält mehrere Jahre. Ohne Prämien für das Zieljahr würden
    // die Abfragen unten leer bleiben, also lieber gleich abbrechen.
    const { count: yearRows } = await supabase
      .from('premiums').select('id', { count: 'exact', head: true }).eq('year', targetYear);
    if (!yearRows) {
      return new Response(
        JSON.stringify({ error: `Keine Prämien für ${targetYear} in der Datenbank` }),
        { status: 409, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }

    // 1. Get all active wecker users not yet notified for target year
    let query = supabase
      .from('user_profiles')
      .select('*')
      .eq('wecker_active', true)
      .not('plz', 'is', null)
      .not('jahrgang', 'is', null)
      .not('franchise', 'is', null)
      .or(`last_notified_year.is.null,last_notified_year.lt.${targetYear}`);

    if (limitUsers > 0) {
      query = query.limit(limitUsers);
    }

    const { data: users, error: usersError } = await query;

    if (usersError) {
      return new Response(
        JSON.stringify({ error: 'Failed to fetch users', details: usersError.message }),
        { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }

    if (!users || users.length === 0) {
      return new Response(
        JSON.stringify({ message: 'No users to notify', target_year: targetYear }),
        { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }

    const results: { email: string; status: string; savings?: number }[] = [];

    for (const user of users as UserProfile[]) {
      try {
        // 2. Look up PLZ region
        const { data: plzData } = await supabase
          .from('plz_regions')
          .select('canton, region, locality')
          .eq('plz', parseInt(user.plz))
          .limit(1);

        if (!plzData || plzData.length === 0) {
          results.push({ email: user.email, status: 'skipped: invalid PLZ' });
          continue;
        }

        const { canton, region } = plzData[0];
        const premiumRegion = `PR-REG CH${region}`;

        // 3. Age class
        const age = targetYear - user.jahrgang;
        let ageClass: string;
        if (age <= 18) ageClass = 'AKL-KIN';
        else if (age <= 25) ageClass = 'AKL-JUG';
        else ageClass = 'AKL-ERW';

        // 4. Get user's current insurer premium
        let currentPremium: Premium | null = null;
        if (user.current_insurer_id) {
          const { data: currentData } = await supabase
            .from('premiums')
            .select('insurer_name, premium, model_type, tariff_name')
            .eq('year', targetYear)
            .eq('canton', canton)
            .eq('region', premiumRegion)
            .eq('age_class', ageClass)
            .eq('franchise', user.franchise)
            .eq('accident_included', true)
            .eq('insurer_id', user.current_insurer_id)
            .order('premium', { ascending: true })
            .limit(1);

          if (currentData && currentData.length > 0) {
            currentPremium = currentData[0];
          }
        }

        // 5. Get cheapest premium across all models
        const { data: cheapestData } = await supabase
          .from('premiums')
          .select('insurer_name, premium, model_type, tariff_name')
          .eq('year', targetYear)
          .eq('canton', canton)
          .eq('region', premiumRegion)
          .eq('age_class', ageClass)
          .eq('franchise', user.franchise)
          .eq('accident_included', true)
          .order('premium', { ascending: true })
          .limit(1);

        if (!cheapestData || cheapestData.length === 0) {
          results.push({ email: user.email, status: 'skipped: no premiums found' });
          continue;
        }

        const cheapest = cheapestData[0];

        // 6. Calculate savings
        const yearlyDiff = currentPremium
          ? (currentPremium.premium - cheapest.premium) * 12
          : 0;

        // Skip if already optimal (less than CHF 5/month difference)
        if (currentPremium && (currentPremium.premium - cheapest.premium) < 5) {
          results.push({ email: user.email, status: 'skipped: already optimal', savings: 0 });
          if (!dryRun) {
            await supabase
              .from('user_profiles')
              .update({ last_notified_year: targetYear })
              .eq('id', user.id);
          }
          continue;
        }

        // 7. Build and send email
        const subject = yearlyDiff > 0
          ? `Du kannst CHF ${yearlyDiff.toFixed(0)} pro Jahr sparen. Neue Prämien ${targetYear}`
          : `Neue Krankenkassenprämien ${targetYear}. Dein Vergleich`;

        const html = buildEmail(user, currentPremium, cheapest, yearlyDiff);

        if (dryRun) {
          results.push({ email: user.email, status: 'dry_run: would send', savings: yearlyDiff });
        } else {
          const sent = await sendEmail(user.email, subject, html);
          if (sent) {
            await supabase
              .from('user_profiles')
              .update({ last_notified_year: targetYear })
              .eq('id', user.id);
            results.push({ email: user.email, status: 'sent', savings: yearlyDiff });
          } else {
            results.push({ email: user.email, status: 'failed: email send error' });
          }
        }

      } catch (err) {
        results.push({ email: user.email, status: `error: ${err.message}` });
      }
    }

    const summary = {
      target_year: targetYear,
      dry_run: dryRun,
      total_users: users.length,
      sent: results.filter(r => r.status === 'sent').length,
      skipped: results.filter(r => r.status.startsWith('skipped')).length,
      failed: results.filter(r => r.status.startsWith('failed') || r.status.startsWith('error')).length,
      results,
    };

    return new Response(
      JSON.stringify(summary),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );

  } catch (err) {
    return new Response(
      JSON.stringify({ error: err.message }),
      { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  }
});
