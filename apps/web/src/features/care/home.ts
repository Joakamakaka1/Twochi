import { queryOptions } from "@tanstack/react-query";
import type { QueryClient } from "@tanstack/react-query";

import { apiError, onForeground, retryApiRead, texts } from "../../shared";
import type { ApiClient, CareActionResult, Home, VisibilitySource } from "../../shared";

export const HOME_KEY = ["home"] as const;

export async function readHome(api: ApiClient): Promise<Home> {
  const { data, error, response } = await api.GET("/api/homes/me");
  if (data === undefined) throw apiError(response.status, error);
  return data;
}

export function homeQuery(api: ApiClient) {
  return queryOptions({
    queryKey: HOME_KEY,
    queryFn: () => readHome(api),
    retry: retryApiRead,
    // Coming back to the page is refreshHomeOnForeground's job; Query's own focus
    // refetch would read Casa a second time.
    refetchOnWindowFocus: false,
  });
}

// The page may have spent hours in the background, or the pet changed from another
// device: Casa is read again from the API instead of trusting the old read.
export function refreshHomeOnForeground(page: VisibilitySource, queryClient: QueryClient): () => void {
  return onForeground(page, () => {
    void queryClient.invalidateQueries({ queryKey: HOME_KEY });
  });
}

// Until both people have signed up there is no pet to care for.
export function homeHeadline(home: Home): string {
  return home.pet === null ? texts.care.petArrivesWithPartner : texts.care.caringFor(home.pet.name);
}

/**
 * Casa after a care action, without reading it again: the pet the response brings and,
 * when it gave an item, that item discovered with the reaction seen now. Without a Casa
 * in the cache there is nothing to update, and the cache stays as it is.
 */
export function homeAfterCare(home: Home | undefined, result: CareActionResult): Home | undefined {
  if (home === undefined) return undefined;
  const discovered = home.pet?.discovered ?? {};
  const { reaction } = result;
  return {
    pet: {
      ...result.pet,
      discovered: reaction === null ? discovered : { ...discovered, [reaction.item_key]: reaction.affinity },
    },
  };
}
