// Viewer request on the default behavior (cloudfront-js-2.0). A path whose last segment
// has no extension is a route of the PWA, so it gets index.html and the router takes
// over; files such as the hashed assets pass unchanged. Custom error responses would do
// the same but for the whole distribution, rewriting the problem+json errors of /api/*,
// which has its own behavior and never runs this function. What still lands here under
// /api (no trailing slash, or another case, since path patterns are case-sensitive) is
// left alone: an API client must get an error, never the PWA with a 200.
function handler(event) {
  var request = event.request;
  var uri = request.uri;
  var lower = uri.toLowerCase();
  if (lower === "/api" || lower.indexOf("/api/") === 0) {
    return request;
  }
  var lastSegment = uri.slice(uri.lastIndexOf("/") + 1);
  if (lastSegment.indexOf(".") === -1) {
    request.uri = "/index.html";
  }
  return request;
}
