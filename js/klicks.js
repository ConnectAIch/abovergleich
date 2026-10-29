// Klick-Zaehler fuer alle Seiten von abovergleich.com, an Vercel Web Analytics.
// Bis 29.10.2026 stand dieser Block nur inline in 27 handgepflegten Seiten. Die
// rund 190 generierten Seiten (Kassen, Kantone, Kuendigung, Rating) luden zwar
// Vercel Analytics, zaehlten aber keinen Klick zu handyabo, zu Quellen oder per Mail.
// Wechsel und Kuendigungen laufen separat ueber kk_events (js/rechner.js, js/kuendigung.js).
// Klicks, die hier zaehlen. abovergleich hat keine Affiliate-Links, der Wert
// liegt woanders: Wie viele Leute wechseln ins Handy-Vertical hinueber, und
// pruefen Besucher unsere Quellen nach?
document.addEventListener('click', function(e){
  var a = e.target.closest('a'); if (!a || !a.href) return;
  var host = a.hostname || '';
  var data = { page: location.pathname };
  var name = null;
  if (/(^|\.)handyabo\.com$/.test(host)) {
    // Der Uebergang ins Handy-Vertical. Direkte Kennzahl fuer den
    // Netzwerk-Effekt zwischen den beiden Seiten.
    name = 'handyabo_click';
    data.target = a.pathname || '/';
  } else if (a.protocol === 'mailto:') {
    name = 'mailto_click';
    data.target = a.href.replace('mailto:', '').split('?')[0];
  } else if (host && host !== location.hostname) {
    // Quellenlinks (priminfo, FINMA, BAG, opendata.swiss ...): zeigt, ob
    // Leute die Zahlen wirklich gegenpruefen.
    name = 'outbound_click';
    data.target = host;
  }
  if (!name) return;
  if (typeof window.va === 'function') window.va('event', { name: name, data: data });
}, true);
