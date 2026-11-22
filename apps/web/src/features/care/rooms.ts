import type { CareAction } from "../../shared";

export type Room = "kitchen" | "bathroom" | "bedroom" | "living_room";

export interface RoomCare {
  room: Room;
  actions: readonly CareAction[];
}

export const ROOMS: readonly RoomCare[] = [
  { room: "kitchen", actions: ["feed"] },
  { room: "bathroom", actions: ["bathe"] },
  { room: "bedroom", actions: ["sleep", "wake"] },
  { room: "living_room", actions: ["play"] },
];
