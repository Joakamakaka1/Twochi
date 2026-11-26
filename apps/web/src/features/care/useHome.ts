import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { useApi } from "../../shared";
import type { CareAction, CareActionResult, Pet } from "../../shared";
import { careActionMutation, careFailureText, careOutcomeText, careTap, onHomeRead } from "./careActions";
import type { CareTap } from "./careActions";
import { homeQuery, refreshHomeOnForeground } from "./home";

export function useHome() {
  const queryClient = useQueryClient();
  useEffect(() => refreshHomeOnForeground(document, queryClient), [queryClient]);
  return useQuery(homeQuery(useApi()));
}

// The clock the bars are drawn at, ticking while Casa is open.
export function useNow(periodMs: number): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = setInterval(() => {
      setNow(new Date());
    }, periodMs);
    return () => {
      clearInterval(timer);
    };
  }, [periodMs]);
  return now;
}

/** Care taps for the pet; `onOutcome` hears each one the engine applied or refused. */
export function useCareActions(petId: Pet["id"], onOutcome: (action: CareAction, result: CareActionResult) => void) {
  const queryClient = useQueryClient();
  const mutation = useMutation(careActionMutation(useApi(), petId, queryClient));
  const { reset } = mutation;
  useEffect(() => onHomeRead(queryClient, reset), [queryClient, reset]);
  const send = (tap: CareTap) => {
    mutation.mutate(tap, {
      onSuccess: (result) => {
        onOutcome(tap.action, result);
      },
    });
  };
  return {
    // Ignored while a tap is in flight, as the disabled buttons are: touching the pet on
    // the scene lands here too.
    tap: (action: CareAction) => {
      if (!mutation.isPending) send(careTap(action));
    },
    // The tap that failed, sent again with its own key.
    retry: () => {
      if (mutation.variables !== undefined) send(mutation.variables);
    },
    isPending: mutation.isPending,
    failure: careFailureText(mutation.error),
    rejection: careOutcomeText(mutation.data),
  };
}
