-- abovergleich: anonyme Ereignisse aus Rechner und Kündigungs-Editor.
-- Angewendet am 01.10.2026 auf zexpmaegqsayleaohiip. Insert nur über die
-- Edge Function kk-ereignis (Service Role); anon/authenticated haben keine Rechte.
create table if not exists public.kk_events (
  id bigint generated always as identity primary key,
  created_at timestamptz not null default now(),
  event text not null check (event in ('vergleich','wechsel_klick','kuendigung_pdf','kuendigung_mail','kuendigung_text')),
  jahr int check (jahr between 2025 and 2040),
  canton text check (char_length(canton) <= 2),
  region text check (char_length(region) <= 12),
  altersklasse text check (altersklasse in ('KIN','JUG','ERW')),
  franchise int check (franchise in (0,100,200,300,400,500,600,1000,1500,2000,2500)),
  unfall boolean,
  kasse_alt int,
  kasse_neu int,
  modell_neu text check (char_length(modell_neu) <= 20),
  praemie_bezahlt int check (praemie_bezahlt between 0 and 3000),
  ersparnis_jahr int check (ersparnis_jahr between -20000 and 20000),
  zusatz text check (zusatz in ('keine','behalten','kuendigen')),
  kanal text check (char_length(kanal) <= 12),
  quelle text check (char_length(quelle) <= 40)
);
create index if not exists kk_events_created_idx on public.kk_events (created_at);
create index if not exists kk_events_event_idx on public.kk_events (event, created_at);
alter table public.kk_events enable row level security;
revoke all on public.kk_events from anon, authenticated;
