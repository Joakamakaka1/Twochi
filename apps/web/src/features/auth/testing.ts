// The double of AuthPort for tests: Supabase Auth as far as this feature can tell.
// Factors belong to the person and outlive their sessions, as in the real one.
import type { Assurance, AuthPort, CodeOutcome, TotpEnrollment } from "./authPort";

interface Factor {
  id: string;
  verified: boolean;
}

export class FakeAuth implements AuthPort {
  // What the person's authenticator app shows right now.
  static readonly CODE = "123456";

  // Every code that reached Auth, in order.
  readonly codesReceived: string[] = [];

  #session: { userId: string; level: Assurance["level"] } | null = null;
  readonly #factors = new Map<string, Factor>();
  readonly #listeners = new Set<() => void>();

  // The person comes back from Google (or the development login): a first-factor session.
  arrive(userId: string): void {
    this.#session = { userId, level: "aal1" };
    this.#notify();
  }

  // The person already has a verified TOTP factor from an earlier sign-in.
  giveVerifiedTotp(userId: string): string {
    const factor = { id: `factor-${userId}`, verified: true };
    this.#factors.set(userId, factor);
    return factor.id;
  }

  assurance = (): Promise<Assurance | null> => {
    if (this.#session === null) return Promise.resolve(null);
    const factor = this.#factors.get(this.#session.userId);
    return Promise.resolve({
      userId: this.#session.userId,
      level: this.#session.level,
      totpFactorId: factor?.verified === true ? factor.id : null,
    });
  };

  accessToken = (): Promise<string | null> =>
    Promise.resolve(this.#session === null ? null : `jwt-${this.#session.userId}-${this.#session.level}`);

  signInWithGoogle = (): Promise<void> => Promise.resolve();

  enrollTotp = (): Promise<TotpEnrollment> => {
    const userId = this.#signedIn().userId;
    const factor = { id: `factor-${userId}`, verified: false };
    this.#factors.set(userId, factor);
    return Promise.resolve({ factorId: factor.id, qrCode: "data:image/svg+xml;utf-8,<svg/>", secret: "SECRET" });
  };

  verifyTotp = (factorId: string, code: string): Promise<CodeOutcome> => {
    this.codesReceived.push(code);
    const session = this.#signedIn();
    const factor = this.#factors.get(session.userId);
    if (factor?.id !== factorId || code !== FakeAuth.CODE) return Promise.resolve("wrong_code");
    factor.verified = true;
    this.#session = { ...session, level: "aal2" };
    this.#notify();
    return Promise.resolve("verified");
  };

  signOut = (): Promise<void> => {
    this.#session = null;
    this.#notify();
    return Promise.resolve();
  };

  onChange = (listener: () => void): (() => void) => {
    this.#listeners.add(listener);
    return () => this.#listeners.delete(listener);
  };

  #signedIn(): { userId: string; level: Assurance["level"] } {
    if (this.#session === null) throw new Error("FakeAuth: nobody is signed in");
    return this.#session;
  }

  #notify(): void {
    for (const listener of this.#listeners) listener();
  }
}
