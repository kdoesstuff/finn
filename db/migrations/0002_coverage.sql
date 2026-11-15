-- 0002 Coverage: which companies FINN keeps deep data on (results, documents, prices history).
--
-- Ingest never reads investor tables, so it cannot learn from holdings which companies to follow.
-- Coverage is the public half of that fact: a symbol and why it is covered, with no link to any
-- investor. The API adds a symbol when an investor holds or researches it; ingest reads the list.
--
-- Also adds finn.lockdown(), which every migration from here on calls last: it revokes anything
-- Supabase's API roles may have been granted on objects in schema finn (for example through
-- default privileges), so a new table can never be readable through the REST API by accident.

set search_path = finn, extensions, public;

create table finn.coverage (
  symbol    text primary key check (symbol ~ '^[A-Z0-9&-]{1,20}$'),
  reason    text not null check (reason in ('holding', 'research', 'requested')),
  added_at  timestamptz not null default now()
);

alter table finn.coverage enable row level security;
revoke all on finn.coverage from public;
grant select on finn.coverage to finn_ingest;
grant select, insert, update on finn.coverage to finn_api;
create policy ingest_rows on finn.coverage for select to finn_ingest using (true);
create policy api_rows on finn.coverage for all to finn_api using (true) with check (true);

create procedure finn.lockdown()
language plpgsql
as $$
declare r text;
begin
  foreach r in array array['anon', 'authenticated', 'service_role'] loop
    if exists (select from pg_roles where rolname = r) then
      execute format('revoke all on schema finn from %I', r);
      execute format('revoke all on all tables in schema finn from %I', r);
      execute format('revoke all on all sequences in schema finn from %I', r);
      execute format('revoke all on all functions in schema finn from %I', r);
      execute format('revoke all on all procedures in schema finn from %I', r);
    end if;
  end loop;
end
$$;
revoke all on procedure finn.lockdown() from public;

call finn.lockdown();
