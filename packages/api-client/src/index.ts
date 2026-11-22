// The typed client of the Twochi API. `schema.d.ts` is generated from `openapi.json`
// (`just openapi`); a route or a field that changes there breaks the callers' `tsc`.
import createClient from "openapi-fetch";
import type { Client } from "openapi-fetch";

import type { components, paths } from "./schema";

export type { components, paths };
export type ApiClient = Client<paths>;
export type Home = components["schemas"]["HomeOut"];
export type Pet = components["schemas"]["PetOut"];

export interface ApiClientOptions {
  // Origin of the API; the paths already start with /api.
  baseUrl: string;
  // The front passes its signed fetch (JWT header and body hash).
  fetch: (request: Request) => Promise<Response>;
}

export function createApiClient(options: ApiClientOptions): ApiClient {
  return createClient<paths>(options);
}
