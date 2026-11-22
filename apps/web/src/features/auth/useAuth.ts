import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, use, useEffect } from "react";

import type { AuthPort } from "./authPort";
import { followAuth, GATE_KEY, gateQuery, TOTP_ENROLLMENT_KEY } from "./gateQuery";
import { submitTotpCode } from "./totp";

// Set by AuthGate for everything it renders.
export const AuthContext = createContext<AuthPort | null>(null);

export function useAuth(): AuthPort {
  const auth = use(AuthContext);
  if (auth === null) throw new Error("useAuth needs an AuthGate above it");
  return auth;
}

export function useGate(auth: AuthPort) {
  const queryClient = useQueryClient();
  useEffect(() => followAuth(auth, queryClient), [auth, queryClient]);
  return useQuery(gateQuery(auth, queryClient));
}

// Each action resolves the gate again itself, without waiting for Auth's event.
function useGateRefresh() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: GATE_KEY });
}

export function useGoogleSignIn() {
  const auth = useAuth();
  return useMutation({ mutationFn: () => auth.signInWithGoogle() });
}

export function useSignOut() {
  const auth = useAuth();
  return useMutation({ mutationFn: () => auth.signOut(), onSuccess: useGateRefresh() });
}

export function useTotpEnrollment() {
  const auth = useAuth();
  return useQuery({
    queryKey: TOTP_ENROLLMENT_KEY,
    queryFn: () => auth.enrollTotp(),
    // One factor per visit to the screen, and the secret leaves the cache with it.
    staleTime: Infinity,
    gcTime: 0,
    retry: false,
  });
}

export function useTotpCode(factorId: string) {
  const auth = useAuth();
  const refreshGate = useGateRefresh();
  const mutation = useMutation({
    mutationFn: (input: string) => submitTotpCode(auth, factorId, input),
    // The mutation cache keeps what was typed: it goes when the form does.
    gcTime: 0,
    onSuccess: async (outcome) => {
      if (outcome === "verified") await refreshGate();
    },
  });
  return {
    submit: mutation.mutate,
    isPending: mutation.isPending,
    // Why the last code did not verify, if the person has to type another.
    problem: mutation.data === undefined || mutation.data === "verified" ? null : mutation.data,
    failed: mutation.isError,
  };
}
