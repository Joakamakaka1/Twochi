import { mutationOptions, queryOptions } from "@tanstack/react-query";
import type { QueryClient } from "@tanstack/react-query";

import {
  ACTIVITIES,
  AFFINITY_FACES,
  apiError,
  FOODS,
  isStillWanted,
  ITEM_ICONS,
  LeftBehindError,
  retryApiRead,
  retryApiWrite,
  texts,
} from "../../shared";
import type { Affinity, ApiClient, ItemKey, TasteRating, Tastes } from "../../shared";

// Only the caller's own tastes: the API has no route to the ones of the pet they care
// for (ADR 0015). Another person's are dropped with the rest of the cache at sign-out.
export const TASTES_KEY = ["tastes"] as const;

export async function readTastes(api: ApiClient): Promise<Tastes> {
  const { data, error, response } = await api.GET("/api/tastes/me");
  if (data === undefined) throw apiError(response.status, error);
  return data;
}

export function tastesQuery(api: ApiClient) {
  return queryOptions({ queryKey: TASTES_KEY, queryFn: () => readTastes(api), retry: retryApiRead });
}

export async function sendTaste(api: ApiClient, rating: TasteRating): Promise<TasteRating> {
  const { data, error, response } = await api.PUT("/api/tastes/me/{item_key}", {
    params: { path: { item_key: rating.item_key } },
    body: { affinity: rating.affinity },
  });
  if (data === undefined) throw apiError(response.status, error);
  return data;
}

function withTaste(tastes: Tastes, rating: TasteRating): Tastes {
  return { ...tastes, tastes: { ...tastes.tastes, [rating.item_key]: rating.affinity } };
}

const RATE_TASTE_KEY = ["tastes", "rate"] as const;

// The clients whose series of ratings had a failure: their tastes are read again once
// the series ends.
const failedSeries = new WeakSet<QueryClient>();

// Each tap saves at once. The face moves before the API answers; a rating sent again
// sets the same value, so a retry is safe. Ratings go out one at a time, in the order
// tapped, so a retry never lands after a later tap. If one fails, the tastes are read
// again once none is left in flight, and the faces show what is stored.
export function rateTasteMutation(api: ApiClient, queryClient: QueryClient) {
  return mutationOptions({
    mutationKey: RATE_TASTE_KEY,
    scope: { id: "tastes" },
    mutationFn: (rating: TasteRating) => {
      if (!isStillWanted(queryClient, RATE_TASTE_KEY, rating)) return Promise.reject(new LeftBehindError());
      return sendTaste(api, rating);
    },
    retry: retryApiWrite,
    onMutate: async (rating) => {
      // A read in flight would answer with the tastes before this rating.
      await queryClient.cancelQueries({ queryKey: TASTES_KEY });
      const tastes = queryClient.getQueryData<Tastes>(TASTES_KEY);
      // Nothing to move once the person has left: the next one's cache is theirs.
      if (tastes !== undefined) queryClient.setQueryData<Tastes>(TASTES_KEY, withTaste(tastes, rating));
    },
    onError: () => {
      failedSeries.add(queryClient);
    },
    // This rating still counts as pending here; the ones queued behind it too.
    onSettled: async () => {
      if (queryClient.isMutating({ mutationKey: RATE_TASTE_KEY }) > 1) return;
      if (!failedSeries.delete(queryClient)) return;
      await queryClient.invalidateQueries({ queryKey: TASTES_KEY });
    },
  });
}

/** One item of «Tus gustos»: what it is and how its person rated it (neutral if never). */
export interface TasteRow {
  key: ItemKey;
  icon: string;
  name: string;
  affinity: Affinity;
}

export interface TasteSection {
  kind: "food" | "activity";
  title: string;
  items: TasteRow[];
}

/** The catalogue by kind, foods first, each item with the caller's rating. */
export function tasteSections(tastes: Tastes["tastes"]): TasteSection[] {
  const rows = (keys: readonly ItemKey[]): TasteRow[] =>
    keys.map((key) => ({
      key,
      icon: ITEM_ICONS[key],
      name: texts.care.items[key],
      affinity: tastes[key] ?? 0,
    }));
  return [
    { kind: "food", title: texts.tastes.kinds.food, items: rows(FOODS) },
    { kind: "activity", title: texts.tastes.kinds.activity, items: rows(ACTIVITIES) },
  ];
}

/** A face of the selector: one step from «lo odio» to «me encanta». */
export interface Face {
  affinity: Affinity;
  icon: string;
  label: string;
}

const AFFINITIES: readonly Affinity[] = [-2, -1, 0, 1, 2];

export const FACES: readonly Face[] = AFFINITIES.map((affinity) => ({
  affinity,
  icon: AFFINITY_FACES[affinity],
  label: texts.tastes.faces[affinity],
}));

/** Until the pet is born, the list shows with the usual notice and nothing to save. */
export function tastesNotice(tastes: Tastes): string | null {
  return tastes.pet_id === null ? texts.care.petArrivesWithPartner : null;
}
