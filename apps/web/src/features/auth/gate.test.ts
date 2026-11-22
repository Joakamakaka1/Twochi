import { describe, expect, it } from "vitest";

import { resolveGate } from "./gate";
import { FakeAuth } from "./testing";

const ALICE = "00000000-0000-4000-8000-00000000a11c";

describe("resolveGate", () => {
  it("asks whoever has no session to sign in", async () => {
    expect(await resolveGate(new FakeAuth())).toEqual({ step: "sign_in" });
  });

  it("sends a first sign-in, with no TOTP yet, to enroll it", async () => {
    const auth = new FakeAuth();
    auth.arrive(ALICE);

    expect(await resolveGate(auth)).toEqual({ step: "enroll_totp" });
  });

  it("keeps asking to enroll while the scanned factor is not verified", async () => {
    const auth = new FakeAuth();
    auth.arrive(ALICE);
    await auth.enrollTotp();

    expect(await resolveGate(auth)).toEqual({ step: "enroll_totp" });
  });

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
