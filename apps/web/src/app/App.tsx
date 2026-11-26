import { QueryClientProvider } from "@tanstack/react-query";

import { AuthGate, HomeScreen, SignOutButton } from "../features";
import { ApiProvider, texts } from "../shared";
import styles from "./App.module.css";
import type { Wiring } from "./wiring";

export function App({ wiring }: { wiring: Wiring }) {
  return (
    <QueryClientProvider client={wiring.queryClient}>
      <ApiProvider api={wiring.api}>
        <AuthGate auth={wiring.auth}>
          <div className={styles.shell}>
            <header className={styles.header}>
              <p className={styles.brand}>{texts.appName}</p>
              <SignOutButton />
            </header>
            <main className={styles.main}>
              <HomeScreen />
            </main>
          </div>
        </AuthGate>
      </ApiProvider>
    </QueryClientProvider>
  );
}
