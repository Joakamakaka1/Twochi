import type { MutationKey, QueryClient } from "@tanstack/react-query";
import { createApiClient } from "@twochi/api-client";
import type { ApiClient, components } from "@twochi/api-client";

import { createSignedFetch } from "./signedFetch";
import type { FetchLike, TokenSource } from "./signedFetch";

export type { ApiClient, Home, Pet } from "@twochi/api-client";

type Schemas = components["schemas"];
export type ActivityKey = Schemas["ActivityKey"];
export type Affinity = Schemas["Affinity"];
export type CareAction = Schemas["CareAction"];
export type CareActionResult = Schemas["CareActionOut"];
export type FoodKey = Schemas["FoodKey"];
// Every item of the catalogue: the contract keeps foods and activities apart.
export type ItemKey = FoodKey | ActivityKey;
export type Mood = Schemas["Mood"];
export type Need = Schemas["Need"];
export type Rejection = Schemas["Rejection"];
// The caller's own tastes (ADR 0015), and one rating of an item.
export type Tastes = Schemas["TastesOut"];
export type TasteRating = Schemas["TasteOut"];

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

// A write whose person has left: the gate emptied the mutation cache, and sending it
// again would go out with the next person's token.
export class LeftBehindError extends Error {
  constructor() {
    super("The person who made this write has left");
    this.name = "LeftBehindError";
  }
}

/**
 * Whether a write is still in the mutation cache under `mutationKey`, with these very
 * `variables`. Each attempt of a write checks it first, and fails with LeftBehindError
 * when the gate has emptied the cache.
 */
export function isStillWanted(queryClient: QueryClient, mutationKey: MutationKey, variables: unknown): boolean {
  return queryClient
    .getMutationCache()
    .findAll({ mutationKey })
    .some((mutation) => mutation.state.variables === variables);
}

// A write is sent again, with its same idempotency key, only when the API may not have
// applied it: a network failure or a 5xx. A duplicate never gets a 409: it waits on the
// pet's lock and receives the stored result (ADR 0009). Any other refusal would get the
// same answer again, and a write left behind by its person is never sent again.
export function retryApiWrite(failureCount: number, error: unknown): boolean {
  if (failureCount >= RETRIES || error instanceof LeftBehindError) return false;
  return !(error instanceof ApiError) || error.status >= 500;
}
