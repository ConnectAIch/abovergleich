// Kündigungsbrief für die Grundversicherung: Formular, Unterschrift, PDF und
// der passende Weg zur Kasse. Alles läuft im Browser, nichts wird gespeichert
// oder von uns verschickt.
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
      ['name', 'street', 'city', 'nr'].forEach(function (k) { if (pf[k] && !$('kd-' + k).value) $('kd-' + k).value = pf[k]; });
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
      '<li><strong>Bei ' + esc(neu.name) + ' anmelden</strong>, für den ' + esc(D.start) + '. Online in ein paar Minuten, ohne Gesundheitsfragen.' +
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
    var city = val('kd-city') || 'PLZ Ort';
    var ort = val('kd-city') ? city.replace(/^\d{4}\s*/, '') || 'Ort' : 'Ort';
    var more = $('kd-more').value.split('\n').map(function (s) { return s.trim(); }).filter(Boolean);
    var subject = ['Kündigung der obligatorischen Krankenpflegeversicherung (Grundversicherung)'];
    if (val('kd-nr')) subject.push('Versicherten-Nr. ' + val('kd-nr'));
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
        'Unterschreib oben, lade das PDF herunter und schick es an <a href="mailto:' + esc(k.mail) + '">' + esc(k.mail) + '</a>' +
        (k.own ? ', <strong>von der Mail-Adresse, die ' + nm + ' von dir kennt</strong>. Von einer anderen Adresse gilt die Kündigung nicht.'
               : ', am besten von der Mail-Adresse, die deine Kasse von dir kennt.') +
        ' Die Eingangsbestätigung der Kasse ist dein Beweis, heb sie auf.' + src;
    } else if (k.portal) {
      el.innerHTML = '<strong>' + nm + ' nimmt die Kündigung per Mail oder im Kundenportal ' + esc(k.portal) + ' an,</strong> nennt aber keine Mail-Adresse. ' +
        'Lade das PDF herunter und schick es über ' + esc(k.portal) + ' oder per Post.' + src;
    } else {
      el.innerHTML = k.post_only
        ? '<strong>Per eingeschriebenem Brief.</strong> ' + nm + ' verlangt das ausdrücklich. ' +
          'Druck das PDF aus und bring es spätestens eine Woche vor dem ' + esc(D.deadline_text) + ' zur Post.' + src
        : '<strong>Per Post an die Adresse im Brief.</strong> ' + nm + ' nennt auf der eigenen Website keinen Mail-Weg für die Grundversicherung. ' +
          'Druck das PDF aus und schick es spätestens eine Woche vor dem ' + esc(D.deadline_text) + ' ab. ' +
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
    var doc = new window.jspdf.jsPDF({ unit: 'mm', format: 'a4' });
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
    y += 3;
    if (sig) {
      var ip = doc.getImageProperties(sig), h = 17, w = Math.min(75, ip.width / ip.height * h);
      doc.addImage(sig, 'PNG', X, y, w, h);
      y += h + 3;
    } else {
      y += 20;
    }
    doc.text(L.name, X, y);
    doc.setProperties({ title: L.subject[0], creator: 'abovergleich.com' });
    return doc;
  }
  function fileName(L) {
    var k = L.kasse ? L.kasse.name : 'Krankenkasse';
    return 'Kuendigung-Grundversicherung-' + k.normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^A-Za-z0-9]+/g, '-') + '.pdf';
  }
  function withPdf(btn, fn) {
    var label = btn.textContent;
    if (!kasse()) { $('kd-msg').textContent = 'Bitte zuerst deine Kasse wählen.'; return; }
    if (!val('kd-name')) { $('kd-msg').textContent = 'Bitte deinen Namen eintragen.'; $('kd-name').focus(); return; }
    $('kd-msg').textContent = '';
    btn.disabled = true;
    btn.textContent = 'Einen Moment…';
    loadPdf().then(function () {
      var L = letter();
      fn(makePdf(L), L);
    }).catch(function () {
      $('kd-msg').textContent = 'Das PDF konnte nicht erstellt werden. Nimm «Text kopieren» oder versuch es nochmals.';
    }).then(function () {
      btn.disabled = false;
      btn.textContent = label;
    });
  }
  // Anonym zählen, von welcher Kasse zu welcher gewechselt wird. Name,
  // Adresse und Unterschrift verlassen den Browser nie.
  function track(event) {
    var L = letter();
    var body = {
      event: event, quelle: 'editor', kasse_alt: L.kasse ? L.kasse.id : null, kasse_neu: neu ? neu.id : null,
      zusatz: (document.querySelector('input[name="kd-zusatz"]:checked') || {}).value,
      kanal: L.kasse ? (L.kasse.mail ? 'mail' : L.kasse.portal ? 'portal' : 'post') : null,
    };
    try {
      fetch('https://zexpmaegqsayleaohiip.supabase.co/functions/v1/kk-ereignis', { method: 'POST', keepalive: true,
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).catch(function () {});
    } catch (e) {}
  }
  $('kd-pdf').onclick = function () {
    withPdf(this, function (doc, L) { doc.save(fileName(L)); track('kuendigung_pdf'); });
  };
  // Mail vorbereiten: PDF speichern und das Mailprogramm mit Empfänger,
  // Betreff und Text öffnen. Den Anhang kann ein mailto-Link nicht mitgeben,
  // der Hinweis sagt das.
  $('kd-mail').onclick = function () {
    withPdf(this, function (doc, L) {
      doc.save(fileName(L));
      track('kuendigung_mail');
      $('kd-msg').textContent = 'PDF gespeichert. Häng es im Mailprogramm an, bevor du auf Senden drückst.';
      location.href = 'mailto:' + encodeURIComponent(L.kasse.mail) + '?subject=' + encodeURIComponent(mailSubject(L)) + '&body=' + encodeURIComponent(mailBody(L));
    });
  };
  // Auf dem Handy: das PDF direkt ins Mailprogramm teilen, mit Anhang
  var canShareFiles = false;
  try { canShareFiles = !!(navigator.canShare && navigator.canShare({ files: [new File(['x'], 'x.pdf', { type: 'application/pdf' })] })); } catch (e) {}
  $('kd-share').hidden = !canShareFiles;
  $('kd-share').onclick = function () {
    withPdf(this, function (doc, L) {
      var file = new File([doc.output('blob')], fileName(L), { type: 'application/pdf' });
      track('kuendigung_mail');
      if (L.kasse.mail && navigator.clipboard) navigator.clipboard.writeText(L.kasse.mail).catch(function () {});
      navigator.share({ files: [file], title: mailSubject(L), text: mailBody(L) }).then(function () {
        if (L.kasse.mail) $('kd-msg').textContent = 'Die Adresse ' + L.kasse.mail + ' ist kopiert, füg sie als Empfänger ein.';
      }).catch(function () {});
    });
  };
  $('kd-copy').onclick = function () {
    var t = plain(letter());
    track('kuendigung_text');
    (navigator.clipboard ? navigator.clipboard.writeText(t) : Promise.reject()).then(
      function () { $('kd-copy').textContent = 'Kopiert'; },
      function () { $('kd-copy').textContent = 'Bitte markieren und kopieren'; });
  };

  ['kd-kasse', 'kd-name', 'kd-nr', 'kd-street', 'kd-city', 'kd-more'].forEach(function (id) {
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
