-- Custom Access Token Hook: adds the caller's couple as the `couple_id` claim, which every
-- RLS policy reads through app.current_couple_id() (Datos y vectores, «Forma de las
-- políticas»). Supabase Auth runs it as supabase_auth_admin each time it issues a token.
-- Enabling it in the hosted project is a dashboard step (TWO-13), after this migration.

create function app.custom_access_token_hook(event jsonb)
returns jsonb
language plpgsql
stable
set search_path = ''
as $$
declare
  claims jsonb := coalesce(event -> 'claims', '{}'::jsonb);
  couple uuid;
begin
  select p.couple_id into couple
  from app.profiles p
  where p.user_id = (event ->> 'user_id')::uuid;

  -- A person not yet in a couple gets no claim, so every couple policy denies them.
  if couple is null then
    claims := claims - 'couple_id';
  else
    claims := jsonb_set(claims, '{couple_id}', to_jsonb(couple::text));
  end if;

  return jsonb_set(event, '{claims}', claims);
end;
$$;

revoke all on function app.custom_access_token_hook(jsonb) from public;
revoke all on function app.custom_access_token_hook(jsonb) from anon, authenticated;
grant execute on function app.custom_access_token_hook(jsonb) to supabase_auth_admin;

grant usage on schema app to supabase_auth_admin;
grant select (user_id, couple_id) on app.profiles to supabase_auth_admin;

create policy auth_admin_reads_couple on app.profiles
  for select to supabase_auth_admin
  using (true);
