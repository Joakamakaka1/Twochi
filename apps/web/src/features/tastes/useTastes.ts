import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { isAuthFailure, useApi } from "../../shared";
import { rateTasteMutation, tastesQuery } from "./tastes";

export function useTastes() {
  return useQuery(tastesQuery(useApi()));
}

/** Rate one item; `failed` says the last rating did not save (after an auth failure the gate takes over). */
export function useRateTaste() {
  const queryClient = useQueryClient();
  const mutation = useMutation(rateTasteMutation(useApi(), queryClient));
  return { rate: mutation.mutate, failed: mutation.isError && !isAuthFailure(mutation.error) };
}
