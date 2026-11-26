import { QueryClient, QueryObserver } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";

import { ApiError, AUTH_HEADER, createApi, isAuthFailure, texts } from "../../shared";
import type { CareActionResult, Home, Pet, VisibilitySource } from "../../shared";
import { homeAfterCare, homeHeadline, homeQuery, readHome, refreshHomeOnForeground } from "./home";

const BRU_PET: Pet = {
  id: "00000000-0000-4000-8000-0000000fb20b",
  name: "Bru",
  model_key: "placeholder",
  asleep: false,
  mood: "happy",
  needs: {
    hunger: { value: 80, updated_at: "2026-11-22T12:00:00Z", rate_per_hour: -4 },
    energy: { value: 80, updated_at: "2026-11-22T12:00:00Z", rate_per_hour: -3 },
    hygiene: { value: 80, updated_at: "2026-11-22T12:00:00Z", rate_per_hour: -2 },
    fun: { value: 80, updated_at: "2026-11-22T12:00:00Z", rate_per_hour: -5 },
    affection: { value: 80, updated_at: "2026-11-22T12:00:00Z", rate_per_hour: -3 },
  },
};

const BRU: Home = { pet: { ...BRU_PET, discovered: {} } };

// The API as a function: records what it was sent and answers what the test says.
function apiAnswering(answer: () => Response) {
  const sent: Request[] = [];
  const api = createApi(() => Promise.resolve("jwt-1"), {
    baseUrl: "https://twochi.test",
    baseFetch: (request) => {
      sent.push(request);
      return Promise.resolve(answer());
    },
  });
  return { api, sent };
}

describe("readHome", () => {
  it("reads the pet in the person's care from /api/homes/me, with their JWT", async () => {
    const { api, sent } = apiAnswering(() => Response.json(BRU));

    expect(await readHome(api)).toEqual(BRU);
    expect(sent.map((request) => `${request.method} ${request.url}`)).toEqual(["GET https://twochi.test/api/homes/me"]);
    expect(sent[0]?.headers.get(AUTH_HEADER)).toBe("jwt-1");
  });

  it("fails with the status when the API refuses, without the body", async () => {
    const problem = { type: "about:blank", title: "Second factor required", status: 403, code: "mfa_required" };
    const { api } = apiAnswering(() => Response.json(problem, { status: 403 }));

    const failure = await readHome(api).catch((error: unknown) => error);

    expect(failure).toBeInstanceOf(ApiError);
    expect(failure).toMatchObject({ status: 403, message: "The API answered 403" });
  });
});

// The API's own problems, as apps/api/src/twochi_api/problems.py builds them.
function problem(status: number, code: string): () => Response {
  return () => Response.json({ type: "about:blank", title: "Request failed", status, code }, { status });
}

// Casa as the screen reads it: an observer that retries as the query says, without the wait.
async function watchHomeFail(answer: () => Response) {
  const { api, sent } = apiAnswering(answer);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retryDelay: 0 } } });
  const observer = new QueryObserver(queryClient, homeQuery(api));
  const stop = observer.subscribe(() => undefined);
  await vi.waitFor(() => {
    expect(observer.getCurrentResult().isError).toBe(true);
  });
  stop();
  return { error: observer.getCurrentResult().error, requests: sent.length };
}

describe("homeQuery when the API refuses the token", () => {
  it.each([
    [401, "unauthenticated"],
    [403, "mfa_required"],
  ])("takes %i %s for an auth failure and does not ask again", async (status, code) => {
    const { error, requests } = await watchHomeFail(problem(status, code));

    expect(requests).toBe(1);
    expect(error).toMatchObject({ status, code });
    expect(isAuthFailure(error)).toBe(true);
  });

  it("asks again when the API fails for any other reason", async () => {
    const { error, requests } = await watchHomeFail(problem(500, "internal_error"));

    expect(isAuthFailure(error)).toBe(false);
    expect(requests).toBe(4);
  });

  it("does not take a 403 with another code for an auth failure", async () => {
    const { error } = await watchHomeFail(problem(403, "not_yours"));

    expect(isAuthFailure(error)).toBe(false);
  });

  it("keeps no code when the failure is not a problem of the API", async () => {
    const { error } = await watchHomeFail(() => new Response("<html>Bad gateway</html>", { status: 502 }));

    expect(error).toMatchObject({ status: 502, code: null });
  });
});

describe("homeHeadline", () => {
  it("names the pet in the person's care", () => {
    expect(homeHeadline(BRU)).toBe("Cuidas a Bru");
  });

  it("says the pet will arrive when their partner joins", () => {
    expect(homeHeadline({ pet: null })).toBe(texts.care.petArrivesWithPartner);
  });
});

// The page as the browser shows it: visible or sent to the background.
class FakePage extends EventTarget implements VisibilitySource {
  visibilityState: DocumentVisibilityState = "visible";

  become(state: DocumentVisibilityState) {
    this.visibilityState = state;
    this.dispatchEvent(new Event("visibilitychange"));
  }
}

describe("refreshHomeOnForeground", () => {
  it("reads Casa again from the API when the page comes back from the background", async () => {
    const later: Home = { pet: { ...BRU_PET, asleep: true, mood: "normal", discovered: {} } };
    let answer: Home = BRU;
    const { api, sent } = apiAnswering(() => Response.json(answer));
    const queryClient = new QueryClient();
    const observer = new QueryObserver(queryClient, homeQuery(api));
    const stopWatching = observer.subscribe(() => undefined);
    await vi.waitFor(() => {
      expect(observer.getCurrentResult().data).toEqual(BRU);
    });
    const page = new FakePage();
    const stop = refreshHomeOnForeground(page, queryClient);

    answer = later;
    page.become("hidden");
    expect(sent).toHaveLength(1);
    page.become("visible");

    await vi.waitFor(() => {
      expect(observer.getCurrentResult().data).toEqual(later);
    });
    expect(sent.map((request) => `${request.method} ${request.url}`)).toEqual([
      "GET https://twochi.test/api/homes/me",
      "GET https://twochi.test/api/homes/me",
    ]);

    stop();
    page.become("hidden");
    page.become("visible");
    await Promise.resolve();
    expect(sent).toHaveLength(2);
    stopWatching();
  });
});

describe("homeAfterCare", () => {
  const fed: Pet = { ...BRU_PET, mood: "normal", needs: { ...BRU_PET.needs, hunger: { ...BRU_PET.needs.hunger, value: 90 } } };
  const gave = (reaction: CareActionResult["reaction"]): CareActionResult => ({
    applied: true,
    rejection: null,
    deltas: { hunger: 10 },
    reaction,
    sickness: null,
    pet: fed,
  });
  const caring = (discovered: NonNullable<Home["pet"]>["discovered"]): Home => ({
    pet: { ...BRU_PET, discovered },
  });

  it("brings the pet of the response, with the item given now discovered", () => {
    const after = homeAfterCare(caring({ sushi: 2 }), gave({ item_key: "broccoli", affinity: -2 }));

    expect(after).toEqual({ pet: { ...fed, discovered: { sushi: 2, broccoli: -2 } } });
  });

  it("replaces what was seen with an item when it is given again", () => {
    const after = homeAfterCare(caring({ pizza: 2 }), gave({ item_key: "pizza", affinity: -1 }));

    expect(after.pet?.discovered).toEqual({ pizza: -1 });
  });

  it("keeps what was discovered when the response brings no reaction", () => {
    const after = homeAfterCare(caring({ pizza: 2 }), { ...gave(null), applied: false, rejection: "asleep" });

    expect(after).toEqual({ pet: { ...fed, discovered: { pizza: 2 } } });
  });

  it("leaves the cache alone when there was no Casa to update", () => {
    expect(homeAfterCare(undefined, gave({ item_key: "ball", affinity: 0 }))).toBeUndefined();
  });
});
