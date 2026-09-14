"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { api } from "@/lib/api";
import { ago, classLabel, eventPhrase, factValueText, formatDate, humanize, num, truncate } from "@/lib/format";
import ActionBadge from "@/components/ActionBadge";
import WhyBreakdown from "@/components/WhyBreakdown";

export default function PersonPage({ params }: { params: { id: string } }) {
  const id = params.id;
  const person = useQuery({ queryKey: ["person", id], queryFn: () => api<any>(`/people/${id}`) });
  const scores = useQuery({ queryKey: ["person", id, "scores"], queryFn: () => api<any>(`/people/${id}/scores`) });
  const facts = useQuery({ queryKey: ["person", id, "facts"], queryFn: () => api<any>(`/people/${id}/facts`) });
  const events = useQuery({ queryKey: ["person", id, "events"], queryFn: () => api<any>(`/people/${id}/events`) });
  const employment = useQuery({
    queryKey: ["person", id, "employment"],
    queryFn: () => api<any>(`/people/${id}/employment`),
  });
  const education = useQuery({
    queryKey: ["person", id, "education"],
    queryFn: () => api<any>(`/people/${id}/education`),
  });
  const activity = useQuery({
    queryKey: ["person", id, "activity"],
    queryFn: () => api<any>(`/people/${id}/activity`),
  });

  const [model, setModel] = useState<string | null>(null);

  if (person.error) return <div className="dim">Couldn&rsquo;t load this person: {(person.error as Error).message}</div>;
  const p = person.data;
  if (!p) return <div className="dim">Loading…</div>;

  const availableModels = Object.keys(p.scores || {});
  const activeModel = model && availableModels.includes(model) ? model : availableModels[0] || null;
  const s = activeModel ? p.scores[activeModel] : null;

  const scoreRows: any[] = scores.data?.items || [];
  const latestSnap = scoreRows
    .filter((r) => r.model === activeModel)
    .sort((a, b) => a.scored_at.localeCompare(b.scored_at))
    .at(-1);

  const seenFactTypes = new Set<string>();
  const knownFacts = (facts.data?.items || []).filter((f: any) => {
    if (f.value?.status === "unknown" || seenFactTypes.has(f.fact_type)) return false;
    seenFactTypes.add(f.fact_type);
    return true;
  });

  return (
    <>
      <div className="pagehead">
        <Link href="/people">← Everyone</Link>
      </div>

      <div className="card detail-head">
        <div>
          <div className="name">{p.name}</div>
          <div className="meta">
            {(p.classes || []).map((c: string) => classLabel(c)).join(" · ") || "Unclassified"}
            {p.primary_location ? ` · ${p.primary_location}` : " · location unknown"}
          </div>
          {p.current_role ? (
            <div className="meta">
              {p.current_role.title} at {p.current_role.company}
            </div>
          ) : p.previous_role ? (
            <div className="meta">
              Previously {p.previous_role.title} at {p.previous_role.company}
              {p.previous_role.ended_at ? ` (until ${p.previous_role.ended_at})` : ""}
            </div>
          ) : (
            <div className="meta">Current role unknown</div>
          )}
        </div>
        {s ? (
          <div className="score">
            <div className="num">{num(s.priority, 0)}</div>
            <div className="lbl">{activeModel} score</div>
            <div style={{ marginTop: 8 }}>
              <ActionBadge action={s.action} />
            </div>
          </div>
        ) : null}
      </div>

      {availableModels.length > 1 ? (
        <div className="toolbar" style={{ marginTop: -10 }}>
          {availableModels.map((m) => (
            <span key={m} className={`tab ${m === activeModel ? "on" : ""}`} onClick={() => setModel(m)}>
              {m} · {num(p.scores[m].priority, 0)}
            </span>
          ))}
        </div>
      ) : null}

      <div className="two-col">
        <div className="card" style={{ padding: 18 }}>
          <h3 style={{ fontSize: 14, marginBottom: 10 }}>How confident are we</h3>
          <div className="kv-row">
            <span className="k">Confidence</span>
            <span className="v">{s ? num(s.confidence, 2) : "—"} (separate from the score)</span>
          </div>
          <div className="kv-row">
            <span className="k">Rank</span>
            <span className="v">
              {s?.rank != null ? `#${s.rank}` : "—"}
              {latestSnap?.percentile != null ? ` · ${num(latestSnap.percentile, 0)}th percentile` : ""}
            </span>
          </div>
          <div className="kv-row">
            <span className="k">Change this week</span>
            <span className="v">{s?.weekly_delta != null ? (s.weekly_delta >= 0 ? "+" : "") + num(s.weekly_delta, 1) : "—"}</span>
          </div>
        </div>

        <div className="card" style={{ padding: 18 }}>
          <h3 style={{ fontSize: 14, marginBottom: 10 }}>How to reach them</h3>
          {p.strongest_path && p.strongest_path.status !== "unknown" ? (
            <>
              <div style={{ fontSize: 14, marginBottom: 6 }}>
                {(() => {
                  // node_names is the full path INCLUDING the target as the last entry —
                  // the people to actually go THROUGH are everyone before that.
                  const via = (p.strongest_path.node_names || []).slice(0, -1);
                  return via.length ? `Through ${via.join(", then ")}` : "A direct connection";
                })()}{" "}
                — {p.strongest_path.hops}-hop, {(p.strongest_path.relationship_strength || "").toLowerCase()} connection.
              </div>
              <div style={{ fontSize: 12.5, color: "var(--ink-faint)" }}>
                Last verified {ago(p.strongest_path.last_verified_at)}
              </div>
            </>
          ) : (
            <div className="unknown">No known path from Chimera yet.</div>
          )}
        </div>
      </div>

      <div className="two-col">
        <div className="card" style={{ padding: 18 }}>
          <h3 style={{ fontSize: 14, marginBottom: 10 }}>Employment history</h3>
          {(employment.data?.items || []).length ? (
            employment.data.items.map((e: any) => (
              <div className="kv-row" key={e.id}>
                <span className="k">
                  {e.title || "Unknown title"} at {e.company || "Unknown company"}
                </span>
                <span className="v">
                  {e.current
                    ? `Since ${formatDate(e.started_at)} · Current`
                    : e.started_at || e.ended_at
                      ? `${formatDate(e.started_at)} – ${formatDate(e.ended_at)}`
                      : "dates unknown"}
                </span>
              </div>
            ))
          ) : (
            <div className="unknown">No employment history on record yet.</div>
          )}
        </div>

        <div className="card" style={{ padding: 18 }}>
          <h3 style={{ fontSize: 14, marginBottom: 10 }}>Education</h3>
          {(education.data?.items || []).length ? (
            education.data.items.map((e: any) => (
              <div className="kv-row" key={e.id}>
                <span className="k">{e.institution || "Unknown institution"}</span>
                <span className="v">{[e.degree, e.field].filter(Boolean).join(", ") || "—"}</span>
              </div>
            ))
          ) : (
            <div className="unknown">No education on record yet.</div>
          )}
        </div>
      </div>

      <div className="section">
        <h2>Recent activity</h2>
        {(events.data?.items || []).length ? (
          <div className="card timeline" style={{ padding: "6px 18px" }}>
            {(events.data.items || []).slice(0, 8).map((e: any) => (
              <div className="item" key={e.id}>
                <div className="dot" />
                <div className="text">
                  {eventPhrase(e.type)}
                  {e.organization ? ` — ${e.organization}` : ""}
                </div>
                <div className="when">{ago(e.occurred_at || e.detected_at)}</div>
              </div>
            ))}
          </div>
        ) : (
          <div className="card empty">No recent activity detected.</div>
        )}
      </div>

      <div className="section">
        <h2>In their own words</h2>
        <div className="card" style={{ padding: "6px 18px" }}>
          {(activity.data?.items || []).length ? (
            activity.data.items.map((a: any) => (
              <div className="evidence-row" key={a.id}>
                {a.title ? <div className="ft">{a.title}</div> : null}
                <blockquote>{truncate(a.text, 500)}</blockquote>
                <div className="src">
                  {ago(a.observed_at)}
                  {a.source_url ? (
                    <>
                      {" · "}
                      <a href={a.source_url} target="_blank" rel="noreferrer">
                        view source
                      </a>
                    </>
                  ) : null}
                </div>
              </div>
            ))
          ) : (
            <div className="empty">No activity or news mentions on record yet.</div>
          )}
        </div>
      </div>

      {(p.inferences || []).length > 0 ? (
        <div className="section">
          <h2>Possible, not confirmed</h2>
          <div className="card" style={{ padding: "6px 18px" }}>
            {p.inferences.map((i: any) => (
              <div className="kv-row" key={i.id}>
                <span className="k">{humanize(i.type)}</span>
                <span className="v">{Math.round(i.probability * 100)}% likely</span>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      <div className="section">
        <h2>What we know</h2>
        <div className="card" style={{ padding: "6px 18px" }}>
          {knownFacts.length ? (
            knownFacts.slice(0, 10).map((f: any) => (
              <div className="kv-row" key={f.id}>
                <span className="k">{humanize(f.fact_type)}</span>
                <span className="v">{factValueText(f.value?.value)}</span>
              </div>
            ))
          ) : (
            <div className="empty">Nothing on record yet.</div>
          )}
          <details className="why">
            <summary>Why this score</summary>
            <div style={{ marginTop: 12 }}>
              {latestSnap ? (
                <WhyBreakdown breakdown={latestSnap.contribution_breakdown} />
              ) : (
                <div className="dim">No scored snapshot for this model yet.</div>
              )}
            </div>
          </details>
        </div>
      </div>
    </>
  );
}
