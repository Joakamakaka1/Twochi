import { texts } from "../../shared";
import { DevSignInForm } from "./DevSignInForm";
import { useAuth, useGoogleSignIn } from "./useAuth";

export function SignInScreen() {
  const auth = useAuth();
  const google = useGoogleSignIn();
  return (
    <main>
      <h1>{texts.appName}</h1>
      <button
        type="button"
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
    </main>
  );
}
