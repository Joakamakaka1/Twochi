import { useQuery } from "@tanstack/react-query";

import { useApi } from "../../shared";
import { homeQuery } from "./home";

export function useHome() {
  return useQuery(homeQuery(useApi()));
}
