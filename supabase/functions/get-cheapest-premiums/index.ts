import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

// Prämienjahr, das der Rechner zeigt. `premiums` enthält mehrere Jahre
// (Vorjahre bleiben für Vergleiche), deshalb wird jede Abfrage darauf gefiltert.
// Jährlich Ende September nach dem Import (scripts/import_premiums.py) anheben.
const PREMIUM_YEAR = 2027;

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
};

Deno.serve(async (req: Request) => {
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders });
  }

  try {
    const { plz, year_of_birth, franchise, accident_included } = await req.json();

    if (!plz || !year_of_birth || !franchise) {
      return new Response(
        JSON.stringify({ error: 'Missing required fields: plz, year_of_birth, franchise' }),
        { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }

    const withAccident = accident_included !== undefined ? accident_included : true;

    const supabase = createClient(
      Deno.env.get('SUPABASE_URL')!,
      Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!
    );

    // 1. Look up PLZ to get canton and region
    const { data: plzData, error: plzError } = await supabase
      .from('plz_regions')
      .select('canton, region, locality')
      .eq('plz', parseInt(plz))
      .limit(1);

    if (plzError || !plzData || plzData.length === 0) {
      return new Response(
        JSON.stringify({ error: `PLZ ${plz} nicht gefunden` }),
        { status: 404, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }

    const { canton, region, locality } = plzData[0];
    const premiumRegion = `PR-REG CH${region}`;

    // 2. Determine age class (massgebend ist das Alter im Prämienjahr)
    const age = PREMIUM_YEAR - parseInt(year_of_birth);
    let ageClass: string;
    if (age <= 18) ageClass = 'AKL-KIN';
    else if (age <= 25) ageClass = 'AKL-JUG';
    else ageClass = 'AKL-ERW';

    // 3. Query cheapest standard model premiums
    const { data: premiums, error: premError } = await supabase
      .from('premiums')
      .select('insurer_name, premium, model_type, tariff_name')
      .eq('year', PREMIUM_YEAR)
      .eq('canton', canton)
      .eq('region', premiumRegion)
      .eq('age_class', ageClass)
      .eq('franchise', parseInt(franchise))
      .eq('accident_included', withAccident)
      .eq('model_type', 'standard')
      .order('premium', { ascending: true })
      .limit(20);

    if (premError) {
      return new Response(
        JSON.stringify({ error: premError.message }),
        { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }

    // 4. Get cheapest across ALL models (enough for filtering)
    const { data: allModels } = await supabase
      .from('premiums')
      .select('insurer_name, premium, model_type, tariff_name')
      .eq('year', PREMIUM_YEAR)
      .eq('canton', canton)
      .eq('region', premiumRegion)
      .eq('age_class', ageClass)
      .eq('franchise', parseInt(franchise))
      .eq('accident_included', withAccident)
      .order('premium', { ascending: true })
      .limit(50);

    // Deduplicate by insurer+model (keep cheapest per insurer per model)
    const seen = new Set<string>();
    const uniquePremiums = (premiums || []).filter(p => {
      if (seen.has(p.insurer_name)) return false;
      seen.add(p.insurer_name);
      return true;
    });

    const seenAll = new Set<string>();
    const uniqueAll = (allModels || []).filter(p => {
      const key = p.insurer_name + '|' + p.model_type;
      if (seenAll.has(key)) return false;
      seenAll.add(key);
      return true;
    });

    const result = {
      year: PREMIUM_YEAR,
      plz: parseInt(plz),
      locality,
      canton,
      region: premiumRegion,
      age,
      age_class: ageClass === 'AKL-ERW' ? 'Erwachsene (26+)' : ageClass === 'AKL-JUG' ? 'Junge Erwachsene (19-25)' : 'Kinder (0-18)',
      franchise: parseInt(franchise),
      accident_included: withAccident,
      standard_model: uniquePremiums.slice(0, 10),
      cheapest_any_model: uniqueAll.slice(0, 20),
    };

    return new Response(
      JSON.stringify(result),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );

  } catch (err) {
    return new Response(
      JSON.stringify({ error: err.message }),
      { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  }
});
