// Kündigungsbrief für die Grundversicherung: Formular, Unterschrift, PDF und
// der passende Weg zur Kasse. Der Brief entsteht im Browser. Auf Wunsch
// schicken wir das PDF an die Person selbst (Edge Function kuendigung-pdf,
// schaltet den Wechsel-Wecker ein), nie an die Kasse.
//
// Abschicken muss der Kunde selbst. Groupe Mutuel und Sympany nehmen eine
// Kündigung per Mail nur vom Absender an, den sie vom Kunden kennen, und bei
// den anderen ist eine fremde Absenderadresse mindestens ein Grund für
// Rückfragen. Deshalb liefert die Seite das PDF und einen fertigen Mailentwurf,
// aber keinen Versand.
//
// Die Daten kommen vom Generator (scripts/build_kk_pages.py) im Block
// #kd-data: Adressen aus dem BAG-Verzeichnis, Kündigungswege aus
// scripts/data/kuendigung_kanaele.json.
(function () {
  var D = JSON.parse(document.getElementById('kd-data').textContent);
  var KASSEN = D.kassen, END = D.end, DEADLINE = new Date(D.deadline + 'T23:59:59');
  var JSPDF_SRC = 'https://cdnjs.cloudflare.com/ajax/libs/jspdf/4.2.1/jspdf.umd.min.js';
  var JSPDF_SRI = 'sha512-plOdviVmws4Y3JAvbnpfKb2hVxKM1lCwsi3vmElYRj+tiDLffZ4FVUj5a8vyKJ9pIgl8JCAHEJ4D1iUKBecswg==';
  var $ = function (id) { return document.getElementById(id); };
  var esc = function (s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); };

  // ── Kasse und Vorausfüllung ────────────────────────────────────────────
  var sel = $('kd-kasse');
  sel.add(new Option('Bitte wählen', ''));
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
  if (window.Combobox) Combobox.enhance(sel, { search: true, placeholder: 'Kasse suchen…' });

  // Aus dem Rechner mit «Wechseln»: zuerst bei der neuen Kasse anmelden, dann
  // die bisherige kündigen. Die Reihenfolge ist egal (die alte Versicherung
  // endet erst, wenn die neue sie bestätigt), aber so vergisst man keinen Teil.
  var neu = KASSEN.find(function (k) { return String(k.id) === new URLSearchParams(location.search).get('neu'); });
  if (neu && String(neu.id) !== sel.value) {
    var w = $('wechsel');
    var go = neu.url ? neu.url + '?utm_source=abovergleich.com&utm_medium=affiliate&utm_campaign=kk-wechsel' : null;
    w.innerHTML = '<h2>Wechsel zu ' + esc(neu.name) + ' in zwei Schritten</h2><ol>' +
      '<li><strong>Bei ' + esc(neu.name) + ' anmelden</strong>, für den ' + esc(D.start) + '. Online in etwa 10 Minuten, ohne Gesundheitsfragen. Halte deine AHV-Nummer bereit (steht auf der Versichertenkarte).' +
      (go ? '<br><a class="kd-go" href="' + esc(go) + '" target="_blank" rel="noopener sponsored">Zu ' + esc(neu.name) + ' &rarr;</a>' : '') + '</li>' +
      '<li><strong>Deine bisherige Kasse kündigen</strong>, bis ' + esc(D.deadline_text) + '. Der Brief ist unten schon vorbereitet. <a href="#vorlage">Zum Brief &darr;</a></li></ol>';
    w.hidden = false;
    $('kd-compare').hidden = true;
  }

  var days = Math.floor((DEADLINE - new Date()) / 86400000);
  if (days >= 0) $('kd-left').textContent = days === 0 ? 'Heute ist der letzte Tag.' : 'Noch ' + days + ' Tage.';

  function kasse() { return KASSEN.find(function (x) { return String(x.id) === sel.value; }) || null; }
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
    $('kd-pad-hint').textContent = sig ? 'Sieht gut aus?' : 'Mit Maus, Finger oder Stift unterschreiben.';
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
    return new Date().toLocaleDateString('de-CH', { day: 'numeric', month: 'long', year: 'numeric' });
  }
  function letter() {
    var k = kasse();
    var name = val('kd-name') || 'Vorname Name';
    var city = (val('kd-plz') + ' ' + val('kd-ort')).trim() || 'PLZ Ort';
    var ort = val('kd-ort') || 'Ort';
    var more = $('kd-more').value.split('\n').map(function (s) { return s.trim(); }).filter(Boolean);
    var subject = ['Kündigung der obligatorischen Krankenpflegeversicherung (Grundversicherung)'];
    var ids = [];
    if (val('kd-nr')) ids.push('Versicherten-Nr. ' + val('kd-nr'));
    if (val('kd-birth')) ids.push('Geburtsdatum ' + val('kd-birth'));
    if (ids.length) subject.push(ids.join(', '));
    var body = [(more.length
      ? 'Hiermit kündige ich die obligatorische Krankenpflegeversicherung nach KVG für mich und die folgenden Personen'
      : 'Hiermit kündige ich meine obligatorische Krankenpflegeversicherung nach KVG') +
      ' fristgerecht auf den ' + END + (more.length ? ':' : '.')];
    more.forEach(function (m) { body.push('- ' + m); });
    var zusatz = (document.querySelector('input[name="kd-zusatz"]:checked') || {}).value;
    if (zusatz === 'behalten') body.push('', 'Meine Zusatzversicherungen sind von dieser Kündigung nicht betroffen und laufen weiter.');
    if (zusatz === 'kuendigen') body.push('', 'Zusätzlich kündige ich meine Zusatzversicherungen nach VVG auf den nächstmöglichen Termin.');
    body.push('', 'Bitte bestätigen Sie mir den Eingang der Kündigung schriftlich.');
    return {
      kasse: k, name: name,
      sender: [name, val('kd-street') || 'Strasse Nr.', city],
      recipient: k ? k.address : ['Name der Krankenkasse', 'Adresse'],
      dateLine: ort + ', ' + today(),
      subject: subject, body: body,
    };
  }
  function plain(L) {
    return [].concat(L.sender, ['', ''], L.recipient, ['', '', L.dateLine, '', ''], L.subject,
      ['', 'Sehr geehrte Damen und Herren', ''], L.body, ['', 'Freundliche Grüsse', '', '', '', L.name]).join('\n');
  }
  function render() {
    var L = letter(), b = $('kd-brief');
    b.textContent = '';
    b.appendChild(document.createTextNode([].concat(L.sender, ['', ''], L.recipient, ['', '', L.dateLine, '', ''], L.subject,
      ['', 'Sehr geehrte Damen und Herren', ''], L.body, ['', 'Freundliche Grüsse', '']).join('\n') + '\n'));
    if (sig) {
      var im = new Image();
      im.src = sig;
      im.alt = 'Unterschrift';
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
    var lines = ['Sehr geehrte Damen und Herren', '',
      'Im Anhang sende ich Ihnen meine unterschriebene Kündigung der Grundversicherung auf den ' + END + '.', '',
      'Name: ' + L.name];
    if (val('kd-nr')) lines.push('Versicherten-Nr.: ' + val('kd-nr'));
    lines.push('', 'Bitte bestätigen Sie mir den Eingang.', '', 'Freundliche Grüsse', L.name);
    return lines.join('\n');
  }
  function mailSubject(L) {
    return 'Kündigung Grundversicherung, ' + L.name + (val('kd-nr') ? ', Vers.-Nr. ' + val('kd-nr') : '');
  }
  function channel(L) {
    var k = L.kasse, el = $('kd-kanal');
    $('kd-mail').hidden = !(k && k.mail);
    if (!k) { el.innerHTML = ''; return; }
    var src = k.src ? '<div class="kd-src">Laut <a href="' + esc(k.src) + '" target="_blank" rel="noopener">Website der Kasse</a>, Stand ' + esc(D.stand) + '.</div>' : '';
    var nm = esc(k.name);
    if (k.mail) {
      el.innerHTML = '<strong>' + nm + ' nimmt die Kündigung per Mail an.</strong> ' +
        'Unterschreib oben, lass dir das PDF zuschicken und leite es an <a href="mailto:' + esc(k.mail) + '">' + esc(k.mail) + '</a>' +
        (k.own ? ', <strong>von der Mail-Adresse, die ' + nm + ' von dir kennt</strong>. Von einer anderen Adresse gilt die Kündigung nicht.'
               : ', am besten von der Mail-Adresse, die deine Kasse von dir kennt.') +
        ' Die Eingangsbestätigung der Kasse ist dein Beweis, heb sie auf.' + src;
    } else if (k.portal) {
      el.innerHTML = '<strong>' + nm + ' nimmt die Kündigung per Mail oder im Kundenportal ' + esc(k.portal) + ' an,</strong> nennt aber keine Mail-Adresse. ' +
        'Lass dir das PDF zuschicken und lade es in ' + esc(k.portal) + ' hoch, oder schick es per Post.' + src;
    } else {
      el.innerHTML = k.post_only
        ? '<strong>Per eingeschriebenem Brief.</strong> ' + nm + ' verlangt das ausdrücklich. ' +
          'Lass dir das PDF zuschicken, druck es aus und bring es spätestens eine Woche vor dem ' + esc(D.deadline_text) + ' zur Post.' + src
        : '<strong>Per Post an die Adresse im Brief.</strong> ' + nm + ' nennt auf der eigenen Website keinen Mail-Weg für die Grundversicherung. ' +
          'Lass dir das PDF zuschicken, druck es aus und schick es spätestens eine Woche vor dem ' + esc(D.deadline_text) + ' ab. ' +
          'Ein Einschreiben ist nicht vorgeschrieben, aber dein Beweis, dass der Brief rechtzeitig ankam.' + src;
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
    ['Sehr geehrte Damen und Herren', ''].concat(L.body).forEach(function (p) {
      if (!p) { y += 3; return; }
      doc.splitTextToSize(p, W).forEach(function (l) { doc.text(l, X, y); y += LH; });
    });
    y += 7;
    doc.text('Freundliche Grüsse', X, y);
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
    doc.text('Erstellt mit abovergleich.com, dem unabhängigen Krankenkassen-Vergleich', X, 287);
    doc.setTextColor(0);
    doc.setFontSize(10.5);
    doc.setProperties({ title: L.subject[0], creator: 'abovergleich.com' });
    return doc;
  }
  function fileName(L) {
    var k = L.kasse ? L.kasse.name : 'Krankenkasse';
    return 'Kuendigung-Grundversicherung-' + k.normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^A-Za-z0-9]+/g, '-') + '.pdf';
  }
  function withPdf(btn, fn) {
    var label = btn.textContent;
    if (!check()) return;
    $('kd-msg').textContent = '';
    btn.disabled = true;
    btn.textContent = 'Einen Moment…';
    loadPdf().then(function () {
      var L = letter();
      return fn(makePdf(L), L);   // darf ein Promise liefern, der Knopf wartet darauf
    }).catch(function () {
      $('kd-msg').textContent = 'Das hat nicht geklappt. Versuch es nochmals oder nimm «Text kopieren».';
    }).then(function () {
      btn.disabled = false;
      btn.textContent = btn.id === 'kd-send' && !$('kd-done').hidden ? 'Nochmals senden' : label;
    });
  }

  // Pflichtfelder: ohne sie findet die Kasse dich nicht sicher, und ohne
  // E-Mail können wir das PDF nicht zuschicken.
  var REQUIRED = [['kd-name', 'Name'], ['kd-birth', 'Geburtsdatum'], ['kd-street', 'Strasse'],
    ['kd-plz', 'PLZ'], ['kd-ort', 'Ort'], ['kd-email', 'E-Mail']];
  var OK = {
    'kd-birth': /^\d{1,2}\.\d{1,2}\.(19|20)\d{2}$/,
    'kd-plz': /^\d{4}$/,
    'kd-email': /^[^\s@]+@[^\s@]+\.[a-z]{2,}$/i,
  };
  function check() {
    if (!kasse()) { $('kd-msg').textContent = 'Bitte zuerst deine Kasse wählen.'; return false; }
    var bad = REQUIRED.filter(function (f) {
      var v = val(f[0]), ok = v && (!OK[f[0]] || OK[f[0]].test(v));
      $(f[0]).classList.toggle('kd-invalid', !ok);
      return !ok;
    });
    if (bad.length) {
      $('kd-msg').textContent = 'Bitte noch ausfüllen: ' + bad.map(function (f) { return f[1]; }).join(', ') + '.';
      $(bad[0][0]).focus();
      return false;
    }
    return true;
  }
  REQUIRED.forEach(function (f) { $(f[0]).addEventListener('input', function () { $(f[0]).classList.remove('kd-invalid'); }); });

  // Statistik ohne Namen, Adresse oder E-Mail (Datenschutz 3.3)
  function track(event) {
    var L = letter();
    var body = {
      event: event, quelle: 'editor', kasse_alt: L.kasse ? L.kasse.id : null, kasse_neu: neu ? neu.id : null,
      plz: plzOf(), jahrgang: jahrgangOf(),
      zusatz: (document.querySelector('input[name="kd-zusatz"]:checked') || {}).value,
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
  function sendCopy(doc, L, force) {
    var email = val('kd-email'), pr = profile(), k = L.kasse;
    var b64 = doc.output('datauristring').split(',')[1];
    var key = email + '|' + $('kd-wecker').checked + '|' + b64.length + '|' + plain(L).length;
    if (sent[key] && !force) return sent[key];
    sent[key] = fetch('https://zexpmaegqsayleaohiip.supabase.co/functions/v1/kuendigung-pdf', {
      method: 'POST', keepalive: b64.length < 60000, headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: email, wecker: $('kd-wecker').checked, pdf: b64, filename: fileName(L), signiert: !!sig,
        kasse: k.name, kanal: k.mail ? 'mail' : k.portal ? 'portal' : 'post', ziel: k.mail || k.portal || '',
        deadline: D.deadline_text, neu: neu ? neu.name : '', neu_url: neu && neu.url ? neu.url : '',
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
    return 'Mail ist unterwegs an ' + val('kd-email') + '. Klick dort auf «Kündigung herunterladen», damit bestätigst du auch deine Adresse. Nichts da? Schau im Spam-Ordner.';
  }

  // Gut sichtbare Bestätigung statt einer Textzeile
  function done() {
    var box = $('kd-done');
    box.innerHTML = '<div class="kd-done-icon">✓</div><div><strong>Verschickt!</strong>' +
      '<p>Die Mail ist unterwegs an <b>' + esc(val('kd-email')) + '</b>. Öffne sie und klick auf «Kündigung herunterladen».</p>' +
      '<p style="font-size:13px;color:var(--muted);margin-top:6px;">Nach 5 Minuten nichts da? Schau im Spam-Ordner nach oder prüf die Adresse oben.</p></div>';
    box.hidden = false;
    $('kd-msg').textContent = '';
    $('kd-send').textContent = 'Nochmals senden';
    $('kd-send').classList.add('sec');
    box.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
  $('kd-send').onclick = function () {
    withPdf(this, function (doc, L) {
      return sendCopy(doc, L, !$('kd-done').hidden).then(function () { done(); },
        function (err) { $('kd-msg').textContent = (err && err.message !== 'Versand' && err.message) || 'Der Versand hat nicht geklappt. Bitte nochmals versuchen.'; });
    });
  };
  // Mail an die Kasse: zuerst die Kopie mit PDF an dich, dann das Mailprogramm
  // mit Empfänger, Betreff und Text. Den Anhang kann ein mailto-Link nicht
  // mitgeben, also leitest du am einfachsten unsere Mail weiter.
  $('kd-mail').onclick = function () {
    withPdf(this, function (doc, L) {
      return sendCopy(doc, L).then(function (res) {
        track('kuendigung_mail');
        $('kd-msg').textContent = sentText(res) + ' Das PDF hängst du dann an die Mail an die Kasse an.';
        location.href = 'mailto:' + encodeURIComponent(L.kasse.mail) + '?subject=' + encodeURIComponent(mailSubject(L)) + '&body=' + encodeURIComponent(mailBody(L));
      }, function () { $('kd-msg').textContent = 'Der Versand hat nicht geklappt. Bitte nochmals versuchen.'; });
    });
  };
  $('kd-copy').onclick = function () {
    if (!check()) return;
    var btn = this, t = plain(letter());
    track('kuendigung_text');
    (navigator.clipboard ? navigator.clipboard.writeText(t) : Promise.reject()).then(
      function () { btn.textContent = 'Kopiert'; },
      function () { btn.textContent = 'Bitte markieren und kopieren'; });
    // Kopie mit PDF trotzdem an die Mail-Adresse
    loadPdf().then(function () { var L = letter(); return sendCopy(makePdf(L), L); })
      .then(function (res) { $('kd-msg').textContent = 'Text kopiert. ' + sentText(res); }, function () {});
  };

  ['kd-kasse', 'kd-name', 'kd-birth', 'kd-nr', 'kd-street', 'kd-plz', 'kd-ort', 'kd-more'].forEach(function (id) {
    $(id).addEventListener('input', render);
    $(id).addEventListener('change', render);
  });
  Array.prototype.forEach.call(document.querySelectorAll('input[name="kd-zusatz"]'), function (r) {
    r.addEventListener('change', function () {
      $('kd-zusatz-warn').hidden = !document.querySelector('input[name="kd-zusatz"][value="kuendigen"]').checked;
      render();
    });
  });
  render();
})();
