-- Tastes: each pet's affinity with the foods and activities of the catalogue (spec TWO-48,
-- ADR 0015). The catalogue lives in the engine's code, so `item_key` has no check against
-- it: a key the catalogue no longer holds is ignored on read.
--
-- Both people of the couple read the tastes: the engine reads one with the caretaker's
-- token when they feed or play. Hiding the list from the caretaker is the API's job, not
-- RLS's (ADR 0015). Only the person a pet represents writes its tastes.

create table app.item_affinities (
  couple_id  uuid not null,
  pet_id     uuid not null,
  item_key   text not null check (item_key ~ '^[a-z0-9_]{1,40}$'),
  affinity   smallint not null check (affinity between -2 and 2),
  updated_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  primary key (pet_id, item_key),
  foreign key (couple_id, pet_id) references app.pets (couple_id, id)
);

create index item_affinities_couple on app.item_affinities (couple_id);

alter table app.item_affinities enable row level security;

create policy couple_read on app.item_affinities
  for select to authenticated
  using (couple_id = (select app.current_couple_id()));

create policy second_factor on app.item_affinities
  as restrictive for all to authenticated
  using ((select app.has_second_factor()))
  with check ((select app.has_second_factor()));

-- The person a pet represents rates it; the caretaker never does. The pets the subquery
-- sees are already only the caller's couple's (couple_read on app.pets).
create policy represented_insert on app.item_affinities
  for insert to authenticated
  with check (
    couple_id = (select app.current_couple_id())
    and exists (
      select 1 from app.pets p
      where p.id = pet_id and p.represents_user_id = (select auth.uid())
    )
  );

create policy represented_update on app.item_affinities
  for update to authenticated
  using (
    couple_id = (select app.current_couple_id())
    and exists (
      select 1 from app.pets p
      where p.id = pet_id and p.represents_user_id = (select auth.uid())
    )
  )
  with check (
    couple_id = (select app.current_couple_id())
    and exists (
      select 1 from app.pets p
      where p.id = pet_id and p.represents_user_id = (select auth.uid())
    )
  );

-- Column grants, as for the engine's writes (ADR 0009): a taste's pet and item never
-- change, and nothing deletes one.
grant select on app.item_affinities to authenticated;
grant insert (couple_id, pet_id, item_key, affinity, updated_at)
  on app.item_affinities to authenticated;
grant update (affinity, updated_at) on app.item_affinities to authenticated;

-- The tastes move RULES_VERSION on (twochi_domain.care), and births record it in their
-- event: the same function as in 20261122000500, with only the version changed.
-- `create or replace` keeps its owner, its grants and its trigger.
create or replace function app.handle_signup()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  listed app.signup_allowlist%rowtype;
begin
  select * into listed
  from app.signup_allowlist a
  where a.email = lower(new.email)
    and a.provider = new.raw_app_meta_data ->> 'provider';
  -- Someone off the list, or signing up another way than theirs: the hook is the gate,
  -- and this repeats its rule for the time before it is enabled. Users inserted by hand
  -- (the local seed, the tests) get no profile, and without one their token reads nothing.
  if not found then
    return null;
  end if;

  -- Two signups at once would each miss the other's profile and no pet would be born:
  -- the couple's row serializes them.
  perform 1 from app.couples c where c.id = listed.couple_id for update;

  -- A couple is two people. Someone listed after both signed up would read everything
  -- of theirs and care for nothing: the signup fails instead.
  if (select count(*) from app.profiles p where p.couple_id = listed.couple_id) >= 2 then
    raise exception 'This couple already has two people.' using errcode = 'check_violation';
  end if;

  insert into app.profiles (user_id, couple_id, display_name)
  values (new.id, listed.couple_id, listed.display_name);

  if (select count(*) from app.profiles p where p.couple_id = listed.couple_id) = 2
     and not exists (select 1 from app.pets p where p.couple_id = listed.couple_id) then
    -- Both people must still be on the list, by their current email, to name their pets.
    -- Otherwise no pet would be born and nothing would try again: fail loudly instead.
    if (
      select count(*)
      from app.profiles p
      join auth.users u on u.id = p.user_id
      join app.signup_allowlist a
        on a.email = lower(u.email) and a.couple_id = p.couple_id
      where p.couple_id = listed.couple_id
    ) <> 2 then
      raise exception 'Both people of the couple must be on the allowlist for the birth.'
        using errcode = 'check_violation';
    end if;

    -- Each pet represents one person and the other cares for it. Born awake, with every
    -- need at the domain's BIRTH_NEED_VALUE and the domain's RULES_VERSION in its event:
    -- test_signups.py fails if these drift from twochi_domain.
    with
      people as (
        select p.user_id, a.pet_name, a.pet_model_key
        from app.profiles p
        join auth.users u on u.id = p.user_id
        join app.signup_allowlist a
          on a.email = lower(u.email) and a.couple_id = p.couple_id
        where p.couple_id = listed.couple_id
      ),
      pets as (
        insert into app.pets
          (couple_id, represents_user_id, caretaker_user_id, name, model_key)
        select listed.couple_id, me.user_id, other.user_id, me.pet_name, me.pet_model_key
        from people me
        join people other on other.user_id <> me.user_id
        returning id
      ),
      needs as (
        insert into app.pet_needs (pet_id, couple_id, need, value, updated_at)
        select pets.id, listed.couple_id, n.need, 80, now()
        from pets
        cross join unnest(array['hunger', 'energy', 'hygiene', 'fun', 'affection'])
          as n (need)
      )
    insert into app.pet_events
      (couple_id, pet_id, source, action, rules_version, idempotency_key)
    select listed.couple_id, pets.id, 'system', 'birth', '2026-11-26', 'birth'
    from pets;
  end if;

  return null;
end;
$$;
