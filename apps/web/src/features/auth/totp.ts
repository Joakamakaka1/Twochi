import type { AuthPort } from "./authPort";

// Why a code did not verify; the person can always try again.
export type CodeProblem = "malformed" | "wrong_code";

export function submitTotpCode(auth: AuthPort, factorId: string, input: string): Promise<"verified" | CodeProblem> {
  return auth.verifyTotp(factorId, input);
}
