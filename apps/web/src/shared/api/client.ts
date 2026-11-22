import { createApiClient } from "@twochi/api-client";
import type { ApiClient } from "@twochi/api-client";

import { createSignedFetch } from "./signedFetch";
import type { FetchLike, TokenSource } from "./signedFetch";

export type { ApiClient, Home, Pet } from "@twochi/api-client";

export interface ApiOptions {
  // Origin that serves /api: the page's own, in production and behind Vite's proxy.
  baseUrl: string;
  baseFetch?: FetchLike;
}

// The only way the front talks to the API: the generated client over the signed fetch.
export function createApi(token: TokenSource, options: ApiOptions): ApiClient {
  return createApiClient({ baseUrl: options.baseUrl, fetch: createSignedFetch(token, options.baseFetch) });
}

// The API refused or failed. Only the status and the problem's stable `code`: the rest
// of a problem body is never kept or shown.
export class ApiError extends Error {
  readonly status: number;
  readonly code: string | null;

  constructor(status: number, code: string | null = null) {
    super(`The API answered ${String(status)}`);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

export function isAuthFailure(_error: unknown): boolean {
  return false;
}

// What TanStack Query does on its own in a browser: three more tries, whatever failed.
export function retryApiRead(failureCount: number, _error: unknown): boolean {
  return failureCount < 3;
}
