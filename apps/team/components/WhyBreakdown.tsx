import { eventPhrase, humanize, num } from "@/lib/format";

const DIM_LABEL: Record<string, string> = {
  quality: "Track record",
  fit: "Fit with the thesis",
  timing: "Why now",
  access: "How reachable",
  authority: "Decision authority",
  capital_relevance: "Capital relevance",
  venture_allocation_fit: "Venture allocation fit",
  emerging_manager_fit: "Emerging-manager fit",
  chimera_fit: "Fit with the fund",
  connectivity: "Network reach",
  independent_paths: "Independent paths",
  cross_sector: "Cross-sector reach",
  relationship_freshness: "Relationship freshness",
  intro_track_record: "Intro track record",
  functional: "Functional match",
  seniority: "Seniority match",
  domain: "Domain match",
  stage_experience: "Stage experience",
  operating_experience: "Operating experience",
  execution_evidence: "Execution evidence",
  location: "Location",
  availability_timing: "Availability",
};

function dimLabel(name: string): string {
  return DIM_LABEL[name] || humanize(name);
}

function barWidth(v: number | null | undefined): number {
  if (v === null || v === undefined) return 0;
  return Math.max(0, Math.min(100, v));
}

/** A simplified, plain-language rendering of ScoreSnapshot.contribution_breakdown — the
 * same underlying arithmetic the analyst terminal shows in full, filtered to what
 * actually moved the number and phrased without the raw/norm/weight notation. */
export default function WhyBreakdown({ breakdown }: { breakdown: any }) {
  if (!breakdown?.dimensions) {
    return <div className="dim">No scored snapshot yet.</div>;
  }
  const dims = Object.entries<any>(breakdown.dimensions);

  return (
    <div>
      {dims.map(([dname, d]) => {
        const unknown = d.status === "unknown";
        const features = Object.entries<any>(d.features || {})
          .filter(([, f]) => f.included !== false && f.status !== "unknown" && Math.abs(f.contribution ?? 0) > 0.001)
          .sort((a, b) => Math.abs(b[1].contribution ?? 0) - Math.abs(a[1].contribution ?? 0))
          .slice(0, 6);

        return (
          <div key={dname} style={{ marginBottom: 16 }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
              <span style={{ fontWeight: 700, fontSize: 13.5 }}>{dimLabel(dname)}</span>
              <span className="mono" style={{ fontSize: 13, color: "var(--ink-dim)" }}>
                {unknown ? "unknown" : num(d.weighted, 1)}
              </span>
            </div>
            {!unknown && (
              <div style={{ height: 6, borderRadius: 4, background: "var(--surface-2)", overflow: "hidden", marginBottom: 8 }}>
                <div
                  style={{
                    height: "100%",
                    width: `${barWidth(d.score)}%`,
                    background: "var(--accent)",
                    borderRadius: 4,
                  }}
                />
              </div>
            )}
            {d.access ? (
              <div style={{ fontSize: 12.5, color: "var(--ink-faint)", marginBottom: 6 }}>
                {d.access.hops != null
                  ? `${d.access.hops}-hop ${d.access.strength || ""} path via ${(d.access.node_names || []).join(" → ") || "an unknown contact"}`
                  : "No known path yet"}
              </div>
            ) : null}
            {features.length > 0 ? (
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, color: "var(--ink-dim)" }}>
                {features.map(([fname, f]) => (
                  <li key={fname}>
                    {f.signals?.length ? (
                      <>
                        {eventPhrase(fname)} — {f.signals[0].days_since}d ago
                      </>
                    ) : (
                      humanize(fname)
                    )}
                    {" "}
                    <span className="mono" style={{ color: "var(--ink-faint)" }}>
                      {f.contribution >= 0 ? "+" : ""}
                      {num(f.contribution, 2)}
                    </span>
                  </li>
                ))}
              </ul>
            ) : !unknown ? (
              <div style={{ fontSize: 12.5, color: "var(--ink-faint)" }}>No supporting evidence found.</div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
