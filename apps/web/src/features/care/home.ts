import { ApiError } from "../../shared";
import type { ApiClient, Home } from "../../shared";

export const HOME_KEY = ["home"] as const;

export async function readHome(api: ApiClient): Promise<Home> {
  const { data, response } = await api.GET("/api/homes/me");
  if (data === undefined) throw new ApiError(response.status);
  return data;
}

export function homeHeadline(_home: Home): string {
  return "";
}
