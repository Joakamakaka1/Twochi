import { createContext, use } from "react";
import type { ReactNode } from "react";

import type { ApiClient } from "./client";

const ApiContext = createContext<ApiClient | null>(null);

export function ApiProvider({ api, children }: { api: ApiClient; children: ReactNode }) {
  return <ApiContext value={api}>{children}</ApiContext>;
}

// The generated client, for the hooks that read or write the API.
export function useApi(): ApiClient {
  const api = use(ApiContext);
  if (api === null) throw new Error("useApi needs an ApiProvider above it");
  return api;
}
