import { phrases, texts } from "../../shared";
import type { CareAction, CareActionResult, Mood, Need, Pet } from "../../shared";
import { lowestNeed, mostUrgent } from "./needBars";
import type { NeedBar } from "./needBars";

/** How long the pet talks about what just happened before its state takes the bubble back. */
export const BUBBLE_MS = 4000;

/** The pet as Casa shows it at `now` (milliseconds since the epoch). */
export interface BubbleState {
  pet: Pick<Pet, "mood" | "asleep">;
  bars: readonly NeedBar[];
  now: number;
}

/**
 * What just happened to the pet: the last care action the engine applied or refused, and
 * when it came back, or tickles (GLOSSARY.md, «Cosquillas»), which only happen on screen.
 */
export type LastOutcome = { action: CareAction; result: CareActionResult; at: number } | { action: "tickle"; at: number };

/** The last outcome while the pet still talks about it, or null once it is over. */
export function currentOutcome(last: LastOutcome | null, now: number): LastOutcome | null {
  return last !== null && now < last.at + BUBBLE_MS ? last : null;
}

/**
 * The outcome after a tickle at `at`: the giggle in course while the fit goes on, so the
 * bubble keeps its words and is not announced on every touch; a new one otherwise.
 */
export function tickled(last: LastOutcome | null, at: number): LastOutcome {
  const outcome = currentOutcome(last, at);
  return outcome?.action === "tickle" ? outcome : { action: "tickle", at };
}

/** Whether the pet is still talking about having healed: it celebrates meanwhile. */
export function celebrating(last: LastOutcome | null, now: number): boolean {
  const outcome = currentOutcome(last, now);
  return outcome !== null && outcome.action !== "tickle" && outcome.result.sickness === "healed";
}

/**
 * Names what the bubble says: each outcome its own, so the same phrase after a second
 * outcome is said again; the state's once the outcome is over.
 */
export function bubbleKey(last: LastOutcome | null, now: number): string {
  const outcome = currentOutcome(last, now);
  return outcome === null ? "state" : `outcome:${String(outcome.at)}`;
}

// One of several phrases; `random` is in [0, 1), as Math.random.
function pick<T>(list: readonly [T, ...T[]], random: () => number): T {
  const index = Math.min(Math.floor(random() * list.length), list.length - 1);
  return list[index] ?? list[0];
}

function outcomePhrase(outcome: LastOutcome, random: () => number): string {
  if (outcome.action === "tickle") return pick(phrases.tickles, random);
  const { action, result } = outcome;
  if (result.sickness === "healed") return pick(phrases.healed, random);
  // Touched or petted asleep, it grumbles and goes on sleeping.
  if (action === "pet" && result.rejection === "asleep") return pick(phrases.grumble, random);
  if (result.rejection !== null) return pick(phrases.rejections[result.rejection], random);
  // What it was given goes before falling sick: the sick look already shows, and the
  // sick bubble comes once this one is over.
  if (result.reaction !== null) {
    const kind = action === "play" ? "activity" : "food";
    const phrase = pick(phrases.reactions[kind][result.reaction.affinity], random);
    return phrase(texts.care.items[result.reaction.item_key]);
  }
  if (result.sickness === "fell_sick") return pick(phrases.fellSick, random);
  // The API's deltas say whether the petting raised the affection; the engine decides.
  if (action === "pet" && (result.deltas.affection ?? 0) <= 0) return pick(phrases.enough, random);
  return pick(phrases.applied[action], random);
}

function moodPhrase(mood: Exclude<Mood, "sick">, random: () => number): string {
  return pick(phrases.moods[mood], random);
}

function statePhrase({ pet, bars }: BubbleState, random: () => number): string {
  if (pet.asleep) return pick(phrases.asleep, random);
  if (pet.mood === "sick") return pick(phrases.sick[lowestNeed(bars)], random);
  const urgent: Need | null = mostUrgent(bars);
  if (urgent !== null) return pick(phrases.asks[urgent], random);
  return moodPhrase(pet.mood, random);
}

/**
 * What the pet says (GLOSSARY.md, «Bocadillo»), in order: the last outcome (tickles
 * included) for a few seconds, asleep, sick with a hint of what it lacks most, the most
 * urgent request under 30, and its mood. `random` picks among the phrases of that situation.
 */
export function chooseBubble(state: BubbleState, last: LastOutcome | null, random: () => number): string {
  const outcome = currentOutcome(last, state.now);
  return outcome !== null ? outcomePhrase(outcome, random) : statePhrase(state, random);
}
