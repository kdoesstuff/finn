-- 0003 Pull: analyses of a company built offline from its own documents (task E5, E6).
--
-- One row per company and kind: the promise ledger, the business snapshot, bull and bear. Every
-- claim in `payload` carries the quote it rests on and the page of the document it came from; the
-- job that writes them drops any claim whose quote is not found in its source. `sources` lists the
-- documents read. Public market data like filings and results: written by ingest, read by the API,
-- no investor link.

set search_path = finn, extensions, public;

create table finn.analyses (
  symbol          text not null check (symbol ~ '^[A-Z0-9&-]{1,20}$'),
  kind            text not null check (kind in ('ledger', 'snapshot', 'bull_bear')),
  payload         jsonb not null check (jsonb_typeof(payload) = 'object'),
  sources         jsonb not null default '[]' check (jsonb_typeof(sources) = 'array'),
  model           text not null default '',
  prompt_version  text not null default '',
  generated_at    timestamptz not null default now(),
  primary key (symbol, kind)
);

alter table finn.analyses enable row level security;
revoke all on finn.analyses from public;
grant select, insert, update, delete on finn.analyses to finn_ingest;
grant select on finn.analyses to finn_api;
create policy ingest_rows on finn.analyses for all to finn_ingest using (true) with check (true);
create policy api_rows on finn.analyses for select to finn_api using (true);

call finn.lockdown();
