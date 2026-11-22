import { queryOptions } from "@tanstack/react-query";

import { ApiError, retryApiRead, texts } from "../../shared";
import type { ApiClient, Home } from "../../shared";

export const HOME_KEY = ["home"] as const;

export async function readHome(api: ApiClient): Promise<Home> {
  const { data, response } = await api.GET("/api/homes/me");
  if (data === undefined) throw new ApiError(response.status);
  return data;
}

export function homeQuery(api: ApiClient) {
  return queryOptions({ queryKey: HOME_KEY, queryFn: () => readHome(api), retry: retryApiRead });
}

// Until both people have signed up there is no pet to care for.
export function homeHeadline(home: Home): string {
  return home.pet === null ? texts.care.petArrivesWithPartner : texts.care.caringFor(home.pet.name);
}
