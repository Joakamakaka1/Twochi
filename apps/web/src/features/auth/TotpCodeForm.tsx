import { useState } from "react";

import { texts } from "../../shared";
import styles from "./TotpCodeForm.module.css";
import { useTotpCode } from "./useAuth";

export function TotpCodeForm({ factorId }: { factorId: string }) {
  const [input, setInput] = useState("");
  const code = useTotpCode(factorId);
  return (
    <form
      className={styles.form}
      onSubmit={(event) => {
        event.preventDefault();
        code.submit(input);
      }}
    >
      <label className={styles.field}>
        {texts.auth.code}
        <input
          className={styles.code}
          inputMode="numeric"
          autoComplete="one-time-code"
          required
          value={input}
          onChange={(event) => {
            setInput(event.target.value);
          }}
        />
      </label>
      <button type="submit" disabled={code.isPending}>
        {texts.auth.submitCode}
      </button>
      {code.problem !== null && <p role="alert">{texts.auth.codeProblems[code.problem]}</p>}
      {code.failed && <p role="alert">{texts.failure}</p>}
    </form>
  );
}
