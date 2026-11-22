import { describe, expect, it } from "vitest";

import { resolveGate } from "./gate";
import { FakeAuth } from "./testing";
import { submitTotpCode } from "./totp";

const ALICE = "00000000-0000-4000-8000-00000000a11c";

function atTheCodeScreen() {
  const auth = new FakeAuth();
  const factorId = auth.giveVerifiedTotp(ALICE);
  auth.arrive(ALICE);
  return { auth, factorId };
}

describe("submitTotpCode", () => {
  it("says a wrong code is wrong and lets the person try again", async () => {
    const { auth, factorId } = atTheCodeScreen();

    expect(await submitTotpCode(auth, factorId, "000000")).toBe("wrong_code");
    expect(await resolveGate(auth)).toEqual({ step: "verify_totp", factorId });

    expect(await submitTotpCode(auth, factorId, FakeAuth.CODE)).toBe("verified");
    expect(await resolveGate(auth)).toEqual({ step: "ready", userId: ALICE });
  });

  it("verifies the first code of a factor just enrolled, and the next sign-in only asks for the code", async () => {
    const auth = new FakeAuth();
    auth.arrive(ALICE);
    const { factorId } = await auth.enrollTotp();

    expect(await submitTotpCode(auth, factorId, FakeAuth.CODE)).toBe("verified");
    expect(await resolveGate(auth)).toEqual({ step: "ready", userId: ALICE });

    await auth.signOut();
    auth.arrive(ALICE);
    expect(await resolveGate(auth)).toEqual({ step: "verify_totp", factorId });
  });
});

describe("submitTotpCode with what people type", () => {
  it("accepts the code with the space authenticator apps show in the middle", async () => {
    const { auth, factorId } = atTheCodeScreen();

    expect(await submitTotpCode(auth, factorId, " 123 456 ")).toBe("verified");
    expect(auth.codesReceived).toEqual(["123456"]);
  });

  it.each(["", "12345", "1234567", "12345a", "١٢٣٤٥٦"])("never sends Auth %j, which is not six digits", async (input) => {
    const { auth, factorId } = atTheCodeScreen();

    expect(await submitTotpCode(auth, factorId, input)).toBe("malformed");
    expect(auth.codesReceived).toEqual([]);
  });
});
