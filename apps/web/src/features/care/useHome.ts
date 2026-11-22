import { useQuery } from "@tanstack/react-query";

import { useApi } from "../../shared";
import { HOME_KEY, readHome } from "./home";

export function useHome() {
  const api = useApi();
  return useQuery({ queryKey: HOME_KEY, queryFn: () => readHome(api) });
}
