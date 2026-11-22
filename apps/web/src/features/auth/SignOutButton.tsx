import { texts } from "../../shared";
import { useSignOut } from "./useAuth";

export function SignOutButton() {
  const signOut = useSignOut();
  return (
    <>
      <button
        type="button"
        disabled={signOut.isPending}
        onClick={() => {
          signOut.mutate();
        }}
      >
        {texts.auth.signOut}
      </button>
      {signOut.isError && <p role="alert">{texts.failure}</p>}
    </>
  );
}
