import { mutationOptions } from "@tanstack/react-query";
import type { QueryClient } from "@tanstack/react-query";

import { apiError } from "../../shared";
import type { ApiClient, CareAction, CareActionResult, Pet } from "../../shared";

export interface CareTap {
  action: CareAction;
  idempotency_key: string;
}

export function careTap(action: CareAction): CareTap {
  return { action, idempotency_key: "tap" };
}

export async function sendCareAction(api: ApiClient, petId: Pet["id"], tap: CareTap): Promise<CareActionResult> {
  const { data, error, response } = await api.POST("/api/pets/{pet_id}/care-actions", {
    params: { path: { pet_id: petId } },
    body: tap,
  });
  if (data === undefined) throw apiError(response.status, error);
  return data;
}

export function careActionMutation(api: ApiClient, petId: Pet["id"], _queryClient: QueryClient) {
  return mutationOptions({
    mutationFn: (tap: CareTap) => sendCareAction(api, petId, tap),
    retry: false,
  });
}

export function careOutcomeText(_result: CareActionResult | undefined): string | null {
  return null;
}
