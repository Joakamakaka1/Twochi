// The part of Supabase Auth this feature needs, named by role. The real adapter is
// supabaseAuth.ts, the only module that imports supabase-js; the tests use the
// hand-written double in testing.ts.

export type AssuranceLevel = "aal1" | "aal2";

export interface Assurance {
  userId: string;
  // What this session has proven: aal2 once the TOTP code was verified in it.
  level: AssuranceLevel;
  // The person's verified TOTP factor, or null while they have none.
  totpFactorId: string | null;
}

export interface TotpEnrollment {
  factorId: string;
  // An SVG image as a data URL.
  qrCode: string;
  // The same secret as text, for whoever cannot scan the QR.
  secret: string;
}

export type CodeOutcome = "verified" | "wrong_code";
export type PasswordOutcome = "signed_in" | "wrong_credentials";

export interface AuthPort {
  // Null without a session.
  assurance: () => Promise<Assurance | null>;
  accessToken: () => Promise<string | null>;
  // Leaves the app: Google and Supabase Auth redirect back with the session.
  signInWithGoogle: () => Promise<void>;
  enrollTotp: () => Promise<TotpEnrollment>;
  verifyTotp: (factorId: string, code: string) => Promise<CodeOutcome>;
  // Ends the session on this device only.
  signOut: () => Promise<void>;
  // Calls the listener when the session changes; returns how to stop listening.
  onChange: (listener: () => void) => () => void;
  // The seed's email users against local Supabase. Only development builds have it.
  signInWithPassword?: (email: string, password: string) => Promise<PasswordOutcome>;
}
