// Prämienrechner der Startseite, eine Datei für alle drei Sprachen
// (/, /fr/, /en/). Die Sprache kommt aus <html lang>, jeder sichtbare Text aus
// T, jeder interne Weg aus ROUTE (gleich wie scripts/i18n.py ROUTES).
// Klassisches Skript ohne Modul-Hülle: checkKK, toggleNav und closeNav müssen
// global bleiben, die Seiten rufen sie aus onclick= auf.
const LANG = { fr: 'fr', en: 'en' }[document.documentElement.lang] || 'de';

// Nur die Wege, die das Skript selbst baut. Muss zu scripts/i18n.py passen.
const ROUTE = {
  kassen:    { de: '/kasse/', fr: '/fr/caisses/', en: '/en/insurers/' },
  kuendigen: { de: '/krankenkasse-kuendigen/', fr: '/fr/resilier-caisse-maladie/', en: '/en/cancel-health-insurance/' },
  rating:    { de: '/krankenkassen-rating/', fr: '/fr/constance-des-primes/', en: '/en/health-insurance-rating/' },
  blog26:    { de: '/blog/krankenkasse-mit-26/', fr: '/fr/guide/caisse-maladie-a-26-ans/', en: '/en/guide/health-insurance-at-26/' },
};
const route = key => ROUTE[key][LANG];

// Die Rating-Daten trägt das <script>-Tag mit (data-rating), damit
// build_kk_pages.bust_assets() die ?v= Prüfsumme in der HTML-Seite nachführt.
const RATING_URL = (document.currentScript && document.currentScript.dataset.rating) || '/rating-daten.json';

// Texte. {name} wird von t(key, { name }) ersetzt. HTML in den Texten ist gewollt.
const T = {
  // Wechsel-Wecker
  weckerConfirmed: { de: 'Dein Wechsel-Wecker ist bestätigt. Wir melden uns, sobald die neuen Prämien da sind.',
    fr: 'Votre rappel de changement est confirmé. Nous vous écrirons dès que les nouvelles primes seront publiées.',
    en: 'Your switch reminder is confirmed. We will be in touch as soon as the new premiums are out.' },
  weckerUnsubscribed: { de: 'Du bist vom Wechsel-Wecker abgemeldet. Wir schicken dir keine Mails mehr.',
    fr: 'Vous êtes désinscrit du rappel de changement. Nous ne vous enverrons plus d’e-mails.',
    en: 'You have unsubscribed from the switch reminder. We will not send you any more emails.' },
  weckerInvalid: { de: 'Dieser Link ist nicht mehr gültig. Melde dich einfach nochmals an.',
    fr: 'Ce lien n’est plus valable. Inscrivez-vous simplement à nouveau.',
    en: 'This link is no longer valid. Just sign up again.' },
  weckerFailed: { de: 'Anmeldung nicht möglich.', fr: 'Inscription impossible.', en: 'Sign-up not possible.' },
  weckerAlready: { de: 'Du bist schon angemeldet. Wir haben deine Angaben aktualisiert.',
    fr: 'Vous êtes déjà inscrit. Nous avons mis à jour vos données.',
    en: 'You are already signed up. We have updated your details.' },
  weckerCheckMail: { de: 'Fast geschafft: Bitte bestätige die Mail, die wir dir eben geschickt haben.',
    fr: 'Presque terminé : veuillez confirmer l’e-mail que nous venons de vous envoyer.',
    en: 'Almost done: please confirm the email we have just sent you.' },

  // Rechnung hochladen
  pdfTooBig: { de: 'PDF zu gross (max. 5 MB).', fr: 'PDF trop volumineux (max. 5 Mo).', en: 'PDF too large (max. 5 MB).' },
  fileUnreadable: { de: 'Datei konnte nicht gelesen werden.', fr: 'Le fichier n’a pas pu être lu.', en: 'The file could not be read.' },
  imageUnreadable: { de: 'Bild konnte nicht gelesen werden. Versuche ein JPG oder PDF.',
    fr: 'L’image n’a pas pu être lue. Essayez avec un JPG ou un PDF.',
    en: 'The image could not be read. Try a JPG or PDF.' },
  pickInsurer: { de: 'Kasse «{insurer}» bitte selbst auswählen', fr: 'Veuillez sélectionner vous-même la caisse «{insurer}»',
    en: 'Please select the insurer “{insurer}” yourself' },
  morePersons: { de: '{n} Personen auf der Rechnung, verglichen wird {name}',
    fr: '{n} personnes sur la facture, la comparaison porte sur {name}',
    en: '{n} people on the bill, comparing {name}' },
  firstPerson: { de: 'die erste', fr: 'la première', en: 'the first one' },
  reading: { de: 'Lese dein Dokument, das dauert ein paar Sekunden…', fr: 'Lecture de votre document, cela prend quelques secondes…',
    en: 'Reading your document, this takes a few seconds…' },
  docUnreadable: { de: 'Das Dokument konnte nicht gelesen werden.', fr: 'Le document n’a pas pu être lu.', en: 'The document could not be read.' },
  applied: { de: 'Übernommen. ', fr: 'Données reprises. ', en: 'Details filled in. ' },
  addPlzYear: { de: 'Bitte PLZ und Jahrgang ergänzen.', fr: 'Veuillez compléter le NPA et l’année de naissance.',
    en: 'Please add your postcode and year of birth.' },
  searchInsurer: { de: 'Kasse suchen…', fr: 'Rechercher une caisse…', en: 'Search insurer…' },

  // Eingaben prüfen, Laden
  badPlz: { de: 'Bitte eine gültige Schweizer PLZ eingeben (1000–9699).', fr: 'Veuillez saisir un NPA suisse valable (1000 à 9699).',
    en: 'Please enter a valid Swiss postcode (1000 to 9699).' },
  badYear: { de: 'Bitte gültiges Geburtsjahr eingeben (1930–2010).', fr: 'Veuillez saisir une année de naissance valable (1930 à 2010).',
    en: 'Please enter a valid year of birth (1930 to 2010).' },
  loadingPremiums: { de: 'Lade Prämien...', fr: 'Chargement des primes...', en: 'Loading premiums...' },
  searching: { de: 'Suche günstigste Kassen...', fr: 'Recherche des caisses les moins chères...', en: 'Finding the cheapest insurers...' },
  loadError: { de: 'Fehler beim Laden der Prämien. Bitte versuche es erneut.', fr: 'Erreur lors du chargement des primes. Veuillez réessayer.',
    en: 'Error loading the premiums. Please try again.' },
  subline: { de: '{locality} ({canton}) · {age} · Franchise CHF {franchise} · {accident}',
    fr: '{locality} ({canton}) · {age} · Franchise CHF {franchise} · {accident}',
    en: '{locality} ({canton}) · {age} · Deductible CHF {franchise} · {accident}' },
  withAccident: { de: 'Mit Unfall', fr: 'Avec accidents', en: 'With accident cover' },
  withoutAccident: { de: 'Ohne Unfall', fr: 'Sans accidents', en: 'Without accident cover' },
  // Altersklassen, wie get-cheapest-premiums sie auf Deutsch liefert. DE zeigt den Servertext.
  age_KIN: { de: 'Kinder (0-18)', fr: 'Enfants (0-18)', en: 'Children (0-18)' },
  age_JUG: { de: 'Junge Erwachsene (19-25)', fr: 'Jeunes adultes (19-25)', en: 'Young adults (19-25)' },
  age_ERW: { de: 'Erwachsene (26+)', fr: 'Adultes (26+)', en: 'Adults (26+)' },

  // Modelle
  model_standard: { de: 'Standard', fr: 'Standard', en: 'Standard' },
  model_family_doctor: { de: 'Hausarzt', fr: 'Médecin de famille', en: 'Family doctor' },
  model_hmo: { de: 'HMO', fr: 'HMO', en: 'HMO' },
  model_telmed: { de: 'Telmed', fr: 'Telmed', en: 'Telmed' },
  model_diverse: { de: 'Alternativ', fr: 'Alternatif', en: 'Alternative' },
  model_apotheke: { de: 'Apotheke', fr: 'Pharmacie', en: 'Pharmacy' },
  standardFree: { de: 'Standard (freie Arztwahl)', fr: 'Standard (libre choix du médecin)', en: 'Standard (free choice of doctor)' },
  tip_standard: { de: 'Freie Arztwahl. Du gehst direkt zu jedem Arzt oder Spital deiner Wahl.',
    fr: 'Libre choix du médecin. Vous allez directement chez le médecin ou à l’hôpital de votre choix.',
    en: 'Free choice of doctor. You go straight to any doctor or hospital you like.' },
  tip_hmo: { de: 'Du gehst zuerst in ein HMO-Zentrum (Gruppenpraxis). Von dort wirst du bei Bedarf überwiesen.',
    fr: 'Vous vous rendez d’abord dans un centre HMO (cabinet de groupe). De là, vous êtes adressé plus loin si nécessaire.',
    en: 'You go to an HMO centre (group practice) first. From there you are referred on if needed.' },
  tip_family_doctor: { de: 'Du gehst immer zuerst zu deinem gewählten Hausarzt. Er überweist dich bei Bedarf weiter.',
    fr: 'Vous consultez toujours d’abord le médecin de famille que vous avez choisi. Il vous adresse plus loin si nécessaire.',
    en: 'You always see the family doctor you have chosen first. They refer you on if needed.' },
  tip_telmed: { de: 'Du rufst zuerst eine medizinische Hotline an, bevor du einen Arzt aufsuchst.',
    fr: 'Vous appelez d’abord une hotline médicale avant de consulter un médecin.',
    en: 'You call a medical hotline first, before you see a doctor.' },
  tip_apotheke: { de: 'Erste Anlaufstelle ist die Apotheke. Von dort wirst du bei Bedarf an einen Arzt verwiesen.',
    fr: 'Votre premier interlocuteur est la pharmacie. De là, vous êtes orienté vers un médecin si nécessaire.',
    en: 'Your first port of call is the pharmacy. From there you are sent to a doctor if needed.' },
  tip_diverse: { de: 'Flexibles Modell: du wählst je nach Fall Hausarzt, Telmed-Hotline oder Apotheke als erste Anlaufstelle.',
    fr: 'Modèle flexible : selon le cas, vous choisissez le médecin de famille, la hotline Telmed ou la pharmacie comme premier interlocuteur.',
    en: 'Flexible model: depending on the case, you choose the family doctor, the Telmed hotline or the pharmacy as your first port of call.' },
  changeVs: { de: '{change}% ggü. {prev}', fr: '{change} % vs {prev}', en: '{change}% vs {prev}' },
  newTariff: { de: 'neuer Tarif', fr: 'nouveau tarif', en: 'new tariff' },

  // Tariferkennung aus dem Rechnungsbetrag
  matchSeveral: { de: 'Dein Betrag passt zu {n} Tarifen mit gleicher Prämie {prev}. Wähle unten, welcher auf deiner Police steht.',
    fr: 'Votre montant correspond à {n} tarifs avec la même prime en {prev}. Choisissez ci-dessous celui qui figure sur votre police.',
    en: 'Your amount matches {n} tariffs with the same premium in {prev}. Choose below which one is on your policy.' },
  matchOne: { de: 'Tarif anhand deiner Rechnung erkannt.', fr: 'Tarif identifié d’après votre facture.', en: 'Tariff identified from your bill.' },
  matchNearest: { de: 'Kein Tarif kostete genau CHF {paid}. Am nächsten liegt {tariff} ({prev}: CHF {price}), damit rechnen wir.',
    fr: 'Aucun tarif ne coûtait exactement CHF {paid}. Le plus proche est {tariff} ({prev} : CHF {price}), nous calculons avec celui-ci.',
    en: 'No tariff cost exactly CHF {paid}. The closest is {tariff} ({prev}: CHF {price}), so we use that one.' },
  matchOtherAcc: { de: 'Dein Betrag passt zu Franchise CHF {franchise} mit Unfall ({tariff}). <button class="kk-link" id="kk-apply-match">Damit rechnen</button>',
    fr: 'Votre montant correspond à une franchise de CHF {franchise} avec accidents ({tariff}). <button class="kk-link" id="kk-apply-match">Calculer ainsi</button>',
    en: 'Your amount matches a CHF {franchise} deductible with accident cover ({tariff}). <button class="kk-link" id="kk-apply-match">Use this</button>' },
  matchOtherNoAcc: { de: 'Dein Betrag passt zu Franchise CHF {franchise} ohne Unfall ({tariff}). <button class="kk-link" id="kk-apply-match">Damit rechnen</button>',
    fr: 'Votre montant correspond à une franchise de CHF {franchise} sans accidents ({tariff}). <button class="kk-link" id="kk-apply-match">Calculer ainsi</button>',
    en: 'Your amount matches a CHF {franchise} deductible without accident cover ({tariff}). <button class="kk-link" id="kk-apply-match">Use this</button>' },
  matchNone: { de: 'Kein Tarif deiner Kasse kostete {prev} genau CHF {paid}. Nimm den Betrag der Grundversicherung von der Rechnung, ohne Zusatzversicherung, oder wähle deinen Tarif unten.',
    fr: 'Aucun tarif de votre caisse ne coûtait exactement CHF {paid} en {prev}. Reprenez le montant de l’assurance de base sur la facture, sans assurance complémentaire, ou choisissez votre tarif ci-dessous.',
    en: 'None of your insurer’s tariffs cost exactly CHF {paid} in {prev}. Use the basic insurance amount from your bill, without supplementary insurance, or choose your tariff below.' },

  // Eigene Kasse
  yourInsurer: { de: 'Deine Kasse', fr: 'Votre caisse', en: 'Your insurer' },
  yourInsurerYear: { de: 'Deine Kasse {year}', fr: 'Votre caisse {year}', en: 'Your insurer {year}' },
  notOffered: { de: 'Bietet an deinem Wohnort keine Grundversicherung für dieses Profil an.',
    fr: 'Ne propose pas d’assurance de base pour ce profil à votre lieu de domicile.',
    en: 'Does not offer basic insurance for this profile where you live.' },
  billYear: { de: 'Rechnung {year}: <strong>CHF {amount}</strong>', fr: 'Facture {year} : <strong>CHF {amount}</strong>',
    en: 'Bill {year}: <strong>CHF {amount}</strong>' },
  prevBill: { de: '{prev}: CHF {amount} <span class="{cls}">({sign}CHF {diff}/Jahr)</span>',
    fr: '{prev} : CHF {amount} <span class="{cls}">({sign}CHF {diff}/an)</span>',
    en: '{prev}: CHF {amount} <span class="{cls}">({sign}CHF {diff}/year)</span>' },
  tariffNew: { de: 'Tarif neu {year}', fr: 'Nouveau tarif {year}', en: 'New tariff in {year}' },
  fromBill: { de: ' · aus deiner Rechnung', fr: ' · d’après votre facture', en: ' · from your bill' },
  assumeStandard: { de: 'Annahme: Standardmodell. Trag oben ein, was du heute zahlst, dann rechnen wir mit deinem Tarif.',
    fr: 'Hypothèse : modèle standard. Indiquez plus haut ce que vous payez aujourd’hui et nous calculerons avec votre tarif.',
    en: 'Assumption: standard model. Enter what you pay today above and we will calculate with your tariff.' },
  alreadyCheapest: { de: 'Du bist schon bei der günstigsten Kasse.', fr: 'Vous êtes déjà à la caisse la moins chère.',
    en: 'You are already with the cheapest insurer.' },
  saveGuessed: { de: 'Falls du im Standardmodell bist: <strong>CHF {amount} pro Jahr</strong> weniger mit {insurer}. <a href="{href}">Jetzt wechseln &rarr;</a>',
    fr: 'Si vous êtes dans le modèle standard : <strong>CHF {amount} par an</strong> de moins avec {insurer}. <a href="{href}">Changer maintenant &rarr;</a>',
    en: 'If you are on the standard model: <strong>CHF {amount} a year</strong> less with {insurer}. <a href="{href}">Switch now &rarr;</a>' },
  saveKnown: { de: '<strong>CHF {amount} pro Jahr</strong> sparst du mit {insurer}. <a href="{href}">Jetzt wechseln &rarr;</a>',
    fr: 'Vous économisez <strong>CHF {amount} par an</strong> avec {insurer}. <a href="{href}">Changer maintenant &rarr;</a>',
    en: 'You save <strong>CHF {amount} a year</strong> with {insurer}. <a href="{href}">Switch now &rarr;</a>' },
  pickerNarrowed: { de: 'Passt zu {n} Tarifen. Welcher steht auf deiner Police?', fr: 'Correspond à {n} tarifs. Lequel figure sur votre police?',
    en: 'Matches {n} tariffs. Which one is on your policy?' },
  pickerAll: { de: 'Anderes Modell? Tarif wählen', fr: 'Autre modèle? Choisir le tarif', en: 'Different model? Choose your tariff' },

  // Abzeichen aus dem Preistreue-Rating
  sitAcc: { de: 'mit Unfall, Franchise {f}', fr: 'avec accidents, franchise {f}', en: 'with accident cover, deductible {f}' },
  sitNoAcc: { de: 'ohne Unfall, Franchise {f}', fr: 'sans accidents, franchise {f}', en: 'without accident cover, deductible {f}' },
  chipNote: { de: 'Preistreue {note}', fr: 'Constance des primes {note}', en: 'Price consistency {note}' },
  chipNoteTip: { de: 'Note in deiner Region für deine Situation ({sit}). Gesamtnote über alle Situationen: {total}.',
    fr: 'Note dans votre région pour votre situation ({sit}). Note globale, toutes situations confondues : {total}.',
    en: 'Score in your region for your situation ({sit}). Overall score across all situations: {total}.' },
  chipCheap: { de: 'Dauerhaft günstig', fr: 'Durablement avantageuse', en: 'Consistently cheap' },
  chipCheapTip: { de: 'In deiner Region in {a} von {b} Jahren seit {from} unter den {top} günstigsten Kassen, bei dieser Franchise.',
    fr: 'Dans votre région, parmi les {top} caisses les moins chères {a} années sur {b} depuis {from}, avec cette franchise.',
    en: 'In your region, among the {top} cheapest insurers in {a} of {b} years since {from}, with this deductible.' },
  chipSince: { de: 'Tarif seit {since}', fr: 'Tarif depuis {since}', en: 'Tariff since {since}' },
  chipSinceTip: { de: 'Diesen Tarif gibt es erst seit {since}, neu oder umbenannt. Neue Sparmodelle starten oft mit viel Rabatt und verlieren ihn in den Folgejahren.',
    fr: 'Ce tarif n’existe que depuis {since}, nouveau ou renommé. Les nouveaux modèles alternatifs démarrent souvent avec un fort rabais et le perdent les années suivantes.',
    en: 'This tariff has only existed since {since}, either new or renamed. New savings models often start with a big discount and lose it in the following years.' },

  // Ergebnisliste
  fullAnalysis: { de: 'Ganze Analyse von {insurer}', fr: 'Analyse complète de la caisse {insurer}', en: 'Full analysis of {insurer}' },
  switchTo: { de: 'Wechseln', fr: 'Changer', en: 'Switch' },
  switchTitle: { de: 'Zu {insurer} wechseln: kündigen und anmelden', fr: 'Passer à {insurer} : résilier et s’inscrire', en: 'Switch to {insurer}: cancel and sign up' },
  analysis: { de: 'Analyse', fr: 'Analyse', en: 'Analysis' },
  changeModel: { de: 'Modell ändern', fr: 'Changer de modèle', en: 'Change model' },
  cheaperYear: { de: 'CHF {amount}/Jahr günstiger', fr: 'CHF {amount}/an de moins', en: 'CHF {amount}/year cheaper' },
  dearerYear: { de: 'CHF {amount}/Jahr teurer', fr: 'CHF {amount}/an de plus', en: 'CHF {amount}/year more' },
  yourInsurerTag: { de: 'Deine Kasse', fr: 'Votre caisse', en: 'Your insurer' },
  noneForModel: { de: 'Keine Prämien für dieses Modell gefunden.', fr: 'Aucune prime trouvée pour ce modèle.', en: 'No premiums found for this model.' },
  showLess: { de: 'Weniger anzeigen', fr: 'Afficher moins', en: 'Show fewer' },
  showMore: { de: 'Weitere Kassen anzeigen ({n})', fr: 'Afficher d’autres caisses ({n})', en: 'Show more insurers ({n})' },
  listNote: { de: 'Pro Kasse der günstigste Tarif, Monatsprämie laut BAG', fr: 'Le tarif le moins cher par caisse, prime mensuelle selon l’OFSP',
    en: 'Cheapest tariff per insurer, monthly premium according to the FOPH' },
  listNoteTip: { de: 'Auf deiner Rechnung steht die Prämie minus Umweltabgabe ({year}: CHF {refund} im Monat). Die Leistungen sind bei allen Kassen und Modellen gesetzlich gleich, nur der Zugangsweg unterscheidet sich.',
    fr: 'Votre facture indique la prime moins la taxe environnementale redistribuée ({year} : CHF {refund} par mois). Les prestations sont les mêmes de par la loi dans toutes les caisses et tous les modèles, seul le premier interlocuteur change.',
    en: 'Your bill shows the premium minus the environmental levy refund ({year}: CHF {refund} a month). By law, benefits are the same with every insurer and model, only the way you access care differs.' },

  // Hinweis für junge Erwachsene
  adultFrom: { de: 'Ab 1. Januar {year} zahlst du die Erwachsenenprämie.', fr: 'À partir du 1er janvier {year}, vous payez la prime pour adultes.',
    en: 'From 1 January {year} you pay the adult premium.' },
  at26: { de: 'Mit 26 wird es deutlich teurer.', fr: 'À 26 ans, la caisse-maladie devient nettement plus chère.', en: 'At 26 it gets much more expensive.' },
  rise26: { de: 'Im selben Tarif steigt die Prämie dann je nach Kasse und Franchise um ein Viertel bis zwei Drittel. ',
    fr: 'Dans le même tarif, la prime augmente alors d’un quart à deux tiers selon la caisse et la franchise. ',
    en: 'On the same tariff, the premium then rises by a quarter to two thirds, depending on insurer and deductible. ' },
  compareAutumn: { de: 'Vergleiche im Herbst {year} neu, die günstigste Kasse für Junge ist oft nicht die günstigste für Erwachsene.',
    fr: 'Comparez à nouveau en automne {year} : la caisse la moins chère pour les jeunes n’est souvent pas la moins chère pour les adultes.',
    en: 'Compare again in autumn {year}: the cheapest insurer for young adults is often not the cheapest for adults.' },
  compareBefore26: { de: 'Vergleiche im Jahr, bevor du 26 wirst, neu.', fr: 'Comparez à nouveau l’année qui précède vos 26 ans.',
    en: 'Compare again in the year before you turn 26.' },
  moreAbout: { de: 'Mehr dazu &rarr;', fr: 'En savoir plus &rarr;', en: 'Read more &rarr;' },
};

function t(key, vars) {
  const e = T[key];
  let s = e[LANG] != null ? e[LANG] : e.de;
  if (vars) s = s.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? String(vars[k]) : m));
  return s;
}

// Fehlermeldungen der Edge Functions kommen auf Deutsch. Auf FR/EN übersetzen,
// was bekannt ist, sonst die allgemeine Meldung (fallbackKey). DE zeigt sie wie bisher.
const SERVER_MSG = {
  'Zu viele Versuche. Bitte später nochmals.': { fr: 'Trop de tentatives. Veuillez réessayer plus tard.', en: 'Too many attempts. Please try again later.' },
  'Bitte eine gültige E-Mail-Adresse eingeben.': { fr: 'Veuillez saisir une adresse e-mail valable.', en: 'Please enter a valid email address.' },
  'Bitte zuerst den Rechner ausfüllen.': { fr: 'Veuillez d’abord remplir le calculateur.', en: 'Please fill in the calculator first.' },
  'Anmeldung nicht möglich. Bitte später nochmals.': { fr: 'Inscription impossible. Veuillez réessayer plus tard.', en: 'Sign-up not possible. Please try again later.' },
  'Die Bestätigungsmail konnte nicht verschickt werden.': { fr: 'L’e-mail de confirmation n’a pas pu être envoyé.', en: 'The confirmation email could not be sent.' },
  'Keine Datei erhalten.': { fr: 'Aucun fichier reçu.', en: 'No file received.' },
  'Datei zu gross (max. 6 MB).': { fr: 'Fichier trop volumineux (max. 6 Mo).', en: 'File too large (max. 6 MB).' },
  'Nur Fotos oder PDF.': { fr: 'Uniquement des photos ou des PDF.', en: 'Photos or PDF only.' },
  'Gerade ausgelastet. Bitte in einer Minute nochmals.': { fr: 'Service surchargé. Veuillez réessayer dans une minute.', en: 'Busy right now. Please try again in a minute.' },
  'Texterkennung nicht erreichbar.': { fr: 'La reconnaissance de texte n’est pas disponible.', en: 'Text recognition is not available.' },
  'Das sieht nicht nach einer Rechnung oder Police einer Krankenkasse aus.': { fr: 'Cela ne ressemble pas à une facture ou à une police de caisse-maladie.',
    en: 'This does not look like a bill or policy from a health insurer.' },
};
function serverMsg(msg, fallbackKey) {
  if (LANG === 'de') return msg || t(fallbackKey);
  if (msg && SERVER_MSG[msg]) return SERVER_MSG[msg][LANG];
  const plz = /^PLZ (\d+) nicht gefunden$/.exec(msg || '');
  if (plz) return LANG === 'fr' ? `NPA ${plz[1]} introuvable` : `Postcode ${plz[1]} not found`;
  return t(fallbackKey);
}

// Zahlen: Franken in allen Sprachen mit Schweizer Apostroph (de-CH). Andere
// Dezimalzahlen: Komma auf FR, Punkt auf EN. Auf DE bleibt es wie bisher: die
// Noten mit Komma, die Prozent-Veränderung mit Punkt (toFixed).
const decSep = (s, commaLangs) => (commaLangs.includes(LANG) ? s.replace('.', ',') : s);

const SUPABASE_URL = 'https://zexpmaegqsayleaohiip.supabase.co';

// ── SWISS VALIDATION HELPERS ──────────────────────────────────────────
const SwissValidation = {
  // Email: proper RFC-lite regex
  isValidEmail(email) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email);
  },

  // Swiss PLZ: 1000–9699 (real CH range)
  isValidPLZ(plz) {
    const n = parseInt(plz, 10);
    return /^\d{4}$/.test(plz) && n >= 1000 && n <= 9699;
  },

  // Name: at least two words, each 2+ chars
  isValidFullName(name) {
    const parts = name.trim().split(/\s+/);
    return parts.length >= 2 && parts.every(p => p.length >= 2);
  },

  // Street: must contain text + a house number
  isValidStreet(street) {
    return /[a-zA-ZäöüÄÖÜ]{2,}/.test(street) && /\d/.test(street);
  },

  // PLZ → City lookup via Swiss Post open data (cached)
  _plzCache: {},
  async lookupCity(plz) {
    if (!this.isValidPLZ(plz)) return null;
    if (this._plzCache[plz]) return this._plzCache[plz];
    try {
      const res = await fetch('https://swisspost.opendatasoft.com/api/records/1.0/search/?dataset=plz_verzeichnis_v2&q=' + plz + '&rows=1&refine.postleitzahl=' + plz);
      const data = await res.json();
      const rec = data.records && data.records[0];
      if (rec) {
        const city = rec.fields.ortbez18 || rec.fields.ortbez27 || null;
        if (city) this._plzCache[plz] = city;
        return city;
      }
    } catch (e) { /* silent fail — user can type city manually */ }
    return null;
  },

  // Show inline error below a field
  showFieldError(inputEl, message) {
    this.clearFieldError(inputEl);
    const err = document.createElement('div');
    err.className = 'field-validation-error';
    err.textContent = message;
    err.style.cssText = 'color:#c0392b;font-size:12px;margin-top:4px;';
    inputEl.parentNode.appendChild(err);
    inputEl.style.borderColor = '#c0392b';
  },

  clearFieldError(inputEl) {
    const existing = inputEl.parentNode.querySelector('.field-validation-error');
    if (existing) existing.remove();
    inputEl.style.borderColor = '';
  },

  clearAllErrors(container) {
    container.querySelectorAll('.field-validation-error').forEach(e => e.remove());
    container.querySelectorAll('input, select').forEach(el => el.style.borderColor = '');
  }
};

// Inject data year from premium-insights.json into .data-year / .data-year-prev spans
fetch('/premium-insights.json').then(r => r.json()).then(d => {
  if (d.data_year) document.querySelectorAll('.data-year').forEach(el => el.textContent = d.data_year);
  if (d.previous_year) document.querySelectorAll('.data-year-prev').forEach(el => el.textContent = d.previous_year);
}).catch(() => {});

// NAV
function toggleNav() {
  document.getElementById('nav-menu').classList.toggle('open');
  document.getElementById('nav-burger').classList.toggle('open');
}
function closeNav() {
  document.getElementById('nav-menu').classList.remove('open');
  document.getElementById('nav-burger').classList.remove('open');
}

// KK CALCULATOR
const KK_API = 'https://zexpmaegqsayleaohiip.supabase.co/functions/v1/get-cheapest-premiums';

// Auswahl "Deine Kasse". value = BAG-Nummer, wie insurer_id in der Antwort.
// Konzernmarken mit Zusatz, weil auf der Police oft die Tochter steht.
const KK_INSURERS = [
  [32,'Aquilana'],[1560,'Agrisano'],[1542,'Assura'],[312,'Atupri'],[343,'Avenir (Groupe Mutuel)'],
  [1322,'Birchmeier'],[290,'Concordia'],[8,'CSS'],[820,'curaulta'],[881,'EGK'],
  [134,'Einsiedler Krankenkasse'],[1386,'Galenos'],[780,'Glarner'],[1562,'Helsana'],
  [360,'KK Luzerner Hinterland'],[246,'KK Steffisburg'],[1040,'KK Visperterminen'],[1318,'KK Wädenswil'],
  [376,'KPT'],[1479,'Mutuel (Groupe Mutuel)'],[455,'ÖKK'],[1535,'Philos (Groupe Mutuel)'],
  [1401,'rhenusana'],[1568,'sana24 (Visana)'],[1509,'Sanitas'],[923,'SLKK'],[941,'sodalis'],
  [194,'Sumiswalder'],[1384,'Swica'],[1555,'Visana'],[966,'vita surselva'],[509,'Vivao Sympany']
];
(function initCurrentInsurer() {
  const sel = document.getElementById('kk-current');
  if (!sel) return;
  KK_INSURERS.forEach(([id, name]) => sel.add(new Option(name, id)));
  try { const saved = localStorage.getItem('kk-current'); if (saved) sel.value = saved; } catch (e) {}
  // Von den Kassenseiten: /?kasse=<BAG-Nummer>#kk-rechner
  const fromLink = new URLSearchParams(location.search).get('kasse');
  if (fromLink && [...sel.options].some(o => o.value === fromLink)) sel.value = fromLink;
  sel.addEventListener('change', () => { try { localStorage.setItem('kk-current', sel.value); } catch (e) {} });
  const groups = { 343: 'groupe mutuel', 1479: 'groupe mutuel', 1535: 'groupe mutuel', 1568: 'visana gruppe',
    1386: 'visana gruppe', 1555: 'visana gruppe', 509: 'sympany', 455: 'oekk okk', 1318: 'waedenswil' };
  Combobox.enhance(sel, { search: true, placeholder: t('searchInsurer'), keywords: v => groups[v] || '' });
  Combobox.enhance(document.getElementById('kk-franchise'));
  Combobox.enhance(document.getElementById('kk-accident'));
  const paid = document.getElementById('kk-paid');
  try { const v = localStorage.getItem('kk-paid'); if (v) paid.value = v; } catch (e) {}
  paid.addEventListener('change', () => { try { localStorage.setItem('kk-paid', paid.value); } catch (e) {} });
})();

// Rechnung oder Police hochladen: Gemini liest Kasse, Prämie, Franchise und
// Adresse (Edge Function read-invoice). Knopf erscheint nur, wenn der Dienst
// eingerichtet ist.
const INVOICE_API = SUPABASE_URL + '/functions/v1/read-invoice';
const WECKER_API = SUPABASE_URL + '/functions/v1/wecker';

(async function initWecker() {
  // Rückmeldung nach dem Klick auf den Link in der Mail
  const state = new URLSearchParams(location.search).get('wecker');
  const texts = { bestaetigt: t('weckerConfirmed'), abgemeldet: t('weckerUnsubscribed'), ungueltig: t('weckerInvalid') };
  if (texts[state]) {
    const b = document.createElement('div');
    b.className = 'wecker-banner'; b.textContent = texts[state];
    const calc = document.getElementById('kk-calc');
    calc.parentNode.insertBefore(b, calc);
  }
  try { window._weckerEnabled = (await (await fetch(WECKER_API)).json()).enabled; } catch (e) {}
  const form = document.getElementById('wecker-form');
  if (!form) return;
  form.addEventListener('submit', async ev => {
    ev.preventDefault();
    const msg = document.getElementById('wecker-msg');
    const say = (t, err) => { msg.textContent = t; msg.classList.toggle('err', !!err); };
    const v = id => document.getElementById(id).value;
    const btn = form.querySelector('button'); btn.disabled = true; say('');
    try {
      const res = await fetch(WECKER_API, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({
        email: v('wecker-email'), plz: v('kk-plz'), jahrgang: v('kk-year'), franchise: v('kk-franchise'),
        accident_included: v('kk-accident') === 'true', current_insurer_id: v('kk-current') || null,
        paid_monthly: parseFloat((v('kk-paid') || '').replace(',', '.')) || null, lang: LANG }) });
      const r = await res.json();
      if (!res.ok || r.error) throw new Error(serverMsg(r.error, 'weckerFailed'));
      say(r.already ? t('weckerAlready') : t('weckerCheckMail'));
      form.reset();
    } catch (e) { say(e.message, true); } finally { btn.disabled = false; }
  });
})();

function insurerIdFromName(name) {
  const n = (name || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
  // Wortgrenzen: «assura» steckt sonst in «Assurance», «css» in anderen Wörtern
  const rules = [
    [/sana24/, 1568], [/\bavenir\b/, 343], [/\bphilos\b/, 1535], [/\bmutuel (assurance|kranken)/, 1479],
    [/agrisano/, 1560], [/helsana/, 1562], [/sanitas/, 1509], [/swica/, 1384], [/visana/, 1555], [/galenos/, 1386],
    [/\bcss\b/, 8], [/concordia/, 290], [/\bkpt\b/, 376], [/atupri/, 312], [/\bassura\b/, 1542], [/\begk\b/, 881],
    [/\b(o|oe)kk\b/, 455], [/sympany|vivao/, 509], [/aquilana/, 32], [/\bslkk\b/, 923], [/sumiswald/, 194],
    [/steffisburg/, 246], [/einsiedl/, 134], [/luzerner hinterland/, 360], [/glarner/, 780], [/curaulta/, 820],
    [/sodalis/, 941], [/vita surselva/, 966], [/visperterminen/, 1040], [/wadenswil/, 1318], [/birchmeier/, 1322],
    [/rhenusana/, 1401],
  ];
  for (const [re, id] of rules) if (re.test(n)) return id;
  // «Groupe Mutuel» allein ist nicht eindeutig (Avenir, Mutuel, Philos)
  return null;
}

function fileToPayload(file) {
  return new Promise((resolve, reject) => {
    if (file.type === 'application/pdf') {
      if (file.size > 5 * 1024 * 1024) return reject(new Error(t('pdfTooBig')));
      const r = new FileReader();
      r.onload = () => resolve({ data: String(r.result).split(',')[1], media_type: 'application/pdf' });
      r.onerror = () => reject(new Error(t('fileUnreadable')));
      return r.readAsDataURL(file);
    }
    // Fotos im Browser verkleinern: schneller, günstiger, und kein Originalbild übertragen
    const img = new Image();
    img.onload = () => {
      const scale = Math.min(1, 1800 / Math.max(img.width, img.height));
      const c = document.createElement('canvas');
      c.width = Math.round(img.width * scale); c.height = Math.round(img.height * scale);
      c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
      URL.revokeObjectURL(img.src);
      resolve({ data: c.toDataURL('image/jpeg', 0.85).split(',')[1], media_type: 'image/jpeg' });
    };
    img.onerror = () => reject(new Error(t('imageUnreadable')));
    img.src = URL.createObjectURL(file);
  });
}

function applyInvoice(r) {
  const $ = id => document.getElementById(id);
  const notes = [];
  const id = insurerIdFromName(r.insurer);
  if (id) { $('kk-current').value = String(id); $('kk-current').dispatchEvent(new Event('change')); }
  else if (r.insurer) notes.push(t('pickInsurer', { insurer: r.insurer }));
  const persons = (r.persons || []).filter(p => p.basic_premium_monthly);
  const person = persons[0];
  if (person) {
    $('kk-paid').value = person.basic_premium_monthly.toFixed(2);
    $('kk-paid').dispatchEvent(new Event('change'));
    if (person.birth_year) $('kk-year').value = person.birth_year;
    if (persons.length > 1) notes.push(t('morePersons', { n: persons.length, name: person.name || t('firstPerson') }));
  }
  if (r.franchise && [...$('kk-franchise').options].some(o => o.value === String(r.franchise))) $('kk-franchise').value = String(r.franchise);
  if (r.accident_included !== null && r.accident_included !== undefined) $('kk-accident').value = String(r.accident_included);
  ['kk-franchise', 'kk-accident'].forEach(id => $(id).dispatchEvent(new Event('change')));
  if (r.postal_code && /^\d{4}$/.test(r.postal_code)) $('kk-plz').value = r.postal_code;
  // Für die Kündigung: nur in diesem Browserfenster merken
  const prefill = { name: r.policyholder_name || person?.name || '', street: r.street || '',
    city: [r.postal_code, r.city].filter(Boolean).join(' '), nr: r.insured_number || '', kasse: id };
  try { sessionStorage.setItem('kd-prefill', JSON.stringify(prefill)); } catch (e) {}
  return notes;
}

(async function initUpload() {
  const box = document.getElementById('kk-upload');
  if (!box) return;
  try {
    const res = await fetch(INVOICE_API);
    if (!(await res.json()).enabled) return;
  } catch (e) { return; }
  box.hidden = false;
  const btn = document.getElementById('kk-upload-btn'), input = document.getElementById('kk-upload-file');
  const status = document.getElementById('kk-upload-status');
  const say = (t, err) => { status.textContent = t; status.classList.toggle('err', !!err); };
  btn.onclick = () => input.click();
  input.onchange = async () => {
    const file = input.files[0];
    input.value = '';
    if (!file) return;
    btn.disabled = true; say(t('reading'));
    try {
      const payload = await fileToPayload(file);
      const res = await fetch(INVOICE_API, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      const r = await res.json();
      if (!res.ok || r.error) throw new Error(serverMsg(r.error, 'docUnreadable'));
      const notes = applyInvoice(r);
      const ready = document.getElementById('kk-plz').value && document.getElementById('kk-year').value;
      say(t('applied') + (notes.length ? notes.join('. ') + '. ' : '') + (ready ? '' : t('addPlzYear')));
      if (ready) checkKK();
      else document.getElementById(document.getElementById('kk-plz').value ? 'kk-year' : 'kk-plz').focus();
    } catch (e) {
      say(e.message, true);
    } finally {
      btn.disabled = false;
    }
  };
})();

// Kündigungs-Schnellstart: Kassenliste aus KK_INSURERS, durchsuchbar
(function () {
  const sel = document.getElementById('kd-quick-kasse');
  if (!sel) return;
  KK_INSURERS.slice().sort((x, y) => x[1].localeCompare(y[1], 'de')).forEach(([id, n]) => sel.add(new Option(n, id)));
  if (window.Combobox) Combobox.enhance(sel, { search: true, placeholder: t('searchInsurer') });
})();

// Preistreue-Rating je Region (scripts/build_rating.py). Lädt im Hintergrund,
// fehlt es, zeigt der Rechner einfach keine Abzeichen.
let RATING_DATA = null;
const ratingLoad = fetch(RATING_URL).then(r => r.ok ? r.json() : null)
  .then(d => { RATING_DATA = d; }).catch(() => {});

// Anonyme Ereignisse (Tabelle kk_events, siehe Datenschutz). Schlägt nie laut fehl.
const EREIGNIS_API = SUPABASE_URL + '/functions/v1/kk-ereignis';
function kkLog(event, fields) {
  try {
    fetch(EREIGNIS_API, { method: 'POST', keepalive: true, headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(Object.assign({ event }, fields)) }).catch(() => {});
  } catch (e) {}
}
const ageKey = a => /^Kind/.test(a || '') ? 'KIN' : /^Jung/.test(a || '') ? 'JUG' : 'ERW';
// Klick auf «Wechseln» in der Ergebnisliste
document.addEventListener('click', ev => {
  const a = ev.target.closest(`a[href*="${route('kuendigen')}"]`);
  if (!a || !a.closest('#kk-calc')) return;
  const q = new URL(a.href, location.href).searchParams;
  kkLog('wechsel_klick', Object.assign({}, window._kkLast || {}, {
    kasse_alt: parseInt(q.get('kasse')) || (window._kkLast || {}).kasse_alt || null,
    kasse_neu: parseInt(q.get('neu')) || null, quelle: 'rechner' }));
});

async function checkKK() {
  const plz = document.getElementById('kk-plz').value.trim();
  const year = document.getElementById('kk-year').value.trim();
  const franchise = document.getElementById('kk-franchise').value;
  const accidentIncluded = document.getElementById('kk-accident').value === 'true';

  if (!plz || !SwissValidation.isValidPLZ(plz)) { alert(t('badPlz')); return; }
  if (!year || year < 1930 || year > 2010) { alert(t('badYear')); return; }

  const resultEl = document.getElementById('kk-result');
  const listEl = document.getElementById('kk-results-list');
  const subEl = document.getElementById('kk-result-sub');
  const filtersEl = document.getElementById('kk-filters');

  // Show loading
  resultEl.style.display = 'block';
  subEl.textContent = t('loadingPremiums');
  listEl.innerHTML = '<div class="kk-loading"><div class="kk-loading-dots"><div class="kk-loading-dot"></div><div class="kk-loading-dot"></div><div class="kk-loading-dot"></div></div>' + t('searching') + '</div>';
  filtersEl.style.display = 'none';
  resultEl.scrollIntoView({ behavior: 'smooth', block: 'center' });

  try {
    const res = await fetch(KK_API, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ plz, year_of_birth: year, franchise, accident_included: accidentIncluded,
        current_insurer_id: parseInt(document.getElementById('kk-current').value) || null })
    });

    const data = await res.json();
    await ratingLoad;

    if (data.error) {
      subEl.textContent = serverMsg(data.error, 'loadError');
      listEl.innerHTML = '';
      return;
    }

    if (data.year) document.querySelectorAll('.calc-year').forEach(el => el.textContent = data.year);
    subEl.textContent = t('subline', { locality: data.locality, canton: data.canton,
      age: LANG === 'de' ? data.age_class : t('age_' + ageKey(data.age_class)),
      franchise: data.franchise.toLocaleString('de-CH'), accident: accidentIncluded ? t('withAccident') : t('withoutAccident') });

    // Insurer website mapping
    // Schlüssel = premiums.insurer_name. Websites laut BAG-Verzeichnis der
    // zugelassenen Krankenversicherer (1.1.2026).
    const insurerUrls = {
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
      'Vivao Sympany': 'https://www.sympany.ch'
    };

    function affiliateLink(insurerName) {
      const base = insurerUrls[insurerName];
      if (!base) return null;
      return base + '?utm_source=abovergleich.com&utm_medium=affiliate&utm_campaign=kk-vergleich';
    }

    const arrowSvg = '<svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 6h8M7 3l3 3-3 3"/></svg>';

    const modelExplain = {
      'standard': t('tip_standard'),
      'hmo': t('tip_hmo'),
      'hausarzt': t('tip_family_doctor'),
      'family_doctor': t('tip_family_doctor'),
      'telmed': t('tip_telmed'),
      'apotheke': t('tip_apotheke'),
      'diverse': t('tip_diverse'),
    };

    function modelTip(modelType) {
      const key = (modelType || '').toLowerCase();
      const text = modelExplain[key];
      if (!text) return '';
      return ` <span class="kk-model-tip" data-tip aria-label="Info">i<span class="tip-text">${text}</span></span>`;
    }

    const modelNames = { hmo: t('model_hmo'), telmed: t('model_telmed'), family_doctor: t('model_family_doctor'), standard: t('model_standard'),
      diverse: t('model_diverse'), apotheke: t('model_apotheke') };
    const fmt = v => v.toLocaleString('de-CH', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const fmt0 = v => Math.round(v).toLocaleString('de-CH');
    const tariffLabel = p => p.model_type === 'standard' ? t('standardFree') : `${modelNames[p.model_type] || p.model_type} · ${p.tariff_name}`;
    const signed = (v, d = 1) => `${v >= 0 ? '+' : '−'}${decSep(Math.abs(v).toFixed(d), ['fr'])}`;
    const changeText = p => p.premium_prev
      ? t('changeVs', { change: signed((p.premium / p.premium_prev - 1) * 100), prev: data.prev_year })
      : t('newTariff');

    const offers = data.offers || [];
    const currentSelect = document.getElementById('kk-current');
    const currentId = parseInt(currentSelect.value) || null;
    const ownOffers = currentId ? offers.filter(p => p.insurer_id === currentId) : [];
    // Vorauswahl Standardmodell: wer sein Modell nicht kennt, hat meist dieses
    let ownPick = ownOffers.find(p => p.model_type === 'standard') || ownOffers[ownOffers.length - 1] || null;
    let ownGuessed = true;       // Tarif nur angenommen, nicht erkannt
    let ownChoices = ownOffers;  // Tarife, die in der Auswahl stehen
    let matchNote = '';
    let matchOther = null;       // Treffer bei anderer Franchise/Unfalldeckung
    let matchNone = false;       // Hinweis «kein Tarif kostete genau …» (früher: matchNote.startsWith('Kein Tarif'))

    // Rechnungsbetrag -> Tarif. Die Kassen ziehen die Umweltabgabe direkt ab,
    // auf der Rechnung steht also BAG-Prämie minus Rückverteilung.
    const refund = data.env_refund || 0, refundPrev = data.env_refund_prev || 0;
    const paid = parseFloat((document.getElementById('kk-paid').value || '').replace(/[^0-9.,]/g, '').replace(',', '.')) || null;
    if (currentId && paid) {
      const near = (a, b) => Math.abs(a - b) < 0.06;
      const matches = (data.current_options || []).filter(p => p.premium_prev
        && (near(p.premium_prev - refundPrev, paid) || near(p.premium_prev, paid)));
      const here = matches.filter(p => p.franchise === data.franchise && p.accident_included === data.accident_included);
      const hereTariffs = new Set(here.map(p => p.tariff));
      const found = ownOffers.filter(p => hereTariffs.has(p.tariff));
      if (found.length) {
        ownPick = found[0];
        ownGuessed = false;
        if (found.length > 1) {
          ownChoices = found;
          matchNote = t('matchSeveral', { n: found.length, prev: data.prev_year });
        } else {
          matchNote = t('matchOne');
        }
      } else if (!matches.length && (() => {
        // Kein exakter Treffer (gerundet, Rabatt, Monat mit Nachzahlung): nimm den
        // Tarif deiner Kasse, dessen Rechnung ${data.prev_year} am nächsten lag
        const opts = (data.current_options || []).filter(p => p.premium_prev
          && p.franchise === data.franchise && p.accident_included === data.accident_included);
        let bestOpt = null, bestGap = Infinity;
        for (const p of opts) {
          const gap = Math.abs(p.premium_prev - refundPrev - paid);
          if (gap < bestGap && ownOffers.some(o => o.tariff === p.tariff)) { bestGap = gap; bestOpt = p; }
        }
        if (!bestOpt || bestGap > paid * 0.1) return false;
        ownPick = ownOffers.find(o => o.tariff === bestOpt.tariff);
        ownGuessed = false;
        matchNote = t('matchNearest', { paid: fmt(paid), tariff: tariffLabel(bestOpt), prev: data.prev_year, price: fmt(bestOpt.premium_prev - refundPrev) });
        matchNone = true;
        return true;
      })()) {
        // naheliegender Tarif gewählt
      } else if (matches.length) {
        matchOther = matches[0];
        matchNote = t(matchOther.accident_included ? 'matchOtherAcc' : 'matchOtherNoAcc', { franchise: fmt0(matchOther.franchise), tariff: tariffLabel(matchOther) });
      } else {
        matchNote = t('matchNone', { prev: data.prev_year, paid: fmt(paid) });
        matchNone = true;
      }
    }

    // Statistik ohne Namen, siehe Datenschutz 3.1. Profil merken, damit der
    // Kündigungs-Editor den Wecker mit derselben Franchise einschalten kann.
    try { localStorage.setItem('kk-profile', JSON.stringify({ plz: parseInt(plz), year: parseInt(year), franchise: Number(data.franchise), accident: accidentIncluded })); } catch (e) {}
    if (offers[0]) kkLog('vergleich', {
      plz: parseInt(plz), jahrgang: parseInt(year),
      jahr: data.year, canton: data.canton, region: data.region, altersklasse: ageKey(data.age_class),
      franchise: Number(data.franchise), unfall: accidentIncluded, kasse_alt: currentId,
      kasse_neu: offers[0].insurer_id, modell_neu: offers[0].model_type, praemie_bezahlt: paid,
      ersparnis_jahr: ownPick && !ownGuessed ? (ownPick.premium - offers[0].premium) * 12 : null, quelle: 'rechner',
    });
    window._kkLast = { plz: parseInt(plz), jahrgang: parseInt(year), jahr: data.year, canton: data.canton, region: data.region, altersklasse: ageKey(data.age_class),
      franchise: Number(data.franchise), unfall: accidentIncluded, kasse_alt: currentId };

    function bestPerInsurer(list) {
      const seen = new Set();
      return list.filter(p => !seen.has(p.insurer_id) && seen.add(p.insurer_id));
    }

    function renderOwn() {
      const el = document.getElementById('kk-own');
      if (!currentId) { el.innerHTML = ''; return; }
      if (!ownPick) {
        el.innerHTML = `<div class="kk-own"><div class="kk-own-label">${t('yourInsurer')}</div><div class="kk-own-title">${currentSelect.selectedOptions[0].textContent}</div>
          <div class="kk-own-delta">${t('notOffered')}</div>
          ${matchNote ? `<div class="kk-own-match">${matchNote}</div>` : ''}</div>`;
        bindMatch(el);
        return;
      }
      const best = offers[0];
      const saveAll = (ownPick.premium - best.premium) * 12;
      // Was auf der Rechnung steht: BAG-Prämie minus Umweltabgabe des Jahres
      const bill = ownPick.premium - refund;
      const billPrev = ownPick.premium_prev ? ownPick.premium_prev - refundPrev : null;
      const facts = [];
      if (refund) facts.push(t('billYear', { year: data.year, amount: fmt(bill) }));
      facts.push(billPrev
        ? t('prevBill', { prev: data.prev_year, amount: fmt(billPrev), cls: bill >= billPrev ? 'kk-more' : 'kk-save',
            sign: bill >= billPrev ? '+' : '−', diff: fmt0(Math.abs(bill - billPrev) * 12) })
        : t('tariffNew', { year: data.year }));
      const picked = !ownGuessed && ownChoices.length === 1 && paid ? t('fromBill') : '';
      const hint = matchOther || (!ownGuessed ? '' : t('assumeStandard'));
      const noMatch = matchNone ? matchNote : '';
      const save = saveAll < 12
        ? t('alreadyCheapest')
        : t(ownGuessed ? 'saveGuessed' : 'saveKnown', { amount: fmt0(saveAll), insurer: best.insurer_name,
            href: `${route('kuendigen')}?kasse=${currentId}&neu=${best.insurer_id}#wechsel` });
      const tariffs = ownChoices.map((p, i) => `<div class="kk-own-tariff${p === ownPick ? ' selected' : ''}" data-i="${i}">
          <span>${tariffLabel(p)}</span><span>CHF ${fmt(p.premium)}</span></div>`).join('');
      const narrowed = ownChoices.length < ownOffers.length;
      const pickerLabel = narrowed ? t('pickerNarrowed', { n: ownChoices.length }) : t('pickerAll');
      el.innerHTML = `<div class="kk-own">
        <div class="kk-own-head">
          <div><div class="kk-own-label">${t('yourInsurerYear', { year: data.year })}</div><div class="kk-own-title">${ownPick.insurer_name}</div><div class="kk-own-delta">${tariffLabel(ownPick)}${picked}</div></div>
          <div class="kk-own-price">CHF ${fmt(ownPick.premium)}</div>
        </div>
        <div class="kk-own-facts">${facts.join(' · ')}</div>
        ${matchOther ? `<div class="kk-own-match">${matchNote}</div>` : noMatch ? `<div class="kk-own-match">${noMatch}</div>` : hint ? `<div class="kk-own-match">${hint}</div>` : ''}
        <div class="kk-own-save">${save}</div>
        ${ownChoices.length > 1 ? `<details class="kk-own-tariffs"${ownGuessed || narrowed ? ' open' : ''}><summary>${pickerLabel}</summary>${tariffs}</details>` : ''}
      </div>`;
      el.querySelectorAll('.kk-own-tariff').forEach(t => t.onclick = () => {
        ownPick = ownChoices[parseInt(t.dataset.i)];
        ownGuessed = false;
        renderOwn();
        const d = el.querySelector('.kk-own-tariffs'); if (d) d.open = true;
        renderFiltered(document.querySelector('.kk-filter-chip.active').dataset.filter);
      });
      bindMatch(el);
    }

    // "Damit rechnen": Franchise und Unfalldeckung aus dem Rechnungstreffer übernehmen
    function bindMatch(el) {
      const btn = el.querySelector('#kk-apply-match');
      if (!btn || !matchOther) return;
      btn.onclick = () => {
        document.getElementById('kk-franchise').value = String(matchOther.franchise);
        document.getElementById('kk-accident').value = String(matchOther.accident_included);
        ['kk-franchise', 'kk-accident'].forEach(id => document.getElementById(id).dispatchEvent(new Event('change')));
        checkKK();
      };
    }

    // Abzeichen je Angebot: Note der Kasse in dieser Region, «dauerhaft günstig»
    // (in mindestens 60 % der Jahre seit 2020 unter den 5 günstigsten, bei
    // dieser Franchise) und ein Hinweis, wenn es den Tarif erst kurz gibt.
    function ratingChips(p) {
      const R = RATING_DATA;
      if (!R) return '';
      const chips = [];
      const v = (R.regionen[`${data.canton}|${data.region}`] || {})[p.insurer_id];
      if (v && v[0] != null) {
        // Note für die eigene Situation: mit/ohne Unfall, Franchise bis 1'000 wie 300, ab 1'500 wie 2'500
        const acc = !!accidentIncluded, f25 = Number(data.franchise) >= 1500;
        const own = v[3] ? v[3][(acc ? 0 : 2) + (f25 ? 1 : 0)] : null;
        const shown = own != null ? own : v[0];
        const fmtN = x => decSep(x.toFixed(1), ['de', 'fr']);
        const sit = t(acc ? 'sitAcc' : 'sitNoAcc', { f: f25 ? "2'500" : '300' });
        chips.push(`<a class="kk-chip kk-chip-note" href="${route('rating')}">${t('chipNote', { note: fmtN(shown) })}</a>` +
          (own != null ? `<span class="kk-model-tip" data-tip aria-label="Info">i<span class="tip-text">${t('chipNoteTip', { sit, total: fmtN(v[0]) })}</span></span>` : ''));
        const yrs = (acc ? v[1] : (v[2] || v[1]))[R.franchisen.indexOf(Number(data.franchise))];
        if (yrs && yrs[1] >= 5 && yrs[0] / yrs[1] >= 0.6) {
          chips.push(`<span class="kk-chip kk-chip-good">${t('chipCheap')} <span class="kk-model-tip" data-tip aria-label="Info">i<span class="tip-text">${t('chipCheapTip', { a: yrs[0], b: yrs[1], from: R.von, top: R.top })}</span></span></span>`);
        }
      }
      const since = (R.seit[p.insurer_id] || {})[String(p.tariff || '').toLowerCase()];
      if (since && p.model_type !== 'standard') {
        chips.push(`<span class="kk-chip kk-chip-new">${t('chipSince', { since })} <span class="kk-model-tip" data-tip aria-label="Info">i<span class="tip-text">${t('chipSinceTip', { since })}</span></span></span>`);
      }
      return chips.length ? `<div class="kk-chips">${chips.join('')}</div>` : '';
    }

    // Kassenname: bei einer anderen Kasse führt er in den Wechsel-Ablauf
    // (kündigen, dann anmelden), wie der Knopf «Wechseln». Wer die Analyse
    // will (Rating, Verlauf, Reserven), nimmt den kleinen Link daneben.
    function kasseName(p, flow) {
      const slug = RATING_DATA && RATING_DATA.slug && RATING_DATA.slug[p.insurer_id];
      const analysis = slug ? `${route('kassen')}${slug}/` : null;
      if (flow) {
        return `<a class="kk-insurer-link" href="${flow}" title="${t('switchTitle', { insurer: p.insurer_name })}">${p.insurer_name} <span aria-hidden="true">›</span></a>`
          + (analysis ? `<a class="kk-analysis" href="${analysis}" title="${t('fullAnalysis', { insurer: p.insurer_name })}">${t('analysis')}</a>` : '');
      }
      return analysis ? `<a class="kk-insurer-link" href="${analysis}" title="${t('fullAnalysis', { insurer: p.insurer_name })}">${p.insurer_name} <span aria-hidden="true">›</span></a>` : p.insurer_name;
    }

    function renderRow(p, rank, opts = {}) {
      const isOwn = currentId && p.insurer_id === currentId;
      // Andere Kasse: «Wechseln» führt in den Ablauf auf der Kündigungsseite
      // (erst bei der neuen Kasse anmelden, dann die alte kündigen). Eigene
      // Kasse, anderes Modell: das ändert man bei der Kasse selbst, ohne Kündigung.
      let cta = '', flow = null;
      if (!isOwn) {
        const q = new URLSearchParams();
        if (currentId) q.set('kasse', currentId);
        q.set('neu', p.insurer_id);
        flow = `${route('kuendigen')}?${q}#wechsel`;
        cta = `<a href="${flow}" class="kk-link">${t('switchTo')} ${arrowSvg}</a>`;
      } else if (p !== ownPick) {
        const link = affiliateLink(p.insurer_name);
        if (link) cta = `<a href="${link}" target="_blank" rel="noopener sponsored" class="kk-link">${t('changeModel')} ${arrowSvg}</a>`;
      }
      let meta = changeText(p);
      // Ersparnis nur gegen einen Tarif, den wir kennen, nie gegen eine Annahme
      if (ownPick && !ownGuessed && p !== ownPick) {
        // auch in der eigenen Kasse: ein anderes Modell kann schon viel sparen
        const diff = (ownPick.premium - p.premium) * 12;
        meta = diff >= 1
          ? `<span class="kk-save">${t('cheaperYear', { amount: fmt0(diff) })}</span>`
          : `<span class="kk-more">${t('dearerYear', { amount: fmt0(-diff) })}</span>`;
      }
      return `<div class="kk-row${opts.best ? ' kk-row-best' : ''}${isOwn ? ' kk-row-own' : ''}">
        <div class="kk-row-left">
          <div class="kk-rank">${rank}</div>
          <div>
            <div class="kk-insurer">${kasseName(p, flow)}${isOwn ? `<span class="kk-tag">${t('yourInsurerTag')}</span>` : ''}</div>
            <div class="kk-model">${tariffLabel(p)}${modelTip(p.model_type)}</div>
            ${ratingChips(p)}
          </div>
        </div>
        <div class="kk-price-cta">
          <div style="text-align:right;">
            <div class="kk-price">CHF ${fmt(p.premium)}</div>
            <div class="kk-row-meta">${meta}</div>
          </div>
          ${cta}
        </div>
      </div>`;
    }

    let expanded = false;
    // Junge Erwachsene: Ab dem Jahr, in dem sie 26 werden, gilt die
    // Erwachsenenprämie (nach Geburtsjahr, Art. 91 KVV). Kein zweiter Preis
    // im Rechner, nur der Hinweis, dann neu zu vergleichen.
    function hint26() {
      if (!/^Junge/.test(data.age_class || '')) return '';
      const born = parseInt(document.getElementById('kk-year').value);
      const from = born + 26;
      const soon = from === data.year + 1;
      return `<div class="kk-hint26${soon ? ' soon' : ''}"><strong>${soon ? t('adultFrom', { year: from }) : t('at26')}</strong> `
        + t('rise26')
        + `${soon ? t('compareAutumn', { year: data.year }) : t('compareBefore26')} `
        + `<a href="${route('blog26')}">${t('moreAbout')}</a></div>`;
    }

    function renderFiltered(filter) {
      const pool = filter === 'alle' ? offers : offers.filter(p => p.model_type === filter);
      const ranked = bestPerInsurer(pool);
      if (ranked.length === 0) {
        listEl.innerHTML = '<div style="color:var(--muted);font-size:14px;">' + t('noneForModel') + '</div>';
        return;
      }
      const top = ranked.slice(0, expanded ? 10 : 3);
      let html = top.map((p, i) => renderRow(p, i + 1, { best: i === 0 })).join('');
      const ownIdx = currentId ? ranked.findIndex(p => p.insurer_id === currentId) : -1;
      if (ownIdx >= top.length) {
        html += '<div class="kk-gap">···</div>' + renderRow(ranked[ownIdx], ownIdx + 1);
      }
      if (ranked.length > 3) {
        html += `<button type="button" class="kk-more-btn" id="kk-more-btn">${expanded ? t('showLess') : t('showMore', { n: Math.min(ranked.length, 10) - 3 })}</button>`;
      }
      html += hint26();
      html += `<div class="kk-list-note">${t('listNote')} <span class="kk-model-tip" data-tip aria-label="Info">i<span class="tip-text">${t('listNoteTip', { year: data.year, refund: fmt(refund) })}</span></span></div>`;
      listEl.innerHTML = html;
      const more = document.getElementById('kk-more-btn');
      if (more) more.onclick = () => { expanded = !expanded; renderFiltered(filter); };
    }

    renderOwn();

    // Setup filter chips
    filtersEl.style.display = '';
    const chips = filtersEl.querySelectorAll('.kk-filter-chip');
    chips.forEach(chip => {
      chip.onclick = () => {
        chips.forEach(c => c.classList.remove('active'));
        chip.classList.add('active');
        expanded = false;
        renderFiltered(chip.dataset.filter);
      };
    });
    // Reset to "Alle" active
    chips.forEach(c => c.classList.remove('active'));
    chips[0].classList.add('active');

    // Initial render
    renderFiltered('alle');

    // Wechsel-Wecker nur zeigen, wenn der Versand eingerichtet ist
    const weckerCta = document.getElementById('wecker-cta');
    if (weckerCta && window._weckerEnabled) weckerCta.style.display = '';
  } catch (err) {
    subEl.textContent = t('loadError');
    listEl.innerHTML = '';
  }
}
