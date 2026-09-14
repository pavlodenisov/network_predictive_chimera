"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, qs } from "@/lib/api";
import { formatDate, until } from "@/lib/format";

const CITIES = ["", "Bengaluru", "New Delhi"];

export default function EventsPage() {
  const [city, setCity] = useState("");
  const { data, isLoading, error } = useQuery({
    queryKey: ["industry-events", city],
    queryFn: () => api<any>(`/industry-events${qs({ city, upcoming_only: true })}`),
  });

  const rows = data?.items || [];

  return (
    <>
      <div className="pagehead">
        <h1>Events</h1>
        <span className="sub">
          Real, sourced conferences and summits worth attending — every date and venue
          links back to the organizer&rsquo;s own listing. Nothing here is generated.
        </span>
      </div>

      <div className="toolbar">
        {CITIES.map((c) => (
          <span key={c || "all"} className={`tab ${city === c ? "on" : ""}`} onClick={() => setCity(c)}>
            {c || "All cities"}
          </span>
        ))}
      </div>

      {error ? <div className="dim">Couldn&rsquo;t load events: {(error as Error).message}</div> : null}
      {isLoading ? (
        <div className="dim">Loading…</div>
      ) : rows.length ? (
        <div className="card-list">
          {rows.map((e: any) => {
            const sameDay = !e.ends_at || e.ends_at.slice(0, 10) === e.starts_at.slice(0, 10);
            return (
              <div className="card" style={{ padding: 18 }} key={e.id}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "flex-start" }}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontWeight: 700, fontSize: 16 }}>{e.name}</div>
                    <div style={{ color: "var(--ink-dim)", fontSize: 13.5, marginTop: 3 }}>
                      {e.city}
                      {e.country ? `, ${e.country}` : ""} · {formatDate(e.starts_at)}
                      {sameDay ? "" : ` – ${formatDate(e.ends_at)}`}
                    </div>
                    {e.venue ? (
                      <div style={{ color: "var(--ink-faint)", fontSize: 13, marginTop: 2 }}>{e.venue}</div>
                    ) : null}
                  </div>
                  <span className="tag" style={{ whiteSpace: "nowrap" }}>
                    {until(e.starts_at)}
                  </span>
                </div>
                {e.description ? (
                  <div style={{ marginTop: 10, fontSize: 14, color: "var(--ink-dim)" }}>{e.description}</div>
                ) : null}
                {(e.topics || []).length ? (
                  <div style={{ marginTop: 10 }}>
                    {e.topics.map((t: string) => (
                      <span className="tag" key={t}>
                        {t}
                      </span>
                    ))}
                  </div>
                ) : null}
                <div style={{ marginTop: 12, fontSize: 12.5, color: "var(--ink-faint)" }}>
                  Source:{" "}
                  <a href={e.source_url} target="_blank" rel="noreferrer">
                    {e.source_label}
                  </a>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="card empty">No upcoming events on record yet.</div>
      )}
    </>
  );
}
