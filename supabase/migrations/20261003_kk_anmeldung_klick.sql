-- abovergleich: Klick auf «Zu <neue Kasse>» als eigenes Ereignis, plus
-- Trichter-Sicht. Angewendet am 03.10.2026 auf zexpmaegqsayleaohiip.
alter table public.kk_events drop constraint kk_events_event_check;
alter table public.kk_events add constraint kk_events_event_check
  check (event in ('vergleich','wechsel_klick','kuendigung_pdf','kuendigung_mail','kuendigung_text','anmeldung_klick'));

-- Trichter je Woche: Ereignisse plus Selbstauskunft aus den Erinnerungen.
-- Nur für Service Role (kein Zugriff für anon/authenticated).
create or replace view public.kk_trichter with (security_invoker = true) as
  select date_trunc('week', created_at)::date as woche, event as schritt, count(*) as n
    from public.kk_events group by 1, 2
  union all
  select date_trunc('week', created_at)::date, 'angemeldet_ja', count(*) filter (where angemeldet)
    from public.kk_kuendigung_pdf group by 1
  union all
  select date_trunc('week', created_at)::date, 'bestaetigt_ja', count(*) filter (where bestaetigt)
    from public.kk_kuendigung_pdf group by 1;
revoke all on public.kk_trichter from anon, authenticated;
