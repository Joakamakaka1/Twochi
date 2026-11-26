import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { useApi } from "../../shared";
import type { CareAction, CareActionResult, Pet } from "../../shared";
import { careActionMutation, careFailureText, careTaps, onHomeRead } from "./careActions";
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
  const { mutate, reset } = mutation;
  // mutate, reset and onOutcome are stable, so the taps (and their lock) live as long as Casa.
  const taps = useMemo(() => careTaps({ mutate, reset }, onOutcome), [mutate, reset, onOutcome]);
  useEffect(() => onHomeRead(queryClient, taps.homeRead), [queryClient, taps]);
  return {
    tap: taps.tap,
    retry: taps.retry,
    isPending: mutation.isPending,
    failure: careFailureText(mutation.error),
  };
}
