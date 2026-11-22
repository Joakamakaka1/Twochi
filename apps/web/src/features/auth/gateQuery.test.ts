import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";

import { ApiError } from "../../shared";
import { followAuth, gateQuery } from "./gateQuery";
import { FakeAuth } from "./testing";

const ALICE = "00000000-0000-4000-8000-00000000a11c";
const BRUNO = "00000000-0000-4000-8000-00000000b20b";
const HOME_KEY = ["home"];

async function enterAtAal2(auth: FakeAuth, userId: string) {
  const factorId = auth.giveVerifiedTotp(userId);
  auth.arrive(userId);
  await auth.verifyTotp(factorId, FakeAuth.CODE);
}

// The app as it runs: one query cache, with the gate following the session.
async function appWith(auth: FakeAuth) {
  const queryClient = new QueryClient();
  followAuth(auth, queryClient);
  const gate = () => queryClient.query(gateQuery(auth, queryClient));
  await gate();
  return { queryClient, gate };
}

describe("the gate in the query cache", () => {
  it("resolves again when the session changes", async () => {
    const auth = new FakeAuth();
    const { gate } = await appWith(auth);
    expect(await gate()).toEqual({ step: "sign_in" });

    await enterAtAal2(auth, ALICE);

    expect(await gate()).toEqual({ step: "ready", userId: ALICE });
  });

  it("forgets what a person loaded once they sign out", async () => {
    const auth = new FakeAuth();
    await enterAtAal2(auth, ALICE);
    const { queryClient, gate } = await appWith(auth);
    queryClient.setQueryData(HOME_KEY, { pet: { name: "Bru" } });

    await auth.signOut();

    expect(await gate()).toEqual({ step: "sign_in" });
    expect(queryClient.getQueryData(HOME_KEY)).toBeUndefined();
  });

  it("forgets it too when another person's session replaces theirs, as from another tab", async () => {
    const auth = new FakeAuth();
    await enterAtAal2(auth, ALICE);
    const { queryClient, gate } = await appWith(auth);
    queryClient.setQueryData(HOME_KEY, { pet: { name: "Bru" } });

    await enterAtAal2(auth, BRUNO);

    expect(await gate()).toEqual({ step: "ready", userId: BRUNO });
    expect(queryClient.getQueryData(HOME_KEY)).toBeUndefined();
  });

  it("keeps what the person loaded while they stay signed in at aal2", async () => {
    const auth = new FakeAuth();
    await enterAtAal2(auth, ALICE);
    const { queryClient, gate } = await appWith(auth);
    queryClient.setQueryData(HOME_KEY, { pet: { name: "Bru" } });

    // A token refresh: the session changes, the person does not.
    auth.arrive(ALICE);
    await auth.verifyTotp(`factor-${ALICE}`, FakeAuth.CODE);

    expect(await gate()).toEqual({ step: "ready", userId: ALICE });
    expect(queryClient.getQueryData(HOME_KEY)).toEqual({ pet: { name: "Bru" } });
  });
});

// A read of the API that fails as the generated client's callers make it fail.
async function apiReadFails(queryClient: QueryClient, error: ApiError) {
  await queryClient.query({ queryKey: HOME_KEY, queryFn: () => Promise.reject(error) }).catch(() => undefined);
}

describe("the gate when the API refuses the token before Auth says anything", () => {
  it("sends the person to verify the code after a 403 mfa_required", async () => {
    const auth = new FakeAuth();
    await enterAtAal2(auth, ALICE);
    const { queryClient, gate } = await appWith(auth);
    auth.arriveInAnotherTab(ALICE);
    expect(await gate()).toEqual({ step: "ready", userId: ALICE });

    await apiReadFails(queryClient, new ApiError(403, "mfa_required"));

    expect(await gate()).toEqual({ step: "verify_totp", factorId: `factor-${ALICE}` });
    expect(queryClient.getQueryData(HOME_KEY)).toBeUndefined();
  });

  it("sends the person to sign in after a 401 with the session gone", async () => {
    const auth = new FakeAuth();
    await enterAtAal2(auth, ALICE);
    const { queryClient, gate } = await appWith(auth);
    auth.loseSessionUnnoticed();

    await apiReadFails(queryClient, new ApiError(401, "unauthenticated"));

    expect(await gate()).toEqual({ step: "sign_in" });
  });

  it("stays where it is when the API fails for another reason", async () => {
    const auth = new FakeAuth();
    await enterAtAal2(auth, ALICE);
    const { queryClient, gate } = await appWith(auth);
    auth.arriveInAnotherTab(ALICE);

    await apiReadFails(queryClient, new ApiError(500, "internal_error"));

    expect(await gate()).toEqual({ step: "ready", userId: ALICE });
  });
});
