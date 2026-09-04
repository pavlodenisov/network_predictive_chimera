"use client";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import Link from "next/link";
import { api, qs } from "@/lib/api";
import { Pill } from "@/lib/fmt";

export default function EventsPage() {
  const [type, setType] = useState("");
  const [status, setStatus] = useState("active");
  const { data, isLoading, error } = useQuery({
    queryKey: ["events", type, status],
    queryFn: () => api<any>(`/events${qs({ event_type: type, status, page_size: 200 })}`),
  });
  return (
    <>
      <div className="pagehead">
        <h2>Events</h2>
        <span className="sub">chronological event tape · {data?.total ?? 0} matching</span>
      </div>
      <div className="toolbar">
        <input placeholder="event type" value={type} onChange={(e) => setType(e.target.value)} />
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          {["", "active", "superseded", "retracted", "expired"].map((s) => (
            <option key={s} value={s}>
              {s || "any status"}
            </option>
          ))}
        </select>
      </div>
      {error ? <div className="err">{String((error as Error).message)}</div> : null}
      {isLoading ? (
        <div className="dim">loading…</div>
      ) : (
        <div className="scroll-x">
          <table className="grid">
            <thead>
              <tr>
                <th className="l">detected</th>
                <th className="l">occurred</th>
                <th className="l">person</th>
                <th className="l">event</th>
                <th className="num">confidence</th>
                <th className="l">severity</th>
                <th className="l">org</th>
                <th className="l">status</th>
              </tr>
            </thead>
            <tbody>
              {(data?.items || []).map((e: any) => (
                <tr key={e.id}>
                  <td className="l faint">{e.detected_at?.slice(0, 10)}</td>
                  <td className="l">{e.occurred_at?.slice(0, 10) || "—"}</td>
                  <td className="l">
                    <Link href={`/person/${e.person_id}`}>{e.person}</Link>
                  </td>
                  <td className="l">{e.type}</td>
                  <td className="num">{e.confidence}</td>
                  <td className="l">
                    <Pill>{e.severity}</Pill>
                  </td>
                  <td className="l">{e.organization || "—"}</td>
                  <td className="l">{e.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
