import { NextRequest } from "next/server";

// Same-origin proxy to the FastAPI backend. The browser only ever talks to this Next.js
// server, so there is NO build-time API URL to bake and NO cross-origin CORS. The backend
// location is read at RUNTIME from API_BASE_URL (works with Render/Railway/Fly linked env
// vars, unlike NEXT_PUBLIC_* which is frozen at build time). Defaults to localhost for
// `npm run dev`.
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

function backendBase(): string {
  let raw = (process.env.API_BASE_URL || "http://localhost:8000").trim();
  if (!/^https?:\/\//i.test(raw)) {
    // scheme-less value: an internal `host:port` (private networking) → http,
    // a public hostname (e.g. foo.onrender.com) → https.
    const internal = /:\d+$/.test(raw) || !raw.includes(".") || raw.startsWith("localhost");
    raw = `${internal ? "http" : "https"}://${raw}`;
  }
  return raw.replace(/\/+$/, "");
}

const HOP_BY_HOP = new Set(["host", "connection", "content-length", "accept-encoding"]);

// A free-tier backend asleep can take 30-60s to wake, which sometimes outruns the
// platform's own gateway timeout (it serves a 502 before the app finishes booting). Retry
// transparently — only for safe/idempotent methods — so the caller never sees that first
// cold 502; they just get a slightly slower first response.
const RETRY_DELAYS_MS = [3000, 6000, 12000];
const RETRYABLE_STATUS = new Set([502, 503, 504]);

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function fetchWithWakeupRetry(
  target: string,
  init: RequestInit,
  retry: boolean,
): Promise<Response> {
  // Next.js patches the global `fetch` with its own caching/dedup layer; `cache: "no-store"`
  // opts a call out of that entirely (documented escape hatch) — without it, retrying the
  // same URL in a loop can hang waiting on that layer instead of hitting the network again.
  const reqInit: RequestInit = { ...init, cache: "no-store" };
  let lastError: unknown;
  for (let attempt = 0; attempt <= RETRY_DELAYS_MS.length; attempt++) {
    try {
      const res = await fetch(target, reqInit);
      const isLastAttempt = attempt === RETRY_DELAYS_MS.length;
      if (!retry || !RETRYABLE_STATUS.has(res.status) || isLastAttempt) return res;
      // Drain rather than cancel: some fetch implementations hang on an aborted body.
      await res.arrayBuffer().catch(() => undefined);
    } catch (err) {
      lastError = err;
      if (!retry || attempt === RETRY_DELAYS_MS.length) throw err;
    }
    await sleep(RETRY_DELAYS_MS[attempt]);
  }
  throw lastError; // unreachable, satisfies the type checker
}

async function handle(req: NextRequest, path: string[]): Promise<Response> {
  const target = `${backendBase()}/${path.map(encodeURIComponent).join("/")}${req.nextUrl.search}`;

  const headers = new Headers();
  req.headers.forEach((v, k) => {
    if (!HOP_BY_HOP.has(k.toLowerCase())) headers.set(k, v);
  });

  const method = req.method.toUpperCase();
  const idempotent = method === "GET" || method === "HEAD";
  const body = idempotent ? undefined : Buffer.from(await req.arrayBuffer());

  let upstream: Response;
  try {
    upstream = await fetchWithWakeupRetry(
      target,
      { method, headers, body, redirect: "manual" },
      idempotent,
    );
  } catch (err) {
    return Response.json(
      { detail: `backend unreachable at ${backendBase()}`, error: String(err) },
      { status: 502 },
    );
  }

  // `fetch` already decompressed the body, so the upstream length/encoding headers no
  // longer describe what we forward — dropping them (the runtime sets a correct length)
  // is what keeps large JSON responses from being truncated.
  const out = new Headers(upstream.headers);
  out.delete("content-encoding");
  out.delete("content-length");
  out.delete("transfer-encoding");
  out.set("cache-control", "no-store");
  return new Response(upstream.body, { status: upstream.status, headers: out });
}

type Ctx = { params: Promise<{ path: string[] }> } | { params: { path: string[] } };

async function route(req: NextRequest, ctx: Ctx): Promise<Response> {
  const { path } = await (ctx.params as Promise<{ path: string[] }>);
  return handle(req, path ?? []);
}

export {
  route as GET,
  route as POST,
  route as PUT,
  route as PATCH,
  route as DELETE,
  route as OPTIONS,
};
