import { describe, expect, it } from "vitest";

import { ApiError, AUTH_HEADER, createApi, texts } from "../../shared";
import type { Home } from "../../shared";
import { homeHeadline, readHome } from "./home";

const BRU: Home = {
  pet: {
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
  },
};

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

describe("homeHeadline", () => {
  it("names the pet in the person's care", () => {
    expect(homeHeadline(BRU)).toBe("Cuidas a Bru");
  });

  it("says the pet will arrive when their partner joins", () => {
    expect(homeHeadline({ pet: null })).toBe(texts.care.petArrivesWithPartner);
  });
});
