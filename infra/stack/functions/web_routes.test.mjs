// Runs with `node --test` from `just check-infra`. The function is plain cloudfront-js,
// with no exports, so the test evaluates its source and takes `handler` from it.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import vm from "node:vm";

const source = readFileSync(new URL("./web_routes.js", import.meta.url), "utf8");
const handler = vm.runInNewContext(`${source}\nhandler;`);

function uriFor(uri) {
  const request = { method: "GET", uri, querystring: {}, headers: {}, cookies: {} };
  return handler({ version: "1.0", context: {}, viewer: {}, request }).uri;
}

test("front routes get index.html", () => {
  for (const uri of ["/", "/pet", "/pet/", "/pet/history", "/v1.2/pet"]) {
    assert.equal(uriFor(uri), "/index.html", uri);
  }
});

test("files with an extension pass unchanged", () => {
  for (const uri of [
    "/index.html",
    "/assets/index-1a2b3c.js",
    "/assets/index-1a2b3c.css",
    "/manifest.webmanifest",
    "/favicon.ico",
    "/sw.js",
  ]) {
    assert.equal(uriFor(uri), uri, uri);
  }
});
