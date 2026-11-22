import type { CareAction } from "../../shared";

// Rooms are interface only: the API knows care actions, not where they happen.
export type Room = "kitchen" | "bathroom" | "bedroom" | "living_room";

export interface RoomCare {
  room: Room;
  actions: readonly CareAction[];
}

/** Casa's four rooms, in order, with the care each one offers; petting is in all. */
export const ROOMS: readonly RoomCare[] = [
  { room: "kitchen", actions: ["feed", "pet"] },
  { room: "bathroom", actions: ["bathe", "pet"] },
  { room: "bedroom", actions: ["sleep", "wake", "pet"] },
  { room: "living_room", actions: ["play", "pet"] },
];
