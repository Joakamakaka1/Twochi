-- The engine's writes for care actions (spec TWO-28, «Datos»): a pet's sleep and sickness,
-- its needs and the event that records each applied action. Nothing else is writable.
--
-- `app` is not exposed in the Data API, so these grants are reachable only through the
-- API, which switches to `authenticated` with the caller's claims. The restrictive
-- second_factor policies already cover every command: an aal1 token writes nothing.

-- Column grants: the identity of a pet, its couple and its people never change here.
grant update (asleep, sick_since) on app.pets to authenticated;
grant update (value, updated_at) on app.pet_needs to authenticated;
-- created_at is the engine's `now`, so the hourly petting limit and the clock agree.
grant insert (
  couple_id, pet_id, actor_user_id, source, action, payload, deltas, rules_version,
  idempotency_key, created_at
) on app.pet_events to authenticated;

-- `select … for update` also needs these: the use case locks the pet before deciding.
create policy couple_update on app.pets
  for update to authenticated
  using (couple_id = (select app.current_couple_id()))
  with check (couple_id = (select app.current_couple_id()));

create policy couple_update on app.pet_needs
  for update to authenticated
  using (couple_id = (select app.current_couple_id()))
  with check (couple_id = (select app.current_couple_id()));

-- A person records events only in their couple, in their own name and never as the
-- system: births and sweeps belong to other roles.
create policy couple_insert on app.pet_events
  for insert to authenticated
  with check (
    couple_id = (select app.current_couple_id())
    and actor_user_id = (select auth.uid())
    and source <> 'system'
  );
