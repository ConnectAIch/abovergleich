// Kündigungsbrief für die Grundversicherung: Formular, Unterschrift, PDF und
// der passende Weg zur Kasse. Der Brief entsteht im Browser. Auf Wunsch
// schicken wir das PDF an die Person selbst (Edge Function kuendigung-pdf,
// schaltet den Wechsel-Wecker ein), nie an die Kasse.
//
// Abschicken muss der Kunde selbst. Groupe Mutuel und Sympany nehmen eine
// Kündigung per Mail nur vom Absender an, den sie vom Kunden kennen, und bei
// den anderen ist eine fremde Absenderadresse mindestens ein Grund für
// Rückfragen. Deshalb liefert die Seite das PDF (als Anhang an die Person
// selbst) und einen fertigen Mailentwurf (mailto mit Empfänger, Betreff und
// Text), aber keinen Versand an die Kasse.
//
// Die Daten kommen vom Generator (scripts/build_kk_pages.py) im Block
// #kd-data: Adressen aus dem BAG-Verzeichnis, Kündigungswege aus
// scripts/data/kuendigung_kanaele.json.
//
// Sprachen: die Oberfläche folgt der Seite (de, fr, en, aus #kd-data). Der
// Brief selbst geht an eine Schweizer Kasse und ist deutsch oder französisch,
// wählbar im Feld «Sprache des Briefs».
(function () {
  var D = JSON.parse(document.getElementById('kd-data').textContent);
  var KASSEN = D.kassen, END = D.end, DEADLINE = new Date(D.deadline + 'T23:59:59');
  var UI = D.lang || 'de';
  var T = {
    choose: { de: 'Bitte wählen', fr: 'Veuillez choisir', en: 'Please choose' },
    search: { de: 'Kasse suchen…', fr: 'Chercher une caisse…', en: 'Search insurer…' },
    st_1: { de: '{k} kündigen', fr: 'Résilier {k}', en: 'Cancel {k}' },
    st_1_any: { de: 'Bisherige Kasse kündigen', fr: 'Résilier la caisse actuelle', en: 'Cancel current insurer' },
    st_2: { de: 'Bei {n} anmelden', fr: 'S’inscrire chez {n}', en: 'Sign up with {n}' },
    last: { de: 'Heute ist der letzte Tag.', fr: 'C’est le dernier jour.', en: 'Today is the last day.' },
    left: { de: 'Noch {n} Tage.', fr: 'Encore {n} jours.', en: '{n} days left.' },
    pad_ok: { de: 'Sieht gut aus?', fr: 'Ça vous convient ?', en: 'Looks good?' },
    pad_go: { de: 'Mit Maus, Finger oder Stift unterschreiben.', fr: 'Signez avec la souris, le doigt ou un stylet.', en: 'Sign with your mouse, finger or stylus.' },
    sig_alt: { de: 'Unterschrift', fr: 'Signature', en: 'Signature' },
    src: { de: 'Laut <a href="{u}" target="_blank" rel="noopener">Website der Kasse</a>, Stand {d}.', fr: 'Selon le <a href="{u}" target="_blank" rel="noopener">site de la caisse</a>, état au {d}.', en: 'According to the <a href="{u}" target="_blank" rel="noopener">insurer’s website</a>, as of {d}.' },
    k_mail: { de: '<strong>{n} nimmt die Kündigung per Mail an.</strong> Du bekommst sie fertig per Mail und leitest sie an {m} weiter',
              fr: '<strong>{n} accepte la résiliation par e-mail.</strong> Vous la recevez prête par e-mail et la transférez à {m}',
              en: '<strong>{n} accepts cancellation by email.</strong> You get it ready-made by email and forward it to {m}' },
    k_own: { de: ', <strong>nur von der Mail-Adresse, die {n} von dir kennt</strong>.', fr: ', <strong>uniquement depuis l’adresse e-mail que {n} connaît</strong>.', en: ', <strong>only from the email address {n} has on file for you</strong>.' },
    k_any: { de: '.', fr: '.', en: '.' },
    k_portal: { de: '<strong>{n} nimmt die Kündigung im Kundenportal {p} an</strong> (PDF hochladen) oder per Post.',
                fr: '<strong>{n} accepte la résiliation dans l’espace client {p}</strong> (téléverser le PDF) ou par la poste.',
                en: '<strong>{n} accepts cancellation in the customer portal {p}</strong> (upload the PDF) or by post.' },
    k_reg: { de: '<strong>{n} verlangt einen eingeschriebenen Brief.</strong> Ausdrucken und spätestens eine Woche vor dem {d} zur Post.',
             fr: '<strong>{n} exige une lettre recommandée.</strong> Imprimez-la et postez-la au plus tard une semaine avant le {d}.',
             en: '<strong>{n} requires a registered letter.</strong> Print it and post it at least one week before {d}.' },
    k_post: { de: '<strong>{n} nennt keinen Mail-Weg, also per Post</strong> an die Adresse im Brief, spätestens eine Woche vor dem {d}. Einschreiben empfohlen.',
              fr: '<strong>{n} n’indique pas de voie par e-mail, donc par la poste</strong> à l’adresse de la lettre, au plus tard une semaine avant le {d}. Recommandé conseillé.',
              en: '<strong>{n} gives no email route, so by post</strong> to the address in the letter, at least one week before {d}. Registered mail recommended.' },
    wait: { de: 'Einen Moment…', fr: 'Un instant…', en: 'One moment…' },
    fail: { de: 'Das hat nicht geklappt. Versuch es nochmals oder nimm «Text kopieren».', fr: 'Cela n’a pas fonctionné. Réessayez ou utilisez « Copier le texte ».', en: 'That didn’t work. Try again or use “Copy text”.' },
    again: { de: 'Nochmals senden', fr: 'Renvoyer', en: 'Send again' },
    f_name: { de: 'Name', fr: 'Nom', en: 'Name' }, f_birth: { de: 'Geburtsdatum', fr: 'Date de naissance', en: 'Date of birth' },
    f_street: { de: 'Strasse', fr: 'Rue', en: 'Street' }, f_plz: { de: 'PLZ', fr: 'NPA', en: 'Postcode' },
    f_ort: { de: 'Ort', fr: 'Localité', en: 'Town' }, f_email: { de: 'E-Mail', fr: 'E-mail', en: 'Email' },
    no_sig: { de: 'Bitte noch unterschreiben. Ohne Unterschrift kann die Kasse die Kündigung zurückweisen, und dann ist die Frist vielleicht schon vorbei.',
              fr: 'Veuillez encore signer. Sans signature, la caisse peut refuser la résiliation, et le délai sera peut-être déjà passé.',
              en: 'Please sign first. Without a signature the insurer can reject the cancellation, and by then the deadline may have passed.' },
    closed_left: { de: 'Die Frist ist vorbei.', fr: 'Le délai est passé.', en: 'The deadline has passed.' },
    no_kasse: { de: 'Bitte zuerst deine Kasse wählen.', fr: 'Veuillez d’abord choisir votre caisse.', en: 'Please choose your insurer first.' },
    missing: { de: 'Bitte noch ausfüllen: {f}.', fr: 'Veuillez encore remplir : {f}.', en: 'Please still fill in: {f}.' },
    sent_txt: { de: 'Mail ist unterwegs an {m}. Klick dort auf «Kündigung herunterladen», damit bestätigst du auch deine Adresse. Nichts da? Schau im Spam-Ordner.',
                fr: 'L’e-mail est en route vers {m}. Cliquez sur « Télécharger la résiliation » : cela confirme aussi votre adresse. Rien reçu ? Regardez dans les spams.',
                en: 'The email is on its way to {m}. Click “Download your cancellation” in it; that also confirms your address. Nothing there? Check your spam folder.' },
    done_t: { de: 'Brief fertig', fr: 'Lettre prête', en: 'Letter ready' },
    done_1_mail: { de: 'Zwei Mails sind unterwegs an <b>{m}</b>: die Kündigung zum Weiterleiten und die nächsten Schritte.', fr: 'Deux e-mails sont en route vers <b>{m}</b> : la résiliation à transférer et les prochaines étapes.', en: 'Two emails are on their way to <b>{m}</b>: the cancellation to forward and the next steps.' },
    done_1: { de: 'Das PDF ist unterwegs an <b>{m}</b>, als Anhang.', fr: 'Le PDF est en route vers <b>{m}</b>, en pièce jointe.', en: 'The PDF is on its way to <b>{m}</b>, as an attachment.' },
    done_2: { de: 'Nichts da? Spam-Ordner prüfen oder die Adresse oben.', fr: 'Rien reçu ? Vérifiez les spams ou l’adresse ci-dessus.', en: 'Nothing there? Check spam or the address above.' },
    nx_h: { de: 'Jetzt noch zwei Schritte', fr: 'Encore deux étapes', en: 'Two more steps' },
    nx_fwd: { de: 'Unsere Mail «{s}» weiterleiten an', fr: 'Transférer notre e-mail « {s} » à', en: 'Forward our email “{s}” to' },
    nx_fwd_sub: { de: 'Text und PDF sind schon drin. Weiterleiten, Adresse einsetzen, senden.', fr: 'Le texte et le PDF y sont déjà. Transférer, coller l’adresse, envoyer.', en: 'Text and PDF are already in it. Forward, paste the address, send.' },
    nx_copy: { de: 'Adresse kopieren', fr: 'Copier l’adresse', en: 'Copy address' },
    nx_alt: { de: 'Oder neue Mail mit Text öffnen und PDF selbst anhängen', fr: 'Ou ouvrir un nouvel e-mail avec le texte et joindre le PDF vous-même', en: 'Or open a new email with the text and attach the PDF yourself' },
    nx_dl: { de: 'PDF herunterladen', fr: 'Télécharger le PDF', en: 'Download PDF' },
    nx_mail: { de: 'Mail an {n} öffnen', fr: 'Ouvrir l’e-mail à {n}', en: 'Open email to {n}' },
    nx_mail_sub: { de: 'An {m}, Betreff und Text sind schon drin. Du hängst nur das PDF aus unserer Mail an.',
                   fr: 'À {m}, objet et texte sont déjà remplis. Il ne reste qu’à joindre le PDF de notre e-mail.',
                   en: 'To {m}, subject and text are already filled in. Just attach the PDF from our email.' },
    nx_own: { de: ' Wichtig: von der Adresse, die {n} von dir kennt.', fr: ' Important : depuis l’adresse que {n} connaît.', en: ' Important: from the address {n} has on file for you.' },
    nx_proof: { de: ' Die Eingangsbestätigung der Kasse aufheben.', fr: ' Conservez la confirmation de réception de la caisse.', en: ' Keep the insurer’s confirmation of receipt.' },
    nx_portal: { de: 'PDF in {p} hochladen oder per Post schicken, bis {d}.', fr: 'Téléverser le PDF dans {p} ou l’envoyer par la poste, d’ici au {d}.', en: 'Upload the PDF to {p} or send it by post, by {d}.' },
    nx_post: { de: 'PDF ausdrucken und per Post an {n}, spätestens eine Woche vor dem {d}.', fr: 'Imprimer le PDF et l’envoyer par la poste à {n}, au plus tard une semaine avant le {d}.', en: 'Print the PDF and post it to {n}, at least one week before {d}.' },
    nx_neu: { de: 'Bei {n} anmelden', fr: 'S’inscrire chez {n}', en: 'Sign up with {n}' },
    nx_neu_sub: { de: 'Online, etwa 10 Minuten, ohne Gesundheitsfragen. AHV-Nummer bereithalten, Beginn {d}.', fr: 'En ligne, environ 10 minutes, sans questions de santé. Numéro AVS sous la main, début le {d}.', en: 'Online, about 10 minutes, no health questions. Have your AHV number ready, start {d}.' },
    nx_neu_form: { de: '{n} hat keine Online-Anmeldung: Offerte anfordern oder Beitrittsformular ausfüllen. Beginn {d}.', fr: '{n} n’a pas d’inscription en ligne : demandez une offre ou remplissez le formulaire d’adhésion. Début le {d}.', en: '{n} has no online sign-up: request an offer or fill in the membership form. Start {d}.' },
    nx_find: { de: 'Günstigste Kasse finden', fr: 'Trouver la caisse la moins chère', en: 'Find the cheapest insurer' },
    nx_find_sub: { de: 'Dann dort anmelden, online in etwa 10 Minuten.', fr: 'Puis s’y inscrire, en ligne en 10 minutes environ.', en: 'Then sign up there, online in about 10 minutes.' },
    nx_conf: { de: 'Danach bestätigt die neue Kasse den Wechsel. Bis dahin bleibst du bei {k} versichert.', fr: 'Ensuite, la nouvelle caisse confirme le changement. D’ici là, vous restez assuré chez {k}.', en: 'The new insurer then confirms the switch. Until then you stay insured with {k}.' },
    send_fail: { de: 'Der Versand hat nicht geklappt. Bitte nochmals versuchen.', fr: 'L’envoi n’a pas fonctionné. Veuillez réessayer.', en: 'Sending didn’t work. Please try again.' },
    attach: { de: ' Das PDF hängst du dann an die Mail an die Kasse an.', fr: ' Joignez ensuite le PDF à l’e-mail destiné à la caisse.', en: ' Then attach the PDF to the email to your insurer.' },
    copied: { de: 'Kopiert', fr: 'Copié', en: 'Copied' },
    copy_manual: { de: 'Bitte markieren und kopieren', fr: 'Veuillez sélectionner et copier', en: 'Please select and copy' },
    copied_msg: { de: 'Text kopiert. ', fr: 'Texte copié. ', en: 'Text copied. ' },
  };
  function t(k, v) {
    var s = (T[k] || {})[UI] || (T[k] || {}).de || k;
    return s.replace(/\{(\w)\}/g, function (_, x) { return v && v[x] != null ? v[x] : ''; });
  }
  // Texte des Briefs, deutsch oder französisch
  var MONTHS = { de: ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'],
                 fr: ['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre'] };
  function longDate(d, lang) { return (lang === 'fr' ? (d.getDate() === 1 ? '1er' : d.getDate()) : d.getDate() + '.') + ' ' + MONTHS[lang][d.getMonth()] + ' ' + d.getFullYear(); }
  var B = {
    de: { name: 'Vorname Name', city: 'PLZ Ort', ort: 'Ort', street: 'Strasse Nr.', kasse: ['Name der Krankenkasse', 'Adresse'],
          subject: 'Kündigung der obligatorischen Krankenpflegeversicherung (Grundversicherung)', nr: 'Versicherten-Nr. ', birth: 'Geburtsdatum ',
          more: 'Hiermit kündige ich die obligatorische Krankenpflegeversicherung nach KVG für mich und die folgenden Personen',
          one: 'Hiermit kündige ich meine obligatorische Krankenpflegeversicherung nach KVG', on: ' fristgerecht auf den ',
          keep: 'Meine Zusatzversicherungen sind von dieser Kündigung nicht betroffen und laufen weiter.',
          confirm: 'Bitte bestätigen Sie mir den Eingang der Kündigung schriftlich.', hello: 'Sehr geehrte Damen und Herren', bye: 'Freundliche Grüsse',
          dateSep: ', ', footer: 'Erstellt mit abovergleich.com, dem unabhängigen Krankenkassen-Vergleich',
          m_body: 'Im Anhang sende ich Ihnen meine unterschriebene Kündigung der Grundversicherung auf den ', m_name: 'Name: ', m_nr: 'Versicherten-Nr.: ',
          m_confirm: 'Bitte bestätigen Sie mir den Eingang.', m_subject: 'Kündigung Grundversicherung, ', m_vnr: ', Vers.-Nr. ',
          file: 'Kuendigung-Grundversicherung-', fallbackKasse: 'Krankenkasse' },
    fr: { name: 'Prénom Nom', city: 'NPA Localité', ort: 'Localité', street: 'Rue et n°', kasse: ['Nom de la caisse-maladie', 'Adresse'],
          subject: 'Résiliation de l’assurance obligatoire des soins (assurance de base)', nr: 'N° d’assuré ', birth: 'Date de naissance ',
          more: 'Par la présente, je résilie dans les délais l’assurance obligatoire des soins selon la LAMal pour moi-même et pour les personnes suivantes',
          one: 'Par la présente, je résilie dans les délais mon assurance obligatoire des soins selon la LAMal', on: ' pour le ',
          keep: 'Mes assurances complémentaires ne sont pas concernées par cette résiliation et sont maintenues.',
          confirm: 'Je vous prie de bien vouloir me confirmer par écrit la réception de cette résiliation.', hello: 'Madame, Monsieur,',
          bye: 'Veuillez agréer, Madame, Monsieur, mes salutations distinguées.', dateSep: ', le ',
          footer: 'Créé avec abovergleich.com, le comparatif indépendant des caisses-maladie',
          m_body: 'Vous trouverez en pièce jointe ma résiliation signée de l’assurance de base pour le ', m_name: 'Nom : ', m_nr: 'N° d’assuré : ',
          m_confirm: 'Je vous prie de bien vouloir m’en confirmer la réception.', m_subject: 'Résiliation assurance de base, ', m_vnr: ', n° d’assuré ',
          file: 'Resiliation-assurance-de-base-', fallbackKasse: 'caisse-maladie' },
  };
  var lsel = document.getElementById('kd-lang'), langTouched = false;
  if (lsel) {
    lsel.value = UI === 'fr' ? 'fr' : 'de';
    lsel.addEventListener('change', function () { langTouched = true; });
  }
  function LL() { return lsel && lsel.value === 'fr' ? 'fr' : 'de'; }
  function b(k) { return B[LL()][k]; }
  function endText() { return D.end_iso ? longDate(new Date(D.end_iso + 'T12:00:00'), LL()) : END; }
  var JSPDF_SRC = 'https://cdnjs.cloudflare.com/ajax/libs/jspdf/4.2.1/jspdf.umd.min.js';
  var JSPDF_SRI = 'sha512-plOdviVmws4Y3JAvbnpfKb2hVxKM1lCwsi3vmElYRj+tiDLffZ4FVUj5a8vyKJ9pIgl8JCAHEJ4D1iUKBecswg==';
  var $ = function (id) { return document.getElementById(id); };
  var esc = function (s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); };

  // ── Kasse und Vorausfüllung ────────────────────────────────────────────
  var sel = $('kd-kasse');
  sel.add(new Option(t('choose'), ''));
  KASSEN.forEach(function (k) { sel.add(new Option(k.name, k.id)); });
  var q = new URLSearchParams(location.search).get('kasse');
  if (q) sel.value = q;
  // Aus dem Rechner (hochgeladene Rechnung), nur für dieses Browserfenster gespeichert
  try {
    var pf = JSON.parse(sessionStorage.getItem('kd-prefill') || 'null');
    if (pf) {
      if (!q && pf.kasse) sel.value = String(pf.kasse);
      ['name', 'street', 'nr'].forEach(function (k) { if (pf[k] && !$('kd-' + k).value) $('kd-' + k).value = pf[k]; });
      var pc = String(pf.city || '').match(/^(\d{4})\s+(.+)$/);
      if (pc && !$('kd-plz').value) { $('kd-plz').value = pc[1]; $('kd-ort').value = pc[2]; }
    }
  } catch (e) {}
  try {
    var pr0 = JSON.parse(localStorage.getItem('kk-profile') || 'null') || {};
    if (/^\d{4}$/.test(String(pr0.plz || '')) && !$('kd-plz').value) $('kd-plz').value = String(pr0.plz);
  } catch (e) {}
  if (window.Combobox) Combobox.enhance(sel, { search: true, placeholder: t('search') });

  // Aus dem Rechner mit «Wechseln»: zuerst bei der neuen Kasse anmelden, dann
  // die bisherige kündigen. Die Reihenfolge ist egal (die alte Versicherung
  // endet erst, wenn die neue sie bestätigt), aber so vergisst man keinen Teil.
  var neu = KASSEN.find(function (k) { return String(k.id) === new URLSearchParams(location.search).get('neu'); });
  if (neu && String(neu.id) === sel.value) neu = null;
  // UTM anhängen, auch wenn der Rechner-Link schon ? oder # enthält
  function utm(u) {
    var h = u.indexOf('#'), a = h < 0 ? u : u.slice(0, h), z = h < 0 ? '' : u.slice(h);
    return a + (a.indexOf('?') < 0 ? '?' : '&') + 'utm_source=abovergleich.com&utm_medium=affiliate&utm_campaign=kk-wechsel' + z;
  }
  var neuGo = neu && neu.url ? utm(neu.url) : null;
  // PLZ und Geburtsdatum aus dem Brief anhängen, wo der Rechner der Kasse sie
  // übernimmt (CSS, ÖKK; siehe signup_prefill). Nur dieser Link im Browser,
  // nicht an unsere Funktion und nicht in die Mail (Datenschutz 3.3).
  function neuLink() {
    if (!neuGo || !neu.prefill) return neuGo;
    var m = val('kd-birth').match(/^(\d{1,2})\.(\d{1,2})\.(\d{4})$/), q = [];
    if (neu.prefill.plz && /^\d{4}$/.test(val('kd-plz'))) q.push(neu.prefill.plz + '=' + val('kd-plz'));
    if (neu.prefill.birth && m) q.push(neu.prefill.birth + '=' + ('0' + m[1]).slice(-2) + '.' + ('0' + m[2]).slice(-2) + '.' + m[3]);
    var h = neuGo.indexOf('#'), a = h < 0 ? neuGo : neuGo.slice(0, h), z = h < 0 ? '' : neuGo.slice(h);
    return q.length ? a + '&' + q.join('&') + z : neuGo;
  }
  // Aus dem Rechner mit «Wechseln»: zwei Schritte als Leiste. Schritt 2 wird
  // aktiv, sobald der Brief verschickt ist (siehe done()).
  function stepper(step) {
    if (!neu) return;
    var k = kasse();
    var w = $('wechsel');
    w.innerHTML = '<li class="' + (step === 1 ? 'on' : 'ok') + '"><b>' + (step === 1 ? '1' : '✓') + '</b>' +
      (k ? t('st_1', { k: esc(k.name) }) : t('st_1_any')) + '</li>' +
      '<li class="' + (step === 2 ? 'on' : '') + '"><b>2</b>' + t('st_2', { n: esc(neu.name) }) + '</li>';
    w.hidden = false;
    $('kd-compare').hidden = true;
  }

  var days = Math.floor((DEADLINE - new Date()) / 86400000);
  if (days >= 0) $('kd-left').textContent = days === 0 ? t('last') : t('left', { n: days });
  // Nach der Frist keinen Brief mehr «fristgerecht auf den 31. Dezember»
  // erstellen lassen, er käme zu spät. Die Seite erklärt den nächsten Termin.
  if (days < 0) {
    $('kd-left').textContent = t('closed_left');
    $('kd-tool').hidden = true;
    $('kd-closed').hidden = false;
  }

  function kasse() { return KASSEN.find(function (x) { return String(x.id) === sel.value; }) || null; }
  stepper(1);
  sel.addEventListener('change', function () { if ($('kd-done').hidden) stepper(1); });
  function val(id) { return $(id).value.trim(); }

  // ── Unterschrift (nach der Zeichenfläche in TreuFlow) ──────────────────
  // Zeigerereignisse bedienen Maus, Finger und Stift mit einem Satz Handler,
  // setPointerCapture hält den Strich, wenn die Hand über den Rand fährt.
  // Ausgegeben wird auf den bemalten Bereich zugeschnitten, mit durchsichtigem
  // Hintergrund: sonst käme ein kleiner Schriftzug im PDF winzig an.
  var pad = $('kd-pad'), ctx = null, drawing = false, sig = null;
  function setupPad() {
    pad.width = pad.clientWidth * 2;
    pad.height = pad.clientHeight * 2;
    ctx = pad.getContext('2d');
    ctx.scale(2, 2);
    ctx.lineWidth = 2.2;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.strokeStyle = '#1c1917';
  }
  function point(e) {
    var r = pad.getBoundingClientRect();
    // Hat sich die Breite seit dem Einrichten geändert (Drehen), umrechnen
    return { x: (e.clientX - r.left) * (pad.width / 2) / r.width, y: (e.clientY - r.top) * (pad.height / 2) / r.height };
  }
  function crop() {
    var d = ctx.getImageData(0, 0, pad.width, pad.height).data;
    var minX = pad.width, minY = pad.height, maxX = -1, maxY = -1;
    for (var y = 0; y < pad.height; y++) {
      for (var x = 0; x < pad.width; x++) {
        if (d[(y * pad.width + x) * 4 + 3] > 8) {
          if (x < minX) minX = x;
          if (x > maxX) maxX = x;
          if (y < minY) minY = y;
          if (y > maxY) maxY = y;
        }
      }
    }
    if (maxX < 0) return null;
    var m = 6;
    minX = Math.max(0, minX - m); minY = Math.max(0, minY - m);
    maxX = Math.min(pad.width - 1, maxX + m); maxY = Math.min(pad.height - 1, maxY + m);
    var out = document.createElement('canvas');
    out.width = maxX - minX + 1;
    out.height = maxY - minY + 1;
    out.getContext('2d').drawImage(pad, minX, minY, out.width, out.height, 0, 0, out.width, out.height);
    return out.toDataURL('image/png');
  }
  function padState() {
    $('kd-pad-hint').textContent = sig ? t('pad_ok') : t('pad_go');
    $('kd-pad-clear').disabled = !sig;
  }
  setupPad();
  pad.addEventListener('pointerdown', function (e) {
    e.preventDefault();
    pad.setPointerCapture(e.pointerId);
    drawing = true;
    var p = point(e);
    ctx.beginPath();
    ctx.moveTo(p.x, p.y);
    ctx.lineTo(p.x + 0.1, p.y); // ein Tipp hinterlässt einen Punkt
    ctx.stroke();
  });
  pad.addEventListener('pointermove', function (e) {
    if (!drawing) return;
    e.preventDefault();
    var p = point(e);
    ctx.lineTo(p.x, p.y);
    ctx.stroke();
  });
  function endStroke(e) {
    if (!drawing) return;
    drawing = false;
    try { pad.releasePointerCapture(e.pointerId); } catch (err) {}
    sig = crop();
    if (sig) pad.classList.remove('kd-invalid');
    padState();
    render();
  }
  pad.addEventListener('pointerup', endStroke);
  pad.addEventListener('pointercancel', endStroke);
  $('kd-pad-clear').onclick = function () {
    ctx.clearRect(0, 0, pad.width, pad.height);
    sig = null;
    padState();
    render();
  };
  padState();

  // ── Der Brief ──────────────────────────────────────────────────────────
  function today() {
    return longDate(new Date(), LL());
  }
  function letter() {
    var k = kasse();
    var name = val('kd-name') || b('name');
    var city = (val('kd-plz') + ' ' + val('kd-ort')).trim() || b('city');
    var ort = val('kd-ort') || b('ort');
    var more = $('kd-more').value.split('\n').map(function (s) { return s.trim(); }).filter(Boolean);
    var subject = [b('subject')];
    var ids = [];
    if (val('kd-nr')) ids.push(b('nr') + val('kd-nr'));
    if (val('kd-birth')) ids.push(b('birth') + val('kd-birth'));
    if (ids.length) subject.push(ids.join(', '));
    var body = [(more.length ? b('more') : b('one')) + b('on') + endText() + (more.length ? (LL() === 'fr' ? ' :' : ':') : '.')];
    more.forEach(function (m) { body.push('- ' + m); });
    // Zusatzversicherung kuendigen gibt es hier bewusst nicht mehr (08.10.2026, versehentlich mitgekuendigt)
    body.push('', b('keep'));
    body.push('', b('confirm'));
    return {
      kasse: k, name: name,
      sender: [name, val('kd-street') || b('street'), city],
      recipient: k ? k.address : b('kasse'),
      dateLine: ort + b('dateSep') + today(),
      subject: subject, body: body, hello: b('hello'), bye: b('bye'), footer: b('footer'),
    };
  }
  function plain(L) {
    return [].concat(L.sender, ['', ''], L.recipient, ['', '', L.dateLine, '', ''], L.subject,
      ['', L.hello, ''], L.body, ['', L.bye, '', '', '', L.name]).join('\n');
  }
  function render() {
    var L = letter(), b = $('kd-brief');
    b.textContent = '';
    b.appendChild(document.createTextNode([].concat(L.sender, ['', ''], L.recipient, ['', '', L.dateLine, '', ''], L.subject,
      ['', L.hello, ''], L.body, ['', L.bye, '']).join('\n') + '\n'));
    if (sig) {
      var im = new Image();
      im.src = sig;
      im.alt = t('sig_alt');
      im.className = 'kd-sig-img';
      b.appendChild(im);
    } else {
      b.appendChild(document.createTextNode('\n\n'));
    }
    b.appendChild(document.createTextNode(L.name));
    channel(L);
  }

  // ── Der Weg zur Kasse ──────────────────────────────────────────────────
  function mailBody(L) {
    var lines = [b('hello'), '',
      b('m_body') + endText() + '.', '',
      b('m_name') + L.name];
    if (val('kd-nr')) lines.push(b('m_nr') + val('kd-nr'));
    lines.push('', b('m_confirm'), '', LL() === 'fr' ? 'Meilleures salutations' : 'Freundliche Grüsse', L.name);
    return lines.join('\n');
  }
  function fwdSubject() {
    return (LL() === 'fr' ? 'Résiliation assurance de base' : 'Kündigung Grundversicherung');
  }
  function mailSubject(L) {
    return b('m_subject') + L.name + (val('kd-nr') ? b('m_vnr') + val('kd-nr') : '');
  }
  function mailtoHref(L) {
    return 'mailto:' + encodeURIComponent(L.kasse.mail) + '?subject=' + encodeURIComponent(mailSubject(L)) + '&body=' + encodeURIComponent(mailBody(L));
  }
  function channel(L) {
    var k = L.kasse, el = $('kd-kanal');
    if (!k) { el.innerHTML = ''; return; }
    var src = k.src ? '<div class="kd-src">' + t('src', { u: esc(k.src), d: esc(D.stand) }) + '</div>' : '';
    var nm = esc(k.name);
    if (k.mail) {
      // Der Mail-Link ist schon ausgefüllt: Empfänger, Betreff, Text
      el.innerHTML = t('k_mail', { n: nm, m: '<a href="' + esc(mailtoHref(L)) + '">' + esc(k.mail) + '</a>' }) +
        (k.own ? t('k_own', { n: nm }) : t('k_any')) + src;
    } else if (k.portal) {
      el.innerHTML = t('k_portal', { n: nm, p: esc(k.portal) }) + src;
    } else {
      el.innerHTML = (k.post_only ? t('k_reg', { n: nm, d: esc(D.deadline_text) }) : t('k_post', { n: nm, d: esc(D.deadline_text) })) + src;
    }
  }

  // ── PDF ────────────────────────────────────────────────────────────────
  var pdfLib = null;
  function loadPdf() {
    if (window.jspdf) return Promise.resolve();
    if (pdfLib) return pdfLib;
    pdfLib = new Promise(function (res, rej) {
      var s = document.createElement('script');
      s.src = JSPDF_SRC;
      s.integrity = JSPDF_SRI;
      s.crossOrigin = 'anonymous';
      s.onload = res;
      s.onerror = function () { pdfLib = null; rej(new Error('jspdf')); };
      document.head.appendChild(s);
    });
    return pdfLib;
  }
  function makePdf(L) {
    var doc = new window.jspdf.jsPDF({ unit: 'mm', format: 'a4', compress: true });
    var X = 22, W = 166, LH = 5.2;
    doc.setFont('helvetica', 'normal');
    doc.setFontSize(10.5);
    var y = 22;
    L.sender.forEach(function (s) { doc.text(s, X, y); y += LH; });
    // Empfänger rechts, passend für ein Couvert C5 mit Fenster rechts
    var ry = 52;
    L.recipient.forEach(function (s) { doc.text(s, 118, ry); ry += LH; });
    y = Math.max(y, ry) + 16;
    doc.text(L.dateLine, X, y);
    y += 13;
    doc.setFont('helvetica', 'bold');
    L.subject.forEach(function (s) { doc.splitTextToSize(s, W).forEach(function (l) { doc.text(l, X, y); y += LH; }); });
    doc.setFont('helvetica', 'normal');
    y += 6;
    [L.hello, ''].concat(L.body).forEach(function (p) {
      if (!p) { y += 3; return; }
      doc.splitTextToSize(p, W).forEach(function (l) { doc.text(l, X, y); y += LH; });
    });
    y += 7;
    doc.splitTextToSize(L.bye, W).forEach(function (l, n) { if (n) y += LH; doc.text(l, X, y); });
    y += 4;
    if (sig) {
      var ip = doc.getImageProperties(sig), h = 17, w = Math.min(75, ip.width / ip.height * h);
      doc.addImage(sig, 'PNG', X, y, w, h, undefined, 'FAST');
      y += h + 6;   // Grundlinie des Namens unter der Unterschrift, nicht hinein
    } else {
      y += 22;
    }
    doc.text(L.name, X, y);
    // Fusszeile
    doc.setFontSize(8);
    doc.setTextColor(150);
    doc.text(L.footer, X, 287);
    doc.setTextColor(0);
    doc.setFontSize(10.5);
    doc.setProperties({ title: L.subject[0], creator: 'abovergleich.com' });
    return doc;
  }
  function fileName(L) {
    var k = L.kasse ? L.kasse.name : b('fallbackKasse');
    return b('file') + k.normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^A-Za-z0-9]+/g, '-') + '.pdf';
  }
  function withPdf(btn, fn) {
    var label = btn.textContent;
    if (!check()) return;
    // Unterschrift ist Pflicht: Die Mail an die Kasse spricht von der
    // unterschriebenen Kündigung, und ein ungezeichneter Brief per Post fällt
    // erst auf, wenn die Kasse nachfragt, oft nach der Frist.
    if (!sig) {
      $('kd-msg').textContent = t('no_sig');
      pad.classList.add('kd-invalid');
      pad.scrollIntoView({ behavior: 'smooth', block: 'center' });
      return;
    }
    $('kd-msg').textContent = '';
    btn.disabled = true;
    btn.textContent = t('wait');
    loadPdf().then(function () {
      var L = letter();
      return fn(makePdf(L), L);   // darf ein Promise liefern, der Knopf wartet darauf
    }).catch(function () {
      $('kd-msg').textContent = t('fail');
    }).then(function () {
      btn.disabled = false;
      btn.textContent = btn.id === 'kd-send' && !$('kd-done').hidden ? t('again') : label;
    });
  }

  // Pflichtfelder: ohne sie findet die Kasse dich nicht sicher, und ohne
  // E-Mail können wir das PDF nicht zuschicken.
  var REQUIRED = [['kd-name', t('f_name')], ['kd-birth', t('f_birth')], ['kd-street', t('f_street')],
    ['kd-plz', t('f_plz')], ['kd-ort', t('f_ort')], ['kd-email', t('f_email')]];
  var OK = {
    'kd-birth': /^\d{1,2}\.\d{1,2}\.(19|20)\d{2}$/,
    'kd-plz': /^\d{4}$/,
    'kd-email': /^[^\s@]+@[^\s@]+\.[a-z]{2,}$/i,
  };
  function check() {
    if (!kasse()) { $('kd-msg').textContent = t('no_kasse'); return false; }
    var bad = REQUIRED.filter(function (f) {
      var v = val(f[0]), ok = v && (!OK[f[0]] || OK[f[0]].test(v));
      $(f[0]).classList.toggle('kd-invalid', !ok);
      return !ok;
    });
    if (bad.length) {
      $('kd-msg').textContent = t('missing', { f: bad.map(function (f) { return f[1]; }).join(', ') });
      $(bad[0][0]).focus();
      return false;
    }
    return true;
  }
  REQUIRED.forEach(function (f) { $(f[0]).addEventListener('input', function () { $(f[0]).classList.remove('kd-invalid'); }); });

  // Geburtsdatum: Das iPhone zeigt bei Zifferntastatur keinen Punkt. Also
  // setzen wir die Punkte selbst (26021989 -> 26.02.1989) und nehmen auch
  // / - , oder Leerzeichen als Trenner an.
  function fmtBirth(v, typing) {
    // Zeichen für Zeichen in Tag, Monat, Jahr einordnen. Nach zwei Ziffern
    // springt es von selbst weiter, ein getippter Trenner schliesst den Teil.
    var g = [''], i = 0;
    for (var k = 0; k < v.length; k++) {
      var c = v.charAt(k);
      if (/\d/.test(c)) {
        if (i < 2 && g[i].length === 2) { i++; g[i] = ''; }
        if (i === 2 && g[2].length === 4) break;
        g[i] += c;
      } else if (/[.\/\-, ]/.test(c) && g[i] !== '' && i < 2) { i++; g[i] = ''; }
    }
    var out = g.map(function (x, n) { return n < 2 && x.length === 1 && (n < g.length - 1 || !typing) ? '0' + x : x; });
    if (out[out.length - 1] === '') { out.pop(); return out.join('.') + (typing ? '.' : ''); }
    return out.join('.');
  }
  $('kd-birth').addEventListener('input', function (e) {
    var el = this, before = el.value;
    if (e.inputType && e.inputType.indexOf('delete') === 0) return;   // Löschen nicht stören
    var after = fmtBirth(before, true);
    if (after !== before) el.value = after;
  });
  $('kd-birth').addEventListener('blur', function () { this.value = fmtBirth(this.value, false); render(); });

  // Statistik ohne Namen, Adresse oder E-Mail (Datenschutz 3.3)
  function track(event) {
    var L = letter();
    var body = {
      event: event, quelle: 'editor', kasse_alt: L.kasse ? L.kasse.id : null, kasse_neu: neu ? neu.id : null,
      plz: plzOf(), jahrgang: jahrgangOf(),
      kanal: L.kasse ? (L.kasse.mail ? 'mail' : L.kasse.portal ? 'portal' : 'post') : null,
    };
    try {
      fetch('https://zexpmaegqsayleaohiip.supabase.co/functions/v1/kk-ereignis', { method: 'POST', keepalive: true,
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).catch(function () {});
    } catch (e) {}
  }
  function plzOf() { return /^\d{4}$/.test(val('kd-plz')) ? parseInt(val('kd-plz'), 10) : null; }
  function jahrgangOf() { var m = val('kd-birth').match(/(19|20)\d{2}\s*$/); return m ? parseInt(m[0], 10) : null; }
  function profile() { try { return JSON.parse(localStorage.getItem('kk-profile') || 'null') || {}; } catch (e) { return {}; } }

  // Kopie per Mail an die Person selbst, bei jeder Aktion genau einmal pro
  // Fassung des Briefs. Mit Häkchen schaltet sie den Wechsel-Wecker ein.
  var sent = {};
  var lastDoc = null;
  function sendCopy(doc, L, force) {
    lastDoc = doc;
    var email = val('kd-email'), pr = profile(), k = L.kasse;
    var b64 = doc.output('datauristring').split(',')[1];
    var key = email + '|' + $('kd-wecker').checked + '|' + b64.length + '|' + plain(L).length;
    if (sent[key] && !force) return sent[key];
    sent[key] = fetch('https://zexpmaegqsayleaohiip.supabase.co/functions/v1/kuendigung-pdf', {
      method: 'POST', keepalive: b64.length < 60000, headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: email, wecker: $('kd-wecker').checked, pdf: b64, filename: fileName(L), signiert: !!sig,
        kasse: k.name, kanal: k.mail ? 'mail' : k.portal ? 'portal' : 'post', ziel: k.mail || k.portal || '',
        name: L.name, nr: val('kd-nr'), letter_lang: LL(), end_text: endText(), own: !!k.own,
        deadline: D.deadline_text, neu: neu ? neu.name : '', neu_url: neu && neu.url ? neu.url : '', neu_online: !neu || neu.online !== false, lang: UI,
        plz: plzOf() || pr.plz, jahrgang: jahrgangOf() || pr.year, franchise: pr.franchise,
        accident_included: pr.accident === true, current_insurer_id: k.id, new_insurer_id: neu ? neu.id : null,
        paid_monthly: (function () { try { return parseFloat((localStorage.getItem('kk-paid') || '').replace(',', '.')) || null; } catch (e) { return null; } })(),
      }),
    }).then(function (r) { return r.json(); }).then(function (res) {
      if (!res.ok) { delete sent[key]; throw new Error(res.error || 'Versand'); }
      track('kuendigung_pdf');
      return res;
    }, function (err) { delete sent[key]; throw err; });
    return sent[key];
  }
  function sentText() {
    return t('sent_txt', { m: val('kd-email') });
  }

  // Gut sichtbare Bestätigung statt einer Textzeile
  function done() {
    var box = $('kd-done'), L = letter(), k = L.kasse, nm = esc(k.name), d = esc(D.deadline_text);
    var step1;
    var dl = ' <button type="button" class="kd-link" id="kd-dl">' + t('nx_dl') + '</button>';
    if (k.mail) {
      // Schritt 1: unsere Mail weiterleiten (Text und PDF drin). mailto bleibt
      // als Ausweg, kann aber keinen Anhang mitgeben.
      step1 = '<strong>' + t('nx_fwd', { s: esc(fwdSubject()) }) + '</strong> <b class="kd-addr">' + esc(k.mail) + '</b> ' +
        '<button type="button" class="kd-go kd-copy-addr" id="kd-copy-addr">' + t('nx_copy') + '</button>' +
        '<div class="kd-nx-sub">' + t('nx_fwd_sub') + (k.own ? t('nx_own', { n: nm }) : '') + t('nx_proof') + '</div>' +
        '<div class="kd-nx-sub"><a id="kd-mailto" href="' + esc(mailtoHref(L)) + '">' + t('nx_alt') + '</a></div>';
    } else if (k.portal) {
      step1 = '<div class="kd-nx-sub">' + t('nx_portal', { p: esc(k.portal), d: d }) + dl + '</div>';
    } else {
      step1 = '<div class="kd-nx-sub">' + t('nx_post', { n: nm, d: d }) + dl + '</div>';
    }
    var step2 = neu
      ? (neuGo ? '<a class="kd-go sec" id="kd-neu-go" href="' + esc(neuLink()) + '" target="_blank" rel="noopener sponsored">' + t('nx_neu', { n: esc(neu.name) }) + ' &rarr;</a>' : '<strong>' + t('nx_neu', { n: esc(neu.name) }) + '</strong>') +
        '<div class="kd-nx-sub">' + (neu.online === false ? t('nx_neu_form', { n: esc(neu.name), d: esc(D.start) }) : t('nx_neu_sub', { d: esc(D.start) })) + '</div>'
      : '<a class="kd-go sec" href="' + esc(D.calc) + '">' + t('nx_find') + ' &rarr;</a><div class="kd-nx-sub">' + t('nx_find_sub') + '</div>';
    box.innerHTML = '<div class="kd-done-head"><div class="kd-done-icon">✓</div><div><strong>' + t('done_t') + '</strong>' +
      '<p>' + t(k.mail ? 'done_1_mail' : 'done_1', { m: esc(val('kd-email')) }) + ' <span class="kd-done-small">' + t('done_2') + '</span></p></div></div>' +
      '<div class="kd-nx-h">' + t('nx_h') + '</div>' +
      '<ol class="kd-nx"><li>' + step1 + '</li><li>' + step2 + '</li></ol>' +
      '<div class="kd-nx-sub">' + t('nx_conf', { k: nm }) + '</div>';
    box.hidden = false;
    var m = $('kd-mailto');
    if (m) m.addEventListener('click', function () { track('kuendigung_mail'); });
    var ca = $('kd-copy-addr');
    if (ca) ca.addEventListener('click', function () {
      track('kuendigung_mail');
      (navigator.clipboard ? navigator.clipboard.writeText(k.mail) : Promise.reject()).then(
        function () { ca.textContent = t('copied'); }, function () { ca.textContent = k.mail; });
    });
    var dlb = $('kd-dl');
    if (dlb) dlb.addEventListener('click', function () { if (lastDoc) lastDoc.save(fileName(L)); });
    var g = $('kd-neu-go');
    if (g) g.addEventListener('click', function () { track('anmeldung_klick'); });
    $('kd-msg').textContent = '';
    $('kd-send').textContent = t('again');
    $('kd-send').classList.add('sec');
    stepper(2);
    box.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
  $('kd-send').onclick = function () {
    withPdf(this, function (doc, L) {
      return sendCopy(doc, L, !$('kd-done').hidden).then(function () { done(); },
        function (err) { $('kd-msg').textContent = (err && err.message !== 'Versand' && err.message) || t('send_fail'); });
    });
  };
  $('kd-copy').onclick = function () {
    if (!check()) return;
    var btn = this, txt = plain(letter());
    track('kuendigung_text');
    (navigator.clipboard ? navigator.clipboard.writeText(txt) : Promise.reject()).then(
      function () { btn.textContent = t('copied'); },
      function () { btn.textContent = t('copy_manual'); });
    // Kopie mit PDF trotzdem an die Mail-Adresse
    loadPdf().then(function () { var L = letter(); return sendCopy(makePdf(L), L); })
      .then(function (res) { $('kd-msg').textContent = t('copied_msg') + sentText(res); }, function () {});
  };

  // Auf der englischen Seite richtet sich die Briefsprache nach der PLZ,
  // bis jemand sie von Hand wählt: 1xxx und 2xxx sind fast ganz Romandie.
  if (lsel && UI === 'en') {
    $('kd-plz').addEventListener('input', function () {
      if (!langTouched && /^\d{4}$/.test(val('kd-plz'))) lsel.value = /^[12]/.test(val('kd-plz')) ? 'fr' : 'de';
    });
  }
  ['kd-kasse', 'kd-name', 'kd-birth', 'kd-nr', 'kd-street', 'kd-plz', 'kd-ort', 'kd-more', 'kd-lang'].forEach(function (id) {
    if (!$(id)) return;
    $(id).addEventListener('input', render);
    $(id).addEventListener('change', render);
  });
  render();
})();
