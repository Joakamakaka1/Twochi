import type { AuthPort } from "./authPort";

// Why a code did not verify; the person can always try again.
export type CodeProblem = "malformed" | "wrong_code";

const SIX_DIGITS = /^[0-9]{6}$/;

// Authenticator apps show the code as "123 456". What is not six digits never reaches
// Auth, so a slip of the finger does not count against its rate limit.
export async function submitTotpCode(auth: AuthPort, factorId: string, input: string): Promise<"verified" | CodeProblem> {
  const code = input.replace(/\s/g, "");
  if (!SIX_DIGITS.test(code)) return "malformed";
  return auth.verifyTotp(factorId, code);
}
