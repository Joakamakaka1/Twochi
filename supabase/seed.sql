-- Local only: `supabase db reset` and `supabase start` load it; `db push` never does.
-- Fictional people for development. Production data never enters this repository.

-- Dev password for the API's login role; production sets its own from Bitwarden.
alter role twochi_api password 'twochi-api-local';

-- A test couple that signs in with email and password, for the front in development.
insert into auth.users (
  instance_id, id, aud, role, email, encrypted_password, email_confirmed_at,
  raw_app_meta_data, raw_user_meta_data, created_at, updated_at,
  confirmation_token, email_change, email_change_token_new, recovery_token
)
select
  '00000000-0000-0000-0000-000000000000', u.id, 'authenticated', 'authenticated', u.email,
  extensions.crypt('twochi-local', extensions.gen_salt('bf')), now(),
  '{"provider": "email", "providers": ["email"]}', '{}', now(), now(), '', '', '', ''
from (values
  ('00000000-0000-4000-8000-00000000a11c'::uuid, 'alice@twochi.test'),
  ('00000000-0000-4000-8000-00000000b20b'::uuid, 'bruno@twochi.test')
) as u (id, email);

insert into auth.identities (
  id, user_id, provider_id, identity_data, provider, last_sign_in_at, created_at, updated_at
)
select gen_random_uuid(), u.id, u.id::text,
       jsonb_build_object('sub', u.id::text, 'email', u.email), 'email', now(), now(), now()
from auth.users u
where u.email in ('alice@twochi.test', 'bruno@twochi.test');

insert into app.couples (id) values ('00000000-0000-4000-8000-0000000c0de1');

insert into app.profiles (user_id, couple_id, display_name) values
  ('00000000-0000-4000-8000-00000000a11c', '00000000-0000-4000-8000-0000000c0de1', 'Alice'),
  ('00000000-0000-4000-8000-00000000b20b', '00000000-0000-4000-8000-0000000c0de1', 'Bruno');

-- Each pet represents one of them and the other cares for it.
insert into app.pets (id, couple_id, represents_user_id, caretaker_user_id, name, model_key)
values
  ('00000000-0000-4000-8000-0000000fa11c', '00000000-0000-4000-8000-0000000c0de1',
   '00000000-0000-4000-8000-00000000a11c', '00000000-0000-4000-8000-00000000b20b',
   'Ali', 'placeholder'),
  ('00000000-0000-4000-8000-0000000fb20b', '00000000-0000-4000-8000-0000000c0de1',
   '00000000-0000-4000-8000-00000000b20b', '00000000-0000-4000-8000-00000000a11c',
   'Bru', 'placeholder');

insert into app.pet_needs (pet_id, couple_id, need, value, updated_at)
select p.id, p.couple_id, n.need, 80, now()
from app.pets p
cross join unnest(array['hunger', 'energy', 'hygiene', 'fun', 'affection']) as n (need);
