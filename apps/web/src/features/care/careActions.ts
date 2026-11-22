import { mutationOptions } from "@tanstack/react-query";
import type { QueryClient } from "@tanstack/react-query";

import { apiError, retryApiWrite, texts } from "../../shared";
import type { ApiClient, CareAction, CareActionResult, Home, Pet } from "../../shared";
import { HOME_KEY } from "./home";

/** One tap on a care button: its action and the key that names it on every retry. */
export interface CareTap {
  action: CareAction;
  idempotency_key: string;
}

/** A new tap, with a key of its own (a UUID fits the API's `[A-Za-z0-9_-]{1,64}`). */
export function careTap(action: CareAction): CareTap {
  return { action, idempotency_key: crypto.randomUUID() };
}

export async function sendCareAction(api: ApiClient, petId: Pet["id"], tap: CareTap): Promise<CareActionResult> {
  const { data, error, response } = await api.POST("/api/pets/{pet_id}/care-actions", {
    params: { path: { pet_id: petId } },
    body: tap,
  });
  if (data === undefined) throw apiError(response.status, error);
  return data;
}

// The mutation keeps the tap as its variables, so each retry sends the same key.
export function careActionMutation(api: ApiClient, petId: Pet["id"], queryClient: QueryClient) {
  return mutationOptions({
    mutationFn: (tap: CareTap) => sendCareAction(api, petId, tap),
    retry: retryApiWrite,
    // A read of Casa in flight would answer with the pet before this action.
    onMutate: () => queryClient.cancelQueries({ queryKey: HOME_KEY }),
    // Applied or refused, the response brings the pet as it is now.
    onSuccess: (result) => {
      queryClient.setQueryData<Home>(HOME_KEY, { pet: result.pet });
    },
  });
}

/** What Casa says after a tap: why the engine refused it, or nothing. */
export function careOutcomeText(result: CareActionResult | undefined): string | null {
  if (result?.rejection == null) return null;
  return texts.care.rejections[result.rejection];
}
