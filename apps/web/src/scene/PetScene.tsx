import { Canvas } from "@react-three/fiber";
import { memo, useImperativeHandle, useRef } from "react";
import type { Ref } from "react";

import type { Animation, Playing } from "./clips";
import { PlaceholderPet } from "./PlaceholderPet";

/** The scene's only entry: play a clip on the pet, from its start. */
export interface PetSceneHandle {
  play(animation: Animation): void;
}

interface PetSceneProps {
  ref?: Ref<PetSceneHandle>;
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
// The Canvas is transparent and draws no room: whatever the page puts behind it (a room's
// backdrop) shows through. Seam: a rigged GLB replaces PlaceholderPet reading the same
// `playing` ref (useGLTF and useAnimations, cross-fading to actions[animation]).
// Memoised: Casa re-renders every second for the need bars, and the scene needs none of it.
export const PetScene = memo(function PetScene({ ref, label, onTap }: PetSceneProps) {
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
    <div role="img" aria-label={label} style={{ height: "100%", touchAction: "manipulation" }}>
      <Canvas
        gl={{ antialias: false, alpha: true }}
        dpr={[1, MAX_DPR]}
        camera={{ position: [0, 1.3, 3.6], fov: 40 }}
        style={{ background: "transparent" }}
        onCreated={({ camera, gl }) => {
          camera.lookAt(...LOOK_AT);
          gl.setClearColor(0x000000, 0);
        }}
      >
        <ambientLight intensity={1.2} />
        <directionalLight position={[2, 4, 3]} intensity={2} />
        <GroundShadow />
        <PlaceholderPet playing={playing} onTap={onTap} />
      </Canvas>
    </div>
  );
});

// A soft shadow under the pet, so it stands on whatever floor the backdrop draws.
function GroundShadow() {
  return (
    <mesh rotation-x={-Math.PI / 2} position-y={0.001} scale={[1, 0.85, 1]}>
      <circleGeometry args={[0.62, 40]} />
      <meshBasicMaterial color="#47355e" transparent opacity={0.18} depthWrite={false} />
    </mesh>
  );
}
