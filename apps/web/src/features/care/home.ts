import type { ApiClient, Home } from "../../shared";

export function readHome(_api: ApiClient): Promise<Home> {
  return Promise.resolve({ pet: null });
}
