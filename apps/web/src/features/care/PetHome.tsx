import { lazy, Suspense, useCallback, useMemo, useState } from "react";
import type { MouseEvent } from "react";

import { texts } from "../../shared";
import type { CareAction, CareActionResult, Pet } from "../../shared";
import { bubbleKey, celebrating, chooseBubble } from "./bubble";
import { Celebration } from "./Celebration";
import { ACTION_ICONS, ROOM_ICONS, SICK_ICON } from "./icons";
import { needBars } from "./needBars";
import { NeedRings } from "./NeedRings";
import { PetBubble } from "./PetBubble";
import styles from "./PetHome.module.css";
import { roomBackdrop } from "./roomBackdrop";
import { ROOMS } from "./rooms";
import type { Room } from "./rooms";
import { petTouches } from "./touch";
import { opensTray } from "./tray";
import type { TrayAction } from "./tray";
import { TraySheet } from "./TraySheet";
import { useCareActions, useNow } from "./useHome";
import { usePetBubble } from "./usePetBubble";
import { usePetStage } from "./usePetStage";

const TICK_MS = 1000;

// Three.js comes in its own chunk, after Casa's first paint.
const PetScene = lazy(() => import("../../scene").then((scene) => ({ default: scene.PetScene })));

// Casa with a pet, upright for the phone: its name, mood and needs on top; the room's
// backdrop, the pet and its bubble in the middle; the room's care above the room bar.
export function PetHome({ pet }: { pet: Pet }) {
  const [room, setRoom] = useState<Room>("kitchen");
  // Feeding and playing first open a tray to choose what to give; the button that opened
  // it gets the focus back when it goes.
  const [tray, setTray] = useState<{ action: TrayAction; opener: HTMLElement } | null>(null);
  const now = useNow(TICK_MS);
  const { attach, react, tickle } = usePetStage(pet);
  const { last, luck, hear, hearTickle } = usePetBubble();
  // Each outcome the engine gives plays its reaction and takes the bubble for a while.
  const onOutcome = useCallback(
    (action: CareAction, result: CareActionResult) => {
      react(action, result);
      hear(action, result);
    },
    [react, hear],
  );
  const care = useCareActions(pet.id, onOutcome);
  const { tap } = care;
  // The first touch of a burst pets, as the button does; tickles stay on screen.
  const touches = useMemo(
    () =>
      petTouches({
        pet: () => {
          tap("pet");
        },
        tickle: () => {
          tickle();
          hearTickle();
        },
      }),
    [tap, tickle, hearTickle],
  );
  // New only when the pet falls asleep or wakes, so the memoised scene skips the bars' tick.
  const { asleep } = pet;
  const petByTouch = useCallback(() => {
    touches(performance.now(), asleep);
  }, [touches, asleep]);
  const actions = ROOMS.find((each) => each.room === room)?.actions ?? [];
  const backdrop = roomBackdrop(room, pet);
  const bars = needBars(pet, now);
  const bubble = chooseBubble({ pet, bars, now: now.getTime() }, last, () => luck);
  const healing = celebrating(last, now.getTime());
  const sick = pet.mood === "sick";

  // While a tap is in flight the buttons say so but stay focusable (aria-disabled), so
  // focus can go back to the one that opened the tray; the taps' own lock drops the tap.
  const careButton = (action: CareAction) => (event: MouseEvent<HTMLButtonElement>) => {
    if (care.isPending) return;
    if (opensTray(action)) setTray({ action, opener: event.currentTarget });
    else care.tap(action);
  };

  return (
    <div className={styles.home}>
      <header className={styles.status}>
        <h1 className={styles.name}>{texts.care.caringFor(pet.name)}</h1>
        <p className={styles.chips}>
          <span className={styles.chip} data-mood={pet.mood}>
            {texts.care.moodIs(texts.care.moods[pet.mood])}
          </span>
          <span className={styles.chip} data-asleep={pet.asleep || undefined}>
            {pet.asleep ? texts.care.asleep : texts.care.awake}
          </span>
        </p>
      </header>

      <NeedRings bars={bars} />

      <div className={styles.stage}>
        {/* Keyed by the picture, so a new room or the light going off fades in. */}
        <img key={backdrop} className={styles.backdrop} src={backdrop} alt="" />
        <div className={styles.scene}>
          <Suspense fallback={null}>
            <PetScene ref={attach} label={texts.care.petFigure(pet.name)} onTap={petByTouch} sick={sick} />
          </Suspense>
        </div>
        {sick && (
          <span className={styles.sickIcon} aria-hidden="true">
            {SICK_ICON}
          </span>
        )}
        {/* Keyed by the outcome, so healing twice celebrates twice. */}
        {healing && last !== null && <Celebration key={last.at} />}
        <PetBubble text={bubble} id={bubbleKey(last, now.getTime())} />
      </div>

      {care.failure !== null && (
        <div className={styles.failure}>
          <p role="alert">{care.failure}</p>
          <button type="button" className={styles.retry} onClick={care.retry}>
            {texts.retry}
          </button>
        </div>
      )}

      <section className={styles.care} aria-label={texts.care.rooms[room]}>
        {actions.map((action) => (
          <button
            key={action}
            type="button"
            className={styles.careButton}
            aria-disabled={care.isPending || undefined}
            onClick={careButton(action)}
          >
            <span className={styles.careIcon} aria-hidden="true">
              {ACTION_ICONS[action]}
            </span>
            {texts.care.actions[action]}
          </button>
        ))}
      </section>

      <nav className={styles.rooms} aria-label={texts.care.roomsTitle}>
        {ROOMS.map((each) => (
          <button
            key={each.room}
            type="button"
            className={styles.room}
            aria-pressed={each.room === room}
            onClick={() => {
              setRoom(each.room);
            }}
          >
            <span className={styles.roomIcon} aria-hidden="true">
              {ROOM_ICONS[each.room]}
            </span>
            {texts.care.rooms[each.room]}
          </button>
        ))}
      </nav>

      {tray !== null && (
        <TraySheet
          action={tray.action}
          opener={tray.opener}
          onChoose={(item) => {
            care.tap(tray.action, item);
          }}
          onClose={() => {
            setTray(null);
          }}
        />
      )}
    </div>
  );
}
