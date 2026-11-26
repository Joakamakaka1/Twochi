import type { Pet } from "../../shared";
import bathroom from "./backdrops/bathroom.svg";
import bedroomDark from "./backdrops/bedroom-dark.svg";
import bedroom from "./backdrops/bedroom.svg";
import kitchen from "./backdrops/kitchen.svg";
import livingRoom from "./backdrops/living-room.svg";
import type { Room } from "./rooms";

/** A room's picture, and the one it shows with the light off while the pet sleeps. */
interface RoomPicture {
  lit: string;
  dark?: string;
}

// The only map from room to picture: placeholder SVGs today. The real backgrounds (PNG
// or WebP) come in by changing an import here; the scene and Casa stay as they are.
const BACKDROPS: Readonly<Record<Room, RoomPicture>> = {
  kitchen: { lit: kitchen },
  bathroom: { lit: bathroom },
  bedroom: { lit: bedroom, dark: bedroomDark },
  living_room: { lit: livingRoom },
};

/** The picture behind the pet in `room`: in the dark while it sleeps, where the room has a dark one. */
export function roomBackdrop(room: Room, pet: Pick<Pet, "asleep">): string {
  const picture = BACKDROPS[room];
  return pet.asleep ? (picture.dark ?? picture.lit) : picture.lit;
}
