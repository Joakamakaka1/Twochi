import { texts } from "../../shared";
import { AuthScreen } from "./AuthScreen";
import { TotpCodeForm } from "./TotpCodeForm";

export function VerifyTotpScreen({ factorId }: { factorId: string }) {
  return (
    <AuthScreen title={texts.auth.verifyTitle} signOut>
      <p>{texts.auth.verifySteps}</p>
      <TotpCodeForm factorId={factorId} />
    </AuthScreen>
  );
}
