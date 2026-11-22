// Composition: the only module that reads the build's configuration. Runs once per
// page load and hands the adapters to App.
import { QueryClient } from "@tanstack/react-query";

import { createSupabaseAuth } from "../features";
import type { AuthPort } from "../features";
import { createApi } from "../shared";
import type { ApiClient } from "../shared";

export interface Wiring {
  auth: AuthPort;
  api: ApiClient;
  queryClient: QueryClient;
}

function required(name: string, value: string | undefined): string {
  if (value === undefined || value === "") throw new Error(`${name} is not set for this build`);
  return value;
}

export function wire(): Wiring {
  const auth = createSupabaseAuth({
    url: required("VITE_SUPABASE_URL", import.meta.env.VITE_SUPABASE_URL),
    publishableKey: required("VITE_SUPABASE_PUBLISHABLE_KEY", import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY),
    redirectTo: window.location.origin,
  });
  // /api is served from the page's own origin: CloudFront in production, Vite's proxy
  // in development.
  const api = createApi(auth.accessToken, { baseUrl: window.location.origin });
  return { auth, api, queryClient: new QueryClient() };
}
