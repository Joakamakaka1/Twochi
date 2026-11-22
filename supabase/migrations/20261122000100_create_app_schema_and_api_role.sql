-- Private schema for the game and the API's login role (Datos y vectores, «Acceso»).
--
-- `app` is not in the Data API's exposed schemas (config.toml, `api.schemas`): the front
-- never reads or writes it through PostgREST. The API reaches it with its own login role
-- and `set local role authenticated`, so the same RLS policies protect both paths.

create schema app;
revoke all on schema app from public;
grant usage on schema app to authenticated;

-- The API logs in as twochi_api and, inside each transaction, switches to `authenticated`
-- with the caller's JWT claims (option B). NOINHERIT: without `set role` it holds no
-- privilege of its own, so a query outside a transaction reads nothing. No BYPASSRLS.
-- The password is never in git: local seed sets a dev one; prod gets it from Bitwarden.
create role twochi_api login noinherit nobypassrls;
grant authenticated to twochi_api;

-- The couple of the caller, from the `couple_id` claim the access token hook adds.
-- Wrapped in `select` inside policies so Postgres evaluates it once per query.
create function app.current_couple_id()
returns uuid
language sql
stable
set search_path = ''
as $$
  select nullif((select auth.jwt()) ->> 'couple_id', '')::uuid
$$;

revoke all on function app.current_couple_id() from public;
grant execute on function app.current_couple_id() to authenticated;

-- The second factor: every table adds a restrictive policy with this check.
create function app.has_second_factor()
returns boolean
language sql
stable
set search_path = ''
as $$
  select coalesce((select auth.jwt()) ->> 'aal', '') = 'aal2'
$$;

revoke all on function app.has_second_factor() from public;
grant execute on function app.has_second_factor() to authenticated;
