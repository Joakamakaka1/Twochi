import { queryOptions } from "@tanstack/react-query";
import type { QueryClient } from "@tanstack/react-query";

import { apiError, retryApiRead, texts } from "../../shared";
import type { ApiClient, Home, VisibilitySource } from "../../shared";

export const HOME_KEY = ["home"] as const;

export async function readHome(api: ApiClient): Promise<Home> {
  const { data, error, response } = await api.GET("/api/homes/me");
  if (data === undefined) throw apiError(response.status, error);
  return data;
}

export function homeQuery(api: ApiClient) {
  return queryOptions({ queryKey: HOME_KEY, queryFn: () => readHome(api), retry: retryApiRead });
}

export function refreshHomeOnForeground(_page: VisibilitySource, _queryClient: QueryClient): () => void {
  return () => undefined;
}

// Until both people have signed up there is no pet to care for.
export function homeHeadline(home: Home): string {
  return home.pet === null ? texts.care.petArrivesWithPartner : texts.care.caringFor(home.pet.name);
}
