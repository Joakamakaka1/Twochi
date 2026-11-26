import { useFrame } from "@react-three/fiber";
import { useRef } from "react";
import type { RefObject } from "react";
import type { Group, Mesh } from "three";

import type { Playing } from "./clips";
import { proceduralPose, sickTremble } from "./procedural";

const BODY_RADIUS = 0.6;
// Closed eyes stay a thin line instead of vanishing.
const CLOSED_EYES = 0.12;
// The placeholder's skin; while sick it takes the colour of the --color-pet-sick token.
const WELL_COLOUR = "#f2b880";

interface PlaceholderPetProps {
  playing: RefObject<Playing>;
  onTap?: (() => void) | undefined;
  sick: boolean;
  /** The skin while sick, from tokens.css; empty keeps the usual skin. */
  sickColour: string;
  reducedMotion: boolean;
}

// The stand-in for the pet's GLB: a body and two eyes, moved by the procedural pose of
// the clip on stage. It mutates the meshes in useFrame and never sets React state there.
export function PlaceholderPet({ playing, onTap, sick, sickColour, reducedMotion }: PlaceholderPetProps) {
  const body = useRef<Group>(null);
  const leftEye = useRef<Mesh>(null);
  const rightEye = useRef<Mesh>(null);

  useFrame(() => {
    const { animation, startedAt } = playing.current;
    const pose = proceduralPose(animation, (performance.now() - startedAt) / 1000);
    const group = body.current;
    if (group === null) return;
    const tremble = sick ? sickTremble(performance.now() / 1000, reducedMotion) : 0;
    group.scale.set(...pose.scale);
    group.position.set(pose.sway + tremble, pose.lift, 0);
    group.rotation.set(pose.lean, 0, pose.tilt);
    for (const eye of [leftEye.current, rightEye.current]) {
      if (eye !== null) eye.scale.y = Math.max(pose.eyes, CLOSED_EYES);
    }
  });

  return (
    <group
      ref={body}
      onClick={(event) => {
        event.stopPropagation();
        onTap?.();
      }}
    >
      <mesh position={[0, BODY_RADIUS, 0]}>
        <sphereGeometry args={[BODY_RADIUS, 32, 24]} />
        <meshStandardMaterial color={sick && sickColour !== "" ? sickColour : WELL_COLOUR} roughness={0.8} />
      </mesh>
      <mesh ref={leftEye} position={[-0.2, 0.75, 0.53]}>
        <sphereGeometry args={[0.07, 16, 12]} />
        <meshStandardMaterial color="#2b2118" />
      </mesh>
      <mesh ref={rightEye} position={[0.2, 0.75, 0.53]}>
        <sphereGeometry args={[0.07, 16, 12]} />
        <meshStandardMaterial color="#2b2118" />
      </mesh>
    </group>
  );
}
