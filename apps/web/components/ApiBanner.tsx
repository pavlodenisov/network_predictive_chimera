"use client";
import { useEffect, useState } from "react";
import { API } from "@/lib/api";

/** Shows a fix-it banner when the FastAPI backend can't be reached through the proxy —
 *  e.g. API_BASE_URL is unset/wrong on the web service, or the API host is down. */
export default function ApiBanner() {
  const [state, setState] = useState<"checking" | "ok" | "down">("checking");

  useEffect(() => {
    let cancelled = false;
    fetch(`${API}/health`, { cache: "no-store" })
      .then((r) => !cancelled && setState(r.ok ? "ok" : "down"))
      .catch(() => !cancelled && setState("down"));
    return () => {
      cancelled = true;
    };
  }, []);

  if (state !== "down") return null;
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
