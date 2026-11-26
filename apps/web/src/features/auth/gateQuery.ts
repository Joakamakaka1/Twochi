import { queryOptions } from "@tanstack/react-query";
import type { QueryClient } from "@tanstack/react-query";

import { isAuthFailure } from "../../shared";
import type { AuthPort } from "./authPort";
import { resolveGate } from "./gate";
import type { Gate } from "./gate";

const AUTH_SCOPE = "auth";
export const GATE_KEY = [AUTH_SCOPE, "gate"] as const;
// The QR and its secret, kept only while the enrollment screen shows them.
export const TOTP_ENROLLMENT_KEY = [AUTH_SCOPE, "totp_enrollment"] as const;

// The gate lives in the query cache and never goes stale by time: only a change of
// session resolves it again (followAuth).
export function gateQuery(auth: AuthPort, queryClient: QueryClient) {
  return queryOptions({
    queryKey: GATE_KEY,
    queryFn: async (): Promise<Gate> => {
      const before = queryClient.getQueryData<Gate>(GATE_KEY);
      const gate = await resolveGate(auth);
      if (!isSamePersonInside(before, gate)) forgetPerson(queryClient);
      return gate;
    },
    staleTime: Infinity,
  });
}

// A change of session is a signal, as a Realtime event is: it only invalidates. The API
// refusing the token, on a read or on a write, is the same signal, and can come first:
// another tab signed in again, or a refresh failed, and Auth's event has not reached
// this tab yet.
export function followAuth(auth: AuthPort, queryClient: QueryClient): () => void {
  const resolveAgain = () => {
    void queryClient.invalidateQueries({ queryKey: GATE_KEY });
  };
  const stopAuth = auth.onChange(resolveAgain);
  const stopReads = queryClient.getQueryCache().subscribe((event) => {
    if (event.type !== "updated" || event.action.type !== "error") return;
    if (isAuthFailure(event.action.error)) resolveAgain();
  });
  const stopWrites = queryClient.getMutationCache().subscribe((event) => {
    if (event.type !== "updated" || event.action.type !== "error") return;
    if (isAuthFailure(event.action.error)) resolveAgain();
  });
  return () => {
    stopAuth();
    stopReads();
    stopWrites();
  };
}

function isSamePersonInside(before: Gate | undefined, gate: Gate): boolean {
  if (gate.step !== "ready") return false;
  return before?.step !== "ready" || before.userId === gate.userId;
}

// Whatever one person loaded must never be shown to the next one on this device, and
// nothing they wrote may be retried with the next one's token.
function forgetPerson(queryClient: QueryClient): void {
  queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== AUTH_SCOPE });
  queryClient.getMutationCache().clear();
}
