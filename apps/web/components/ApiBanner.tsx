"use client";
import { useEffect, useState } from "react";
import { API } from "@/lib/api";

/** Shows a fix-it banner when the FastAPI backend is unreachable — e.g. a Vercel deploy
 *  where NEXT_PUBLIC_API_BASE_URL isn't set, or the API host isn't running. */
export default function ApiBanner() {
  const [state, setState] = useState<"checking" | "ok" | "down">("checking");

  useEffect(() => {
    const ctrl = new AbortController();
    fetch(`${API}/health`, { signal: ctrl.signal, cache: "no-store" })
      .then((r) => setState(r.ok ? "ok" : "down"))
      .catch(() => setState("down"));
    return () => ctrl.abort();
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
      Backend not reachable at <code className="mono">{API}</code>. Set{" "}
      <code className="mono">NEXT_PUBLIC_API_BASE_URL</code> to a running FastAPI host and
      redeploy — the UI is a client of that API and has no data of its own.
    </div>
  );
}
