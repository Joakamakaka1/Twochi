import { describe, expect, it } from "vitest";

import { AUTH_HEADER, CONTENT_SHA256_HEADER, createSignedFetch } from "./signedFetch";

const SHA256_EMPTY = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855";
const SHA256_ABC = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad";

function recorder() {
  const sent: Request[] = [];
  const baseFetch = (request: Request) => {
    sent.push(request);
    return Promise.resolve(new Response(null, { status: 204 }));
  };
  return { sent, baseFetch };
}

describe("createSignedFetch", () => {
  it("sends the body's SHA-256 and the JWT in its own header", async () => {
    const { sent, baseFetch } = recorder();
    const signedFetch = createSignedFetch(() => Promise.resolve("jwt-1"), baseFetch);

    await signedFetch(new Request("https://twochi.test/api/pings", { method: "POST", body: "abc" }));

    const request = sent[0];
    expect(request?.headers.get(CONTENT_SHA256_HEADER)).toBe(SHA256_ABC);
    expect(request?.headers.get(AUTH_HEADER)).toBe("jwt-1");
    expect(request?.headers.get("authorization")).toBeNull();
    expect(await request?.text()).toBe("abc");
  });

  it("hashes an empty body when there is none", async () => {
    const { sent, baseFetch } = recorder();
    const signedFetch = createSignedFetch(() => Promise.resolve("jwt-1"), baseFetch);

    await signedFetch(new Request("https://twochi.test/api/health"));

    expect(sent[0]?.headers.get(CONTENT_SHA256_HEADER)).toBe(SHA256_EMPTY);
  });

  it("sends no auth header without a session", async () => {
    const { sent, baseFetch } = recorder();
    const signedFetch = createSignedFetch(() => Promise.resolve(null), baseFetch);

    await signedFetch(new Request("https://twochi.test/api/health"));

    expect(sent[0]?.headers.has(AUTH_HEADER)).toBe(false);
  });

  it("drops an Authorization header the caller set, which CloudFront would overwrite", async () => {
    const { sent, baseFetch } = recorder();
    const signedFetch = createSignedFetch(() => Promise.resolve("jwt-1"), baseFetch);

    await signedFetch(
      new Request("https://twochi.test/api/pings", {
        method: "POST",
        body: "abc",
        headers: { authorization: "Bearer jwt-1" },
      }),
    );

    expect(sent[0]?.headers.get("authorization")).toBeNull();
  });
});
