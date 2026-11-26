// The React Three Fiber scene: the only folder that imports Three.js. Features drive it
// through PetSceneHandle.play(animation). Its Canvas is transparent: what sits behind it
// (a room's backdrop) is the page's business, not the scene's.
export type { Animation } from "./clips";
export { PetScene } from "./PetScene";
export type { PetSceneHandle } from "./PetScene";
