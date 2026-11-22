-- Signups from the allowlist (ADR 0007): the table `just provision` fills, the Before User
-- Created Hook that rejects every other email, and the trigger that creates the profile
-- and, with the second person of a couple, gives birth to both pets.
--
-- No row enters git: the emails and names live in a local file that `provision` reads.
-- Enabling the hook in the hosted project is a dashboard step (TWO-13), after this migration.

create table app.signup_allowlist (
  email         text primary key
                check (email = lower(email) and length(email) between 3 and 320),
  couple_id     uuid not null references app.couples,
  display_name  text not null check (length(display_name) between 1 and 60),
  -- The pet that will represent this person, cared for by the other one.
  pet_name      text not null check (length(pet_name) between 1 and 40),
  pet_model_key text not null check (pet_model_key ~ '^[a-z0-9_-]{1,40}$'),
  -- How this person may sign up: the couple with Google; only the test couple, which
  -- `provision` creates through the admin API, with email. A password signup to a
  -- Google person's email is refused, so nobody takes their place in the couple.
  provider      text not null default 'google' check (provider in ('google', 'email')),
  created_at    timestamptz not null default now()
);

create index signup_allowlist_couple on app.signup_allowlist (couple_id);

-- The template, minus the read policy: no client reads the list, through the API or
-- with its own token. Only the hook reads it, and only the email and the provider.
alter table app.signup_allowlist enable row level security;
revoke all on app.signup_allowlist from public, anon, authenticated;

create policy second_factor on app.signup_allowlist
  as restrictive for all to authenticated
  using ((select app.has_second_factor()))
  with check ((select app.has_second_factor()));

grant select (email, provider) on app.signup_allowlist to supabase_auth_admin;

create policy auth_admin_reads_emails on app.signup_allowlist
  for select to supabase_auth_admin
  using (true);

-- Before User Created Hook: Supabase Auth runs it as supabase_auth_admin before a person
-- signs up (users created through the admin API skip it). `{}` lets the signup through;
-- an error object rejects it. The message never names the email, so a rejection leaks
-- nothing about who is on the list.
create function app.before_user_created_hook(event jsonb)
returns jsonb
language sql
stable
set search_path = ''
as $$
  select case
    when exists (
      select 1 from app.signup_allowlist a
      where a.email = lower(event -> 'user' ->> 'email')
        and a.provider = event -> 'user' -> 'app_metadata' ->> 'provider'
    ) then '{}'::jsonb
    else jsonb_build_object(
      'error', jsonb_build_object('http_code', 403, 'message', 'Signups are closed.')
    )
  end
$$;

revoke all on function app.before_user_created_hook(jsonb) from public;
revoke all on function app.before_user_created_hook(jsonb) from anon, authenticated;
grant execute on function app.before_user_created_hook(jsonb) to supabase_auth_admin;

-- After a user is inserted: their profile and, once the couple has both, the two pets.
--
-- security definer, owned by postgres: the birth is the system acting, not a person, so
-- it writes past the policies that bind `authenticated` (ADR 0007). Granting
-- supabase_auth_admin inserts on the game tables instead would give Auth's role those
-- writes for good. Nobody may call it: only the trigger runs it.
create function app.handle_signup()
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
    select listed.couple_id, pets.id, 'system', 'birth', '2026-11-22', 'birth'
    from pets;
  end if;

  return null;
end;
$$;

revoke all on function app.handle_signup() from public;
revoke all on function app.handle_signup() from anon, authenticated;

create trigger handle_signup
  after insert on auth.users
  for each row execute function app.handle_signup();
