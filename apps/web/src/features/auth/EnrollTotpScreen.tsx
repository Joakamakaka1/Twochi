import { texts } from "../../shared";
import { SignOutButton } from "./SignOutButton";
import { TotpCodeForm } from "./TotpCodeForm";
import { useTotpEnrollment } from "./useAuth";

export function EnrollTotpScreen() {
  const enrollment = useTotpEnrollment();
  return (
    <main>
      <h1>{texts.auth.enrollTitle}</h1>
      {enrollment.data !== undefined ? (
        <>
          <p>{texts.auth.enrollSteps}</p>
          <img src={enrollment.data.qrCode} alt={texts.auth.enrollQrAlt} width={200} height={200} />
          <p>
            {texts.auth.enrollSecret} <code>{enrollment.data.secret}</code>
          </p>
          <TotpCodeForm factorId={enrollment.data.factorId} />
        </>
      ) : enrollment.isError ? (
        <>
          <p role="alert">{texts.failure}</p>
          <button type="button" onClick={() => void enrollment.refetch()}>
            {texts.retry}
          </button>
        </>
      ) : (
        <p>{texts.loading}</p>
      )}
      <SignOutButton />
    </main>
  );
}
