import type { AuthPort } from "./authPort";

// Where the person stands on the way in. Only `ready` (aal2) shows the app.
export type Gate =
  | { step: "sign_in" }
  | { step: "enroll_totp" }
  | { step: "verify_totp"; factorId: string }
  | { step: "ready"; userId: string };

// The API and RLS enforce aal2 on their own; this only decides which screen to show.
export async function resolveGate(auth: AuthPort): Promise<Gate> {
  const assurance = await auth.assurance();
  if (assurance?.level === "aal2") return { step: "ready", userId: assurance.userId };
  return { step: "verify_totp", factorId: assurance?.totpFactorId ?? "" };
}
