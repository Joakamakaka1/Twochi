import { MutationObserver, QueryClient } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";

import { ApiError, createApi, texts } from "../../shared";
import type { CareActionResult, Home, Pet } from "../../shared";
import {
  careActionMutation,
  careFailureText,
  careTap,
  careTaps,
  onHomeRead,
} from "./careActions";
import { HOME_KEY, homeQuery } from "./home";

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

const applied: CareActionResult = {
  applied: true,
  rejection: null,
  deltas: { hunger: 25 },
  reaction: { item_key: "pizza", affinity: 0 },
  sickness: null,
  pet: FED,
};
const tooTired: CareActionResult = {
  applied: false,
  rejection: "too_tired",
  deltas: {},
  reaction: null,
  sickness: null,
  pet: BRU,
};
const bathed: CareActionResult = { ...applied, deltas: { hygiene: 60 }, reaction: null };

interface Sent {
  url: string;
  body: { action: string; idempotency_key: string; item_key?: string } | null;
}

// The API as a function: records each care action it was sent and answers in turn.
function apiAnswering(...answers: (() => Response | Promise<Response>)[]) {
  const sent: Sent[] = [];
  const api = createApi(() => Promise.resolve("jwt-1"), {
    baseUrl: "https://twochi.test",
    baseFetch: async (request) => {
      const body = request.method === "GET" ? null : ((await request.clone().json()) as Sent["body"]);
      sent.push({ url: `${request.method} ${request.url}`, body });
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
    const [first, second] = sent.map((request) => request.body?.idempotency_key);
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

  it("keeps the pet the response brings when the engine refuses", async () => {
    const { api } = apiAnswering(() => Response.json(tooTired));
    const { queryClient, observer } = careFor(api);

    await observer.mutate(careTap("play"));

    await vi.waitFor(() => {
      expect(observer.getCurrentResult().isSuccess).toBe(true);
    });
    expect(queryClient.getQueryData(HOME_KEY)).toEqual({ pet: BRU });
    expect(observer.getCurrentResult().data).toEqual(tooTired);
  });

  it("sends the item the carer chose from the tray with the tap", async () => {
    const { api, sent } = apiAnswering(() => Response.json(applied));
    const { observer } = careFor(api);

    await observer.mutate(careTap("feed", "tortilla"));

    expect(sent[0]?.body).toMatchObject({ action: "feed", item_key: "tortilla" });
  });

  it("sends no item with an action that takes none", async () => {
    const { api, sent } = apiAnswering(() => Response.json(bathed));
    const { observer } = careFor(api);

    await observer.mutate(careTap("bathe"));

    expect(sent[0]?.body).not.toHaveProperty("item_key");
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

// An answer the test releases when it wants, as a slow network or a retry would.
function lateAnswer() {
  let release: (response: Response) => void = () => undefined;
  const answer = new Promise<Response>((resolve) => {
    release = resolve;
  });
  return { answer: () => answer, release };
}

describe("a care action answered after the person left", () => {
  it("leaves the cache empty once the person was forgotten", async () => {
    const late = lateAnswer();
    const { api, sent } = apiAnswering(late.answer);
    const { queryClient, observer } = careFor(api);
    const tap = observer.mutate(careTap("feed"));
    await vi.waitFor(() => {
      expect(sent).toHaveLength(1);
    });

    // What signing out does to the cache (forgetPerson in features/auth).
    queryClient.removeQueries();
    late.release(Response.json(applied));
    await tap;

    expect(queryClient.getQueryData(HOME_KEY)).toBeUndefined();
  });

  it("never writes into the Casa of the next person who signs in", async () => {
    const late = lateAnswer();
    const { api, sent } = apiAnswering(late.answer);
    const { queryClient, observer } = careFor(api);
    const tap = observer.mutate(careTap("feed"));
    await vi.waitFor(() => {
      expect(sent).toHaveLength(1);
    });

    queryClient.removeQueries();
    queryClient.setQueryData<Home>(HOME_KEY, { pet: null });
    late.release(Response.json(applied));
    await tap;

    expect(queryClient.getQueryData(HOME_KEY)).toEqual({ pet: null });
  });

  it("is not sent again once the gate forgot the person's writes", async () => {
    const late = lateAnswer();
    const { api, sent } = apiAnswering(late.answer, () => Response.json(applied));
    const { queryClient, observer } = careFor(api);
    const tap = observer.mutate(careTap("feed")).catch((error: unknown) => error);
    await vi.waitFor(() => {
      expect(sent).toHaveLength(1);
    });

    // What the gate does when another person signs in: a retry would carry their token.
    queryClient.getMutationCache().clear();
    late.release(problem(503, "database_unavailable")());

    expect(await tap).toBeInstanceOf(Error);
    expect(sent).toHaveLength(1);
  });
});

// Casa's taps over a care mutation that is on screen (subscribed), as useMutation's is:
// per-tap callbacks only reach a watched observer.
function tapsFor(api: ReturnType<typeof createApi>) {
  const { queryClient, observer } = careFor(api);
  observer.subscribe(() => undefined);
  const onOutcome = vi.fn();
  const taps = careTaps(
    {
      mutate: (tap, callbacks) => {
        observer.mutate(tap, callbacks).catch(() => undefined);
      },
      reset: () => {
        observer.reset();
      },
    },
    onOutcome,
  );
  return { queryClient, observer, taps, onOutcome };
}

describe("careTaps", () => {
  it("sends one tap at a time, also two in the same task (the figure and the button)", async () => {
    const late = lateAnswer();
    const { api, sent } = apiAnswering(late.answer, () => Response.json(applied));
    const { taps, onOutcome } = tapsFor(api);

    taps.tap("pet");
    taps.tap("pet");
    await vi.waitFor(() => {
      expect(sent).toHaveLength(1);
    });
    late.release(Response.json(applied));
    await vi.waitFor(() => {
      expect(onOutcome).toHaveBeenCalledTimes(1);
    });
    expect(sent).toHaveLength(1);

    taps.tap("feed");
    await vi.waitFor(() => {
      expect(sent).toHaveLength(2);
    });
  });

  it("sends the item chosen in the tray with its tap", async () => {
    const { api, sent } = apiAnswering(() => Response.json(applied));
    const { taps, onOutcome } = tapsFor(api);

    taps.tap("play", "video_games");
    await vi.waitFor(() => {
      expect(onOutcome).toHaveBeenCalledTimes(1);
    });

    expect(sent[0]?.body).toMatchObject({ action: "play", item_key: "video_games" });
  });

  it("hears the outcome of each tap, applied or refused", async () => {
    const { api } = apiAnswering(
      () => Response.json(applied),
      () => Response.json(tooTired),
    );
    const { taps, onOutcome } = tapsFor(api);

    taps.tap("feed");
    await vi.waitFor(() => {
      expect(onOutcome).toHaveBeenCalledTimes(1);
    });
    taps.tap("play");
    await vi.waitFor(() => {
      expect(onOutcome).toHaveBeenCalledTimes(2);
    });

    expect(onOutcome.mock.calls).toEqual([
      ["feed", applied],
      ["play", tooTired],
    ]);
  });

  it("hears nothing of a tap that failed, and retry sends it again with the same key", async () => {
    const { api, sent } = apiAnswering(problem(401, "unauthenticated"), () => Response.json(applied));
    const { observer, taps, onOutcome } = tapsFor(api);

    taps.tap("feed");
    await vi.waitFor(() => {
      expect(observer.getCurrentResult().isError).toBe(true);
    });
    expect(onOutcome).not.toHaveBeenCalled();

    taps.retry();
    await vi.waitFor(() => {
      expect(onOutcome).toHaveBeenCalledWith("feed", applied);
    });
    expect(sent).toHaveLength(2);
    expect(sent[1]?.body).toEqual(sent[0]?.body);
  });

  it("keeps a tap in flight, and its reaction, when Casa is read meanwhile", async () => {
    const late = lateAnswer();
    const { api, sent } = apiAnswering(late.answer, () => Response.json({ pet: BRU }));
    const { queryClient, taps, onOutcome } = tapsFor(api);
    onHomeRead(queryClient, taps.homeRead);

    taps.tap("feed");
    await vi.waitFor(() => {
      expect(sent).toHaveLength(1);
    });
    await queryClient.query(homeQuery(api));
    late.release(Response.json(applied));

    await vi.waitFor(() => {
      expect(onOutcome).toHaveBeenCalledWith("feed", applied);
    });
  });

  it("clears a failed tap's text when Casa is read again with no tap in flight", async () => {
    const { api } = apiAnswering(problem(422, "invalid_item"), () => Response.json({ pet: BRU }));
    const { queryClient, observer, taps } = tapsFor(api);
    onHomeRead(queryClient, taps.homeRead);

    taps.tap("feed");
    await vi.waitFor(() => {
      expect(careFailureText(observer.getCurrentResult().error)).toBe(texts.failure);
    });

    await queryClient.query(homeQuery(api));
    expect(careFailureText(observer.getCurrentResult().error)).toBeNull();
  });
});
