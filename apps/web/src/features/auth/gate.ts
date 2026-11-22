import type { AuthPort } from "./authPort";

// Where the person stands on the way in. Only `ready` (aal2) shows the app.
export type Gate =
  | { step: "sign_in" }
  | { step: "enroll_totp" }
  | { step: "verify_totp"; factorId: string }
  | { step: "ready"; userId: string };

export function resolveGate(_auth: AuthPort): Promise<Gate> {
  return Promise.resolve({ step: "sign_in" });
}
