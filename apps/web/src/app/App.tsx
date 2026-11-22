import { QueryClientProvider } from "@tanstack/react-query";

import { AuthGate, HomeScreen, SignOutButton } from "../features";
import { ApiProvider } from "../shared";
import type { Wiring } from "./wiring";

export function App({ wiring }: { wiring: Wiring }) {
  return (
    <QueryClientProvider client={wiring.queryClient}>
      <ApiProvider api={wiring.api}>
        <AuthGate auth={wiring.auth}>
          <main>
            <HomeScreen />
            <SignOutButton />
          </main>
        </AuthGate>
      </ApiProvider>
    </QueryClientProvider>
  );
}
