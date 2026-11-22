import { describe, expect, it } from "vitest";

import { resolveGate } from "./gate";
import { FakeAuth } from "./testing";

const ALICE = "00000000-0000-4000-8000-00000000a11c";

describe("resolveGate", () => {
  it("sends an aal1 session to verify the TOTP code", async () => {
    const auth = new FakeAuth();
    const factorId = auth.giveVerifiedTotp(ALICE);
    auth.arrive(ALICE);

    expect(await resolveGate(auth)).toEqual({ step: "verify_totp", factorId });
  });

  it("lets an aal2 session in", async () => {
    const auth = new FakeAuth();
    const factorId = auth.giveVerifiedTotp(ALICE);
    auth.arrive(ALICE);
    await auth.verifyTotp(factorId, FakeAuth.CODE);

    expect(await resolveGate(auth)).toEqual({ step: "ready", userId: ALICE });
  });
});
