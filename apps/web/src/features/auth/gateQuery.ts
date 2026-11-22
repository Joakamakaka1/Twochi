import { queryOptions } from "@tanstack/react-query";
import type { QueryClient } from "@tanstack/react-query";

import type { AuthPort } from "./authPort";
import { resolveGate } from "./gate";

export const GATE_KEY = ["auth", "gate"] as const;

export function gateQuery(auth: AuthPort, _queryClient: QueryClient) {
  return queryOptions({ queryKey: GATE_KEY, queryFn: () => resolveGate(auth), staleTime: Infinity });
}

export function followAuth(_auth: AuthPort, _queryClient: QueryClient): () => void {
  return () => undefined;
}
