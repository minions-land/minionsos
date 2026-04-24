/**
 * Cloudflare Worker — HTTPS + CORS proxy for EACN API.
 *
 * Solves two problems:
 *   1. Mixed content: GitHub Pages (HTTPS) cannot fetch from HTTP API
 *   2. CORS: Browser blocks cross-origin requests without proper headers
 *
 * Deploy:
 *   npx wrangler deploy
 *
 * Usage:
 *   https://<your-worker>.workers.dev/health
 *   → proxies to http://175.102.130.69:37892/health
 */

const UPSTREAM = "http://175.102.130.69:37892";

export default {
  async fetch(request) {
    // Handle CORS preflight
    if (request.method === "OPTIONS") {
      return new Response(null, {
        status: 204,
        headers: corsHeaders(),
      });
    }

    // Build upstream URL — strip the worker's origin, keep the path + query
    const url = new URL(request.url);
    const upstream = UPSTREAM + url.pathname + url.search;

    try {
      const resp = await fetch(upstream, {
        method: request.method,
        headers: {
          "Content-Type": "application/json",
        },
        body: request.method !== "GET" && request.method !== "HEAD"
          ? await request.text()
          : undefined,
      });

      // Clone response and add CORS headers
      const body = await resp.arrayBuffer();
      return new Response(body, {
        status: resp.status,
        headers: {
          ...Object.fromEntries(resp.headers.entries()),
          ...corsHeaders(),
        },
      });
    } catch (err) {
      return new Response(JSON.stringify({ error: "Upstream unreachable" }), {
        status: 502,
        headers: { "Content-Type": "application/json", ...corsHeaders() },
      });
    }
  },
};

function corsHeaders() {
  return {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
  };
}
