// Development only: SignInScreen renders it behind `import.meta.env.DEV`, so a
// production build drops this module.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { devTexts, texts } from "../../shared";
import type { AuthPort } from "./authPort";
import styles from "./DevSignInForm.module.css";
import { GATE_KEY } from "./gateQuery";

type PasswordSignIn = NonNullable<AuthPort["signInWithPassword"]>;

function usePasswordSignIn(signIn: PasswordSignIn) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (credentials: { email: string; password: string }) => signIn(credentials.email, credentials.password),
    // The mutation cache keeps what was typed: it goes when the form does.
    gcTime: 0,
    onSuccess: async (outcome) => {
      if (outcome === "signed_in") await queryClient.invalidateQueries({ queryKey: GATE_KEY });
    },
  });
}

export function DevSignInForm({ signIn }: { signIn: PasswordSignIn }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const attempt = usePasswordSignIn(signIn);
  return (
    <form
      className={styles.form}
      onSubmit={(event) => {
        event.preventDefault();
        attempt.mutate({ email, password });
      }}
    >
      <h2 className={styles.title}>{devTexts.title}</h2>
      <label className={styles.field}>
        {devTexts.email}
        <input
          type="email"
          autoComplete="username"
          required
          value={email}
          onChange={(event) => {
            setEmail(event.target.value);
          }}
        />
      </label>
      <label className={styles.field}>
        {devTexts.password}
        <input
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(event) => {
            setPassword(event.target.value);
          }}
        />
      </label>
      <button type="submit" className={styles.submit} disabled={attempt.isPending}>
        {devTexts.submit}
      </button>
      {attempt.data === "wrong_credentials" && <p role="alert">{devTexts.wrongCredentials}</p>}
      {attempt.isError && <p role="alert">{texts.failure}</p>}
    </form>
  );
}
