-- 0005 Filing notes: what a filing says, read from its own attachment (tasks C3, D2).
--
-- One row per filing: a one-line "what changed" with the exact sentence it rests on, and for a
-- management change the incoming or outgoing person's background as the filing itself states it
-- (SEBI requires a brief profile of an appointed director or key managerial person). Every
-- sentence carries a quote that was found in the filing's text; the job that writes these stores
-- nothing when nothing could be checked. Public market data like the filings themselves: written by
-- ingest, read by the API, no investor link.

set search_path = finn, extensions, public;

create table finn.filing_notes (
  seq_id          text primary key references finn.filings (seq_id) on delete cascade,
  kind            text not null check (kind in ('summary', 'person')),
  summary         text check (summary is null or length(summary) between 1 and 400),
  quote           text check (quote is null or length(quote) between 1 and 1000),
  page            integer check (page is null or page >= 1),
  person          jsonb check (person is null or jsonb_typeof(person) = 'object'),
  model           text not null default '',
  prompt_version  text not null default '',
  generated_at    timestamptz not null default now(),
  check (summary is not null or person is not null)
);

alter table finn.filing_notes enable row level security;
revoke all on finn.filing_notes from public;
grant select, insert, update, delete on finn.filing_notes to finn_ingest;
grant select on finn.filing_notes to finn_api;
create policy ingest_rows on finn.filing_notes for all to finn_ingest using (true) with check (true);
create policy api_rows on finn.filing_notes for select to finn_api using (true);

call finn.lockdown();
