import { useState } from "react";

import { texts } from "../../shared";
import type { Pet } from "../../shared";
import { needBars } from "./needBars";
import { ROOMS } from "./rooms";
import type { Room } from "./rooms";
import { useCareActions, useNow } from "./useHome";

const TICK_MS = 1000;

// Casa with a pet: its state, its needs going down live and the four rooms.
export function PetHome({ pet }: { pet: Pet }) {
  const [room, setRoom] = useState<Room>("kitchen");
  const now = useNow(TICK_MS);
  const care = useCareActions(pet.id);
  const actions = ROOMS.find((each) => each.room === room)?.actions ?? [];

  return (
    <>
      <h1>{texts.care.caringFor(pet.name)}</h1>
      <p>
        {texts.care.moodIs(texts.care.moods[pet.mood])} · {pet.asleep ? texts.care.asleep : texts.care.awake}
      </p>

      <section aria-labelledby="needs-title">
        <h2 id="needs-title">{texts.care.needsTitle}</h2>
        <ul>
          {needBars(pet, now).map((bar) => (
            <li key={bar.need}>
              <label htmlFor={`need-${bar.need}`}>{texts.care.needs[bar.need]}</label>{" "}
              <meter id={`need-${bar.need}`} min={0} max={100} value={bar.value} /> {Math.round(bar.value)}
              {bar.asks && <strong> {texts.care.asksFor}</strong>}
            </li>
          ))}
        </ul>
      </section>

      <nav aria-label={texts.care.roomsTitle}>
        {ROOMS.map((each) => (
          <button
            key={each.room}
            type="button"
            aria-pressed={each.room === room}
            onClick={() => {
              setRoom(each.room);
            }}
          >
            {texts.care.rooms[each.room]}
          </button>
        ))}
      </nav>

      <section aria-labelledby="room-title">
        <h2 id="room-title">{texts.care.rooms[room]}</h2>
        {actions.map((action) => (
          <button
            key={action}
            type="button"
            disabled={care.isPending}
            onClick={() => {
              care.tap(action);
            }}
          >
            {texts.care.actions[action]}
          </button>
        ))}
      </section>

      <p role="status">{care.rejection}</p>
      {care.failure !== null && (
        <>
          <p role="alert">{care.failure}</p>
          <button type="button" onClick={care.retry}>
            {texts.retry}
          </button>
        </>
      )}
    </>
  );
}
