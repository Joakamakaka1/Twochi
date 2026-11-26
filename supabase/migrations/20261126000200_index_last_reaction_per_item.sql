-- Gustos descubiertos (TWO-52): Casa reads, for each item of the catalogue, the last
-- event that gave it to the pet. One probe per item reaches that event through this
-- index, however long the pet's history grows. Only feeding and playing store an item,
-- so the rest of the events stay out of it.
create index pet_events_pet_item_last
  on app.pet_events (pet_id, (payload ->> 'item_key'), id desc)
  where (payload ->> 'item_key') is not null;
