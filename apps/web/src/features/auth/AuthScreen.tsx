import type { ReactNode } from "react";

import styles from "./AuthScreen.module.css";
import { SignOutButton } from "./SignOutButton";

interface AuthScreenProps {
  title?: string;
  // Every step after signing in offers a way out.
  signOut?: boolean;
  children: ReactNode;
}

// The frame every step before Casa shares: one card in a phone-wide column.
export function AuthScreen({ title, signOut = false, children }: AuthScreenProps) {
  return (
    <main className={styles.screen}>
      <div className={styles.card}>
        {title !== undefined && <h1 className={styles.title}>{title}</h1>}
        {children}
      </div>
      {signOut && <SignOutButton />}
    </main>
  );
}
