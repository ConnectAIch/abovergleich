import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import { PDFDocument, StandardFonts, rgb } from "https://esm.sh/pdf-lib@1.17.1";
import { encode as base64Encode } from "https://deno.land/std@0.208.0/encoding/base64.ts";

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
};

interface InsurerAddress {
  name: string;
  street: string;
  plz_city: string;
}

// Adressen laut BAG-Verzeichnis der zugelassenen Krankenversicherer (Stand
// 1.10.2026, scripts/kv_verzeichnis.py). Schlüssel = Auswahl im Dialog auf
// index.html (captureInsurers). Groupe Mutuel: gemeinsame Adresse von Avenir,
// Mutuel und Philos.
const insurerAddresses: Record<string, InsurerAddress> = {
  'Aquilana': { name: 'Aquilana Versicherungen', street: 'Bruggerstrasse 46', plz_city: '5401 Baden' },
  'Assura': { name: 'Assura-Basis SA', street: 'Avenue C.-F. Ramuz 70', plz_city: '1009 Pully' },
  'Atupri': { name: 'Atupri Gesundheitsversicherung AG', street: 'Laupenstrasse 18', plz_city: '3008 Bern' },
  'Concordia': { name: 'CONCORDIA Schweiz. Kranken- und Unfallversicherung AG', street: 'Bundesplatz 15', plz_city: '6002 Luzern' },
  'CSS': { name: 'CSS Kranken-Versicherung AG', street: 'Tribschenstrasse 21, Postfach 2568', plz_city: '6002 Luzern' },
  'EGK': { name: 'EGK Grundversicherungen AG', street: 'Birspark 1', plz_city: '4242 Laufen' },
  'Galenos': { name: 'Galenos AG', street: 'Binzmühlestrasse 95', plz_city: '8050 Zürich' },
  'Groupe Mutuel': { name: 'Groupe Mutuel', street: 'Rue des Cèdres 5', plz_city: '1919 Martigny' },
  'Helsana': { name: 'Helsana Versicherungen AG', street: 'Postfach', plz_city: '8081 Zürich' },
  'KPT': { name: 'KPT Krankenkasse AG', street: 'Wankdorfallee 3, Postfach', plz_city: '3001 Bern' },
  'ÖKK': { name: 'ÖKK Kranken- und Unfallversicherungen AG', street: 'Bahnhofstrasse 13', plz_city: '7302 Landquart' },
  'Rhenusana': { name: 'rhenusana', street: 'Widnauerstrasse 6', plz_city: '9435 Heerbrugg' },
  'Sanitas': { name: 'Sanitas Grundversicherungen AG', street: 'Jägergasse 3, Postfach 2010', plz_city: '8021 Zürich' },
  'Swica': { name: 'SWICA Krankenversicherung AG', street: 'Römerstrasse 37', plz_city: '8401 Winterthur' },
  'Sympany': { name: 'Vivao Sympany AG', street: 'Peter Merian-Weg 4', plz_city: '4002 Basel' },
  'Visana': { name: 'Visana AG', street: 'Weltpoststrasse 19, Postfach', plz_city: '3000 Bern 16' },
  // ältere Schlüssel, falls ein gecachter Seitenstand sie noch schickt
  'Vivao': { name: 'Vivao Sympany AG', street: 'Peter Merian-Weg 4', plz_city: '4002 Basel' },
  'Mutuel': { name: 'Groupe Mutuel', street: 'Rue des Cèdres 5', plz_city: '1919 Martigny' },
};

const insurerUrls: Record<string, string> = {
  'Aquilana': 'https://www.aquilana.ch',
  'Assura': 'https://www.assura.ch',
  'Atupri': 'https://www.atupri.ch',
  'Concordia': 'https://www.concordia.ch',
  'CSS': 'https://www.css.ch',
  'EGK': 'https://www.egk.ch',
  'Galenos': 'https://www.galenos.ch',
  'Groupe Mutuel': 'https://www.groupemutuel.ch',
  'Helsana': 'https://www.helsana.ch',
  'KPT': 'https://www.kpt.ch',
  'Mutuel': 'https://www.groupemutuel.ch',
  'ÖKK': 'https://www.oekk.ch',
  'Rhenusana': 'https://www.rhenusana.ch',
  'Sanitas': 'https://www.sanitas.com',
  'Swica': 'https://www.swica.ch',
  'Sympany': 'https://www.sympany.ch',
  'Visana': 'https://www.visana.ch',
  'Vivao': 'https://www.sympany.ch',
};

async function generatePDF(
  senderName: string,
  senderStreet: string,
  senderPlzCity: string,
  insurerKey: string,
  targetYear: number
): Promise<Uint8Array> {
  const pdfDoc = await PDFDocument.create();
  const page = pdfDoc.addPage([595.28, 841.89]);
  const font = await pdfDoc.embedFont(StandardFonts.Helvetica);
  const fontBold = await pdfDoc.embedFont(StandardFonts.HelveticaBold);
  const fontSize = 11;
  const lineHeight = 16;
  const black = rgb(0, 0, 0);
  const gray = rgb(0.4, 0.4, 0.4);
  let y = 780;
  const leftMargin = 70;

  const insurer = insurerAddresses[insurerKey];
  if (!insurer) throw new Error('Unknown insurer: ' + insurerKey);

  const drawRight = (text: string, yPos: number, f = font, size = 9) => {
    const w = f.widthOfTextAtSize(text, size);
    page.drawText(text, { x: 595.28 - 70 - w, y: yPos, size, font: f, color: gray });
  };
  drawRight(senderName, y);
  drawRight(senderStreet, y - 13);
  drawRight(senderPlzCity, y - 26);

  y = 700;
  page.drawText(insurer.name, { x: leftMargin, y, size: fontSize, font: fontBold, color: black });
  y -= lineHeight;
  page.drawText(insurer.street, { x: leftMargin, y, size: fontSize, font, color: black });
  y -= lineHeight;
  page.drawText(insurer.plz_city, { x: leftMargin, y, size: fontSize, font, color: black });

  y -= 50;
  const now = new Date();
  const months = ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'];
  const cityPart = senderPlzCity.replace(/^\d+\s*/, '');
  const dateStr = cityPart + ', ' + now.getDate() + '. ' + months[now.getMonth()] + ' ' + now.getFullYear();
  page.drawText(dateStr, { x: leftMargin, y, size: fontSize, font, color: black });

  y -= 45;
  page.drawText('Kündigung der obligatorischen Krankenpflegeversicherung (OKP)', {
    x: leftMargin, y, size: 13, font: fontBold, color: black
  });
  y -= 20;
  page.drawText('per 31. Dezember ' + targetYear, {
    x: leftMargin, y, size: 12, font: fontBold, color: black
  });

  y -= 40;
  const bodyLines = [
    'Sehr geehrte Damen und Herren,',
    '',
    'hiermit kündige ich meine obligatorische Krankenpflegeversicherung (Grundversicherung',
    'nach KVG) fristgerecht per 31. Dezember ' + targetYear + '.',
    '',
    'Bitte senden Sie mir eine schriftliche Bestätigung der Kündigung an meine',
    'oben angegebene Adresse.',
    '',
    'Versicherungsnehmer/in: ' + senderName,
    'Adresse: ' + senderStreet + ', ' + senderPlzCity,
    '',
    'Ich danke Ihnen für die Bearbeitung und verbleibe',
    '',
    'mit freundlichen Grüssen,',
  ];

  for (const line of bodyLines) {
    page.drawText(line, { x: leftMargin, y, size: fontSize, font, color: black });
    y -= lineHeight;
  }

  y -= 30;
  page.drawText('____________________________', { x: leftMargin, y, size: fontSize, font, color: gray });
  y -= lineHeight;
  page.drawText(senderName, { x: leftMargin, y, size: 10, font, color: gray });

  y -= 50;
  page.drawText('Tipp: Senden Sie dieses Schreiben per Einschreiben, um einen Zustellnachweis zu haben.', {
    x: leftMargin, y, size: 9, font, color: gray
  });
  y -= 14;
  page.drawText('Erstellt auf abovergleich.com am ' + now.getDate() + '.' + (now.getMonth() + 1) + '.' + now.getFullYear(), {
    x: leftMargin, y, size: 8, font, color: rgb(0.6, 0.6, 0.6)
  });

  return await pdfDoc.save();
}

async function sendEmailWithPDF(
  to: string,
  senderName: string,
  insurerName: string,
  targetInsurerName: string,
  pdfBytes: Uint8Array,
  affiliateLink: string
): Promise<{ ok: boolean; error?: string }> {
  const SENDGRID_API_KEY = Deno.env.get('SENDGRID_API_KEY');
  if (!SENDGRID_API_KEY) {
    return { ok: false, error: 'SENDGRID_API_KEY not set' };
  }

  const pdfBase64 = base64Encode(pdfBytes);

  const html = `<!DOCTYPE html><html lang="de"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head><body style="margin:0;padding:0;background:#fafaf9;font-family:-apple-system,BlinkMacSystemFont,sans-serif;"><div style="max-width:560px;margin:0 auto;padding:40px 20px;"><div style="text-align:center;margin-bottom:32px;"><span style="font-weight:800;font-size:20px;color:#1c1917;">abo<span style="color:#a68600;">vergleich</span>.com</span></div><div style="background:#ffffff;border-radius:16px;padding:32px;border:1px solid rgba(0,0,0,0.06);"><div style="text-align:center;font-size:40px;margin-bottom:16px;">&#9989;</div><h1 style="font-size:22px;font-weight:800;color:#1c1917;text-align:center;margin:0 0 8px;">Dein K&uuml;ndigungsschreiben ist bereit!</h1><p style="font-size:15px;color:#78716c;text-align:center;line-height:1.6;margin:0 0 28px;">Hallo ${senderName}, im Anhang findest du dein fertiges K&uuml;ndigungsschreiben f&uuml;r die ${insurerName}.</p><div style="background:#f5f5f4;border-radius:12px;padding:20px;margin-bottom:20px;"><div style="font-size:14px;font-weight:700;color:#1c1917;margin-bottom:12px;">N&auml;chste Schritte:</div><div style="font-size:14px;color:#78716c;line-height:1.8;">1. PDF-Anhang ausdrucken<br>2. Unterschreiben<br>3. Per <strong style="color:#1c1917;">Einschreiben</strong> an die ${insurerName} senden<br>4. Bei der neuen Kasse anmelden</div></div><div style="text-align:center;margin-top:24px;"><a href="${affiliateLink}" style="display:inline-block;background:#fed001;color:#1c1917;padding:14px 32px;border-radius:10px;font-weight:700;font-size:15px;text-decoration:none;">Jetzt bei ${targetInsurerName} anmelden</a></div><p style="font-size:13px;color:#78716c;text-align:center;margin-top:20px;line-height:1.6;"><strong style="color:#1c1917;">Wichtig:</strong> Die K&uuml;ndigung muss bis sp&auml;testens 30. November bei deiner alten Kasse eingehen.</p></div><div style="text-align:center;margin-top:24px;"><p style="font-size:12px;color:#a8a29e;line-height:1.6;">Erstellt mit abovergleich.com</p></div></div></body></html>`;

  try {
    const res = await fetch('https://api.sendgrid.com/v3/mail/send', {
      method: 'POST',
      headers: {
        'Authorization': 'Bearer ' + SENDGRID_API_KEY,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        personalizations: [{ to: [{ email: to }] }],
        from: { email: 'hello@handyabo.com', name: 'abovergleich.com' },
        reply_to: { email: 'hello@handyabo.com', name: 'abovergleich.com' },
        subject: 'Dein Kündigungsschreiben für die ' + insurerName,
        content: [{ type: 'text/html', value: html }],
        attachments: [{
          content: pdfBase64,
          filename: 'Kuendigung_' + insurerName.replace(/[^a-zA-Z0-9]/g, '_') + '.pdf',
          type: 'application/pdf',
          disposition: 'attachment'
        }]
      }),
    });

    if (res.status >= 200 && res.status < 300) {
      return { ok: true };
    } else {
      const errBody = await res.text();
      console.error('SendGrid response:', res.status, errBody);
      return { ok: false, error: 'SendGrid ' + res.status + ': ' + errBody };
    }
  } catch (err) {
    console.error('SendGrid fetch error:', err);
    return { ok: false, error: err.message };
  }
}

Deno.serve(async (req: Request) => {
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders });
  }

  try {
    const body = await req.json();
    const { email, name, street, plz_city, current_insurer, target_insurer_name, wecker_active } = body;

    if (!email || !name || !street || !plz_city || !current_insurer) {
      return new Response(
        JSON.stringify({ error: 'Fehlende Felder. Bitte alle Felder ausfüllen.' }),
        { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }

    const targetYear = new Date().getFullYear();

    const pdfBytes = await generatePDF(name, street, plz_city, current_insurer, targetYear);

    const targetUrl = insurerUrls[target_insurer_name] || 'https://abovergleich.com';
    const affLink = targetUrl + '?utm_source=abovergleich.com&utm_medium=affiliate&utm_campaign=kuendigung';

    const insurerAddr = insurerAddresses[current_insurer];
    const result = await sendEmailWithPDF(
      email,
      name,
      insurerAddr?.name || current_insurer,
      target_insurer_name || 'der neuen Kasse',
      pdfBytes,
      affLink
    );

    const supabase = createClient(
      Deno.env.get('SUPABASE_URL')!,
      Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!
    );

    await supabase.from('kuendigung_leads').insert({
      email,
      name,
      street,
      plz_city,
      current_insurer,
      target_insurer: target_insurer_name,
      wecker_active: wecker_active !== false,
      created_at: new Date().toISOString()
    });

    if (!result.ok) {
      return new Response(
        JSON.stringify({ error: 'E-Mail Fehler: ' + (result.error || 'unbekannt'), lead_saved: true }),
        { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }

    return new Response(
      JSON.stringify({
        success: true,
        message: 'Kündigungsschreiben wurde per E-Mail gesendet.',
        affiliate_link: affLink
      }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );

  } catch (err) {
    return new Response(
      JSON.stringify({ error: err.message }),
      { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  }
});
