import { hashKey, mutationOptions } from "@tanstack/react-query";
import type { QueryClient } from "@tanstack/react-query";

import { apiError, isAuthFailure, retryApiWrite, texts } from "../../shared";
import type { ApiClient, CareAction, CareActionResult, Home, ItemKey, Pet } from "../../shared";
import { HOME_KEY } from "./home";

/**
 * One tap on a care button: its action, the item chosen in the tray when feeding or
 * playing, and the key that names it on every retry.
 */
export interface CareTap {
  action: CareAction;
  idempotency_key: string;
  item_key?: ItemKey;
}

/** A new tap, with a key of its own (a UUID fits the API's `[A-Za-z0-9_-]{1,64}`). */
export function careTap(action: CareAction, item?: ItemKey): CareTap {
  const tap = { action, idempotency_key: crypto.randomUUID() };
  return item === undefined ? tap : { ...tap, item_key: item };
}

export async function sendCareAction(api: ApiClient, petId: Pet["id"], tap: CareTap): Promise<CareActionResult> {
  const { data, error, response } = await api.POST("/api/pets/{pet_id}/care-actions", {
    params: { path: { pet_id: petId } },
    body: tap,
  });
  if (data === undefined) throw apiError(response.status, error);
  return data;
}

// The Casa this tap was made from: signing out removes it, and the next person's is
// another one.
function currentHome(queryClient: QueryClient) {
  return queryClient.getQueryCache().find<Home>({ queryKey: HOME_KEY, exact: true });
}

// The mutation keeps the tap as its variables, so each retry sends the same key.
export function careActionMutation(api: ApiClient, petId: Pet["id"], queryClient: QueryClient) {
  return mutationOptions({
    mutationFn: (tap: CareTap) => sendCareAction(api, petId, tap),
    retry: retryApiWrite,
    onMutate: async () => {
      // A read of Casa in flight would answer with the pet before this action.
      await queryClient.cancelQueries({ queryKey: HOME_KEY });
      return { home: currentHome(queryClient) };
    },
    // Applied or refused, the response brings the pet as it is now; it goes into the
    // Casa it was tapped from, and nowhere once that person has left.
    onSuccess: (result, _tap, sent) => {
      if (sent.home === undefined || currentHome(queryClient) !== sent.home) return;
      queryClient.setQueryData<Home>(HOME_KEY, { pet: result.pet });
    },
  });
}

/** The care-action mutation as Casa's taps use it: useMutation's `mutate` and `reset`. */
export interface CareMutation {
  mutate: (
    tap: CareTap,
    callbacks: { onSuccess: (result: CareActionResult) => void; onSettled: () => void },
  ) => void;
  reset: () => void;
}

/** Casa's care taps, the button's and the figure's, over the mutation. */
export interface CareTaps {
  tap: (action: CareAction, item?: ItemKey) => void;
  /** The tap that failed, sent again with its own key. */
  retry: () => void;
  /** Casa was read again from the API (see onHomeRead). */
  homeRead: () => void;
}

/**
 * One tap in flight at a time: the figure and the button can land in the same task,
 * before a render disables the buttons. `onOutcome` hears each tap the engine applied
 * or refused.
 */
export function careTaps(mutation: CareMutation, onOutcome: (action: CareAction, result: CareActionResult) => void): CareTaps {
  let inFlight = false;
  let last: CareTap | undefined;
  const send = (tap: CareTap) => {
    inFlight = true;
    last = tap;
    mutation.mutate(tap, {
      onSuccess: (result) => {
        onOutcome(tap.action, result);
      },
      onSettled: () => {
        inFlight = false;
      },
    });
  };
  return {
    tap: (action, item) => {
      if (!inFlight) send(careTap(action, item));
    },
    retry: () => {
      if (!inFlight && last !== undefined) send(last);
    },
    // The reset clears a refusal's text, which is about the pet before this read. A tap
    // in flight has no text yet, and resetting would detach it: its reaction and the end
    // of the lock would never arrive.
    homeRead: () => {
      if (!inFlight) mutation.reset();
    },
  };
}

/** What Casa says after a tap: why the engine refused it, how the pet took what it was given, or nothing. */
export function careOutcomeText(result: CareActionResult | undefined): string | null {
  if (result === undefined) return null;
  if (result.rejection !== null) return texts.care.rejections[result.rejection];
  if (result.reaction === null) return null;
  const { item_key, affinity } = result.reaction;
  return texts.care.reactionTo(texts.care.items[item_key], texts.care.reactions[affinity]);
}

/** What Casa says when a tap failed: nothing after an auth failure, as the gate takes over. */
export function careFailureText(error: unknown): string | null {
  return error === null || isAuthFailure(error) ? null : texts.failure;
}

/**
 * Calls `read` each time Casa is read again from the API, not when a care response
 * writes it; returns how to stop. A refusal's text is about the pet before that read.
 */
export function onHomeRead(queryClient: QueryClient, read: () => void): () => void {
  const homeHash = hashKey(HOME_KEY);
  return queryClient.getQueryCache().subscribe((event) => {
    if (event.type !== "updated" || event.query.queryHash !== homeHash) return;
    if (event.action.type === "success" && event.action.manual !== true) read();
  });
}
