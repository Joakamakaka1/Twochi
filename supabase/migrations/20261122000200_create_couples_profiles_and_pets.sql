-- Core game tables (Datos y vectores, «Tablas del núcleo»). Every table follows the
-- template: couple_id, read policy by couple, restrictive aal2 policy, created_at and the
-- index of the policy column. None holds private content, so none needs a per-person policy.
-- Only reads are granted here; the engine's writes arrive with the care actions.

create table app.couples (
  id         uuid primary key default gen_random_uuid(),
  timezone   text not null default 'Europe/Madrid',
  created_at timestamptz not null default now()
);

create table app.profiles (
  user_id           uuid primary key references auth.users on delete cascade,
  couple_id         uuid not null references app.couples,
  display_name      text not null check (length(display_name) between 1 and 60),
  quiet_hours_start time not null default '23:00',
  quiet_hours_end   time not null default '08:00',
  created_at        timestamptz not null default now(),
  unique (couple_id, user_id)
);

create table app.pets (
  id                uuid primary key default gen_random_uuid(),
  couple_id         uuid not null references app.couples,
  represents_user_id uuid not null,
  caretaker_user_id uuid not null,
  name              text not null check (length(name) between 1 and 40),
  model_key         text not null check (model_key ~ '^[a-z0-9_-]{1,40}$'),
  level             integer not null default 1 check (level >= 1),
  xp                integer not null default 0 check (xp >= 0),
  asleep            boolean not null default false,
  sick_since        timestamptz,
  created_at        timestamptz not null default now(),
  unique (couple_id, id),
  -- One pet per represented person, cared for by the other person of the same couple.
  unique (represents_user_id),
  check (represents_user_id <> caretaker_user_id),
  foreign key (couple_id, represents_user_id) references app.profiles (couple_id, user_id),
  foreign key (couple_id, caretaker_user_id) references app.profiles (couple_id, user_id)
);

-- The last stored value of each need; the current value is computed on read.
create table app.pet_needs (
  pet_id     uuid not null,
  couple_id  uuid not null,
  need       text not null
             check (need in ('hunger', 'energy', 'hygiene', 'fun', 'affection')),
  value      double precision not null check (value between 0 and 100),
  updated_at timestamptz not null,
  created_at timestamptz not null default now(),
  primary key (pet_id, need),
  foreign key (couple_id, pet_id) references app.pets (couple_id, id)
);

-- Immutable record of what happens to a pet: never updated, never deleted.
create table app.pet_events (
  id              bigint generated always as identity primary key,
  couple_id       uuid not null,
  pet_id          uuid not null,
  actor_user_id   uuid references app.profiles,
  source          text not null check (source in ('ui', 'chat', 'system')),
  action          text not null,
  payload         jsonb not null default '{}',
  deltas          jsonb not null default '{}',
  rules_version   text not null,
  idempotency_key text not null unique,
  created_at      timestamptz not null default now(),
  foreign key (couple_id, pet_id) references app.pets (couple_id, id)
);

create index profiles_couple on app.profiles (couple_id);
create index pets_couple on app.pets (couple_id);
create index pets_caretaker on app.pets (caretaker_user_id);
create index pet_needs_couple on app.pet_needs (couple_id);
create index pet_events_couple_created on app.pet_events (couple_id, created_at desc);
create index pet_events_pet_created on app.pet_events (pet_id, created_at desc);

alter table app.couples enable row level security;
alter table app.profiles enable row level security;
alter table app.pets enable row level security;
alter table app.pet_needs enable row level security;
alter table app.pet_events enable row level security;

create policy couple_read on app.couples
  for select to authenticated
  using (id = (select app.current_couple_id()));

create policy couple_read on app.profiles
  for select to authenticated
  using (couple_id = (select app.current_couple_id()));

create policy couple_read on app.pets
  for select to authenticated
  using (couple_id = (select app.current_couple_id()));

create policy couple_read on app.pet_needs
  for select to authenticated
  using (couple_id = (select app.current_couple_id()));

create policy couple_read on app.pet_events
  for select to authenticated
  using (couple_id = (select app.current_couple_id()));

-- Restrictive: added to the policies above, never replacing them. A token without the
-- second factor reads and writes nothing, through the API or straight from the browser.
create policy second_factor on app.couples
  as restrictive for all to authenticated
  using ((select app.has_second_factor()))
  with check ((select app.has_second_factor()));

create policy second_factor on app.profiles
  as restrictive for all to authenticated
  using ((select app.has_second_factor()))
  with check ((select app.has_second_factor()));

create policy second_factor on app.pets
  as restrictive for all to authenticated
  using ((select app.has_second_factor()))
  with check ((select app.has_second_factor()));

create policy second_factor on app.pet_needs
  as restrictive for all to authenticated
  using ((select app.has_second_factor()))
  with check ((select app.has_second_factor()));

create policy second_factor on app.pet_events
  as restrictive for all to authenticated
  using ((select app.has_second_factor()))
  with check ((select app.has_second_factor()));

grant select on app.couples, app.profiles, app.pets, app.pet_needs, app.pet_events
  to authenticated;
