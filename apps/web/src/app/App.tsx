import { QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

import { AuthGate, HomeScreen, SignOutButton, TastesScreen } from "../features";
import { ApiProvider, texts } from "../shared";
import styles from "./App.module.css";
import type { Wiring } from "./wiring";

export function App({ wiring }: { wiring: Wiring }) {
  return (
    <QueryClientProvider client={wiring.queryClient}>
      <ApiProvider api={wiring.api}>
        <AuthGate auth={wiring.auth}>
          <Shell />
        </AuthGate>
      </ApiProvider>
    </QueryClientProvider>
  );
}

// The two screens of the app: Casa and «Tus gustos». Plain state, no router: inside the
// gate, so the next person who signs in starts in Casa.
type View = "home" | "tastes";

function Shell() {
  const [view, setView] = useState<View>("home");
  return (
    <div className={styles.shell}>
      <header className={styles.header}>
        <p className={styles.brand}>{texts.appName}</p>
        <div className={styles.actions}>
          <button
            type="button"
            className={styles.switch}
            onClick={() => {
              setView(view === "home" ? "tastes" : "home");
            }}
          >
            {view === "home" ? texts.tastes.open : texts.tastes.backHome}
          </button>
          <SignOutButton />
        </div>
      </header>
      <main className={styles.main}>{view === "home" ? <HomeScreen /> : <TastesScreen />}</main>
    </div>
  );
}
