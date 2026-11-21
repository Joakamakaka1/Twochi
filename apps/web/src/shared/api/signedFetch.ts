// fetch for /api behind CloudFront with OAC on a Lambda Function URL (AWS, «Borde», option 1).
// CloudFront signs the origin request itself, in Authorization, so:
// - the body's SHA-256 goes in x-amz-content-sha256, which the signature covers;
// - the JWT goes in its own header, and any Authorization the caller set is dropped.
// The generated client takes this function as its fetch.

export const AUTH_HEADER = "X-Twochi-Auth";
export const CONTENT_SHA256_HEADER = "x-amz-content-sha256";

export type TokenSource = () => Promise<string | null>;
export type FetchLike = (request: Request) => Promise<Response>;

async function sha256Hex(body: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", body);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export function createSignedFetch(
  token: TokenSource,
  baseFetch: FetchLike = (request) => fetch(request),
): FetchLike {
  return async (request) => {
    const body = await request.clone().arrayBuffer();
    const headers = new Headers(request.headers);
    headers.delete("authorization");
    headers.set(CONTENT_SHA256_HEADER, await sha256Hex(body));
    const jwt = await token();
    if (jwt) headers.set(AUTH_HEADER, jwt);
    return baseFetch(new Request(request, { headers }));
  };
}
