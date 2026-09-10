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

async function handle(req: NextRequest, path: string[]): Promise<Response> {
  const target = `${backendBase()}/${path.map(encodeURIComponent).join("/")}${req.nextUrl.search}`;

  const headers = new Headers();
  req.headers.forEach((v, k) => {
    if (!HOP_BY_HOP.has(k.toLowerCase())) headers.set(k, v);
  });

  const method = req.method.toUpperCase();
  const body =
    method === "GET" || method === "HEAD" ? undefined : Buffer.from(await req.arrayBuffer());

  let upstream: Response;
  try {
    upstream = await fetch(target, { method, headers, body, redirect: "manual" });
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
