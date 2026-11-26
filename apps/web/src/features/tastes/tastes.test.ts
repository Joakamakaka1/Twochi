import { MutationObserver, QueryClient } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";

import { ApiError, AUTH_HEADER, createApi, ITEM_ICONS } from "../../shared";
import type { Tastes } from "../../shared";
import { FACES, rateTasteMutation, readTastes, TASTES_KEY, tasteSections, tastesNotice } from "./tastes";

const ALI = "00000000-0000-4000-8000-0000000fa11c";

interface Sent {
  request: string;
  body: unknown;
}

// The API as a function: records what it was sent and answers in turn.
function apiAnswering(...answers: (() => Response)[]) {
  const sent: Sent[] = [];
  const headers: Headers[] = [];
  const api = createApi(() => Promise.resolve("jwt-1"), {
    baseUrl: "https://twochi.test",
    baseFetch: async (request) => {
      const body: unknown = request.method === "GET" ? null : await request.clone().json();
      sent.push({ request: `${request.method} ${request.url}`, body });
      headers.push(request.headers);
      const answer = answers[Math.min(sent.length, answers.length) - 1];
      if (answer === undefined) throw new Error("no answer for this request");
      return Promise.resolve(answer());
    },
  });
  return { api, sent, headers };
}

const problem = (status: number, code: string) => () =>
  Response.json({ type: "about:blank", title: "Request failed", status, code }, { status });

describe("readTastes", () => {
  it("reads the caller's own tastes from /api/tastes/me, with their JWT", async () => {
    const tastes: Tastes = { pet_id: ALI, tastes: { pizza: 2 } };
    const { api, sent, headers } = apiAnswering(() => Response.json(tastes));

    expect(await readTastes(api)).toEqual(tastes);
    expect(sent.map((each) => each.request)).toEqual(["GET https://twochi.test/api/tastes/me"]);
    expect(headers[0]?.get(AUTH_HEADER)).toBe("jwt-1");
  });

  it("fails with the status and the problem's code", async () => {
    const { api } = apiAnswering(problem(403, "mfa_required"));

    const failure = await readTastes(api).catch((error: unknown) => error);

    expect(failure).toBeInstanceOf(ApiError);
    expect(failure).toMatchObject({ status: 403, code: "mfa_required" });
  });
});

describe("tasteSections", () => {
  it("lists the foods and then the activities of the catalogue, with their icons and names", () => {
    const [foods, activities] = tasteSections({});

    expect(foods?.title).toBe("Comidas");
    expect(foods?.items.map((item) => item.key)).toEqual([
      "tortilla",
      "paella",
      "pizza",
      "burger",
      "sushi",
      "pasta",
      "tacos",
      "salad",
      "broccoli",
      "strawberries",
      "ice_cream",
      "chocolate",
    ]);
    expect(activities?.title).toBe("Actividades");
    expect(activities?.items.map((item) => item.key)).toEqual([
      "ball",
      "video_games",
      "dance",
      "reading",
      "drawing",
      "puzzle",
    ]);
    expect(foods?.items).toContainEqual({ key: "strawberries", icon: "🍓", name: "Fresas", affinity: 0 });
    expect(activities?.items).toContainEqual({ key: "puzzle", icon: "🧩", name: "Puzle", affinity: 0 });
  });

  it("shows what was rated, and anything not rated as neutral", () => {
    const items = tasteSections({ pizza: 2, ball: -2 }).flatMap((section) => section.items);

    expect(items.find((item) => item.key === "pizza")?.affinity).toBe(2);
    expect(items.find((item) => item.key === "ball")?.affinity).toBe(-2);
    expect(items.find((item) => item.key === "sushi")?.affinity).toBe(0);
  });

  it("puts every item of the catalogue in exactly one section", () => {
    const listed = tasteSections({}).flatMap((section) => section.items.map((item) => item.key));

    expect([...listed].sort()).toEqual(Object.keys(ITEM_ICONS).sort());
    expect(new Set(listed).size).toBe(listed.length);
  });
});

describe("the five faces", () => {
  it("go from hating to loving, each with its name", () => {
    expect(FACES.map((face) => [face.affinity, face.label])).toEqual([
      [-2, "Lo odio"],
      [-1, "No me gusta"],
      [0, "Me da igual"],
      [1, "Me gusta"],
      [2, "Me encanta"],
    ]);
    expect(new Set(FACES.map((face) => face.icon)).size).toBe(5);
  });
});

describe("tastesNotice", () => {
  it("says the pet arrives with the partner until it is born", () => {
    expect(tastesNotice({ pet_id: null, tastes: {} })).toBe("Tu mascota llegará cuando tu pareja se una.");
  });

  it("says nothing once the pet is born", () => {
    expect(tastesNotice({ pet_id: ALI, tastes: {} })).toBeNull();
  });
});

// The screen's tastes already read, and a rating as the screen sends it: retries as
// the mutation says, without the wait.
function ratingWith(api: ReturnType<typeof createApi>, tastes: Tastes = { pet_id: ALI, tastes: { pizza: -1 } }) {
  const queryClient = new QueryClient();
  queryClient.setQueryData<Tastes>(TASTES_KEY, tastes);
  const observer = new MutationObserver(queryClient, { ...rateTasteMutation(api, queryClient), retryDelay: 0 });
  return { queryClient, observer };
}

describe("rating a taste", () => {
  it("sends the item in the path and the affinity in the body", async () => {
    const { api, sent } = apiAnswering(() => Response.json({ item_key: "ball", affinity: 1 }));
    const { observer } = ratingWith(api);

    await observer.mutate({ item_key: "ball", affinity: 1 });

    expect(sent).toEqual([{ request: "PUT https://twochi.test/api/tastes/me/ball", body: { affinity: 1 } }]);
  });

  it("shows the new face at once and keeps it, without reading the tastes again", async () => {
    let answer: (response: Response) => void = () => undefined;
    const pending = new Promise<Response>((resolve) => {
      answer = resolve;
    });
    const sent: string[] = [];
    const api = createApi(() => Promise.resolve("jwt-1"), {
      baseUrl: "https://twochi.test",
      baseFetch: (request) => {
        sent.push(`${request.method} ${request.url}`);
        return pending;
      },
    });
    const { queryClient, observer } = ratingWith(api);

    const rated = observer.mutate({ item_key: "pizza", affinity: 2 });
    await vi.waitFor(() => {
      expect(sent).toHaveLength(1);
    });

    expect(queryClient.getQueryData<Tastes>(TASTES_KEY)).toEqual({ pet_id: ALI, tastes: { pizza: 2 } });
    answer(Response.json({ item_key: "pizza", affinity: 2 }));
    await rated;
    expect(queryClient.getQueryData<Tastes>(TASTES_KEY)).toEqual({ pet_id: ALI, tastes: { pizza: 2 } });
    expect(queryClient.getQueryState(TASTES_KEY)?.isInvalidated).toBe(false);
    expect(sent).toEqual(["PUT https://twochi.test/api/tastes/me/pizza"]);
  });

  it("reads the tastes again when the rating failed, so the faces show what is stored", async () => {
    const { api } = apiAnswering(problem(409, "no_pet_yet"));
    const { queryClient, observer } = ratingWith(api);

    const failure = await observer.mutate({ item_key: "pizza", affinity: 2 }).catch((error: unknown) => error);

    expect(failure).toMatchObject({ status: 409, code: "no_pet_yet" });
    expect(queryClient.getQueryState(TASTES_KEY)?.isInvalidated).toBe(true);
  });

  it("sends the same rating again when the API may not have stored it", async () => {
    const { api, sent } = apiAnswering(problem(503, "database_unavailable"), () =>
      Response.json({ item_key: "pizza", affinity: 2 }),
    );
    const { queryClient, observer } = ratingWith(api);

    await observer.mutate({ item_key: "pizza", affinity: 2 });

    expect(sent.map((each) => each.request)).toEqual([
      "PUT https://twochi.test/api/tastes/me/pizza",
      "PUT https://twochi.test/api/tastes/me/pizza",
    ]);
    expect(queryClient.getQueryData<Tastes>(TASTES_KEY)?.tastes).toEqual({ pizza: 2 });
  });

  it("writes nothing into a cache the person already left", async () => {
    const { api } = apiAnswering(() => Response.json({ item_key: "pizza", affinity: 2 }));
    const { queryClient, observer } = ratingWith(api);
    queryClient.removeQueries({ queryKey: TASTES_KEY });

    await observer.mutate({ item_key: "pizza", affinity: 2 });

    expect(queryClient.getQueryData(TASTES_KEY)).toBeUndefined();
  });
});
