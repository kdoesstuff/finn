-- 0004 Network: the investor's own contacts (Founding brief only; served only to `full` sessions).
--
-- Every row belongs to one investor and is visible only inside that investor's scope
-- (finn.current_investor(), set per transaction by the API). The API role may only read: the demo
-- investor is read-only, and its synthetic network is loaded by the admin (`ingest.py
-- seed-network`). The ingest role gets nothing here: it never sees investor data. Deleting the
-- investor deletes the whole network (on delete cascade).
--
-- People are keyed per investor: the same person in two investors' networks is two rows, so one
-- investor's network can never reveal another's. `degree` is 0 for the investor's own profile
-- (id 'me'), 1 for a direct contact, 2 for someone a contact knows. Network data never goes to a
-- model (finn.llm is not imported by finn.network; a test checks it).

set search_path = finn, extensions, public;

create table finn.network_people (
  investor_id  uuid not null references finn.investors (id) on delete cascade,
  id           text not null check (id ~ '^(me|p[0-9]{3})$'),
  first_name   text not null check (length(first_name) between 1 and 80),
  last_name    text not null check (length(last_name) between 1 and 80),
  headline     text not null default '' check (length(headline) <= 200),
  location     text not null default '' check (length(location) <= 80),
  degree       smallint not null check (degree in (0, 1, 2)),
  synthetic    boolean not null default true,
  primary key (investor_id, id)
);

create table finn.network_roles (
  investor_id  uuid not null,
  person_id    text not null,
  ord          smallint not null check (ord >= 0),
  org          text not null check (length(org) between 1 and 120),
  symbol       text check (symbol is null or symbol ~ '^[A-Z0-9&-]{1,20}$'),
  sector       text not null default '',
  function     text not null default '',
  title        text not null check (length(title) between 1 and 120),
  started      date not null,
  ended        date check (ended is null or ended >= started),
  primary key (investor_id, person_id, ord),
  foreign key (investor_id, person_id) references finn.network_people (investor_id, id) on delete cascade
);
create index network_roles_symbol on finn.network_roles (investor_id, symbol);

create table finn.network_schools (
  investor_id  uuid not null,
  person_id    text not null,
  ord          smallint not null check (ord >= 0),
  school       text not null check (length(school) between 1 and 120),
  degree       text not null default '',
  year         smallint check (year between 1950 and 2100),
  primary key (investor_id, person_id, ord),
  foreign key (investor_id, person_id) references finn.network_people (investor_id, id) on delete cascade
);

-- A connection: from the investor ('me') to a contact, or from a contact to someone they know.
create table finn.network_edges (
  investor_id   uuid not null,
  from_id       text not null,
  to_id         text not null,
  kind          text not null check (kind in ('worked_together', 'classmate', 'conference', 'former_client',
                                              'introduced')),
  strength      smallint not null check (strength between 1 and 5),
  since         date not null,
  last_contact  date,
  context       text not null default '' check (length(context) <= 200),
  primary key (investor_id, from_id, to_id),
  foreign key (investor_id, from_id) references finn.network_people (investor_id, id) on delete cascade,
  foreign key (investor_id, to_id) references finn.network_people (investor_id, id) on delete cascade,
  check (from_id <> to_id)
);

alter table finn.network_people enable row level security;
alter table finn.network_roles enable row level security;
alter table finn.network_schools enable row level security;
alter table finn.network_edges enable row level security;

revoke all on finn.network_people, finn.network_roles, finn.network_schools, finn.network_edges from public;
grant select on finn.network_people, finn.network_roles, finn.network_schools, finn.network_edges to finn_api;

create policy own_rows on finn.network_people for select to finn_api using (investor_id = finn.current_investor());
create policy own_rows on finn.network_roles for select to finn_api using (investor_id = finn.current_investor());
create policy own_rows on finn.network_schools for select to finn_api using (investor_id = finn.current_investor());
create policy own_rows on finn.network_edges for select to finn_api using (investor_id = finn.current_investor());

call finn.lockdown();
