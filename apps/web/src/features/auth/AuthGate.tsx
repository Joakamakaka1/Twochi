import { Fragment } from "react";
import type { ReactNode } from "react";

import { texts } from "../../shared";
import type { AuthPort } from "./authPort";
import { EnrollTotpScreen } from "./EnrollTotpScreen";
import { SignInScreen } from "./SignInScreen";
import { AuthContext, useGate } from "./useAuth";
import { VerifyTotpScreen } from "./VerifyTotpScreen";

interface AuthGateProps {
  auth: AuthPort;
  // The app: rendered only for a session at aal2.
  children: ReactNode;
}

export function AuthGate({ auth, children }: AuthGateProps) {
  const gate = useGate(auth);
  return <AuthContext value={auth}>{screen()}</AuthContext>;

  function screen(): ReactNode {
    if (gate.data === undefined) {
      if (!gate.isError) return <p>{texts.loading}</p>;
      return (
        <main>
          <p role="alert">{texts.failure}</p>
          <button type="button" onClick={() => void gate.refetch()}>
            {texts.retry}
          </button>
        </main>
      );
    }
    switch (gate.data.step) {
      case "sign_in":
        return <SignInScreen />;
      case "enroll_totp":
        return <EnrollTotpScreen />;
      case "verify_totp":
        return <VerifyTotpScreen factorId={gate.data.factorId} />;
      case "ready":
        // Keyed by person: another one never inherits what was on screen.
        return <Fragment key={gate.data.userId}>{children}</Fragment>;
    }
  }
}
