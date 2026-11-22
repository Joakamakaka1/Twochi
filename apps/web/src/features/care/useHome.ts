import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { useApi } from "../../shared";
import type { CareAction, Pet } from "../../shared";
import { careActionMutation, careOutcomeText, careTap } from "./careActions";
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

export function useCareActions(petId: Pet["id"]) {
  const queryClient = useQueryClient();
  const mutation = useMutation(careActionMutation(useApi(), petId, queryClient));
  return {
    tap: (action: CareAction) => {
      mutation.mutate(careTap(action));
    },
    // The tap that failed, sent again with its own key.
    retry: () => {
      if (mutation.variables !== undefined) mutation.mutate(mutation.variables);
    },
    isPending: mutation.isPending,
    failed: mutation.isError,
    rejection: careOutcomeText(mutation.data),
  };
}
