import { texts } from "../../shared";
import { SignOutButton } from "./SignOutButton";
import { TotpCodeForm } from "./TotpCodeForm";

export function VerifyTotpScreen({ factorId }: { factorId: string }) {
  return (
    <main>
      <h1>{texts.auth.verifyTitle}</h1>
      <p>{texts.auth.verifySteps}</p>
      <TotpCodeForm factorId={factorId} />
      <SignOutButton />
    </main>
  );
}
