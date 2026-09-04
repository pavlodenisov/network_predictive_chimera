"use client";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
import { Delta, Pill, Val, ago } from "@/lib/fmt";
import { ScoreDecomposition } from "@/components/ScoreDecomposition";

export default function PersonPage({ params }: { params: { id: string } }) {
  const id = params.id;
  const person = useQuery({ queryKey: ["person", id], queryFn: () => api<any>(`/people/${id}`) });
  const scores = useQuery({ queryKey: ["person", id, "scores"], queryFn: () => api<any>(`/people/${id}/scores`) });
  const facts = useQuery({ queryKey: ["person", id, "facts"], queryFn: () => api<any>(`/people/${id}/facts`) });
  const events = useQuery({ queryKey: ["person", id, "events"], queryFn: () => api<any>(`/people/${id}/events`) });
  const rels = useQuery({ queryKey: ["person", id, "rels"], queryFn: () => api<any>(`/people/${id}/relationships`) });
  const features = useQuery({ queryKey: ["person", id, "features"], queryFn: () => api<any>(`/people/${id}/features`) });

  const [model, setModel] = useState("founder");

  if (person.error) return <div className="err">{String((person.error as Error).message)}</div>;
  const p = person.data;
  if (!p) return <div className="dim">loading…</div>;

  const scoreRows: any[] = scores.data?.items || [];
  const modelRows = scoreRows.filter((s) => s.model === model).sort((a, b) => a.scored_at.localeCompare(b.scored_at));
  const latest = modelRows[modelRows.length - 1];
  const s = p.scores?.[model];
  const availableModels = Object.keys(p.scores || {});

  return (
    <>
      <div className="crumbs">
        <Link href="/">Intelligence</Link> / {p.name}
      </div>

      <div className="pagehead">
        <h2>{p.name}</h2>
        <span className="sub">
          {(p.classes || []).map((c: string) => (
            <Pill key={c}>{c}</Pill>
          ))}
          {" "}
          {p.primary_location || "location unknown"} · entity resolution {p.entity_resolution_status}
        </span>
      </div>

      <div className="grid2">
        <div className="panel">
          <h3>Header</h3>
          <div className="kv">
            <span className="k">{model} priority</span>
            <span className="v big">{s ? s.priority.toFixed(1) : "—"}</span>
            <span className="k">rank</span>
            <span className="v">
              #{s?.rank ?? "—"} {latest?.percentile != null ? `· ${latest.percentile.toFixed(1)}th pct` : ""}
            </span>
            <span className="k">weekly Δ</span>
            <span className="v">
              <Delta v={s?.weekly_delta} />
            </span>
            <span className="k">confidence</span>
            <span className="v">{s ? s.confidence.toFixed(2) : "—"} (separate from priority)</span>
            <span className="k">action</span>
            <span className="v">
              {s?.action ? <Pill act>{s.action}</Pill> : "—"} {(s?.reason_codes || []).join(" · ")}
            </span>
            <span className="k">current role</span>
            <span className="v">
              {p.current_role ? `${p.current_role.title} @ ${p.current_role.company}` : <span className="unknown">unknown</span>}
            </span>
            <span className="k">previous role</span>
            <span className="v">
              {p.previous_role
                ? `${p.previous_role.title} @ ${p.previous_role.company} (ended ${p.previous_role.ended_at || "?"})`
                : "—"}
            </span>
          </div>
        </div>

        <div className="panel">
          <h3>Warm paths</h3>
          {p.strongest_path ? (
            <div className="kv">
              <span className="k">strongest path</span>
              <span className="v">
                {p.strongest_path.status === "unknown" ? (
                  <span className="unknown">unknown</span>
                ) : (
                  `${p.strongest_path.hops}-hop ${p.strongest_path.relationship_strength} · score ${p.strongest_path.score}`
                )}
              </span>
              <span className="k">path</span>
              <span className="v">{(p.strongest_path.node_names || []).join(" → ") || "—"}</span>
              <span className="k">last verified</span>
              <span className="v">{ago(p.strongest_path.last_verified_at)}</span>
            </div>
          ) : (
            <div className="faint">no known path from a Chimera node</div>
          )}
        </div>
      </div>

      <div className="panel">
        <h3>Score decomposition — why is {p.name} ranked #{s?.rank ?? "?"}</h3>
        <div className="toolbar">
          {availableModels.map((m) => (
            <span key={m} className={m === model ? "chip on" : "chip"} onClick={() => setModel(m)}>
              {m} {p.scores[m].priority.toFixed(1)}
            </span>
          ))}
        </div>
        {latest ? (
          <ScoreDecomposition breakdown={latest.contribution_breakdown} delta={latest.delta_breakdown} />
        ) : (
          <div className="faint">no {model} snapshot</div>
        )}
      </div>

      <div className="grid2">
        <div className="panel">
          <h3>Score history ({model})</h3>
          <table className="grid">
            <thead>
              <tr>
                <th className="l">as of</th>
                <th className="num">priority</th>
                <th className="num">Δ</th>
                <th className="num">conf</th>
                <th className="num">rank</th>
              </tr>
            </thead>
            <tbody>
              {modelRows.map((r) => (
                <tr key={r.id}>
                  <td className="l">{r.as_of_date}</td>
                  <td className="num">{r.priority_score?.toFixed(1)}</td>
                  <td className="num">
                    <Delta v={r.delta_breakdown?.priority_delta} />
                  </td>
                  <td className="num">{r.confidence_score?.toFixed(2)}</td>
                  <td className="num">{r.rank ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="panel">
          <h3>Inferences (labelled — not facts)</h3>
          {(p.inferences || []).length === 0 ? (
            <div className="faint">none</div>
          ) : (
            <table className="grid">
              <thead>
                <tr>
                  <th className="l">type</th>
                  <th className="num">probability</th>
                  <th className="l">model</th>
                  <th className="l">explanation</th>
                </tr>
              </thead>
              <tbody>
                {p.inferences.map((i: any) => (
                  <tr key={i.id}>
                    <td className="l">{i.type}</td>
                    <td className="num">{i.probability}</td>
                    <td className="l faint">{i.model_version}</td>
                    <td className="l faint">{i.explanation_code}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      <div className="panel">
        <h3>Events</h3>
        <table className="grid">
          <thead>
            <tr>
              <th className="l">type</th>
              <th className="l">occurred</th>
              <th className="l">detected</th>
              <th className="num">confidence</th>
              <th className="l">severity</th>
              <th className="l">org</th>
              <th className="l">status</th>
            </tr>
          </thead>
          <tbody>
            {(events.data?.items || []).map((e: any) => (
              <tr key={e.id}>
                <td className="l">{e.type}</td>
                <td className="l">{e.occurred_at?.slice(0, 10) || "—"}</td>
                <td className="l faint">{e.detected_at?.slice(0, 10)}</td>
                <td className="num">{e.confidence}</td>
                <td className="l">{e.severity}</td>
                <td className="l">{e.organization || "—"}</td>
                <td className="l">{e.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="panel">
        <h3>Evidence — facts trace to an immutable source record</h3>
        <div className="tree">
          {(facts.data?.items || []).map((f: any) => (
            <details key={f.id}>
              <summary>
                <span className="lbl">
                  <Pill>fact</Pill> {f.fact_type}
                </span>{" "}
                <span className="mono">{JSON.stringify(f.value)}</span>
                <span className="faint"> · {f.extraction_method} · conf {f.extraction_confidence}</span>
              </summary>
              {(f.evidence || []).map((ev: any) => (
                <details key={ev.id}>
                  <summary>
                    <span className="lbl">
                      <Pill>evidence</Pill> {ev.source_label} · strength {ev.evidence_strength}
                    </span>
                    {ev.quoted_fragment ? <span className="faint"> “{ev.quoted_fragment.slice(0, 90)}”</span> : null}
                  </summary>
                  {ev.observation ? (
                    <div className="row" style={{ display: "block" }}>
                      <div className="lbl">
                        <Pill>raw observation</Pill> {ev.observation.content_type} · observed{" "}
                        {ev.observation.observed_at?.slice(0, 10)} · ingested {ev.observation.ingested_at?.slice(0, 10)}
                      </div>
                      <pre className="mono faint" style={{ whiteSpace: "pre-wrap", margin: "4px 0", fontSize: 11 }}>
                        {ev.observation.raw_text || JSON.stringify(ev.observation.raw_json, null, 1)}
                      </pre>
                      {ev.observation.source_url ? (
                        <a href={ev.observation.source_url} target="_blank" rel="noreferrer">
                          {ev.observation.source_url}
                        </a>
                      ) : null}
                    </div>
                  ) : (
                    <div className="row faint">observation not retained</div>
                  )}
                </details>
              ))}
              {(f.evidence || []).length === 0 ? <div className="row err">no evidence — provenance violation</div> : null}
            </details>
          ))}
        </div>
      </div>

      <div className="grid2">
        <div className="panel">
          <h3>Relationships</h3>
          <table className="grid">
            <thead>
              <tr>
                <th className="l">person</th>
                <th className="l">type</th>
                <th className="l">strength</th>
                <th className="num">conf</th>
                <th className="l">verified</th>
              </tr>
            </thead>
            <tbody>
              {(rels.data?.items || []).map((r: any) => (
                <tr key={r.id}>
                  <td className="l">
                    <Link href={`/person/${r.other_person_id}`}>{r.other_person_name}</Link>
                  </td>
                  <td className="l">{r.relationship_type}</td>
                  <td className="l">{r.relationship_strength}</td>
                  <td className="num">{r.confidence ?? "—"}</td>
                  <td className="l faint">{ago(r.last_verified_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="panel">
          <h3>Data gaps</h3>
          {(features.data?.items || []).slice(0, 1).map((fs: any) => (
            <div key={fs.id}>
              <div className="faint" style={{ marginBottom: 4 }}>
                {fs.model_target} feature set {fs.feature_set_version} · as of {fs.as_of_date}
              </div>
              <div className="mono" style={{ fontSize: 11.5 }}>
                {(fs.missing_features || []).length
                  ? (fs.missing_features || []).map((m: string) => (
                      <span key={m} className="unknown" style={{ marginRight: 8 }}>
                        {m}
                      </span>
                    ))
                  : "no missing features"}
              </div>
              {Object.entries<any>(fs.data_freshness || {}).some(([, v]) => v?.stale) ? (
                <div style={{ marginTop: 6 }} className="warn">
                  stale:{" "}
                  {Object.entries<any>(fs.data_freshness)
                    .filter(([, v]) => v?.stale)
                    .map(([k, v]) => `${k} (${v.age_days}d)`)
                    .join(", ")}
                </div>
              ) : null}
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
