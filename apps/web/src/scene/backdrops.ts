/** The room the pet is in; each one has its own backdrop behind the figure. */
export type Backdrop = "kitchen" | "bathroom" | "bedroom" | "living_room";

/** Placeholder colours for each room's wall and floor, until the real backgrounds arrive. */
export const BACKDROPS: Record<Backdrop, { wall: string; floor: string }> = {
  kitchen: { wall: "#fbe3c4", floor: "#d9a066" },
  bathroom: { wall: "#cfeef5", floor: "#9fc9d6" },
  bedroom: { wall: "#ddd3f2", floor: "#a996cf" },
  living_room: { wall: "#dff0d2", floor: "#a8c98d" },
};
