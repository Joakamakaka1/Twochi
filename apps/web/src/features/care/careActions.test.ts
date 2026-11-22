import { MutationObserver, QueryClient } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";

import { ApiError, createApi, texts } from "../../shared";
import type { CareActionResult, Home, Pet } from "../../shared";
import { careActionMutation, careFailureText, careOutcomeText, careTap } from "./careActions";
import { HOME_KEY } from "./home";

const need = (value: number) => ({ value, updated_at: "2026-11-22T12:00:00Z", rate_per_hour: -3 });

const BRU: Pet = {
  id: "00000000-0000-4000-8000-0000000fb20b",
  name: "Bru",
  model_key: "placeholder",
  asleep: false,
  mood: "normal",
  needs: { hunger: need(40), energy: need(40), hygiene: need(40), fun: need(40), affection: need(40) },
};

const FED: Pet = { ...BRU, mood: "happy", needs: { ...BRU.needs, hunger: need(65) } };

const applied: CareActionResult = { applied: true, rejection: null, deltas: { hunger: 25 }, pet: FED };
const tooTired: CareActionResult = { applied: false, rejection: "too_tired", deltas: {}, pet: BRU };

interface Sent {
  url: string;
  body: { action: string; idempotency_key: string };
}

// The API as a function: records each care action it was sent and answers in turn.
function apiAnswering(...answers: (() => Response)[]) {
  const sent: Sent[] = [];
  const api = createApi(() => Promise.resolve("jwt-1"), {
    baseUrl: "https://twochi.test",
    baseFetch: async (request) => {
      sent.push({ url: `${request.method} ${request.url}`, body: (await request.clone().json()) as Sent["body"] });
      const answer = answers[Math.min(sent.length, answers.length) - 1];
      if (answer === undefined) throw new Error("no answer for this request");
      return answer();
    },
  });
  return { api, sent };
}

const problem = (status: number, code: string) => () =>
  Response.json({ type: "about:blank", title: "Request failed", status, code }, { status });

// Casa with its pet already read, and a care action as the screen sends it: retries
// as the mutation says, without the wait.
function careFor(api: ReturnType<typeof createApi>) {
  const queryClient = new QueryClient();
  queryClient.setQueryData<Home>(HOME_KEY, { pet: BRU });
  const observer = new MutationObserver(queryClient, { ...careActionMutation(api, BRU.id, queryClient), retryDelay: 0 });
  return { queryClient, observer };
}

describe("care actions", () => {
  it("sends each tap with a new idempotency key the API accepts", async () => {
    const { api, sent } = apiAnswering(() => Response.json(applied));
    const { observer } = careFor(api);

    await observer.mutate(careTap("feed"));
    await observer.mutate(careTap("feed"));

    expect(sent.map((request) => request.url)).toEqual([
      `POST https://twochi.test/api/pets/${BRU.id}/care-actions`,
      `POST https://twochi.test/api/pets/${BRU.id}/care-actions`,
    ]);
    const [first, second] = sent.map((request) => request.body.idempotency_key);
    expect(first).not.toBe(second);
    for (const key of [first, second]) expect(key).toMatch(/^[A-Za-z0-9_-]{1,64}$/);
  });

  it("reuses the key of the tap when it has to send it again", async () => {
    const { api, sent } = apiAnswering(problem(503, "database_unavailable"), () => Response.json(applied));
    const { observer } = careFor(api);

    const result = await observer.mutate(careTap("feed"));

    expect(result).toEqual(applied);
    expect(sent).toHaveLength(2);
    expect(sent[1]?.body).toEqual(sent[0]?.body);
  });

  it("does not send the tap again when the API refuses the token", async () => {
    const { api, sent } = apiAnswering(problem(401, "unauthenticated"));
    const { observer } = careFor(api);

    await observer.mutate(careTap("feed")).catch(() => undefined);

    expect(sent).toHaveLength(1);
    expect(observer.getCurrentResult().error).toMatchObject({ status: 401, code: "unauthenticated" });
  });

  it("moves the bars to the pet the response brings", async () => {
    const { api } = apiAnswering(() => Response.json(applied));
    const { queryClient, observer } = careFor(api);

    await observer.mutate(careTap("feed"));

    expect(queryClient.getQueryData(HOME_KEY)).toEqual({ pet: FED });
  });

  it("keeps the pet the response brings when the engine refuses, and says why", async () => {
    const { api } = apiAnswering(() => Response.json(tooTired));
    const { queryClient, observer } = careFor(api);

    await observer.mutate(careTap("play"));

    await vi.waitFor(() => {
      expect(observer.getCurrentResult().isSuccess).toBe(true);
    });
    expect(queryClient.getQueryData(HOME_KEY)).toEqual({ pet: BRU });
    expect(careOutcomeText(observer.getCurrentResult().data)).toBe(texts.care.rejections.too_tired);
  });

  it("says nothing when the action was applied or nothing was tapped yet", () => {
    expect(careOutcomeText(applied)).toBeNull();
    expect(careOutcomeText(undefined)).toBeNull();
  });
});

describe("careFailureText", () => {
  it("offers to send the tap again when the API failed", () => {
    expect(careFailureText(new ApiError(503, "database_unavailable"))).toBe(texts.failure);
    expect(careFailureText(new TypeError("Failed to fetch"))).toBe(texts.failure);
  });

  it("offers nothing when the API refused the token: the gate takes the person away", () => {
    expect(careFailureText(new ApiError(401, "unauthenticated"))).toBeNull();
    expect(careFailureText(new ApiError(403, "mfa_required"))).toBeNull();
  });

  it("says nothing when no tap failed", () => {
    expect(careFailureText(null)).toBeNull();
  });
});
