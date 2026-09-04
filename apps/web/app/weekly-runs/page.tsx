"use client";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/lib/api";


export default function WeeklyRunsPage() {
  const { data, isLoading } = useQuery({ queryKey: ["weekly-runs"], queryFn: () => api<any>("/weekly-runs") });
  const [sel, setSel] = useState<string | null>(null);
  const detail = useQuery({
    queryKey: ["weekly-run", sel],
    queryFn: () => api<any>(`/weekly-runs/${sel}`),
    enabled: !!sel,
  });
  const runs = data?.items || [];

  return (
    <>
      <div className="pagehead">
        <h2>Weekly Runs</h2>
        <span className="sub">the scheduled job runs the identical pipeline as a manual run</span>
      </div>
      {isLoading ? <div className="dim">loading…</div> : null}
      <div className="scroll-x">
        <table className="grid">
          <thead>
            <tr>
              <th className="l">started</th>
              <th className="l">as of</th>
              <th className="l">status</th>
              <th className="num">obs</th>
              <th className="num">updated</th>
              <th className="num">discovered</th>
              <th className="num">events</th>
              <th className="num">facts</th>
              <th className="l">models</th>
              <th className="l">code</th>
              <th className="l"></th>
            </tr>
          </thead>
          <tbody>
            {runs.map((r: any) => (
              <tr key={r.id}>
                <td className="l">{r.started_at?.slice(0, 16).replace("T", " ")}</td>
                <td className="l">{r.as_of_date}</td>
                <td className={r.status === "success" ? "l pos" : "l warn"}>{r.status}</td>
                <td className="num">{r.observations_ingested}</td>
                <td className="num">{r.people_updated}</td>
                <td className="num">{r.people_discovered}</td>
                <td className="num">{r.events_created}</td>
                <td className="num">{r.facts_created}</td>
                <td className="l faint">{(r.scoring_models_run || []).join(",")}</td>
                <td className="l faint">{r.code_version}</td>
                <td className="l">
                  <button className="link" onClick={() => setSel(r.id)}>
                    audit trail
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {sel && detail.data ? (
        <div className="panel">
          <h3>Run {sel.slice(0, 8)} · {detail.data.status}</h3>
          <div className="grid2">
            <div>
              <h3>Stage stats</h3>
              <table className="grid">
                <thead>
                  <tr>
                    <th className="l">stage</th>
                    <th className="num">count</th>
                    <th className="num">ms</th>
                    <th className="num">warn</th>
                  </tr>
                </thead>
                <tbody>
                  {(detail.data.stage_stats || []).map((s: any, i: number) => (
                    <tr key={i}>
                      <td className="l">{s.stage}</td>
                      <td className="num">{s.count}</td>
                      <td className="num">{s.duration_ms}</td>
                      <td className="num">{(s.warnings || []).length}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div>
              <h3>Source coverage</h3>
              <table className="grid">
                <thead>
                  <tr>
                    <th className="l">source</th>
                    <th className="l">status</th>
                    <th className="num">records</th>
                  </tr>
                </thead>
                <tbody>
                  {(detail.data.source_coverage || []).map((s: any, i: number) => (
                    <tr key={i}>
                      <td className="l">{s.source}</td>
                      <td className={s.status === "successful" ? "l pos" : "l warn"}>{s.status}</td>
                      <td className="num">{s.records}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {(detail.data.warnings || []).length ? (
                <div className="warn" style={{ marginTop: 8 }}>
                  {(detail.data.warnings || []).map((w: string, i: number) => (
                    <div key={i}>{w}</div>
                  ))}
                </div>
              ) : null}
            </div>
          </div>
          <h3 style={{ marginTop: 12 }}>Digest</h3>
          <pre className="mono faint" style={{ whiteSpace: "pre-wrap", fontSize: 11, margin: 0 }}>
            {JSON.stringify(detail.data.digest, null, 1)}
          </pre>
        </div>
      ) : null}
    </>
  );
}
