import { texts } from "../../shared";
import { DevSignInForm } from "./DevSignInForm";
import styles from "./SignInScreen.module.css";
import { useAuth, useGoogleSignIn } from "./useAuth";

export function SignInScreen() {
  const auth = useAuth();
  const google = useGoogleSignIn();
  return (
    <main className={styles.screen}>
      <div className={styles.hero}>
        <h1 className={styles.wordmark}>{texts.appName}</h1>
      </div>
      <div className={styles.actions}>
        <button
          type="button"
          className={styles.google}
          disabled={google.isPending}
          onClick={() => {
            google.mutate();
          }}
        >
          {texts.auth.signInWithGoogle}
        </button>
        {google.isError && <p role="alert">{texts.failure}</p>}
        {import.meta.env.DEV && auth.signInWithPassword !== undefined && (
          <DevSignInForm signIn={auth.signInWithPassword} />
        )}
      </div>
    </main>
  );
}
