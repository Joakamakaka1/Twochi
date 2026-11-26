import { texts } from "../../shared";
import styles from "./SignOutButton.module.css";
import { useSignOut } from "./useAuth";

export function SignOutButton() {
  const signOut = useSignOut();
  return (
    <div className={styles.signOut}>
      <button
        type="button"
        className={styles.button}
        disabled={signOut.isPending}
        onClick={() => {
          signOut.mutate();
        }}
      >
        {texts.auth.signOut}
      </button>
      {signOut.isError && <p role="alert">{texts.failure}</p>}
    </div>
  );
}
