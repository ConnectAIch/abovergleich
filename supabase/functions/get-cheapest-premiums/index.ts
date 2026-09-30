import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

// Prämienjahr, das der Rechner zeigt. `premiums` enthält mehrere Jahre
// (Vorjahre bleiben für Vergleiche), deshalb wird jede Abfrage darauf gefiltert.
// Jährlich Ende September nach dem Import (scripts/import_premiums.py) anheben.
const PREMIUM_YEAR = 2027;
const PREV_YEAR = PREMIUM_YEAR - 1;

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
};

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { ...corsHeaders, 'Content-Type': 'application/json' } });

type Row = {
  insurer_id: number; insurer_name: string; premium: number;
  model_type: string; tariff: string; tariff_name: string;
};

// Einige Tarifcodes wurden zwischen den Jahren umbenannt, z.B. "Santé (HMO)"
// hiess vorher "HMO". Gleiche Logik wie scripts/build_kk_pages.py.
// Klein geschrieben, Swica schreibt denselben Tarif 2026 "CASA" und 2027 "Casa".
function tariffCandidates(tariff: string): string[] {
  const t = tariff.toLowerCase();
  const m = t.match(/^(.*?)\s*\((.*)\)\s*$/);
  return m ? [t, m[2], m[1]] : [t];
}

Deno.serve(async (req: Request) => {
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders });
  }

  try {
    const { plz, year_of_birth, franchise, accident_included } = await req.json();

    if (!plz || !year_of_birth || !franchise) {
      return json({ error: 'Missing required fields: plz, year_of_birth, franchise' }, 400);
    }

    const withAccident = accident_included !== undefined ? accident_included : true;

    const supabase = createClient(
      Deno.env.get('SUPABASE_URL')!,
      Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!
    );

    // 1. PLZ -> Kanton und Prämienregion
    const { data: plzData, error: plzError } = await supabase
      .from('plz_regions')
      .select('canton, region, locality')
      .eq('plz', parseInt(plz))
      .limit(1);

    if (plzError || !plzData || plzData.length === 0) {
      return json({ error: `PLZ ${plz} nicht gefunden` }, 404);
    }

    const { canton, region, locality } = plzData[0];
    const premiumRegion = `PR-REG CH${region}`;

    // 2. Altersklasse (massgebend ist das Alter im Prämienjahr)
    const age = PREMIUM_YEAR - parseInt(year_of_birth);
    let ageClass: string;
    if (age <= 18) ageClass = 'AKL-KIN';
    else if (age <= 25) ageClass = 'AKL-JUG';
    else ageClass = 'AKL-ERW';

    // 3. Alle Tarife für dieses Profil, dieses und letztes Jahr. Bei Kindern
    //    nur die Prämie fürs erste Kind (K1), sonst stehen Geschwisterrabatte
    //    als "günstigste Kasse" in der Liste.
    const fetchYear = (year: number) => {
      let q = supabase
        .from('premiums')
        .select('insurer_id, insurer_name, premium, model_type, tariff, tariff_name')
        .eq('year', year)
        .eq('canton', canton)
        .eq('region', premiumRegion)
        .eq('age_class', ageClass)
        .eq('franchise', parseInt(franchise))
        .eq('accident_included', withAccident)
        .order('premium', { ascending: true })
        .limit(1000);
      if (ageClass === 'AKL-KIN') q = q.eq('age_subgroup', 'K1');
      return q;
    };

    const [{ data: cur, error: curError }, { data: prev }] = await Promise.all([
      fetchYear(PREMIUM_YEAR), fetchYear(PREV_YEAR),
    ]);

    if (curError) {
      return json({ error: curError.message }, 500);
    }

    const prevByTariff = new Map<string, number>();
    for (const p of (prev || []) as Row[]) prevByTariff.set(`${p.insurer_id}|${p.tariff.toLowerCase()}`, Number(p.premium));

    const offers = ((cur || []) as Row[]).map(p => {
      let before: number | null = null;
      for (const t of tariffCandidates(p.tariff)) {
        const hit = prevByTariff.get(`${p.insurer_id}|${t}`);
        if (hit !== undefined) { before = hit; break; }
      }
      return { ...p, premium: Number(p.premium), premium_prev: before };
    });

    // Kompatibel zur bisherigen Antwort (älterer Frontend-Stand im Cache)
    const seen = new Set<string>();
    const standard_model = offers.filter(p => p.model_type === 'standard')
      .filter(p => !seen.has(p.insurer_name) && seen.add(p.insurer_name)).slice(0, 10);
    const seenAll = new Set<string>();
    const cheapest_any_model = offers
      .filter(p => { const k = p.insurer_name + '|' + p.model_type; return !seenAll.has(k) && seenAll.add(k); })
      .slice(0, 20);

    return json({
      year: PREMIUM_YEAR,
      prev_year: PREV_YEAR,
      plz: parseInt(plz),
      locality,
      canton,
      region: premiumRegion,
      age,
      age_class: ageClass === 'AKL-ERW' ? 'Erwachsene (26+)' : ageClass === 'AKL-JUG' ? 'Junge Erwachsene (19-25)' : 'Kinder (0-18)',
      franchise: parseInt(franchise),
      accident_included: withAccident,
      insurer_count: new Set(offers.map(p => p.insurer_id)).size,
      offers,
      standard_model,
      cheapest_any_model,
    });

  } catch (err) {
    return json({ error: err.message }, 500);
  }
});
