"use client";
import { useEffect, useState } from "react";
import { API } from "@/lib/api";

// A free-tier backend can take up to ~60s to wake from idle. The proxy already retries a
// cold 502 server-side; this gives the very first health probe the same patience before
// showing anything alarming, so a cold start reads as "waking up", not "broken".
const RETRY_DELAYS_MS = [1500, 3000, 6000, 12000, 20000];

export default function ApiBanner() {
  const [state, setState] = useState<"checking" | "waking" | "ok" | "down">("checking");

  useEffect(() => {
    let cancelled = false;

    async function probe() {
      for (let attempt = 0; attempt <= RETRY_DELAYS_MS.length; attempt++) {
        try {
          const res = await fetch(`${API}/health`, { cache: "no-store" });
          if (cancelled) return;
          if (res.ok) return setState("ok");
        } catch {
          if (cancelled) return;
        }
        if (attempt < RETRY_DELAYS_MS.length) {
          setState("waking");
          await new Promise((r) => setTimeout(r, RETRY_DELAYS_MS[attempt]));
        }
      }
      if (!cancelled) setState("down");
    }

    probe();
    return () => {
      cancelled = true;
    };
  }, []);

  if (state === "ok" || state === "checking") return null;

  if (state === "waking") {
    return (
      <div
        style={{
          background: "#2a2410",
          borderBottom: "1px solid var(--warn)",
          color: "#f0d998",
          padding: "6px 14px",
          fontSize: 12,
        }}
      >
        Waking up the backend (free-tier instances sleep when idle) — this can take up to a
        minute on the first load. Retrying automatically…
      </div>
    );
  }

  return (
    <div
      style={{
        background: "#3d1a1a",
        borderBottom: "1px solid var(--neg)",
        color: "#ffd7d5",
        padding: "6px 14px",
        fontSize: 12,
      }}
    >
      Backend not reachable. Set <code className="mono">API_BASE_URL</code> on this web
      service to the FastAPI host and redeploy — the UI is a client of that API and has no
      data of its own.
    </div>
  );
}
