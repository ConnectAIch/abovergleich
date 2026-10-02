-- Sprache (de, fr, en) für Kündigungs-PDFs und Wechsel-Wecker: Mails,
-- Erinnerungen und Jahresmail gehen in der Sprache der Seite raus.
alter table public.kk_kuendigung_pdf add column if not exists lang text not null default 'de' check (lang in ('de','fr','en'));
alter table public.kk_wecker add column if not exists lang text not null default 'de' check (lang in ('de','fr','en'));
comment on column public.kk_kuendigung_pdf.lang is 'Sprache der Seite, auf der der Brief erstellt wurde: Mails und Erinnerungen in dieser Sprache';
comment on column public.kk_wecker.lang is 'Sprache der Anmeldung: Bestätigung und Jahresmail in dieser Sprache';
