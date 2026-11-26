import { texts } from "../../shared";
import { AuthScreen } from "./AuthScreen";
import styles from "./EnrollTotpScreen.module.css";
import { TotpCodeForm } from "./TotpCodeForm";
import { useTotpEnrollment } from "./useAuth";

export function EnrollTotpScreen() {
  const enrollment = useTotpEnrollment();
  return (
    <AuthScreen title={texts.auth.enrollTitle} signOut>
      {enrollment.data !== undefined ? (
        <>
          <p>{texts.auth.enrollSteps}</p>
          <img
            className={styles.qr}
            src={enrollment.data.qrCode}
            alt={texts.auth.enrollQrAlt}
            width={200}
            height={200}
          />
          <p className={styles.secret}>
            {texts.auth.enrollSecret} <code className={styles.key}>{enrollment.data.secret}</code>
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
    </AuthScreen>
  );
}
