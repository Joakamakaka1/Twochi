import { Canvas } from "@react-three/fiber";
import { useImperativeHandle, useRef } from "react";
import type { Ref } from "react";

import { BACKDROPS } from "./backdrops";
import type { Backdrop } from "./backdrops";
import type { Animation, Playing } from "./clips";
import { PlaceholderPet } from "./PlaceholderPet";

/** The scene's only entry: play a clip on the pet, from its start. */
export interface PetSceneHandle {
  play(animation: Animation): void;
}

interface PetSceneProps {
  ref?: Ref<PetSceneHandle>;
  backdrop: Backdrop;
  /** What a screen reader says the figure is. */
  label: string;
  /** Touching the figure; the same care has its own button outside the canvas. */
  onTap?: (() => void) | undefined;
}

// Phones report a pixel ratio of 3 or more; past 2 it costs memory and frames, not detail.
const MAX_DPR = 2;
const LOOK_AT = [0, 0.6, 0] as const;

// The single Canvas of the app. R3F disposes what it builds here (geometries, materials,
// the renderer) when it unmounts, so nothing is freed by hand.
//
// Seams: a rigged GLB replaces PlaceholderPet reading the same `playing` ref (useGLTF and
// useAnimations, cross-fading to actions[animation]); the room's real background replaces
// RoomBackdrop.
export function PetScene({ ref, backdrop, label, onTap }: PetSceneProps) {
  const playing = useRef<Playing>({ animation: "idle", startedAt: 0 });
  useImperativeHandle(
    ref,
    () => ({
      play: (animation) => {
        playing.current = { animation, startedAt: performance.now() };
      },
    }),
    [],
  );

  return (
    <div role="img" aria-label={label} style={{ height: "min(50vh, 360px)", touchAction: "manipulation" }}>
      <Canvas
        gl={{ antialias: false }}
        dpr={[1, MAX_DPR]}
        camera={{ position: [0, 1.3, 3.6], fov: 40 }}
        onCreated={({ camera }) => {
          camera.lookAt(...LOOK_AT);
        }}
      >
        <RoomBackdrop backdrop={backdrop} />
        <ambientLight intensity={1.2} />
        <directionalLight position={[2, 4, 3]} intensity={2} />
        <PlaceholderPet playing={playing} onTap={onTap} />
      </Canvas>
    </div>
  );
}

function RoomBackdrop({ backdrop }: { backdrop: Backdrop }) {
  const { wall, floor } = BACKDROPS[backdrop];
  return (
    <>
      <color attach="background" args={[wall]} />
      <mesh rotation-x={-Math.PI / 2}>
        <circleGeometry args={[2.5, 48]} />
        <meshStandardMaterial color={floor} />
      </mesh>
    </>
  );
}
