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

const PROBLEM_CODE = /^[a-z_]{1,64}$/;

// From a response the generated client could not read as data: its status and, when the
// body is one of the API's problems (application/problem+json), its `code`.
export function apiError(status: number, body: unknown): ApiError {
  const code = typeof body === "object" && body !== null && "code" in body ? body.code : null;
  return new ApiError(status, typeof code === "string" && PROBLEM_CODE.test(code) ? code : null);
}

// The API did not accept the token: nobody is signed in (401) or this session lacks
// the second factor (403 mfa_required). The gate resolves again on it.
export function isAuthFailure(error: unknown): boolean {
  if (!(error instanceof ApiError)) return false;
  return error.status === 401 || (error.status === 403 && error.code === "mfa_required");
}

const RETRIES = 3;

// TanStack Query's own three retries, except after an auth failure: the same token
// would get the same answer, and the person would wait for nothing.
export function retryApiRead(failureCount: number, error: unknown): boolean {
  return failureCount < RETRIES && !isAuthFailure(error);
}
