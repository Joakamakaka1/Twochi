import { MutationObserver, QueryClient } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";

import { createApi } from "../../shared";
import type { CareActionResult, Home, Pet } from "../../shared";
import { careActionMutation, careTaps } from "./careActions";
import { HOME_KEY } from "./home";
import { BURST_GAP_MS, classifyTouches, petTouches } from "./touch";

const T0 = 1_000_000;

describe("classifyTouches", () => {
  it("pets on a single touch", () => {
    expect(classifyTouches([T0])).toEqual(["pet"]);
  });

  it("does nothing on the second touch of a burst, and tickles from the third", () => {
    expect(classifyTouches([T0, T0 + 200, T0 + 400, T0 + 600, T0 + 800])).toEqual([
      "pet",
      "nothing",
      "tickle",
      "tickle",
      "tickle",
    ]);
  });

  it("keeps a burst going while each touch comes within 500 ms of the one before", () => {
    expect(BURST_GAP_MS).toBe(500);
    expect(classifyTouches([T0, T0 + 500, T0 + 1000])).toEqual(["pet", "nothing", "tickle"]);
  });

  it("starts a new burst, and pets again, after a pause longer than 500 ms", () => {
    expect(classifyTouches([T0, T0 + 300, T0 + 801, T0 + 1000, T0 + 1300])).toEqual([
      "pet",
      "nothing",
      "pet",
      "nothing",
      "tickle",
    ]);
  });

  it("ends a fit of tickles with a pause, and the next touch pets", () => {
    expect(classifyTouches([T0, T0 + 100, T0 + 200, T0 + 300, T0 + 2000])).toEqual([
      "pet",
      "nothing",
      "tickle",
      "tickle",
      "pet",
    ]);
  });

  it("classifies nothing when there was no touch", () => {
    expect(classifyTouches([])).toEqual([]);
  });
});

const need = (value: number) => ({ value, updated_at: "2026-11-26T12:00:00Z", rate_per_hour: -3 });

const BRU: Pet = {
  id: "00000000-0000-4000-8000-0000000fb20b",
  name: "Bru",
  model_key: "placeholder",
  asleep: false,
  mood: "normal",
  needs: { hunger: need(40), energy: need(40), hygiene: need(40), fun: need(40), affection: need(40) },
};

const petted: CareActionResult = {
  applied: true,
  rejection: null,
  deltas: { affection: 15 },
  reaction: null,
  sickness: null,
  pet: BRU,
};

// The figure's touches over Casa's real care taps, against an API that records every
// request it gets and answers each with a petting.
function touchesOverTheApi() {
  const sent: string[] = [];
  const api = createApi(() => Promise.resolve("jwt-1"), {
    baseUrl: "https://twochi.test",
    baseFetch: (request) => {
      sent.push(`${request.method} ${request.url}`);
      return Promise.resolve(Response.json(petted));
    },
  });
  const queryClient = new QueryClient();
  queryClient.setQueryData<Home>(HOME_KEY, { pet: { ...BRU, discovered: {} } });
  const observer = new MutationObserver(queryClient, careActionMutation(api, BRU.id, queryClient));
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
  const tickle = vi.fn();
  const touch = petTouches({
    pet: () => {
      taps.tap("pet");
    },
    tickle,
  });
  return { sent, onOutcome, tickle, touch };
}

describe("petTouches", () => {
  it("sends one petting for a burst, and tickles without any request to the API", async () => {
    const { sent, onOutcome, tickle, touch } = touchesOverTheApi();

    touch(T0, false);
    await vi.waitFor(() => {
      expect(onOutcome).toHaveBeenCalledTimes(1);
    });
    for (const at of [T0 + 150, T0 + 300, T0 + 450, T0 + 600, T0 + 750]) touch(at, false);
    // Give any request the tickles might have made the time to arrive.
    await new Promise((settled) => setTimeout(settled, 20));

    expect(tickle).toHaveBeenCalledTimes(4);
    expect(sent).toEqual([`POST https://twochi.test/api/pets/${BRU.id}/care-actions`]);
    expect(onOutcome).toHaveBeenCalledTimes(1);
  });

  it("pets again, with its own request, once the burst is over", async () => {
    const { sent, onOutcome, touch } = touchesOverTheApi();

    touch(T0, false);
    await vi.waitFor(() => {
      expect(onOutcome).toHaveBeenCalledTimes(1);
    });
    touch(T0 + 2000, false);
    await vi.waitFor(() => {
      expect(onOutcome).toHaveBeenCalledTimes(2);
    });

    expect(sent).toHaveLength(2);
  });

  it("only pets, for the engine to refuse, while asleep: a sleeping pet feels no tickles", () => {
    const pet = vi.fn();
    const tickle = vi.fn();
    const touch = petTouches({ pet, tickle });

    for (const at of [T0, T0 + 100, T0 + 200, T0 + 300]) touch(at, true);

    expect(pet).toHaveBeenCalledTimes(1);
    expect(tickle).not.toHaveBeenCalled();
  });
});
