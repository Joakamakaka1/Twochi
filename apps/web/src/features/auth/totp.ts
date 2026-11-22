import type { AuthPort } from "./authPort";

// Why a code did not verify; the person can always try again.
export type CodeProblem = "malformed" | "wrong_code";

export function submitTotpCode(_auth: AuthPort, _factorId: string, _input: string): Promise<"verified" | CodeProblem> {
  return Promise.resolve("malformed");
}
