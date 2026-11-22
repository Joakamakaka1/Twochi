// The AuthPort on Supabase Auth: the only module of the front that imports supabase-js.
import { createClient, isAuthApiError, isAuthSessionMissingError } from "@supabase/supabase-js";

import type { AuthPort } from "./authPort";

export interface SupabaseAuthConfig {
  // The project URL and its publishable key: both public by design.
  url: string;
  publishableKey: string;
  // Where Google sends the person back: this app's origin, allowed in Supabase Auth.
  redirectTo: string;
}

// What Auth answers when the session no longer exists there: signed out elsewhere,
// or the person was removed.
const SESSION_GONE = [401, 403, 404];

function isSessionGone(error: unknown): boolean {
  return isAuthSessionMissingError(error) || (isAuthApiError(error) && SESSION_GONE.includes(error.status));
}

export function createSupabaseAuth(config: SupabaseAuthConfig): AuthPort {
  // The session is kept in localStorage, so opening the app again does not ask for the
  // code. PKCE keeps tokens out of the redirect URL: Google returns a one-use code.
  const { auth } = createClient(config.url, config.publishableKey, { auth: { flowType: "pkce" } });

  return {
    assurance: async () => {
      const session = await auth.getSession();
      if (session.error !== null) throw session.error;
      if (session.data.session === null) return null;

      // Asks the server, so a session that is gone there is noticed here.
      const factors = await auth.mfa.listFactors();
      if (factors.error !== null) {
        if (!isSessionGone(factors.error)) throw factors.error;
        await auth.signOut({ scope: "local" });
        return null;
      }
      const assurance = await auth.mfa.getAuthenticatorAssuranceLevel();
      if (assurance.error !== null) throw assurance.error;

      return {
        userId: session.data.session.user.id,
        level: assurance.data.currentLevel === "aal2" ? "aal2" : "aal1",
        totpFactorId: factors.data.totp[0]?.id ?? null,
      };
    },

    accessToken: async () => {
      const { data } = await auth.getSession();
      return data.session?.access_token ?? null;
    },

    signInWithGoogle: async () => {
      const { error } = await auth.signInWithOAuth({ provider: "google", options: { redirectTo: config.redirectTo } });
      if (error !== null) throw error;
    },

    enrollTotp: async () => {
      // Leftovers of an enrollment cut short would pile up against the factor limit.
      const factors = await auth.mfa.listFactors();
      if (factors.error !== null) throw factors.error;
      for (const factor of factors.data.all) {
        if (factor.factor_type !== "totp" || factor.status !== "unverified") continue;
        const { error } = await auth.mfa.unenroll({ factorId: factor.id });
        if (error !== null) throw error;
      }
      const { data, error } = await auth.mfa.enroll({ factorType: "totp", issuer: "Twochi" });
      if (error !== null) throw error;
      return { factorId: data.id, qrCode: data.totp.qr_code, secret: data.totp.secret };
    },

    verifyTotp: async (factorId, code) => {
      const { error } = await auth.mfa.challengeAndVerify({ factorId, code });
      if (error === null) return "verified";
      if (error.code === "mfa_verification_failed") return "wrong_code";
      throw error;
    },

    signOut: async () => {
      const { error } = await auth.signOut({ scope: "local" });
      if (error !== null) throw error;
    },

    onChange: (listener) => {
      // Supabase calls back while it holds its session lock: the listener runs in a
      // later task, so whatever it reads from the session does not wait on that lock.
      const { data } = auth.onAuthStateChange(() => {
        setTimeout(listener, 0);
      });
      return () => {
        data.subscription.unsubscribe();
      };
    },

    // Email and password are the seed's users on local Supabase. `import.meta.env.DEV`
    // is a constant at build time, so a production bundle has no trace of this.
    signInWithPassword: import.meta.env.DEV
      ? async (email, password) => {
          const { error } = await auth.signInWithPassword({ email, password });
          if (error === null) return "signed_in";
          if (error.code === "invalid_credentials") return "wrong_credentials";
          throw error;
        }
      : undefined,
  };
}
